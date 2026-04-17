#!/usr/bin/env python3
"""Crossref search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.crossref"
PROVIDER = "crossref"
API_URL = "https://api.crossref.org/works"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL, timeout=args.timeout, query_params={"query": query, "rows": payload.top_k * 2, "select": "DOI,title,author,issued,URL,container-title,abstract,score"}, headers={"mailto": "msdp@example.org"})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"Crossref returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        candidates = []
        for row in data.get("message", {}).get("items", []):
            issued = row.get("issued", {}).get("date-parts", [[None]])
            year = issued[0][0] if issued and issued[0] else None
            if payload.year_start and isinstance(year, int) and year < payload.year_start:
                continue
            if payload.year_end and isinstance(year, int) and year > payload.year_end:
                continue
            authors = [" ".join(p for p in [a.get("given", ""), a.get("family", "")] if p).strip() for a in row.get("author", [])]
            authors = [a for a in authors if a]
            title = ((row.get("title") or [""])[0] or "").strip()
            source_url = row.get("URL")
            candidates.append({"candidate_id": hash_candidate(title, source_url or row.get("DOI", "")), "title": title, "authors": authors, "year": year, "doi": row.get("DOI"), "source_url": source_url, "pdf_url": None, "venue": ((row.get("container-title") or [None])[0]), "abstract_snippet": (row.get("abstract") or "").strip(), "provider": PROVIDER, "provider_rank": len(candidates) + 1, "provider_score": row.get("score"), "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
            if len(candidates) >= payload.top_k:
                break
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "ok", {"query": query, "year_start": payload.year_start, "year_end": payload.year_end, "top_k": payload.top_k, "candidates": candidates}, []))
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
    raise SystemExit(run(parse_common_args("Search Crossref and return top-k candidate manuscripts")))
