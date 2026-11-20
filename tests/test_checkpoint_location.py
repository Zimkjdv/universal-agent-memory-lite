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


def save_dacls(directory, backend):
    """Capture owner/DACL SDDL for every object in this disposable fixture."""
    from ctypes import wintypes as w

    c = backend.c
    convert = backend.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p]
    convert.restype = w.BOOL
    saved = {}
    for path in (directory, *directory.rglob("*")):
        descriptor, text = c.c_void_p(), c.c_void_p()
        code = backend.adv.GetNamedSecurityInfoW(str(path), 1, 5, None, None, None, None, c.byref(descriptor))
        if code:
            raise OSError(code, "Cannot capture the fixture's original permissions.")
        try:
            if not convert(descriptor, 1, 5, c.byref(text), None):
                raise c.WinError(c.get_last_error())
            saved[path] = c.wstring_at(text)
        finally:
            backend.kernel.LocalFree(text)
            backend.kernel.LocalFree(descriptor)
    return saved


def restore_dacls(saved, backend):
    """Restore each saved DACL without triggering automatic child inheritance."""
    from ctypes import wintypes as w

    c = backend.c
    convert = backend.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes, convert.restype = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p], w.BOOL
    # This low-level fixture-only API applies the saved descriptor directly.
    # SetNamedSecurityInfo recomputes inheritance on hosted Windows runners.
    set_file = backend.adv.SetFileSecurityW
    set_file.argtypes, set_file.restype = [w.LPCWSTR, w.DWORD, c.c_void_p], w.BOOL
    for path, sddl in saved.items():
        descriptor = c.c_void_p()
        if not convert(sddl, 1, c.byref(descriptor), None):
            raise c.WinError(c.get_last_error())
        try:
            if not set_file(str(path), 4, descriptor):  # DACL only; retain owner.
                raise c.WinError(c.get_last_error())
        finally:
            backend.kernel.LocalFree(descriptor)


class CheckpointLocationTests(Workspace):
    maxDiff = None

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

    @unittest.skipUnless(os.name == "nt", "Windows legacy DACL restoration")
    def test_restore_preserves_legacy_explicit_dacl_without_inherited_duplicates(self):
        from ctypes import wintypes as w

        directory = self.base / "legacy-acl"
        directory.mkdir()
        backend = WindowsAcl()
        c = backend.c
        descriptor = c.c_void_p()
        convert = backend.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes, convert.restype = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p], w.BOOL
        set_file = backend.adv.SetFileSecurityW
        set_file.argtypes, set_file.restype = [w.LPCWSTR, w.DWORD, c.c_void_p], w.BOOL
        # Reproduce the legacy explicit ACL found on hosted Git directories.
        sddl = f"D:(A;OICI;FA;;;{backend.current_sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        self.assertTrue(convert(sddl, 1, c.byref(descriptor), None))
        try:
            self.assertTrue(set_file(str(directory), 4, descriptor), c.get_last_error())
        finally:
            backend.kernel.LocalFree(descriptor)
        (directory / "child").mkdir()
        (directory / "child" / "fixture.txt").write_text("fixture", encoding="utf-8")
        before = backend.snapshot(directory)
        saved = save_dacls(directory, backend)
        try:
            subprocess.run(["icacls", str(directory), "/deny",
                            f"*{backend.current_sid}:(OI)(CI)(WD,AD,WEA,WA,DE,DC)"],
                           capture_output=True, check=True)
        finally:
            restore_dacls(saved, backend)
        self.assertEqual(backend.snapshot(directory), before)
        self.assertEqual(save_dacls(directory, backend), saved)

    @unittest.skipUnless(os.name == "nt", "Windows directory DACL")
    def test_checkpoint_and_repair_with_windows_git_directory_write_denied(self):
        directory = self.git.directory()
        self.assertTrue(directory.is_relative_to(self.base))
        backend = WindowsAcl()
        permissions_before = backend.snapshot(directory)
        files_before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        saved = save_dacls(directory, backend)
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
            restore_dacls(saved, backend)
        self.assertEqual(backend.snapshot(directory), permissions_before)
        self.assertEqual(save_dacls(directory, backend), saved)
        self.assertEqual(files_before, {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()})
