import json
import os
import subprocess
import unittest
from unittest.mock import patch

from uaml.errors import UamlError
from uaml.formats import json_bytes
from uaml.permissions import WindowsAcl
from uaml.project_memory import checkpoint, checkpoint_marker
from uaml.recovery import recover
from uaml.repair import repair
from uaml.storage import write

from .support import Workspace


def restore_dacl(directory, saved_acl, backend):
    """Restore this fixture's saved DACL without requiring SeRestorePrivilege."""
    from ctypes import wintypes as w

    c = backend.c
    descriptor, dacl = c.c_void_p(), c.c_void_p()
    present, defaulted = w.BOOL(), w.BOOL()
    convert = backend.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes, convert.restype = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p], w.BOOL
    extract = backend.adv.GetSecurityDescriptorDacl
    extract.argtypes = [c.c_void_p, c.POINTER(w.BOOL), c.POINTER(c.c_void_p), c.POINTER(w.BOOL)]
    extract.restype = w.BOOL
    set_info = backend.adv.SetNamedSecurityInfoW
    set_info.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p]
    set_info.restype = w.DWORD
    sddl = saved_acl.read_text(encoding="utf-16-le").splitlines()[1]
    if not convert(sddl, 1, c.byref(descriptor), None):
        raise OSError("Cannot parse the fixture's saved DACL.")
    try:
        if not extract(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)) or not present:
            raise OSError("Cannot read the fixture's saved DACL.")
        code = set_info(str(directory), 1, 4, None, None, dacl, None)
        if code:
            raise OSError(code, "Cannot restore the fixture's DACL.")
    finally:
        backend.kernel.LocalFree(descriptor)


class CheckpointLocationTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()

    def interrupted(self):
        def fail(path, *args, **kwargs):
            if path.name == "HANDOFF.md":
                raise OSError("fixture interruption")
            return write(path, *args, **kwargs)

        with patch("uaml.project_memory.write", side_effect=fail):
            with self.assertRaises(OSError):
                checkpoint(self.git, self.registry, "test-agent")
        return json.loads(checkpoint_marker(self.git).read_bytes())["snapshot_id"]

    def test_new_checkpoints_use_project_marker_and_preserve_git_files(self):
        directory = self.git.directory()
        before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}

        def guarded_write(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(directory), "Git directory write")
            return write(path, *args, **kwargs)

        with patch("uaml.project_memory.write", side_effect=guarded_write):
            self.assertEqual(checkpoint(self.git, self.registry, "manual")["status"], "CHECKPOINT_SAVED")
        self.assertEqual(checkpoint_marker(self.git), self.repo / ".uaml/checkpoint-pending.json")
        self.assertFalse(checkpoint_marker(self.git).exists())
        self.assertEqual(before, {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()})

    def test_legacy_git_marker_is_still_detected_and_repaired(self):
        transaction = self.interrupted()
        marker = checkpoint_marker(self.git)
        legacy = self.git.directory() / "uaml-checkpoint-pending.json"
        if marker != legacy:
            marker.rename(legacy)
        self.assertEqual(checkpoint_marker(self.git), legacy)
        self.assertIn("CHECKPOINT_TRANSACTION_PENDING", {item["code"] for item in recover(self.git, self.registry)["diagnostics"]})
        plan = repair(self.git, self.registry, transaction)
        self.assertEqual(repair(self.git, self.registry, transaction, True, plan["plan_hash"])["status"], "REPAIRED")
        self.assertFalse(legacy.exists())
        self.assertEqual(checkpoint_marker(self.git), self.repo / ".uaml/checkpoint-pending.json")

    def test_repair_review_binds_the_marker_location(self):
        transaction = self.interrupted()
        plan = repair(self.git, self.registry, transaction)
        marker = checkpoint_marker(self.git)
        legacy = self.git.directory() / "uaml-checkpoint-pending.json"
        marker.rename(legacy)
        original = legacy.read_bytes()
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        self.assertEqual(legacy.read_bytes(), original)

    def test_markers_in_both_locations_require_inspection(self):
        transaction = self.interrupted()
        marker = self.repo / ".uaml/checkpoint-pending.json"
        legacy = self.git.directory() / "uaml-checkpoint-pending.json"
        raw = json_bytes({"schema_version": 1, "snapshot_id": transaction})
        marker.write_bytes(raw)
        legacy.write_bytes(raw)
        with self.assertRaises(UamlError) as error:
            checkpoint(self.git, self.registry, "retry")
        self.assertEqual(error.exception.code, "CHECKPOINT_MARKER_CONFLICT")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "CHECKPOINT_MARKER_CONFLICT")
        self.assertEqual(marker.read_bytes(), raw)
        self.assertEqual(legacy.read_bytes(), raw)

    @unittest.skipUnless(os.name == "nt", "Windows directory DACL")
    def test_checkpoint_and_repair_with_windows_git_directory_write_denied(self):
        directory = self.git.directory()
        self.assertTrue(directory.is_relative_to(self.base))
        saved_acl = self.base / "git-acl.txt"
        backend = WindowsAcl()
        permissions_before = backend.snapshot(directory)
        files_before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        subprocess.run(["icacls", str(directory), "/save", str(saved_acl)], capture_output=True, check=True)
        try:
            subprocess.run(["icacls", str(directory), "/deny", f"*{backend.current_sid}:(OI)(CI)(WD,AD,WEA,WA,DE,DC)"],
                           capture_output=True, check=True)
            with self.assertRaises(PermissionError):
                (directory / "write-probe").write_bytes(b"should be denied")
            self.assertEqual(checkpoint(self.git, self.registry, "manual")["status"], "CHECKPOINT_SAVED")
            transaction = self.interrupted()
            plan = repair(self.git, self.registry, transaction)
            self.assertEqual(repair(self.git, self.registry, transaction, True, plan["plan_hash"])["status"], "REPAIRED")
            self.assertEqual(recover(self.git, self.registry)["status"], "RECOVERED")
        finally:
            restore_dacl(directory, saved_acl, backend)
        self.assertEqual(backend.snapshot(directory), permissions_before)
        self.assertEqual(files_before, {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()})
