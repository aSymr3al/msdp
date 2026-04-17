# msdp
Manuscript Search Download and Parse.

## Planning Documents
Before implementation, requirements and interoperability standards are captured in:
- `docs/requirements-and-standards.md`
- `docs/implementation-plan.md`

## Implemented Search Tools (Protocol v1)
MSDP includes **10 popular academic search engines/providers** with a consistent CLI and envelope format:
1. `tools/google_scholar_search.py`
2. `tools/arxiv_search.py`
3. `tools/semantic_scholar_search.py`
4. `tools/crossref_search.py`
5. `tools/openalex_search.py`
6. `tools/pubmed_search.py`
7. `tools/europe_pmc_search.py`
8. `tools/dblp_search.py`
9. `tools/doaj_search.py`
10. `tools/biorxiv_search.py`

Shared helper utilities live in `tools/common_search_tool.py`.

## Implemented Parse Tool (Protocol v1 Envelope)
- `tools/pdf_parse_tool.py`: parses a single PDF and extracts important information (title, DOI, year, abstract, contact emails, detected sections) with typed error handling using **PyMuPDF** (current default backend).
- `tools/pdf_parse_tool_pypdf_legacy.py`: legacy parser variant kept for backward compatibility with **pypdf**.

Example:
```bash
python3 tools/pdf_parse_tool.py \
  --input-pdf artifacts/raw/sample.pdf \
  --output - \
  --max-pages 5
```

## Tool-Specific Standard
- `docs/google-scholar-search-tool-standard.md`: Input/output standard for the initial search tool in Protocol v1 envelope format.

## Tasks
- `tasks/search_papers.py`: ready-to-run aggregator task that executes selected search tools, merges outputs, and emits a deduplicated Protocol v1 JSON envelope suitable for downstream scripts.

Example:
```bash
python3 tasks/search_papers.py \
  --keywords "graph neural networks" "molecular property prediction" \
  --year-start 2020 \
  --year-end 2026 \
  --top-k 5 \
  --engines arxiv semantic_scholar openalex \
  --output artifacts/search_papers.json
```

- `tasks/search_and_download.py`: orchestration task that runs multi-engine search and attempts to download discovered PDFs, logging per-step timing and download success/failure title summaries.

Example:
```bash
python3 tasks/search_and_download.py \
  --keywords "graph neural networks" "molecular property prediction" \
  --year-start 2020 \
  --year-end 2026 \
  --top-k 5 \
  --engines arxiv openalex semantic_scholar \
  --download-dir artifacts/pdfs \
  --output artifacts/search_and_download.json
```
