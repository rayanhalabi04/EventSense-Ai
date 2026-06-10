---
description: "Task list for CI Evaluation Gates feature implementation"
---

# Tasks: CI Evaluation Gates

**Branch**: `018-ci-evaluation-gates` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/018-ci-evaluation-gates/` (spec.md, plan.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 015 — Evaluation: suites emit `summary_metrics` JSON to `eval-artifacts/`
- Spec 017 — Dockerized Stack: `docker compose up` + smoke writing `eval-artifacts/docker_smoke.json`
- Spec 006/009/014/001 — the gated components (classifier, RAG, guardrails, tenant isolation)

**Tech stack**: GitHub Actions · Python gate script (stdlib + PyYAML) · pytest · Docker Compose · `pgvector/pgvector:pg16`

**No new schema / no HTTP endpoints** — CI config + a threshold file + a gate script over Spec 015 outputs.

## Format: `[ID] [P?] [Story?] Description`
- `[P]` = parallelizable (different files, no dependency)
- `[Story]` = the user story the task serves (US1–US4)

---

## Phase 1 — Headless entrypoints (US1)

- [ ] T001 [US1] Confirm Spec 015 suites run non-interactively and write per-area JSON summaries to `eval-artifacts/` (add a thin CLI wrapper `python -m app.eval.run --area <area> --out eval-artifacts/` if missing).
- [ ] T002 [US1] Confirm Spec 017 smoke writes `eval-artifacts/docker_smoke.json` and exits non-zero on failure.

## Phase 2 — Threshold config + gate script (US2/US3)

- [ ] T003 [US3] Add `eval/thresholds.yaml` with committed defaults (classifier floors, RAG floors, safety zero-tolerance flags).
- [ ] T004 [US2] Implement `scripts/ci_gate.py`: load thresholds + Spec 015 summaries + `docker_smoke.json`; evaluate each gate; **fail closed** on missing config/metric; print a per-gate table; write `eval-artifacts/gate_summary.md`; exit non-zero on any failure.
- [ ] T005 [US2] Gate logic — classifier (macro_f1/accuracy floors), rag_retrieval (hit@3/mrr/refusal floors + `no_cross_tenant_source_rate==1.0`), guardrail + tenant_isolation (zero tolerance), agent_workflow (wrong/autonomous → fail), docker_smoke.
- [ ] T006 [P] [US2] Unit tests `backend/tests/unit/test_ci_gate.py`: synthetic summaries → assert pass/fail per gate, zero-tolerance behavior, fail-closed on missing metric/malformed config.

## Phase 3 — CI workflow (US1/US2/US4)

- [ ] T007 [US1] `.github/workflows/ci.yml`: push/PR triggers; ordered stages build → tests → stack-up → docker-smoke → eval → gate → publish; pgvector service/compose; `APP_ENV=test`, stub models.
- [ ] T008 [US4] Upload `eval-artifacts/**` (`actions/upload-artifact`); write `gate_summary.md` to `$GITHUB_STEP_SUMMARY`; optional PR comment.
- [ ] T009 [US2] Wire the `gate` step to run `scripts/ci_gate.py` and fail the job on non-zero exit.
- [ ] T010 [P] [US1] `.github/workflows/nightly.yml` (optional) — scheduled fuller eval run on the complete fixture set.
- [ ] T011 [US4] Fork-secret guarding — gate any secret-dependent step to trusted runs; core gates need no secrets.

## Phase 4 — Local parity (US2)

- [ ] T012 [US2] Add a `Makefile` `ci` target running the same stages locally (tests → compose up → smoke → eval → gate), exiting non-zero on gate failure.

## Phase 5 — Validation

- [ ] T013 Dry-run a PR → assert stages run in order and per-stage status surfaces (AC-01).
- [ ] T014 Induced regression — classifier below floor → build fails naming the gate/metric; revert → passes (AC-02, AC-08).
- [ ] T015 [P] Induced regression — RAG below floor / a cross-tenant source → build fails (AC-03).
- [ ] T016 [P] Induced regression — one red-team case passes through → build fails (zero tolerance) (AC-04).
- [ ] T017 [P] Induced regression — an isolation probe leaks → build fails (zero tolerance) (AC-05).
- [ ] T018 [P] Induced regression — stop a stack service → smoke fails → build fails (AC-06).
- [ ] T019 [P] Induced regression — wrong/autonomous agent action → build fails (AC-07).
- [ ] T020 [P] Config gap — missing/malformed `thresholds.yaml` or missing metric → build fails (fail closed) (AC-13).
- [ ] T021 [P] Redaction scan — CI artifacts/logs carry no secrets/prompts/cross-tenant data (AC-12).
- [ ] T022 [P] Local parity — `make ci` reproduces a failing gate (AC-14); fork run gets no secrets (AC-15).

---

## Dependencies / ordering

- T001–T002 (headless outputs) before the gate script can consume them.
- T003–T006 (config + gate + tests) before T007–T009 (workflow wiring).
- Validation (T013–T022) after the workflow + `make ci` exist.
- `[P]` tasks touch different files / induce independent regressions and can run in parallel.

## Acceptance mapping

- US1 → AC-01, AC-10 (pipeline runs in order, deterministic)
- US2 → AC-02..AC-08, AC-13, AC-14 (blocking behavior + local parity + fail-closed)
- US3 → AC-09 (committed, reviewable thresholds)
- US4 → AC-11, AC-12, AC-15 (publish, redaction, fork-secret safety)
