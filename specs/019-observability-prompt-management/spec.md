# Feature Specification: Observability and Prompt Management

**Feature Branch**: `019-observability-prompt-management`

**Created**: 2026-06-10

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 010 — Suggested Replies](../010-suggested-replies/spec.md)
- [Spec 012 — Escalation to Manager (Risky-Case Agent)](../012-escalation-to-manager/spec.md)
- [Spec 013 — Audit Logs](../013-audit-logs/spec.md)
- [Spec 014 — Guardrails](../014-guardrails/spec.md)

**Input**: User description: "The system should be observable — structured logs with correlation IDs, basic metrics, and timing/latency for AI calls (classifier, RAG, reply, agent, guardrails) — and AI prompts should be managed as versioned, hashed templates loaded from a registry rather than hardcoded, with the prompt version recorded on each AI output."

---

## Goal

Make EventSense AI **observable and its prompts managed**, so the team can see what the system is doing and reproduce/trace any AI output. Two cohesive halves:

1. **Observability** — emit **structured (JSON) logs** with a **correlation/request id** threaded through every request and into every AI step (classifier, RAG, reply, agent, guardrail, audit); record **latency/timing** for each AI call; expose lightweight **metrics** (counts + durations of AI calls, guardrail refusals, cross-tenant blocks, agent runs) at a `/metrics` endpoint. All logs/metrics are **redacted** (no secrets, JWTs, system prompts, raw PII, or cross-tenant data) reusing the Spec 014 redactor.
2. **Prompt management** — AI prompts (reply generation, agent system/tool prompts, summarization) live as **versioned, hashed templates in a registry** (in-repo files) loaded at runtime rather than hardcoded; every AI output records the **`prompt_id@version` (+ hash)** that produced it, so an output is traceable to the exact prompt, and prompts can be reviewed/changed as a diff.

This is a cross-cutting reliability/maintainability layer over the existing AI pipeline. It changes **no** business behavior — it instruments and parameterizes what already runs. It does **not** add real WhatsApp/calendar/billing, an external APM vendor, or a large prompt-experimentation platform.

---

## Observability Signals

| Signal | Examples | Notes |
|--------|----------|-------|
| **Structured logs** | request start/end, AI step start/end, guardrail decision, agent tool call, error | JSON lines; `request_id`, `tenant_id`, `user_id`, `route`, `latency_ms`, `outcome`; **redacted** |
| **Correlation id** | `request_id` (per request) propagated to every AI step + audit/guardrail/agent record | Lets one request be traced end to end |
| **Latency/timing** | per-call ms for classifier / RAG / reply / agent / guardrail | Stored on the log line + as a metric |
| **Metrics** | counters + histograms: `ai_calls_total{component}`, `ai_latency_ms{component}`, `guardrail_refusals_total{category}`, `cross_tenant_blocks_total`, `agent_runs_total`, `agent_tool_calls_total{tool}` | Exposed at `/metrics` (Prometheus text) |

## Prompt Registry

| Field | Description |
|-------|-------------|
| `prompt_id` | Stable id (e.g., `suggested_reply.system`, `agent.system`, `escalation.summary`) |
| `version` | Semver-ish or incrementing version of that prompt |
| `hash` | Content hash (e.g., SHA-256) of the rendered template |
| `template` | The prompt text with named variables (no secrets, no tenant data baked in) |
| `metadata` | Owner, description, last-changed; no secrets |

---

## Main Users

| Role | Description |
|------|-------------|
| **Developer / operator** | Reads structured logs by `request_id` to trace a request through the AI pipeline; watches `/metrics` for latency/error/refusal rates; edits prompt templates in the registry as reviewable diffs. |
| **Project owner / reviewer** | Reviews prompt changes (diffs + version bumps) and uses metrics/timing as evidence the system is healthy and performant for the report. |
| **System / AI services** | Emit redacted structured logs + metrics for each step; load prompts from the registry and stamp `prompt_id@version` on outputs. Not human actors. |

Platform Admin sees no tenant content via logs/metrics (signals are redacted and aggregate).

---

## User Stories

### User Story 1 — Trace a Request End-to-End via Correlation ID (Priority: P1)

Every incoming request is assigned (or accepts) a `request_id`. That id is attached to the request's structured logs and propagated into each AI step (classifier → RAG → reply → agent → guardrail) and into the audit/guardrail/agent records. A developer can take one `request_id` and see the full, ordered, redacted trace of what happened — which steps ran, how long each took, and the outcome — without any secret/PII/cross-tenant data appearing.

