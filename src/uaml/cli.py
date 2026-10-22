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
from . import knowledge
from . import proposals
from .validation import validate
from . import forking
from . import replicas
from . import context
from . import adapters


def parser():
    result = argparse.ArgumentParser(description="UAML portable binding and recovery prototype")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--repo", type=Path, default=Path.cwd(), help="repository or a directory within it")
    result.add_argument("--registry", help="private registry path outside Git (or UAML_HOME)")
    result.add_argument("--json", action="store_true", help="structured output, including errors")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "resolve"):
        commands.add_parser(name)
    recovery = commands.add_parser("recover")
    recovery.add_argument("--compact", action="store_true", help="bounded JSON evidence for agent handoff")
    recovery.add_argument("--max-bytes", type=int, help="compact UTF-8 output budget, 8192..65536 (default 32768)")
    adapter = commands.add_parser("adapter", help="preview/install independent manual agent entry files")
    adapter.add_argument("--agent", choices=("codex", "claude-code", "all"), required=True)
    adapter.add_argument("--apply", action="store_true")
    adapter.add_argument("--expect-plan")
    verify = commands.add_parser("validate", help="read-only binding, memory, checkpoint and optional knowledge checks")
    verify.add_argument("--knowledge", action="store_true", help="include the explicitly authorized knowledge area")
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
    compare = vaults.add_parser("compare", help="read-only comparison of this approved project's registered Vault copies")
    compare.add_argument("--knowledge", action="store_true")
    select = vaults.add_parser("select", help="acknowledge a reviewed authoritative copy for this project")
    select.add_argument("path", type=Path)
    select.add_argument("--expect-comparison", required=True)
    select.add_argument("--knowledge", action="store_true")
    projects = commands.add_parser("project").add_subparsers(dest="action", required=True)
    init = projects.add_parser("init")
    init.add_argument("--vault", required=True, dest="vault_id")
    init.add_argument("--name", required=True)
    approve = projects.add_parser("trust", help="approve this checkout; knowledge is disabled unless explicitly requested")
    approve.add_argument("--knowledge", choices=("none", "read", "write"), default="none")
    independent = projects.add_parser("fork", help="preview a new independent identity; never inherit old Vault grants")
    independent.add_argument("--name")
    independent.add_argument("--vault", dest="vault_id", help="explicit target Vault ID, never inferred")
    independent.add_argument("--proposal", help="inspect or resume an existing fork plan UUID")
    independent.add_argument("--apply", action="store_true")
    independent.add_argument("--expect-plan")
    notes = commands.add_parser("knowledge").add_subparsers(dest="action", required=True)
    add = notes.add_parser("add", help="explicitly import a new Markdown note, never overwrite an ID")
    add.add_argument("file", type=Path)
    add.add_argument("--allow-similar", action="store_true")
    add.add_argument("--expect-candidates", help="review_hash of the source and current knowledge inventory")
    proposal = notes.add_parser("propose", help="prepare a private local revision proposal; do not write the Vault")
    proposal.add_argument("file", type=Path)
    accept = notes.add_parser("apply", help="apply a hash-bound reviewed proposal")
    accept.add_argument("proposal_id")
    accept.add_argument("--expect-plan", required=True)
    accept.add_argument("--allow-similar", action="store_true")
    get = notes.add_parser("get")
    get.add_argument("id")
    find = notes.add_parser("search")
    find.add_argument("query")
    find.add_argument("--os")
    find.add_argument("--architecture")
    find.add_argument("--component")
    find.add_argument("--component-version", dest="version")
    find.add_argument("--status", choices=knowledge.STATUSES)
    find.add_argument("--limit", type=int, default=5)
    return result


def dispatch(args):
    registry_path = registry_location(args.registry)
    if args.command == "vault":
        if args.action in ("compare", "select"):
            git = Git(args.repo)
            if args.action == "compare":
                return replicas.compare(git, registry_path, args.knowledge)
            return replicas.select(git, registry_path, args.path, args.expect_comparison, args.knowledge)
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
        if args.max_bytes is not None and not args.compact:
            raise UamlError("COMMAND_INVALID", "--max-bytes requires --compact.")
        if args.compact:
            return context.recover_context(git, registry_path, args.max_bytes if args.max_bytes is not None else context.DEFAULT_BUDGET)
        return recover(git, registry_path)
    if args.command == "adapter":
        if args.apply:
            return adapters.install(git, args.agent, args.expect_plan)
        if args.expect_plan:
            raise UamlError("COMMAND_INVALID", "--expect-plan requires --apply.")
        return adapters.preview(git, args.agent)
    if args.command == "validate":
        return validate(git, registry_path, args.knowledge)
    if args.command == "checkpoint":
        return checkpoint(git, registry_path, args.agent)
    if args.command == "repair":
        return repair(git, registry_path, args.transaction, args.apply, args.expect_plan)
    if args.command == "project":
        if args.action == "init":
            return init_project(git, registry_path, args.vault_id, args.name)
        if args.action == "fork":
            if args.proposal:
                if args.name or args.vault_id:
                    raise UamlError("COMMAND_INVALID", "Use either a prepared proposal or new name/target, not both.")
                if args.apply:
                    return forking.apply(git, registry_path, args.proposal, args.expect_plan)
                return forking.inspect(git, registry_path, args.proposal)[0]
            if args.apply or args.expect_plan or not args.name or not args.vault_id:
                raise UamlError("COMMAND_INVALID", "First preview with --name and --vault; then apply its --proposal and --expect-plan.")
            return forking.prepare(git, registry_path, args.name, args.vault_id)
        return trust(git, registry_path, args.knowledge)
    if args.command == "knowledge":
        if args.action == "add":
            return knowledge.add(git, registry_path, args.file, args.allow_similar, args.expect_candidates)
        if args.action == "propose":
            return proposals.propose(git, registry_path, args.file)
        if args.action == "apply":
            return proposals.apply(git, registry_path, args.proposal_id, args.expect_plan, args.allow_similar)
        if args.action == "get":
            return knowledge.get(git, registry_path, args.id)
        return knowledge.search(git, registry_path, args.query,
                                {key: getattr(args, key) for key in ("os", "architecture", "component", "version", "status")
                                 if getattr(args, key)}, args.limit)
    raise UamlError("COMMAND_UNKNOWN", "Unknown command.")


