# MSDP Implementation Plan (Phase-Oriented)

## Goal
Deliver a reliable, composable tool ecosystem for manuscript discovery and download that adheres to `Protocol v1` and can be called by external orchestrators.

## Phase 0 — Foundation (Docs + Contracts)
**Deliverables**
- finalize protocol and schema docs,
- define exit codes and error taxonomy,
- define adapter interfaces and manifests.

**Tasks**
1. Lock JSON Schemas for envelope/candidate/download/error.
2. Add versioning policy (`protocol_version`, backward compatibility rules).
3. Define contract test fixtures.

**Exit Criteria**
- requirements doc approved,
- schema fixtures committed,
- initial contract tests drafted.

---

## Phase 1 — Core Runtime Skeleton
**Deliverables**
- shared SDK/core library,
- adapter loader,
- run context + structured logging,
- config resolver.

**Tasks**
1. Implement base types and validation utilities.
2. Implement CLI scaffold using common flags.
3. Implement stdio request/response handler.
4. Add run manifest writer.

**Exit Criteria**
- a dummy adapter runs through CLI and stdio,
- envelope and error schema validation enforced.

---

## Phase 2 — Search Adapters (MVP)
**Deliverables**
- Adapter A: modern web search provider,
- Adapter B: academic search provider,
- normalization + dedup pipeline.

**Tasks**
1. Implement provider-specific query/pagination modules.
2. Map raw results to Candidate Schema.
3. Implement URL canonicalization and candidate ID hashing.
4. Add dedup merge logic with provenance retention.

**Exit Criteria**
- same query across 2 providers yields merged canonical candidates,
- rate-limit and transient failures are retried successfully.

---

## Phase 3 — Downloader Adapters (MVP)
**Deliverables**
- Adapter C: downloader for Site 1,
- Adapter D: downloader for Site 2,
- shared download manager with retry/circuit breaker.

**Tasks**
1. Implement landing-page-to-file resolution flow.
2. Add checksum + file metadata verification.
3. Add resumable download support where technically feasible.
4. Persist failed downloads to dead-letter queue.

**Exit Criteria**
- successful download + integrity metadata produced,
- expected permanent failures classified and queued.

---

## Phase 4 — Reliability, Observability, QA
**Deliverables**
- contract tests,
- adapter integration tests,
- observability dashboards/log templates,
- failure-injection tests.

**Tasks**
1. Build golden test vectors for schema and dedup.
2. Add chaos tests for 429/5xx/timeouts.
3. Validate idempotency behavior on repeated invocations.
4. Publish runbook for operations and debugging.

**Exit Criteria**
- target pass rates met,
- logs/manifests sufficient for root-cause analysis.

---

## Phase 5 — External Integration and Scale
**Deliverables**
- stable public CLI conventions,
- optional remote execution wrapper,
- plugin packaging guidance.

**Tasks**
1. Add compatibility tests for external callers.
2. Add version negotiation policy for protocol updates.
3. Benchmark concurrency and tune per-provider throttles.

**Exit Criteria**
- other programs can reliably call search/download pipelines,
- compatibility matrix documented.

---

## Work Breakdown Structure (Initial)
- **WBS-1 Contracts**: schema files, validators, contract tests.
- **WBS-2 Runtime**: config, logging, run IDs, manifest writing.
- **WBS-3 Search**: provider clients, normalization, dedup.
- **WBS-4 Download**: resolvers, retries, integrity checks.
- **WBS-5 Ops**: metrics, failure queues, runbooks.

## Risks and Mitigations
- **Provider anti-bot/rate-limits** -> adaptive throttling + backoff + provider-specific policies.
- **Schema drift** -> strict versioning + CI contract gates.
- **Fragile site-specific scrapers** -> isolate adapters + snapshot tests.
- **Duplicate explosion** -> deterministic canonicalization + threshold review workflow.

## Suggested Milestones
- **M1 (Week 1)**: contracts + runtime skeleton.
- **M2 (Week 2-3)**: first 2 search adapters + dedup.
- **M3 (Week 3-4)**: first 2 downloader adapters + integrity checks.
- **M4 (Week 5)**: contract/integration hardening and docs.

## Definition of Done (Project Baseline)
- All MVP adapters conform to Protocol v1.
- End-to-end flow is reproducible with manifest artifacts.
- Typed errors and retries behave per policy.
- External caller can execute via CLI or stdio with predictable outputs.