**Why this priority**: Correlation is the foundation of observability — without it, logs are unlinkable noise. It is the prerequisite for debugging the AI pipeline. Core P1.

**Independent Test**: Send a request through the classify→risk→RAG→reply path; capture its `request_id`; assert structured log lines for each step share that id, include `tenant_id`/`route`/`latency_ms`/`outcome`, are valid JSON, and contain no secret/PII/system-prompt/cross-tenant content. Assert the same `request_id` appears on the resulting audit/guardrail records.

**Acceptance Scenarios**:

1. **Given** an incoming request, **When** it is handled, **Then** a `request_id` is generated (or taken from an inbound header) and added to every log line for that request.
2. **Given** an AI step runs (classifier/RAG/reply/agent/guardrail), **When** it logs, **Then** the line carries the same `request_id`, the component name, `latency_ms`, and an `outcome`.
3. **Given** a request produces an audit/guardrail/agent record, **When** it is written, **Then** the record carries the same `request_id` for correlation.
4. **Given** any log line, **When** inspected, **Then** it contains no secrets/JWTs/system prompts/raw PII/cross-tenant data (Spec 014 redactor applied).

---

### User Story 2 — Latency and Metrics for AI Calls (Priority: P1)

Each AI call records its duration; the system exposes aggregate metrics — call counts and latency histograms per component (classifier/RAG/reply/agent/guardrail), guardrail refusals by category, cross-tenant blocks, and agent runs/tool-calls — at a `/metrics` endpoint in Prometheus text format. A developer/owner can see p50/p95 latency and error/refusal rates as evidence of health and performance.

**Why this priority**: Timing + counts are the headline "is it healthy/fast?" signals for operations and the report. Equal P1 with tracing.

**Independent Test**: Drive several requests; scrape `/metrics`; assert `ai_calls_total{component=...}` increments per component, `ai_latency_ms` histograms have observations, `guardrail_refusals_total{category=...}` increments when a refusal occurs, and `cross_tenant_blocks_total` increments on a blocked cross-tenant attempt. Assert `/metrics` exposes no tenant content or secrets.

**Acceptance Scenarios**:

1. **Given** an AI call completes, **When** it returns, **Then** its `latency_ms` is recorded on the log line and observed into the component's latency metric.
2. **Given** requests have run, **When** `/metrics` is scraped, **Then** it returns Prometheus-format counters + histograms for AI calls, guardrail refusals (by category), cross-tenant blocks, and agent runs/tool-calls.
3. **Given** a guardrail refusal or cross-tenant block occurs, **When** metrics update, **Then** the corresponding counter increments.
4. **Given** `/metrics`, **When** it is read, **Then** it exposes only aggregate numbers/labels — no tenant content, message text, secrets, or PII; access is restricted (operator/owner, not public tenant routes).

---

### User Story 3 — Prompts Loaded From a Versioned, Hashed Registry (Priority: P1)

AI prompts are not hardcoded in service code. They live in an in-repo **prompt registry** (versioned template files), each with a `prompt_id`, `version`, content `hash`, and named variables. Services (reply generation, the risky-case agent, escalation summarization) load the active prompt from the registry at runtime. The team changes a prompt by editing the template and bumping its version — a reviewable diff.

**Why this priority**: Centralized, versioned prompts make AI behavior reviewable and reproducible (and decouple prompt edits from code). Core P1 of the prompt-management half.

**Independent Test**: Assert the reply/agent/summary services read their prompt from the registry (not an inline string); change a template + bump its version; assert the service uses the new version and the change is a single reviewable diff; assert each registry entry has a `prompt_id`, `version`, and a content `hash` that matches the template.

**Acceptance Scenarios**:

1. **Given** an AI service needs a prompt, **When** it runs, **Then** it loads the active template from the registry by `prompt_id` (no hardcoded prompt string in the service path).
2. **Given** a registry entry, **When** loaded, **Then** it exposes `prompt_id`, `version`, a content `hash`, the template, and named variables; the `hash` matches the template content.
3. **Given** a prompt is edited, **When** its version is bumped and committed, **Then** the service uses the new version on the next run and the change is a reviewable diff.
4. **Given** a missing/invalid prompt id or a hash mismatch, **When** loading, **Then** the service fails fast with a clear error (no silent fallback to an unknown prompt).

---

### User Story 4 — Each AI Output Records Its Prompt Version (Priority: P2)

