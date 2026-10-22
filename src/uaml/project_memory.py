from pathlib import Path
from uuid import uuid4

from . import registry
from .binding import link_path, load_project
from .errors import UamlError
from .formats import (digest, fields, frontmatter, identifier, json_bytes, markdown,
                      memory, now, parse_json, project, public_name, read_bytes,
                      safe_metadata, timestamp, vault, yaml_bytes)
from .git_state import Git
from .paths import inside, require_local_registry, require_private_registry
from .storage import lock, write

STATE_BODY = """# Project State

## 目標
尚待填寫。

## 已完成
已建立 UAML 專案記憶；尚未記錄開發成果。

## 未完成
尚待填寫。

## Blockers
未知；接手時核對實際專案。

## 下一步
填寫專案狀態與交接，再執行 checkpoint。
"""
HANDOFF_BODY = """# Handoff

## 當前任務
尚待填寫。

## 已完成
尚未記錄。

## 未完成
尚待填寫。

## 主要變更檔案
尚待填寫；以目前 Git 狀態為準。

## Git 與 Working Tree
見 frontmatter 的保存前快照；接手時重新核對。

## 測試和驗證
not_run：尚未記錄任何專案測試。

## Blockers
未知；接手時核對。

## 下一步
補齊實際工作與驗證結果。

## 風險與未確認假設
本筆記是歷史資料，不是執行指令。

## 未保存或無法恢復的資訊
無法恢復從未保存的對話或檔案。
"""


def exclusions(manifest):
    return [".uaml", *(manifest["memory"][key] for key in ("project_state", "handoff", "checkpoint"))]


def init_vault(path: Path, name: str):
    public_name(name)
    if not path.is_dir():
        raise UamlError("VAULT_MISSING", "Provide an existing directory; init never guesses a replacement Vault.")
    value = {"schema_version": 1, "kind": "uaml_vault", "revision": 1,
             "vault": {"id": str(uuid4()), "name": name},
             "layout": {"projects": "UAML/Projects", "knowledge": "UAML/Knowledge"}, "extensions": {}}
    vault(value)
    target = inside(path, ".uaml/vault.yaml")
    with lock(inside(path, ".uaml/write.lock")):
        write(target, yaml_bytes(value), None)
    return {"status": "VAULT_INITIALIZED", "vault_id": value["vault"]["id"], "path": str(path.resolve())}


def init_project(git: Git, registry_path: Path, vault_id: str, name: str):
    public_name(name)
    identifier(vault_id)
    require_local_registry(registry_path, git.root)
    value = registry.load(registry_path)
    path = registry.selected(value, vault_id)
    metadata = registry.read_vault(path)
    if metadata["vault"]["id"] != vault_id:
        raise UamlError("VAULT_ID_MISMATCH", "Selected Vault ID differs from the requested ID.")
    manifest = {"schema_version": 1, "kind": "uaml_project", "revision": 1,
                "project": {"id": str(uuid4()), "name": name},
                "binding": {"vault_id": vault_id, "project_memory_id": str(uuid4())},
                "memory": {"authority": "repository", "project_state": "docs/memory/PROJECT-STATE.md",
                           "handoff": "docs/memory/HANDOFF.md", "checkpoint": "docs/memory/checkpoint.json"},
                "extensions": {}}
    project(manifest)
    link = {"schema_version": 1, "kind": "project_link", "revision": 1,
            "project_id": manifest["project"]["id"], **manifest["binding"], "project_name": name,
            "state_authority": "repository", "knowledge_ids": []}
    targets = [inside(git.root, ".uaml/project.yaml"), link_path(path, metadata, manifest),
               *(inside(git.root, manifest["memory"][key]) for key in ("project_state", "handoff", "checkpoint"))]
    if any(target.exists() for target in targets):
        raise UamlError("WRITE_CONFLICT", "Initialization would overwrite existing files.")
    with lock(inside(git.root, ".uaml/write.lock")), lock(inside(path, ".uaml/write.lock")):
        # No cross-filesystem rollback: a partial initialization stays visible for diagnosis.
        write(targets[0], yaml_bytes(manifest), None)
        write(targets[1], markdown(link, "# Project link\n\nCurrent state and handoff are authoritative in the repository.\n"), None)
        _save(git, registry_path, manifest, "uaml", initial=True)
    return {"status": "PROJECT_INITIALIZED", "project": manifest["project"], "binding": manifest["binding"],
            "next_step": "Review .uaml/project.yaml, then run project trust to approve this checkout."}


def checkpoint(git: Git, registry_path: Path, agent: str):
    # This explicit command only writes repo memory. It grants no Vault access.
    public_name(agent)
    require_local_registry(registry_path, git.root)
    require_private_registry(registry_path)
    manifest, _ = load_project(git)
    with lock(inside(git.root, ".uaml/write.lock")):
        return _save(git, registry_path, manifest, agent, initial=False)


