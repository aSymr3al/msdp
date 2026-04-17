# msdp
Manuscript Search Download and Parse.

## Planning Documents
Before implementation, requirements and interoperability standards are captured in:
- `docs/requirements-and-standards.md`
- `docs/implementation-plan.md`

## Implemented Tool (Initial)
- `tools/google_scholar_search.py`: Python 3.x search tool that accepts query keywords, year range, and top-k; queries Google Scholar and returns normalized manuscript candidates including PDF URLs when available.

## Tool-Specific Standard
- `doc/google-scholar-search-tool-standard.md`: Input/output standard for the first search tool in Protocol v1 envelope format.
