#!/usr/bin/env python3
"""Search across engines, download discovered PDFs, and parse downloaded files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "1.0"
TOOL_NAME = "tasks.search_download_and_parse"
ROOT = Path(__file__).resolve().parents[1]
SEARCH_TASK = ROOT / "tasks" / "search_papers.py"
DOWNLOAD_TOOL = ROOT / "tools" / "pdf_download_tool.py"
PARSE_TOOL = ROOT / "tools" / "pdf_parse_tool.py"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search papers, download PDFs, and parse downloaded files")
    parser.add_argument("--keywords", nargs="+", required=True, help="Search keywords")
    parser.add_argument("--year-start", type=int, default=None, help="Inclusive lower year bound")
    parser.add_argument("--year-end", type=int, default=None, help="Inclusive upper year bound")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k results per engine (1..50)")
    parser.add_argument("--engines", nargs="+", default=None, help="Subset of engines to run")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout for search engines and downloads")
    parser.add_argument("--download-dir", default="artifacts/pdfs", help="Directory where PDFs are saved")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages parsed per PDF (1..50)")
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
            "candidate_count": len(data.get("search", {}).get("candidates", [])),
            "download_success_count": data.get("download_summary", {}).get("success_count", 0),
            "download_failure_count": data.get("download_summary", {}).get("failure_count", 0),
            "parse_success_count": data.get("parse_summary", {}).get("success_count", 0),
            "parse_failure_count": data.get("parse_summary", {}).get("failure_count", 0),
            "parse_skipped_count": data.get("parse_summary", {}).get("skipped_count", 0),
        },
    }


def write_output(path: str, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        sys.stdout.write(rendered + "\n")
    else:
        Path(path).write_text(rendered + "\n", encoding="utf-8")


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


def run_download_tool(candidates: list[dict[str, Any]], args: argparse.Namespace) -> tuple[int, dict[str, Any] | None, str, int]:
    with tempfile.TemporaryDirectory() as td:
        input_file = Path(td) / "download_input.json"
        output_file = Path(td) / "download_output.json"
        request_payload = {"items": candidates, "download_dir": args.download_dir}
        input_file.write_text(json.dumps(request_payload), encoding="utf-8")
        cmd = [
            sys.executable,
            str(DOWNLOAD_TOOL),
            "--input",
            str(input_file),
            "--output",
            str(output_file),
            "--timeout",
            str(args.timeout),
        ]
        started = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration_ms = int((time.monotonic() - started) * 1000)
        payload = None
        if output_file.exists():
            try:
                payload = json.loads(output_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
        return proc.returncode, payload, proc.stderr.strip(), duration_ms


def run_parse_tool(pdf_path: str, args: argparse.Namespace) -> tuple[int, dict[str, Any] | None, str, int]:
    with tempfile.TemporaryDirectory() as td:
        output_file = Path(td) / "parse_output.json"
        cmd = [
            sys.executable,
            str(PARSE_TOOL),
            "--input-pdf",
            pdf_path,
            "--max-pages",
            str(args.max_pages),
            "--output",
            str(output_file),
        ]
        started = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration_ms = int((time.monotonic() - started) * 1000)
        payload = None
        if output_file.exists():
            try:
                payload = json.loads(output_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
        return proc.returncode, payload, proc.stderr.strip(), duration_ms


def execute(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s | %(levelname)s | %(message)s")

    started_at = utc_now()
    run_id = args.run_id or str(uuid.uuid4())
    errors: list[dict[str, Any]] = []

    if args.max_pages < 1 or args.max_pages > 50:
        errors.append({"code": "VALIDATION", "message": "'--max-pages' must be between 1 and 50", "provider": "search_download_and_parse", "retryable": False, "context": {}})
        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="error",
            data={"search": {}, "downloaded": [], "failed": [], "download_summary": {}, "parsed": [], "parse_summary": {}},
            errors=errors,
        )
        write_output(args.output, envelope)
        return 20

    logging.info("Starting search, download, and parse run_id=%s", run_id)
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
            data={"search": {}, "downloaded": [], "failed": [], "download_summary": {}, "parsed": [], "parse_summary": {}},
            errors=errors,
        )
        write_output(args.output, envelope)
        return 30

    candidates = search_payload.get("data", {}).get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    d_rc, download_payload, download_stderr, download_ms = run_download_tool(candidates, args)
    logging.info("Download step completed in %d ms (rc=%d)", download_ms, d_rc)

    if download_stderr:
        logging.warning("Download tool stderr: %s", download_stderr)

    if download_payload is None:
        errors.append({"code": "DOWNLOAD_PARSE", "message": "Could not parse download output", "provider": "pdf_download_tool", "retryable": False, "context": {}})
        download_data = {"downloaded": [], "failed": [], "download_summary": {}}
    else:
        download_data = download_payload.get("data", {})

    downloaded = download_data.get("downloaded", []) if isinstance(download_data.get("downloaded"), list) else []
    failed = download_data.get("failed", []) if isinstance(download_data.get("failed"), list) else []
    summary = dict(download_data.get("download_summary", {}) if isinstance(download_data.get("download_summary"), dict) else {})
    summary["search_duration_ms"] = search_ms
    summary["download_duration_ms"] = download_ms
    summary["total_candidates"] = len(candidates)

    parsed_results: list[dict[str, Any]] = []
    parse_success = 0
    parse_failure = 0
    parse_skipped = 0
    parse_duration_total = 0

    for item in downloaded:
        if not isinstance(item, dict):
            parse_skipped += 1
            parsed_results.append({"status": "skipped", "reason": "Invalid download item format", "parsed": None, "errors": []})
            continue

        pdf_path = item.get("path")
        title = item.get("title")
        if not pdf_path:
            parse_skipped += 1
            parsed_results.append({"title": title, "input_pdf": None, "status": "skipped", "reason": "Missing local PDF path", "parsed": None, "errors": []})
            continue

        p_rc, parse_payload, parse_stderr, parse_ms = run_parse_tool(str(pdf_path), args)
        parse_duration_total += parse_ms
        if parse_stderr:
            logging.warning("Parse tool stderr for '%s': %s", title, parse_stderr)

        if parse_payload is None:
            parse_failure += 1
            err = {"code": "PARSE_OUTPUT_INVALID", "message": "Could not parse parser output", "provider": "pdf_parse_tool", "retryable": False, "context": {"pdf_path": str(pdf_path)}}
            errors.append(err)
            parsed_results.append({"title": title, "input_pdf": str(pdf_path), "status": "error", "parse_run_id": None, "parse_duration_ms": parse_ms, "parsed": None, "errors": [err]})
            continue

        parse_errors = parse_payload.get("errors", []) if isinstance(parse_payload.get("errors"), list) else []
        parse_status = parse_payload.get("status")
        if p_rc == 0 and parse_status == "ok":
            parse_success += 1
            item_status = "ok"
        else:
            parse_failure += 1
            item_status = "error"
            if p_rc not in {0, 10, 20, 30, 40}:
                parse_errors = parse_errors + [{"code": "PARSE_FAILED", "message": f"pdf_parse_tool exited with {p_rc}", "provider": "pdf_parse_tool", "retryable": False, "context": {"return_code": p_rc, "pdf_path": str(pdf_path)}}]

        parsed_results.append(
            {
                "title": title,
                "input_pdf": str(pdf_path),
                "status": item_status,
                "parse_run_id": parse_payload.get("run_id"),
                "parse_duration_ms": parse_ms,
                "parsed": parse_payload.get("data", {}).get("parsed"),
                "errors": parse_errors,
            }
        )

        if parse_errors:
            errors.extend(parse_errors)

    parse_summary = {
        "success_count": parse_success,
        "failure_count": parse_failure,
        "skipped_count": parse_skipped,
        "total_downloaded": len(downloaded),
        "parse_duration_ms": parse_duration_total,
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
        "parsed": parsed_results,
        "parse_summary": parse_summary,
    }

    if rc not in {0, 10}:
        errors.extend(search_payload.get("errors", []))
        errors.append({"code": "SEARCH_FAILED", "message": f"search_papers exited with {rc}", "provider": "search_papers", "retryable": False, "context": {"return_code": rc}})
        status = "error"
    else:
        if rc == 10:
            errors.extend(search_payload.get("errors", []))
        if download_payload and isinstance(download_payload.get("errors"), list):
            errors.extend(download_payload.get("errors", []))
        if d_rc not in {0, 10}:
            errors.append({"code": "DOWNLOAD_FAILED", "message": f"pdf_download_tool exited with {d_rc}", "provider": "pdf_download_tool", "retryable": False, "context": {"return_code": d_rc}})
            status = "error"
        elif parse_failure > 0:
            status = "ok"
        else:
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
