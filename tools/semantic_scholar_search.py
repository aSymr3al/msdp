#!/usr/bin/env python3
"""Semantic Scholar search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.semantic_scholar"
PROVIDER = "semantic_scholar"
API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        request = load_json(args.input)
        payload = normalize_input(request)
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL, timeout=args.timeout, query_params={"query": query, "limit": payload.top_k, "fields": "title,year,authors,url,abstract,externalIds"})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"Semantic Scholar returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        candidates = []
        for idx, row in enumerate(data.get("data", []), start=1):
            year = row.get("year")
            if payload.year_start and isinstance(year, int) and year < payload.year_start:
                continue
            if payload.year_end and isinstance(year, int) and year > payload.year_end:
                continue
            source_url = row.get("url")
            doi = (row.get("externalIds") or {}).get("DOI")
            authors = [a.get("name", "").strip() for a in row.get("authors", []) if a.get("name")]
            title = (row.get("title") or "").strip()
            candidates.append({"candidate_id": hash_candidate(title, source_url or str(idx)), "title": title, "authors": authors, "year": year, "doi": doi, "source_url": source_url, "pdf_url": None, "venue": None, "abstract_snippet": (row.get("abstract") or "").strip(), "provider": PROVIDER, "provider_rank": len(candidates) + 1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "ok", {"query": query, "year_start": payload.year_start, "year_end": payload.year_end, "top_k": payload.top_k, "candidates": candidates[: payload.top_k]}, []))
        return 0
    except ValueError as exc:
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"candidates": []}, [make_error(PROVIDER, "VALIDATION", str(exc))]))
        return 20
    except Exception as exc:  # pylint: disable=broad-except
        message, retryable = classify_network_error(exc)
        code = "NETWORK" if retryable else "INTERNAL"
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"candidates": []}, [make_error(PROVIDER, code, message, retryable)]))
        return 30 if code == "NETWORK" else 40


if __name__ == "__main__":
    raise SystemExit(run(parse_common_args("Search Semantic Scholar and return top-k candidate manuscripts")))
