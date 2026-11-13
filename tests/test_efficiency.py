"""T15 CLI measurements against an isolated, synthetic repository and Vault."""
import io
import json
import unittest
from contextlib import redirect_stdout
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from uaml.cli import main
from uaml.formats import digest, frontmatter, markdown, read_at_most
from uaml.project_memory import checkpoint

from .test_knowledge import KnowledgeWorkspace

NOTE_BYTES = 84 * 1024
SCAN_BYTES = 16 * 1024 * 1024


class EfficiencyTests(KnowledgeWorkspace):
    def measure_cli(self, *arguments):
        reads = []

        def measured(path, size, missing="MEMORY_MISSING"):
            raw = read_at_most(path, size, missing)
            reads.append((path, len(raw)))
            return raw

        output = io.StringIO()
        started = perf_counter()
        with (redirect_stdout(output), patch("uaml.formats.read_at_most", side_effect=measured),
              patch("uaml.knowledge.read_at_most", side_effect=measured)):
            exit_code = main(["--repo", str(self.repo), "--registry", str(self.registry), "--json", *arguments])
        elapsed = round((perf_counter() - started) * 1000, 1)
        stdout = output.getvalue().encode("utf-8")
        knowledge_root = self.vault / "UAML/Knowledge"
        note_reads = [(path, size) for path, size in reads if path.is_relative_to(knowledge_root)]
        self.assertNotIn(self.vault / "private.md", {path for path, _ in reads})
        stats = {"command": " ".join(arguments), "elapsed_ms": elapsed, "stdout_bytes": len(stdout),
                 "knowledge_files_read": len(note_reads), "knowledge_bytes_read": sum(size for _, size in note_reads),
                 "total_uaml_bytes_read": sum(size for _, size in reads)}
        if __name__ == "__main__":
            print(json.dumps(stats, ensure_ascii=False))
        return exit_code, json.loads(stdout), stats

    def test_large_recovery_and_search_stay_inside_read_and_output_budgets(self):
        handoff = self.repo / "docs/memory/HANDOFF.md"
        header, _ = frontmatter(handoff.read_bytes())
        handoff.write_bytes(markdown(header, "## 已完成\n" + "歷史細節\\\"\t" * 12000
                                     + "\n## Blockers\n確認測試環境。\n## 下一步\n執行驗收。\n"))
        checkpoint(self.git, self.registry, "fixture")
        (self.vault / "private.md").write_text("跨機驗收", encoding="utf-8")
        root = self.vault / "UAML/Knowledge"
        root.mkdir(parents=True)
        header, _ = self.note(title="跨機驗收")

        padding = b"Synthetic content.\n"

        def populate(first, last):
            for index in range(first, last + 1):
                header["id"] = str(UUID(int=index))
                raw = markdown(header, "合成驗收筆記\n")
                repetitions, remainder = divmod(NOTE_BYTES - len(raw), len(padding))
                (root / f"{header['id']}.md").write_bytes(raw + padding * repetitions + padding[:remainder])

        def snapshot():
            return {path: digest(path.read_bytes()) for path in self.base.rglob("*") if path.is_file()}

        populate(1, 190)
        before = snapshot()
        exit_code, recovered, recovery_io = self.measure_cli("recover", "--compact")
        self.assertEqual(exit_code, 0)
        self.assertEqual(recovered["status"], "RECOVERED")
        self.assertLessEqual(recovery_io["stdout_bytes"], 32 * 1024)
        self.assertEqual(recovery_io["knowledge_files_read"], 0)
        self.assertTrue(recovered["budget"]["truncated"])
        sections = [section for source in recovered["sources"] for section in source["sections"]]
        self.assertTrue(any("執行驗收" in section["untrusted_markdown"] for section in sections))

        command = ("knowledge", "search", "跨機驗收")
        exit_code, found, search_io = self.measure_cli(*command)
        self.assertEqual(exit_code, 0)
        self.assertEqual(found["status"], "KNOWLEDGE_RESULTS")
        self.assertEqual(found["total_matches"], 190)
        self.assertEqual(len(found["results"]), 5)
        self.assertTrue(found["truncated"])
        self.assertTrue(all(result["truncated"] for result in found["results"]))
        self.assertEqual(search_io["knowledge_files_read"], 190)
        self.assertEqual(search_io["knowledge_bytes_read"], 190 * NOTE_BYTES)
        self.assertEqual(snapshot(), before)

        populate(191, 200)
        before = snapshot()
        exit_code, limited, limit_io = self.measure_cli(*command)
        self.assertEqual(exit_code, 1)
        self.assertEqual(limited["status"], "DEGRADED")
        self.assertFalse(limited["complete"])
        self.assertIn("SCAN_LIMIT", {diagnostic["code"] for diagnostic in limited["diagnostics"]})
        self.assertEqual(limited["scanned"], SCAN_BYTES // NOTE_BYTES)
        self.assertEqual(limit_io["knowledge_files_read"], SCAN_BYTES // NOTE_BYTES + 1)
        self.assertEqual(limit_io["knowledge_bytes_read"], SCAN_BYTES + 1)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
