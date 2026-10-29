"""Local, read-only migration preflight plus opt-in byte-preserving Git rules."""
import os
from itertools import islice
from pathlib import Path

from .binding import load_project
from .errors import UamlError
from .formats import digest, identifier, json_bytes, parse_json, read_bytes
from .knowledge import authorize, check_read_stamp, read_stamp, scan
from .paths import inside, local_key
from .recovery import recover
from .storage import lock, write
from .validation import relations, sections

RULES = {".uaml/.gitattributes": b"project.yaml -text\n",
         "docs/memory/.gitattributes": b"PROJECT-STATE.md -text\nHANDOFF.md -text\ncheckpoint.json -text\n"}


def rules(git, apply=False, expected_plan=None):
    _, manifest_raw = load_project(git)
    if apply:
        if not expected_plan:
            raise UamlError("PLAN_REQUIRED", "Preview migration rules, then pass --expect-plan.")
        with lock(inside(git.root, ".uaml/write.lock")):
            preview = rules(git)
            if preview["status"] == "MIGRATION_RULE_CONFLICT":
                raise UamlError("MIGRATION_RULE_CONFLICT", "Preserve existing attribute rules and review manually; no overwrite performed.")
            if all(a["action"] == "keep" for a in preview["actions"]):
                return {**preview, "status": "MIGRATION_RULES_INSTALLED"}
            if preview["plan_hash"] != expected_plan:
                raise UamlError("WRITE_CONFLICT", "Rule targets, binding or checkout changed; preview again.")
            for action in preview["actions"]:
                if action["action"] == "create":
                    write(inside(git.root, action["path"]), RULES[action["path"]], None)
        return {**preview, "status": "MIGRATION_RULES_INSTALLED",
                "next_step": "Review and commit the two rule files yourself before the next memory checkpoint; no Git index/config was changed."}
    actions = []
    for relative, payload in RULES.items():
        try:
            prior = read_bytes(inside(git.root, relative))
        except UamlError as exc:
            if exc.code != "MEMORY_MISSING":
                raise
            prior = None
        actions.append({"path": relative, "action": "create" if prior is None else ("keep" if prior == payload else "conflict"),
                        "before_hash": digest(prior) if prior is not None else None, "after_hash": digest(payload)})
    return {"status": "MIGRATION_RULE_CONFLICT" if any(a["action"] == "conflict" for a in actions) else "MIGRATION_RULES_PREVIEW",
            "plan_hash": digest(json_bytes({"git": git.identity(), "manifest": digest(manifest_raw), "actions": actions})),
            "actions": actions, "files": {p: raw.decode("ascii") for p, raw in RULES.items()},
            "next_step": "Review --apply --expect-plan to create only missing per-directory rules; existing different rules are preserved."}


def pending_checkpoints(registry_path, git, project_id):
    folder = inside(registry_path.parent, "transactions")
    if not folder.exists():
        return []
    if folder.is_symlink() or getattr(folder.lstat(), "st_file_attributes", 0) & 0x400:
        raise UamlError("UNSAFE_PATH", "Linked private journal directory requires manual inspection.")
    pending = []
    with os.scandir(folder) as stream:
        entries = list(islice(stream, 1025))
    if len(entries) > 1024:
        raise UamlError("JOURNAL_SCAN_LIMIT", "Journal preflight exceeded 1024 entries; review unfinished work before moving.")
    for entry in entries:
        if not entry.name.endswith(".json"):
            continue
        path = inside(folder, entry.name)
        if not entry.is_file(follow_symlinks=False):
            raise UamlError("UNSAFE_PATH", "Journal entries must be regular files.")
        value = parse_json(read_bytes(path))
        identifier(value.get("project_id"))
        if (type(value.get("schema_version")) is not int or value["schema_version"] not in (1, 2) or
                not isinstance(value.get("repository_root"), str) or not Path(value["repository_root"]).is_absolute() or
                value.get("status") not in ("prepared", "complete")):
            raise UamlError("JOURNAL_INVALID", "A local checkpoint journal has unknown identity/status; inspect it before moving.")
        if value["project_id"] == project_id and local_key(Path(value["repository_root"])) == local_key(git.root):
            if value.get("status") != "complete":
                pending.append(entry.name)
    return sorted(pending)


