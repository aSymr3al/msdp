#!/usr/bin/env python3
"""bioRxiv search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.biorxiv"
PROVIDER = "biorxiv"
API_URL = "https://api.biorxiv.org/details/biorxiv"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords).lower()
        status, data = fetch_json(API_URL + "/2020-01-01/3000-01-01", timeout=args.timeout)
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"bioRxiv returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        candidates = []
        for row in data.get("collection", []):
            title = (row.get("title") or "").strip()
            if query and query not in title.lower() and query not in (row.get("abstract") or "").lower():
                continue
            year = int(str(row.get("date", ""))[:4]) if str(row.get("date", ""))[:4].isdigit() else None
            if payload.year_start and year and year < payload.year_start:
                continue
            if payload.year_end and year and year > payload.year_end:
                continue
            source_url = row.get("url")
            doi = row.get("doi")
            candidates.append({"candidate_id": hash_candidate(title, source_url or doi or str(len(candidates)+1)), "title": title, "authors": [a.strip() for a in (row.get("authors") or "").split(";") if a.strip()], "year": year, "doi": doi, "source_url": source_url, "pdf_url": f"https://www.biorxiv.org/content/{doi}v{row.get('version')}.full.pdf" if doi else None, "venue": "bioRxiv", "abstract_snippet": (row.get("abstract") or "").strip(), "provider": PROVIDER, "provider_rank": len(candidates)+1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
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
    raise SystemExit(run(parse_common_args("Search bioRxiv and return top-k candidate manuscripts")))
