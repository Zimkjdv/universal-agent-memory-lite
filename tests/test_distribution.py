from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.verify_distribution import audit_wheel, requirement, safe_names


class DistributionTests(unittest.TestCase):
    def test_unsafe_archive_paths_are_rejected(self):
        for name in ("", ".", "/absolute", "../outside", "a/../../outside", "C:/local", "a\\b", "pkg/.venv/secret", "pkg/.uaml-local/registry.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_names([name])

    def test_normal_archive_paths_are_accepted(self):
        safe_names(["uaml/cli.py", "package/docs/MIGRATION-GUIDE.md", "package/tests/test_migration.py"])

    def test_dependency_order_and_case_are_compared_consistently(self):
        self.assertEqual(requirement("PyYAML>=6.0.2,<7"), requirement("pyyaml<7,>=6.0.2"))

    def test_wheel_without_required_modules_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="uaml-bad-wheel-") as folder:
            path = Path(folder) / "incomplete.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("uaml/__init__.py", "")
            with self.assertRaises(ValueError):
                audit_wheel(path)

    def test_wheel_with_private_payload_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="uaml-private-wheel-") as folder:
            path = Path(folder) / "private.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(".uaml-local/registry.json", "{}")
            with self.assertRaises(ValueError):
                audit_wheel(path)
