import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uaml import permissions, private_storage, registry
from uaml.errors import UamlError
from uaml.formats import digest
from uaml.project_memory import checkpoint
from uaml.storage import write

from .support import Workspace


class PrivateHomeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="uaml-private-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.path = self.base / "new private 資料" / "registry.json"

    def test_initialize_new_home_and_registry_without_git_or_vault(self):
        result = registry.initialize(self.path)
        self.assertEqual(result["status"], "REGISTRY_INITIALIZED")
        self.assertEqual(registry.load(self.path), registry.empty())
        self.assertEqual(permissions.audit(self.path)["status"], "PERMISSIONS_RESTRICTED")

    def test_existing_directory_is_preserved_and_explicit_init_refused(self):
        self.path.parent.mkdir()
        original = self.path.parent.stat()
        sentinel = self.path.parent / "keep.txt"
        sentinel.write_bytes(b"user content")
        with self.assertRaises(UamlError) as caught:
            registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "PRIVATE_HOME_EXISTS")
        self.assertEqual(private_storage.ensure_home(self.path), [])
        self.assertEqual(self.path.parent.stat().st_mode, original.st_mode)
        self.assertEqual(sentinel.read_bytes(), b"user content")
        self.assertFalse(self.path.exists())

    def test_repeated_init_never_overwrites_registry(self):
        registry.initialize(self.path)
        original = self.path.read_bytes()
        with self.assertRaises(UamlError):
            registry.initialize(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_registry_file_appearing_after_home_creation_is_not_overwritten(self):
        original_lock = registry.lock
        content = b"concurrent user data"
        def racing_lock(path):
            self.path.write_bytes(content)
            return original_lock(path)
        with patch("uaml.registry.lock", side_effect=racing_lock):
            with self.assertRaises(UamlError) as caught:
                registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")
        self.assertEqual(self.path.read_bytes(), content)

    def test_missing_ancestors_are_created_privately_existing_parent_is_kept(self):
        original = self.base.stat().st_mode
        nested = self.base / "new parent" / "new child" / "registry.json"
        result = registry.initialize(nested)
        self.assertEqual(len(result["created_directories"]), 2)
        self.assertEqual(self.base.stat().st_mode, original)
        inspector = permissions.WindowsAcl().inspect if os.name == "nt" else permissions.posix_inspect
        for path in result["created_directories"]:
            self.assertEqual(inspector(Path(path))["state"], "RESTRICTED")

    def test_permission_failure_blocks_registry_payload(self):
        backend = "uaml.private_storage.WindowsPrivateDirectory" if os.name == "nt" else "uaml.private_storage.posix_inspect"
        with patch(backend, side_effect=PermissionError("fixture")):
            with self.assertRaises(UamlError) as caught:
                registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "PRIVATE_HOME_UNAVAILABLE")
        self.assertFalse(self.path.exists())

    def test_unverified_new_directory_blocks_payload(self):
        backend = "uaml.private_storage.WindowsPrivateDirectory.inspect" if os.name == "nt" else "uaml.private_storage.posix_inspect"
        with patch(backend, return_value={"state": "UNVERIFIED", "issues": []}):
            with self.assertRaises(UamlError) as caught:
                registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "PRIVATE_HOME_UNVERIFIED")
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_directory_creation_race_is_not_adopted(self):
        def racing_create(directory):
            directory.mkdir()
            raise FileExistsError("competing writer")
        if os.name == "nt":
            target = "uaml.private_storage.WindowsPrivateDirectory.create"
            side_effect = racing_create
        else:
            target = "pathlib.Path.mkdir"
            original = Path.mkdir
            def side_effect(directory, **kwargs):
                original(directory)
                raise FileExistsError("competing writer")
        with patch(target, autospec=True, side_effect=(lambda _, directory: racing_create(directory)) if os.name == "nt" else side_effect):
            with self.assertRaises(UamlError) as caught:
                registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "WRITE_CONFLICT")
        self.assertFalse(self.path.exists())

    def test_repository_private_home_refused(self):
        (self.base / ".git").mkdir()
        with self.assertRaises(UamlError) as caught:
            registry.initialize(self.path)
        self.assertEqual(caught.exception.code, "REGISTRY_IN_REPOSITORY")
        self.assertFalse(self.path.parent.exists())

    def test_cli_init_is_explicit_and_successful(self):
        result = subprocess.run([sys.executable, "-m", "uaml", "--registry", str(self.path), "--json", "registry", "init"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout.decode())
        self.assertEqual(json.loads(result.stdout)["status"], "REGISTRY_INITIALIZED")

    def test_windows_native_new_home_does_not_inherit_everyone(self):
        if os.name != "nt":
            self.skipTest("Windows native DACL inheritance")
        granted = subprocess.run(["icacls", str(self.base), "/grant", "*S-1-1-0:(OI)(CI)R"], capture_output=True)
        self.assertEqual(granted.returncode, 0)
        backend = permissions.WindowsAcl()
        parent_before = backend.snapshot(self.base)
        self.assertEqual(backend.inspect(self.base)["state"], "RISK")
        registry.initialize(self.path)
        artifact = self.path.parent / "backups" / "fixture.bak"
        artifact.parent.mkdir()
        artifact.write_bytes(b"synthetic private bytes")
        for path in (self.path.parent, self.path, artifact.parent, artifact):
            self.assertEqual(backend.inspect(path)["state"], "RESTRICTED")
        self.assertEqual(backend.snapshot(self.base), parent_before)

    def test_posix_new_home_has_owner_only_mode(self):
        if os.name == "nt":
            self.skipTest("POSIX directory mode")
        registry.initialize(self.path)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)