When an AI output is produced (a suggested reply, an agent recommendation, an escalation summary), the system records which `prompt_id@version` (and hash) generated it — on the output record and/or its audit/observability log — so any output can be traced to the exact prompt that produced it. This pairs with the model `model_version`/hash (Spec 006) for full reproducibility.

**Why this priority**: Output→prompt traceability makes results reproducible and reviewable, but the pipeline functions once prompts are registry-loaded (US3). P2.

**Independent Test**: Generate a suggested reply; assert the stored reply (or its audit/observability record) carries the `prompt_id@version` (+ hash) used, and that it matches the registry entry the service loaded. Repeat for an agent recommendation and an escalation summary.

**Acceptance Scenarios**:

1. **Given** a suggested reply is generated, **When** it is stored/logged, **Then** the `prompt_id@version` (+ hash) used is recorded and matches the registry.
2. **Given** an agent recommendation or escalation summary, **When** produced, **Then** its `prompt_id@version` is recorded for traceability.
3. **Given** a recorded `prompt_id@version`, **When** combined with `model_version` (006), **Then** the output is reproducible (same prompt + model + input → same result for deterministic components).
4. **Given** the recorded prompt reference, **When** stored, **Then** it carries no secrets/PII/cross-tenant data — only the id/version/hash.

---

### Edge Cases

- **Inbound `request_id` header**: if a trusted caller supplies a correlation id, it is used; otherwise one is generated. An untrusted/oversized value is replaced with a generated id.
- **High log volume**: logs are structured + level-gated (debug/info/warn/error); verbose AI-step logging is gated by config so production stays manageable.
- **`/metrics` exposure**: `/metrics` is not a tenant content route; it is restricted to operator/owner (or internal network) and carries only aggregate labels — never message text or tenant identifiers that leak content.
- **Redaction in logs**: a message body, secret, or system prompt must never land in a log line; the Spec 014 redactor is applied to any free-text field before logging.
- **Prompt hash mismatch**: a template edited without a version bump (hash ≠ recorded) fails fast — prevents silent prompt drift.
- **Missing prompt at runtime**: a referenced `prompt_id` absent from the registry fails fast with a clear error, never falls back to an empty/hardcoded prompt.
- **Cardinality**: metric labels are bounded (component, category, tool) — no per-tenant/per-message labels that would explode cardinality or leak identifiers.
- **Tenant scoping**: logs may include `tenant_id` for correlation, but never tenant **content**; metrics never include `tenant_id` as a label (aggregate only).
- **No new autonomy**: observability/prompt-management add no actions — they instrument and parameterize; the human-review/approval and tenant boundaries are unchanged.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST assign a `request_id` to every request (or accept a trusted inbound one) and include it on every structured log line for that request.
- **FR-002**: Logs MUST be **structured (JSON)** with at least `request_id`, `tenant_id`, `user_id`, `route`/`component`, `latency_ms` (where applicable), `outcome`, and `level`.
- **FR-003**: The `request_id` MUST be propagated into each AI step (classifier, RAG, reply, agent, guardrail) and onto the audit/guardrail/agent records produced by that request.
- **FR-004**: Each AI call MUST record its **latency** and log start/end (or a single timed line) with the component name and outcome.
- **FR-005**: The system MUST expose a `/metrics` endpoint (Prometheus text) with at least: `ai_calls_total{component}`, `ai_latency_ms{component}` histogram, `guardrail_refusals_total{category}`, `cross_tenant_blocks_total`, `agent_runs_total`, `agent_tool_calls_total{tool}`.
- **FR-006**: All logs and metrics MUST be **redacted** (Spec 014 redactor) — no secrets, JWTs, system prompts, raw PII, message bodies, or cross-tenant data; metrics carry only bounded aggregate labels (no `tenant_id`/per-message labels).
- **FR-007**: `/metrics` MUST NOT be a public tenant content route; access MUST be restricted to operator/owner or internal use.
- **FR-008**: AI prompts (reply, agent system/tool, summarization) MUST be loaded from a **versioned prompt registry** (in-repo template files) rather than hardcoded in service code.
- **FR-009**: Each registry entry MUST expose `prompt_id`, `version`, a content `hash`, the `template` (named variables), and `metadata`; the `hash` MUST match the template content.
- **FR-010**: Loading a missing/invalid `prompt_id` or a template whose content hash does not match its recorded hash MUST **fail fast** with a clear error (no silent fallback).
- **FR-011**: Each AI output (suggested reply, agent recommendation, escalation summary) MUST record the `prompt_id@version` (+ hash) that produced it, on the output record and/or its audit/observability log.
- **FR-012**: The recorded prompt reference MUST carry no secrets/PII/cross-tenant data — only id/version/hash.
- **FR-013**: Verbose AI-step logging MUST be **config-gated** (log level / flag) so production volume stays manageable; errors are always logged.
- **FR-014**: Observability and prompt management MUST add **no new business actions** — they instrument and parameterize existing behavior; tenant isolation, guardrails, and human-review steps are unchanged.

