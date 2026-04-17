#!/usr/bin/env python3
"""Google Scholar search adapter for MSDP Protocol v1.

Reads a JSON payload from --input (or stdin) and writes an envelope-compliant
JSON response to --output (or stdout).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROTOCOL_VERSION = "1.0"
TOOL_NAME = "search.google_scholar"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
RESULT_RE = re.compile(r"<div class=\"gs_r gs_or gs_scl\".*?<\/div>\s*<\/div>", re.DOTALL)
TITLE_RE = re.compile(r"<h3 class=\"gs_rt\".*?<a href=\"([^\"]+)\"[^>]*>(.*?)<\/a>.*?<\/h3>", re.DOTALL)
TITLE_FALLBACK_RE = re.compile(r"<h3 class=\"gs_rt\"[^>]*>(.*?)<\/h3>", re.DOTALL)
META_RE = re.compile(r"<div class=\"gs_a\">(.*?)<\/div>", re.DOTALL)
SNIPPET_RE = re.compile(r"<div class=\"gs_rs\">(.*?)<\/div>", re.DOTALL)
PDF_RE = re.compile(r"<div class=\"gs_or_ggsm\">\s*<a href=\"([^\"]+)\"", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class InputPayload:
    keywords: list[str]
    year_start: int | None
    year_end: int | None
    top_k: int


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Google Scholar and return top-k candidate manuscripts")
    parser.add_argument("--input", default="-", help="Input JSON file path or '-' for stdin")
    parser.add_argument("--output", default="-", help="Output JSON file path or '-' for stdout")
    parser.add_argument("--run-id", default=None, help="Optional run UUID")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        sys.stdout.write(rendered + "\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(rendered + "\n")


def normalize_input(raw: dict[str, Any]) -> InputPayload:
    keywords = raw.get("keywords")
    year_start = raw.get("year_start")
    year_end = raw.get("year_end")
    top_k = raw.get("top_k")

    if not isinstance(keywords, list) or not keywords or any(not isinstance(k, str) or not k.strip() for k in keywords):
        raise ValueError("'keywords' must be a non-empty list of strings")
    if year_start is not None and (not isinstance(year_start, int) or year_start < 1900 or year_start > 2100):
        raise ValueError("'year_start' must be null or an integer between 1900 and 2100")
    if year_end is not None and (not isinstance(year_end, int) or year_end < 1900 or year_end > 2100):
        raise ValueError("'year_end' must be null or an integer between 1900 and 2100")
    if year_start is not None and year_end is not None and year_start > year_end:
        raise ValueError("'year_start' cannot be greater than 'year_end'")
    if not isinstance(top_k, int) or top_k < 1 or top_k > 50:
        raise ValueError("'top_k' must be an integer between 1 and 50")

    return InputPayload(keywords=[k.strip() for k in keywords], year_start=year_start, year_end=year_end, top_k=top_k)


def build_search_url(payload: InputPayload) -> str:
    query = quote_plus(" ".join(payload.keywords))
    parts = [f"https://scholar.google.com/scholar?q={query}", f"num={payload.top_k}", "hl=en"]
    if payload.year_start is not None:
        parts.append(f"as_ylo={payload.year_start}")
    if payload.year_end is not None:
        parts.append(f"as_yhi={payload.year_end}")
    return "&".join(parts)


def clean_text(value: str) -> str:
    no_tags = TAG_RE.sub(" ", value)
    unescaped = html.unescape(no_tags)
    return " ".join(unescaped.split())


def first_year(text: str) -> int | None:
    found = YEAR_RE.search(text)
    return int(found.group(0)) if found else None


def hash_candidate(title: str, source_url: str) -> str:
    blob = f"{title.strip().lower()}|{source_url.strip().lower()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


def parse_candidates(html_text: str, query: str) -> list[dict[str, Any]]:
    rows = RESULT_RE.findall(html_text)
    out: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        title_match = TITLE_RE.search(row)
        source_url = ""
        if title_match:
            source_url = html.unescape(title_match.group(1))
            title = clean_text(title_match.group(2))
        else:
            fallback = TITLE_FALLBACK_RE.search(row)
            if not fallback:
                continue
            title = clean_text(fallback.group(1))

        meta_match = META_RE.search(row)
        author_text = clean_text(meta_match.group(1)) if meta_match else ""
        authors_raw = author_text.split(" - ", 1)[0]
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        snippet_match = SNIPPET_RE.search(row)
        snippet = clean_text(snippet_match.group(1)) if snippet_match else ""

        pdf_match = PDF_RE.search(row)
        pdf_url = html.unescape(pdf_match.group(1)) if pdf_match else ""

        year = first_year(author_text)
        candidate_id = hash_candidate(title=title, source_url=source_url or pdf_url or str(idx))

        out.append(
            {
                "candidate_id": candidate_id,
                "title": title,
                "authors": authors,
                "year": year,
                "doi": None,
                "source_url": source_url or None,
                "pdf_url": pdf_url or None,
                "venue": None,
                "abstract_snippet": snippet,
                "provider": "google_scholar",
                "provider_rank": idx,
                "provider_score": None,
                "provenance": [
                    {
                        "provider": "google_scholar",
                        "query": query,
                        "fetched_at": utc_now(),
                    }
                ],
            }
        )

    return out


def make_error(code: str, message: str, retryable: bool = False, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "provider": "google_scholar",
        "context": context or {},
    }


def make_envelope(run_id: str, started_at: str, status: str, data: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, Any]:
    ended = utc_now()
    duration_ms = int(
        (
            dt.datetime.fromisoformat(ended.replace("Z", "+00:00"))
            - dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        ).total_seconds()
        * 1000
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tool": TOOL_NAME,
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "ended_at": ended,
        "duration_ms": duration_ms,
        "data": data,
        "errors": errors,
        "metrics": {"candidate_count": len(data.get("candidates", []))},
    }


def fetch_html(url: str, timeout: int) -> tuple[int, str]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:  # nosec B310
        status = resp.getcode()
        body = resp.read().decode("utf-8", errors="replace")
        return status, body


def run(args: argparse.Namespace) -> int:
    run_id = args.run_id or str(uuid.uuid4())
    started_at = utc_now()

    try:
        request = load_json(args.input)
        payload = normalize_input(request)
        url = build_search_url(payload)

        try:
            status_code, body = fetch_html(url=url, timeout=args.timeout)
        except HTTPError as exc:
            status_code = exc.code
            body = ""
        except URLError as exc:
            envelope = make_envelope(
                run_id=run_id,
                started_at=started_at,
                status="error",
                data={"candidates": []},
                errors=[make_error(code="NETWORK", message=str(exc), retryable=True)],
            )
            dump_json(args.output, envelope)
            return 30

        if status_code != 200:
            envelope = make_envelope(
                run_id=run_id,
                started_at=started_at,
                status="error",
                data={"query": " ".join(payload.keywords), "candidates": []},
                errors=[
                    make_error(
                        code="NETWORK",
                        message=f"Google Scholar returned HTTP {status_code}",
                        retryable=status_code in {429, 500, 502, 503, 504},
                        context={"url": url, "http_status": status_code},
                    )
                ],
            )
            dump_json(args.output, envelope)
            return 30

        query_text = " ".join(payload.keywords)
        candidates = parse_candidates(body, query=query_text)[: payload.top_k]

        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="ok",
            data={
                "query": query_text,
                "year_start": payload.year_start,
                "year_end": payload.year_end,
                "top_k": payload.top_k,
                "search_url": url,
                "candidates": candidates,
            },
            errors=[],
        )
        dump_json(args.output, envelope)
        return 0

    except ValueError as exc:
        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="error",
            data={"candidates": []},
            errors=[make_error(code="VALIDATION", message=str(exc), retryable=False)],
        )
        dump_json(args.output, envelope)
        return 20
    except Exception as exc:  # pylint: disable=broad-except
        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="error",
            data={"candidates": []},
            errors=[make_error(code="INTERNAL", message=str(exc), retryable=False)],
        )
        dump_json(args.output, envelope)
        return 40


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
