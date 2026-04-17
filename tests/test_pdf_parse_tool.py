from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PdfParseToolTests(unittest.TestCase):
    def test_parse_success(self):
        module = load_module("pdf_parse_tool", "pdf_parse_tool.py")

        def mock_extract_text(_pdf_path: Path, max_pages: int) -> str:
            self.assertEqual(max_pages, 3)
            return """A Great Paper Title
Abstract: We present a robust method for extraction.
1 Introduction
Contact: first.author@example.edu
DOI: 10.1234/ABC.5678
Published in 2024
Results and Conclusion sections follow.
"""

        with tempfile.TemporaryDirectory() as td:
            fake_pdf = Path(td) / "paper.pdf"
            fake_pdf.write_bytes(b"%PDF-1.4 test")
            out = Path(td) / "out.json"
            module.extract_text_from_pdf = mock_extract_text

            rc = module.run(Namespace(input_pdf=str(fake_pdf), output=str(out), run_id="run-1", max_pages=3))
            body = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(body["status"], "ok")
        parsed = body["data"]["parsed"]
        self.assertEqual(parsed["title"], "A Great Paper Title")
        self.assertEqual(parsed["doi"], "10.1234/ABC.5678")
        self.assertEqual(parsed["year"], 2024)
        self.assertIn("first.author@example.edu", parsed["contact_emails"])
        self.assertIn("introduction", parsed["detected_sections"])

    def test_validation_error(self):
        module = load_module("pdf_parse_tool_validation", "pdf_parse_tool.py")
        with tempfile.TemporaryDirectory() as td:
            bad_path = Path(td) / "paper.txt"
            bad_path.write_text("not a pdf", encoding="utf-8")
            out = Path(td) / "out.json"
            rc = module.run(Namespace(input_pdf=str(bad_path), output=str(out), run_id="run-2", max_pages=2))
            body = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(rc, 20)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["errors"][0]["code"], "VALIDATION")


if __name__ == "__main__":
    unittest.main()
