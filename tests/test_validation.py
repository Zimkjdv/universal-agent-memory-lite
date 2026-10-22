import json
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from uaml.binding import trust
from uaml.formats import frontmatter, markdown
from uaml.knowledge import add
from uaml.project_memory import checkpoint
from uaml.validation import validate

from .support import Workspace
from .test_knowledge import KnowledgeWorkspace


class ValidationTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()

    def test_validated_is_read_only_and_knowledge_is_opt_in(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch("uaml.validation.knowledge.scan", side_effect=AssertionError("unexpected knowledge read")):
            result = validate(self.git, self.registry)
        self.assertEqual(result["status"], "VALIDATED")
        self.assertEqual(result["checks"][-1]["status"], "NOT_REQUESTED")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_missing_file_does_not_hide_other_valid_sources(self):
        (self.repo / "docs/memory/PROJECT-STATE.md").unlink()
        result = validate(self.git, self.registry)
        self.assertEqual(result["status"], "VALIDATION_ISSUES")
        self.assertTrue(any(c["area"] == "handoff" and c["status"] == "VALID" for c in result["checks"]))
        self.assertTrue(any(c["area"] == "project_state" and c["status"] == "UNVERIFIED" for c in result["checks"]))

    def test_missing_duplicate_and_empty_sections_are_reported(self):
        file = self.repo / "docs/memory/HANDOFF.md"
        header, body = frontmatter(file.read_bytes())
        body = body.replace("## 下一步\n補齊實際工作與驗證結果。", "## 下一步\n")
        body += "\n## 已完成\nconflicting second section\n"
        file.write_bytes(markdown(header, body))
        checkpoint(self.git, self.registry, "manual")
        result = validate(self.git, self.registry)
        issues = [d for d in result["diagnostics"] if d["code"] == "MEMORY_SECTION_INVALID"]
        self.assertEqual(len(issues), 2)

    def test_headings_inside_code_do_not_satisfy_missing_sections(self):
        file = self.repo / "docs/memory/HANDOFF.md"
        header, body = frontmatter(file.read_bytes())
        body = "```markdown\n" + body + "\n```\n"
        file.write_bytes(markdown(header, body))
        checkpoint(self.git, self.registry, "manual")
        result = validate(self.git, self.registry)
        self.assertEqual(sum(d["code"] == "MEMORY_SECTION_INVALID" for d in result["diagnostics"]), 10)

    def test_code_is_allowed_as_section_content(self):
        file = self.repo / "docs/memory/HANDOFF.md"
        header, body = frontmatter(file.read_bytes())
        body = body.replace("補齊實際工作與驗證結果。", "```text\ninspect the tests\n```")
        file.write_bytes(markdown(header, body))
        checkpoint(self.git, self.registry, "manual")
        self.assertEqual(validate(self.git, self.registry)["status"], "VALIDATED")

    def test_stale_git_and_broken_checkpoint_are_issues(self):
        (self.repo / "app.py").write_text("new code\n", encoding="utf-8")
        result = validate(self.git, self.registry)
        self.assertIn("STALE_MEMORY", {d["code"] for d in result["diagnostics"]})
        (self.repo / "docs/memory/checkpoint.json").write_text("{}", encoding="utf-8")
        result = validate(self.git, self.registry)
        self.assertEqual(result["checks"][-2]["status"], "UNVERIFIED")

    def test_optional_knowledge_does_not_bypass_authorization(self):
        with patch("uaml.validation.knowledge.scan", side_effect=AssertionError("unauthorized read")):
            result = validate(self.git, self.registry, True)
        self.assertIn("KNOWLEDGE_ACCESS_DENIED", {d["code"] for d in result["diagnostics"]})

    def test_cli_success_and_diagnostic_exit_codes(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "validate"]
        good = subprocess.run(command, capture_output=True)
        self.assertEqual(good.returncode, 0)
        self.assertEqual(json.loads(good.stdout.decode("utf-8"))["status"], "VALIDATED")
        (self.repo / "docs/memory/HANDOFF.md").write_text("broken", encoding="utf-8")
        bad = subprocess.run(command, capture_output=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout.decode("utf-8"))["status"], "VALIDATION_ISSUES")


class KnowledgeValidationTests(KnowledgeWorkspace):
    def test_missing_knowledge_and_project_index_references(self):
        header, body = self.note()
        header["related_ids"] = [str(uuid4())]
        add(self.git, self.registry, self.source(header, body))
        index = next((self.vault / "UAML/Projects").glob("*/PROJECT.md"))
        link, link_body = frontmatter(index.read_bytes())
        link["knowledge_ids"] = [str(uuid4())]
        index.write_bytes(markdown(link, link_body))
        result = validate(self.git, self.registry, True)
        self.assertTrue({"KNOWLEDGE_LINK_MISSING", "PROJECT_KNOWLEDGE_LINK_MISSING"}.issubset({d["code"] for d in result["diagnostics"]}))

    def test_valid_supersession_and_cycle_detection(self):
        first, first_body = self.note()
        second, second_body = self.note(title="replacement", body="# Changed\nUpdated procedure.")
        first.update(status="superseded", superseded_by=second["id"])
        second["supersedes"] = [first["id"]]
        root = self.vault / "UAML/Knowledge"
        root.mkdir(parents=True)
        (root / f"{first['id']}.md").write_bytes(markdown(first, first_body))
        (root / f"{second['id']}.md").write_bytes(markdown(second, second_body))
        self.assertEqual(validate(self.git, self.registry, True)["status"], "VALIDATED")
        first["supersedes"] = [second["id"]]
        (root / f"{first['id']}.md").write_bytes(markdown(first, first_body))
        result = validate(self.git, self.registry, True)
        self.assertIn("SUPERSESSION_CYCLE", {d["code"] for d in result["diagnostics"]})

    def test_corrupt_catalog_never_claims_reference_completeness(self):
        root = self.vault / "UAML/Knowledge"
        root.mkdir(parents=True)
        (root / "broken.md").write_text("broken", encoding="utf-8")
        result = validate(self.git, self.registry, True)
        self.assertEqual(result["checks"][-1]["status"], "INCOMPLETE")
        self.assertEqual(result["status"], "VALIDATION_ISSUES")