### Key Entities

- **RequestContext** (new, in-memory): carries `request_id`, `tenant_id`, `user_id` through the request; source of the correlation id on logs/records.
- **Structured log event** (new, emitted): a redacted JSON log line (not a DB entity).
- **Metric** (new, in-process): counters/histograms exposed at `/metrics` (no DB entity).
- **PromptTemplate** (new, file-backed): a registry entry (`prompt_id`, `version`, `hash`, `template`, `metadata`).
- **PromptRef** (new, recorded): `prompt_id@version` (+ hash) stamped on an AI output / audit record.
- Reuses: **AuditLog** (013), **GuardrailDecision** (014), agent-run record (012 Advanced), **ClassificationResult**/`model_version` (006).

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Request + optional `X-Request-Id` | HTTP | Correlation id (generated if absent/untrusted) |
| Authenticated session | JWT | `tenant_id`/`user_id` for log correlation (never content) |
| AI call boundaries | Services 006/009/010/012/014 | Where timing + logs are emitted |
| Prompt registry files | `backend/app/prompts/` (or `prompts/`) | Versioned, hashed templates loaded at runtime |
| Log level / flags | Config | Gate verbose AI-step logging |

---

## Outputs

| Output | Description |
|--------|-------------|
| Structured logs | Redacted JSON lines with `request_id` + timing + outcome |
| `/metrics` | Prometheus-format counters + histograms (aggregate, redacted) |
| Loaded prompt | The active registry template for a `prompt_id` |
| Recorded prompt ref | `prompt_id@version` (+ hash) on AI outputs/audit |
| Fail-fast errors | On missing prompt / hash mismatch (clear message) |

---

## Main Workflow

1. **Request arrives** — a `request_id` is assigned (or taken from a trusted header) and placed in the request context.
2. **Pipeline runs** — classifier → RAG → reply → (agent) → guardrail; each step emits a redacted structured log line with the shared `request_id`, component, `latency_ms`, outcome, and observes its latency metric.
3. **Prompts loaded** — reply/agent/summary services load their active template from the registry by `prompt_id` (hash-verified) instead of an inline string.
4. **Outputs stamped** — each AI output records the `prompt_id@version` (+ hash) used (with the `model_version` from 006) for reproducibility.
5. **Records correlated** — audit (013), guardrail (014), and agent-run (012) records carry the same `request_id`.
6. **Signals exposed** — `/metrics` serves aggregate counters/histograms; logs are searchable by `request_id`; all redacted.