def render(value):
    if value.get("kind") == "recovery_context":
        return context.encode(value).rstrip("\n")
    lines = [f"UAML {value['status']}"]
    if "binding" in value and isinstance(value["binding"], dict):
        lines.append(f"Binding: {value['binding'].get('status', value['binding'])}")
    if value.get("repository_root"):
        lines.append(f"Repository: {value['repository_root']}")
    for diagnostic in value.get("diagnostics", []):
        lines.append(f"[{diagnostic['code']}] {diagnostic['message']}")
    for check in value.get("checks", []):
        lines.append(f"Check {check['area']}: {check['status']}")
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
    if "activation" in value:
        for agent, prompt in value["activation"]["prompts"].items():
            lines.append(f"Manual activation ({agent}): {prompt}")
        for path, content in value["files"].items():
            lines.extend([f"\n--- Adapter preview: {path} ---", content])
    notes = value.get("results", []) or ([value] if "untrusted_markdown" in value else [])
    for note in notes:
        lines.extend([f"\nKnowledge {note['id']} [{note['metadata']['status']}]: {note['metadata']['title']}",
                      f"SHA-256: {note['sha256']}", str(note['metadata']['applicability']),
                      f"Source projects: {note['metadata']['source_project_ids']}",
                      f"Verification: {note['metadata']['verification']}",
                      note['usage_warning'], note['untrusted_markdown']])
        if note["truncated"]:
            lines.append("[knowledge excerpt truncated]")
    if "total_matches" in value:
        lines.append(f"Matches: {value['total_matches']}; scan complete: {value['complete']}")
    if "review_hash" in value:
        lines.append(f"Candidate review hash: {value['review_hash']}")
    if "proposal_id" in value:
        lines.append(f"Proposal ID: {value['proposal_id']}")
    if "fork_id" in value:
        lines.append(f"Fork plan: {value['fork_id']}; project ID: {value['project']['id']}")
    if "comparison_hash" in value:
        lines.append(f"Replica comparison hash: {value['comparison_hash']}")
    for copy in value.get("copies", []):
        lines.append(f"Copy {copy['candidate_id']}: {copy['status']} ({copy['path']})")
        lines.append(f"  project link: {copy['project_link_hash']}; knowledge: {copy['knowledge_hash']}")
    if "replicas" in value:
        lines.append(f"Replicas: {value['replicas']['status']}")
    for candidate in value.get("candidates", []):
        lines.append(f"Similar candidate {candidate['id']}: score {candidate['score']}")
    if "untrusted_diff" in value:
        lines.append("Historical, untrusted diff for review:\n" + value["untrusted_diff"])
        if value["diff_truncated"]:
            lines.append(f"[diff truncated; inspect payload: {value['review_payload']}]")
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
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    print(output)
    return 0 if value["status"] in {"OK", "RESOLVED", "RECOVERED", "TRUSTED", "VAULT_INITIALIZED", "VAULT_REGISTERED", "PROJECT_INITIALIZED", "CHECKPOINT_SAVED", "REPAIR_PREVIEW", "REPAIR_NOT_NEEDED", "REPAIRED", "KNOWLEDGE_ADDED", "KNOWLEDGE_FOUND", "KNOWLEDGE_RESULTS", "KNOWLEDGE_DUPLICATE", "KNOWLEDGE_PROPOSED", "KNOWLEDGE_APPLIED", "VALIDATED", "FORK_PREVIEW", "FORK_APPLIED", "FORK_ALREADY_APPLIED", "REPLICA_EQUIVALENT", "REPLICA_SELECTED", "ADAPTER_PREVIEW", "ADAPTER_INSTALLED", "ADAPTER_ALREADY_INSTALLED"} else 1
