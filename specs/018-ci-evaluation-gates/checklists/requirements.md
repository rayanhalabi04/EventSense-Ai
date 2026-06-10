# Requirements Checklist: CI Evaluation Gates

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-10
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (quality + safety as a blocking, visible merge condition)
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Operational rules, Edge/Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicit (no CD/deploy, no training, no online metrics)

---

## Functional Requirements

- [ ] CI triggers on every push/PR (FR-001, AC-01)
- [ ] Ordered pipeline: build → tests → stack up → smoke → eval suites (FR-002, AC-01)
- [ ] Build fails on test fail / smoke fail / classifier floor / RAG floor or cross-tenant / any guardrail / any isolation / wrong-or-autonomous agent (FR-003, AC-02..AC-07)
- [ ] Safety gates are zero-tolerance (FR-004, AC-04, AC-05)
- [ ] Thresholds in one committed `eval/thresholds.yaml`, read by CI only (FR-005, AC-09)
- [ ] Eval deterministic in CI (stub models + fixtures + eval tenants) (FR-006, AC-10)
- [ ] Summary + artifacts uploaded; per-gate summary surfaced (FR-007, AC-11)
- [ ] No secrets/prompts/cross-tenant data in artifacts/logs (FR-008, AC-12)
- [ ] Missing/malformed config or missing metric fails closed (FR-009, AC-13)
- [ ] Pipeline runs locally via one entrypoint `make ci` (FR-010, AC-14)
- [ ] No production secrets to untrusted/forked PRs (FR-011, AC-15)
- [ ] Reasonable time budget; fuller suite may run nightly (FR-012)

---

## Gate Coverage

- [ ] `tests` — any failure blocks
- [ ] `docker_smoke` — non-zero blocks
- [ ] `classifier` — macro-F1/accuracy floor
- [ ] `rag_retrieval` — hit@3/MRR/refusal floor + `no_cross_tenant_source_rate==1.0`
- [ ] `guardrail` — zero tolerance
- [ ] `tenant_isolation` — zero tolerance
- [ ] `agent_workflow` — wrong action / bound breach / autonomous side effect blocks

---

## Operational / Security Requirements

- [ ] Safety is zero-tolerance, never averaged with quality (OR-01)
- [ ] Thresholds explicit + committed; loosening is a reviewed diff (OR-02)
- [ ] Deterministic gates (no external flake flips a gate) (OR-03)
- [ ] No secret exposure to untrusted PRs; redacted artifacts (OR-04)
- [ ] Fail closed on missing config/artifact/metric (OR-05)
- [ ] Reproducible locally via `make ci` (OR-06)

---

## Edge Cases Covered

- [ ] Flaky external dependency → stub/deterministic, no gate flip
- [ ] Missing classifier artifact → fail fast
- [ ] Empty/partial golden set → required-metric gap fails (no silent skip)
- [ ] Threshold file missing/malformed → fail closed
- [ ] Long runtime → bounded/sampled per-PR; nightly fuller
- [ ] Forked PR secrets → gated to trusted runs
- [ ] Single safety failure → hard stop regardless of quality

---

## Implementation Readiness

- [ ] Gate-script logic is unit-testable offline (synthetic summaries)
- [ ] No new persisted entities/endpoints — no data-model/contracts needed
- [ ] Headless entrypoints for Spec 015 suites + Spec 017 smoke confirmed
- [ ] Validation induces a regression per gate and asserts the build fails + reverts pass