def check(git, registry_path, mode, include_knowledge=False):
    if mode not in ("github", "local"):
        raise UamlError("COMMAND_INVALID", "Migration mode must be github or local.")
    manifest, manifest_raw = load_project(git)
    recovery = recover(git, registry_path, body_limit=None)
    observation = recovery["git"]
    checks, diagnostics = [], []

    def record(area, passed, code, message):
        checks.append({"area": area, "status": "PASS" if passed else "REVIEW"})
        if not passed:
            diagnostics.append({"code": code, "message": message})

    record("binding", recovery["binding"]["status"] == "RESOLVED", recovery["binding"]["status"],
           "Resolve the authorized source Vault association before migration; never create a replacement or inherit a new checkout grant.")
    record("checkpoint", len(recovery["sources"]) == 2 and all(s["checkpoint_verified"] for s in recovery["sources"]),
           "MEMORY_INCOMPLETE", "Save/repair a complete matching State/Handoff/checkpoint before moving.")
    for diagnostic in recovery["diagnostics"]:
        if diagnostic["code"] != "STALE_MEMORY":
            diagnostics.append(diagnostic)
    memory_paths = [".uaml/project.yaml", *(manifest["memory"][key] for key in ("project_state", "handoff", "checkpoint"))]
    artifacts = []
    for relative in memory_paths:
        try:
            raw = manifest_raw if relative == ".uaml/project.yaml" else read_bytes(inside(git.root, relative))
            committed = git.run("show", f"HEAD:{relative}", optional=True)
            same = committed is not None and digest(committed) == digest(raw)
            artifacts.append({"path": relative, "sha256": digest(raw), "present_in_head": committed is not None, "same_as_head": same})
            if mode == "github":
                record(relative, same, "MEMORY_NOT_COMMITTED_EXACTLY", "Commit the current byte-exact memory files; clone cannot include uncommitted or normalized content.")
        except UamlError as exc:
            diagnostics.append({**exc.diagnostic(), "path": relative})
    for source in recovery["sources"]:
        diagnostics.extend(sections(source["untrusted_markdown"], source["metadata"]["kind"], source["path"]))
        differences = set(source["git_differences"])
        if "head" in differences:
            saved, current = source["metadata"]["git"]["head"], observation["snapshot"]["head"]
            known = saved and current and git.run("merge-base", "--is-ancestor", saved, current, optional=True) is not None
            paths = git.run("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", saved, current, "--") if known else None
            changed = [p for p in (paths.decode("utf-8", errors="replace").split("\0") if paths is not None else []) if p]
            allowed = set(memory_paths) | set(RULES)
            # A memory-only commit is expected because a saved HEAD cannot name
            # the future commit containing the checkpoint itself.
            if known and all(p in allowed or p.startswith(".uaml/adapters/") for p in changed):
                differences.remove("head")
        record(source["metadata"]["kind"] + "_freshness", not differences, "STALE_MEMORY", "Current branch, code history or working content differs from saved memory; review and checkpoint current facts.")
    changes = observation["changes"]
    record("working_tree", mode == "local" or not changes, "WORKTREE_NOT_IN_CLONE", "GitHub clone omits local changes; commit/push intended work or choose local-copy mode.")
    if mode == "local":
        identity = git.identity()
        record("git_directory", Path(identity["git_directory"]).is_relative_to(git.root), "EXTERNAL_GIT_DIRECTORY",
               "This checkout depends on external Git metadata (for example a worktree); copying this folder alone is insufficient.")
    else:
        for relative, payload in RULES.items():
            committed = git.run("show", f"HEAD:{relative}", optional=True)
            record(relative + "_rules", committed is not None and committed.replace(b"\r\n", b"\n") == payload,
                   "BYTE_RULES_UNVERIFIED", "Commit the reviewed UAML per-directory -text rules, or manually review existing custom attributes; byte hashes must survive checkout conversion.")
        attributes = git.run("check-attr", "-z", "text", "filter", "working-tree-encoding", "--", *memory_paths).decode("utf-8", errors="replace").split("\0")
        safe = all((attributes[i + 1] == "text" and attributes[i + 2] == "unset") or
                   (attributes[i + 1] != "text" and attributes[i + 2] in ("unspecified", "unset")) for i in range(0, len(attributes) - 1, 3))
        record("checkout_attributes", safe, "CHECKOUT_TRANSFORM", "Local attributes still enable conversion/filter/encoding for memory; inspect overrides before moving.")
        upstream = observation["snapshot"]["upstream"]
        ahead_behind = git.run("rev-list", "--left-right", "--count", "HEAD...@{upstream}", "--", optional=True) if upstream else None
        record("local_tracking_ref", ahead_behind is not None and ahead_behind.split() == [b"0", b"0"], "PUSH_EVIDENCE_MISSING",
               "No matching local upstream evidence; review/push intended commits. This check never contacts the remote server.")
    try:
        pending = pending_checkpoints(registry_path, git, manifest["project"]["id"])
        record("local_journals", not pending, "CHECKPOINT_TRANSACTION_PENDING", "Finish/review prepared checkpoint journals before leaving their original private payloads behind.")
    except (UamlError, OSError) as exc:
        diagnostics.append(exc.diagnostic() if isinstance(exc, UamlError) else {"code": "JOURNAL_READ_FAILED", "message": "Cannot inspect local journals; preflight is incomplete."})
    tracked = git.run("ls-files", "-z").decode("utf-8", errors="replace").split("\0")
    suspected = [p for p in tracked if p and (Path(p).name == "registry.json" or p.startswith(".uaml-local/") or
                any(p.startswith(f".uaml/{name}/") for name in ("backups", "transactions", "proposals", "forks", "supersessions")))]
    record("private_artifacts", not suspected, "PRIVATE_ARTIFACT_TRACKED", "Potential machine-private Registry/artifact paths are tracked; inspect before publishing. Contents were not read.")
    if include_knowledge:
        try:
            _, vault_path, root = authorize(git, registry_path)
            stamp = read_stamp(vault_path)
            notes, issues, complete = scan(root)
            check_read_stamp(vault_path, stamp)
            diagnostics.extend(issues)
            link_issues = relations(notes) if complete else []
            diagnostics.extend(link_issues)
            record("knowledge", complete and not link_issues, "KNOWLEDGE_UNVERIFIED", "Resolve incomplete or inconsistent knowledge before transferring a stable Vault copy.")
        except UamlError as exc:
            diagnostics.append(exc.diagnostic())
            checks.append({"area": "knowledge", "status": "REVIEW"})
    else:
        checks.append({"area": "knowledge", "status": "NOT_REQUESTED"})
    return {"status": "MIGRATION_CHECKED" if not diagnostics else "MIGRATION_REVIEW_REQUIRED", "mode": mode,
            "project_id": manifest["project"]["id"], **manifest["binding"], "checks": checks, "artifacts": artifacts,
            "git": {**observation, "changes": changes[:30], "change_count": len(changes), "truncated": len(changes) > 30},
            "suspected_private_paths": suspected[:30], "suspected_private_count": len(suspected), "diagnostics": diagnostics,
            "limitations": ["Preflight is local evidence, not completed migration or proof of live remote synchronization.",
                            "No clone, copy, fetch, commit, push, Vault write or automatic approval was performed.",
                            "Transfer the correct Vault separately. On the destination register its new path and explicitly trust the new checkout.",
                            "Private Registry, grants, backups and pending plans are not portable public metadata; knowledge checks require --knowledge and a grant.",
                            "Ignored files, external tools and unsaved conversations are not reconstructed; local-copy users must preserve required files themselves."]}
