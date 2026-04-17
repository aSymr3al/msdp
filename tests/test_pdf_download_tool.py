from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PdfDownloadToolTests(unittest.TestCase):
    def test_extract_pdf_links_and_download(self):
        module = load_module("pdf_download_tool", "pdf_download_tool.py")

        html = """
        <html>
          <head><meta name='citation_pdf_url' content='/paper.pdf'></head>
          <body><a href='https://example.org/files/other.pdf'>PDF</a></body>
        </html>
        """
        links = module.extract_pdf_links(html, "https://example.org/landing")
        self.assertIn("https://example.org/paper.pdf", links)
        self.assertIn("https://example.org/files/other.pdf", links)

        def mock_request(url: str, timeout: int, accept: str):
            if url.endswith("landing"):
                return 200, html.encode("utf-8"), "text/html", url
            return 200, b"%PDF-1.7 mock", "application/pdf", "https://example.org/paper.pdf"

        module.request_url = mock_request

        with tempfile.TemporaryDirectory() as td:
            args = Namespace(input="-", output="-", timeout=5, run_id="run-1", log_level="INFO")
            success, failure = module.download_item(
                {"title": "Sample", "source_url": "https://example.org/landing"},
                1,
                Path(td),
                args.timeout,
            )
        self.assertIsNotNone(success)
        self.assertIsNone(failure)
        assert success is not None
        self.assertEqual(success["resolved_url"], "https://example.org/paper.pdf")


if __name__ == "__main__":
    unittest.main()
