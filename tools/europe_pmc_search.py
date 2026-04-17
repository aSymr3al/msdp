#!/usr/bin/env python3
"""Europe PMC search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.europe_pmc"
PROVIDER = "europe_pmc"
API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        status, data = fetch_json(API_URL, timeout=args.timeout, query_params={"query": query, "format": "json", "pageSize": payload.top_k * 2})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"Europe PMC returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        results = data.get("resultList", {}).get("result", [])
        candidates = []
        for row in results:
            year = int(row.get("pubYear")) if str(row.get("pubYear", "")).isdigit() else None
            if payload.year_start and year and year < payload.year_start:
                continue
            if payload.year_end and year and year > payload.year_end:
                continue
            title = (row.get("title") or "").strip()
            source_url = row.get("sourceUrl") or row.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url")
            doi = row.get("doi")
            pmid = row.get("pmid")
            if not source_url and pmid:
                source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            candidates.append({"candidate_id": hash_candidate(title, source_url or str(len(candidates)+1)), "title": title, "authors": [a.strip() for a in (row.get("authorString") or "").split(",") if a.strip()], "year": year, "doi": doi, "source_url": source_url, "pdf_url": None, "venue": row.get("journalTitle"), "abstract_snippet": (row.get("abstractText") or "").strip(), "provider": PROVIDER, "provider_rank": len(candidates)+1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
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
    raise SystemExit(run(parse_common_args("Search Europe PMC and return top-k candidate manuscripts")))
