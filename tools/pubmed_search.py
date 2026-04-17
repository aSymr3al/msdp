#!/usr/bin/env python3
"""PubMed search adapter for MSDP Protocol v1."""
from __future__ import annotations

from common_search_tool import classify_network_error, dump_json, fetch_json, hash_candidate, load_json, make_envelope, make_error, next_run_id, normalize_input, parse_common_args, utc_now

TOOL_NAME = "search.pubmed"
PROVIDER = "pubmed"
SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        payload = normalize_input(load_json(args.input))
        query = " ".join(payload.keywords)
        term = query
        if payload.year_start:
            term += f" AND {payload.year_start}:3000[pdat]"
        status, search = fetch_json(SEARCH_URL, timeout=args.timeout, query_params={"db": "pubmed", "retmode": "json", "retmax": payload.top_k * 2, "term": term})
        if status != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"PubMed search returned HTTP {status}", status in {429, 500, 502, 503, 504})]))
            return 30
        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "ok", {"query": query, "year_start": payload.year_start, "year_end": payload.year_end, "top_k": payload.top_k, "candidates": []}, []))
            return 0
        status2, summaries = fetch_json(SUMMARY_URL, timeout=args.timeout, query_params={"db": "pubmed", "retmode": "json", "id": ",".join(ids)})
        if status2 != 200:
            dump_json(args.output, make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"PubMed summary returned HTTP {status2}", status2 in {429, 500, 502, 503, 504})]))
            return 30
        result = summaries.get("result", {})
        candidates = []
        for pmid in ids:
            row = result.get(pmid, {})
            year = None
            pubdate = row.get("pubdate", "")
            if pubdate[:4].isdigit():
                year = int(pubdate[:4])
            if payload.year_end and year and year > payload.year_end:
                continue
            title = (row.get("title") or "").strip()
            source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            authors = [a.get("name", "").strip() for a in row.get("authors", []) if a.get("name")]
            candidates.append({"candidate_id": hash_candidate(title, source_url), "title": title, "authors": authors, "year": year, "doi": None, "source_url": source_url, "pdf_url": None, "venue": row.get("fulljournalname"), "abstract_snippet": "", "provider": PROVIDER, "provider_rank": len(candidates) + 1, "provider_score": None, "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}]})
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
    raise SystemExit(run(parse_common_args("Search PubMed and return top-k candidate manuscripts")))
