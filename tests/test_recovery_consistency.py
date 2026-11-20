from unittest.mock import patch

from uaml.context import recover_context
from uaml.formats import frontmatter, markdown, read_bytes
from uaml.migration import check
from uaml.project_memory import checkpoint
from uaml.recovery import recover
from uaml.validation import validate

from .support import Workspace


class RecoveryConsistencyTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()
        self.note = self.repo / "docs/memory/HANDOFF.md"

    def during_read(self, operation, change):
        changed = False

        def read(path, *args):
            nonlocal changed
            raw = read_bytes(path, *args)
            if path == self.note and not changed:
                changed = True
                change()
            return raw

        with patch("uaml.recovery.read_bytes", side_effect=read):
            result = operation()
        self.assertTrue(changed)
        return result

    def save(self):
        header, body = frontmatter(self.note.read_bytes())
        self.note.write_bytes(markdown(header, body + "\nConcurrent saved work.\n"))
        checkpoint(self.git, self.registry, "another-agent")

    def test_complete_checkpoint_during_recovery_invalidates_captured_sources(self):
        report = self.during_read(lambda: recover(self.git, self.registry), self.save)
        self.assertEqual(report["status"], "DEGRADED")
        self.assertIn("MEMORY_CHANGED_DURING_READ", {item["code"] for item in report["diagnostics"]})
        self.assertEqual(report["sources"], [])
        self.assertEqual(recover(self.git, self.registry)["status"], "RECOVERED")

    def test_manual_edit_during_recovery_is_detected_without_a_checkpoint_write(self):
        report = self.during_read(lambda: recover(self.git, self.registry),
                                  lambda: self.note.write_bytes(self.note.read_bytes() + b"\nnew manual edit\n"))
        self.assertEqual(report["status"], "DEGRADED")
        self.assertEqual(report["sources"], [])
        self.assertIn("MEMORY_CHANGED_DURING_READ", {item["code"] for item in report["diagnostics"]})
        self.assertTrue(self.note.read_bytes().endswith(b"new manual edit\n"))

    def test_compact_validation_and_migration_inherit_read_conflict(self):
        operations = (lambda: recover_context(self.git, self.registry),
                      lambda: validate(self.git, self.registry),
                      lambda: check(self.git, self.registry, "local"))
        for operation in operations:
            with self.subTest(operation=operation):
                report = self.during_read(operation, self.save)
                self.assertIn("MEMORY_CHANGED_DURING_READ", {item["code"] for item in report["diagnostics"]})
                self.assertNotIn(report["status"], ("RECOVERED", "VALIDATED", "MIGRATION_CHECKED"))

    def test_read_failure_during_final_verification_keeps_diagnostic(self):
        report = self.during_read(lambda: recover(self.git, self.registry), self.note.unlink)
        self.assertEqual(report["status"], "DEGRADED")
        self.assertEqual(report["sources"], [])
        self.assertIn("MEMORY_MISSING", {item["code"] for item in report["diagnostics"]})

    def test_validation_uses_the_same_body_as_the_recovered_hash(self):
        from uaml.recovery import recover as original_recover

        def recovered(*args, **kwargs):
            result = original_recover(*args, **kwargs)
            header, _ = frontmatter(self.note.read_bytes())
            self.note.write_bytes(markdown(header, "## unrelated\nNew manual content.\n"))
            return result

        with patch("uaml.validation.recover", side_effect=recovered):
            report = validate(self.git, self.registry)
        self.assertEqual(report["status"], "VALIDATED")
        self.assertEqual(self.note.read_bytes().split(b"---\n")[-1], b"## unrelated\nNew manual content.\n")