class PrivateCheckpointTests(Workspace):
    def test_checkpoint_without_local_registry_creates_protected_journal_home(self):
        self.bind()
        missing = self.base / "relocated private home" / "registry.json"
        result = checkpoint(self.git, missing, "manual")
        self.assertEqual(result["status"], "CHECKPOINT_SAVED")
        self.assertFalse(missing.exists())  # no replacement Registry or Vault invented
        inspector = permissions.WindowsAcl().inspect if os.name == "nt" else permissions.posix_inspect
        self.assertEqual(inspector(missing.parent)["state"], "RESTRICTED")
        self.assertTrue(list((missing.parent / "transactions").iterdir()))

    def test_checkpoint_artifacts_are_private_under_an_existing_shared_home(self):
        self.bind()
        shared = self.base / "legacy shared home"
        shared.mkdir()
        if os.name == "nt":
            subprocess.run(["icacls", str(shared), "/grant", "*S-1-1-0:(OI)(CI)R"], capture_output=True, check=True)
            inspector = permissions.WindowsAcl().inspect
        else:
            shared.chmod(0o755)
            inspector = permissions.posix_inspect
        self.assertEqual(inspector(shared)["state"], "RISK")
        result = checkpoint(self.git, shared / "registry.json", "manual")
        self.assertEqual(result["status"], "CHECKPOINT_SAVED")
        self.assertEqual(inspector(shared)["state"], "RISK")
        for name in ("transactions", "backups"):
            directory = shared / name
            self.assertEqual(inspector(directory)["state"], "RESTRICTED")
            self.assertTrue(list(directory.iterdir()))
            for artifact in directory.iterdir():
                self.assertEqual(inspector(artifact)["state"], "RESTRICTED")

    def test_unsafe_existing_backup_folder_blocks_checkpoint_before_journal_or_memory_writes(self):
        self.bind()
        backups = self.registry.parent / "backups"
        if os.name == "nt":
            subprocess.run(["icacls", str(backups), "/grant", "*S-1-1-0:(OI)(CI)R"], capture_output=True, check=True)
        else:
            backups.chmod(0o777)
        original = {path: path.read_bytes() for directory in (backups, self.registry.parent / "transactions",
                    self.repo / "docs/memory") for path in directory.iterdir()}
        with self.assertRaises(UamlError) as caught:
            checkpoint(self.git, self.registry, "manual")
        self.assertEqual(caught.exception.code, "PRIVATE_ARTIFACT_UNSAFE")
        self.assertEqual(original, {path: path.read_bytes() for path in original})
        self.assertEqual(set((self.registry.parent / "transactions").iterdir()),
                         {path for path in original if path.parent.name == "transactions"})

    def test_private_staging_permission_failure_keeps_existing_target(self):
        target = self.base / "target.md"
        target.write_bytes(b"original")
        with patch("uaml.storage.verify_private_permissions", side_effect=UamlError("PRIVATE_ARTIFACT_UNSAFE", "fixture")):
            with self.assertRaises(UamlError) as caught:
                write(target, b"replacement", digest(b"original"), self.base / "private backups")
        self.assertEqual(caught.exception.code, "PRIVATE_ARTIFACT_UNSAFE")
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(list((self.base / "private backups").iterdir()), [])

    @unittest.skipIf(os.name == "nt", "legacy Unix artifact modes")
    def test_legacy_readable_artifact_directory_is_usable_inside_private_home(self):
        self.bind()
        for name in ("transactions", "backups"):
            (self.registry.parent / name).chmod(0o755)
        self.assertEqual(checkpoint(self.git, self.registry, "manual")["status"], "CHECKPOINT_SAVED")
        for name in ("transactions", "backups"):
            self.assertEqual(stat.S_IMODE((self.registry.parent / name).stat().st_mode), 0o755)
