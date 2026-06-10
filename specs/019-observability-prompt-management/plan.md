# Implementation Plan: Observability and Prompt Management

**Branch**: `019-observability-prompt-management` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/019-observability-prompt-management/spec.md`

**Depends on**:
- [Spec 013 — Audit Logs](../013-audit-logs/plan.md): records carry `request_id`; reuse for output→prompt traceability
- [Spec 014 — Guardrails](../014-guardrails/plan.md): the **redactor** reused for logs/metrics
- [Spec 006](../006-intent-classifier/plan.md) / [009](../009-rag-over-tenant-documents/plan.md) / [010](../010-suggested-replies/plan.md) / [012 agent](../012-escalation-to-manager/plan.md): the AI calls instrumented + the prompts registered

---

## Summary

Add a cross-cutting observability + prompt-management layer. **Observability**: a middleware assigns/propagates a `request_id`, a structured JSON logger emits redacted log lines, AI calls are timed via a small decorator/context manager, and a Prometheus `/metrics` endpoint exposes aggregate counters/histograms. **Prompt management**: AI prompts move from hardcoded strings into a file-backed, versioned, hash-verified registry loaded at runtime; each AI output records the `prompt_id@version` (+ hash) that produced it. No business logic or tenant-boundary change — instrumentation + parameterization only, reusing the Spec 014 redactor.

---

## Technical Approach

- **Request context + correlation id**: a FastAPI middleware reads a trusted `X-Request-Id` (or generates a UUID), stores `request_id`/`tenant_id`/`user_id` in a `contextvars`-based `RequestContext`, and binds it to the logger. The id is read by AI steps and passed to audit/guardrail/agent writes (add a nullable `request_id` field to those records or include it in their metadata/log).
- **Structured logging**: configure stdlib `logging` with a JSON formatter (or `structlog`) emitting one object per event with `request_id`, `tenant_id`, `user_id`, `component`/`route`, `latency_ms`, `outcome`, `level`. A logging filter runs free-text fields through the Spec 014 redactor before emit. Verbose AI-step logs are gated by `LOG_LEVEL`/`AI_TRACE_ENABLED`.
- **Timing**: a `@timed(component)` decorator / `with timed("rag"):` context manager wraps each AI call (classifier/RAG/reply/agent/guardrail), logs a timed line and observes `ai_latency_ms{component}` + increments `ai_calls_total{component}`.
- **Metrics**: use `prometheus_client`; define counters/histograms once (registry singleton); mount `GET /metrics` returning the text exposition. Restrict via a role/internal guard (operator/owner) — not a tenant content route. Labels bounded to `component`/`category`/`tool` (no tenant/message labels).
- **Prompt registry**: `backend/app/prompts/*.yaml` files, each `{ prompt_id, version, hash, template, metadata }`. A `PromptRegistry` loads them at startup, computes the content hash, and **fails fast** if a recorded hash mismatches or a referenced id is missing. Services fetch via `registry.get("suggested_reply.system")` returning a `PromptTemplate` with `.render(**vars)` and `.ref` (`prompt_id@version` + hash). Replace inline prompt strings in reply (010), agent (012), and summarization (012) paths.
- **Output stamping**: when an AI output is produced, record its `PromptRef` — on the suggested-reply row (add a `prompt_ref` column or reuse a metadata JSON), the agent-run record, and/or the audit/log line — alongside the `model_version` (006). Keep it to id/version/hash (no content).
- **Redaction reuse**: import the Spec 014 redactor as a standalone util used by both the log filter and any metric label sanitization.

---

## Backend Tasks

1. **`core/request_context.py`** — `contextvars` `RequestContext` (`request_id`/`tenant_id`/`user_id`) + accessors.
2. **`api/middleware/correlation.py`** — assign/accept `request_id`; populate context; add `X-Request-Id` to the response.
3. **`core/logging.py`** — JSON log config + a redaction filter (reuses Spec 014 redactor) + `LOG_LEVEL`/`AI_TRACE_ENABLED` gating.
4. **`core/observability.py`** — `timed(component)` decorator/context manager; metric definitions (counters/histograms) via `prometheus_client`.
5. **`api/v1/metrics.py`** — `GET /metrics` (Prometheus text), operator/owner-restricted, not a tenant content route.
6. **Instrument AI calls** — wrap classifier (006), RAG (009), reply (010), agent + tools (012), guardrail (014) with `timed(...)` + outcome logging; increment `guardrail_refusals_total`/`cross_tenant_blocks_total`/`agent_runs_total`/`agent_tool_calls_total` at the existing decision points.
7. **`prompts/`** registry files — `suggested_reply.system`, `agent.system`, `agent.tool_router`, `escalation.summary` (seed with the current inline prompts; version `1.0.0`).
8. **`ai/prompt_registry.py`** — load + hash-verify + `get(prompt_id)` → `PromptTemplate` (`render`, `ref`); fail fast on missing/mismatch.
9. **Replace inline prompts** — reply/agent/summary services load from the registry; record `prompt_ref` on the output (+ pair with `model_version`).
10. **Propagate `request_id`** — pass into audit (013)/guardrail (014)/agent-run (012) writes (nullable field or metadata).
11. **Config** — `AI_TRACE_ENABLED`, `LOG_LEVEL`, `METRICS_ENABLED`, `METRICS_ROLE`, `PROMPT_DIR`.

---

## Testing Tasks

- **Unit** — `PromptRegistry` load/hash-verify (`test_prompt_registry.py`): valid load; hash mismatch → fail fast; missing id → fail fast; `.render` substitutes vars; `.ref` = `prompt_id@version`+hash.
- **Unit** — redaction filter (`test_log_redaction.py`): secret/PII/system-prompt/message-body → redacted in the emitted line.
- **Integration** — correlation: one request → all step logs share `request_id`; audit/guardrail/agent records carry it (AC-01..AC-03).
- **Integration** — metrics: drive requests → `/metrics` increments counters + has latency observations; guardrail refusal / cross-tenant block increment their counters (AC-05..AC-07); `/metrics` aggregate-only + access-restricted (AC-08).
- **Integration** — prompt stamping: reply/agent/summary outputs record the registry `prompt_ref` matching the loaded entry (AC-13); ref carries no content (AC-14).
- **Integration** — prompt edit: bump a template version → service uses it (AC-11).
- **Redaction scan** — no secrets/PII/content in any log/metric (AC-04, AC-08, AC-14).
- **No-behavior-change** — existing 006/009/010/012/014 tests still pass (instrumentation is transparent) (AC-16).

---

## Build Order

1. **Request context + correlation middleware** + JSON logging with redaction filter.
2. **Timing + metrics** (`observability.py` + `/metrics`) and instrument the AI calls.
3. **Prompt registry** (`prompt_registry.py` + `prompts/*.yaml`) with hash-verify + fail-fast; unit tests.
4. **Replace inline prompts** in reply/agent/summary; stamp `prompt_ref` on outputs.
5. **Propagate `request_id`** into audit/guardrail/agent records.
6. **Validation** — correlation/metrics/prompt integration tests + redaction scan + no-behavior-change regression.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/019-observability-prompt-management/
├── plan.md
├── spec.md
├── quickstart.md
├── tasks.md
└── checklists/
    └── requirements.md
```

> No `data-model.md` or `contracts/api-contracts.md`: the prompt registry is **file-backed** (no new table), `/metrics` is a single read-only Prometheus endpoint (documented inline), and `request_id`/`prompt_ref` reuse existing records (a nullable column or metadata JSON, not a new entity).

### Source Code Layout

New files:

```
backend/app/core/request_context.py        # contextvars RequestContext
backend/app/core/logging.py                # JSON logging + redaction filter
backend/app/core/observability.py          # timed() + prometheus metrics
backend/app/api/middleware/correlation.py  # request_id middleware
backend/app/api/v1/metrics.py              # GET /metrics (restricted)
backend/app/ai/prompt_registry.py          # load + hash-verify + get()
backend/app/prompts/                        # versioned, hashed prompt templates (*.yaml)
backend/tests/unit/test_prompt_registry.py
backend/tests/unit/test_log_redaction.py
backend/tests/integration/test_observability.py
```

Modified files:

```
backend/app/main.py                         # add correlation middleware + mount /metrics + logging config
backend/app/services/<reply/agent/summary>  # load prompts from registry; stamp prompt_ref
backend/app/services/<classifier/rag/guardrail>  # wrap calls with timed() + metrics
backend/app/services/audit_service.py       # accept/propagate request_id
backend/app/core/config.py                  # AI_TRACE_ENABLED, METRICS_*, PROMPT_DIR
```

**Structure Decision**: A cross-cutting instrumentation + parameterization layer on the existing FastAPI backend. No new tenant-owned tables: the prompt registry is file-backed and versioned-as-code; observability emits structured logs + a restricted `/metrics` endpoint; correlation/prompt refs reuse existing records. The Spec 014 redactor is reused so no signal can leak secrets/PII/cross-tenant data.
