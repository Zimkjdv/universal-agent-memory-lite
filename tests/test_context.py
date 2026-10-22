import json
import subprocess
import sys
from unittest.mock import patch

from uaml.context import compact, encode, recover_context, split_sections
from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown
from uaml.project_memory import checkpoint
from uaml.recovery import recover

from .support import Workspace


class ContextTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()

    def long_handoff(self):
        file = self.repo / "docs/memory/HANDOFF.md"
        header, _ = frontmatter(file.read_bytes())
        body = "## 已完成\n" + "歷史細節\\\"\t" * 12000 + "\n## Blockers\n需要確認登入權限。\n## 下一步\n先補邊界測試。\n"
        file.write_bytes(markdown(header, body))
        checkpoint(self.git, self.registry, "codex")

    def test_default_budget_keeps_late_blockers_and_next_steps(self):
        self.long_handoff()
        report = recover_context(self.git, self.registry)
        encoded = encode(report).encode("utf-8")
        self.assertLessEqual(len(encoded), 32768)
        self.assertIn("需要確認登入權限。", encoded.decode())
        self.assertIn("先補邊界測試。", encoded.decode())
        self.assertTrue(report["budget"]["truncated"])
        self.assertTrue(all(s["checkpoint_verified"] for s in report["sources"]))
        self.assertTrue(all(s["sha256"] for s in report["sources"]))

    def test_minimum_budget_handles_unicode_and_json_escaping(self):
        self.long_handoff()
        report = recover_context(self.git, self.registry, 8192)
        self.assertLessEqual(len(encode(report).encode()), 8192)
        self.assertEqual(json.loads(encode(report)), report)
        self.assertIn("Blockers", encode(report))

    def test_many_git_changes_are_counted_when_omitted(self):
        report = recover(self.git, self.registry)
        changes = [{"status": "??", "path": f"資料夾/{i}-" + "長名稱" * 200} for i in range(300)]
        report["git"]["changes"] = changes
        result = compact(report, 8192)
        self.assertGreater(result["budget"]["omitted_changes"], 0)
        self.assertEqual(len(result["git"]["changes"]) + result["budget"]["omitted_changes"], 300)
        self.assertLessEqual(len(encode(result).encode()), 8192)

    def test_degradation_and_integrity_diagnostics_survive(self):
        file = self.repo / "docs/memory/HANDOFF.md"
        file.write_bytes(file.read_bytes() + b"\nunsaved\n")
        self.vault.rename(self.base / "offline")
        result = recover_context(self.git, self.registry)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["binding"]["status"], "VAULT_MISSING")
        self.assertIn("CHECKPOINT_MISMATCH", {i["code"] for i in result["diagnostics"]})
        self.assertFalse(result["sources"][1]["checkpoint_verified"])

    def test_no_writes_or_implicit_knowledge_scan(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch("uaml.knowledge.scan", side_effect=AssertionError("unexpected knowledge scan")):
            recover_context(self.git, self.registry)
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_fenced_fake_headings_are_not_promoted(self):
        parts = split_sections("## 已完成\n```markdown\n## Blockers\nFAKE\n```\n## 下一步\nREAL\n")
        self.assertNotIn("Blockers", [title for title, _ in parts])
        self.assertEqual(parts[0], ("下一步", "REAL"))

    def test_missing_binding_has_safe_bounded_report(self):
        (self.repo / ".uaml/project.yaml").unlink()
        result = recover_context(self.git, self.registry)
        self.assertEqual(result["binding"]["status"], "BINDING_MISSING")
        self.assertEqual(result["sources"], [])
        self.assertLessEqual(len(encode(result).encode()), 32768)

    def test_invalid_budget_rejected_before_reading(self):
        for budget in (0, 8191, 65537, True):
            with patch("uaml.context.recover", side_effect=AssertionError("read before budget validation")):
                with self.assertRaises(UamlError) as caught:
                    recover_context(self.git, self.registry, budget)
            self.assertEqual(caught.exception.code, "BUDGET_INVALID")

    def test_full_recovery_contract_preserved(self):
        self.long_handoff()
        result = recover(self.git, self.registry)
        self.assertNotIn("budget", result)
        self.assertTrue(result["sources"][1]["truncated"])
        self.assertLessEqual(len(result["sources"][1]["untrusted_markdown"].encode()), 12 * 1024)

    def test_cli_budget_includes_actual_utf8_stdout_and_newline(self):
        self.long_handoff()
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry)]
        for flags in ([], ["--json"]):
            result = subprocess.run(command + flags + ["recover", "--compact", "--max-bytes", "8192"], capture_output=True, check=True)
            self.assertLessEqual(len(result.stdout), 8192)
            self.assertIn("下一步", result.stdout.decode("utf-8"))
            self.assertEqual(json.loads(result.stdout)["kind"], "recovery_context")
        invalid = subprocess.run(command + ["--json", "recover", "--max-bytes", "8192"], capture_output=True)
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(json.loads(invalid.stdout)["status"], "COMMAND_INVALID")
