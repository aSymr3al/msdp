#!/usr/bin/env python3
"""Search across multiple engines and download discovered PDFs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "1.0"
TOOL_NAME = "tasks.search_and_download"
ROOT = Path(__file__).resolve().parents[1]
SEARCH_TASK = ROOT / "tasks" / "search_papers.py"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search papers across engines and download available PDFs")
    parser.add_argument("--keywords", nargs="+", required=True, help="Search keywords")
    parser.add_argument("--year-start", type=int, default=None, help="Inclusive lower year bound")
    parser.add_argument("--year-end", type=int, default=None, help="Inclusive upper year bound")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k results per engine (1..50)")
    parser.add_argument("--engines", nargs="+", default=None, help="Subset of engines to run")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout for search engines and downloads")
    parser.add_argument("--download-dir", default="artifacts/pdfs", help="Directory where PDFs are saved")
    parser.add_argument("--output", default="-", help="Output JSON path or '-' for stdout")
    parser.add_argument("--run-id", default=None, help="Optional run UUID")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity")
    return parser.parse_args()


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
            "candidate_count": len(data.get("search", {}).get("candidates", [])),
        },
    }


def write_output(path: str, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        sys.stdout.write(rendered + "\n")
    else:
        Path(path).write_text(rendered + "\n", encoding="utf-8")


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower())
    return cleaned.strip("_.")[:120] or "paper"


def build_search_command(args: argparse.Namespace, output_file: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(SEARCH_TASK),
        "--keywords",
        *args.keywords,
        "--top-k",
        str(args.top_k),
        "--timeout",
        str(args.timeout),
        "--output",
        str(output_file),
    ]
    if args.year_start is not None:
        cmd.extend(["--year-start", str(args.year_start)])
    if args.year_end is not None:
        cmd.extend(["--year-end", str(args.year_end)])
    if args.engines:
        cmd.extend(["--engines", *args.engines])
    return cmd


def run_search(args: argparse.Namespace) -> tuple[int, dict[str, Any] | None, str, int]:
    with tempfile.TemporaryDirectory() as td:
        output_file = Path(td) / "search_output.json"
        cmd = build_search_command(args, output_file)
        started = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration_ms = int((time.monotonic() - started) * 1000)
        payload = None
        if output_file.exists():
            try:
                payload = json.loads(output_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
        stderr = proc.stderr.strip()
        return proc.returncode, payload, stderr, duration_ms


def download_pdf(url: str, destination: Path, timeout: int) -> tuple[bool, str | None, int]:
    req = Request(url, headers={"User-Agent": "msdp-search-and-download/1.0", "Accept": "application/pdf,*/*"})
    started = time.monotonic()
    try:
        with urlopen(req, timeout=timeout) as response:  # nosec B310
            status = response.getcode() or 0
            if status >= 400:
                return False, f"HTTP {status}", int((time.monotonic() - started) * 1000)
            content = response.read()
            if not content:
                return False, "Empty response body", int((time.monotonic() - started) * 1000)
            destination.write_bytes(content)
            return True, None, int((time.monotonic() - started) * 1000)
    except HTTPError as exc:
        return False, f"HTTP {exc.code}", int((time.monotonic() - started) * 1000)
    except URLError as exc:
        return False, f"URL error: {exc.reason}", int((time.monotonic() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), int((time.monotonic() - started) * 1000)


def execute(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s | %(levelname)s | %(message)s")

    started_at = utc_now()
    run_id = args.run_id or str(uuid.uuid4())
    errors: list[dict[str, Any]] = []

    logging.info("Starting search and download run_id=%s", run_id)
    rc, search_payload, search_stderr, search_ms = run_search(args)
    logging.info("Search step completed in %d ms (rc=%d)", search_ms, rc)

    if search_stderr:
        logging.warning("Search task stderr: %s", search_stderr)

    if search_payload is None:
        errors.append({"code": "SEARCH_PARSE", "message": "Could not parse search output", "provider": "search_papers", "retryable": False, "context": {}})
        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="error",
            data={"search": {}, "downloaded": [], "failed": [], "download_summary": {}},
            errors=errors,
        )
        write_output(args.output, envelope)
        return 30

    candidates = search_payload.get("data", {}).get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for idx, candidate in enumerate(candidates, start=1):
        title = (candidate.get("title") or f"paper_{idx}").strip()
        pdf_url = candidate.get("pdf_url")

        if not pdf_url:
            failed.append({"title": title, "url": None, "reason": "Missing pdf_url"})
            logging.info("Skip download (missing pdf_url): %s", title)
            continue

        file_stem = sanitize_filename(title)
        target = download_dir / f"{idx:03d}_{file_stem}.pdf"

        ok, reason, elapsed_ms = download_pdf(str(pdf_url), target, args.timeout)
        if ok:
            downloaded.append({"title": title, "url": pdf_url, "path": str(target), "duration_ms": elapsed_ms})
            logging.info("Downloaded '%s' in %d ms -> %s", title, elapsed_ms, target)
        else:
            failed.append({"title": title, "url": pdf_url, "reason": reason or "Unknown error", "duration_ms": elapsed_ms})
            logging.warning("Failed '%s' in %d ms: %s", title, elapsed_ms, reason)

    success_titles = [d["title"] for d in downloaded]
    failed_titles = [f["title"] for f in failed]
    logging.info("Download summary: successful=%d failed=%d", len(downloaded), len(failed))
    logging.info("Successfully downloaded titles: %s", success_titles)
    logging.info("Failed titles: %s", failed_titles)

    summary = {
        "success_count": len(downloaded),
        "failure_count": len(failed),
        "success_titles": success_titles,
        "failed_titles": failed_titles,
        "search_duration_ms": search_ms,
        "total_candidates": len(candidates),
    }

    data = {
        "search": {
            "status": search_payload.get("status"),
            "run_id": search_payload.get("run_id"),
            "candidates": candidates,
            "engine_results": search_payload.get("data", {}).get("engine_results", []),
        },
        "downloaded": downloaded,
        "failed": failed,
        "download_summary": summary,
    }

    if rc not in {0, 10}:
        errors.extend(search_payload.get("errors", []))
        errors.append({"code": "SEARCH_FAILED", "message": f"search_papers exited with {rc}", "provider": "search_papers", "retryable": False, "context": {"return_code": rc}})
        status = "error"
    else:
        if rc == 10:
            errors.extend(search_payload.get("errors", []))
        status = "ok"

    envelope = make_envelope(run_id=run_id, started_at=started_at, status=status, data=data, errors=errors)
    write_output(args.output, envelope)

    if status == "error":
        return 30
    if errors:
        return 10
    return 0


def main() -> int:
    return execute(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
