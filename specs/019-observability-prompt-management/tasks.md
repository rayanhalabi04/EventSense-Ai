---
description: "Task list for Observability and Prompt Management feature implementation"
---

# Tasks: Observability and Prompt Management

**Branch**: `019-observability-prompt-management` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/019-observability-prompt-management/` (spec.md, plan.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 013 — Audit Logs: `AuditService.log_event`; records can carry `request_id`
- Spec 014 — Guardrails: the **redactor** (reused for log/metric fields); refusal/cross-tenant decision points
- Spec 006/009/010/012 — the AI calls instrumented + the prompts moved into the registry

**Tech stack**: FastAPI + SQLAlchemy 2.x async + pydantic v2 · stdlib `logging` JSON (or structlog) · `prometheus_client` · `contextvars` · file-backed YAML prompt registry

**No new tenant-owned tables**: prompt registry is file-backed; `request_id`/`prompt_ref` reuse existing records (nullable column or metadata JSON); `/metrics` is a single read-only endpoint.

## Format: `[ID] [P?] [Story?] Description`
- `[P]` = parallelizable (different files, no dependency)
- `[Story]` = the user story the task serves (US1–US4)

---

## Phase 1 — Correlation + structured logging (US1)

- [ ] T001 [US1] `core/request_context.py` — `contextvars` `RequestContext` (`request_id`/`tenant_id`/`user_id`) + accessors.
- [ ] T002 [US1] `api/middleware/correlation.py` — accept trusted `X-Request-Id` or generate UUID; populate context; set `X-Request-Id` response header; register in `main.py`.
- [ ] T003 [US1] `core/logging.py` — JSON formatter + a **redaction filter** (reuses Spec 014 redactor) + `LOG_LEVEL`/`AI_TRACE_ENABLED` gating.
- [ ] T004 [P] [US1] Unit test `test_log_redaction.py` — secret/PII/system-prompt/message-body → redacted in the emitted line (AC-04).

## Phase 2 — Timing + metrics (US2)

- [ ] T005 [US2] `core/observability.py` — `timed(component)` decorator/context manager + `prometheus_client` metric defs (`ai_calls_total`, `ai_latency_ms`, `guardrail_refusals_total`, `cross_tenant_blocks_total`, `agent_runs_total`, `agent_tool_calls_total`).
- [ ] T006 [US2] `api/v1/metrics.py` — `GET /metrics` (Prometheus text); operator/owner-restricted; not a tenant content route; mount in `main.py`.
- [ ] T007 [US2] Instrument AI calls — wrap classifier (006), RAG (009), reply (010), agent + tools (012), guardrail (014) with `timed(...)` + outcome logging.
- [ ] T008 [US2] Increment `guardrail_refusals_total{category}` / `cross_tenant_blocks_total` / `agent_runs_total` / `agent_tool_calls_total{tool}` at the existing decision points.
- [ ] T009 [P] [US2] Integration test — `/metrics` increments counters + has latency observations; refusal/cross-tenant increment counters; aggregate-only + access restricted (AC-05..AC-08).

## Phase 3 — Prompt registry (US3)

- [ ] T010 [US3] `prompts/*.yaml` — seed `suggested_reply.system`, `agent.system`, `agent.tool_router`, `escalation.summary` from the current inline prompts (version `1.0.0`, computed hash).
- [ ] T011 [US3] `ai/prompt_registry.py` — load all templates at startup, compute + verify content hash, `get(prompt_id)` → `PromptTemplate` (`.render(**vars)`, `.ref`); **fail fast** on missing id / hash mismatch.
- [ ] T012 [P] [US3] Unit test `test_prompt_registry.py` — valid load; hash mismatch → fail fast; missing id → fail fast; `.render` substitutes vars; `.ref` = `prompt_id@version`+hash (AC-10, AC-12).
- [ ] T013 [US3] Replace inline prompt strings in reply/agent/summary services with `registry.get(...)` (AC-09).

## Phase 4 — Output → prompt traceability + correlation propagation (US4)

- [ ] T014 [US4] Stamp `prompt_ref` (`prompt_id@version`+hash) on each AI output — suggested-reply record, agent-run record, escalation summary — paired with `model_version` (006). Use a column or metadata JSON (no new table).
- [ ] T015 [US4] Propagate `request_id` into audit (013) / guardrail (014) / agent-run (012) writes (nullable field or metadata).
- [ ] T016 [P] [US4] Integration test — outputs record the registry `prompt_ref` matching the loaded entry; ref carries no content; records carry `request_id` (AC-13, AC-14, AC-03).

## Phase 5 — Config + validation

- [ ] T017 [US1/US2/US3] `core/config.py` — `AI_TRACE_ENABLED`, `LOG_LEVEL`, `METRICS_ENABLED`, `METRICS_ROLE`, `PROMPT_DIR`.
- [ ] T018 Integration test — one request → all step logs share `request_id`; audit/guardrail/agent carry it (AC-01..AC-03).
- [ ] T019 [P] Integration test — bump a template version → service uses the new version; change is a reviewable diff (AC-11).
- [ ] T020 [P] Config test — verbose AI logging gated by `AI_TRACE_ENABLED`/`LOG_LEVEL`; errors always logged (AC-15).
- [ ] T021 [P] Redaction scan — no secrets/PII/system prompts/message bodies/cross-tenant data in any log/metric/prompt-ref (AC-04, AC-08, AC-14).
- [ ] T022 [P] No-behavior-change regression — existing 006/009/010/012/014 tests still pass; isolation/guardrails/human-review unchanged (AC-16).

---

## Dependencies / ordering

- T001–T003 (context + logging) before instrumenting calls (T007).
- T005–T006 (metrics + endpoint) before T007–T009.
- T010–T011 (registry) before T013 (replace inline prompts) and T014 (stamp refs).
- Validation (T018–T022) after the layer is wired.
- `[P]` tasks touch different files and can run in parallel.

## Acceptance mapping

- US1 → AC-01, AC-02, AC-03, AC-04 (correlation + structured redacted logs)
- US2 → AC-05, AC-06, AC-07, AC-08 (latency + metrics, aggregate + restricted)
- US3 → AC-09, AC-10, AC-11, AC-12 (registry-loaded, hashed, versioned, fail-fast)
- US4 → AC-13, AC-14 (output → prompt ref); AC-15, AC-16 (gating + no behavior change)
