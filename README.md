# msdp
Manuscript Search Download and Parse.

## Planning Documents
Before implementation, requirements and interoperability standards are captured in:
- `docs/requirements-and-standards.md`
- `docs/implementation-plan.md`

## Implemented Search Tools (Protocol v1)
MSDP now includes **10 popular academic search engines/providers** with a consistent CLI and envelope format:
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

## Tool-Specific Standard
- `doc/google-scholar-search-tool-standard.md`: Input/output standard for the initial search tool in Protocol v1 envelope format.
