# Implementation Plan: Evaluation

**Branch**: `015-evaluation` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/015-evaluation/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): eval tenants A/B; run tenant scope; isolation subject
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): `created_by`; developer/owner trigger; manager/instructor read-only
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): synthetic messages for e2e scenarios (eval namespace)
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): held-out splits + golden set (disjoint from training)
- [Spec 007 — Risk Detection](../007-risk-detection/plan.md): risk labels + high-risk workflow tests
- [Spec 008 — Document Upload](../008-document-upload/plan.md): eval-tenant documents
- [Spec 009 — RAG](../009-rag-over-tenant-documents/plan.md): retrieval evaluated (hit@k/MRR/source/refusal/no-cross-tenant)
- [Spec 010 — Suggested Replies](../010-suggested-replies/plan.md): reply groundedness/source-usage
- [Spec 011 — Follow-Up Tasks](../011-follow-up-tasks/plan.md) / [Spec 012 — Escalation](../012-escalation-to-manager/plan.md): recommend-action workflow tests
- [Spec 013 — Audit Logs](../013-audit-logs/plan.md): isolation + PII-redaction-in-summary evidence; eval-tagging
- [Spec 014 — Guardrails](../014-guardrails/plan.md): red-team suite invokes the real guardrail; redaction backstop for stored results

**Note**: This feature observes and measures features 001–014. It adds an evaluation harness (scripts + thin service), two new tables, optional endpoints, and an optional read-only dashboard. It changes **no** production behavior and adds **no** step to the live pipeline.

---

## Summary

Add an evaluation harness with eight area runners (`classifier`, `risk_detection`, `rag_retrieval`, `suggested_reply`, `guardrail`, `tenant_isolation`, `agent_workflow`, `end_to_end`). A run is recorded as an immutable `EvaluationRun` (`tenant_id?`, `run_name`, `area`, `status`, timestamps, `created_by`, `summary_metrics` JSON, `artifact_paths` JSON, `notes`); each test case yields an `EvaluationResult` (`input_payload`/`expected_output`/`actual_output`/`passed`/`score`/`error_message`/`metadata`). Golden sets are versioned fixtures kept **separate from training data** and disjoint-checked. The harness invokes the **real** services (006–014) on fixtures/held-out splits — never the training data — captures outputs through the guardrail/audit **redactor**, scores them with a metrics module (sklearn-style classification metrics + custom RAG/guardrail/isolation scorers), and writes JSON/CSV/Markdown artifacts. Optional endpoints (`POST /api/evaluations/runs`, `GET …`) and a read-only React dashboard surface the latest summary + pass/fail grid + confusion matrix. Triggering requires the developer/owner role; managers/instructors are read-only. Evaluation is out-of-band: synthetic fixtures / a dedicated eval tenant, eval audit entries tagged, nothing surfaced in the real inbox, nothing auto-sent or auto-created.

---

## Technical Approach

