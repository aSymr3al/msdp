# PDF Parse Tool I/O Standard (MSDP Protocol v1)

This document defines the input/output contract for:
`tools/pdf_parse_tool.py`.

## 1) Tool Identity
- **Tool name**: `parse.pdf_key_info`
- **Language**: Python 3.x
- **Invocation style**: CLI with direct PDF input and JSON output

## 2) CLI Contract
```bash
python3 tools/pdf_parse_tool.py \
  --input-pdf <path/to/file.pdf> \
  --output <json file | -> \
  [--run-id <uuid>] \
  [--max-pages <1..50>]
```

### Exit Codes
- `0`: success
- `20`: validation error (bad path, wrong extension, invalid max-pages)
- `30`: provider/network failure (reserved if future parser uses remote APIs)
- `40`: parse/internal failure

## 3) Input Standard
- `input_pdf` (required): existing path ending in `.pdf`.
- `max_pages` (optional): integer in `[1, 50]`, default `5`.

## 4) Output Standard
Output uses shared Protocol v1 envelope with parser payload:

```json
{
  "protocol_version": "1.0",
  "tool": "parse.pdf_key_info",
  "run_id": "uuid",
  "status": "ok",
  "data": {
    "parsed": {
      "input_pdf": "artifacts/raw/example.pdf",
      "title": "...",
      "doi": "10.xxxx/xxxx",
      "year": 2024,
      "abstract": "...",
      "contact_emails": ["author@example.edu"],
      "detected_sections": ["abstract", "introduction", "methods", "results", "conclusion"],
      "text_preview": "..."
    }
  },
  "errors": [],
  "metrics": {
    "parsed_fields_count": 7,
    "text_chars": 14567
  }
}
```

## 5) Error Handling Standard
Errors are envelope `errors[]` items with:
- `VALIDATION`: input path/format/page-range issues,
- `PARSE`: empty text extraction, missing parser dependency, malformed PDF,
- `INTERNAL`: unexpected runtime faults.

## 6) Planned Extraction Heuristics
- Title: first plausible heading line.
- DOI: regex-based (`10.xxxx/...`).
- Year: latest plausible year in extracted text.
- Abstract: text block after `Abstract` until next major heading.
- Contacts: email regex extraction.
- Sections: keyword detection (introduction, methods, results, conclusion, etc.).
