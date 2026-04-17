#!/usr/bin/env python3
"""Aggregate MSDP search tools and emit a deduplicated Protocol v1 envelope."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "1.0"
TOOL_NAME = "tasks.search_papers"
ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"

ENGINE_TO_SCRIPT = {
    "google_scholar": "google_scholar_search.py",
    "arxiv": "arxiv_search.py",
    "semantic_scholar": "semantic_scholar_search.py",
    "crossref": "crossref_search.py",
    "openalex": "openalex_search.py",
    "pubmed": "pubmed_search.py",
    "europe_pmc": "europe_pmc_search.py",
    "dblp": "dblp_search.py",
    "doaj": "doaj_search.py",
    "biorxiv": "biorxiv_search.py",
}
DEFAULT_ENGINES = list(ENGINE_TO_SCRIPT.keys())


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multiple MSDP paper search tools and deduplicate results")
    parser.add_argument("--keywords", nargs="+", required=True, help="Search keywords")
    parser.add_argument("--year-start", type=int, default=None, help="Inclusive lower year bound")
    parser.add_argument("--year-end", type=int, default=None, help="Inclusive upper year bound")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k results per engine (1..50)")
    parser.add_argument("--engines", nargs="+", default=DEFAULT_ENGINES, help="Engines to run")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout passed to each engine")
    parser.add_argument("--run-id", default=None, help="Optional run UUID")
    parser.add_argument("--output", default="-", help="Output JSON path or '-' for stdout")
    return parser.parse_args()


def normalize_input(args: argparse.Namespace) -> dict[str, Any]:
    keywords = [k.strip() for k in args.keywords if k and k.strip()]
    if not keywords:
        raise ValueError("'--keywords' must include at least one non-empty value")
    if args.year_start is not None and (args.year_start < 1900 or args.year_start > 2100):
        raise ValueError("'--year-start' must be between 1900 and 2100")
    if args.year_end is not None and (args.year_end < 1900 or args.year_end > 2100):
        raise ValueError("'--year-end' must be between 1900 and 2100")
    if args.year_start is not None and args.year_end is not None and args.year_start > args.year_end:
        raise ValueError("'--year-start' cannot be greater than '--year-end'")
    if args.top_k < 1 or args.top_k > 50:
        raise ValueError("'--top-k' must be between 1 and 50")

    invalid = [e for e in args.engines if e not in ENGINE_TO_SCRIPT]
    if invalid:
        raise ValueError(f"Unsupported engines: {', '.join(invalid)}")

    # Keep stable ordering while removing duplicates.
    seen: set[str] = set()
    engines: list[str] = []
    for eng in args.engines:
        if eng not in seen:
            seen.add(eng)
            engines.append(eng)

    return {
        "keywords": keywords,
        "year_start": args.year_start,
        "year_end": args.year_end,
        "top_k": args.top_k,
        "engines": engines,
    }


def hash_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def normalize_title(title: str | None) -> str:
    return " ".join((title or "").lower().split())


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi_norm = doi.lower().strip()
    return doi_norm.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip().rstrip("/")
    return cleaned.lower() if cleaned else None


def dedup_key(candidate: dict[str, Any]) -> str:
    doi = normalize_doi(candidate.get("doi"))
    if doi:
        return f"doi:{doi}"
    source_url = normalize_url(candidate.get("source_url"))
    if source_url:
        return f"url:{source_url}"
    title = normalize_title(candidate.get("title"))
    year = candidate.get("year")
    return f"title:{title}|year:{year}"


def merge_candidates(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)

    for field in ["doi", "source_url", "pdf_url", "venue", "abstract_snippet"]:
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]

    if not merged.get("year") and incoming.get("year"):
        merged["year"] = incoming["year"]

    authors = list(dict.fromkeys((merged.get("authors") or []) + (incoming.get("authors") or [])))
    merged["authors"] = authors

    provenance = (merged.get("provenance") or []) + (incoming.get("provenance") or [])
    dedup_prov: list[dict[str, Any]] = []
    prov_seen: set[str] = set()
    for p in provenance:
        key = json.dumps(p, sort_keys=True)
        if key not in prov_seen:
            prov_seen.add(key)
            dedup_prov.append(p)
    merged["provenance"] = dedup_prov

    rank_existing = merged.get("provider_rank")
    rank_incoming = incoming.get("provider_rank")
    if isinstance(rank_existing, int) and isinstance(rank_incoming, int):
        merged["provider_rank"] = min(rank_existing, rank_incoming)

    providers = set()
    for p in merged["provenance"]:
        provider = p.get("provider")
        if provider:
            providers.add(provider)
    merged["provider"] = ",".join(sorted(providers)) if providers else merged.get("provider")

    merged["candidate_id"] = hash_identity(dedup_key(merged))
    return merged


def run_engine(script_name: str, payload: dict[str, Any], timeout: int) -> tuple[int, dict[str, Any] | None, str]:
    script_path = TOOLS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "input.json"
        out = Path(td) / "output.json"
        inp.write_text(json.dumps(payload), encoding="utf-8")

        cmd = [
            sys.executable,
            str(script_path),
            "--input",
            str(inp),
            "--output",
            str(out),
            "--timeout",
            str(timeout),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        parsed: dict[str, Any] | None = None
        if out.exists():
            try:
                parsed = json.loads(out.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                parsed = None

        return proc.returncode, parsed, proc.stderr.strip()


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
            "candidate_count": len(data.get("candidates", [])),
            "engine_count": len(data.get("engine_results", [])),
            "success_engine_count": sum(1 for e in data.get("engine_results", []) if e.get("status") == "ok"),
        },
    }


def write_output(path: str, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if path == "-":
        sys.stdout.write(rendered + "\n")
    else:
        Path(path).write_text(rendered + "\n", encoding="utf-8")


def execute(args: argparse.Namespace) -> int:
    started_at = utc_now()
    run_id = args.run_id or str(uuid.uuid4())

    try:
        request = normalize_input(args)
    except ValueError as exc:
        envelope = make_envelope(
            run_id=run_id,
            started_at=started_at,
            status="error",
            data={"candidates": [], "engine_results": []},
            errors=[
                {
                    "code": "VALIDATION",
                    "message": str(exc),
                    "retryable": False,
                    "provider": "search_papers_task",
                    "context": {},
                }
            ],
        )
        write_output(args.output, envelope)
        return 20

    base_payload = {
        "keywords": request["keywords"],
        "year_start": request["year_start"],
        "year_end": request["year_end"],
        "top_k": request["top_k"],
    }

    engine_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    aggregated: dict[str, dict[str, Any]] = {}

    for engine in request["engines"]:
        rc, response, stderr = run_engine(ENGINE_TO_SCRIPT[engine], base_payload, args.timeout)

        if rc == 0 and response and response.get("status") == "ok":
            candidates = response.get("data", {}).get("candidates", [])
            if not isinstance(candidates, list):
                candidates = []

            for cand in candidates:
                key = dedup_key(cand)
                if key in aggregated:
                    aggregated[key] = merge_candidates(aggregated[key], cand)
                else:
                    normalized = dict(cand)
                    normalized["candidate_id"] = hash_identity(key)
                    aggregated[key] = normalized

            engine_results.append(
                {
                    "engine": engine,
                    "tool": response.get("tool"),
                    "status": "ok",
                    "candidate_count": len(candidates),
                    "run_id": response.get("run_id"),
                }
            )
            continue

        err_list = response.get("errors", []) if response else []
        errors.extend(err_list if isinstance(err_list, list) else [])
        if stderr:
            errors.append(
                {
                    "code": "INTERNAL",
                    "message": stderr,
                    "retryable": False,
                    "provider": engine,
                    "context": {},
                }
            )
        engine_results.append(
            {
                "engine": engine,
                "tool": response.get("tool") if response else ENGINE_TO_SCRIPT[engine],
                "status": "error",
                "return_code": rc,
                "run_id": response.get("run_id") if response else None,
            }
        )

    deduped_candidates = sorted(
        aggregated.values(),
        key=lambda c: (c.get("provider_rank") if isinstance(c.get("provider_rank"), int) else 10_000, c.get("title") or ""),
    )

    data = {
        "query": " ".join(request["keywords"]),
        "keywords": request["keywords"],
        "year_start": request["year_start"],
        "year_end": request["year_end"],
        "top_k": request["top_k"],
        "engines": request["engines"],
        "engine_results": engine_results,
        "candidates": deduped_candidates,
    }

    status = "ok" if any(e.get("status") == "ok" for e in engine_results) else "error"
    envelope = make_envelope(run_id=run_id, started_at=started_at, status=status, data=data, errors=errors)
    write_output(args.output, envelope)

    if status == "ok" and errors:
        return 10
    if status == "ok":
        return 0
    return 30


def main() -> int:
    return execute(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
