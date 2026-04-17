from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TASKS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SearchDownloadAndParseTaskTests(unittest.TestCase):
    def test_execute_downloads_and_parses(self):
        module = load_module("search_download_and_parse_task", "search_download_and_parse.py")

        search_payload = {
            "status": "ok",
            "run_id": "search-1",
            "data": {
                "engine_results": [{"engine": "arxiv", "status": "ok"}],
                "candidates": [
                    {"title": "Paper One", "pdf_url": "https://example.org/one.pdf"},
                    {"title": "Paper Two", "pdf_url": "https://example.org/two.pdf"},
                ],
            },
            "errors": [],
        }

        def mock_run_search(_args):
            return 0, search_payload, "", 100

        module.run_search = mock_run_search

        def mock_run_download_tool(_candidates, _args):
            return (
                10,
                {
                    "status": "ok",
                    "data": {
                        "downloaded": [
                            {"title": "Paper One", "path": "/tmp/one.pdf"},
                            {"title": "Paper Two", "path": "/tmp/two.pdf"},
                        ],
                        "failed": [{"title": "Paper Three", "reason": "HTTP 404"}],
                        "download_summary": {
                            "success_count": 2,
                            "failure_count": 1,
                            "success_titles": ["Paper One", "Paper Two"],
                            "failed_titles": ["Paper Three"],
                        },
                    },
                    "errors": [{"code": "PARTIAL_DOWNLOAD_FAILURE", "message": "Some downloads failed"}],
                },
                "",
                50,
            )

        module.run_download_tool = mock_run_download_tool

        parse_calls: list[str] = []

        def mock_run_parse_tool(pdf_path: str, _args):
            parse_calls.append(pdf_path)
            if pdf_path.endswith("one.pdf"):
                return (
                    0,
                    {
                        "status": "ok",
                        "run_id": "parse-1",
                        "data": {"parsed": {"input_pdf": pdf_path, "title": "Paper One", "doi": "10.1000/one", "year": 2024}},
                        "errors": [],
                    },
                    "",
                    20,
                )
            return (
                40,
                {
                    "status": "error",
                    "run_id": "parse-2",
                    "data": {"parsed": None},
                    "errors": [{"code": "PARSE", "message": "No extractable text found in PDF"}],
                },
                "",
                30,
            )

        module.run_parse_tool = mock_run_parse_tool

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            args = Namespace(
                keywords=["gnn"],
                year_start=2020,
                year_end=2026,
                top_k=3,
                engines=["arxiv"],
                timeout=7,
                download_dir=str(Path(td) / "pdfs"),
                max_pages=5,
                output=str(out),
                run_id="run-1",
                log_level="INFO",
            )
            rc = module.execute(args)
            self.assertEqual(rc, 10)
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(parse_calls, ["/tmp/one.pdf", "/tmp/two.pdf"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["parse_summary"]["success_count"], 1)
        self.assertEqual(payload["data"]["parse_summary"]["failure_count"], 1)
        self.assertEqual(len(payload["data"]["parsed"]), 2)
        self.assertEqual(payload["data"]["parsed"][0]["status"], "ok")
        self.assertEqual(payload["data"]["parsed"][1]["status"], "error")


if __name__ == "__main__":
    unittest.main()
