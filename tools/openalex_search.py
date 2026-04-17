#!/usr/bin/env python3
"""OpenAlex search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.openalex"
PROVIDER = "openalex"
API_URL = "https://api.openalex.org/works"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL, timeout=args.timeout, query_params={"search": query, "per-page": payload.top_k * 2})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"OpenAlex returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        candidates = []
        for row in data.get("results", []):
            year = row.get("publication_year")
            if payload.year_start and isinstance(year, int) and year < payload.year_start:
                continue
            if payload.year_end and isinstance(year, int) and year > payload.year_end:
                continue
            title = (row.get("display_name") or "").strip()
            source_url = row.get("id")
            authors = [a.get("author", {}).get("display_name", "").strip() for a in row.get("authorships", []) if a.get("author", {}).get("display_name")]
            open_access = row.get("open_access", {})
            pdf_url = open_access.get("oa_url") if open_access.get("is_oa") else None
            candidates.append({"candidate_id": hash_candidate(title, source_url or str(len(candidates) + 1)), "title": title, "authors": authors, "year": year, "doi": row.get("doi"), "source_url": source_url, "pdf_url": pdf_url, "venue": (row.get("primary_location", {}).get("source", {}) or {}).get("display_name"), "abstract_snippet": "", "provider": PROVIDER, "provider_rank": len(candidates) + 1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
            if len(candidates) >= payload.top_k:
                break
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "ok", {"query": query, "year_start": payload.year_start, "year_end": payload.year_end, "top_k": payload.top_k, "candidates": candidates}, []))
        return 0
    except ValueError as exc:
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"candidates": []}, [make_error(PROVIDER, "VALIDATION", str(exc))]))
        return 20
    except Exception as exc:
        message, retryable = classify_network_error(exc)
        code = "NETWORK" if retryable else "INTERNAL"
        dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"candidates": []}, [make_error(PROVIDER, code, message, retryable)]))
        return 30 if code == "NETWORK" else 40


if __name__ == "__main__":
    raise SystemExit(run(parse_common_args("Search OpenAlex and return top-k candidate manuscripts")))
