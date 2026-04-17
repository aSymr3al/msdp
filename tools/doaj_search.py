#!/usr/bin/env python3
"""DOAJ search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.doaj"
PROVIDER = "doaj"
API_URL = "https://doaj.org/api/search/articles/"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL + query, timeout=args.timeout, query_params={"pageSize": payload.top_k * 2})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"DOAJ returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        results = data.get("results", [])
        candidates = []
        for row in results:
            bib = row.get("bibjson", {})
            year = int(bib.get("year")) if str(bib.get("year", "")).isdigit() else None
            if payload.year_start and year and year < payload.year_start:
                continue
            if payload.year_end and year and year > payload.year_end:
                continue
            links = bib.get("link", [])
            source_url = links[0].get("url") if links else None
            pdf_url = next((l.get("url") for l in links if (l.get("type") or "").lower() == "fulltext"), None)
            title = (bib.get("title") or "").strip()
            authors = [a.get("name", "").strip() for a in bib.get("author", []) if a.get("name")]
            candidates.append({"candidate_id": hash_candidate(title, source_url or str(len(candidates)+1)), "title": title, "authors": authors, "year": year, "doi": bib.get("identifier", [{}])[0].get("id") if bib.get("identifier") else None, "source_url": source_url, "pdf_url": pdf_url, "venue": (bib.get("journal") or {}).get("title"), "abstract_snippet": (bib.get("abstract") or "").strip(), "provider": PROVIDER, "provider_rank": len(candidates)+1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
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
    raise SystemExit(run(parse_common_args("Search DOAJ and return top-k candidate manuscripts")))
