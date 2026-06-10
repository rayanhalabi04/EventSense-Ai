# Feature Specification: CI Evaluation Gates

**Feature Branch**: `018-ci-evaluation-gates`

**Created**: 2026-06-10

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 014 — Guardrails](../014-guardrails/spec.md)
- [Spec 015 — Evaluation](../015-evaluation/spec.md)
- [Spec 017 — Dockerized Stack](../017-dockerized-stack/spec.md)

**Input**: User description: "Continuous integration should automatically run the test suites and the evaluation harness on every push/PR, and fail the build when quality or safety regresses — classifier accuracy below threshold, RAG retrieval below threshold, any guardrail/red-team failure, any tenant-isolation failure, or a broken Docker smoke test."

---

## Goal

Turn the Spec 015 evaluation harness from an on-demand convenience into an **automated quality and safety gate**. On every push and pull request, CI builds the project, runs unit + integration tests, brings up the Spec 017 stack, runs the Docker smoke test, and runs the evaluation suites (classifier, RAG retrieval, guardrail/red-team, tenant isolation, agent workflow). The build **fails** when a measurable threshold regresses — classifier macro-F1/accuracy below a floor, RAG hit@k/refusal-correctness below a floor, **any** guardrail/red-team case failing, **any** tenant-isolation probe failing, or the Docker smoke test broken. Thresholds live in a single committed config so they are reviewable and tunable. CI publishes the evaluation summary + artifacts (JSON/Markdown) on each run so reviewers see the numbers in the PR. This makes "the AI still works and is still safe" a **blocking, visible** condition for merging — closing the loop the Spec 015 Out-of-Scope note left open ("CI evaluation gating — deferred").

---

## Gate Categories

| Gate | Source | Fail condition (default) |
|------|--------|--------------------------|
| `tests` | backend unit + integration (pytest) | Any test fails |
| `docker_smoke` | Spec 017 smoke test | Smoke exits non-zero |
| `classifier` | Spec 015 `classifier` area | `macro_f1` or `accuracy` below floor |
| `rag_retrieval` | Spec 015 `rag_retrieval` area | `hit_at_3`/`mrr`/`refusal_correctness` below floor; `no_cross_tenant_source_rate` < 1.0 |
| `guardrail` | Spec 015 `guardrail` (red-team) area | Any red-team case fails (zero tolerance) |
| `tenant_isolation` | Spec 015 `tenant_isolation` area | Any isolation probe fails (zero tolerance) |
| `agent_workflow` | Spec 015 `agent_workflow` area | Wrong action recommendation, bound not respected, or any autonomous side effect |

> Safety gates (`guardrail`, `tenant_isolation`) are **zero-tolerance** (any failure fails the build). Quality gates (`classifier`, `rag_retrieval`) use **numeric thresholds**.

---

## Main Users

| Role | Description |
|------|-------------|
| **Developer / contributor** | Pushes commits / opens PRs; reads the CI gate result and the published eval summary; fixes regressions before merge. |
| **Project owner / reviewer** | Sets and reviews thresholds in the committed config; uses the gate as the merge condition; reads artifacts in the PR. |
| **CI runner** (automation) | Executes the pipeline: build → tests → stack up → smoke → eval suites → threshold check → publish. No human in the loop. |

---

## User Stories

### User Story 1 — CI Runs Tests, Smoke, and Eval on Every Push/PR (Priority: P1)

When a contributor pushes a branch or opens a PR, CI checks out the code, installs dependencies, runs the backend unit + integration test suites, brings up the Spec 017 stack, runs the Docker smoke test, and runs the Spec 015 evaluation suites against the seeded eval tenants/fixtures. The job is reproducible (same images, same fixtures) and reports each stage's result.

**Why this priority**: Automation is the feature — without CI running these on every change, the gate cannot exist. Every other story depends on the pipeline running.

**Independent Test**: Open a PR with a trivial change; assert the CI workflow triggers, runs `tests`, `docker_smoke`, and the eval suites, and reports per-stage status in the checks UI.

**Acceptance Scenarios**:

1. **Given** a push or PR, **When** CI triggers, **Then** it runs (in order) build → unit/integration tests → stack up → Docker smoke → eval suites, and surfaces each stage's pass/fail.
2. **Given** the eval suites, **When** they run in CI, **Then** they use the deterministic fixtures/golden sets and the seeded eval tenants (no flaky external calls), and produce the Spec 015 `EvaluationRun` summaries/artifacts.
3. **Given** any infrastructure failure (image build, DB up), **When** it occurs, **Then** CI fails with a clear stage error (not a false green).

---

### User Story 2 — The Build Fails on Quality or Safety Regression (Priority: P1)

