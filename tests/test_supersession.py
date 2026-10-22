import json
import subprocess
import sys
from unittest.mock import patch

from uaml import knowledge, supersession
from uaml.binding import trust
from uaml.errors import UamlError
from uaml.formats import digest, frontmatter, json_bytes, markdown
from uaml.proposals import propose
from uaml.storage import lock, write
from uaml.validation import relations, validate

from .test_knowledge import KnowledgeWorkspace


class SupersessionTests(KnowledgeWorkspace):
    def setUp(self):
        super().setUp()
        self.old, self.old_body = self.note(version="3.11")
        self.new, self.new_body = self.note(version="3.12")
        for header, body in ((self.old, self.old_body), (self.new, self.new_body)):
            knowledge.add(self.git, self.registry, self.source(header, body))
        self.root = self.vault / "UAML/Knowledge"

    def prepare(self):
        return supersession.prepare(self.git, self.registry, self.old["id"], self.new["id"], "已驗證新版環境；舊版經驗保留供查詢。")

    def apply(self, plan):
        return supersession.apply(self.git, self.registry, plan["transaction_id"], plan["plan_hash"])

    def assert_code(self, code, call):
        with self.assertRaises(UamlError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def interrupt_second_note(self, plan):
        def interrupted(path, *args, **kwargs):
            if path.name == f"{self.new['id']}.md":
                raise OSError("fixture interruption")
            return write(path, *args, **kwargs)
        with patch("uaml.supersession.write", side_effect=interrupted), self.assertRaises(OSError):
            self.apply(plan)

    def test_prepare_leaves_vault_unchanged_and_shows_both_full_payloads(self):
        before = {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        plan = self.prepare()
        self.assertEqual(before, {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()})
        self.assertEqual(plan["status"], "SUPERSESSION_PREVIEW")
        self.assertEqual(len(plan["review_payloads"]), 2)
        self.assertIn("superseded_by", plan["untrusted_diff"])
        self.assertEqual(plan["applicability"]["replacement"], self.new["applicability"])

    def test_apply_preserves_bodies_evidence_and_provenance_and_links_both_notes(self):
        plan = self.prepare()
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_APPLIED")
        old = knowledge.get(self.git, self.registry, self.old["id"])
        new = knowledge.get(self.git, self.registry, self.new["id"])
        self.assertEqual(old["metadata"]["superseded_by"], self.new["id"])
        self.assertEqual(old["metadata"]["status"], "superseded")
        self.assertIn(self.old["id"], new["metadata"]["supersedes"])
        for note, original, body in ((old, self.old, self.old_body), (new, self.new, self.new_body)):
            self.assertEqual(note["untrusted_markdown"], body)
            self.assertEqual(note["metadata"]["revision"], 2)
            self.assertEqual(note["metadata"]["created_at"], original["created_at"])
            self.assertEqual(note["metadata"]["verification"], original["verification"])
        self.assertFalse((self.vault / ".uaml/knowledge-transaction.json").exists())
        self.assertTrue((self.vault / ".uaml/knowledge-revision.json").exists())
        self.assertEqual(relations(knowledge.scan(self.root)[0]), [])
        self.assertEqual(validate(self.git, self.registry, True)["status"], "VALIDATED")
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_ALREADY_APPLIED")
        results = knowledge.search(self.git, self.registry, "Python")
        self.assertEqual([n["id"] for n in results["results"]], [self.new["id"]])
        self.assertTrue(any((self.registry.parent / "backups").glob("*.bak")))

    def test_read_grant_can_prepare_but_cannot_apply(self):
        trust(self.git, self.registry, "read")
        plan = self.prepare()
        self.assert_code("KNOWLEDGE_ACCESS_DENIED", lambda: self.apply(plan))
        self.assertFalse((self.vault / ".uaml/knowledge-transaction.json").exists())

    def test_wrong_plan_and_changed_payload_are_rejected_before_any_vault_write(self):
        plan = self.prepare()
        before = {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        self.assert_code("WRITE_CONFLICT", lambda: supersession.apply(self.git, self.registry, plan["transaction_id"], "0" * 64))
        payload = self.registry.parent / "supersessions" / f"{plan['transaction_id']}.0.after"
        payload.write_bytes(payload.read_bytes() + b"\nmanual edit\n")
        self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))
        self.assertEqual(before, {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()})

    def test_manual_note_edit_is_not_overwritten(self):
        plan = self.prepare()
        target = self.root / f"{self.old['id']}.md"
        target.write_bytes(target.read_bytes() + b"\nuser work\n")
        before = target.read_bytes()
        self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.vault / ".uaml/knowledge-transaction.json").exists())

    def test_catalog_change_requires_new_review(self):
        plan = self.prepare()
        header, body = self.note(version="3.13")
        knowledge.add(self.git, self.registry, self.source(header, body))
        self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))

    def test_interrupted_transaction_blocks_readers_and_other_writers_then_resumes(self):
        plan = self.prepare()
        self.interrupt_second_note(plan)
        self.assert_code("KNOWLEDGE_TRANSACTION_PENDING", lambda: knowledge.get(self.git, self.registry, self.old["id"]))
        self.assert_code("KNOWLEDGE_TRANSACTION_PENDING", lambda: knowledge.search(self.git, self.registry, "Python"))
        header, body = self.note(version="3.13")
        self.assert_code("KNOWLEDGE_TRANSACTION_PENDING", lambda: knowledge.add(self.git, self.registry, self.source(header, body)))
        self.assertEqual(validate(self.git, self.registry, True)["status"], "VALIDATION_ISSUES")
        resumed = supersession.inspect(self.git, self.registry, plan["transaction_id"])[0]
        self.assertTrue(resumed["pending"])
        self.assertEqual([a["action"] for a in resumed["actions"]], ["keep", "finish"])
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_APPLIED")
        self.assertEqual(relations(knowledge.scan(self.root)[0]), [])

    def test_manual_edit_after_interruption_is_preserved_and_marker_remains(self):
        plan = self.prepare()
        self.interrupt_second_note(plan)
        file = self.root / f"{self.new['id']}.md"
        file.write_bytes(file.read_bytes() + b"\nmanual after crash\n")
        before = file.read_bytes()
        self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))
        self.assertEqual(file.read_bytes(), before)
        self.assertTrue((self.vault / ".uaml/knowledge-transaction.json").exists())

    def test_completion_marker_cleanup_failure_can_resume(self):
        plan = self.prepare()
        from pathlib import Path
        original = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path.name == "knowledge-transaction.json":
                raise OSError("fixture cleanup interruption")
            return original(path, *args, **kwargs)
        with patch("pathlib.Path.unlink", new=interrupted), self.assertRaises(OSError):
            self.apply(plan)
        self.assertTrue((self.vault / ".uaml/knowledge-transaction.json").exists())
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_APPLIED")

    def test_interruption_before_first_note_preserves_both_originals(self):
        plan = self.prepare()
        before = {p: p.read_bytes() for p in self.root.glob("*.md")}
        original = write
        def interrupted(path, *args, **kwargs):
            if path.name == f"{self.old['id']}.md":
                raise OSError("fixture first-note interruption")
            return original(path, *args, **kwargs)
        with patch("uaml.supersession.write", side_effect=interrupted), self.assertRaises(OSError):
            self.apply(plan)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.glob("*.md")})
        self.assertTrue((self.vault / ".uaml/knowledge-transaction.json").exists())
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_APPLIED")

    def test_receipt_write_failure_keeps_readers_blocked_until_resumed(self):
        plan = self.prepare()
        original = write
        def interrupted(path, *args, **kwargs):
            if path.name == "knowledge-revision.json":
                raise OSError("fixture receipt failure")
            return original(path, *args, **kwargs)
        with patch("uaml.supersession.write", side_effect=interrupted), self.assertRaises(OSError):
            self.apply(plan)
        self.assert_code("KNOWLEDGE_TRANSACTION_PENDING", lambda: knowledge.search(self.git, self.registry, "Python"))
        self.assertEqual(self.apply(plan)["status"], "SUPERSESSION_APPLIED")

    def test_another_prepared_transaction_cannot_replace_pending_marker(self):
        first, second = self.prepare(), self.prepare()
        self.interrupt_second_note(first)
        marker = self.vault / ".uaml/knowledge-transaction.json"
        before = marker.read_bytes()
        self.assert_code("KNOWLEDGE_TRANSACTION_PENDING", lambda: self.apply(second))
        self.assertEqual(marker.read_bytes(), before)
        self.assertEqual(self.apply(first)["status"], "SUPERSESSION_APPLIED")

    def test_forged_payload_cannot_modify_body_even_with_updated_plan_hash(self):
        plan = self.prepare()
        folder = self.registry.parent / "supersessions"
        payload = folder / f"{plan['transaction_id']}.1.after"
        payload.write_bytes(payload.read_bytes() + b"\nunauthorized body rewrite\n")
        file = folder / f"{plan['transaction_id']}.json"
        value = json.loads(file.read_bytes())
        value["entries"][1]["after_hash"] = digest(payload.read_bytes())
        raw = json_bytes(value)
        file.write_bytes(raw)
        before = {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        self.assert_code("SCHEMA_INVALID", lambda: supersession.apply(self.git, self.registry, plan["transaction_id"], digest(raw)))
        self.assertEqual(before, {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()})

    def test_completed_plan_never_overwrites_later_manual_edits(self):
        plan = self.prepare()
        self.apply(plan)
        file = self.root / f"{self.old['id']}.md"
        file.write_bytes(file.read_bytes() + b"\npost-completion history\n")
        before = file.read_bytes()
        self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))
        self.assertEqual(file.read_bytes(), before)

    def test_reader_rejects_transaction_completed_during_scan(self):
        plan = self.prepare()
        original = knowledge.scan
        triggered = False
        def interleaved(root):
            nonlocal triggered
            if not triggered:
                triggered = True
                notes = original(root)
                self.apply(plan)
                return notes
            return original(root)
        with patch("uaml.knowledge.scan", side_effect=interleaved):
            self.assert_code("WRITE_CONFLICT", lambda: knowledge.search(self.git, self.registry, "Python"))

    def test_locks_and_binding_changes_are_respected(self):
        plan = self.prepare()
        with lock(self.vault / ".uaml/write.lock"):
            self.assert_code("WRITE_CONFLICT", lambda: self.apply(plan))
        self.git_cmd("remote", "add", "origin", "https://example.invalid/moved")
        self.assert_code("CHECKOUT_UNTRUSTED", lambda: self.apply(plan))

    def test_self_replacement_inactive_target_and_cycles_are_rejected(self):
        self.assert_code("SUPERSESSION_INVALID", lambda: supersession.prepare(self.git, self.registry, self.old["id"], self.old["id"], "self"))
        plan = self.prepare()
        self.apply(plan)
        self.assert_code("SUPERSESSION_INVALID", lambda: self.prepare())
        self.assert_code("SUPERSESSION_INVALID", lambda: supersession.prepare(self.git, self.registry, self.new["id"], self.old["id"], "cycle"))

    def test_replacement_chain_preserves_previous_associations(self):
        self.apply(self.prepare())
        header, body = self.note(version="3.13")
        knowledge.add(self.git, self.registry, self.source(header, body))
        second = supersession.prepare(self.git, self.registry, self.new["id"], header["id"], "第三版替代第二版，保留完整鏈。")
        self.apply(second)
        self.assertEqual(relations(knowledge.scan(self.root)[0]), [])
        middle = knowledge.get(self.git, self.registry, self.new["id"])["metadata"]
        self.assertEqual(middle["supersedes"], [self.old["id"]])
        self.assertEqual(middle["superseded_by"], header["id"])

    def test_single_note_proposal_cannot_resurrect_superseded_note(self):
        self.apply(self.prepare())
        file = self.root / f"{self.old['id']}.md"
        header, body = frontmatter(file.read_bytes())
        header.update(revision=3, status="verified")
        self.assert_code("RELATION_CHANGE_UNSUPPORTED", lambda: propose(self.git, self.registry, self.source(header, body)))

    def test_cli_prepare_inspect_apply(self):
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "knowledge", "supersede"]
        result = subprocess.run(command + ["--old", self.old["id"], "--replacement", self.new["id"], "--reason", "明確審查新版"], capture_output=True, check=True)
        plan = json.loads(result.stdout)
        inspected = subprocess.run(command + ["--transaction", plan["transaction_id"]], capture_output=True, check=True)
        self.assertEqual(json.loads(inspected.stdout)["plan_hash"], plan["plan_hash"])
        applied = subprocess.run(command + ["--transaction", plan["transaction_id"], "--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout)["status"], "SUPERSESSION_APPLIED")
