# Implementation Plan: CI Evaluation Gates

**Branch**: `018-ci-evaluation-gates` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/018-ci-evaluation-gates/spec.md`

**Depends on**:
- [Spec 015 — Evaluation](../015-evaluation/plan.md): the suites + `summary_metrics` the gates read
- [Spec 017 — Dockerized Stack](../017-dockerized-stack/plan.md): stack up + Docker smoke test in CI
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): classifier metrics floor
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/plan.md): RAG metrics floor
- [Spec 014 — Guardrails](../014-guardrails/plan.md) + [Spec 001](../001-multi-tenant-workspace/plan.md): zero-tolerance safety/isolation gates

---

## Summary

Add a CI pipeline (GitHub Actions) that runs tests + the Spec 017 stack/smoke + the Spec 015 eval suites on every push/PR and **fails the build** on quality or safety regression. A single committed `eval/thresholds.yaml` holds the floors and zero-tolerance flags; a small gate script (`scripts/ci_gate.py`) reads Spec 015 `summary_metrics` + the Docker smoke JSON and decides pass/fail. The same pipeline runs locally via `make ci`. No application business logic changes.

---

## Technical Approach

- **Workflow**: `.github/workflows/ci.yml` with ordered stages (jobs/steps): `build` → `tests` → `stack-up` → `docker-smoke` → `eval` → `gate` → `publish`. Use the `pgvector/pgvector:pg16` service (or compose) for DB-backed tests/eval.
- **Determinism**: set `APP_ENV=test`, use the local/stub embedding + reply models and the calibrated-SVM artifact (committed); no real LLM/embedding API keys needed for the core gates. Versioned fixtures + seeded eval tenants make results reproducible.
- **Gate script** (`scripts/ci_gate.py`): inputs = Spec 015 run summaries (JSON in `eval-artifacts/`) + `eval-artifacts/docker_smoke.json` + `eval/thresholds.yaml`. Logic:
  - `classifier`: fail if `macro_f1 < floor` or `accuracy < floor`.
  - `rag_retrieval`: fail if `hit_at_3 < floor` or `mrr < floor` or `refusal_correctness < floor` or `no_cross_tenant_source_rate < 1.0`.
  - `guardrail`, `tenant_isolation`: fail if any case `passed=false` (zero tolerance).
  - `agent_workflow`: fail on wrong action / bound breach / any autonomous side effect.
  - `docker_smoke`: fail if `passed=false`.
  - Missing required metric / malformed config → fail closed (exit non-zero) with a clear message.
  - Print a per-gate table; write `eval-artifacts/gate_summary.md` for the job summary.
- **Thresholds config** (`eval/thresholds.yaml`): committed defaults, e.g.
  ```yaml
  classifier: { macro_f1_floor: 0.80, accuracy_floor: 0.82 }
  rag_retrieval: { hit_at_3_floor: 0.70, mrr_floor: 0.60, refusal_correctness_floor: 0.90 }
  safety: { guardrail_zero_tolerance: true, isolation_zero_tolerance: true }
  ```
  (Defaults are starting points; tune from the first real eval run.)
- **Local parity**: `make ci` runs the same stages (tests → compose up → smoke → eval → gate) so a contributor reproduces a gate failure before pushing.
- **Secrets on forks**: core gates need no secrets; any optional secret-dependent stage uses `if: github.event.pull_request.head.repo.full_name == github.repository` (trusted) and is skipped (non-blocking) on forks.
- **Time budget**: per-PR eval uses bounded/sampled fixtures; a scheduled nightly workflow runs the fuller set.
- **Publish**: upload `eval-artifacts/**` via `actions/upload-artifact`; write the per-gate summary to `$GITHUB_STEP_SUMMARY`; optionally post a PR comment.

---

## CI / Tooling Tasks

1. **`.github/workflows/ci.yml`** — push/PR triggers; ordered stages; pgvector service/compose; artifact upload; job summary.
2. **`.github/workflows/nightly.yml`** (optional) — scheduled fuller eval run.
3. **`eval/thresholds.yaml`** — committed floors + zero-tolerance flags (the only threshold source).
4. **`scripts/ci_gate.py`** — read Spec 015 summaries + smoke JSON + thresholds → per-gate pass/fail → fail closed on gaps → write `gate_summary.md`.
5. **`Makefile` `ci` target** — local parity (tests → compose up → smoke → eval → gate).
6. **Eval headless entrypoints** — ensure Spec 015 suites + Spec 017 smoke run non-interactively and write JSON to `eval-artifacts/` (coordinate with 015/017; add a thin CLI wrapper if needed).
7. **Fork-secret guarding** — gate secret-dependent steps to trusted runs.

---

## Testing Tasks

- **Gate-script unit tests** (`tests/unit/test_ci_gate.py`): given synthetic summaries, assert pass/fail per gate (classifier floor, RAG floor, cross-tenant=fail, any guardrail/isolation fail, smoke fail, missing metric → fail closed, malformed config → fail).
- **Workflow dry-run**: open a PR → assert stages run in order and statuses surface.
- **Induced regressions** (behind flags/stubs): classifier below floor; one red-team case passing through; an isolation leak; a broken smoke → assert the build fails naming the gate. Revert → passes.
- **Redaction scan**: CI artifacts/logs contain no secrets/prompts/cross-tenant data.
- **Local parity**: `make ci` reproduces a failing gate locally.

---

## Build Order

1. **Headless entrypoints** — confirm Spec 015 suites + Spec 017 smoke emit JSON to `eval-artifacts/`.
2. **Threshold config** — `eval/thresholds.yaml` with committed defaults.
3. **Gate script** — `scripts/ci_gate.py` + its unit tests (the decision logic, testable offline).
4. **Workflow** — `.github/workflows/ci.yml` wiring stages + artifact upload + job summary.
5. **Local parity** — `make ci`.
6. **Validation** — induced regressions per gate; fork-secret guard; redaction scan; nightly (optional).

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/018-ci-evaluation-gates/
├── plan.md
├── spec.md
├── quickstart.md
├── tasks.md
└── checklists/
    └── requirements.md
```

> No `data-model.md` or `contracts/api-contracts.md` — this feature adds CI config + a gate script over Spec 015 outputs; it introduces no persisted entities or HTTP endpoints.

### Source Code Layout

New files:

```
.github/workflows/ci.yml
.github/workflows/nightly.yml          # optional fuller scheduled run
eval/thresholds.yaml                   # the single committed threshold source
scripts/ci_gate.py                     # reads Spec 015 summaries + smoke JSON → pass/fail
backend/tests/unit/test_ci_gate.py     # gate-logic unit tests
```

Modified files:

```
Makefile                               # add `ci` target (local parity)
```

**Structure Decision**: CI is a thin, deterministic gate over the Spec 015 eval outputs and the Spec 017 smoke test. The only new "logic" is the threshold-comparison script (unit-tested offline); the workflow orchestrates existing suites. Safety gates are zero-tolerance; quality gates are numeric floors in a committed config.
