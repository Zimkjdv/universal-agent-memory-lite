import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from uaml import registry, replicas
from uaml.binding import resolve, trust
from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown, parse_yaml, yaml_bytes
from uaml.knowledge import add, get, search

from .support import Workspace
from .test_knowledge import KnowledgeWorkspace


class ReplicaTests(Workspace):
    def setUp(self):
        super().setUp()
        self.bind()
        self.copy = self.base / "Vault copy"
        shutil.copytree(self.vault, self.copy)
        registry.register(self.registry, self.copy, select=True)

    def change_copy_index(self):
        index = next((self.copy / "UAML/Projects").glob("*/PROJECT.md"))
        index.write_bytes(index.read_bytes() + b"\ncopy-specific history\n")
        return index

    def test_equivalent_copies_compare_readonly(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        report = replicas.compare(self.git, self.registry)
        self.assertEqual(report["status"], "REPLICA_EQUIVALENT")
        self.assertEqual(report["available_count"], 2)
        self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})

    def test_divergent_index_requires_reviewed_authority_not_register_select(self):
        self.change_copy_index()
        self.assertEqual(resolve(self.git, self.registry)["status"], "REPLICA_CONFLICT")
        registry.register(self.registry, self.vault, select=True)
        self.assertEqual(resolve(self.git, self.registry)["status"], "REPLICA_CONFLICT")
        report = replicas.compare(self.git, self.registry)
        before = {p: p.read_bytes() for root in (self.vault, self.copy) for p in root.rglob("*") if p.is_file()}
        replicas.select(self.git, self.registry, self.vault, report["comparison_hash"])
        resolved = resolve(self.git, self.registry)
        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertEqual(resolved["replicas"]["status"], "REPLICA_AUTHORITY_CONFIRMED")
        self.assertEqual(before, {p: p.read_bytes() for root in (self.vault, self.copy) for p in root.rglob("*") if p.is_file()})

    def test_stale_comparison_and_post_selection_edits_require_review(self):
        index = self.change_copy_index()
        report = replicas.compare(self.git, self.registry)
        index.write_bytes(index.read_bytes() + b"\nfurther edits\n")
        with self.assertRaises(UamlError) as error:
            replicas.select(self.git, self.registry, self.vault, report["comparison_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        report = replicas.compare(self.git, self.registry)
        replicas.select(self.git, self.registry, self.vault, report["comparison_hash"])
        index.write_bytes(index.read_bytes() + b"\nanother edit\n")
        self.assertEqual(resolve(self.git, self.registry)["status"], "REPLICA_CONFLICT")

    def test_missing_old_copy_is_reported_without_creating_replacement(self):
        self.vault.rename(self.base / "offline-old-location")
        report = replicas.compare(self.git, self.registry)
        self.assertEqual(report["missing_count"], 1)
        self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")
        self.assertFalse(self.vault.exists())

    def test_wrong_identity_copy_is_unverified_and_not_read_as_project_memory(self):
        metadata = self.copy / ".uaml/vault.yaml"
        value = parse_yaml(metadata.read_text(encoding="utf-8"))
        value["vault"]["id"] = str(uuid4())
        metadata.write_bytes(yaml_bytes(value))
        registry.register(self.registry, self.vault, select=True)
        original_link_path = replicas.link_path

        def safe_link(path, *args):
            self.assertNotEqual(path, self.copy)
            return original_link_path(path, *args)

        with patch("uaml.replicas.link_path", side_effect=safe_link):
            report = replicas.compare(self.git, self.registry)
        self.assertEqual(report["status"], "REPLICA_UNVERIFIED")
        self.assertEqual(resolve(self.git, self.registry)["status"], "REPLICA_UNVERIFIED")

    def test_changed_layout_is_not_a_new_read_grant(self):
        metadata = self.copy / ".uaml/vault.yaml"
        value = parse_yaml(metadata.read_text(encoding="utf-8"))
        value["layout"]["knowledge"] = "Private"
        metadata.write_bytes(yaml_bytes(value))
        registry.register(self.registry, self.vault, select=True)
        report = replicas.compare(self.git, self.registry)
        self.assertEqual(report["status"], "REPLICA_UNVERIFIED")
        self.assertIn("REPLICA_IDENTITY_CHANGED", {d["code"] for d in report["diagnostics"]})

    def test_no_grant_means_no_replica_content_comparison(self):
        value = json.loads(self.registry.read_text(encoding="utf-8"))
        value["checkout_grants"] = []
        self.registry.write_text(json.dumps(value), encoding="utf-8")
        with patch("uaml.replicas.collect", side_effect=AssertionError("unapproved read")), self.assertRaises(UamlError) as error:
            replicas.compare(self.git, self.registry)
        self.assertEqual(error.exception.code, "CHECKOUT_UNTRUSTED")

    def test_missing_reverse_index_cannot_be_selected_as_authority(self):
        next((self.copy / "UAML/Projects").glob("*/PROJECT.md")).unlink()
        registry.register(self.registry, self.vault, select=True)
        report = replicas.compare(self.git, self.registry)
        self.assertEqual(report["status"], "REPLICA_CONFLICT")
        with self.assertRaises(UamlError) as error:
            replicas.select(self.git, self.registry, self.copy, report["comparison_hash"])
        self.assertEqual(error.exception.code, "PROJECT_LINK_MISSING")

    def test_unreadable_copy_is_not_treated_as_empty_or_missing(self):
        registry.register(self.registry, self.vault, select=True)
        original = registry.read_vault

        def denied(path):
            if path == self.copy:
                raise UamlError("READ_DENIED", "fixture denial")
            return original(path)

        with patch("uaml.replicas.registry.read_vault", side_effect=denied):
            report = replicas.compare(self.git, self.registry)
            self.assertEqual(report["status"], "REPLICA_UNVERIFIED")
            with self.assertRaises(UamlError):
                replicas.select(self.git, self.registry, self.vault, report["comparison_hash"])

    def test_cli_compare_conflict_and_select(self):
        self.change_copy_index()
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "vault"]
        compared = subprocess.run(command + ["compare"], capture_output=True)
        self.assertEqual(compared.returncode, 1)
        report = json.loads(compared.stdout.decode("utf-8"))
        selected = subprocess.run(command + ["select", str(self.vault), "--expect-comparison", report["comparison_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(selected.stdout.decode("utf-8"))["status"], "REPLICA_SELECTED")


class KnowledgeReplicaTests(KnowledgeWorkspace):
    def setUp(self):
        super().setUp()
        header, body = self.note()
        self.note_id = header["id"]
        add(self.git, self.registry, self.source(header, body))
        self.copy = self.base / "knowledge-copy"
        shutil.copytree(self.vault, self.copy)
        registry.register(self.registry, self.copy, select=True)

    def modify_copy(self):
        file = self.copy / "UAML/Knowledge" / f"{self.note_id}.md"
        header, body = frontmatter(file.read_bytes())
        file.write_bytes(markdown(header, body + "\ncopy variant\n"))

    def test_knowledge_conflicts_are_checked_on_explicit_operations_not_resolve(self):
        self.modify_copy()
        with patch("uaml.knowledge.scan", side_effect=AssertionError("resolve must not scan knowledge")):
            self.assertEqual(resolve(self.git, self.registry)["status"], "RESOLVED")
        with self.assertRaises(UamlError) as error:
            search(self.git, self.registry, "Python")
        self.assertEqual(error.exception.code, "REPLICA_CONFLICT")
        report = replicas.compare(self.git, self.registry, True)
        self.assertTrue(report["knowledge_diverged"])
        replicas.select(self.git, self.registry, self.vault, report["comparison_hash"], True)
        self.assertNotIn("copy variant", get(self.git, self.registry, self.note_id)["untrusted_markdown"])

    def test_new_knowledge_change_invalidates_authority_acknowledgment(self):
        self.modify_copy()
        report = replicas.compare(self.git, self.registry, True)
        replicas.select(self.git, self.registry, self.vault, report["comparison_hash"], True)
        self.modify_copy()
        with self.assertRaises(UamlError) as error:
            get(self.git, self.registry, self.note_id)
        self.assertEqual(error.exception.code, "REPLICA_CONFLICT")

    def test_project_only_selection_never_acknowledges_knowledge_divergence(self):
        self.modify_copy()
        report = replicas.compare(self.git, self.registry)
        replicas.select(self.git, self.registry, self.vault, report["comparison_hash"])
        with self.assertRaises(UamlError) as error:
            search(self.git, self.registry, "Python")
        self.assertEqual(error.exception.code, "REPLICA_CONFLICT")

    def test_knowledge_compare_requires_its_own_grant(self):
        trust(self.git, self.registry)
        with self.assertRaises(UamlError) as error:
            replicas.compare(self.git, self.registry, True)
        self.assertEqual(error.exception.code, "KNOWLEDGE_ACCESS_DENIED")
