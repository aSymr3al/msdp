#!/usr/bin/env python3
"""DBLP search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.dblp"
PROVIDER = "dblp"
API_URL = "https://dblp.org/search/publ/api"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL, timeout=args.timeout, query_params={"q": query, "format": "json", "h": payload.top_k * 2})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"DBLP returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        candidates = []
        for hit in hits:
            info = hit.get("info", {})
            year = int(info.get("year")) if str(info.get("year", "")).isdigit() else None
            if payload.year_start and year and year < payload.year_start:
                continue
            if payload.year_end and year and year > payload.year_end:
                continue
            authors_data = info.get("authors", {}).get("author", [])
            if isinstance(authors_data, list):
                authors = [a.get("text", "").strip() if isinstance(a, dict) else str(a).strip() for a in authors_data]
            else:
                authors = [authors_data.get("text", "").strip()] if isinstance(authors_data, dict) else [str(authors_data).strip()]
            title = (info.get("title") or "").strip()
            source_url = info.get("url")
            candidates.append({"candidate_id": hash_candidate(title, source_url or str(len(candidates)+1)), "title": title, "authors": [a for a in authors if a], "year": year, "doi": info.get("doi"), "source_url": source_url, "pdf_url": None, "venue": info.get("venue"), "abstract_snippet": "", "provider": PROVIDER, "provider_rank": len(candidates)+1, "provider_score": float(hit.get("@score", 0.0)) if str(hit.get("@score", "")).replace('.', '', 1).isdigit() else None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
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
    raise SystemExit(run(parse_common_args("Search DBLP and return top-k candidate manuscripts")))
