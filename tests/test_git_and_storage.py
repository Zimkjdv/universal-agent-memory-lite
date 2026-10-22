import json
import os
import subprocess
import sys
from pathlib import Path

from uaml.errors import UamlError
from uaml.formats import digest
from uaml.git_state import Git
from uaml.storage import lock, write

from .support import Workspace


class GitTests(Workspace):
    def test_subdirectory_and_worktree_root(self):
        folder = self.repo / "nested"
        folder.mkdir()
        self.assertEqual(Git(folder).root, self.repo.resolve())
        worktree = self.base / "other worktree"
        self.git_cmd("worktree", "add", "-b", "other", str(worktree))
        self.assertEqual(Git(worktree).root, worktree.resolve())
        self.assertTrue((worktree / ".git").is_file())

    def test_unborn_and_detached_head(self):
        empty = self.base / "unborn"
        empty.mkdir()
        self.git_cmd("init", "-b", "main", cwd=empty)
        state = Git(empty).observe()["snapshot"]
        self.assertIsNone(state["head"])
        self.assertEqual(state["branch"], "main")
        self.git_cmd("checkout", "--detach")
        self.assertIsNone(self.git.observe()["snapshot"]["branch"])

    def test_staged_rename_keeps_both_paths(self):
        self.git_cmd("mv", "app.py", "renamed.py")
        changes = self.git.observe()["changes"]
        self.assertEqual(changes[0]["path"], "renamed.py")
        self.assertEqual(changes[0]["original_path"], "app.py")

    def test_environment_files_are_not_fingerprinted(self):
        (self.repo / ".env").write_text("PRIVATE=value")
        result = self.git.observe()
        self.assertIsNone(result["snapshot"]["working_tree_fingerprint"])
        self.assertIsNotNone(result["fingerprint_warning"])
        self.assertNotIn("PRIVATE=value", str(result))


class StorageTests(Workspace):
    def test_conflicting_write_keeps_user_content(self):
        target = self.base / "note.md"
        write(target, b"first", None)
        target.write_bytes(b"manual edit")
        with self.assertRaises(UamlError) as error:
            write(target, b"replacement", digest(b"first"))
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        self.assertEqual(target.read_bytes(), b"manual edit")
        with self.assertRaises(UamlError):
            write(target, b"create again", None)

    def test_rewrite_has_original_backup(self):
        target = self.base / "note.md"
        backups = self.base / "backups"
        write(target, b"first", None)
        write(target, b"second", digest(b"first"), backups)
        self.assertEqual(target.read_bytes(), b"second")
        self.assertEqual([p.read_bytes() for p in backups.iterdir()], [b"first"])

    def test_live_process_lock_is_not_stolen(self):
        path = self.base / "writer.lock"
        code = "import sys,time; from pathlib import Path; from uaml.storage import lock;\nwith lock(Path(sys.argv[1])):\n print('locked', flush=True)\n time.sleep(30)\n"
        process = subprocess.Popen([sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b"locked")
            payload = path.read_bytes()
            with self.assertRaises(UamlError) as error:
                with lock(path):
                    self.fail("stole the lock")
            self.assertEqual(error.exception.code, "WRITE_CONFLICT")
            self.assertEqual(payload, path.read_bytes())
        finally:
            process.terminate()
            process.communicate(timeout=5)

    def test_replaced_lock_is_not_removed(self):
        path = self.base / "writer.lock"
        with lock(path):
            path.write_bytes(b"different owner")
        self.assertEqual(path.read_bytes(), b"different owner")


class CliTests(Workspace):
    def cli(self, *args):
        process = subprocess.run([sys.executable, "-m", "uaml", "--json", "--repo", str(self.repo),
                                  "--registry", str(self.registry), *args], capture_output=True)
        return process, json.loads(process.stdout.decode("utf-8"))

    def test_json_success_and_error_exit_codes(self):
        self.bind()
        process, result = self.cli("recover")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(result["status"], "RECOVERED")
        self.registry.unlink()
        process, result = self.cli("resolve")
        self.assertEqual(process.returncode, 1)
        self.assertEqual(result["status"], "REGISTRY_MISSING")

    def test_actual_cli_init_register_trust_save_recover(self):
        process, result = self.cli("project", "init", "--vault", self.vault_id, "--name", "CLI 專案")
        self.assertEqual(process.returncode, 0, result)
        process, result = self.cli("project", "trust")
        self.assertEqual(process.returncode, 0, result)
        process, result = self.cli("checkpoint", "--agent", "claude-code")
        self.assertEqual(process.returncode, 0, result)
        process, result = self.cli("recover")
        self.assertEqual(process.returncode, 0, result)
        self.assertEqual(result["sources"][0]["metadata"]["source_agent"], "claude-code")

    def test_cli_missing_vault_register_does_not_create_directory(self):
        absent = self.base / "absent"
        process, result = self.cli("vault", "register", str(absent))
        self.assertEqual(process.returncode, 1)
        self.assertEqual(result["status"], "VAULT_MISSING")
        self.assertFalse(absent.exists())
