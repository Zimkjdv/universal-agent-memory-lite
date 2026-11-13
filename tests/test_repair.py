import json
import subprocess
import sys
from unittest.mock import patch

from uaml.errors import UamlError
from uaml.formats import frontmatter, markdown
from uaml.project_memory import checkpoint, checkpoint_marker
from uaml.recovery import recover
from uaml.repair import repair
from uaml.storage import write

from .support import Workspace


class RepairTests(Workspace):
    def interrupted(self, target="HANDOFF.md"):
        self.bind()
        note = self.repo / "docs/memory/HANDOFF.md"
        header, body = frontmatter(note.read_bytes())
        note.write_bytes(markdown(header, body + "\nSaved task: finish the parser.\n"))

        def fail(path, *args, **kwargs):
            if path.name == target:
                raise OSError("interrupted")
            return write(path, *args, **kwargs)

        with patch("uaml.project_memory.write", side_effect=fail), self.assertRaises(OSError):
            checkpoint(self.git, self.registry, "test-agent")
        pending = [p for p in (self.registry.parent / "transactions").glob("*.json")
                   if json.loads(p.read_text(encoding="utf-8"))["status"] == "prepared"]
        self.assertEqual(len(pending), 1)
        return pending[0].stem

    def test_preview_is_read_only_and_apply_finishes_saved_snapshot(self):
        transaction = self.interrupted()
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        plan = repair(self.git, self.registry, transaction)
        self.assertEqual(plan["status"], "REPAIR_PREVIEW")
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})
        result = repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(result["status"], "REPAIRED")
        recovered = recover(self.git, self.registry)
        self.assertEqual(recovered["status"], "RECOVERED")
        self.assertIn("finish the parser", recovered["sources"][1]["untrusted_markdown"])
        self.assertEqual(repair(self.git, self.registry, transaction)["status"], "REPAIR_NOT_NEEDED")

    def test_interruption_before_checkpoint_is_repairable(self):
        transaction = self.interrupted("checkpoint.json")
        plan = repair(self.git, self.registry, transaction)
        self.assertEqual(plan["actions"][-1]["action"], "finish")
        repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(recover(self.git, self.registry)["status"], "RECOVERED")

    def test_interruption_before_first_write_blocks_new_checkpoint_in_any_registry(self):
        transaction = self.interrupted("PROJECT-STATE.md")
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry), "--json"]
        compact = subprocess.run(command + ["recover", "--compact"], capture_output=True)
        self.assertEqual(compact.returncode, 1)
        self.assertIn(transaction, next(item["message"] for item in json.loads(compact.stdout)["diagnostics"]
                                        if item["code"] == "CHECKPOINT_TRANSACTION_PENDING"))
        original = {p: p.read_bytes() for p in (self.repo / "docs/memory").iterdir()}
        other_registry = self.base / "other" / "registry.json"
        for path in (self.registry, other_registry):
            with self.assertRaises(UamlError) as error:
                checkpoint(self.git, path, "retry")
            self.assertEqual(error.exception.code, "CHECKPOINT_TRANSACTION_PENDING")
        self.assertFalse(other_registry.parent.exists())
        self.assertEqual(original, {p: p.read_bytes() for p in original})

    def test_complete_journal_with_marker_can_be_finalized_without_rewriting_files(self):
        self.bind()
        with patch("uaml.project_memory.clear_checkpoint_marker", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                checkpoint(self.git, self.registry, "test-agent")
        marker = checkpoint_marker(self.git)
        transaction = json.loads(marker.read_bytes())["snapshot_id"]
        report = recover(self.git, self.registry)
        self.assertEqual(report["status"], "DEGRADED")
        self.assertTrue(all(source["checkpoint_verified"] for source in report["sources"]))
        plan = repair(self.git, self.registry, transaction)
        self.assertEqual(plan["status"], "REPAIR_PREVIEW")
        self.assertTrue(all(action["action"] == "keep" for action in plan["actions"]))
        with patch("uaml.repair.write") as write_file:
            self.assertEqual(repair(self.git, self.registry, transaction, True, plan["plan_hash"])["status"], "REPAIRED")
        write_file.assert_not_called()
        self.assertFalse(marker.exists())
        self.assertEqual(recover(self.git, self.registry)["status"], "RECOVERED")

    def test_repair_of_another_journal_cannot_replace_pending_checkpoint(self):
        transaction = self.interrupted()
        journals = (self.registry.parent / "transactions").glob("*.json")
        older = next(path.stem for path in journals if path.stem != transaction)
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, older, True, "old-plan")
        self.assertEqual(error.exception.code, "CHECKPOINT_TRANSACTION_PENDING")
        self.assertEqual(json.loads(checkpoint_marker(self.git).read_bytes())["snapshot_id"], transaction)

    def test_legacy_prepared_journal_remains_repairable_without_marker(self):
        transaction = self.interrupted()
        marker = checkpoint_marker(self.git)
        plan = repair(self.git, self.registry, transaction)
        marker.unlink()
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        legacy_plan = repair(self.git, self.registry, transaction)
        self.assertEqual(repair(self.git, self.registry, transaction, True, legacy_plan["plan_hash"])["status"], "REPAIRED")
        self.assertFalse(marker.exists())

    def test_corrupt_pending_marker_is_preserved(self):
        self.interrupted()
        marker = checkpoint_marker(self.git)
        marker.write_bytes(b"not a journal")
        with self.assertRaises(UamlError) as error:
            checkpoint(self.git, self.registry, "retry")
        self.assertEqual(error.exception.code, "MEMORY_CORRUPT")
        self.assertEqual(marker.read_bytes(), b"not a journal")

    def test_pending_marker_is_per_worktree_and_not_tracked(self):
        transaction = self.interrupted()
        worktree = self.base / "linked checkout"
        self.git_cmd("worktree", "add", "--detach", str(worktree))
        other_git = type(self.git)(worktree)
        self.assertFalse(checkpoint_marker(other_git).exists())
        self.assertEqual(json.loads(checkpoint_marker(self.git).read_bytes())["snapshot_id"], transaction)
        self.assertNotIn(b"uaml-checkpoint-pending", self.git_cmd("status", "--porcelain", "--untracked-files=all"))

    def test_manual_edit_after_interruption_is_never_overwritten(self):
        transaction = self.interrupted()
        plan = repair(self.git, self.registry, transaction)
        note = self.repo / "docs/memory/PROJECT-STATE.md"
        note.write_bytes(note.read_bytes() + b"\nmanual work after crash\n")
        before = note.read_bytes()
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(error.exception.code, "REPAIR_CONFLICT")
        self.assertEqual(note.read_bytes(), before)

    def test_requires_exact_reviewed_plan(self):
        transaction = self.interrupted()
        for expected in (None, "wrong"):
            with self.subTest(expected=expected), self.assertRaises(UamlError) as error:
                repair(self.git, self.registry, transaction, True, expected)
            self.assertIn(error.exception.code, ("PLAN_REQUIRED", "WRITE_CONFLICT"))

    def test_tampered_payload_cannot_be_applied(self):
        transaction = self.interrupted()
        blob = self.registry.parent / "transactions" / f"{transaction}.1.after"
        blob.write_bytes(blob.read_bytes() + b"modified")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "REPAIR_CONFLICT")

    def test_journal_cannot_target_another_file(self):
        transaction = self.interrupted()
        journal = self.registry.parent / "transactions" / f"{transaction}.json"
        value = json.loads(journal.read_text(encoding="utf-8"))
        value["entries"][0]["path"] = "AGENTS.md"
        journal.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "SCHEMA_INVALID")

    def test_changed_binding_and_other_checkout_are_rejected(self):
        transaction = self.interrupted()
        file = self.repo / ".uaml/project.yaml"
        file.write_bytes(file.read_bytes().replace("測試專案".encode(), b"changed"))
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "REPAIR_CONFLICT")

    def test_live_or_leftover_lock_not_stolen(self):
        transaction = self.interrupted()
        plan = repair(self.git, self.registry, transaction)
        lock = self.repo / ".uaml/write.lock"
        lock.write_text("existing owner", encoding="utf-8")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction, True, plan["plan_hash"])
        self.assertEqual(error.exception.code, "WRITE_CONFLICT")
        self.assertEqual(lock.read_text(), "existing owner")

    def test_old_journal_does_not_invent_missing_payloads(self):
        transaction = self.interrupted()
        journal = self.registry.parent / "transactions" / f"{transaction}.json"
        journal.write_text('{"schema_version":1}', encoding="utf-8")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "REPAIR_UNSUPPORTED")

    def test_completed_transaction_cannot_erase_later_manual_edits(self):
        self.bind()
        transaction = checkpoint(self.git, self.registry, "manual")["snapshot_id"]
        note = self.repo / "docs/memory/HANDOFF.md"
        note.write_bytes(note.read_bytes() + b"\nlater edit\n")
        with self.assertRaises(UamlError) as error:
            repair(self.git, self.registry, transaction)
        self.assertEqual(error.exception.code, "REPAIR_CONFLICT")

    def test_cli_preview_and_apply(self):
        transaction = self.interrupted()
        command = [sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry),
                   "--json", "repair", "--transaction", transaction]
        preview = subprocess.run(command, capture_output=True, check=True)
        plan = json.loads(preview.stdout.decode("utf-8"))
        applied = subprocess.run(command + ["--apply", "--expect-plan", plan["plan_hash"]], capture_output=True, check=True)
        self.assertEqual(json.loads(applied.stdout.decode("utf-8"))["status"], "REPAIRED")
