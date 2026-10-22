import json
import subprocess
import sys
from unittest.mock import patch

from uaml import adapters
from uaml.binding import trust
from uaml.context import recover_context
from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown
from uaml.project_memory import checkpoint
from uaml.storage import lock, write

from .support import Workspace


class AdapterTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind(approve=False)

    def test_preview_is_readonly_without_vault_permission(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch("uaml.registry.read_vault", side_effect=AssertionError("adapter must not read Vault")):
            plan = adapters.preview(self.git, "all")
        self.assertEqual(plan["status"], "ADAPTER_PREVIEW")
        self.assertEqual(len(plan["files"]), 3)
        self.assertEqual(plan["activation"]["mode"], "manual")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_install_preserves_rules_registry_vault_and_working_code(self):
        protected = [self.repo / name for name in ("AGENTS.md", "CLAUDE.md", "REQUIREMENTS.md", "AGENTS-MAINTENANCE.md")]
        for path in protected:
            path.write_text("existing user rules\n", encoding="utf-8")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        plan = adapters.preview(self.git, "all")
        result = adapters.install(self.git, "all", plan["plan_hash"])
        self.assertEqual(result["status"], "ADAPTER_INSTALLED")
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        after = {p for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(after - set(before), {self.repo / relative for relative in plan["files"]})
        self.assertEqual(adapters.install(self.git, "all", plan["plan_hash"])["status"], "ADAPTER_ALREADY_INSTALLED")

    def test_existing_different_file_blocks_all_writes(self):
        path = self.repo / ".uaml/adapters/CODEX.md"
        path.parent.mkdir()
        path.write_text("user's custom adapter\n", encoding="utf-8")
        plan = adapters.preview(self.git, "codex")
        self.assertEqual(plan["status"], "ADAPTER_CONFLICT")
        with self.assertRaises(UamlError) as caught:
            adapters.install(self.git, "codex", plan["plan_hash"])
        self.assertEqual(caught.exception.code, "ADAPTER_CONFLICT")
        self.assertFalse((path.parent / "WORKFLOW.md").exists())
        self.assertEqual(path.read_text(encoding="utf-8"), "user's custom adapter\n")

    def test_stale_plan_is_rejected_after_remote_or_binding_change(self):
        plan = adapters.preview(self.git, "codex")
        self.git_cmd("remote", "add", "origin", "https://example.invalid/new")
        with self.assertRaises(UamlError) as caught:
            adapters.install(self.git, "codex", plan["plan_hash"])
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")
        self.assertFalse((self.repo / ".uaml/adapters").exists())

    def test_invalid_plan_and_missing_plan_do_not_write(self):
        for expected in (None, "0" * 64):
            with self.assertRaises(UamlError):
                adapters.install(self.git, "codex", expected)
        self.assertFalse((self.repo / ".uaml/adapters").exists())

    def test_live_repo_lock_is_respected(self):
        plan = adapters.preview(self.git, "codex")
        with lock(self.repo / ".uaml/write.lock"), self.assertRaises(UamlError) as caught:
            adapters.install(self.git, "codex", plan["plan_hash"])
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")

    def test_interrupted_creation_can_be_repreviewed_without_overwrite(self):
        plan = adapters.preview(self.git, "all")

        def interrupted(path, *args):
            if path.name == "CODEX.md":
                raise OSError("fixture interruption")
            return write(path, *args)

        with patch("uaml.adapters.write", side_effect=interrupted), self.assertRaises(OSError):
            adapters.install(self.git, "all", plan["plan_hash"])
        shared = self.repo / ".uaml/adapters/WORKFLOW.md"
        before = shared.read_bytes()
        next_plan = adapters.preview(self.git, "all")
        adapters.install(self.git, "all", next_plan["plan_hash"])
        self.assertEqual(shared.read_bytes(), before)
        self.assertTrue((shared.parent / "CLAUDE-CODE.md").is_file())

    def test_generated_files_are_portable_and_share_one_protocol(self):
        plan = adapters.preview(self.git, "all")
        for content in plan["files"].values():
            self.assertNotIn(str(self.base), content)
            self.assertNotIn(self.vault_id, content)
        for relative in (".uaml/adapters/CODEX.md", ".uaml/adapters/CLAUDE-CODE.md"):
            self.assertIn("WORKFLOW.md", plan["files"][relative])
            self.assertNotIn("checkpoint --agent", plan["files"][relative])
        self.assertIn("recover --compact", plan["files"][".uaml/adapters/WORKFLOW.md"])

    def test_protocol_supports_codex_claude_codex_saved_agent_names(self):
        trust(self.git, self.registry)
        for agent in ("codex", "claude-code", "codex"):
            file = self.repo / "docs/memory/HANDOFF.md"
            header, body = frontmatter(file.read_bytes())
            file.write_bytes(markdown(header, body.replace("尚待填寫。", f"Saved by {agent}.")))
            checkpoint(self.git, self.registry, agent)
            report = recover_context(self.git, self.registry)
            self.assertEqual(report["status"], "RECOVERED")
            self.assertTrue(all(s["metadata"]["source_agent"] == agent for s in report["sources"]))

    def test_cli_preview_and_apply(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "adapter", "--agent", "all"]
        preview = subprocess.run(command, capture_output=True, check=True)
        plan = json.loads(preview.stdout)
        applied = subprocess.run(command + ["--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout)["status"], "ADAPTER_INSTALLED")
