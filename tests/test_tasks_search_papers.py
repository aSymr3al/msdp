from __future__ import annotations

import importlib.util
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


class SearchPapersTaskTests(unittest.TestCase):
    def test_deduplicate_across_engines(self):
        module = load_module("search_papers_task", "search_papers.py")

        first_response = {
            "tool": "search.arxiv",
            "run_id": "r1",
            "status": "ok",
            "data": {
                "candidates": [
                    {
                        "candidate_id": "a",
                        "title": "Graph Neural Networks for Molecules",
                        "authors": ["Alice"],
                        "year": 2024,
                        "doi": "10.1000/xyz",
                        "source_url": "https://example.org/paper",
                        "pdf_url": "https://example.org/paper.pdf",
                        "venue": None,
                        "abstract_snippet": "A",
                        "provider": "arxiv",
                        "provider_rank": 1,
                        "provider_score": None,
                        "provenance": [{"provider": "arxiv", "query": "gnn", "fetched_at": "2026-01-01T00:00:00Z"}],
                    }
                ]
            },
            "errors": [],
        }

        second_response = {
            "tool": "search.openalex",
            "run_id": "r2",
            "status": "ok",
            "data": {
                "candidates": [
                    {
                        "candidate_id": "b",
                        "title": "Graph Neural Networks for Molecules",
                        "authors": ["Bob"],
                        "year": 2024,
                        "doi": "https://doi.org/10.1000/xyz",
                        "source_url": "https://example.org/paper/",
                        "pdf_url": None,
                        "venue": "Venue",
                        "abstract_snippet": "B",
                        "provider": "openalex",
                        "provider_rank": 2,
                        "provider_score": None,
                        "provenance": [{"provider": "openalex", "query": "gnn", "fetched_at": "2026-01-01T00:00:02Z"}],
                    }
                ]
            },
            "errors": [],
        }

        calls = []

        def mock_run_engine(script_name: str, payload: dict, timeout: int):
            calls.append(script_name)
            if script_name == module.ENGINE_TO_SCRIPT["arxiv"]:
                return 0, first_response, ""
            return 0, second_response, ""

        module.run_engine = mock_run_engine

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            args = Namespace(
                keywords=["gnn"],
                year_start=2020,
                year_end=2026,
                top_k=5,
                engines=["arxiv", "openalex"],
                timeout=10,
                run_id="run-1",
                output=str(out),
            )
            rc = module.execute(args)
            self.assertEqual(rc, 0)
            result = out.read_text(encoding="utf-8")

        self.assertEqual(len(calls), 2)
        self.assertIn('"status": "ok"', result)
        self.assertIn('"candidate_count": 1', result)
        self.assertIn('"Alice"', result)
        self.assertIn('"Bob"', result)

    def test_validation_failure(self):
        module = load_module("search_papers_task_validation", "search_papers.py")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            args = Namespace(
                keywords=[],
                year_start=2020,
                year_end=2026,
                top_k=5,
                engines=["arxiv"],
                timeout=10,
                run_id="run-2",
                output=str(out),
            )
            rc = module.execute(args)
            self.assertEqual(rc, 20)
            text = out.read_text(encoding="utf-8")
            self.assertIn('"status": "error"', text)
            self.assertIn("VALIDATION", text)


if __name__ == "__main__":
    unittest.main()
