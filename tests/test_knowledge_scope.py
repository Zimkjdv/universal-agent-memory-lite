import os
import subprocess
from unittest.mock import patch

from uaml import replicas
from uaml.errors import UamlError
from uaml.knowledge import add, get, search
from uaml.formats import markdown, read_at_most

from .test_knowledge import KnowledgeWorkspace


class KnowledgeScopeTests(KnowledgeWorkspace):
    def link_directory(self, link, target):
        self.assertTrue(link.is_relative_to(self.base))
        self.assertTrue(target.is_relative_to(self.base))
        if os.name == "nt":
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(target, target_is_directory=True)
            self.addCleanup(link.unlink)

    def test_linked_knowledge_root_is_rejected_before_content_read_or_write(self):
        private = self.vault / "Personal"
        private.mkdir()
        header, body = self.note()
        note = private / f"{header['id']}.md"
        note.write_bytes(markdown(header, body))
        root = self.vault / "UAML/Knowledge"
        self.link_directory(root, private)
        source = self.source(header, body)
        original = note.read_bytes()

        def guarded_read(path, *args):
            self.assertFalse(path.resolve().is_relative_to(private), "private note read")
            return read_at_most(path, *args)

        for operation in (lambda: search(self.git, self.registry, "Python"),
                          lambda: get(self.git, self.registry, header["id"]),
                          lambda: add(self.git, self.registry, source)):
            with self.subTest(operation=operation):
                with (patch("uaml.knowledge.read_at_most", side_effect=guarded_read),
                      patch("uaml.formats.read_at_most", side_effect=guarded_read)):
                    with self.assertRaises(UamlError) as error:
                        operation()
                self.assertEqual(error.exception.code, "UNSAFE_PATH")
        self.assertEqual(note.read_bytes(), original)

    def test_linked_ancestor_is_rejected_before_scan(self):
        area = self.vault / "UAML"
        relocated = self.vault / "original-area"
        self.assertTrue(relocated.is_relative_to(self.base))
        area.rename(relocated)
        self.link_directory(area, relocated)
        with patch("uaml.knowledge.scan", side_effect=AssertionError("linked area scanned")):
            with self.assertRaises(UamlError) as error:
                search(self.git, self.registry, "Python")
        self.assertEqual(error.exception.code, "UNSAFE_PATH")

    def test_explicit_replica_comparison_rejects_a_linked_root(self):
        private = self.vault / "Personal"
        private.mkdir()
        self.link_directory(self.vault / "UAML/Knowledge", private)
        with patch("uaml.knowledge.scan", side_effect=AssertionError("linked replica scanned")):
            report = replicas.compare(self.git, self.registry, True)
        self.assertEqual(report["status"], "REPLICA_UNVERIFIED")
        self.assertIn("UNSAFE_PATH", {item["code"] for item in report["diagnostics"]})

    def test_file_in_place_of_knowledge_directory_has_stable_diagnostic(self):
        root = self.vault / "UAML/Knowledge"
        root.write_bytes(b"keep this user file")
        with self.assertRaises(UamlError) as error:
            search(self.git, self.registry, "Python")
        self.assertEqual(error.exception.code, "UNSAFE_PATH")
        self.assertEqual(root.read_bytes(), b"keep this user file")