- **Harness = scripts + thin service**: the authoritative entry points are CLI scripts (`backend/eval/run_*.py`) and a notebook; a thin `EvaluationService` wraps them so optional endpoints + the dashboard call the **same** runners (no second code path). Runners are plain async functions returning a `RunOutcome` (summary + per-case results) that the service persists.
- **Area runners**: one module per area under `backend/eval/runners/` (`classifier.py`, `risk.py`, `rag.py`, `reply.py`, `guardrail.py`, `isolation.py`, `agent_workflow.py`, `end_to_end.py`). Each loads its fixtures, invokes the real service(s), scores, and returns results.
- **Real-component invocation**: runners call the same service functions production uses (classifier predict, RAG retrieve, reply generate, `guardrails.check_*`) so evidence reflects the real system. RAG/e2e runs use a **dedicated eval tenant** with seeded eval documents; the classifier run can be global (`tenant_id=null`) on a shared labeled split.
- **Held-out + golden discipline**: the classifier/RAG datasets expose `train`/`validation`/`test`/`golden` splits; runners use only `validation`/`test`/`golden`. A `leakage_check` asserts golden∩train = ∅ by stable id + content hash and fails loudly on overlap (FR-012).
- **Metrics module (`backend/eval/metrics.py`)**: classification metrics (accuracy, macro/weighted-F1, per-class P/R/F1, confusion matrix with label ordering) via scikit-learn; custom scorers for RAG (hit@k, MRR, source/tenant correctness, refusal correctness, no-cross-tenant-source rate), reply (groundedness/unsupported/source-usage, reusing 014's `validate_rag_grounding`), and pass/fail booleans for guardrail/isolation/agent/e2e. All metrics are **NaN-safe** (no-support class → `null`).
- **Redaction before storage (SP-02)**: every stored `input_payload`/`actual_output`/`metadata` passes through the 014/013 redactor; a leaked secret/PII is redacted in storage **and** the originating safety test is marked `passed=false` (the leak is the failure).
- **Immutable runs (Out of Scope: no edit/delete)**: `evaluation_runs`/`evaluation_results` have no update/delete path; re-running creates a new run; prior runs are retained for trend/regression comparison.
- **Out-of-band + no autonomy**: runners never auto-send a reply or auto-create a task/escalation; the agent_workflow runner asserts the system **recommends** an action. Eval audit entries are tagged (`metadata.eval_run_id`) so a real manager isn't misled (SP-07).
- **Exports (`backend/eval/export.py`)**: serialize a run to JSON (full), CSV (per-case table), and Markdown (report-ready summary + confusion matrix + pass/fail grid); record `artifact_paths` on the run.

---

## Backend Tasks

1. **`schemas/evaluation.py`** — Pydantic: `EvaluationRunCreate`, `EvaluationRunResponse`, `EvaluationRunListItem`, `EvaluationRunListResponse`, `EvaluationResultResponse`, `EvaluationResultListResponse`, `EvaluationSummaryResponse`, `EvaluationRunFilters`; plus `EvaluationArea`, `EvaluationStatus` enums.
2. **`models/evaluation.py`** — SQLAlchemy `EvaluationRun`, `EvaluationResult`, `EvaluationTestCase`, optional `EvaluationMetric` (immutable, no `updated_at`).
3. **`services/evaluation_service.py`**:
   - `create_run(session, *, user_id, role, area, tenant_id=None, run_name, split, notes)` — role-gate (owner); create `pending` run; dispatch the area runner; persist results + summary; finalize `completed`/`failed`.
   - `list_runs(session, *, caller, filters, limit, offset)` — tenant-scoped/global, newest-first, paginated.
   - `get_run(session, *, caller, run_id)` — scope-resolve (404/403).
   - `list_results(session, *, caller, run_id, limit, offset)` — per-run results, paginated.
   - `summary(session, *, caller, area=None)` — latest run(s)' `summary_metrics` per area for the dashboard.
4. **`eval/` harness package** (see Evaluation Script tasks) — runners, metrics, fixtures loader, redaction shim, export.
5. **`api/v1/evaluations.py`** — endpoints (trigger + reads) with `require_role`; optional per-area trigger endpoints.
6. **Config** — `EVAL_ENABLED`, `EVAL_TENANT_A_SLUG`/`EVAL_TENANT_B_SLUG`, `EVAL_ARTIFACT_DIR`, `EVAL_RESULTS_MAX_LIMIT`, `EVAL_OWNER_ROLE` in settings.
7. **Router mount** — register the evaluations router at `/api` in `main.py` (behind `EVAL_ENABLED`).

---

## Evaluation Script / Notebook Tasks

1. **`backend/eval/run_all.py`** — CLI entry: `python -m eval.run_all --area classifier --split test` → runs a runner, persists a run, writes artifacts, prints the summary.
2. **Per-area CLIs** — `run_classifier.py`, `run_rag.py`, `run_guardrails.py`, `run_isolation.py`, `run_e2e.py` (thin wrappers over the runners) for the quickstart.
3. **`backend/eval/notebook.ipynb`** — a notebook that runs each area, displays the confusion matrix + metric tables inline, and links the exported artifacts (for the report).
4. **`runners/` modules** — one per area; each: load fixtures → invoke real service(s) on the eval tenant/split → score → return `RunOutcome(summary, results)`.
5. **Redaction shim (`eval/redaction.py`)** — wrap captured outputs through 014/013 redactor before they enter `EvaluationResult`; flag any redaction as a failed safety test where relevant.
6. **No-autonomy guard** — runners import only read/recommend paths; a test asserts no runner calls reply-send / task-create / escalation-create.

---

## Golden Dataset Tasks

1. **`backend/eval/fixtures/`** — versioned per-area fixtures: `classifier_golden.jsonl`, `rag_questions.jsonl`, `reply_cases.jsonl`, `guardrail_redteam.jsonl`, `isolation_probes.jsonl`, `agent_workflow.jsonl`, `e2e_scenarios.jsonl` — each case with a stable `id`, `area`, `input`, `expected_output`, optional `labels`, and a `version`.
2. **Disjointness / leakage check (`eval/leakage.py`)** — assert golden/test ∩ train = ∅ by id + content hash (006 exposes train ids/hashes); fail loudly on overlap (FR-012, AC-02).
3. **Synthetic/redacted content rule** — fixtures contain only synthetic clients/PII-free or `[REDACTED]`-style content, no secrets/JWTs/system-prompt text; a fixture-scan test enforces SP-01.
4. **Two eval tenants seeded** — a fixture loader seeds Tenant A + Tenant B with distinct documents so isolation/RAG runs have real cross-tenant separation to probe.
5. **11 e2e scenarios** — encode pricing, booking, availability, guest-count change, urgent change, complaint, cancellation, payment issue, human escalation, unsupported question, cross-tenant attack as fixtures with expected outcomes (intent, refusal, escalation-recommendation, no-leak).

---

## Metric Calculation Tasks

1. **Classifier (`metrics.classification_metrics(y_true, y_pred, labels)`)** — accuracy, macro_f1, weighted_f1, per-class precision/recall/f1, confusion_matrix (+ label order); golden_set_accuracy over the golden split. NaN-safe for no-support classes.
2. **RAG (`metrics.rag_metrics(cases)`)** — hit_at_1/3/5, mrr, source_tenant_correctness, source_document_correctness, refusal_correctness (correct refuse on no-source), no_cross_tenant_source_rate. Refusal scored **separately** from source-correctness (FR-018, AC-04).
3. **Reply (`metrics.reply_metrics(cases)`)** — groundedness (via 014 `validate_rag_grounding`), no_unsupported_claims rate, source_usage rate.
4. **Risk (`metrics.risk_metrics(...)`)** — per-level precision/recall, accuracy, high-risk recall on labeled cases.
5. **Pass/fail scorers** — guardrail (`expected_block == actual_block`), isolation (`access_blocked == true` per entity), agent_workflow (`recommended_action == expected`), e2e (per-scenario assertion bundle). Each returns `passed` + a short `metadata` reason.
6. **Aggregation** — a `summarize(results)` helper rolls per-case results into `summary_metrics` (counts, rates, the metric dicts above) for the run + dashboard.

---

## Storage / Export Tasks

1. **DB persistence** — `evaluation_runs` + `evaluation_results` (+ optional `evaluation_metrics`) via Alembic; immutable (no update/delete path).
2. **Artifact writer (`eval/export.py`)** — `export_json(run)`, `export_csv(run)`, `export_markdown(run)` to `EVAL_ARTIFACT_DIR/<run_id>/`; record paths in `run.artifact_paths`. Markdown is report-ready (summary table + confusion matrix + pass/fail grid).
3. **Redaction on export** — exports serialize the already-redacted stored fields; a final scan asserts no secret/JWT/prompt/cross-tenant pattern in any artifact (SP-03, AC-16).
4. **Download endpoint (optional)** — `GET /api/evaluations/runs/{id}/export?format=markdown|csv|json` streams the artifact (owner/manager/instructor read).
5. **Retention** — runs are retained (no auto-purge); re-runs accumulate for trend comparison (AC-21).

---

## Optional Dashboard Page Tasks

1. **`api/evaluations.ts`** — typed client: `triggerRun(area, opts)` (owner), `listRuns(filters)`, `getRun(id)`, `listResults(runId, page)`, `getSummary(area?)`, `exportRun(id, format)`.
2. **`types/evaluation.ts`** — `EvaluationArea`, `EvaluationStatus`, `EvaluationRun`, `EvaluationResult`, `EvaluationSummary` TS types.
3. **`pages/EvaluationDashboardPage.tsx`** — `/evaluation` read-only dashboard: latest run per area, summary-metric cards (accuracy/F1, hit@k/MRR, pass counts), a **scenario pass/fail grid**, and a **confusion-matrix** view.
4. **`components/evaluation/`** — `MetricCard.tsx`, `ConfusionMatrix.tsx`, `PassFailGrid.tsx`, `RunList.tsx`, `RunDetail.tsx`, `ResultTable.tsx` (paginated, bounded sample).
5. **Trigger control (owner only)** — a "Run evaluation" control visible only to the developer/owner role; hidden/disabled for manager/instructor (read-only).
6. **States** — loading, empty (no runs), `running`/`failed` badges, 403 (non-owner trigger), 404; **no** edit/delete controls; export buttons (JSON/CSV/Markdown).

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/evaluations/runs` | POST | owner | Trigger a run for an area/split (creates an `EvaluationRun`) |
| `/api/evaluations/runs` | GET | owner/manager/instructor | List runs (filters + pagination, scope-gated) |
| `/api/evaluations/runs/{run_id}` | GET | owner/manager/instructor | Get one run (summary + status) |
| `/api/evaluations/runs/{run_id}/results` | GET | owner/manager/instructor | Paginated per-case results |
| `/api/evaluations/summary` | GET | owner/manager/instructor | Latest summary metrics per area (dashboard) |
| `/api/evaluations/runs/{run_id}/export` | GET | owner/manager/instructor | Download JSON/CSV/Markdown artifact |
| `/api/evaluations/classifier/run` *(optional)* | POST | owner | Convenience trigger for the classifier area |
| `/api/evaluations/rag/run` *(optional)* | POST | owner | Convenience trigger for the RAG area |
| `/api/evaluations/guardrails/run` *(optional)* | POST | owner | Convenience trigger for the guardrail area |

- Triggers require the owner role (FR-015); reads are scope-gated (404/403 cross-tenant). Invalid area/split/format/filter → 422.
- No update/delete routes (immutable); any such method → 405.
- Endpoints call the same runners as the CLI (one harness, two front doors).

---

## Testing Tasks

**Backend unit** — `tests/unit/test_eval_metrics.py`: classification metrics correctness + NaN-safety (AC-22), RAG hit@k/MRR/refusal-separation (AC-04), reply groundedness; `tests/unit/test_eval_leakage.py`: golden∩train disjointness fails on overlap (AC-02); `tests/unit/test_eval_redaction.py`: captured secret/PII redacted + flagged (AC-17); `tests/unit/test_eval_fixtures.py`: fixtures contain no secrets/prompts (SP-01).

**Backend integration** — `tests/integration/test_evaluations.py`:
- Classifier run → summary keys + artifact (AC-01); RAG run → metrics incl. no_cross_tenant_source_rate=1.0 (AC-03, AC-05); reply metrics (AC-06)
- Guardrail suite per-case pass/fail (AC-07); isolation suite per-entity pass/fail (AC-08); agent recommends + no autonomy (AC-09); e2e 11 scenarios (AC-10)
- Run/result persistence with all fields (AC-11, AC-12); export JSON/CSV/Markdown matches summary (AC-13)
- No secrets/prompts/cross-tenant in results/exports (AC-16); leaked secret redacted + test failed (AC-17); no prod pollution / eval audit tagged (AC-18)
- Run `completed` on test failure vs `failed` on harness error (AC-19); tenant-scoped reads + cross-tenant 404/403 (AC-20); re-run new run, prior retained (AC-21)
- Non-owner trigger → 403; read side-effect-free (AC-15)

**Frontend** — dashboard renders summary cards + confusion matrix + pass/fail grid; owner-only trigger control; no edit/delete; export buttons (AC-14).

---

## Build Order

1. **Schemas + enums** — `EvaluationArea`/`EvaluationStatus` + DTOs + filter model.
2. **DB + models** — Alembic migration + `EvaluationRun`/`EvaluationResult`/`EvaluationTestCase`(+`EvaluationMetric`); immutable; indexes.
3. **Fixtures + leakage** — versioned golden/fixture sets per area + the disjointness/leakage check + fixture-no-secrets scan + two seeded eval tenants.
4. **Metrics** — classification + RAG + reply + risk + pass/fail scorers + `summarize`, all NaN-safe, unit-tested.
5. **Redaction shim + export** — wrap captured outputs; JSON/CSV/Markdown writers with a no-leak scan.
6. **Runners + service** — eight area runners invoking the real services; `EvaluationService.create_run` (role-gate, dispatch, persist, finalize) + read functions.
7. **CLIs + notebook** — `run_all.py` + per-area CLIs + notebook for the report.
8. **API** — trigger + read + export endpoints + router mount + role/scope gating; integration tests (AC-01..AC-22).
9. **Optional dashboard** — types + client → dashboard (summary cards, confusion matrix, pass/fail grid, run list/detail, results table) → owner-only trigger → export buttons → states.
10. **Validation** — run the 7-step quickstart (classifier, RAG, guardrail, isolation, e2e, view/export, no-secrets check); confirm all 22 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/015-evaluation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── evaluations.py                # trigger + read + export endpoints
│   ├── services/
│   │   └── evaluation_service.py         # create_run (role-gate, dispatch, persist) + reads
│   ├── models/
│   │   └── evaluation.py                 # EvaluationRun / EvaluationResult / EvaluationTestCase / EvaluationMetric
│   └── schemas/
│       └── evaluation.py                 # Pydantic + EvaluationArea / EvaluationStatus enums
├── eval/                                  # the harness (scripts + runners + metrics + fixtures)
│   ├── run_all.py
│   ├── run_classifier.py / run_rag.py / run_guardrails.py / run_isolation.py / run_e2e.py
│   ├── notebook.ipynb
│   ├── metrics.py
│   ├── leakage.py
│   ├── redaction.py
│   ├── export.py
│   ├── fixtures/
│   │   ├── classifier_golden.jsonl
│   │   ├── rag_questions.jsonl
│   │   ├── reply_cases.jsonl
│   │   ├── guardrail_redteam.jsonl
│   │   ├── isolation_probes.jsonl
│   │   ├── agent_workflow.jsonl
│   │   └── e2e_scenarios.jsonl
│   └── runners/
│       ├── classifier.py / risk.py / rag.py / reply.py
│       ├── guardrail.py / isolation.py / agent_workflow.py / end_to_end.py
├── alembic/versions/
│   └── 00xx_create_evaluation_tables.py
└── tests/
    ├── integration/
    │   └── test_evaluations.py
    └── unit/
        ├── test_eval_metrics.py
        ├── test_eval_leakage.py
        ├── test_eval_redaction.py
        └── test_eval_fixtures.py

frontend/
└── src/
    ├── api/
    │   └── evaluations.ts
    ├── types/
    │   └── evaluation.ts
    ├── pages/
    │   └── EvaluationDashboardPage.tsx
    └── components/evaluation/
        ├── MetricCard.tsx
        ├── ConfusionMatrix.tsx
        ├── PassFailGrid.tsx
        ├── RunList.tsx
        ├── RunDetail.tsx
        └── ResultTable.tsx
```

Modified files:

```
backend/app/main.py                                  # mount evaluations router (behind EVAL_ENABLED)
backend/app/core/config.py                           # EVAL_* settings
backend/app/services/audit_service.py (013)          # accept an eval_run_id tag on eval audit entries (SP-07)
frontend/src/App.tsx                                 # add /evaluation route
frontend/src/components/NavBar (or Sidebar)          # add Evaluation nav item (owner/manager/instructor)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–014. Evaluation is an **out-of-band harness**: CLI scripts + a notebook are the primary entry points, a thin `EvaluationService` lets optional endpoints + a read-only dashboard call the **same** runners, and two immutable tables store the evidence. Runners invoke the real services (006–014) on versioned golden/held-out fixtures (disjoint from training), score with a NaN-safe metrics module, redact captured outputs before storage, and write report-ready JSON/CSV/Markdown artifacts. The "no production pollution", "no autonomy", "held-out only", "redaction", and "owner-triggers / read-only oversight" guarantees live in the harness + service so they hold no matter which front door is used.
