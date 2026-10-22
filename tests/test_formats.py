import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from uaml.errors import UamlError
from uaml.formats import frontmatter, parse_json, parse_yaml, read_bytes
from uaml.paths import inside, relative_path


class ParsingTests(unittest.TestCase):
    def test_rejects_yaml_alias_tags_merge_duplicates_and_multiple_documents(self):
        values = ["key: 1\nkey: 2", "key: &a text\nother: *a", "key: !!python/object:bad {}",
                  "<<: {}", "key: 1\n---\nkey: 2", "1: value", "key: [" * 20]
        for value in values:
            with self.subTest(value=value), self.assertRaises(UamlError):
                parse_yaml(value)

    def test_unicode_frontmatter_and_crlf(self):
        header, body = frontmatter("---\r\ntitle: 中文\r\n---\r\n# 內容\r\n".encode())
        self.assertEqual(header["title"], "中文")
        self.assertEqual(body, "# 內容\n")

    def test_json_duplicate_keys_rejected(self):
        with self.assertRaises(UamlError):
            parse_json(b'{"schema_version": 1, "schema_version": 2}')

    def test_rejects_oversize_and_invalid_utf8(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "large"
            path.write_bytes(b"x" * (256 * 1024 + 1))
            with self.assertRaises(UamlError) as error:
                read_bytes(path)
            self.assertEqual(error.exception.code, "DOCUMENT_TOO_LARGE")
        with self.assertRaises(UamlError):
            parse_json(b'\xff')

    def test_rejects_nonportable_and_traversal_paths(self):
        for value in ("../private", "a/../../b", "C:/secret", "//host/share", "a\\b", ".git/../file",
                      "a//b", "a/./b", "file:stream", "CON.md", "a/NUL", "a.", "https://x", "a\x00b"):
            with self.subTest(value=value), self.assertRaises(UamlError):
                relative_path(value)
        self.assertEqual(relative_path("docs/中文 with spaces.md"), "docs/中文 with spaces.md")

    def test_rejects_directory_junction_escape_on_windows(self):
        import os
        import subprocess
        if os.name != "nt":
            self.skipTest("Windows junction-specific case")
        with TemporaryDirectory() as folder:
            root, outside = Path(folder) / "root", Path(folder) / "outside"
            root.mkdir()
            outside.mkdir()
            junction = root / "linked"
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
            if result.returncode:
                self.skipTest("This Windows environment cannot create a junction")
            try:
                with self.assertRaises(UamlError) as error:
                    inside(root, "linked/secret.md")
                self.assertEqual(error.exception.code, "UNSAFE_PATH")
            finally:
                junction.rmdir()
