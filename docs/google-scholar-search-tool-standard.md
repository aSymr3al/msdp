# Google Scholar Search Tool I/O Standard (MSDP Protocol v1)

This document defines the input/output contract for the first MSDP search tool implementation:
`tools/google_scholar_search.py`.

## 1) Tool Identity
- **Tool name**: `search.google_scholar`
- **Language**: Python 3.x
- **Invocation style**: CLI with JSON input/output

## 2) CLI Contract
```bash
python3 tools/google_scholar_search.py \
  --input <json file | -> \
  --output <json file | -> \
  [--run-id <uuid>] \
  [--timeout <seconds>]
```

### Exit Codes
- `0`: success
- `20`: validation error
- `30`: provider/network failure
- `40`: internal error

## 3) Input Standard
Input JSON contains the required search fields below.

### Input Schema (logical)
```json
{
  "keywords": ["graph neural networks", "molecular property prediction"],
  "year_start": 2020,
  "year_end": 2026,
  "top_k": 5
}
```

### Field Rules
- `keywords` (required): non-empty array of non-empty strings.
- `year_start` (optional): integer in `[1900, 2100]` or `null`.
- `year_end` (optional): integer in `[1900, 2100]` or `null`.
- `top_k` (required): integer in `[1, 50]`.
- If both years are provided, `year_start <= year_end`.

## 4) Output Standard
Output follows the shared MSDP envelope format (`Protocol v1`).

### Success Response Example
```json
{
  "protocol_version": "1.0",
  "tool": "search.google_scholar",
  "run_id": "8ec8b8e3-7d8b-4cde-9828-4cc38f8f84b8",
  "status": "ok",
  "started_at": "2026-04-17T00:00:00Z",
  "ended_at": "2026-04-17T00:00:02Z",
  "duration_ms": 2000,
  "data": {
    "query": "graph neural networks molecular property prediction",
    "year_start": 2020,
    "year_end": 2026,
    "top_k": 5,
    "search_url": "https://scholar.google.com/scholar?...",
    "candidates": [
      {
        "candidate_id": "13f6cc1ec8d4fabc0134",
        "title": "...",
        "authors": ["..."],
        "year": 2024,
        "doi": null,
        "source_url": "https://...",
        "pdf_url": "https://...pdf",
        "venue": null,
        "abstract_snippet": "...",
        "provider": "google_scholar",
        "provider_rank": 1,
        "provider_score": null,
        "provenance": [
          {
            "provider": "google_scholar",
            "query": "graph neural networks molecular property prediction",
            "fetched_at": "2026-04-17T00:00:01Z"
          }
        ]
      }
    ]
  },
  "errors": [],
  "metrics": {
    "candidate_count": 1
  }
}
```

### Error Response Example
```json
{
  "protocol_version": "1.0",
  "tool": "search.google_scholar",
  "run_id": "2cd865ff-71e1-41ef-a5de-c30b2f890ff1",
  "status": "error",
  "data": {
    "candidates": []
  },
  "errors": [
    {
      "code": "VALIDATION",
      "message": "'top_k' must be an integer between 1 and 50",
      "retryable": false,
      "provider": "google_scholar",
      "context": {}
    }
  ]
}
```

## 5) Candidate Field Notes
- `source_url`: publication/landing page URL parsed from the title link.
- `pdf_url`: direct downloadable PDF URL when shown in Scholar's PDF side link.
- `year`: parsed from Scholar metadata line when available.

## 6) Operational Notes
- Query terms are joined with spaces before submission.
- Year filters are mapped to Scholar URL parameters `as_ylo` and `as_yhi`.
- HTML parsing extracts ranked rows from Scholar result cards.
- `candidate_id` is a stable hash of normalized title + source URL.

## 7) Compliance with Project Standards
This tool aligns with:
- protocol envelope conventions in `docs/requirements-and-standards.md`,
- the phase-2 search adapter direction in `docs/implementation-plan.md`.
