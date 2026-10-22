"""Preview and finish a checkpoint, refusing unknown post-interruption edits."""
from pathlib import Path

from .binding import load_project
from .errors import UamlError
from .formats import (digest, fields, frontmatter, identifier, json_bytes, memory,
                      parse_json, read_bytes, safe_metadata)
from .paths import inside, local_key, require_local_registry, require_private_registry
from .project_memory import validate_checkpoint
from .storage import lock, write


def _read_optional(path):
    try:
        return read_bytes(path)
    except UamlError as exc:
        if exc.code != "MEMORY_MISSING":
            raise
        return None


def inspect(git, registry_path: Path, transaction_id: str):
    identifier(transaction_id)
    require_local_registry(registry_path, git.root)
    require_private_registry(registry_path)
    manifest, _ = load_project(git)
    journal_path = inside(registry_path.parent, f"transactions/{transaction_id}.json")
    raw = read_bytes(journal_path, "TRANSACTION_MISSING")
    value = parse_json(raw)
    if value.get("schema_version") != 2:
        raise UamlError("REPAIR_UNSUPPORTED", "This journal has no verified payloads; inspect old backups manually.")
    fields(value, ("schema_version", "repository_root", "project_id", "binding_fingerprint", "entries",
                   "status", "checkpoint", "previous_hashes", "previous_checkpoint_hash"))
    if (not isinstance(value["repository_root"], str)
            or local_key(Path(value["repository_root"])) != local_key(git.root)
            or value["project_id"] != manifest["project"]["id"]
            or value["binding_fingerprint"] != digest(json_bytes(manifest))):
        raise UamlError("REPAIR_CONFLICT", "Journal identity or binding differs from the current repository.")
    validate_checkpoint(value["checkpoint"], manifest)
    if value["checkpoint"]["snapshot_id"] != transaction_id or value["status"] not in ("prepared", "complete"):
        raise UamlError("SCHEMA_INVALID", "Invalid journal status or snapshot ID.")
    paths = [manifest["memory"][key] for key in ("project_state", "handoff", "checkpoint")]
    if not isinstance(value["entries"], list) or len(value["entries"]) != 3:
        raise UamlError("SCHEMA_INVALID", "Journal must cover exactly the three checkpoint files.")
    prepared, current, actions = {}, {}, []
    for index, entry in enumerate(value["entries"]):
        fields(entry, ("path", "before_hash", "after_hash", "before_blob", "after_blob"))
        if entry["path"] != paths[index] or entry["after_blob"] != f"transactions/{transaction_id}.{index}.after":
            raise UamlError("SCHEMA_INVALID", "Unexpected journal path or payload name.")
        after = read_bytes(inside(registry_path.parent, entry["after_blob"]))
        if digest(after) != entry["after_hash"]:
            raise UamlError("REPAIR_CONFLICT", "Prepared payload hash differs; no repair performed.")
        if entry["before_hash"] is None:
            if entry["before_blob"] is not None:
                raise UamlError("SCHEMA_INVALID", "Unexpected before-image for a new file.")
        else:
            if entry["before_blob"] != f"transactions/{transaction_id}.{index}.before":
                raise UamlError("SCHEMA_INVALID", "Unexpected before-image name.")
            before = read_bytes(inside(registry_path.parent, entry["before_blob"]))
            if digest(before) != entry["before_hash"]:
                raise UamlError("REPAIR_CONFLICT", "Before-image hash differs; inspect backups manually.")
        safe_metadata(after.decode("utf-8-sig"))
        if index < 2:
            header, _ = frontmatter(after)
            memory(header, ("project_state", "handoff")[index], manifest["project"]["id"])
            if header["snapshot_id"] != transaction_id or value["checkpoint"]["files"][entry["path"]] != digest(after):
                raise UamlError("REPAIR_CONFLICT", "Prepared memory does not match its checkpoint.")
        elif parse_json(after) != value["checkpoint"]:
            raise UamlError("REPAIR_CONFLICT", "Prepared checkpoint differs from the journal.")
        existing = _read_optional(inside(git.root, entry["path"]))
        current_hash = digest(existing) if existing is not None else None
        if current_hash != entry["after_hash"] and current_hash != entry["before_hash"]:
            raise UamlError("REPAIR_CONFLICT", "A target was edited after preparation; preserve those edits and review manually.")
        if value["status"] == "complete" and current_hash != entry["after_hash"]:
            raise UamlError("REPAIR_CONFLICT", "This transaction is complete; it cannot overwrite subsequent edits.")
        current[entry["path"]] = current_hash
        prepared[entry["path"]] = after
        actions.append({"path": entry["path"], "action": "keep" if current_hash == entry["after_hash"] else "finish"})
    plan_hash = digest(json_bytes({"journal_hash": digest(raw), "current_hashes": current}))
    plan = {"status": "REPAIR_NOT_NEEDED" if value["status"] == "complete" else "REPAIR_PREVIEW",
            "transaction_id": transaction_id, "plan_hash": plan_hash, "actions": actions,
            "limitations": ["Only finish the saved snapshot; no commands or unsaved information are reconstructed."]}
    return plan, value, raw, journal_path, prepared, current


def repair(git, registry_path: Path, transaction_id: str, apply=False, expected_plan=None):
    if not apply:
        return inspect(git, registry_path, transaction_id)[0]
    if not expected_plan:
        raise UamlError("PLAN_REQUIRED", "Preview repair first, then pass --expect-plan with its plan_hash.")
    with lock(inside(git.root, ".uaml/write.lock")):
        plan, value, raw, journal_path, prepared, current = inspect(git, registry_path, transaction_id)
        if plan["plan_hash"] != expected_plan:
            raise UamlError("WRITE_CONFLICT", "Repair plan changed; preview again before applying.")
        if plan["status"] == "REPAIR_NOT_NEEDED":
            return plan
        # Order is validated: the checkpoint is always published last.
        for relative, data in prepared.items():
            if current[relative] != digest(data):
                write(inside(git.root, relative), data, current[relative], registry_path.parent / "backups")
        value["status"] = "complete"
        write(journal_path, json_bytes(value), digest(raw))
        return {**plan, "status": "REPAIRED"}
