from unittest.mock import patch

from uaml.context import recover_context
from uaml.formats import digest, frontmatter, json_bytes, markdown
from uaml.recovery import recover
from uaml.validation import validate

from .support import Workspace


class FreshnessTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()
        self.git_cmd("add", ".")
        self.git_cmd("commit", "-m", "persist memory")

    def test_memory_commit_is_recovered_with_evidence_and_no_writes(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch.object(self.git, "memory_history", wraps=self.git.memory_history) as observed:
            report = recover(self.git, self.registry)
        self.assertEqual(report["status"], "RECOVERED")
        self.assertTrue(all(s["head_evidence"]["status"] == "MEMORY_ONLY" for s in report["sources"]))
        self.assertNotEqual(report["sources"][0]["head_evidence"]["saved_head"], report["git"]["snapshot"]["head"])
        self.assertEqual(observed.call_count, 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})
        self.assertEqual(validate(self.git, self.registry)["status"], "VALIDATED")
        self.assertEqual(recover_context(self.git, self.registry)["sources"][0]["head_evidence"]["status"], "MEMORY_ONLY")

    def test_code_commit_remains_stale(self):
        (self.repo / "app.py").write_text("changed code\n", encoding="utf-8")
        self.git_cmd("add", "app.py")
        self.git_cmd("commit", "-m", "code change")
        report = recover(self.git, self.registry)
        self.assertIn("STALE_MEMORY", {d["code"] for d in report["diagnostics"]})
        self.assertEqual(report["sources"][0]["head_evidence"]["status"], "CODE_CHANGED")

    def test_code_change_then_revert_is_not_hidden_by_equal_end_trees(self):
        original = (self.repo / "app.py").read_bytes()
        (self.repo / "app.py").write_bytes(b"temporary code change\n")
        self.git_cmd("add", "app.py")
        self.git_cmd("commit", "-m", "temporary change")
        (self.repo / "app.py").write_bytes(original)
        self.git_cmd("add", "app.py")
        self.git_cmd("commit", "-m", "restore content")
        self.assertEqual(recover(self.git, self.registry)["sources"][0]["head_evidence"]["status"], "CODE_CHANGED")

    def test_branch_change_is_still_reported(self):
        self.git_cmd("checkout", "-b", "different-work")
        report = recover(self.git, self.registry)
        self.assertEqual(report["status"], "DEGRADED")
        self.assertIn("branch", report["sources"][0]["git_differences"])

    def test_unknown_saved_commit_is_not_accepted(self):
        file = self.repo / "docs/memory/PROJECT-STATE.md"
        header, body = frontmatter(file.read_bytes())
        header["git"]["head"] = "f" * 40
        raw = markdown(header, body)
        file.write_bytes(raw)
        import json
        checkpoint = self.repo / "docs/memory/checkpoint.json"
        value = json.loads(checkpoint.read_bytes())
        value["files"]["docs/memory/PROJECT-STATE.md"] = digest(raw)
        checkpoint.write_bytes(json_bytes(value))
        report = recover(self.git, self.registry)
        self.assertIn("HEAD_UNVERIFIED", {d["code"] for d in report["diagnostics"]})
        self.assertIn("head", report["sources"][0]["git_differences"])

    def test_history_budget_stays_unverified(self):
        self.git_cmd("commit", "--allow-empty", "-m", "more history")
        with patch("uaml.git_state.MAX_MEMORY_COMMITS", 1):
            report = recover(self.git, self.registry)
        self.assertIn("HEAD_UNVERIFIED", {d["code"] for d in report["diagnostics"]})

    def test_unrecognized_adapter_code_is_not_treated_as_memory(self):
        file = self.repo / ".uaml/adapters/execute.py"
        file.parent.mkdir()
        file.write_text("print('code')\n", encoding="utf-8")
        self.git_cmd("add", ".uaml/adapters/execute.py")
        self.git_cmd("commit", "-m", "code in metadata area")
        self.assertEqual(recover(self.git, self.registry)["sources"][0]["head_evidence"]["status"], "CODE_CHANGED")

    def test_moved_or_diverged_history_stays_unverified(self):
        self.git_cmd("checkout", "--orphan", "independent-history")
        self.git_cmd("commit", "-m", "unrelated root")
        report = recover(self.git, self.registry)
        self.assertIn("HEAD_UNVERIFIED", {d["code"] for d in report["diagnostics"]})
