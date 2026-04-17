#!/usr/bin/env python3
"""Common helpers for MSDP Protocol v1 search adapters."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "1.0"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class InputPayload:
    keywords: list[str]
    year_start: int | None
    year_end: int | None
    top_k: int


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_common_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
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

    return InputPayload(
        keywords=[k.strip() for k in keywords],
        year_start=year_start,
        year_end=year_end,
        top_k=top_k,
    )


def hash_candidate(title: str, source_url: str) -> str:
    blob = f"{title.strip().lower()}|{source_url.strip().lower()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


def make_error(provider: str, code: str, message: str, retryable: bool = False, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "provider": provider,
        "context": context or {},
    }


def make_envelope(tool_name: str, run_id: str, started_at: str, status: str, data: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, Any]:
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
        "tool": tool_name,
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "ended_at": ended,
        "duration_ms": duration_ms,
        "data": data,
        "errors": errors,
        "metrics": {"candidate_count": len(data.get("candidates", []))},
    }


def fetch_json(url: str, timeout: int, query_params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    if query_params:
        url = f"{url}?{urlencode(query_params, doseq=True)}"
    req_headers = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=timeout) as resp:  # nosec B310
        status = resp.getcode()
        body = resp.read().decode("utf-8", errors="replace")
    return status, json.loads(body)


def fetch_text(url: str, timeout: int, query_params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    if query_params:
        url = f"{url}?{urlencode(query_params, doseq=True)}"
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=timeout) as resp:  # nosec B310
        status = resp.getcode()
        body = resp.read().decode("utf-8", errors="replace")
    return status, body


def next_run_id(value: str | None) -> str:
    return value or str(uuid.uuid4())


def classify_network_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}", exc.code in {429, 500, 502, 503, 504}
    if isinstance(exc, URLError):
        return str(exc), True
    return str(exc), False