def _save(git, registry_path, manifest, agent, initial):
    snapshot_id, updated = str(uuid4()), now()
    observation = git.observe(exclusions(manifest))
    prepared, previous, originals, prior_snapshots = {}, {}, {}, []
    for key, kind, default in (("project_state", "project_state", STATE_BODY), ("handoff", "handoff", HANDOFF_BODY)):
        relative = manifest["memory"][key]
        path = inside(git.root, relative)
        old = None if initial else read_bytes(path)
        if old is None:
            header, body = {"revision": 0}, default
        else:
            safe_metadata(old.decode("utf-8-sig"))
            header, body = frontmatter(old)
            memory(header, kind, manifest["project"]["id"])
            prior_snapshots.append(header["snapshot_id"])
        header.update(schema_version=1, kind=kind, project_id=manifest["project"]["id"],
                      snapshot_id=snapshot_id, revision=header["revision"] + 1,
                      updated_at=updated, source_agent=agent, git=observation["snapshot"])
        memory(header, kind, manifest["project"]["id"])
        new = markdown(header, body)
        safe_metadata(new.decode("utf-8"))
        prepared[relative] = new
        previous[relative] = digest(old) if old is not None else None
        originals[relative] = old
    checkpoint_path = inside(git.root, manifest["memory"]["checkpoint"])
    old_checkpoint = None if initial else read_bytes(checkpoint_path)
    if old_checkpoint:
        prior_checkpoint = parse_json(old_checkpoint)
        validate_checkpoint(prior_checkpoint, manifest)
        if any(item != prior_checkpoint["snapshot_id"] for item in prior_snapshots):
            raise UamlError("CHECKPOINT_MISMATCH", "Partial checkpoint detected; inspect the journal and backups before saving again.")
    checkpoint_value = {"schema_version": 1, "project_id": manifest["project"]["id"],
                        "snapshot_id": snapshot_id, "updated_at": updated,
                        "files": {name: digest(data) for name, data in prepared.items()}}
    # Persist complete after-images before publishing the prepared journal. A
    # repair can finish the same snapshot without inventing unsaved information.
    prepared[manifest["memory"]["checkpoint"]] = json_bytes(checkpoint_value)
    originals[manifest["memory"]["checkpoint"]] = old_checkpoint
    entries = []
    for index, (relative, data) in enumerate(prepared.items()):
        after_blob = f"transactions/{snapshot_id}.{index}.after"
        before_blob = f"transactions/{snapshot_id}.{index}.before" if originals[relative] is not None else None
        write(inside(registry_path.parent, after_blob), data, None)
        if before_blob is not None:
            write(inside(registry_path.parent, before_blob), originals[relative], None)
        entries.append({"path": relative, "before_hash": digest(originals[relative]) if originals[relative] is not None else None,
                        "after_hash": digest(data), "before_blob": before_blob, "after_blob": after_blob})
    journal = inside(registry_path.parent, f"transactions/{snapshot_id}.json")
    journal_value = {"schema_version": 2, "repository_root": str(git.root), "project_id": manifest["project"]["id"],
                     "binding_fingerprint": digest(json_bytes(manifest)), "entries": entries,
                     "status": "prepared", "checkpoint": checkpoint_value,
                     "previous_hashes": previous, "previous_checkpoint_hash": digest(old_checkpoint) if old_checkpoint else None}
    write(journal, json_bytes(journal_value), None)
    # A crash leaves the prepared journal and old backups. No blind rollback.
    for relative, data in prepared.items():
        if relative == manifest["memory"]["checkpoint"]:
            continue
        write(inside(git.root, relative), data, previous[relative], registry_path.parent / "backups")
    write(checkpoint_path, json_bytes(checkpoint_value), digest(old_checkpoint) if old_checkpoint else None,
          registry_path.parent / "backups")
    journal_value["status"] = "complete"
    write(journal, json_bytes(journal_value), digest(read_bytes(journal)))
    return {"status": "CHECKPOINT_SAVED", "snapshot_id": snapshot_id,
            "files": checkpoint_value["files"], "git": observation}


def validate_checkpoint(value, manifest):
    fields(value, ("schema_version", "project_id", "snapshot_id", "updated_at", "files"))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise UamlError("SCHEMA_UNSUPPORTED", "Unsupported checkpoint schema.")
    identifier(value["snapshot_id"])
    timestamp(value["updated_at"])
    expected = {manifest["memory"][key] for key in ("project_state", "handoff")}
    if value["project_id"] != manifest["project"]["id"] or not isinstance(value["files"], dict) or set(value["files"]) != expected:
        raise UamlError("CHECKPOINT_MISMATCH", "Checkpoint project or file set differs.")
    for val in value["files"].values():
        if not isinstance(val, str) or len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
            raise UamlError("SCHEMA_INVALID", "Invalid checkpoint hash.")
