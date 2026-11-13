"""Terminate a real checkpoint writer at deterministic publication boundaries."""
import json
import os
import signal
import subprocess
import sys
from time import monotonic, sleep

from uaml.formats import digest, frontmatter, markdown
from uaml.project_memory import checkpoint_marker

from .support import Workspace


WRITER = """
import os
import sys
from pathlib import Path
from unittest.mock import patch

from uaml.cli import main
from uaml.formats import parse_json
from uaml.storage import write

repo, registry, ready = map(Path, sys.argv[1:4])
stage = sys.argv[4]

def pause_after_write(path, data, *args, **kwargs):
    write(path, data, *args, **kwargs)
    if path.name == stage or (stage == 'journal complete' and path.parent.name == 'transactions'
                              and path.suffix == '.json' and parse_json(data)['status'] == 'complete'):
        ready.write_text(str(os.getpid()), encoding='ascii')
        sys.stdin.readline()

with patch('uaml.project_memory.write', side_effect=pause_after_write):
    raise SystemExit(main(['--repo', str(repo), '--registry', str(registry), 'checkpoint', '--agent', 'crash-fixture']))
"""


class CheckpointProcessTests(Workspace):
    def cli(self, *args):
        result = subprocess.run([sys.executable, "-m", "uaml", "--repo", str(self.repo), "--registry", str(self.registry),
                                 "--json", *args], capture_output=True, timeout=20)
        return result.returncode, json.loads(result.stdout)

    def crash_at(self, stage, lock_path, index):
        ready = self.base / f"writer-{index}.ready"
        with subprocess.Popen([sys.executable, "-c", WRITER, str(self.repo), str(self.registry), str(ready), stage],
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as process:
            try:
                deadline = monotonic() + 20
                while (not ready.exists() or ready.stat().st_size == 0) and process.poll() is None and monotonic() < deadline:
                    sleep(0.025)
                if not ready.exists() or ready.stat().st_size == 0:
                    _, stderr = process.communicate(b"\n", timeout=10)
                    self.fail(f"Writer did not reach {stage}: {stderr.decode(errors='replace')}")
                writer_pid = int(ready.read_text(encoding="ascii"))
                self.assertEqual(json.loads(lock_path.read_bytes())["pid"], writer_pid)
                # Windows venv launchers may have a distinct PID from the writer.
                if writer_pid == process.pid:
                    process.kill()
                else:
                    os.kill(writer_pid, signal.SIGTERM)
                self.assertNotEqual(process.wait(timeout=10), 0)
            finally:
                if process.poll() is None:
                    process.communicate(b"\n", timeout=10)

    def test_cli_repairs_after_writer_is_killed_at_each_publication_boundary(self):
        self.bind()
        memory = self.repo / "docs/memory"
        note = memory / "HANDOFF.md"
        lock_path = self.repo / ".uaml/write.lock"
        marker = checkpoint_marker(self.git)
        stages = (marker.name, "PROJECT-STATE.md", note.name, "checkpoint.json", "journal complete")
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                header, body = frontmatter(note.read_bytes())
                task = f"Saved before termination at {stage}."
                note.write_bytes(markdown(header, body + f"\n{task}\n"))
                before = {path: digest(path.read_bytes()) for path in memory.iterdir()}
                self.crash_at(stage, lock_path, index)
                transaction = json.loads(marker.read_bytes())["snapshot_id"]
                journal_path = self.registry.parent / "transactions" / f"{transaction}.json"
                journal = json.loads(journal_path.read_bytes())
                self.assertEqual(journal["status"], "complete" if stage == "journal complete" else "prepared")

                published = min(index, 3)
                for position, entry in enumerate(journal["entries"]):
                    path = self.repo / entry["path"]
                    self.assertEqual(entry["before_hash"], before[path])
                    self.assertEqual(digest((self.registry.parent / entry["before_blob"]).read_bytes()), before[path])
                    expected = entry["after_hash"] if position < published else before[path]
                    self.assertEqual(digest(path.read_bytes()), expected)

                exit_code, report = self.cli("recover", "--compact")
                self.assertEqual((exit_code, report["status"]), (1, "DEGRADED"))
                self.assertTrue(any(item["code"] == "CHECKPOINT_TRANSACTION_PENDING" and transaction in item["message"]
                                    for item in report["diagnostics"]))
                exit_code, plan = self.cli("repair", "--transaction", transaction)
                self.assertEqual((exit_code, plan["status"]), (0, "REPAIR_PREVIEW"))
                self.assertEqual([action["action"] for action in plan["actions"]],
                                 ["keep"] * published + ["finish"] * (3 - published))
                apply = ("repair", "--transaction", transaction, "--apply", "--expect-plan", plan["plan_hash"])
                lock_bytes = lock_path.read_bytes()
                exit_code, refused = self.cli(*apply)
                self.assertEqual((exit_code, refused["status"]), (1, "WRITE_CONFLICT"))
                self.assertEqual(lock_path.read_bytes(), lock_bytes)
                # Only this fixture's verified dead child owns the lock.
                lock_path.rename(self.base / f"writer-{index}.lock")
                exit_code, repaired = self.cli(*apply)
                self.assertEqual((exit_code, repaired["status"]), (0, "REPAIRED"))
                self.assertFalse(marker.exists())
                self.assertEqual(json.loads(journal_path.read_bytes())["status"], "complete")
                for entry in journal["entries"]:
                    self.assertEqual(digest((self.repo / entry["path"]).read_bytes()), entry["after_hash"])
                exit_code, recovered = self.cli("recover")
                self.assertEqual((exit_code, recovered["status"]), (0, "RECOVERED"))
                self.assertTrue(all(source["checkpoint_verified"] for source in recovered["sources"]))
                self.assertIn(task, recovered["sources"][1]["untrusted_markdown"])
