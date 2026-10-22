import shutil
from unittest.mock import patch
from uuid import uuid4

from uaml import registry
from uaml.binding import load_project, resolve, trust
from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown, parse_yaml, yaml_bytes
from uaml.git_state import Git
from uaml.project_memory import init_project
from uaml.recovery import recover

from .support import Workspace


class BindingTests(Workspace):
    def test_end_to_end_and_readonly_resolution(self):
        self.bind()
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        result = resolve(self.git, self.registry)
        self.assertEqual(result["status"], "RESOLVED")
        recovered = recover(self.git, self.registry)
        self.assertEqual(recovered["status"], "RECOVERED")
        self.assertTrue(all(s["checkpoint_verified"] for s in recovered["sources"]))
        after = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_unapproved_checkout_never_reads_vault(self):
        self.bind(approve=False)
        with patch("uaml.binding.verify_vault", side_effect=AssertionError("private Vault read")):
            result = resolve(self.git, self.registry)
        self.assertEqual(result["status"], "CHECKOUT_UNTRUSTED")
        report = recover(self.git, self.registry)
        self.assertEqual(len(report["sources"]), 2)  # Repo memory still available.
        self.assertEqual(report["status"], "DEGRADED")

    def test_copied_fork_requires_new_grant(self):
        self.bind()
        copied = self.base / "fork"
        shutil.copytree(self.repo, copied)
        self.assertEqual(resolve(Git(copied), self.registry)["status"], "CHECKOUT_UNTRUSTED")

    def test_changed_remote_invalidates_grant_without_exposing_url(self):
        self.bind()
        self.git_cmd("remote", "add", "origin", "https://user:secret@example.invalid/project")
        result = resolve(self.git, self.registry)
        self.assertEqual(result["status"], "CHECKOUT_UNTRUSTED")
        self.assertNotIn("secret", str(result))

    def test_changed_binding_requires_review(self):
        self.bind()
        file = self.repo / ".uaml/project.yaml"
        value = parse_yaml(file.read_text(encoding="utf-8"))
        value["binding"]["project_memory_id"] = str(uuid4())
        file.write_bytes(yaml_bytes(value))
        self.assertEqual(resolve(self.git, self.registry)["status"], "CHECKOUT_UNTRUSTED")

    def test_missing_vault_is_not_created(self):
        self.bind()
        original = self.vault
        self.vault.rename(self.base / "moved")
        self.assertEqual(resolve(self.git, self.registry)["status"], "VAULT_MISSING")
        self.assertFalse(original.exists())

    def test_relocation_preserves_portable_manifest(self):
        self.bind()
        old_manifest = (self.repo / ".uaml/project.yaml").read_bytes()
        moved = self.base / "moved vault"
        self.vault.rename(moved)
        registry.register(self.registry, moved, select=True, expected_id=self.vault_id)
        self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")
        self.assertEqual(old_manifest, (self.repo / ".uaml/project.yaml").read_bytes())

    def test_duplicate_registration_and_multiple_copies(self):
        self.bind()
        registry.register(self.registry, self.vault)
        value = registry.load(self.registry)
        self.assertEqual(len(value["vaults"][0]["candidates"]), 1)
        copied = self.base / "copy"
        shutil.copytree(self.vault, copied)
        registry.register(self.registry, copied)
        self.assertEqual(resolve(self.git, self.registry)["status"], "MULTIPLE_CANDIDATES")
        registry.register(self.registry, copied, select=True)
        self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")

    def test_wrong_vault_id_relocation_preserves_registry(self):
        self.bind()
        before = self.registry.read_bytes()
        with self.assertRaises(UamlError):
            registry.register(self.registry, self.vault, expected_id=str(uuid4()), select=True)
        self.assertEqual(before, self.registry.read_bytes())

    def test_reverse_link_mismatch_and_missing(self):
        self.bind()
        file = next((self.vault / "UAML/Projects").glob("*/PROJECT.md"))
        header, body = frontmatter(file.read_bytes())
        header["project_id"] = str(uuid4())
        file.write_bytes(markdown(header, body))
        self.assertEqual(resolve(self.git, self.registry)["status"], "PROJECT_LINK_MISMATCH")
        file.unlink()
        self.assertEqual(resolve(self.git, self.registry)["status"], "PROJECT_LINK_MISSING")

    def test_missing_and_corrupt_registry(self):
        self.bind()
        self.registry.unlink()
        self.assertEqual(resolve(self.git, self.registry)["status"], "REGISTRY_MISSING")
        self.registry.write_text("{}", encoding="utf-8")
        self.assertEqual(resolve(self.git, self.registry)["status"], "SCHEMA_INVALID")

    def test_access_denied_is_not_treated_as_empty(self):
        self.bind()
        with patch("uaml.binding.verify_vault", side_effect=UamlError("READ_DENIED", "Denied by fixture")):
            self.assertEqual(resolve(self.git, self.registry)["status"], "READ_DENIED")

    def test_invalid_utf8_vault_degrades_without_hiding_repo_memory(self):
        self.bind()
        (self.vault / ".uaml/vault.yaml").write_bytes(b"\xff")
        result = recover(self.git, self.registry)
        self.assertEqual(result["binding"]["status"], "MEMORY_CORRUPT")
        self.assertEqual(len(result["sources"]), 2)

    def test_malformed_selected_candidate_is_a_diagnostic(self):
        import json
        self.bind()
        value = json.loads(self.registry.read_text(encoding="utf-8"))
        value["vaults"][0]["selected_candidate_id"] = {}
        self.registry.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(resolve(self.git, self.registry)["status"], "SCHEMA_INVALID")

    def test_init_never_overwrites_user_memory_or_agent_rules(self):
        for relative in ("AGENTS.md", "CLAUDE.md", "docs/memory/HANDOFF.md"):
            file = self.repo / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("user content", encoding="utf-8")
        with self.assertRaises(UamlError) as error:
            init_project(self.git, self.registry, self.vault_id, "Test")
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        for relative in ("AGENTS.md", "CLAUDE.md", "docs/memory/HANDOFF.md"):
            self.assertEqual((self.repo / relative).read_text(), "user content")
        self.assertFalse((self.repo / ".uaml/project.yaml").exists())

    def test_registry_inside_repository_rejected(self):
        with self.assertRaises(UamlError) as error:
            init_project(self.git, self.repo / "registry.json", self.vault_id, "Test")
        self.assertEqual(error.exception.code, "REGISTRY_IN_REPOSITORY")

    def test_register_cannot_put_private_registry_in_any_repo_or_vault(self):
        for target in (self.repo / "private.json", self.vault / "private.json"):
            with self.subTest(target=target), self.assertRaises(UamlError) as error:
                registry.register(target, self.vault)
            self.assertIn(error.exception.code, ("REGISTRY_IN_REPOSITORY", "REGISTRY_IN_VAULT"))
            self.assertFalse(target.exists())

    def test_invalid_schema_and_unsafe_paths_fail_before_vault_read(self):
        self.bind()
        manifest, _ = load_project(self.git)
        file = self.repo / ".uaml/project.yaml"
        manifest["schema_version"] = 99
        file.write_bytes(yaml_bytes(manifest))
        with self.assertRaises(UamlError) as error:
            resolve(self.git, self.registry)
        self.assertEqual(error.exception.code, "SCHEMA_UNSUPPORTED")
        manifest["schema_version"] = 1
        manifest["memory"]["handoff"] = ".git/config"
        file.write_bytes(yaml_bytes(manifest))
        with self.assertRaises(UamlError):
            resolve(self.git, self.registry)
