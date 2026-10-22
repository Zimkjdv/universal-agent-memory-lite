import json
import shutil
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from uaml import forking, registry
from uaml.binding import load_project, resolve, trust
from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown
from uaml.git_state import Git
from uaml.project_memory import checkpoint, init_vault
from uaml.storage import write
from uaml.validation import validate

from .support import Workspace


class ForkTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()
        self.original = load_project(self.git)[0]
        self.target = self.base / "fork-vault"
        self.target.mkdir()
        self.target_id = init_vault(self.target, "Fork Vault")["vault_id"]
        registry.register(self.registry, self.target)

    def prepare(self, git=None):
        return forking.prepare(git or self.git, self.registry, "Independent Project", self.target_id)

    def test_new_identity_blank_handoff_and_explicit_reapproval(self):
        trust(self.git, self.registry, "write")
        handoff = self.repo / "docs/memory/HANDOFF.md"
        header, body = frontmatter(handoff.read_bytes())
        handoff.write_bytes(markdown(header, body + "\nOriginal private task.\n"))
        checkpoint(self.git, self.registry, "original")
        plan = self.prepare()
        self.assertNotEqual(plan["project"]["id"], self.original["project"]["id"])
        self.assertNotEqual(plan["binding"]["project_memory_id"], self.original["binding"]["project_memory_id"])
        result = forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(result["status"], "FORK_APPLIED")
        self.assertNotIn("Original private task", handoff.read_text(encoding="utf-8"))
        self.assertEqual(resolve(self.git, self.registry)["status"], "CHECKOUT_UNTRUSTED")
        trust(self.git, self.registry)
        self.assertEqual(resolve(self.git, self.registry)["access"]["knowledge_access"], "none")
        self.assertEqual(validate(self.git, self.registry)["status"], "VALIDATED")

    def test_preview_changes_neither_repo_nor_target_vault(self):
        before = {p: p.read_bytes() for root in (self.repo, self.vault, self.target) for p in root.rglob("*") if p.is_file()}
        self.prepare()
        after = {p: p.read_bytes() for root in (self.repo, self.vault, self.target) for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_source_vault_is_never_read_and_may_be_offline(self):
        self.vault.rename(self.base / "source-vault-offline")
        original_read = registry.read_vault

        def read_target_only(path):
            self.assertEqual(path, self.target)
            return original_read(path)

        with patch("uaml.forking.registry.read_vault", side_effect=read_target_only):
            plan = self.prepare()
            forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertFalse(self.vault.exists())

    def test_copied_repo_does_not_modify_original_repo_or_index(self):
        before = {p: p.read_bytes() for root in (self.repo, self.vault) for p in root.rglob("*") if p.is_file()}
        copied = self.base / "forked-copy"
        shutil.copytree(self.repo, copied)
        git = Git(copied)
        plan = self.prepare(git)
        forking.apply(git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(before, {p: p.read_bytes() for root in (self.repo, self.vault) for p in root.rglob("*") if p.is_file()})
        self.assertNotEqual(load_project(git)[0]["project"]["id"], self.original["project"]["id"])

    def test_dirty_code_index_and_agent_rules_are_preserved(self):
        for name, content in (("app.py", "staged"), ("AGENTS.md", "custom rules"), ("CLAUDE.md", "other rules")):
            (self.repo / name).write_text(content, encoding="utf-8")
        self.git_cmd("add", "app.py")
        (self.repo / "app.py").write_text("unstaged", encoding="utf-8")
        before = {name: (self.repo / name).read_bytes() for name in ("app.py", "AGENTS.md", "CLAUDE.md")}
        index = self.git_cmd("show", ":app.py")
        plan = self.prepare()
        forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(index, self.git_cmd("show", ":app.py"))
        self.assertEqual(before, {name: (self.repo / name).read_bytes() for name in before})

    def test_manual_memory_change_after_review_prevents_any_apply(self):
        plan = self.prepare()
        handoff = self.repo / "docs/memory/HANDOFF.md"
        handoff.write_bytes(handoff.read_bytes() + b"\nnew manual progress\n")
        before = {p: p.read_bytes() for root in (self.repo, self.target) for p in root.rglob("*") if p.is_file()}
        with self.assertRaises(UamlError) as error:
            forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(error.exception.code, "FORK_CONFLICT")
        self.assertEqual(before, {p: p.read_bytes() for root in (self.repo, self.target) for p in root.rglob("*") if p.is_file()})

    def test_wrong_plan_and_payload_tampering_are_rejected(self):
        plan = self.prepare()
        with self.assertRaises(UamlError):
            forking.apply(self.git, self.registry, plan["fork_id"], "wrong")
        payload = self.registry.parent / "forks" / f"{plan['fork_id']}.0.after"
        payload.write_bytes(payload.read_bytes() + b"tampered")
        with self.assertRaises(UamlError) as error:
            forking.inspect(self.git, self.registry, plan["fork_id"])
        self.assertEqual(error.exception.code, "FORK_CONFLICT")

    def test_unknown_target_is_not_created_or_inferred(self):
        with self.assertRaises(UamlError) as error:
            forking.prepare(self.git, self.registry, "Fork", str(uuid4()))
        self.assertEqual(error.exception.code, "VAULT_UNREGISTERED")

    def test_remote_change_invalidates_fork_plan(self):
        plan = self.prepare()
        self.git_cmd("remote", "add", "origin", "https://example.invalid/new.git")
        with self.assertRaises(UamlError) as error:
            forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(error.exception.code, "FORK_CONFLICT")

    def test_partial_fork_can_resume_without_overwriting_manual_work(self):
        plan = self.prepare()

        def interrupt(path, *args, **kwargs):
            if path.name == "HANDOFF.md":
                raise OSError("interruption")
            return write(path, *args, **kwargs)

        with patch("uaml.forking.write", side_effect=interrupt), self.assertRaises(OSError):
            forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(load_project(self.git)[0]["project"]["id"], self.original["project"]["id"])
        result = forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])
        self.assertEqual(result["status"], "FORK_APPLIED")
        trust(self.git, self.registry)
        self.assertEqual(validate(self.git, self.registry)["status"], "VALIDATED")
        self.assertEqual(forking.apply(self.git, self.registry, plan["fork_id"], plan["plan_hash"])["status"], "FORK_ALREADY_APPLIED")
        self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")

    def test_archive_contains_original_managed_memory(self):
        old = (self.repo / "docs/memory/HANDOFF.md").read_bytes()
        plan = self.prepare()
        archive = self.registry.parent / "forks" / f"{plan['fork_id']}.1.before"
        self.assertEqual(archive.read_bytes(), old)

    def test_cli_preview_apply_and_explicit_target_requirement(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "project", "fork"]
        missing = subprocess.run(command + ["--name", "Fork"], capture_output=True)
        self.assertEqual(missing.returncode, 1)
        preview = subprocess.run(command + ["--name", "Fork", "--vault", self.target_id], capture_output=True, check=True)
        plan = json.loads(preview.stdout.decode("utf-8"))
        applied = subprocess.run(command + ["--proposal", plan["fork_id"], "--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout.decode("utf-8"))["status"], "FORK_APPLIED")
