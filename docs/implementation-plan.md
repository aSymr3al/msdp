# MSDP Implementation Plan (Refined, Phase-Oriented)

## Goal
Deliver a reliable, composable tool ecosystem for manuscript discovery, download, and PDF parsing that adheres to `Protocol v1` and can be called by external orchestrators.

## Delivery Principles
- Build contracts first; implementation follows explicit schemas.
- Keep provider-specific behavior isolated in adapters.
- Require deterministic JSON envelopes and typed errors for every tool.
- Add tests in parallel with each feature (not after all coding).

---

## Phase 0 — Foundation (Docs + Contracts)
**Deliverables**
- finalized protocol and schema docs,
- exit codes and error taxonomy,
- adapter interfaces/manifests,
- parser output contract baseline.

**Tasks**
1. Lock JSON Schemas for envelope/candidate/download/error/parser-result.
2. Add versioning policy (`protocol_version`, backward compatibility rules).
3. Add contract test fixtures for success, partial, and failure paths.

**Exit Criteria**
- requirements doc approved,
- schema fixtures committed,
- contract tests drafted and runnable.

---

## Phase 1 — Core Runtime Skeleton
**Deliverables**
- shared SDK/core library,
- adapter loader,
- run context + structured logging,
- config resolver.

**Tasks**
1. Implement base types and validation utilities.
2. Implement CLI scaffold with common flags and exit codes.
3. Implement stdio request/response handler.
4. Add run manifest writer.

**Exit Criteria**
- dummy adapter runs through CLI and stdio,
- envelope/error schema validation enforced.

---

## Phase 2 — Search Adapters (MVP)
**Deliverables**
- multiple search adapters,
- normalization + dedup pipeline.

**Tasks**
1. Implement provider-specific query/pagination modules.
2. Map raw results to Candidate Schema.
3. Implement URL canonicalization and candidate ID hashing.
4. Add dedup merge logic with provenance retention.

**Exit Criteria**
- same query across providers yields merged canonical candidates,
- rate-limit and transient failures are retried successfully.

---

## Phase 3 — Downloader Adapters (MVP)
**Deliverables**
- source-specific downloader adapters,
- shared download manager with retry/circuit breaker.

**Tasks**
1. Implement landing-page-to-file resolution flow.
2. Add checksum + file metadata verification.
3. Add resumable download support where feasible.
4. Persist failed downloads to dead-letter queue.

**Exit Criteria**
- successful download + integrity metadata produced,
- expected permanent failures classified and queued.

---

## Phase 4 — PDF Parse Adapter (New)
**Deliverables**
- `parse.pdf_key_info` adapter for one-PDF input,
- structured key-info extraction output,
- parser-specific error handling and validation.

**Tasks**
1. Define parser input (`input_pdf`, `max_pages`) and output (`title`, `doi`, `year`, `abstract`, `sections`, etc.).
2. Implement text extraction wrapper with dependency validation.
3. Implement deterministic regex/heuristic extraction for key metadata.
4. Emit envelope-compliant output with `PARSE` and `VALIDATION` errors.
5. Add unit tests for happy path and failure scenarios (missing file, wrong extension, empty text).

**Exit Criteria**
- one PDF file can be parsed via CLI,
- output matches parser contract,
- failures are typed and actionable.

---

## Phase 5 — Reliability, Observability, QA
**Deliverables**
- contract tests,
- adapter integration tests,
- observability templates,
- failure-injection tests.

**Tasks**
1. Build golden vectors for schema and dedup.
2. Add chaos tests for 429/5xx/timeouts.
3. Validate idempotency behavior on repeated invocations.
4. Publish runbook for operations and debugging.

**Exit Criteria**
- target pass rates met,
- logs/manifests sufficient for root-cause analysis.

---

## Phase 6 — External Integration and Scale
**Deliverables**
- stable public CLI conventions,
- optional remote execution wrapper,
- plugin packaging guidance,
- parser-chain integration guidance (search -> download -> parse).

**Tasks**
1. Add compatibility tests for external callers.
2. Add version negotiation policy for protocol updates.
3. Benchmark concurrency and tune per-provider throttles.
4. Add end-to-end benchmark including parser stage.

**Exit Criteria**
- external programs reliably execute discovery/download/parse pipelines,
- compatibility matrix documented.

---

## Work Breakdown Structure (Updated)
- **WBS-1 Contracts**: schema files, validators, contract tests.
- **WBS-2 Runtime**: config, logging, run IDs, manifest writing.
- **WBS-3 Search**: provider clients, normalization, dedup.
- **WBS-4 Download**: resolvers, retries, integrity checks.
- **WBS-5 Parse**: PDF extraction, metadata heuristics, parse errors.
- **WBS-6 Ops**: metrics, failure queues, runbooks.

## Risks and Mitigations
- **Provider anti-bot/rate-limits** -> adaptive throttling + backoff + provider-specific policies.
- **Schema drift** -> strict versioning + CI contract gates.
- **Fragile site-specific scrapers** -> isolate adapters + snapshot tests.
- **Duplicate explosion** -> deterministic canonicalization + threshold review workflow.
- **PDF extraction variance** -> bounded heuristics + confidence notes + parser fallback behavior.

## Suggested Milestones
- **M1 (Week 1)**: contracts + runtime skeleton.
- **M2 (Week 2-3)**: search adapters + dedup.
- **M3 (Week 3-4)**: downloader adapters + integrity checks.
- **M4 (Week 4-5)**: PDF parse adapter + parser tests.
- **M5 (Week 6)**: contract/integration hardening and docs.

## Definition of Done (Project Baseline)
- Search/download/parse adapters conform to Protocol v1 envelope contracts.
- End-to-end flow is reproducible with manifest artifacts.
- Typed errors and retries behave per policy.
- External caller can execute via CLI or stdio with predictable outputs.
