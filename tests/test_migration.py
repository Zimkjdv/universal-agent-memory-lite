import json
import shutil
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from uaml import migration, registry
from uaml.binding import load_project, trust
from uaml.errors import UamlError
from uaml.formats import frontmatter, json_bytes, markdown
from uaml.git_state import Git
from uaml.project_memory import checkpoint
from uaml.recovery import recover

from .support import Workspace


class MigrationTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()

    def install_rules(self):
        plan = migration.rules(self.git)
        return migration.rules(self.git, True, plan["plan_hash"])

    def committed_source(self):
        self.install_rules()
        self.git_cmd("add", ".")
        self.git_cmd("commit", "-m", "track byte-preserving rules and memory")
        checkpoint(self.git, self.registry, "codex")
        self.git_cmd("add", "docs/memory")
        self.git_cmd("commit", "-m", "save clean checkpoint")
        remote = self.base / "origin.git"
        self.git_cmd("init", "--bare", str(remote))
        self.git_cmd("remote", "add", "origin", str(remote))
        self.git_cmd("push", "-u", "origin", "main")
        # Remote identity changed, so approval is explicit again.
        trust(self.git, self.registry)
        return remote

    def test_local_preflight_is_readonly_and_accepts_saved_uncommitted_work(self):
        (self.repo / "app.py").write_text("saved local work\n", encoding="utf-8")
        checkpoint(self.git, self.registry, "codex")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        report = migration.check(self.git, self.registry, "local")
        self.assertEqual(report["status"], "MIGRATION_CHECKED", report["diagnostics"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})
        self.assertFalse(all(a["present_in_head"] for a in report["artifacts"]))

    def test_github_preflight_rejects_unsaved_or_uncommitted_memory(self):
        report = migration.check(self.git, self.registry, "github")
        codes = {d["code"] for d in report["diagnostics"]}
        self.assertIn("MEMORY_NOT_COMMITTED_EXACTLY", codes)
        self.assertIn("BYTE_RULES_UNVERIFIED", codes)
        self.assertIn("WORKTREE_NOT_IN_CLONE", codes)

    def test_committed_memory_only_head_change_is_explained(self):
        self.committed_source()
        self.assertTrue(any(d["code"] == "STALE_MEMORY" for d in recover(self.git, self.registry)["diagnostics"]))
        report = migration.check(self.git, self.registry, "github")
        self.assertEqual(report["status"], "MIGRATION_CHECKED", report["diagnostics"])
        self.assertTrue(all(a["same_as_head"] for a in report["artifacts"]))

    def test_real_clone_with_crlf_and_fresh_registry_preserves_binding_and_hashes(self):
        remote = self.committed_source()
        destination = self.base / "new-computer" / "clone"
        self.git_cmd("-c", "core.autocrlf=true", "clone", "--branch", "main", str(remote), str(destination))
        new_vault = self.base / "new-computer" / "different-drive-vault"
        shutil.copytree(self.vault, new_vault)
        new_registry = self.base / "new-computer" / "private" / "registry.json"
        new_git = Git(destination)
        initial = recover(new_git, new_registry)
        self.assertEqual(initial["binding"]["status"], "REGISTRY_MISSING")
        registry.register(new_registry, new_vault)
        self.assertEqual(recover(new_git, new_registry)["binding"]["status"], "CHECKOUT_UNTRUSTED")
        trust(new_git, new_registry)
        result = migration.check(new_git, new_registry, "github")
        self.assertEqual(result["status"], "MIGRATION_CHECKED", result["diagnostics"])
        self.assertTrue(all(s["checkpoint_verified"] for s in recover(new_git, new_registry)["sources"]))
        self.assertEqual(load_project(self.git)[0]["binding"], load_project(new_git)[0]["binding"])
        for relative in [".uaml/project.yaml", "docs/memory/PROJECT-STATE.md", "docs/memory/HANDOFF.md", "docs/memory/checkpoint.json"]:
            self.assertEqual((self.repo / relative).read_bytes(), (destination / relative).read_bytes())

    def test_local_copy_keeps_staged_unstaged_and_untracked_files(self):
        (self.repo / "app.py").write_text("staged\n", encoding="utf-8")
        self.git_cmd("add", "app.py")
        (self.repo / "app.py").write_text("unstaged\n", encoding="utf-8")
        (self.repo / "新工作.txt").write_text("untracked", encoding="utf-8")
        checkpoint(self.git, self.registry, "claude-code")
        status = self.git_cmd("status", "--porcelain=v1", "-z")
        destination = self.base / "copied-project"
        new_vault = self.base / "copied-vault"
        shutil.copytree(self.repo, destination)
        shutil.copytree(self.vault, new_vault)
        new_registry = self.base / "other-private" / "registry.json"
        registry.register(new_registry, new_vault)
        new_git = Git(destination)
        trust(new_git, new_registry)
        result = migration.check(new_git, new_registry, "local")
        self.assertEqual(result["status"], "MIGRATION_CHECKED", result["diagnostics"])
        self.assertEqual(status, self.git_cmd("status", "--porcelain=v1", "-z", cwd=destination))
        self.assertEqual(self.git_cmd("show", ":app.py"), self.git_cmd("show", ":app.py", cwd=destination))
        self.assertEqual((destination / "新工作.txt").read_text(encoding="utf-8"), "untracked")

    def test_rules_preview_apply_preserve_existing_attributes_and_index(self):
        root_rules = self.repo / ".gitattributes"
        root_rules.write_text("*.py text\n", encoding="utf-8")
        prior = self.git_cmd("ls-files", "--stage", "-z")
        plan = migration.rules(self.git)
        self.assertFalse((self.repo / ".uaml/.gitattributes").exists())
        self.install_rules()
        self.assertEqual(root_rules.read_text(encoding="utf-8"), "*.py text\n")
        self.assertEqual(prior, self.git_cmd("ls-files", "--stage", "-z"))
        self.assertEqual(migration.rules(self.git, True, plan["plan_hash"])["status"], "MIGRATION_RULES_INSTALLED")

    def test_existing_different_rule_and_stale_plan_refuse_overwrite(self):
        plan = migration.rules(self.git)
        path = self.repo / "docs/memory/.gitattributes"
        path.write_text("*.md text eol=lf\n", encoding="utf-8")
        self.assertEqual(migration.rules(self.git)["status"], "MIGRATION_RULE_CONFLICT")
        with self.assertRaises(UamlError):
            migration.rules(self.git, True, plan["plan_hash"])
        self.assertEqual(path.read_text(encoding="utf-8"), "*.md text eol=lf\n")
        self.assertFalse((self.repo / ".uaml/.gitattributes").exists())

    def test_changed_code_or_snapshot_integrity_requires_review(self):
        self.committed_source()
        (self.repo / "app.py").write_text("not saved in handoff\n", encoding="utf-8")
        report = migration.check(self.git, self.registry, "local")
        self.assertIn("STALE_MEMORY", {d["code"] for d in report["diagnostics"]})
        file = self.repo / "docs/memory/HANDOFF.md"
        file.write_bytes(file.read_bytes() + b"\nmanual pending memory\n")
        report = migration.check(self.git, self.registry, "local")
        self.assertIn("MEMORY_INCOMPLETE", {d["code"] for d in report["diagnostics"]})

    def test_pending_checkpoint_and_tracked_private_registry_are_reported(self):
        journal = next((self.registry.parent / "transactions").glob("*.json"))
        value = json.loads(journal.read_bytes())
        value["status"] = "prepared"
        journal.write_bytes(json_bytes(value))
        (self.repo / "registry.json").write_text("{}", encoding="utf-8")
        self.git_cmd("add", "registry.json")
        report = migration.check(self.git, self.registry, "local")
        codes = {d["code"] for d in report["diagnostics"]}
        self.assertIn("CHECKPOINT_TRANSACTION_PENDING", codes)
        self.assertIn("PRIVATE_ARTIFACT_TRACKED", codes)

    def test_knowledge_is_opt_in_and_requires_existing_grant(self):
        with patch("uaml.migration.scan", side_effect=AssertionError("implicit knowledge scan")):
            migration.check(self.git, self.registry, "local")
        report = migration.check(self.git, self.registry, "local", True)
        self.assertIn("KNOWLEDGE_ACCESS_DENIED", {d["code"] for d in report["diagnostics"]})
        trust(self.git, self.registry, "read")
        self.assertEqual(migration.check(self.git, self.registry, "local", True)["status"], "MIGRATION_CHECKED")

    def test_linked_worktree_copy_requires_external_git_metadata(self):
        self.committed_source()
        destination = self.base / "linked-checkout"
        self.git_cmd("worktree", "add", "-b", "migration-test", str(destination))
        new_git = Git(destination)
        trust(new_git, self.registry)
        report = migration.check(new_git, self.registry, "local")
        self.assertIn("EXTERNAL_GIT_DIRECTORY", {d["code"] for d in report["diagnostics"]})

    def test_local_attribute_override_cannot_silently_reenable_transform(self):
        self.committed_source()
        (self.repo / ".git/info/attributes").write_text(".uaml/project.yaml text eol=crlf\n", encoding="utf-8")
        report = migration.check(self.git, self.registry, "github")
        self.assertIn("CHECKOUT_TRANSFORM", {d["code"] for d in report["diagnostics"]})

    def test_pending_vault_knowledge_transaction_requires_original_plan(self):
        trust(self.git, self.registry, "read")
        marker = {"schema_version": 1, "kind": "knowledge_supersession", "id": str(uuid4()), "plan_hash": "0" * 64}
        (self.vault / ".uaml/knowledge-transaction.json").write_bytes(json_bytes(marker))
        report = migration.check(self.git, self.registry, "local", True)
        self.assertIn("KNOWLEDGE_TRANSACTION_PENDING", {d["code"] for d in report["diagnostics"]})

    def test_malformed_private_journal_degrades_without_traceback(self):
        journal = next((self.registry.parent / "transactions").glob("*.json"))
        value = json.loads(journal.read_bytes())
        value["repository_root"] = 123
        journal.write_bytes(json_bytes(value))
        report = migration.check(self.git, self.registry, "local")
        self.assertIn("JOURNAL_INVALID", {d["code"] for d in report["diagnostics"]})

    def test_cli_rules_and_source_check(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "migration"]
        preview = subprocess.run(command + ["rules"], capture_output=True, check=True)
        plan = json.loads(preview.stdout)
        applied = subprocess.run(command + ["rules", "--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout)["status"], "MIGRATION_RULES_INSTALLED")
        result = subprocess.run(command + ["check", "--mode", "github"], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "MIGRATION_REVIEW_REQUIRED")
