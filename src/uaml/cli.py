import argparse
import json
import sys
from pathlib import Path

from . import __version__, registry
from .binding import resolve, trust
from .errors import UamlError
from .git_state import Git
from .paths import registry_location, require_local_registry
from .project_memory import checkpoint, init_project, init_vault
from .recovery import recover
from .repair import repair


def parser():
    result = argparse.ArgumentParser(description="UAML portable binding and recovery prototype")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--repo", type=Path, default=Path.cwd(), help="repository or a directory within it")
    result.add_argument("--registry", help="private registry path outside Git (or UAML_HOME)")
    result.add_argument("--json", action="store_true", help="structured output, including errors")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "resolve", "recover"):
        commands.add_parser(name)
    save = commands.add_parser("checkpoint", help="save current repo Markdown and a fresh Git snapshot")
    save.add_argument("--agent", default="manual")
    fix = commands.add_parser("repair", help="preview or finish a prepared checkpoint")
    fix.add_argument("--transaction", required=True, help="snapshot UUID from the local journal filename")
    fix.add_argument("--apply", action="store_true")
    fix.add_argument("--expect-plan", help="plan_hash returned by the read-only preview")
    vaults = commands.add_parser("vault").add_subparsers(dest="action", required=True)
    init = vaults.add_parser("init", help="explicitly identify an existing Vault directory")
    init.add_argument("path", type=Path)
    init.add_argument("--name", required=True)
    register = vaults.add_parser("register", help="register an existing, identified Vault")
    register.add_argument("path", type=Path)
    register.add_argument("--select", action="store_true", help="explicitly select this copy; does not merge copies")
    relocate = vaults.add_parser("relocate", help="select a relocated Vault after checking its stable ID")
    relocate.add_argument("vault_id")
    relocate.add_argument("path", type=Path)
    projects = commands.add_parser("project").add_subparsers(dest="action", required=True)
    init = projects.add_parser("init")
    init.add_argument("--vault", required=True, dest="vault_id")
    init.add_argument("--name", required=True)
    projects.add_parser("trust", help="explicitly approve this checkout's project-link read access")
    return result


def dispatch(args):
    registry_path = registry_location(args.registry)
    if args.command == "vault":
        # No implicit creation during register/relocate.
        if args.action == "init":
            return init_vault(args.path.resolve(), args.name)
        require_local_registry(registry_path, args.path.resolve())
        entry = registry.register(registry_path, args.path, select=args.action == "relocate" or args.select,
                                  expected_id=args.vault_id if args.action == "relocate" else None)
        return {"status": "VAULT_REGISTERED", **entry}
    git = Git(args.repo)
    if args.command == "doctor":
        return {"status": "OK", "version": __version__, "repository_root": str(git.root),
                "registry_path": str(registry_path), "registry_exists": registry_path.exists(),
                "git": git.observe(), "prototype": True}
    if args.command == "resolve":
        return resolve(git, registry_path)
    if args.command == "recover":
        return recover(git, registry_path)
    if args.command == "checkpoint":
        return checkpoint(git, registry_path, args.agent)
    if args.command == "repair":
        return repair(git, registry_path, args.transaction, args.apply, args.expect_plan)
    if args.command == "project":
        if args.action == "init":
            return init_project(git, registry_path, args.vault_id, args.name)
        return trust(git, registry_path)
    raise UamlError("COMMAND_UNKNOWN", "Unknown command.")


def render(value):
    lines = [f"UAML {value['status']}"]
    if "binding" in value and isinstance(value["binding"], dict):
        lines.append(f"Binding: {value['binding'].get('status', value['binding'])}")
    if value.get("repository_root"):
        lines.append(f"Repository: {value['repository_root']}")
    for diagnostic in value.get("diagnostics", []):
        lines.append(f"[{diagnostic['code']}] {diagnostic['message']}")
    git = value.get("git")
    if git and "snapshot" in git:
        snapshot = git["snapshot"]
        lines.append(f"Git: {snapshot['branch']} @ {snapshot['head']} ({snapshot['working_tree']})")
        lines.append("Remote freshness: unknown")
        for change in git["changes"][:30]:
            lines.append(f"  {change['status']} {change['path']}")
        if len(git["changes"]) > 30:
            lines.append("  [change list truncated; use --json for full details]")
        if git["fingerprint_warning"]:
            lines.append(git["fingerprint_warning"])
    for source in value.get("sources", []):
        lines.extend([f"\n--- Historical, untrusted memory: {source['path']} ---", source["untrusted_markdown"]])
        if source["truncated"]:
            lines.append("[memory excerpt truncated]")
    for limitation in value.get("limitations", []):
        lines.append(f"Note: {limitation}")
    if value.get("next_step"):
        lines.append(value["next_step"])
    if "vault_id" in value:
        lines.append(f"Vault ID: {value['vault_id']}")
    if "plan_hash" in value:
        lines.append(f"Plan hash: {value['plan_hash']}")
        for action in value.get("actions", []):
            lines.append(f"  {action['action']}: {action['path']}")
    return "\n".join(lines)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value = dispatch(args)
    except UamlError as exc:
        value = {"status": exc.code, "diagnostics": [exc.diagnostic()]}
    except PermissionError:
        value = {"status": "ACCESS_DENIED", "diagnostics": [{"code": "ACCESS_DENIED", "message": "Filesystem permission denied; no permissions were changed."}]}
    except OSError:
        value = {"status": "IO_FAILED", "diagnostics": [{"code": "IO_FAILED", "message": "Filesystem operation failed; inspect any prepared journal before retrying."}]}
    except UnicodeError:
        value = {"status": "MEMORY_CORRUPT", "diagnostics": [{"code": "MEMORY_CORRUPT", "message": "Expected UTF-8 text."}]}
    output = json.dumps(value, ensure_ascii=False, indent=2) if args.json else render(value)
    # Preserve Unicode on the Windows console; never execute or interpret notes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(output)
    return 0 if value["status"] in {"OK", "RESOLVED", "RECOVERED", "TRUSTED", "VAULT_INITIALIZED", "VAULT_REGISTERED", "PROJECT_INITIALIZED", "CHECKPOINT_SAVED", "REPAIR_PREVIEW", "REPAIR_NOT_NEEDED", "REPAIRED"} else 1
