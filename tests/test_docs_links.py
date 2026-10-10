"""Offline documentation checker fixtures; never fetch remote links."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "check_docs_links", Path(__file__).resolve().parents[1] / "scripts" / "check_docs_links.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class DocumentationLinkTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "docs").mkdir()

    def write(self, path, text):
        (self.root / path).write_text(text, encoding="utf-8")

    def test_valid_inline_reference_html_and_unicode_anchors(self):
        self.write("README.md", '# Home\n\n[guide](docs/guide.md#中文标题)\n'
                   '[again][guide]\n\n[guide]: docs/guide.md#usage-1\n'
                   '<img src="docs/small%20image.png">\n'
                   '[external](https://example.invalid/a#missing)\n')
        self.write("docs/guide.md", '# Guide\n\n## 中文标题\n\n## Usage\n\n## Usage\n')
        (self.root / "docs/small image.png").write_bytes(b"fixture")
        errors, files, links = checker.audit(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(files, 2)
        self.assertEqual(links, 4)

    def test_missing_file_anchor_and_reference_reported(self):
        self.write("README.md", "# Home\n\n[missing](docs/absent.md)\n"
                   "[anchor](docs/guide.md#absent)\n[ref][undefined]\n")
        self.write("docs/guide.md", "# Guide\n")
        errors, _, _ = checker.audit(self.root)
        self.assertTrue(any("missing target" in e for e in errors))
        self.assertTrue(any("missing heading anchor" in e for e in errors))
        self.assertTrue(any("undefined reference" in e for e in errors))

    def test_translated_readme_links_are_audited(self):
        self.write("README.md", "# Home\n\n[中文](README.zh-CN.md)\n")
        self.write("README.zh-CN.md", "# 中文\n\n[English](README.md)\n[指南](docs/missing.md)\n")
        errors, files, _ = checker.audit(self.root)
        self.assertEqual(files, 2)
        self.assertTrue(any("README.zh-CN.md: missing target" in e for e in errors))
        self.write("docs/missing.md", "# Guide\n")
        self.assertEqual(checker.audit(self.root)[0], [])

    def test_code_examples_ignored_but_machine_paths_rejected(self):
        fence = chr(96) * 3
        self.write("README.md", f"# Home\n\n{fence}text\n[example](missing.md)\n"
                   f"{fence}\n{chr(96)}[inline](missing.md){chr(96)}\n")
        self.assertEqual(checker.audit(self.root)[0], [])
        self.write("README.md", "# Home\n\n" + "Z:" + "/private/example.png\n")
        self.assertTrue(any("machine path" in e for e in checker.audit(self.root)[0]))

    def test_structural_errors(self):
        self.write("README.md", "# Home\n\n### Skipped\n\n| A | B |\n| --- | --- |\n"
                   "| one |\n\n" + chr(96) * 3 + "\nunclosed")
        errors, _, _ = checker.audit(self.root)
        for message in ("heading skips", "table column", "unclosed code fence"):
            self.assertTrue(any(message in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
