#!/usr/bin/env python3
"""PDF parser adapter for extracting key manuscript information (MSDP Protocol v1)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common_search_tool import (
    classify_network_error,
    dump_json,
    make_envelope,
    make_error,
    next_run_id,
    utc_now,
)

TOOL_NAME = "parse.pdf_key_info"
PROVIDER = "pdf_parser"
MAX_TEXT_LEN = 40000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse one academic PDF and extract important manuscript information")
    parser.add_argument("--input-pdf", required=True, help="Path to input PDF file")
    parser.add_argument("--output", default="-", help="Output JSON file path or '-' for stdout")
    parser.add_argument("--run-id", default=None, help="Optional run UUID")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages to parse for key metadata")
    return parser.parse_args()


def extract_text_from_pdf(pdf_path: Path, max_pages: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Missing dependency 'pypdf'. Install with: pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    snippets: list[str] = []
    for page in reader.pages[:max_pages]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            snippets.append(page_text)
    return "\n".join(snippets)


def compact_text(value: str, limit: int = 1200) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit].strip()


def find_title(text: str) -> str | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    # Prefer first line with enough alphabetic content and acceptable length.
    for line in lines[:15]:
        if 15 <= len(line) <= 220 and sum(ch.isalpha() for ch in line) >= 8:
            return line
    return lines[0][:220]


def find_abstract(text: str) -> str | None:
    match = re.search(r"\babstract\b\s*[:\-]?\s*(.+?)(?:\n\s*\n|\n\s*(?:1\.?\s+)?introduction\b)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return compact_text(match.group(1), limit=2000) or None


def find_doi(text: str) -> str | None:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, flags=re.IGNORECASE)
    return match.group(0).rstrip(".,;") if match else None


def find_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if not years:
        return None
    # Prefer the most recent plausible publication year in text.
    plausible = [y for y in years if 1900 <= y <= 2100]
    return max(plausible) if plausible else None


def find_emails(text: str) -> list[str]:
    emails = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    dedup: list[str] = []
    seen: set[str] = set()
    for email in emails:
        lowered = email.lower()
        if lowered not in seen:
            seen.add(lowered)
            dedup.append(email)
    return dedup[:10]


def detect_sections(text: str) -> list[str]:
    section_names = [
        "abstract",
        "introduction",
        "related work",
        "method",
        "methods",
        "experiments",
        "results",
        "discussion",
        "conclusion",
        "references",
    ]
    found = [name for name in section_names if re.search(rf"\b{name}\b", text, flags=re.IGNORECASE)]
    return found


def parse_pdf_text(text: str, pdf_path: str) -> dict:
    bounded = text[:MAX_TEXT_LEN]
    return {
        "input_pdf": pdf_path,
        "title": find_title(bounded),
        "doi": find_doi(bounded),
        "year": find_year(bounded),
        "abstract": find_abstract(bounded),
        "contact_emails": find_emails(bounded),
        "detected_sections": detect_sections(bounded),
        "text_preview": compact_text(bounded, limit=600),
    }


def run(args: argparse.Namespace) -> int:
    run_id = next_run_id(args.run_id)
    started_at = utc_now()

    try:
        pdf_path = Path(args.input_pdf)
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError("'input_pdf' must point to a .pdf file")
        if not pdf_path.exists():
            raise ValueError(f"PDF file not found: {pdf_path}")
        if args.max_pages < 1 or args.max_pages > 50:
            raise ValueError("'max_pages' must be between 1 and 50")

        raw_text = extract_text_from_pdf(pdf_path, max_pages=args.max_pages)
        if not raw_text.strip():
            envelope = make_envelope(
                TOOL_NAME,
                run_id,
                started_at,
                "error",
                {"parsed": None},
                [make_error(PROVIDER, "PARSE", "No extractable text found in PDF", retryable=False)],
            )
            dump_json(args.output, envelope)
            return 40

        parsed = parse_pdf_text(raw_text, str(pdf_path))
        envelope = make_envelope(
            TOOL_NAME,
            run_id,
            started_at,
            "ok",
            {"parsed": parsed},
            [],
        )
        envelope["metrics"].update(
            {
                "parsed_fields_count": sum(1 for value in parsed.values() if value not in (None, [], "")),
                "text_chars": len(raw_text),
            }
        )
        dump_json(args.output, envelope)
        return 0

    except ValueError as exc:
        dump_json(
            args.output,
            make_envelope(
                TOOL_NAME,
                run_id,
                started_at,
                "error",
                {"parsed": None},
                [make_error(PROVIDER, "VALIDATION", str(exc), retryable=False)],
            ),
        )
        return 20
    except Exception as exc:  # pylint: disable=broad-except
        message, retryable = classify_network_error(exc)
        code = "PARSE" if not retryable else "NETWORK"
        exit_code = 30 if code == "NETWORK" else 40
        dump_json(
            args.output,
            make_envelope(
                TOOL_NAME,
                run_id,
                started_at,
                "error",
                {"parsed": None},
                [make_error(PROVIDER, code, message, retryable=retryable)],
            ),
        )
        return exit_code


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
