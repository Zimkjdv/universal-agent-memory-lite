import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from uaml import permissions
from uaml.errors import UamlError

from .support import Workspace


class PermissionTests(Workspace):
    def test_readonly_audit_checks_known_private_artifacts_without_opening_content(self):
        artifact = self.registry.parent / "proposals" / "fixture.md"
        artifact.parent.mkdir()
        artifact.write_text("private payload", encoding="utf-8")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        visited = []
        def restricted(path):
            visited.append(path)
            return {"state": "RESTRICTED", "issues": []}
        with patch.object(Path, "open", side_effect=AssertionError("audit opened content")):
            result = permissions.audit(self.registry, restricted)
        self.assertEqual(result["status"], "PERMISSIONS_RESTRICTED")
        self.assertIn(artifact, visited)
        self.assertFalse(any(p.is_relative_to(self.vault) for p in visited))
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_missing_registry_is_not_initialized(self):
        missing = self.base / "not-created" / "registry.json"
        with self.assertRaises(UamlError) as caught:
            permissions.audit(missing)
        self.assertEqual(caught.exception.code, "REGISTRY_MISSING")
        self.assertFalse(missing.parent.exists())

    def test_repo_or_vault_registry_rejected(self):
        for location in (self.repo / "registry.json", self.vault / "registry.json"):
            with self.assertRaises(UamlError):
                permissions.audit(location)

    def test_unreadable_acl_is_unverified_not_success(self):
        def denied(path):
            raise PermissionError("fixture")
        result = permissions.audit(self.registry, denied)
        self.assertEqual(result["status"], "PERMISSION_ISSUES")
        self.assertFalse(result["complete"])
        self.assertTrue(all(e["state"] == "UNVERIFIED" for e in result["entries"]))

    def test_nested_artifact_directory_not_traversed(self):
        nested = self.registry.parent / "backups" / "unexpected"
        nested.mkdir(parents=True)
        secret = nested / "unrelated-private.txt"
        secret.write_text("do not inspect", encoding="utf-8")
        visited = []
        def inspector(path):
            visited.append(path)
            return {"state": "RESTRICTED", "issues": []}
        result = permissions.audit(self.registry, inspector)
        self.assertNotIn(secret, visited)
        self.assertFalse(result["complete"])

    def test_budget_reports_incomplete(self):
        folder = self.registry.parent / "backups"
        folder.mkdir(exist_ok=True)
        for index in range(8):
            (folder / f"{index}.bak").write_bytes(b"private")
        with patch("uaml.permissions.MAX_TARGETS", 5):
            result = permissions.audit(self.registry, lambda p: {"state": "RESTRICTED", "issues": []})
        self.assertFalse(result["complete"])
        self.assertIn("AUDIT_LIMIT", {d["code"] for d in result["diagnostics"]})
        self.assertLessEqual(len(result["entries"]), 5)

    def test_multiple_hard_links_require_manual_review(self):
        linked = self.registry.parent / "shared-alias.json"
        os.link(self.registry, linked)
        result = permissions.audit(self.registry, lambda p: {"state": "RESTRICTED", "issues": []})
        self.assertTrue(any(i["code"] == "AUDIT_HARDLINK" for e in result["entries"] for i in e["issues"]))

    def test_windows_grants_null_empty_and_unknown_aces_are_distinguished(self):
        current = "S-1-5-21-123"
        base = {"owner_sid": current, "dacl_null": False, "aces": [{"type": "allow", "sid": current, "mask": 0x1F01FF, "inherit_only": False}]}
        self.assertEqual(permissions.evaluate_windows(base, current)["state"], "RESTRICTED")
        cases = [({**base, "dacl_null": True}, "RISK"), ({**base, "aces": []}, "UNVERIFIED"),
                 ({**base, "aces": [{"type": "unknown"}]}, "UNVERIFIED"),
                 ({**base, "aces": base["aces"] + [{"type": "allow", "sid": "S-1-1-0", "mask": 1, "inherit_only": True}]}, "RISK")]
        for value, state in cases:
            self.assertEqual(permissions.evaluate_windows(value, current)["state"], state)

    def test_windows_native_acl_detects_real_world_read_grant(self):
        if os.name != "nt":
            self.skipTest("Windows native DACL test")
        file = self.base / "ACL fixture.txt"
        file.write_text("synthetic data", encoding="utf-8")
        backend = permissions.WindowsAcl()
        original = file.read_bytes()
        granted = subprocess.run(["icacls", str(file), "/grant", "*S-1-1-0:R"], capture_output=True)
        self.assertEqual(granted.returncode, 0, "Cannot prepare a real ACL fixture")
        result = backend.inspect(file)
        self.assertEqual(result["state"], "RISK")
        self.assertIn("S-1-1-0", {issue.get("principal") for issue in result["issues"]})
        self.assertEqual(file.read_bytes(), original)

    def test_cli_audit_runs_without_git_and_reports_actual_acl_findings(self):
        result = subprocess.run([sys.executable, "-m", "uaml", "--repo", str(self.base), "--registry", str(self.registry), "--json", "registry", "audit"], capture_output=True)
        report = json.loads(result.stdout)
        self.assertIn(report["status"], ("PERMISSIONS_RESTRICTED", "PERMISSION_ISSUES"))
        self.assertEqual(result.returncode, 0 if report["status"] == "PERMISSIONS_RESTRICTED" else 1)
