"""Opt-in short references appended to native project instructions after review."""
import os
import re

from .adapters import files_for
from .binding import load_project
from .errors import UamlError
from .formats import digest, json_bytes, read_bytes, safe_metadata, text
from .paths import inside, require_private_registry
from .permissions import WindowsAcl, posix_inspect
from .private_storage import ensure_home
from .storage import lock, write

MAX_ENTRY_BYTES = 32768
MARKER = "<!-- UAML:NATIVE:"


def plain(path):
    if not path.exists() and not path.is_symlink():
        return
    info = path.lstat()
    if (not path.is_file() or path.is_symlink() or info.st_nlink > 1
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise UamlError("UNSAFE_PATH", "Native entry files must be regular, unlinked files inside the repository.")


def optional(path):
    plain(path)
    try:
        raw = read_bytes(path)
    except UamlError as exc:
        if exc.code != "MEMORY_MISSING":
            raise
        return None
    safe_metadata(text(raw))
    return raw


def block(agent, newline="\n"):
    filename = "CODEX.md" if agent == "codex" else "CLAUDE-CODE.md"
    name = "Codex" if agent == "codex" else "Claude Code"
    return newline.join((f"{MARKER}{agent}:BEGIN -->", f"For {name}: when starting a new conversation, taking over interrupted work,",
                         "or explicitly saving a milestone/handoff, read",
                         f"`.uaml/adapters/{filename}` from the Git root and follow its shared UAML workflow.",
                         f"{MARKER}{agent}:END -->", ""))


def check_prose(content):
    fence = None
    for line in content.splitlines():
        if MARKER in line and fence:
            raise UamlError("NATIVE_ENTRY_CONFLICT", "A UAML native marker is inside a code fence; review manually.")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            token, tail = match.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = None
    if fence or content.count("<!--") != content.count("-->"):
        raise UamlError("NATIVE_ENTRY_CONFLICT", "Unclosed Markdown fence/comment could hide the reference; review manually.")


def _prepare(git, registry_path, agent):
    _, manifest_raw = load_project(git)
    require_private_registry(registry_path)
    payloads = files_for(agent)
    dependencies = {}
    for relative, expected in payloads.items():
        raw = optional(inside(git.root, relative))
        if raw is None or text(raw).replace("\r\n", "\n") != expected.decode("utf-8"):
            raise UamlError("ADAPTER_REQUIRED", "Install/review the shared manual adapters first; native references require matching targets.")
        dependencies[relative] = digest(raw)
    names = ("codex", "claude-code") if agent == "all" else (agent,)
    if "codex" in names and (inside(git.root, "AGENTS.override.md").exists()
                              or inside(git.root, "AGENTS.override.md").is_symlink()):
        raise UamlError("NATIVE_ENTRY_SHADOWED", "AGENTS.override.md shadows AGENTS.md; preserve it and choose manual activation or integrate manually.")
    targets = {"codex": "AGENTS.md", "claude-code": "CLAUDE.md"}
    actions, additions, prepared = [], {}, {}
    # Creating CLAUDE.md must not silently suppress existing shared project rules.
    agents_raw = optional(inside(git.root, "AGENTS.md")) if "claude-code" in names else None
    if "claude-code" in names:
        dependencies["AGENTS.md"] = digest(agents_raw) if agents_raw is not None else None
    for name in names:
        relative = targets[name]
        before = optional(inside(git.root, relative))
        content = text(before) if before is not None else ""
        check_prose(content)
        newline = "\r\n" if before and b"\r\n" in before and b"\n" not in before.replace(b"\r\n", b"") else "\n"
        reference = block(name, newline)
        if MARKER in content:
            if content.count(MARKER) != 2 or reference not in content:
                raise UamlError("NATIVE_ENTRY_CONFLICT", "Native reference markers are customized, duplicate or incomplete; preserve them and review manually.")
            after, addition, action = before, "", "keep"
        else:
            prefix = ""
            if before is None and name == "claude-code" and (agents_raw is not None or "codex" in names):
                prefix = "@AGENTS.md" + newline + newline
            separator = "" if not before else (newline if before.endswith(b"\n") else newline + newline)
            addition = separator + prefix + reference
            after = (before or b"") + addition.encode("utf-8")
            action = "create" if before is None else "append"
        if len(after) > MAX_ENTRY_BYTES:
            raise UamlError("NATIVE_ENTRY_TOO_LARGE", "Native entry would exceed 32 KiB; integrate a short reference manually and check agent context limits.")
        prepared[relative] = (before, after)
        additions[relative] = addition
        actions.append({"path": relative, "action": action, "before_hash": digest(before) if before is not None else None,
                        "after_hash": digest(after), "added_bytes": len(addition.encode("utf-8"))})
    backup_root = inside(registry_path.parent, "adapter-backups")
    identity = git.identity()
    plan = {"agent": agent, "git": identity, "manifest_hash": digest(manifest_raw), "actions": actions,
            "dependencies": dependencies, "backup_directory": str(backup_root)}
    report = {"status": "NATIVE_ADAPTER_PREVIEW", "agent": agent, "plan_hash": digest(json_bytes(plan)),
              "actions": actions, "files": additions, "dependencies": dependencies, "backup_directory": str(backup_root),
              "limitations": ["Only the displayed additions are proposed; original bytes are preserved and existing files backed up privately.",
                              "Native discovery depends on agent version, overrides, settings and combined context limits; verify in a new real session.",
                              "No Vault, global settings, Hooks or permissions are granted; interrupted multi-file writes require a fresh preview."],
              "next_step": "Review every addition and backup location; explicitly pass --native --apply --expect-plan."}
    return report, prepared, backup_root, digest(json_bytes(identity))


def preview(git, registry_path, agent):
    return _prepare(git, registry_path, agent)[0]


def install(git, registry_path, agent, expected_plan):
    if not expected_plan:
        raise UamlError("PLAN_REQUIRED", "Preview native references, then explicitly pass --expect-plan.")
    with lock(inside(git.root, ".uaml/write.lock")):
        report, prepared, backup_root, identity_hash = _prepare(git, registry_path, agent)
        if all(a["action"] == "keep" for a in report["actions"]):
            return {**report, "status": "NATIVE_ADAPTER_ALREADY_INSTALLED", "next_step": "References are unchanged; verify activation in a new agent session."}
        if expected_plan != report["plan_hash"]:
            raise UamlError("WRITE_CONFLICT", "Native plan, instructions, adapter targets, checkout or backup location changed; preview again.")
        ensure_home(registry_path)
        ensure_home(backup_root / "placeholder.json")
        info = backup_root.lstat()
        inspector = WindowsAcl().inspect if os.name == "nt" else posix_inspect
        if (backup_root.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400
                or inspector(backup_root)["state"] != "RESTRICTED"):
            raise UamlError("NATIVE_BACKUP_UNSAFE", "Private backup directory permissions are unverified; inspect them manually. No native entry was changed.")
        backups = {}
        # Save every original first. A later failure never rolls back user content.
        with lock(backup_root / "write.lock"):
            for action in report["actions"]:
                if action["action"] == "keep":
                    continue
                relative = action["path"]
                before, _ = prepared[relative]
                if before is not None:
                    backup = inside(backup_root, f"{identity_hash}-{relative}-{digest(before)}.before")
                    plain(backup)
                    if backup.exists():
                        if read_bytes(backup) != before:
                            raise UamlError("WRITE_CONFLICT", "An existing native backup differs; inspect it before retrying.")
                    else:
                        write(backup, before, None)
                    backups[relative] = str(backup)
            # Recheck the complete plan after backup preparation, before publication.
            if preview(git, registry_path, agent)["plan_hash"] != expected_plan:
                raise UamlError("WRITE_CONFLICT", "Native instructions or dependencies changed while preparing backups.")
            for action in report["actions"]:
                if action["action"] != "keep":
                    path = inside(git.root, action["path"])
                    plain(path)
                    write(path, prepared[action["path"]][1], action["before_hash"])
    return {**report, "status": "NATIVE_ADAPTER_INSTALLED", "backups": backups,
            "next_step": "Start a new agent session and confirm the reference and shared workflow are read. T01/T02 remain unverified."}
