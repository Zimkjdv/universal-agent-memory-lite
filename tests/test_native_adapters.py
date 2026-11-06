import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from uaml import adapters, native_adapters, permissions
from uaml.errors import UamlError
from uaml.formats import digest
from uaml.storage import write

from .support import Workspace


class NativeAdapterTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind(approve=False)
        manual = adapters.preview(self.git, "all")
        adapters.install(self.git, "all", manual["plan_hash"])

    def preview(self, agent="all"):
        return native_adapters.preview(self.git, self.registry, agent)

    def apply(self, plan, agent="all"):
        return native_adapters.install(self.git, self.registry, agent, plan["plan_hash"])

    def test_preview_is_readonly_and_never_reads_vault_or_changes_private_home(self):
        (self.repo / "AGENTS.md").write_bytes(b"original project rules\n")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch("uaml.registry.read_vault", side_effect=AssertionError("no Vault reads")):
            plan = self.preview()
        self.assertEqual(plan["status"], "NATIVE_ADAPTER_PREVIEW")
        self.assertIn("@AGENTS.md", plan["files"]["CLAUDE.md"])
        self.assertNotIn("original project rules", plan["files"]["AGENTS.md"])
        self.assertFalse((self.registry.parent / "adapter-backups").exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_apply_appends_preserves_original_bytes_and_saves_private_backups(self):
        originals = {"AGENTS.md": b"\xef\xbb\xbf# Project rules\r\nKeep user changes.\r\n",
                     "CLAUDE.md": b"# Claude rules without final newline"}
        for name, raw in originals.items():
            (self.repo / name).write_bytes(raw)
        registry_before = self.registry.read_bytes()
        vault_before = {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        plan = self.preview()
        result = self.apply(plan)
        self.assertEqual(result["status"], "NATIVE_ADAPTER_INSTALLED")
        for name, raw in originals.items():
            actual = (self.repo / name).read_bytes()
            self.assertEqual(actual, raw + plan["files"][name].encode())
            self.assertEqual(digest(actual), next(a["after_hash"] for a in plan["actions"] if a["path"] == name))
            backup = Path(result["backups"][name])
            self.assertEqual(backup.read_bytes(), raw)
            inspector = permissions.WindowsAcl().inspect if os.name == "nt" else permissions.posix_inspect
            self.assertEqual(inspector(backup)["state"], "RESTRICTED")
        self.assertNotIn(b"\n", (self.repo / "AGENTS.md").read_bytes().replace(b"\r\n", b""))
        self.assertEqual(self.registry.read_bytes(), registry_before)
        self.assertEqual(vault_before, {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()})
        audited = permissions.audit(self.registry)
        self.assertTrue(any(e["path"].startswith("adapter-backups/") for e in audited["entries"]))

    def test_new_claude_imports_existing_rules_instead_of_copying_or_suppressing_them(self):
        (self.repo / "AGENTS.md").write_bytes(b"Shared development rules\n")
        plan = self.preview("claude-code")
        self.apply(plan, "claude-code")
        content = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(content.startswith("@AGENTS.md\n\n"))
        self.assertNotIn("Shared development rules", content)
        self.assertIn("For Claude Code:", content)
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), b"Shared development rules\n")

    def test_both_new_files_share_rules_with_agent_specific_conditional_references(self):
        self.apply(self.preview())
        self.assertIn(b"For Codex:", (self.repo / "AGENTS.md").read_bytes())
        self.assertTrue((self.repo / "CLAUDE.md").read_bytes().startswith(b"@AGENTS.md\n"))

    def test_repeated_apply_preserves_files_without_duplicate_blocks(self):
        plan = self.preview()
        self.apply(plan)
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(self.apply(plan)["status"], "NATIVE_ADAPTER_ALREADY_INSTALLED")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_changed_native_rules_invalidates_whole_plan(self):
        plan = self.preview()
        (self.repo / "CLAUDE.md").write_bytes(b"user changed rules")
        with self.assertRaises(UamlError) as caught:
            self.apply(plan)
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.registry.parent / "adapter-backups").exists())

    def test_shared_rules_changed_before_new_claude_import_invalidates_plan(self):
        (self.repo / "AGENTS.md").write_bytes(b"before")
        plan = self.preview("claude-code")
        (self.repo / "AGENTS.md").write_bytes(b"after")
        with self.assertRaises(UamlError):
            self.apply(plan, "claude-code")
        self.assertFalse((self.repo / "CLAUDE.md").exists())

    def test_native_targets_require_installed_reviewed_manual_adapters(self):
        target = self.repo / ".uaml/adapters/CODEX.md"
        original = target.read_bytes()
        for raw in (None, b"custom instructions"):
            target.unlink(missing_ok=True)
            if raw:
                target.write_bytes(raw)
            with self.assertRaises(UamlError) as caught:
                self.preview("codex")
            self.assertEqual(caught.exception.code, "ADAPTER_REQUIRED")
        target.write_bytes(original.replace(b"\n", b"\r\n"))
        self.assertEqual(self.preview("codex")["status"], "NATIVE_ADAPTER_PREVIEW")

    def test_shadowing_override_is_not_silently_modified_or_ignored(self):
        override = self.repo / "AGENTS.override.md"
        override.write_bytes(b"authoritative override")
        with self.assertRaises(UamlError) as caught:
            self.preview("codex")
        self.assertEqual(caught.exception.code, "NATIVE_ENTRY_SHADOWED")
        self.assertEqual(override.read_bytes(), b"authoritative override")

    def test_custom_partial_duplicate_or_fenced_markers_refuse_automatic_changes(self):
        reference = native_adapters.block("codex")
        for content in (reference.replace("For Codex:", "custom"), reference + reference,
                        reference.splitlines()[0], "```md\n" + reference + "```\n", "```md\nunfinished"):
            (self.repo / "AGENTS.md").write_text(content, encoding="utf-8")
            with self.assertRaises(UamlError) as caught:
                self.preview("codex")
            self.assertEqual(caught.exception.code, "NATIVE_ENTRY_CONFLICT")

    def test_secrets_are_rejected_before_backup_or_output(self):
        raw = "github_pat_" + "A" * 30
        (self.repo / "AGENTS.md").write_text(raw, encoding="utf-8")
        with self.assertRaises(UamlError) as caught:
            self.preview("codex")
        self.assertEqual(caught.exception.code, "SENSITIVE_CONTENT")
        self.assertNotIn(raw, str(caught.exception))
        self.assertFalse((self.registry.parent / "adapter-backups").exists())

    def test_linked_entry_is_rejected_and_external_bytes_preserved(self):
        outside = self.base / "external instructions.md"
        outside.write_bytes(b"outside data")
        os.link(outside, self.repo / "AGENTS.md")
        with self.assertRaises(UamlError) as caught:
            self.preview("codex")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
        self.assertEqual(outside.read_bytes(), b"outside data")

    def test_oversized_entry_and_unclosed_comment_refuse_append(self):
        for raw, code in ((b"a" * 32768, "NATIVE_ENTRY_TOO_LARGE"), (b"<!-- unfinished", "NATIVE_ENTRY_CONFLICT")):
            (self.repo / "AGENTS.md").write_bytes(raw)
            with self.assertRaises(UamlError) as caught:
                self.preview("codex")
            self.assertEqual(caught.exception.code, code)

    def test_changed_backup_location_and_missing_review_are_rejected(self):
        plan = self.preview()
        for expected in (None, "0" * 64):
            with self.assertRaises(UamlError):
                native_adapters.install(self.git, self.registry, "all", expected)
        with self.assertRaises(UamlError):
            native_adapters.install(self.git, self.base / "other home" / "registry.json", "all", plan["plan_hash"])
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_unsafe_existing_backup_directory_stops_before_entry_changes(self):
        folder = self.registry.parent / "adapter-backups"
        folder.mkdir()
        plan = self.preview()
        inspector = "uaml.native_adapters.WindowsAcl.inspect" if os.name == "nt" else "uaml.native_adapters.posix_inspect"
        with patch(inspector, return_value={"state": "RISK", "issues": []}), self.assertRaises(UamlError) as caught:
            self.apply(plan)
        self.assertEqual(caught.exception.code, "NATIVE_BACKUP_UNSAFE")
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_interruption_preserves_backup_and_supports_fresh_preview_without_rollback(self):
        (self.repo / "AGENTS.md").write_bytes(b"original shared rules\n")
        (self.repo / "CLAUDE.md").write_bytes(b"original Claude rules\n")
        plan = self.preview()
        def interrupted(path, *args):
            if path == self.repo / "CLAUDE.md":
                raise OSError("fixture interruption")
            return write(path, *args)
        with patch("uaml.native_adapters.write", side_effect=interrupted), self.assertRaises(OSError):
            self.apply(plan)
        agents = (self.repo / "AGENTS.md").read_bytes()
        self.assertEqual((self.repo / "CLAUDE.md").read_bytes(), b"original Claude rules\n")
        self.assertEqual(len(list((self.registry.parent / "adapter-backups").glob("*.before"))), 2)
        fresh = self.preview()
        self.assertEqual([a["action"] for a in fresh["actions"]], ["keep", "append"])
        self.apply(fresh)
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), agents)

    def test_changes_during_backup_preparation_block_all_native_writes(self):
        (self.repo / "AGENTS.md").write_bytes(b"original rules\n")
        plan = self.preview()
        def edit_during_backup(path, *args):
            result = write(path, *args)
            if path.suffix == ".before":
                (self.repo / "AGENTS.md").write_bytes(b"concurrent user change\n")
            return result
        with patch("uaml.native_adapters.write", side_effect=edit_during_backup), self.assertRaises(UamlError) as caught:
            self.apply(plan)
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), b"concurrent user change\n")
        self.assertFalse((self.repo / "CLAUDE.md").exists())

    def test_cli_native_preview_and_explicit_apply(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "adapter", "--agent", "all", "--native"]
        result = subprocess.run(command, capture_output=True, check=True)
        plan = json.loads(result.stdout)
        applied = subprocess.run(command + ["--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout)["status"], "NATIVE_ADAPTER_INSTALLED")