CI compares the eval results against committed thresholds and **fails the build** if any gate regresses: classifier below its accuracy/macro-F1 floor, RAG below its hit@k/refusal floor or with any cross-tenant source, **any** guardrail/red-team case failing, **any** tenant-isolation probe failing, the agent recommending a wrong/autonomous action, or the Docker smoke test broken. A passing build means all gates held.

**Why this priority**: A pipeline that runs but never blocks is just logging. The blocking behavior is what protects quality and safety. Equal P1.

**Independent Test**: Introduce a regression behind a flag (e.g., a stub that drops classifier accuracy below the floor, or a guardrail that lets one red-team case through); assert CI **fails** and names the failing gate + metric. Revert; assert CI passes.

**Acceptance Scenarios**:

1. **Given** classifier macro-F1/accuracy below the configured floor, **When** the gate evaluates, **Then** the build **fails** and reports the metric, the floor, and the gate name.
2. **Given** RAG hit@3/MRR/refusal-correctness below the floor **or** `no_cross_tenant_source_rate < 1.0`, **When** the gate evaluates, **Then** the build **fails**.
3. **Given** **any** guardrail/red-team case failing, **When** the gate evaluates, **Then** the build **fails** (zero tolerance) and names the failing case category.
4. **Given** **any** tenant-isolation probe failing (A reads B's data/chunk), **When** the gate evaluates, **Then** the build **fails** (zero tolerance).
5. **Given** a broken Docker smoke test, **When** the gate evaluates, **Then** the build **fails**.
6. **Given** all gates within thresholds, **When** the gate evaluates, **Then** the build **passes**.

---

### User Story 3 — Thresholds Are Committed, Reviewable, and Tunable (Priority: P2)

The pass/fail thresholds live in a single committed config file (e.g., `eval/thresholds.yaml`) — classifier floors, RAG floors, and the zero-tolerance flags for safety gates. Changing a threshold is a reviewable diff. CI reads this file; no thresholds are hidden in pipeline YAML or code.

**Why this priority**: Tunable, reviewable thresholds keep the gate honest (no silent loosening) but the gate works with sensible defaults first. P2.

**Independent Test**: Lower the classifier floor in `eval/thresholds.yaml` in a PR; assert CI reads the new value (a previously-failing run now passes) and the change is a visible diff. Confirm safety gates cannot be set below zero-tolerance without an explicit, reviewed change.

**Acceptance Scenarios**:

1. **Given** `eval/thresholds.yaml`, **When** CI runs, **Then** it reads classifier/RAG floors and safety zero-tolerance flags from that file only.
2. **Given** a threshold change, **When** it is committed, **Then** it appears as a reviewable diff and takes effect on the next run.
3. **Given** the safety gates, **When** configured, **Then** loosening them (allowing a guardrail/isolation failure) requires an explicit, reviewed config change — not a default.

---

### User Story 4 — Results Are Published on the PR (Priority: P2)

CI uploads the evaluation summary + artifacts (JSON/Markdown) as build artifacts and posts/links a concise summary (per-gate pass/fail + key metrics) so a reviewer sees the numbers without digging through logs. Artifacts contain no secrets/prompts/cross-tenant data (Spec 015 redaction).

**Why this priority**: Visibility makes the gate actionable and the project defensible, but the blocking behavior already protects the branch. P2.

**Independent Test**: On a PR run, assert the eval summary is attached as an artifact and a short per-gate summary is visible on the run; assert no secrets/prompts/cross-tenant data appear.

**Acceptance Scenarios**:

1. **Given** a completed CI run, **When** it finishes, **Then** the eval summary + JSON/Markdown artifacts are uploaded and retrievable from the run.
2. **Given** a PR, **When** CI completes, **Then** a concise per-gate summary (pass/fail + key metrics) is surfaced (job summary or PR comment).
3. **Given** published artifacts, **When** inspected, **Then** they contain no secrets/JWTs/system prompts/cross-tenant data (Spec 015 redaction holds in CI).

---

### Edge Cases

- **Flaky external dependency** (e.g., embedding/LLM API): CI uses deterministic local/stub models and fixtures so gates are reproducible; a network flake does not flip a gate.
- **Missing classifier artifact in CI**: the `classifier`/`docker_smoke` stages fail fast (harness error), not a fake pass.
- **Empty/partial golden set**: the harness reports "no golden cases" (Spec 015) and the gate treats a missing required metric as a failure (not a silent skip).
- **Threshold file missing/malformed**: CI fails with a clear config error rather than running ungated.
- **Long eval runtime**: suites are bounded (sampled fixtures where appropriate) so CI stays within a reasonable time budget; the full set can run on a nightly schedule.
- **Forked PRs / secrets**: gates that need no secrets run on forks; anything needing secrets is gated to trusted runs — never exposing secrets to untrusted PRs.
- **Regression in safety = hard stop**: a single guardrail/isolation failure fails the build regardless of quality metrics (safety is not averaged away).
- **Quality just below floor**: fails with the exact metric vs floor so the author can decide to fix or (via reviewed config) adjust the floor.

---

## Requirements

### Functional Requirements

- **FR-001**: CI MUST trigger on every push and pull request to run the gate pipeline.
- **FR-002**: The pipeline MUST run, in order: dependency install/build → backend unit + integration tests → Spec 017 stack up → Docker smoke test → Spec 015 eval suites (`classifier`, `rag_retrieval`, `guardrail`, `tenant_isolation`, `agent_workflow`).
- **FR-003**: The pipeline MUST **fail the build** when: any test fails; the Docker smoke test exits non-zero; classifier `macro_f1`/`accuracy` is below the configured floor; RAG `hit_at_3`/`mrr`/`refusal_correctness` is below the floor or `no_cross_tenant_source_rate < 1.0`; **any** guardrail/red-team case fails; **any** tenant-isolation probe fails; or the agent recommends a wrong/autonomous action.
- **FR-004**: Safety gates (`guardrail`, `tenant_isolation`, agent no-autonomous-side-effect) MUST be **zero-tolerance** — a single failure fails the build.
- **FR-005**: Quality thresholds MUST live in a single committed config file (`eval/thresholds.yaml`) read by CI; no thresholds hidden in pipeline YAML or code.
- **FR-006**: The eval suites in CI MUST be **deterministic** — local/stub models + versioned fixtures + seeded eval tenants; no flaky external calls decide a gate.
- **FR-007**: CI MUST upload the Spec 015 evaluation summary + artifacts (JSON/Markdown) and surface a concise per-gate summary on the run/PR.
- **FR-008**: Published artifacts/logs MUST contain no secrets/JWTs/system prompts/cross-tenant data (Spec 015 redaction MUST hold in CI).
- **FR-009**: A missing/malformed threshold file, missing classifier artifact, or missing required metric MUST fail the build (no silent skip / no false pass).
- **FR-010**: The pipeline MUST be runnable **locally** with the same entrypoint (e.g., `make ci` / a script) so a contributor can reproduce a gate failure before pushing.
- **FR-011**: CI MUST NOT require or expose production secrets to untrusted (forked) PRs; secret-dependent stages are gated to trusted runs.
- **FR-012**: The pipeline SHOULD keep within a reasonable time budget (bounded/sampled fixtures); a fuller suite MAY run on a scheduled (nightly) job.

### Key Entities

- **CI workflow** (new): the pipeline definition (`.github/workflows/ci.yml` or equivalent) with ordered stages.
- **Threshold config** (new): `eval/thresholds.yaml` — classifier/RAG floors + safety zero-tolerance flags.
- **Gate result** (new, ephemeral): per-gate pass/fail + metric vs floor, computed from Spec 015 `summary_metrics`.
- **Published artifacts**: Spec 015 JSON/Markdown exports + the Docker smoke JSON, attached to the run.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Push / PR event | VCS | Triggers the pipeline |
| Repo code + fixtures | Checkout | Code, golden/eval fixtures, seed |
| `eval/thresholds.yaml` | Committed config | Floors + safety flags read by the gate step |
| Spec 017 stack | Compose | Brought up in CI for smoke + eval |
| Spec 015 harness | Eval scripts | Produces `summary_metrics` per area |

---

## Outputs

| Output | Description |
|--------|-------------|
| Build status | Pass/fail check on the commit/PR |
| Per-gate summary | Each gate's pass/fail + metric vs floor (job summary / PR comment) |
| Uploaded artifacts | Spec 015 JSON/Markdown + Docker smoke JSON |
| Failure reason | The failing gate + metric vs floor (or the failing safety case) |

---

## Main Workflow

1. **Trigger** — a push/PR starts the CI workflow.
2. **Build + install** — dependencies installed; backend (and frontend) build.
3. **Tests** — backend unit + integration suites run; any failure fails the build.
4. **Stack up** — the Spec 017 compose stack starts (postgres/pgvector + migrate + seed + api).
5. **Docker smoke** — Spec 017 smoke test runs; non-zero exit fails the build.
6. **Eval suites** — Spec 015 `classifier`, `rag_retrieval`, `guardrail`, `tenant_isolation`, `agent_workflow` run on fixtures/eval tenants, producing `summary_metrics`.
7. **Gate check** — CI reads `eval/thresholds.yaml` and compares; any quality floor breach or any safety failure fails the build.
8. **Publish** — upload summary + artifacts; surface the per-gate summary on the run/PR.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | CI triggers on push/PR and runs tests → stack → smoke → eval in order | PR run inspection |
| AC-02 | Build fails when classifier macro-F1/accuracy is below the floor | Induced regression run |
| AC-03 | Build fails when RAG hit@3/MRR/refusal below floor or any cross-tenant source | Induced regression run |
| AC-04 | Build fails on ANY guardrail/red-team case failure (zero tolerance) | Induced bypass run |
| AC-05 | Build fails on ANY tenant-isolation probe failure (zero tolerance) | Induced leak run |
| AC-06 | Build fails on a broken Docker smoke test | Stopped-service run |
| AC-07 | Build fails on a wrong/autonomous agent action | Induced agent regression |
| AC-08 | Build passes when all gates are within thresholds | Clean run |
| AC-09 | Thresholds read only from committed `eval/thresholds.yaml`; changes are reviewable diffs | Config-change PR |
| AC-10 | Eval suites are deterministic in CI (no flaky external call flips a gate) | Repeat runs identical |
| AC-11 | Summary + artifacts uploaded; per-gate summary surfaced on the run/PR | Artifact + summary review |
| AC-12 | No secrets/prompts/cross-tenant data in CI artifacts/logs | Redaction scan |
| AC-13 | Missing/malformed threshold file or missing required metric fails the build (no silent skip) | Induced config/metric gap |
| AC-14 | The pipeline runs locally via one entrypoint (`make ci`) reproducing a failure | Local run |
| AC-15 | Forked PRs do not get production secrets; secret stages gated to trusted runs | Fork run inspection |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 015 — Evaluation | Required | Provides the suites + `summary_metrics` the gates read |
| Spec 017 — Dockerized Stack | Required | Stack up + Docker smoke test run in CI |
| Spec 006 — Intent Classifier | Required | Classifier metrics gated (macro-F1/accuracy floor) |
| Spec 009 — RAG Over Tenant Documents | Required | RAG metrics gated (hit@k/refusal/no-cross-tenant) |
| Spec 014 — Guardrails | Required | Red-team suite gated (zero tolerance) |
| Spec 001 — Multi-Tenant Workspace | Required | Tenant-isolation suite gated (zero tolerance) |
| CI provider (GitHub Actions) | Required | Executes the workflow; no app code change |

---

## Security / Operational Rules

| Rule | Description |
|------|-------------|
| **OR-01: Safety is zero-tolerance** | A single guardrail/red-team or tenant-isolation failure fails the build; safety is never averaged with quality. |
| **OR-02: Thresholds are explicit + committed** | Floors live in `eval/thresholds.yaml`; loosening a gate is a reviewed diff, never a hidden default. |
| **OR-03: Deterministic gates** | Local/stub models + versioned fixtures + seeded eval tenants; no external flake decides merge-ability. |
| **OR-04: No secret exposure** | Production secrets are never exposed to untrusted PRs; artifacts/logs carry no secrets/prompts/cross-tenant data (Spec 015 redaction). |
| **OR-05: Fail closed** | Missing config/artifact/metric fails the build rather than running ungated. |
| **OR-06: Reproducible locally** | The same gate runs via `make ci` so a contributor can fix before pushing. |

---

## Out of Scope

- **Deploying** on green (CD / release automation) — gating only; deployment is separate.
- **Online/production metrics or live A/B gating** — gates run on fixtures/eval tenants, not production traffic.
- **Auto-tuning thresholds** — thresholds are human-set, committed values.
- **Training/retraining models in CI** — CI evaluates the committed artifact; training is offline (Spec 006).
- **Non-GitHub CI providers' specifics** — one provider for the MVP; the entrypoint is portable (`make ci`).
- **Real WhatsApp API, calendar sync, billing, mobile app, full CRM** — out of scope entirely.
- **Changing application business logic** — this feature adds CI + a threshold config only.

---

## Assumptions

- The repo uses GitHub Actions (or an equivalent) for CI; the gate logic is a thin script over Spec 015 outputs so it is provider-portable.
- Spec 015 suites and Spec 017 smoke test are implemented and runnable headlessly with deterministic fixtures + local/stub models.
- `eval/thresholds.yaml` is the single source of pass/fail thresholds; sensible defaults are committed (e.g., classifier macro-F1 floor, RAG hit@3/refusal floors, safety zero-tolerance).
- Eval fixtures/golden sets are committed and synthetic/redacted (Spec 015), so CI needs no real client data or production secrets for the core gates.
- A `make ci` entrypoint runs the same pipeline locally as in CI.
- Long/full suites may be moved to a scheduled nightly job; per-PR runs use bounded/sampled fixtures to stay fast.