No client message is sent, no tenant boundary crossed, and no new autonomous action taken.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Every request gets a `request_id` present on all its log lines | Integration test: assert shared id |
| AC-02 | Each AI step logs the shared `request_id`, component, `latency_ms`, outcome as JSON | Integration test |
| AC-03 | Audit/guardrail/agent records carry the request's `request_id` | Integration test |
| AC-04 | No secrets/JWTs/system prompts/raw PII/message bodies/cross-tenant data in any log | Redaction scan |
| AC-05 | AI-call latency is recorded and observed into the component's metric | Integration test |
| AC-06 | `/metrics` returns Prometheus counters + histograms for ai_calls, latency, guardrail refusals (by category), cross-tenant blocks, agent runs/tool-calls | Scrape + assert |
| AC-07 | Guardrail refusal / cross-tenant block increments its counter | Integration test |
| AC-08 | `/metrics` exposes only aggregate labels (no tenant content/secrets); access restricted | Scrape + access test |
| AC-09 | Reply/agent/summary services load prompts from the registry (no hardcoded prompt string) | Code/integration test |
| AC-10 | Each registry entry has prompt_id/version/hash/template; hash matches content | Unit test |
| AC-11 | Editing a template + bumping version → service uses the new version; change is a reviewable diff | Integration test |
| AC-12 | Missing prompt id or hash mismatch fails fast with a clear error (no silent fallback) | Unit test |
| AC-13 | Each AI output records the `prompt_id@version` (+ hash) used, matching the registry | Integration test |
| AC-14 | Recorded prompt ref contains no secrets/PII/cross-tenant data | Redaction scan |
| AC-15 | Verbose AI logging is config-gated; errors always logged | Config test |
| AC-16 | Observability/prompt-management add no new business actions; isolation/guardrails/human-review unchanged | Code/integration review |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | `tenant_id` for correlation (never content); metrics stay aggregate |
| Spec 002 — Authentication and Roles | Required | `user_id` for correlation; `/metrics` restricted to operator/owner |
| Spec 006 — Intent Classifier | Required | `model_version`/hash paired with prompt ref; classifier timing |
| Spec 009 — RAG / Spec 010 — Replies | Required | Timed AI calls; reply prompt loaded from the registry + stamped |
| Spec 012 — Risky-Case Agent | Required | Agent system/tool prompts from the registry; agent run/tool metrics + prompt ref |
| Spec 013 — Audit Logs | Required | Records carry `request_id`; reuse for output→prompt traceability |
| Spec 014 — Guardrails | Required | The **redactor** reused for logs/metrics; refusal counters |
| Logging/metrics libs (stdlib `logging` JSON + a Prometheus client) | Required | No external APM vendor |

---

## Security / Privacy Rules

| Rule | Description |
|------|-------------|
| **SP-01: Redact every emitted field** | Logs/metrics pass free-text through the Spec 014 redactor; no secrets/JWTs/system prompts/raw PII/message bodies/cross-tenant data is emitted. |
| **SP-02: Metrics are aggregate only** | `/metrics` carries bounded labels (component/category/tool); never `tenant_id`/message ids/content — no cardinality blowup, no content leak. |
| **SP-03: `/metrics` is not a tenant route** | It is restricted to operator/owner or internal use; tenant users/Platform Admin cannot read it as a content route. |
| **SP-04: Correlation id ≠ content** | `request_id`/`tenant_id`/`user_id` correlate records; they never carry message text or secrets. |
| **SP-05: Prompts carry no secrets/tenant data** | Registry templates and recorded prompt refs contain no secrets/keys or tenant content; tenant data is injected at runtime as variables, not stored in the template. |
| **SP-06: Fail closed on prompt integrity** | Missing prompt / hash mismatch fails fast — no silent fallback to an unknown/empty prompt. |
| **SP-07: No new autonomy/boundary change** | Instrumentation/parameterization only; tenant isolation, guardrails, and human-review/approval are unchanged. |

---

## Out of Scope

- **External APM / vendor tracing** (Datadog/New Relic/OTel collector backends) — MVP uses structured logs + a `/metrics` endpoint; an OpenTelemetry exporter is future hardening.
- **Distributed tracing across multiple services** — single-backend correlation id for the MVP; full span trees are future.
- **Log aggregation/storage/retention infra** (ELK, Loki) — emit structured logs to stdout; shipping/retention is deferred.
- **A prompt A/B-testing / experimentation platform** — the registry is versioned templates + diffs, not an online experimentation system.
- **A DB-backed prompt-editing UI** — prompts are file-backed, edited as code/diffs; an in-app editor is out of scope.
- **Dashboards** — `/metrics` is scrape-ready; building Grafana dashboards is out of scope (Spec 015 has the eval dashboard).
- **Real WhatsApp API, calendar sync, billing, mobile app, full CRM** — out of scope entirely.
- **Changing AI business logic** — this feature instruments and parameterizes; it does not change what the AI decides.

---

## Assumptions

- A single backend process (per Spec 017) — one correlation id per request is sufficient; no cross-service trace propagation is needed for the MVP.
- The prompt registry is **file-backed** (e.g., `backend/app/prompts/*.yaml`) loaded at startup and cached; hashes are computed at load and verified — no DB table is required for the MVP.
- Tenant content is injected into prompts at runtime as variables; templates themselves never contain tenant data or secrets.
- `/metrics` uses a Prometheus client library and is exposed on the backend, restricted to operator/owner or the internal network.
- The Spec 014 redactor is reusable as a standalone utility for log/metric fields.
- Recording `prompt_id@version` reuses existing records (the suggested-reply row, audit log, agent-run record) — no new tenant-owned table is required.
- Verbose AI-step logging is off/low by default and raised via config when debugging.
