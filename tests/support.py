import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from uaml import registry
from uaml.binding import trust
from uaml.git_state import Git
from uaml.project_memory import init_project, init_vault


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uaml-tests-")
        self.addCleanup(self.temp.cleanup)
        # Windows runners may expose TEMP through an 8.3 alias. Match the
        # canonical roots used by production Registry/Git path resolution.
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "專案 with spaces"
        self.repo.mkdir()
        self.git_cmd("init", "-b", "main")
        self.git_cmd("config", "user.name", "UAML Tests")
        self.git_cmd("config", "user.email", "tests@example.invalid")
        (self.repo / "app.py").write_text("print('initial')\n", encoding="utf-8")
        self.git_cmd("add", "app.py")
        self.git_cmd("commit", "-m", "initial")
        self.vault = self.base / "技術 Vault"
        self.vault.mkdir()
        self.registry = self.base / "private" / "registry.json"
        self.vault_id = init_vault(self.vault, "技術知識")["vault_id"]
        registry.register(self.registry, self.vault)
        self.git = Git(self.repo)

    def git_cmd(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout

    def bind(self, approve=True):
        self.initialized = init_project(self.git, self.registry, self.vault_id, "測試專案")
        if approve:
            trust(self.git, self.registry)
        return self.initialized
