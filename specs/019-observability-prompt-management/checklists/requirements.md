# Requirements Checklist: Observability and Prompt Management

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-10
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (traceable, observable AI pipeline + reviewable versioned prompts)
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Security/privacy, Edge/Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicit (no external APM, no DB prompt UI, no business-logic change)

---

## Observability Requirements

- [ ] Every request gets/accepts a `request_id` on all its log lines (FR-001, AC-01)
- [ ] Structured JSON logs with request_id/tenant_id/user_id/component/latency_ms/outcome/level (FR-002, AC-02)
- [ ] `request_id` propagated into AI steps + audit/guardrail/agent records (FR-003, AC-03)
- [ ] Each AI call records latency + start/end (FR-004, AC-05)
- [ ] `/metrics` (Prometheus) exposes ai_calls/ai_latency/guardrail_refusals/cross_tenant_blocks/agent_runs/agent_tool_calls (FR-005, AC-06)
- [ ] Logs/metrics redacted; metrics aggregate-only labels (FR-006, AC-04, AC-08)
- [ ] `/metrics` restricted to operator/owner; not a tenant content route (FR-007, AC-08)
- [ ] Verbose AI logging config-gated; errors always logged (FR-013, AC-15)

---

## Prompt-Management Requirements

- [ ] Prompts loaded from a versioned registry, not hardcoded (FR-008, AC-09)
- [ ] Each entry has prompt_id/version/hash/template/metadata; hash matches content (FR-009, AC-10)
- [ ] Missing id or hash mismatch fails fast, no silent fallback (FR-010, AC-12)
- [ ] Each AI output records prompt_id@version (+ hash) used (FR-011, AC-13)
- [ ] Recorded prompt ref carries no secrets/PII/cross-tenant data (FR-012, AC-14)
- [ ] Editing a template + version bump → service uses new version; reviewable diff (AC-11)

---

## Security / Privacy Requirements

- [ ] Redact every emitted field (Spec 014 redactor) (SP-01, AC-04)
- [ ] Metrics aggregate-only; no tenant_id/message labels (SP-02, AC-08)
- [ ] `/metrics` not a tenant route; restricted access (SP-03, AC-08)
- [ ] Correlation ids carry no content (SP-04)
- [ ] Prompts carry no secrets/tenant data; tenant data injected at runtime (SP-05)
- [ ] Fail closed on prompt integrity (missing/mismatch) (SP-06, AC-12)
- [ ] No new autonomy/boundary change (SP-07, AC-16)

---

## Edge Cases Covered

- [ ] Inbound request-id header (trusted) vs generated; untrusted/oversized replaced
- [ ] High log volume → level/flag-gated verbose logging
- [ ] `/metrics` not public; aggregate-only
- [ ] Redaction in logs (no body/secret/system-prompt)
- [ ] Prompt hash mismatch → fail fast (no silent drift)
- [ ] Missing prompt at runtime → fail fast
- [ ] Bounded metric cardinality (no per-tenant/per-message labels)
- [ ] tenant_id correlates but never carries content; metrics never label tenant_id

---

## Implementation Readiness

- [ ] No new tenant-owned tables (file-backed registry; reuse existing records) — no data-model/contracts needed
- [ ] `/metrics` is a single documented read-only endpoint
- [ ] Spec 014 redactor reusable as a standalone util for logs/metrics
- [ ] No-behavior-change regression planned (existing AI specs' tests still pass)
- [ ] Build order: context+logging → timing+metrics → registry → replace prompts+stamp → propagate → validate
