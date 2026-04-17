#!/usr/bin/env python3
"""arXiv search adapter for MSDP Protocol v1."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from common_search_tool import (
    InputPayload,
    classify_network_error,
    dump_json,
    fetch_text,
    hash_candidate,
    load_json,
    make_envelope,
    make_error,
    next_run_id,
    normalize_input,
    parse_common_args,
    utc_now,
)

TOOL_NAME = "search.arxiv"
PROVIDER = "arxiv"
API_URL = "https://export.arxiv.org/api/query"


def parse_candidates(xml_text: str, payload: InputPayload, query: str) -> list[dict]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    out: list[dict] = []
    rank = 0
    for entry in root.findall("atom:entry", ns):
        rank += 1
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        source_url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
        authors = [a.findtext("atom:name", default="", namespaces=ns).strip() for a in entry.findall("atom:author", ns)]
        authors = [a for a in authors if a]
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
        if payload.year_start and year and year < payload.year_start:
            continue
        if payload.year_end and year and year > payload.year_end:
            continue
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        cid = hash_candidate(title=title, source_url=source_url or (pdf_url or str(rank)))
        out.append(
            {
                "candidate_id": cid,
                "title": title,
                "authors": authors,
                "year": year,
                "doi": None,
                "source_url": source_url or None,
                "pdf_url": pdf_url,
                "venue": "arXiv",
                "abstract_snippet": summary,
                "provider": PROVIDER,
                "provider_rank": len(out) + 1,
                "provider_score": None,
                "provenance": [{"provider": PROVIDER, "query": query, "fetched_at": utc_now()}],
            }
        )
        if len(out) >= payload.top_k:
            break
    return out


def run(args) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()
    try:
        request = load_json(args.input)
        payload = normalize_input(request)
        query = " ".join(payload.keywords)
        status, xml_text = fetch_text(
            API_URL,
            timeout=args.timeout,
            query_params={"search_query": f"all:{query}", "start": 0, "max_results": payload.top_k * 2},
        )
        if status != 200:
            envelope = make_envelope(TOOL_NAME, run_id, started_at, "error", {"query": query, "candidates": []}, [make_error(PROVIDER, "NETWORK", f"arXiv returned HTTP {status}", status in {429, 500, 502, 503, 504})])
            dump_json(args.output, envelope)
            return 30
        candidates = parse_candidates(xml_text, payload, query)
        envelope = make_envelope(TOOL_NAME, run_id, started_at, "ok", {"query": query, "year_start": payload.year_start, "year_end": payload.year_end, "top_k": payload.top_k, "candidates": candidates}, [])
        dump_json(args.output, envelope)
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
    raise SystemExit(run(parse_common_args("Search arXiv and return top-k candidate manuscripts")))
