"""Reviewed independent project identity; no inherited Vault read or grants."""
import copy
from pathlib import Path
from uuid import uuid4

from . import registry
from .binding import link_path, load_project
from .errors import UamlError
from .formats import (digest, fields, frontmatter, identifier, json_bytes, markdown, memory, now,
                      parse_json, parse_yaml, project, project_link, public_name, read_bytes, safe_metadata, text, yaml_bytes)
from .paths import inside, local_key, require_local_registry, require_private_registry
from .project_memory import HANDOFF_BODY, STATE_BODY, exclusions, validate_checkpoint
from .storage import lock, write


def target_vault(registry_path, vault_id):
    path = registry.selected(registry.load(registry_path), vault_id)
    metadata = registry.read_vault(path)
    if metadata["vault"]["id"] != vault_id:
        raise UamlError("VAULT_ID_MISMATCH", "Explicit fork target has a different Vault identity.")
    return path, metadata, digest(read_bytes(inside(path, ".uaml/vault.yaml")))


def prepare(git, registry_path: Path, name: str, vault_id: str):
    public_name(name)
    identifier(vault_id)
    require_local_registry(registry_path, git.root)
    require_private_registry(registry_path)
    old_manifest, _ = load_project(git)
    # Only the explicit target is inspected; never resolve the inherited binding.
    vault_path, vault_metadata, vault_hash = target_vault(registry_path, vault_id)
    if git.root.is_relative_to(vault_path) or vault_path.is_relative_to(git.root):
        raise UamlError("UNSAFE_PATH", "Fork target Vault and repository must be separate roots.")
    new = copy.deepcopy(old_manifest)
    new.update(revision=1, project={"id": str(uuid4()), "name": name},
               binding={"vault_id": vault_id, "project_memory_id": str(uuid4())})
    new.pop("repository", None)  # An old canonical URL is not the new fork's URL.
    project(new)
    snapshot_id, time = str(uuid4()), now()
    snapshot = git.observe(exclusions(new))["snapshot"]
    after = {}
    for key, kind, body in (("project_state", "project_state", STATE_BODY), ("handoff", "handoff", HANDOFF_BODY)):
        header = {"schema_version": 1, "kind": kind, "revision": 1, "project_id": new["project"]["id"],
                  "snapshot_id": snapshot_id, "updated_at": time, "source_agent": "uaml-fork", "git": snapshot}
        after[new["memory"][key]] = markdown(header, body)
    checkpoint = {"schema_version": 1, "project_id": new["project"]["id"], "snapshot_id": snapshot_id,
                  "updated_at": time, "files": {path: digest(data) for path, data in after.items()}}
    after[new["memory"]["checkpoint"]] = json_bytes(checkpoint)
    after[".uaml/project.yaml"] = yaml_bytes(new)  # Identity switches last.
    fork_id, entries = str(uuid4()), []
    for index, (relative, data) in enumerate(after.items()):
        old = read_bytes(inside(git.root, relative))
        safe_metadata(text(old))
        for suffix, payload in (("before", old), ("after", data)):
            write(inside(registry_path.parent, f"forks/{fork_id}.{index}.{suffix}"), payload, None)
        entries.append({"path": relative, "before_hash": digest(old), "after_hash": digest(data)})
    link = {"schema_version": 1, "kind": "project_link", "revision": 1, "project_id": new["project"]["id"],
            **new["binding"], "project_name": name, "state_authority": "repository", "knowledge_ids": []}
    link_bytes = markdown(link, "# Independent fork\n\nState is authoritative in the new repository; no inherited knowledge links.\n")
    if link_path(vault_path, vault_metadata, new).exists():
        raise UamlError("WRITE_CONFLICT", "New project memory location already exists.")
    write(inside(registry_path.parent, f"forks/{fork_id}.link"), link_bytes, None)
    plan = {"schema_version": 1, "kind": "project_fork", "id": fork_id, "git_identity": git.identity(),
            "target_vault_id": vault_id, "target_vault_path": str(vault_path), "vault_hash": vault_hash,
            "source_project_id": old_manifest["project"]["id"], "link_hash": digest(link_bytes), "entries": entries}
    raw = json_bytes(plan)
    write(inside(registry_path.parent, f"forks/{fork_id}.json"), raw, None)
    return inspect(git, registry_path, fork_id)[0]


