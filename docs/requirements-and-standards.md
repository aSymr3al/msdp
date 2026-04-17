# MSDP Requirements, Interfaces, and Protocol Standards

## 1) Purpose and Scope
MSDP (Manuscript Search, Download, and Parse) is a modular toolkit that coordinates multiple tools/scripts to:
1. discover candidate manuscripts from modern web and academic search engines,
2. normalize and deduplicate metadata,
3. download content from source-specific websites,
4. record robust execution status and errors,
5. expose stable machine interfaces for orchestration by other programs.

This document defines the cross-tool requirements and interoperability standards before implementation.

---

## 2) Design Principles
- **Composable modules**: each tool does one job and communicates via strict contracts.
- **Deterministic I/O**: all tools emit structured JSON envelopes.
- **Idempotent operations**: repeated calls should not duplicate results or corrupt state.
- **Failure transparency**: errors are typed, actionable, and logged with context.
- **Observability-first**: every run and item has traceable IDs and timings.
- **Provider isolation**: engine/site-specific code stays in adapters, not core contracts.
- **Offline-first artifacts**: all fetched artifacts and metadata stored locally with checksums.

---

## 3) Functional Requirements

### FR-1: Search Discovery Tools
The system must support multiple search providers:
- general web engines,
- academic search engines,
- optional metadata APIs.

Required behaviors:
- query by keyword, boolean query, author, year range, venue,
- pagination support,
- rate-limit aware backoff,
- provider-specific relevance score capture,
- return normalized candidate records.

### FR-2: Candidate Normalization and Deduplication
- normalize fields (title, authors, DOI, URL, year, source, snippet),
- canonicalize URLs,
- fuzzy title matching with deterministic threshold,
- merge duplicates into a single canonical candidate with provenance list.

### FR-3: Source-Specific Download Tools
- each supported website has a dedicated downloader adapter,
- adapters support direct file URLs and landing page resolution,
- retries with exponential backoff and jitter,
- integrity checks (content-type, size bounds, checksum),
- resumable downloads where possible.

### FR-4: Error Handling and Recovery
- typed errors (`NETWORK`, `AUTH`, `RATE_LIMIT`, `NOT_FOUND`, `PARSE`, `VALIDATION`, `INTERNAL`),
- retry policy based on error class,
- dead-letter queue for persistent failures,
- partial-progress persistence.

### FR-5: Programmatic Invocation
Other programs must be able to call tools via:
- CLI contract,
- JSON over stdio,
- optional HTTP/gRPC wrapper later (same core schema).

### FR-6: Auditability
- structured logs and run manifests,
- reproducible run configuration snapshot,
- per-item lifecycle state tracking.

---

## 4) Non-Functional Requirements
- **Reliability**: successful retry/recovery for transient failures.
- **Performance**: configurable concurrency with provider-safe throttling.
- **Portability**: Linux/macOS support; Python-first toolchain assumed.
- **Security**: secrets from env/secret manager only, never plaintext in logs.
- **Compliance**: robots/ToS-aware crawling policy flags per provider.
- **Maintainability**: plugin architecture with explicit adapter interfaces.

---

## 5) Shared Data Contracts (Protocol v1)

### 5.1 Envelope (all tool outputs)
```json
{
  "protocol_version": "1.0",
  "tool": "search.google",
  "run_id": "uuid",
  "status": "ok",
  "started_at": "2026-04-17T00:00:00Z",
  "ended_at": "2026-04-17T00:00:02Z",
  "duration_ms": 2000,
  "data": {},
  "errors": [],
  "metrics": {}
}
```

### 5.2 Candidate Schema
```json
{
  "candidate_id": "stable-hash",
  "title": "...",
  "authors": ["..."],
  "year": 2024,
  "doi": "10.xxxx/xxxx",
  "source_url": "https://...",
  "pdf_url": "https://...",
  "venue": "...",
  "abstract_snippet": "...",
  "provider": "google_scholar",
  "provider_rank": 3,
  "provider_score": 0.87,
  "provenance": [
    {
      "provider": "google_scholar",
      "query": "...",
      "fetched_at": "2026-04-17T00:00:00Z"
    }
  ]
}
```

### 5.3 Download Result Schema
```json
{
  "download_id": "uuid",
  "candidate_id": "stable-hash",
  "status": "downloaded",
  "http_status": 200,
  "resolved_url": "https://...",
  "local_path": "artifacts/raw/<candidate_id>.pdf",
  "sha256": "...",
  "bytes": 123456,
  "mime_type": "application/pdf",
  "attempt_count": 2,
  "warnings": []
}
```

### 5.4 Error Schema
```json
{
  "code": "RATE_LIMIT",
  "message": "Provider returned 429",
  "retryable": true,
  "provider": "example_provider",
  "context": {
    "url": "https://...",
    "attempt": 1
  }
}
```

---

## 6) Interface Standards

### 6.1 CLI Standard
All tools must support:
- `--input <json file | ->`
- `--output <json file | ->`
- `--config <path>`
- `--run-id <uuid>`
- `--log-level <debug|info|warn|error>`
- exit codes:
  - `0` success,
  - `10` partial success,
  - `20` validation error,
  - `30` provider/network failure,
  - `40` internal error.

### 6.2 Stdio JSON RPC-like Contract
Request:
```json
{
  "protocol_version": "1.0",
  "tool": "downloader.arxiv",
  "action": "execute",
  "run_id": "uuid",
  "payload": {}
}
```

Response uses the shared envelope.

### 6.3 Configuration Standard
- layered config: defaults < file < env < CLI,
- strict schema validation,
- environment variables prefixed `MSDP_`.

---

## 7) Adapter Plugin Protocol
Each adapter (search or downloader) must implement:
- `capabilities()` -> declares supported filters/features,
- `validate_input(payload)` -> strict validation,
- `execute(payload, context)` -> returns envelope-compliant data,
- `healthcheck()` -> quick readiness check.

Adapter manifest fields:
- `name`, `version`, `type` (`search`/`download`),
- `supported_domains` or `supported_engines`,
- `auth_requirements`,
- `rate_limit_profile`.

---

## 8) Reliability Standards
- default retry policy: max 4 attempts, exponential backoff base 1.5s, full jitter,
- circuit breaker per provider,
- persistent queue for pending/retry/dead-letter states,
- idempotency key: hash of (`tool`, canonicalized input, run scope).

---

## 9) Storage and Artifacts
Recommended directory contract:
- `artifacts/raw/` downloaded binaries,
- `artifacts/normalized/` canonical metadata,
- `artifacts/logs/` structured logs,
- `artifacts/manifests/` run manifests,
- `artifacts/dead-letter/` persistent failures.

Manifests include run config hash, tool versions, and summary metrics.

---

## 10) Security and Compliance Standards
- no secret values in logs or artifacts,
- redact auth headers/cookies in error context,
- configurable domain allowlist,
- configurable robots/ToS policy per provider,
- user-agent string must identify contact + project.

---

## 11) Acceptance Criteria (for initial baseline)
1. At least two search adapters and two downloader adapters integrated behind common contracts.
2. End-to-end run from query -> candidates -> download results with structured manifest.
3. Simulated transient failure recovers via retry; permanent failure lands in dead-letter.
4. All tools pass schema validation tests and contract tests.
5. CLI and stdio invocation both supported for at least one adapter of each type.

---

## 12) Open Decisions
- protocol transport for remote orchestration (HTTP vs gRPC),
- canonical dedup scoring algorithm and thresholds,
- persistent store choice (SQLite vs Postgres) for larger-scale runs,
- parser stage boundaries (out of scope for current planning phase).
