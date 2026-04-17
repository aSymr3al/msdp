from __future__ import annotations

import importlib.util
import sys as _sys
import json
import tempfile
import unittest
import sys
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
    _sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SearchToolTests(unittest.TestCase):
    def run_with_mock(self, module, payload: dict, mock_fetch_fn_name: str, mock_fetch):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            inp.write_text(json.dumps(payload), encoding="utf-8")
            setattr(module, mock_fetch_fn_name, mock_fetch)
            rc = module.run(Namespace(input=str(inp), output=str(out), run_id="test-run", timeout=10))
            body = json.loads(out.read_text(encoding="utf-8"))
            return rc, body

    def test_google_scholar(self):
        module = load_module("google_scholar_search", "google_scholar_search.py")

        def mock_fetch_html(url: str, timeout: int):
            html = '<div class="gs_r gs_or gs_scl"><div><h3 class="gs_rt"><a href="https://example.org/p">A Paper</a></h3><div class="gs_a">A One, B Two - 2022</div><div class="gs_rs">Snippet</div><div class="gs_or_ggsm"><a href="https://example.org/p.pdf">[PDF]</a></div></div></div></div>'
            return 200, html

        payload = {"keywords": ["test"], "year_start": 2020, "year_end": 2026, "top_k": 3}
        rc, body = self.run_with_mock(module, payload, "fetch_html", mock_fetch_html)
        self.assertEqual(rc, 0)
        self.assertEqual(body["status"], "ok")
        self.assertGreaterEqual(len(body["data"]["candidates"]), 1)

    def test_other_tools(self):
        cases = [
            ("arxiv_search.py", "fetch_text", lambda *_, **__: (200, """<feed xmlns='http://www.w3.org/2005/Atom'><entry><id>http://arxiv.org/abs/1</id><published>2024-01-01T00:00:00Z</published><title>Arxiv Title</title><summary>Abstract</summary><author><name>Author A</name></author><link title='pdf' href='http://arxiv.org/pdf/1.pdf' /></entry></feed>""")),
            ("semantic_scholar_search.py", "fetch_json", lambda *_ , **__: (200, {"data": [{"title": "Sem Title", "year": 2023, "authors": [{"name": "AA"}], "url": "https://s2.org/p", "abstract": "x", "externalIds": {"DOI": "10.1/abc"}}]})),
            ("crossref_search.py", "fetch_json", lambda *_ , **__: (200, {"message": {"items": [{"DOI": "10.1/x", "title": ["Crossref Title"], "author": [{"given": "A", "family": "B"}], "issued": {"date-parts": [[2022]]}, "URL": "https://doi.org/10.1/x", "container-title": ["J"], "abstract": "abs", "score": 12.0}]}})),
            ("openalex_search.py", "fetch_json", lambda *_ , **__: (200, {"results": [{"display_name": "OpenAlex Title", "publication_year": 2024, "id": "https://openalex.org/W1", "authorships": [{"author": {"display_name": "A"}}], "open_access": {"is_oa": True, "oa_url": "https://x.pdf"}, "doi": "10.2/y", "primary_location": {"source": {"display_name": "Venue"}}}]})),
            ("pubmed_search.py", "fetch_json", self.mock_pubmed_fetch),
            ("europe_pmc_search.py", "fetch_json", lambda *_ , **__: (200, {"resultList": {"result": [{"title": "EPMC Title", "pubYear": "2023", "authorString": "A, B", "doi": "10.3/z", "journalTitle": "J", "abstractText": "abs", "sourceUrl": "https://epmc.org/1"}]}})),
            ("dblp_search.py", "fetch_json", lambda *_ , **__: (200, {"result": {"hits": {"hit": [{"@score": "1.0", "info": {"title": "DBLP Title", "authors": {"author": ["A"]}, "year": "2021", "url": "https://dblp.org/rec/1", "venue": "Conf", "doi": "10.4/q"}}]}}})),
            ("doaj_search.py", "fetch_json", lambda *_ , **__: (200, {"results": [{"bibjson": {"title": "DOAJ Title", "year": "2020", "author": [{"name": "A"}], "journal": {"title": "Journal"}, "link": [{"url": "https://doaj.org/article/1", "type": "fulltext"}], "abstract": "abs", "identifier": [{"id": "10.5/w"}]}}]})),
            ("biorxiv_search.py", "fetch_json", lambda *_ , **__: (200, {"collection": [{"title": "Test BioRxiv Title", "date": "2025-01-01", "authors": "A;B", "doi": "10.1101/2025.01.01.123456", "version": "1", "url": "https://www.biorxiv.org/content/10.1101/2025.01.01.123456v1", "abstract": "abs"}]})),
        ]

        payload = {"keywords": ["test"], "year_start": 2019, "year_end": 2026, "top_k": 3}
        for idx, (filename, fn_name, mock_fn) in enumerate(cases, start=1):
            module = load_module(f"tool_{idx}", filename)
            rc, body = self.run_with_mock(module, payload, fn_name, mock_fn)
            self.assertEqual(rc, 0, msg=filename)
            self.assertEqual(body["status"], "ok", msg=filename)
            self.assertGreaterEqual(len(body["data"]["candidates"]), 1, msg=filename)

    @staticmethod
    def mock_pubmed_fetch(url: str, timeout: int, query_params=None, headers=None):
        if "esearch.fcgi" in url:
            return 200, {"esearchresult": {"idlist": ["1"]}}
        return 200, {"result": {"1": {"title": "PubMed Title", "pubdate": "2024 Jan", "authors": [{"name": "A"}], "fulljournalname": "J"}}}


if __name__ == "__main__":
    unittest.main()