def inspect(git, registry_path: Path, fork_id: str):
    identifier(fork_id)
    require_local_registry(registry_path, git.root)
    require_private_registry(registry_path)
    raw = read_bytes(inside(registry_path.parent, f"forks/{fork_id}.json"), "FORK_PLAN_MISSING")
    value = parse_json(raw)
    fields(value, ("schema_version", "kind", "id", "git_identity", "target_vault_id", "target_vault_path", "vault_hash", "source_project_id", "link_hash", "entries"))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != "project_fork" or value["id"] != fork_id:
        raise UamlError("SCHEMA_INVALID", "Invalid fork plan.")
    if value["git_identity"] != git.identity():
        raise UamlError("FORK_CONFLICT", "Checkout or Remote changed after fork review.")
    identifier(value["target_vault_id"])
    vault_path, vault_metadata, vault_hash = target_vault(registry_path, value["target_vault_id"])
    if str(vault_path) != value["target_vault_path"] or vault_hash != value["vault_hash"]:
        raise UamlError("FORK_CONFLICT", "Target Vault selection or identity changed after review.")
    if not isinstance(value["entries"], list) or len(value["entries"]) != 4:
        raise UamlError("SCHEMA_INVALID", "A fork plan covers exactly the four UAML files.")
    prepared, originals, current = {}, {}, {}
    for index, entry in enumerate(value["entries"]):
        fields(entry, ("path", "before_hash", "after_hash"))
        if not isinstance(entry["path"], str):
            raise UamlError("SCHEMA_INVALID", "Fork target path must be a string.")
        before = read_bytes(inside(registry_path.parent, f"forks/{fork_id}.{index}.before"))
        after = read_bytes(inside(registry_path.parent, f"forks/{fork_id}.{index}.after"))
        if digest(before) != entry["before_hash"] or digest(after) != entry["after_hash"]:
            raise UamlError("FORK_CONFLICT", "Fork payload changed after preparation.")
        safe_metadata(text(after))
        if entry["path"] in prepared:
            raise UamlError("SCHEMA_INVALID", "Duplicate fork target.")
        prepared[entry["path"]], originals[entry["path"]] = after, before
    new = project(parse_yaml(text(list(prepared.values())[-1])))
    old = project(parse_yaml(text(list(originals.values())[-1])))
    paths = [new["memory"][key] for key in ("project_state", "handoff", "checkpoint")] + [".uaml/project.yaml"]
    if list(prepared) != paths or new["project"]["id"] == old["project"]["id"] or new["binding"]["project_memory_id"] == old["binding"]["project_memory_id"]:
        raise UamlError("SCHEMA_INVALID", "Fork must use new identities and only standard UAML targets.")
    if old["project"]["id"] != value["source_project_id"] or new["binding"]["vault_id"] != value["target_vault_id"]:
        raise UamlError("SCHEMA_INVALID", "Fork identity associations differ.")
    checkpoint = parse_json(prepared[paths[2]])
    validate_checkpoint(checkpoint, new)
    for index, path in enumerate(paths[:2]):
        header, _ = frontmatter(prepared[path])
        memory(header, ("project_state", "handoff")[index], new["project"]["id"])
        if header["snapshot_id"] != checkpoint["snapshot_id"] or checkpoint["files"][path] != digest(prepared[path]):
            raise UamlError("FORK_CONFLICT", "Prepared fork memory is inconsistent.")
    actions = []
    for entry in value["entries"]:
        actual = read_bytes(inside(git.root, entry["path"]))
        current[entry["path"]] = digest(actual)
        if digest(actual) not in (entry["before_hash"], entry["after_hash"]):
            raise UamlError("FORK_CONFLICT", "Managed memory changed after review; preserve edits and prepare a new fork plan.")
        actions.append({"path": entry["path"], "action": "keep" if digest(actual) == entry["after_hash"] else "replace_with_new_identity"})
    link_bytes = read_bytes(inside(registry_path.parent, f"forks/{fork_id}.link"))
    if digest(link_bytes) != value["link_hash"]:
        raise UamlError("FORK_CONFLICT", "New reverse-index payload changed.")
    link_header, _ = frontmatter(link_bytes)
    project_link(link_header, new)
    if link_header["knowledge_ids"]:
        raise UamlError("SCHEMA_INVALID", "Independent forks cannot inherit private knowledge links.")
    target_link = link_path(vault_path, vault_metadata, new)
    link_exists = target_link.exists()
    if link_exists and digest(read_bytes(target_link)) != value["link_hash"]:
        raise UamlError("FORK_CONFLICT", "New reverse index was separately modified.")
    done = all(item["action"] == "keep" for item in actions)
    if done and not link_exists:
        raise UamlError("FORK_CONFLICT", "Completed identity is missing its reverse index; inspect manually.")
    result = {"status": "FORK_ALREADY_APPLIED" if done else "FORK_PREVIEW", "fork_id": fork_id,
              "plan_hash": digest(raw), "project": new["project"], "binding": new["binding"], "actions": actions,
              "next_step": "Applying archives old memory locally, replaces only managed UAML files, creates a blank reverse index and revokes this checkout's grant. Review then trust the new identity separately."}
    return result, value, prepared, current, vault_path, target_link, link_bytes


def apply(git, registry_path: Path, fork_id: str, expected_plan: str):
    if not expected_plan:
        raise UamlError("PLAN_REQUIRED", "Preview the independent fork and pass its plan_hash.")
    preview = inspect(git, registry_path, fork_id)
    if preview[0]["plan_hash"] != expected_plan:
        raise UamlError("WRITE_CONFLICT", "Fork plan does not match the reviewed hash.")
    vault_path = preview[4]
    with lock(inside(git.root, ".uaml/write.lock")), lock(inside(vault_path, ".uaml/write.lock")):
        result, value, prepared, current, current_vault, target_link, link_bytes = inspect(git, registry_path, fork_id)
        if result["plan_hash"] != expected_plan or current_vault != vault_path:
            raise UamlError("WRITE_CONFLICT", "Fork plan changed before locking.")
        if result["status"] == "FORK_ALREADY_APPLIED":
            return result

        def revoke(data):
            data["checkout_grants"] = [grant for grant in data["checkout_grants"]
                                       if local_key(Path(grant["repository_root"])) != local_key(git.root)]

        registry.update(registry_path, revoke)
        if not target_link.exists():
            write(target_link, link_bytes, None)
        for path, content in prepared.items():
            if current[path] != digest(content):
                write(inside(git.root, path), content, current[path], registry_path.parent / "backups")
        return {**result, "status": "FORK_APPLIED"}
