import json
import subprocess
import sys
from uuid import uuid4
from unittest.mock import patch

from uaml.binding import trust
from uaml.dedup import jaccard, tokens
from uaml.errors import UamlError
from uaml.formats import markdown
from uaml.knowledge import add, get, search
from uaml.proposals import apply, propose

from .test_knowledge import KnowledgeWorkspace


class DedupTests(KnowledgeWorkspace):
    def test_concurrent_processes_cannot_create_two_exact_authorities(self):
        one_header, body = self.note()
        two_header = {**one_header, "id": str(uuid4())}
        sources = [self.source(one_header, body), self.source(two_header, body)]
        gate = self.base / "start-workers"
        code = ("import sys,time; from pathlib import Path; from uaml.cli import main; "
                "print('READY',flush=True)\n"
                "while not Path(sys.argv[4]).exists(): time.sleep(0.01)\n"
                "raise SystemExit(main(['--repo',sys.argv[1],'--registry',sys.argv[2],'--json','knowledge','add',sys.argv[3]]))")
        workers = [subprocess.Popen([sys.executable, "-c", code, str(self.repo), str(self.registry), str(source), str(gate)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for source in sources]
        try:
            for worker in workers:
                self.assertEqual(worker.stdout.readline().strip(), b"READY")
            gate.write_text("go", encoding="utf-8")
            results = [json.loads(worker.communicate(timeout=15)[0].decode("utf-8")) for worker in workers]
            self.assertEqual(sum(result["status"] == "KNOWLEDGE_ADDED" for result in results), 1)
            self.assertTrue(all(result["status"] in ("KNOWLEDGE_ADDED", "KNOWLEDGE_DUPLICATE", "WRITE_CONFLICT") for result in results))
            self.assertEqual(len(list((self.vault / "UAML/Knowledge").glob("*.md"))), 1)
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.terminate()
                    worker.communicate(timeout=5)

    def test_exact_content_new_id_returns_existing_authority(self):
        header, body = self.note()
        original = add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        result = add(self.git, self.registry, self.source(header, body))
        self.assertEqual(result["status"], "KNOWLEDGE_DUPLICATE")
        self.assertEqual(result["id"], original["id"])
        self.assertEqual(len(list((self.vault / "UAML/Knowledge").glob("*.md"))), 1)

    def test_same_id_exact_import_is_idempotent(self):
        header, body = self.note()
        source = self.source(header, body)
        add(self.git, self.registry, source)
        self.assertEqual(add(self.git, self.registry, source)["status"], "KNOWLEDGE_DUPLICATE")

    def test_distinct_chinese_notes_do_not_collapse_to_empty_tokens(self):
        self.assertTrue(tokens("中文筆記"))
        self.assertEqual(jaccard(set(), set()), 0)
        for title, body in (("水果產地", "# 水果\n香蕉蘋果農場收成。"), ("天文觀測", "# 夜空\n星系月球望遠鏡影像。")):
            header, body = self.note(title=title, body=body)
            self.assertEqual(add(self.git, self.registry, self.source(header, body))["status"], "KNOWLEDGE_ADDED")

    def test_near_duplicate_requires_review_of_same_catalog(self):
        header, body = self.note()
        add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        candidate_file = self.source(header, body + "\n請先建立備份。")
        result = add(self.git, self.registry, candidate_file)
        self.assertEqual(result["status"], "KNOWLEDGE_SIMILAR")
        self.assertEqual(len(list((self.vault / "UAML/Knowledge").glob("*.md"))), 1)
        with self.assertRaises(UamlError):
            add(self.git, self.registry, candidate_file, True, "wrong")
        applied = add(self.git, self.registry, candidate_file, True, result["review_hash"])
        self.assertEqual(applied["status"], "KNOWLEDGE_ADDED")

    def test_different_versions_conditions_and_os_remain_separate(self):
        for version, os_name, condition in (("3.12", "windows", "GPU required"), ("3.11", "windows", "GPU required"),
                                            ("3.12", "linux", "GPU required"), ("3.12", "windows", "CPU only")):
            header, body = self.note(version=version)
            header["applicability"].update(os=[os_name], conditions=[condition])
            self.assertEqual(add(self.git, self.registry, self.source(header, body))["status"], "KNOWLEDGE_ADDED")
        self.assertEqual(search(self.git, self.registry, "Python")["total_matches"], 4)

    def test_negation_is_not_removed_or_automatically_merged(self):
        header, body = self.note(title="Install compiler", body="Do install the compiler before building the entire package.")
        add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        result = add(self.git, self.registry, self.source(header, "Do not install the compiler before building the entire package."))
        self.assertIn("w:not", tokens("not"))
        self.assertEqual(result["status"], "KNOWLEDGE_SIMILAR")

    def test_incomplete_scan_never_allows_duplicate_blind_import(self):
        header, body = self.note()
        add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        (self.vault / "UAML/Knowledge/broken.md").write_text("broken", encoding="utf-8")
        with self.assertRaises(UamlError) as error:
            add(self.git, self.registry, self.source(header, body))
        self.assertEqual(error.exception.code, "SCAN_INCOMPLETE")


class ProposalTests(KnowledgeWorkspace):
    def revision(self):
        header, body = self.note(status="experimental")
        add(self.git, self.registry, self.source(header, body))
        header["revision"] = 2
        return header, body + "\n新步驟：驗證工具版本。\n"

    def test_propose_changes_only_private_artifacts_apply_backs_up_original(self):
        header, body = self.revision()
        note_path = self.vault / "UAML/Knowledge" / f"{header['id']}.md"
        original = note_path.read_bytes()
        result = propose(self.git, self.registry, self.source(header, body))
        self.assertEqual(note_path.read_bytes(), original)
        self.assertIn("新步驟", result["untrusted_diff"])
        applied = apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(applied["revision"], 2)
        self.assertIn("新步驟", get(self.git, self.registry, header["id"])["untrusted_markdown"])
        self.assertIn(original, [p.read_bytes() for p in (self.registry.parent / "backups").glob("*.bak")])

    def test_manual_edit_after_review_is_preserved(self):
        header, body = self.revision()
        result = propose(self.git, self.registry, self.source(header, body))
        target = self.vault / "UAML/Knowledge" / f"{header['id']}.md"
        target.write_bytes(target.read_bytes() + b"\nmanual edit\n")
        before = target.read_bytes()
        with self.assertRaises(UamlError) as error:
            apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        self.assertEqual(target.read_bytes(), before)

    def test_stale_or_modified_proposals_and_payloads_are_rejected(self):
        header, body = self.revision()
        result = propose(self.git, self.registry, self.source(header, body))
        with self.assertRaises(UamlError):
            apply(self.git, self.registry, result["proposal_id"], "wrong")
        payload = self.registry.parent / "proposals" / f"{result['proposal_id']}.md"
        payload.write_bytes(payload.read_bytes() + b"tampered")
        with self.assertRaises(UamlError) as error:
            apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")

    def test_read_access_can_propose_but_cannot_apply(self):
        header, body = self.revision()
        trust(self.git, self.registry, "read")
        result = propose(self.git, self.registry, self.source(header, body))
        with self.assertRaises(UamlError) as error:
            apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(error.exception.code, "KNOWLEDGE_ACCESS_DENIED")

    def test_source_creation_time_and_revision_must_be_preserved(self):
        header, body = self.revision()
        for key, val in (("created_at", "2000-01-01T00:00:00Z"), ("revision", 5), ("source_project_ids", [])):
            changed = {**header, key: val}
            with self.subTest(key=key), self.assertRaises(UamlError):
                propose(self.git, self.registry, self.source(changed, body))

    def test_verified_changed_steps_need_new_verification_or_downgrade(self):
        header, body = self.note()
        add(self.git, self.registry, self.source(header, body))
        header["revision"] = 2
        body += "\nChanged procedure.\n"
        with self.assertRaises(UamlError) as error:
            propose(self.git, self.registry, self.source(header, body))
        self.assertEqual(error.exception.code, "VERIFICATION_REQUIRED")
        header["status"] = "experimental"
        self.assertEqual(propose(self.git, self.registry, self.source(header, body))["status"], "KNOWLEDGE_PROPOSED")

    def test_fresh_verification_is_accepted_as_user_evidence_not_executed(self):
        header, body = self.note()
        header["verification"]["checked_at"] = "2026-01-01T00:00:00Z"
        add(self.git, self.registry, self.source(header, body))
        header["revision"] = 2
        header["verification"]["checked_at"] = "2026-02-01T00:00:00Z"
        result = propose(self.git, self.registry, self.source(header, body + "\nRevalidated changed step.\n"))
        self.assertEqual(apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])["status"], "KNOWLEDGE_APPLIED")

    def test_two_reviewed_updates_cannot_lose_the_first_update(self):
        header, body = self.revision()
        one = propose(self.git, self.registry, self.source(header, body + "first proposal"))
        two = propose(self.git, self.registry, self.source(header, body + "second proposal"))
        apply(self.git, self.registry, one["proposal_id"], one["plan_hash"])
        with self.assertRaises(UamlError):
            apply(self.git, self.registry, two["proposal_id"], two["plan_hash"])
        self.assertIn("first proposal", get(self.git, self.registry, header["id"])["untrusted_markdown"])

    def test_catalog_change_requires_a_new_proposal(self):
        header, body = self.revision()
        reviewed = propose(self.git, self.registry, self.source(header, body))
        other, other_body = self.note(title="Docker networks", body="# Containers\nBridge and port routing.")
        add(self.git, self.registry, self.source(other, other_body))
        with self.assertRaises(UamlError) as error:
            apply(self.git, self.registry, reviewed["proposal_id"], reviewed["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")

    def test_cli_near_duplicate_exit_and_explicit_acknowledgment(self):
        header, body = self.note()
        add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        source = self.source(header, body + "\nAdditional precaution.\n")
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json",
                   "knowledge", "add", str(source)]
        preview = subprocess.run(command, capture_output=True)
        self.assertEqual(preview.returncode, 1)
        result = json.loads(preview.stdout.decode("utf-8"))
        accepted = subprocess.run(command + ["--allow-similar", "--expect-candidates", result["review_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(accepted.stdout.decode("utf-8"))["status"], "KNOWLEDGE_ADDED")

    def test_new_proposal_runs_duplicate_checks_and_near_acknowledgment(self):
        header, body = self.note()
        add(self.git, self.registry, self.source(header, body))
        header["id"] = str(uuid4())
        self.assertEqual(propose(self.git, self.registry, self.source(header, body))["status"], "KNOWLEDGE_DUPLICATE")
        result = propose(self.git, self.registry, self.source(header, body + "\nExtra reminder.\n"))
        self.assertTrue(result["candidates"])
        with self.assertRaises(UamlError) as error:
            apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(error.exception.code, "SIMILARITY_REVIEW_REQUIRED")
        self.assertEqual(apply(self.git, self.registry, result["proposal_id"], result["plan_hash"], True)["status"], "KNOWLEDGE_APPLIED")

    def test_deprecation_requires_reason_and_is_hidden_by_default(self):
        header, body = self.revision()
        header.update(status="deprecated", deprecation_reason="old environment only")
        result = propose(self.git, self.registry, self.source(header, body))
        apply(self.git, self.registry, result["proposal_id"], result["plan_hash"])
        self.assertEqual(search(self.git, self.registry, "Python")["total_matches"], 0)

    def test_cli_review_and_apply(self):
        header, body = self.revision()
        source = self.source(header, body)
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json", "knowledge"]
        result = subprocess.run(command + ["propose", str(source)], check=True, capture_output=True)
        plan = json.loads(result.stdout.decode("utf-8"))
        applied = subprocess.run(command + ["apply", plan["proposal_id"], "--expect-plan", plan["plan_hash"]], check=True, capture_output=True)
        self.assertEqual(json.loads(applied.stdout.decode("utf-8"))["status"], "KNOWLEDGE_APPLIED")
