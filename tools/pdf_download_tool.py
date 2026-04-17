#!/usr/bin/env python3
"""Download PDFs from direct links or by resolving landing pages."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import time
import uuid
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "1.0"
TOOL_NAME = "tools.pdf_download"
UA = "msdp-pdf-download/1.0"
PDF_MAGIC = b"%PDF"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download PDFs from URL candidates")
    parser.add_argument("--input", default="-", help="Input JSON file path or '-' for stdin")
    parser.add_argument("--output", default="-", help="Output JSON file path or '-' for stdout")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    parser.add_argument("--run-id", default=None, help="Optional run UUID")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(__import__("sys").stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path: str, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        __import__("sys").stdout.write(rendered + "\n")
        return
    Path(path).write_text(rendered + "\n", encoding="utf-8")


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip().lower())
    return cleaned.strip("_.")[:120] or "paper"


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
        "metrics": {
            "download_success_count": data.get("download_summary", {}).get("success_count", 0),
            "download_failure_count": data.get("download_summary", {}).get("failure_count", 0),
            "candidate_count": len(data.get("attempted", [])),
        },
    }


def error_dict(code: str, message: str, retryable: bool, context: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "message": message, "retryable": retryable, "provider": "pdf_download", "context": context}


def request_url(url: str, timeout: int, accept: str) -> tuple[int, bytes, str | None, str]:
    req = Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urlopen(req, timeout=timeout) as response:  # nosec B310
        status = response.getcode() or 0
        body = response.read()
        content_type = response.headers.get("Content-Type")
        final_url = response.geturl()
    return status, body, content_type, final_url


def extract_pdf_links(html: str, base_url: str) -> list[str]:
    patterns = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<a[^>]+href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',
        r'<a[^>]+href=["\']([^"\']*(?:download|fulltext|pdf)[^"\']*)["\']',
    ]
    found: list[str] = []
    for pat in patterns:
        for match in re.findall(pat, html, flags=re.IGNORECASE):
            candidate = unescape(match).strip()
            if not candidate:
                continue
            found.append(urljoin(base_url, candidate))

    # keep order, remove duplicates and obvious non-http schemes
    seen: set[str] = set()
    urls: list[str] = []
    for raw in found:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            continue
        if raw not in seen:
            seen.add(raw)
            urls.append(raw)
    return urls[:8]


def is_pdf_response(content_type: str | None, body: bytes, url: str) -> bool:
    ctype = (content_type or "").lower()
    if "application/pdf" in ctype:
        return True
    if body.startswith(PDF_MAGIC):
        return True
    return url.lower().split("?", 1)[0].endswith(".pdf") and body[:1] == b"%"


def try_download_once(url: str, timeout: int) -> tuple[bool, bytes | None, str | None, str, list[str]]:
    trace: list[str] = []
    status, body, content_type, final_url = request_url(url, timeout, "application/pdf,text/html,*/*")
    trace.append(f"fetch:{final_url} status={status} type={content_type}")
    if status >= 400:
        return False, None, f"HTTP {status}", final_url, trace
    if not body:
        return False, None, "Empty response body", final_url, trace

    if is_pdf_response(content_type, body, final_url):
        return True, body, None, final_url, trace

    # landing page -> attempt to resolve PDF links
    text = body.decode("utf-8", errors="replace")
    pdf_links = extract_pdf_links(text, final_url)
    if not pdf_links:
        return False, None, "No PDF link found in landing page", final_url, trace

    for candidate in pdf_links:
        try:
            c_status, c_body, c_type, c_final = request_url(candidate, timeout, "application/pdf,*/*")
            trace.append(f"explore:{candidate} -> {c_final} status={c_status} type={c_type}")
            if c_status >= 400:
                continue
            if c_body and is_pdf_response(c_type, c_body, c_final):
                return True, c_body, None, c_final, trace
        except HTTPError as exc:
            trace.append(f"explore:{candidate} http_error={exc.code}")
        except URLError as exc:
            trace.append(f"explore:{candidate} url_error={exc.reason}")
        except Exception as exc:  # noqa: BLE001
            trace.append(f"explore:{candidate} error={exc}")

    return False, None, "Discovered links did not return PDF content", final_url, trace


def download_item(item: dict[str, Any], idx: int, download_dir: Path, timeout: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    title = (item.get("title") or f"paper_{idx}").strip()
    source_url = item.get("pdf_url") or item.get("source_url")
    if not source_url:
        return None, {"title": title, "url": None, "reason": "Missing source URL", "duration_ms": 0}

    target = download_dir / f"{idx:03d}_{sanitize_filename(title)}.pdf"
    started = time.monotonic()
    attempts = 2
    traces: list[str] = []
    reason = "Unknown error"

    for attempt in range(1, attempts + 1):
        try:
            ok, body, err, resolved_url, trace = try_download_once(str(source_url), timeout)
            traces.extend([f"attempt={attempt} {line}" for line in trace])
            if ok and body:
                target.write_bytes(body)
                elapsed_ms = int((time.monotonic() - started) * 1000)
                return {
                    "title": title,
                    "url": source_url,
                    "resolved_url": resolved_url,
                    "path": str(target),
                    "bytes": len(body),
                    "attempt_count": attempt,
                    "duration_ms": elapsed_ms,
                }, None
            reason = err or reason
        except HTTPError as exc:
            reason = f"HTTP {exc.code}"
            traces.append(f"attempt={attempt} http_error={exc.code}")
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except URLError as exc:
            reason = f"URL error: {exc.reason}"
            traces.append(f"attempt={attempt} url_error={exc.reason}")
        except OSError as exc:
            reason = f"File error: {exc}"
            traces.append(f"attempt={attempt} file_error={exc}")
            break
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            traces.append(f"attempt={attempt} error={exc}")
            break

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return None, {"title": title, "url": source_url, "reason": reason, "duration_ms": elapsed_ms, "trace": traces}


def execute(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s | %(levelname)s | %(message)s")
    started_at = utc_now()
    run_id = args.run_id or str(uuid.uuid4())

    try:
        payload = load_json(args.input)
    except Exception as exc:  # noqa: BLE001
        envelope = make_envelope(
            run_id,
            started_at,
            "error",
            {"attempted": [], "downloaded": [], "failed": [], "download_summary": {}},
            [error_dict("VALIDATION", f"Invalid input JSON: {exc}", False, {})],
        )
        dump_json(args.output, envelope)
        return 20

    items = payload.get("items", [])
    download_dir_value = payload.get("download_dir", "artifacts/pdfs")
    if not isinstance(items, list):
        items = []

    download_dir = Path(download_dir_value)
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        envelope = make_envelope(
            run_id,
            started_at,
            "error",
            {"attempted": [], "downloaded": [], "failed": [], "download_summary": {}},
            [error_dict("INTERNAL", f"Unable to create download directory: {exc}", False, {"download_dir": str(download_dir)})],
        )
        dump_json(args.output, envelope)
        return 40

    downloaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            failed.append({"title": f"paper_{idx}", "url": None, "reason": "Invalid candidate format", "duration_ms": 0})
            continue
        success, failure = download_item(item, idx, download_dir, args.timeout)
        if success:
            downloaded.append(success)
        elif failure:
            failed.append(failure)

    success_titles = [d["title"] for d in downloaded]
    failed_titles = [f["title"] for f in failed]
    data = {
        "attempted": items,
        "downloaded": downloaded,
        "failed": failed,
        "download_summary": {
            "success_count": len(downloaded),
            "failure_count": len(failed),
            "success_titles": success_titles,
            "failed_titles": failed_titles,
        },
    }

    errors: list[dict[str, Any]] = []
    if failed:
        errors.append(error_dict("PARTIAL_DOWNLOAD_FAILURE", "Some downloads failed", True, {"failure_count": len(failed)}))

    status = "ok"
    envelope = make_envelope(run_id, started_at, status, data, errors)
    dump_json(args.output, envelope)
    return 10 if failed else 0


def main() -> int:
    return execute(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
