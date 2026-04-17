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


class SearchAndDownloadTaskTests(unittest.TestCase):
    def test_execute_downloads_and_reports_failures(self):
        module = load_module("search_and_download_task", "search_and_download.py")

        search_payload = {
            "status": "ok",
            "run_id": "search-1",
            "data": {
                "engine_results": [{"engine": "arxiv", "status": "ok"}],
                "candidates": [
                    {"title": "Paper One", "pdf_url": "https://example.org/one.pdf"},
                    {"title": "Paper Two", "pdf_url": None},
                    {"title": "Paper Three", "pdf_url": "https://example.org/three.pdf"},
                ],
            },
            "errors": [],
        }

        def mock_run_search(_args):
            return 0, search_payload, "", 123

        module.run_search = mock_run_search

        calls: list[list[dict[str, object]]] = []

        def mock_run_download_tool(candidates: list[dict[str, object]], _args):
            calls.append(candidates)
            return (
                10,
                {
                    "status": "ok",
                    "data": {
                        "downloaded": [
                            {"title": "Paper One", "url": "https://example.org/one.pdf", "path": "/tmp/001_paper_one.pdf", "duration_ms": 10}
                        ],
                        "failed": [
                            {"title": "Paper Two", "url": None, "reason": "Missing source URL", "duration_ms": 0},
                            {"title": "Paper Three", "url": "https://example.org/three.pdf", "reason": "HTTP 404", "duration_ms": 11},
                        ],
                        "download_summary": {
                            "success_count": 1,
                            "failure_count": 2,
                            "success_titles": ["Paper One"],
                            "failed_titles": ["Paper Two", "Paper Three"],
                        },
                    },
                    "errors": [{"code": "PARTIAL_DOWNLOAD_FAILURE", "message": "Some downloads failed"}],
                },
                "",
                18,
            )

        module.run_download_tool = mock_run_download_tool

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            download_dir = Path(td) / "pdfs"
            args = Namespace(
                keywords=["gnn"],
                year_start=2020,
                year_end=2026,
                top_k=3,
                engines=["arxiv"],
                timeout=7,
                download_dir=str(download_dir),
                output=str(out),
                run_id="run-1",
                log_level="INFO",
            )
            rc = module.execute(args)
            self.assertEqual(rc, 10)
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(len(calls), 1)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["download_summary"]["success_count"], 1)
        self.assertEqual(payload["data"]["download_summary"]["failure_count"], 2)
        self.assertIn("Paper One", payload["data"]["download_summary"]["success_titles"])
        self.assertIn("Paper Two", payload["data"]["download_summary"]["failed_titles"])
        self.assertIn("Paper Three", payload["data"]["download_summary"]["failed_titles"])


if __name__ == "__main__":
    unittest.main()
