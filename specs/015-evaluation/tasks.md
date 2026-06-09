---
description: "Task list for Evaluation feature implementation"
---

# Tasks: Evaluation

**Branch**: `015-evaluation` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/015-evaluation/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement; this feature **observes/measures** them):
- Spec 001 — Multi-Tenant Workspace: `tenants`, `tenant_id` isolation, server-side tenant-scoped retrieval, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`; two **eval tenants** (A, B) seeded here
- Spec 002 — Authentication and Roles: JWT auth; roles; `require_role`; the developer/owner role (`EVAL_OWNER_ROLE`) triggers, manager/instructor read-only
- Spec 003 — Message Simulator: synthetic messages for e2e/isolation fixtures (eval namespace)
- Spec 006 — Intent Classifier: the trained model artifact + the `train`/`validation`/`test`/`golden` split ids/hashes (for the leakage check); the predict function
- Spec 007 — Risk Detection: risk-level labels + the risk engine (for risk + high-risk workflow tests)
- Spec 008 — Document Upload: eval-tenant documents to retrieve over
- Spec 009 — RAG Over Tenant Documents: the tenant-scoped retrieve function + `source_document_ids` + the `rag_no_source_found` signal
- Spec 010 — Suggested Replies: the reply generator (groundedness/source-usage scored)
- Spec 011 — Follow-Up Tasks / Spec 012 — Escalation: the recommend-action signals (recommend, never auto-create)
- Spec 013 — Audit Logs: `AuditService.log_event` + the audit redactor; accepts an `eval_run_id` tag (SP-07)
- Spec 014 — Guardrails: `guardrails.check_user_input`/`check_ai_output` + `validate_rag_grounding` + `redact_text`/`redact_pii` (red-team suite + the redaction backstop for stored results)

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 + scikit-learn (classification metrics, reused from 006) (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend) · CLI scripts + a notebook are the primary harness entry points

**New schema**: three tables `evaluation_runs` + `evaluation_results` + `evaluation_test_cases` (+ optional `evaluation_metrics`) + one Alembic migration. **Append-only** — no `updated_at`, no update/delete path (re-run instead). Loose FKs to `tenants`/`users` (`ON DELETE SET NULL`); `evaluation_results` cascades from its run for referential tidiness only (no app delete path). `area`/`status` persisted as constrained strings; JSON payloads/metrics as JSONB.

**Config defaults** (plan.md #6): `EVAL_ENABLED=true`, `EVAL_TENANT_A_SLUG`/`EVAL_TENANT_B_SLUG`, `EVAL_ARTIFACT_DIR`, `EVAL_RESULTS_MAX_LIMIT`, `EVAL_OWNER_ROLE`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US4]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–014 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` + tenant-scoped session context (001), `require_role` + `get_current_tenant_context` + the owner-role check (002), the message creator for eval fixtures (003), the classifier predict fn + train/validation/test/golden split ids+hashes (006), the risk engine + labels (007), eval-tenant document ingestion (008), the RAG retrieve fn + `source_document_ids` + `rag_no_source_found` (009), the reply generator (010), the task/escalation recommendation signals (011/012), `AuditService.log_event` + audit redactor + the `eval_run_id` tag hook (013), `guardrails.check_user_input`/`check_ai_output` + `validate_rag_grounding` + `redact_text`/`redact_pii` (014), and `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (001). Do NOT redefine any of these.
- [ ] T002 Add the `EVAL_*` settings to `backend/app/core/config.py` with documented defaults: `EVAL_ENABLED=true`, `EVAL_TENANT_A_SLUG`, `EVAL_TENANT_B_SLUG`, `EVAL_ARTIFACT_DIR`, `EVAL_RESULTS_MAX_LIMIT` (e.g. 500), `EVAL_OWNER_ROLE` (the developer/owner role name) (plan.md #6)
- [ ] T003 Add the `eval_run_id` tag hook to `backend/app/services/audit_service.py` (013): allow the audit writer to accept an optional `eval_run_id` (stored in audit metadata) so eval-generated audit entries are distinguishable from real activity — non-breaking, additive (SP-07, AC-18, research.md Decision 12)
- [ ] T004 Confirm 006 exposes a stable train/validation/test/golden split (by id + content hash) the leakage check can read; record the accessor. If only training data exists, document that the golden/test fixtures (Phase 3) are the authoritative held-out source and the disjointness check runs against the training ids/hashes (FR-012, AC-02)
- [ ] T005 Verify `backend/tests/unit/` and `backend/tests/integration/` exist with `__init__.py`; create `backend/eval/` as a package (`__init__.py`) and the `eval/fixtures/` + `eval/runners/` directories; create any missing test dirs

**Checkpoint**: Dependencies confirmed reused; config + audit eval-tag in place; split/leakage source decided; `eval/` package scaffolded.

---

## Phase 2: Database, Models & Schemas (Foundational — Blocking)

**Purpose**: The three append-only tables, ORM models, enums, and Pydantic DTOs underpin every runner, endpoint, and test. **BLOCKS everything.**

**⚠️ CRITICAL**: Phases 6–8 cannot run without this phase.

- [ ] T006 [P] Create the `EvaluationArea` (`classifier`, `risk_detection`, `rag_retrieval`, `suggested_reply`, `guardrail`, `tenant_isolation`, `agent_workflow`, `end_to_end`) and `EvaluationStatus` (`pending`, `running`, `completed`, `failed`) string enums in `backend/app/schemas/evaluation.py` (shared by service + API + runners) — per data-model.md
- [ ] T007 Create the SQLAlchemy models in `backend/app/models/evaluation.py` per data-model.md: `EvaluationRun` (`id` PK; `tenant_id` FK→`tenants.id` `SET NULL` NULL indexed; `run_name` VARCHAR(160) NOT NULL; `area` VARCHAR(32) NOT NULL; `status` VARCHAR(16) NOT NULL default `pending`; `started_at`/`completed_at` TIMESTAMPTZ NULL; `created_by` FK→`users.id` `SET NULL` NULL; `summary_metrics` JSONB NOT NULL default `dict`; `artifact_paths` JSONB NOT NULL default `dict`; `notes` TEXT NULL; `created_at` TIMESTAMPTZ server_default now; **no `updated_at`**; indexes `ix_eval_run_tenant_created`, `ix_eval_run_area_created`, `ix_eval_run_status`, `ix_eval_run_created_by`), `EvaluationResult` (`id` PK; `evaluation_run_id` FK→`evaluation_runs.id` `CASCADE` NOT NULL indexed; `test_case_id` FK→`evaluation_test_cases.id` `SET NULL` NULL; `area` VARCHAR(32); `input_payload`/`expected_output`/`actual_output` JSONB NOT NULL default `dict`; `passed` BOOLEAN NOT NULL; `score` DOUBLE PRECISION NULL; `error_message` TEXT NULL; `metadata_`→column `"metadata"` JSONB NOT NULL default `dict`; `created_at`; indexes `ix_eval_result_run`, `ix_eval_result_run_passed`, `ix_eval_result_area`), `EvaluationTestCase` (`id` PK; `area`; `tenant_id` FK `SET NULL` NULL; `name` VARCHAR(160); `input`/`expected_output` JSONB NOT NULL; `labels` JSONB default `dict`; `content_hash` VARCHAR(64) NOT NULL indexed; `version` VARCHAR(32) NOT NULL; `created_at`; indexes `(area, version)`, `(content_hash)`), and optional `EvaluationMetric` (`id` PK; `evaluation_run_id` FK `CASCADE` indexed; `name` VARCHAR(64); `value` DOUBLE PRECISION NULL; `label` VARCHAR(64) NULL; `created_at`) (depends on T006)
- [ ] T008 Create Alembic migration `backend/alembic/versions/00xx_create_evaluation_tables.py`: create all three (+ optional metrics) tables with columns, FKs (`tenant_id`/`created_by`→`SET NULL`; `evaluation_run_id`→`CASCADE`; `test_case_id`→`SET NULL`), defaults (`status='pending'`, JSONB `{}`), and all indexes; **no** `updated_at`; provide a correct `downgrade()` dropping the tables + indexes (depends on T007)
- [ ] T009 Add Pydantic models to `backend/app/schemas/evaluation.py` (alongside the enums) per data-model.md: `EvaluationRunCreate` (`area`, `run_name` 1–160, `split: Literal["validation","test","golden"]="test"` with a `field_validator` rejecting `"train"`, `tenant_id: UUID|None`, `notes: str|None ≤2000`), `EvaluationRunFilters` (`area`/`status`/`tenant_id`/`created_from`/`created_to`), `EvaluationRunListItem` (`from_attributes=True`), `EvaluationRunResponse(EvaluationRunListItem)` (+`summary_metrics`/`artifact_paths`/`notes`), `EvaluationResultResponse` (all result fields incl. `metadata`), `EvaluationRunListResponse`/`EvaluationResultListResponse` (`items`/`total`/`limit`/`offset`), `EvaluationSummaryResponse` (`areas: dict[str, dict]`) (depends on T006)

**Checkpoint**: `alembic upgrade head` creates the three append-only tables; models + enums + schemas importable; `split=train` is rejected at the schema boundary.

---

## Phase 3: Golden Datasets, Fixtures, Leakage & Eval Tenants (Foundational — Blocking)

**Purpose**: Versioned per-area fixtures (synthetic/redacted, no real PII/secrets/prompts), the train-disjointness leakage check, the fixture-no-secrets scan, and two seeded eval tenants with distinct documents. **BLOCKS the runners (Phase 6).**

- [ ] T010 [P] [US4] Create the versioned per-area fixtures under `backend/eval/fixtures/` (`*.jsonl`), each case with stable `id`, `area`, `input`, `expected_output`, optional `labels` (incl. `split`), `content_hash`, `version`: `classifier_golden.jsonl` (intent labels), `rag_questions.jsonl` (labeled tenant-document questions incl. no-source cases), `reply_cases.jsonl` (grounded + ungrounded drafts), `guardrail_redteam.jsonl` (injection / disclosure / unsupported / PII / cross-tenant / invented-policy), `isolation_probes.jsonl` (per-entity A→B probes), `agent_workflow.jsonl` (high-risk → recommend action), `e2e_scenarios.jsonl` (the 11 named scenarios). Synthetic/redacted content only — no real secrets/JWTs/keys/system-prompt text (plan.md Golden Dataset #1, SP-01)
- [ ] T011 [US4] Encode the **11 e2e scenarios** in `e2e_scenarios.jsonl` with expected outcomes: pricing request, booking inquiry, availability question, guest-count change, urgent change, complaint, cancellation request, payment issue, human escalation (expects a **recommended** escalation/task — no auto-create), unsupported question (expects **refusal**), cross-tenant attack (expects **blocked** + no B data) (FR-011, AC-10) (depends on T010)
- [ ] T012 [US4] Implement the fixtures loader + the two-eval-tenant seeder `backend/eval/seed_fixtures.py`: load `EvaluationTestCase` rows from the fixtures, and seed **Tenant A + Tenant B** (`EVAL_TENANT_A_SLUG`/`EVAL_TENANT_B_SLUG`) with **distinct** synthetic documents so isolation/RAG runs have real cross-tenant separation to probe (plan.md Golden Dataset #4, research.md Decision 3) (depends on T010, T002)
- [ ] T013 [P] [US4] Implement the leakage/disjointness check `backend/eval/leakage.py`: assert golden/test ∩ train = ∅ by stable `id` **and** `content_hash` (using the 006 train ids/hashes from T004); fail **loudly** on any overlap (raise + a run note "leakage check: passed/FAILED"); used by the classifier runner before scoring golden accuracy (FR-012, AC-02, research.md Decision 2) (depends on T010, T004)
- [ ] T014 [P] [US4] Unit `backend/tests/unit/test_eval_fixtures.py`: scan every fixture for real PII/secrets/JWTs/API-keys/system-prompt patterns → assert none (synthetic/redacted only); assert each case has a stable `id`, `expected_output`, `area`, and `version` (SP-01, AC-02 support) (depends on T010)

**Checkpoint**: Fixtures exist (synthetic, versioned), the leakage check fails loudly on overlap, fixtures are secret-free, and two eval tenants are seeded with distinct documents.

---

## Phase 4: Metrics Module (Foundational — Blocking, unit-tested)

**Purpose**: The NaN-safe scoring functions — classification (sklearn), RAG, reply, risk, and pass/fail scorers — plus the `summarize` aggregator. Pure functions, unit-tested before the runners compose them. **BLOCKS the runners (Phase 6).**

- [ ] T015 [P] [US1] Implement `classification_metrics(y_true, y_pred, labels)` in `backend/eval/metrics.py`: accuracy, macro_f1, weighted_f1, per-class precision/recall/f1, `confusion_matrix` (+ `labels` ordering) via scikit-learn; `golden_set_accuracy` helper over the golden split; **NaN-safe** — a no-support class → `null` (not a crash) (FR-005, AC-01, AC-22, research.md Decision 4)
- [ ] T016 [P] [US1] Implement `rag_metrics(cases)` in `backend/eval/metrics.py`: `hit_at_1/3/5`, `mrr`, `source_tenant_correctness`, `source_document_correctness`, `refusal_correctness` (correct refuse when no source) scored **separately** from source-correctness, and `no_cross_tenant_source_rate`; a "refuse-everything" input must score low on `source_document_correctness` (FR-006, FR-018, AC-03, AC-04, AC-05, research.md Decision 6)
- [ ] T017 [P] [US1] Implement `reply_metrics(cases)` in `backend/eval/metrics.py`: `groundedness` (reusing 014 `validate_rag_grounding` — invented policies/prices are NOT grounded), `no_unsupported_claims` rate, `source_usage` rate, per-case + aggregate (FR-007, AC-06)
- [ ] T018 [P] Implement `risk_metrics(...)` in `backend/eval/metrics.py`: per-level precision/recall, accuracy, and high-risk recall on labeled risk cases (spec area 2; FR-002)
- [ ] T019 [P] Implement the pass/fail scorers + `summarize(results)` in `backend/eval/metrics.py`: guardrail (`expected_block == actual_block` per category), isolation (`access_blocked == true` per entity + `no_cross_tenant_source_rate`), agent_workflow (`recommended_action == expected` + `no_autonomous_side_effect`), e2e (per-scenario assertion bundle) — each returns `passed` + a short `metadata` reason; `summarize` rolls per-case results into the area's `summary_metrics` dict (FR-008, FR-009, FR-010, FR-011, research.md Decision 8)
- [ ] T020 [P] Unit `backend/tests/unit/test_eval_metrics.py`: classification metrics correctness + NaN-safety on a no-support class (AC-01, AC-22); RAG hit@k/MRR + refusal scored separately so a refuse-all stub scores low on source-correctness (AC-04); reply groundedness counts an invented policy as ungrounded (AC-06) (depends on T015, T016, T017)

**Checkpoint**: All scorers are pure, NaN-safe, unit-tested; `summarize` produces the per-area `summary_metrics` shape from data-model.md.

---

## Phase 5: Redaction Shim & Export (Foundational — Blocking for storage)

**Purpose**: Redact captured outputs before storage (and flag a leak as a failed test), and write report-ready JSON/CSV/Markdown artifacts with a final no-leak scan.

- [ ] T021 [US1] Implement the redaction shim `backend/eval/redaction.py`: `redact_result(input_payload, actual_output, metadata) -> (clean_input, clean_actual, clean_meta, leaked: bool)` wrapping the 014/013 `redact_text`/`redact_pii` over every stored field; if a captured output contained a secret/JWT/key/PII/system-prompt, redact it **and** return `leaked=True` so the originating safety test is set `passed=False` (the leak is the failure, not a silent fix) (FR-016, SP-02, AC-17, research.md Decision 7) (depends on T001)
- [ ] T022 [P] Unit `backend/tests/unit/test_eval_redaction.py`: a captured secret/JWT/email/phone in `actual_output` → redacted to placeholders in storage AND `leaked=True` (the safety test would be marked failed); no forbidden content survives (SP-02, AC-17) (depends on T021)
- [ ] T023 [US3] Implement the artifact writers `backend/eval/export.py`: `export_json(run)` (full), `export_csv(run)` (per-case table), `export_markdown(run)` (report-ready: summary table + confusion matrix + pass/fail grid) to `EVAL_ARTIFACT_DIR/<run_id>/`; return the paths for `run.artifact_paths`; serialize the **already-redacted** stored fields and run a final scan asserting no secret/JWT/prompt/cross-tenant pattern in any artifact (FR-013, SP-03, AC-13, AC-16, research.md Decision 10) (depends on T021)

**Checkpoint**: Captured outputs are redacted (and leaks flagged) before storage; JSON/CSV/Markdown artifacts are written and scanned clean.

---

## Phase 6: Area Runners + CLIs (User Stories 1–4)

**Purpose**: One runner per area invoking the **real** services (006–014) on the eval tenant/split, scoring with Phase 4 metrics, redacting via Phase 5, and returning a `RunOutcome(summary, results)`. Plus the CLI entry points the quickstart uses. **No runner auto-sends or auto-creates anything.**

- [ ] T024 [US1] Implement `backend/eval/runners/classifier.py` `run_classifier(session, *, run, split, tenant_id)`: load the classifier fixtures/held-out split (never `train`), run the leakage check (T013) for the golden split, invoke the real 006 predict fn, score with `classification_metrics`, return per-case `EvaluationResult`s + the summary (FR-005, AC-01, AC-02) (depends on T013, T015, T021)
- [ ] T025 [P] [US1] Implement `backend/eval/runners/risk.py` `run_risk(...)`: run labeled risk cases through the real 007 engine, compare expected `risk_level`/flags, score with `risk_metrics`, return results (spec area 2) (depends on T018, T021)
- [ ] T026 [US1] Implement `backend/eval/runners/rag.py` `run_rag(...)`: run the golden RAG questions over the **eval tenant** via the real 009 retrieve fn (incl. no-source cases), score with `rag_metrics` (hit@k/MRR/source/tenant/refusal/`no_cross_tenant_source_rate`); a Tenant-A query must never return a Tenant-B chunk (FR-006, FR-018, AC-03, AC-04, AC-05) (depends on T016, T012, T021)
- [ ] T027 [P] [US1] Implement `backend/eval/runners/reply.py` `run_reply(...)`: generate replies for grounded questions via the real 010 generator, score with `reply_metrics` (groundedness/no-unsupported/source-usage) (FR-007, AC-06) (depends on T017, T021)
- [ ] T028 [US2] Implement `backend/eval/runners/guardrail.py` `run_guardrail(...)`: send each red-team case through the **real** 014 `check_user_input`/`check_ai_output`, record blocked/refused/redacted per category (injection_blocked, disclosure_refused, unsupported_refused, pii_redacted, cross_tenant_blocked, invented_policy_blocked), score pass/fail; a captured leak → redacted + `passed=False` (FR-008, AC-07, AC-17) (depends on T019, T021)
- [ ] T029 [US2] Implement `backend/eval/runners/isolation.py` `run_isolation(...)`: as Tenant A, attempt to read Tenant B's messages, documents, RAG sources/chunks, tasks, escalations, and audit logs, plus a Tenant-A RAG query; each probe `passed=True` iff access is blocked (404/403) and no B data/chunk returned; `no_cross_tenant_source_rate` must be 1.0 (FR-009, AC-05, AC-08, SP-06) (depends on T019, T012, T021)
- [ ] T030 [P] [US3] Implement `backend/eval/runners/agent_workflow.py` `run_agent_workflow(...)`: assert high-risk cases **recommend** the correct task/escalation action and that **no** runner imports/calls the reply-send / task-create / escalation-create paths (no autonomous side effect) (FR-010, AC-09, research.md Decision 9) (depends on T019, T021)
- [ ] T031 [US3] Implement `backend/eval/runners/end_to_end.py` `run_end_to_end(...)`: drive the 11 named scenarios through classify→risk→RAG→reply→task/escalation-recommendation→audit on synthetic fixtures (eval namespace), score per-scenario pass/fail with a `metadata.reason`; unsupported→refuses, human-escalation→recommends, cross-tenant→blocked (FR-011, AC-10) (depends on T019, T021, T011)
- [ ] T032 No-autonomy + no-pollution guard across runners: ensure runners import only read/recommend paths; eval-created messages/docs/audit stay in the eval tenant/namespace and audit entries carry the `eval_run_id` tag (T003); add a shared assertion/comment + back it with the Phase 9 test (FR-010, FR-017, SP-07, SP-08, AC-18, research.md Decisions 9 & 12) (depends on T024–T031)
- [ ] T033 [P] Implement the CLI entry points in `backend/eval/`: `run_all.py` (`python -m eval.run_all --area <area> --split <split>` → dispatch a runner, persist a run via the service, write artifacts, print the summary) + thin per-area wrappers `run_classifier.py`, `run_rag.py`, `run_guardrails.py`, `run_isolation.py`, `run_e2e.py` (plan.md Eval Script #1–2) (depends on T024–T031, T036)
- [ ] T034 [P] Create the report notebook `backend/eval/notebook.ipynb`: runs each area, displays the confusion matrix + metric tables inline, and links the exported artifacts (for the final report) (plan.md Eval Script #3) (depends on T033)

**Checkpoint**: Eight runners invoke the real services on the eval tenant/split, score + redact, and return `RunOutcome`; CLIs + notebook drive them; no autonomy, no production pollution.

---

## Phase 7: Evaluation Service & API

**Purpose**: The thin `EvaluationService` that role-gates the trigger, dispatches the area runner, persists results + summary + artifacts, and finalizes `completed`/`failed`; plus the trigger + read + export endpoints with the role matrix and scope-gating. Endpoints call the **same** runners as the CLI (one harness, two front doors). **No update/delete routes (immutable → 405).**

- [ ] T035 Implement the runner dispatch table + helpers in `backend/app/services/evaluation_service.py`: `AREA_RUNNERS` mapping each `EvaluationArea` → its runner; `_to_result_row(run_id, r)` (redact via T021 before building the `EvaluationResult`); `_scope_runs`/`_can_read` (tenant-scoped run readable only within its tenant + authorized roles; global `tenant_id=null` per role/config); `_count` (FR-020, SP-04, data-model.md) (depends on T007, T021, T024–T031)
- [ ] T036 [US1][US2][US3] Implement `create_run(session, *, user_id, role, payload: EvaluationRunCreate) -> EvaluationRun` in `backend/app/services/evaluation_service.py`: role-gate (`role != EVAL_OWNER_ROLE` → `ForbiddenError` `INSUFFICIENT_ROLE`); create the run `running` (`created_by`, `started_at`); dispatch the area runner; persist each redacted result; set `summary_metrics`; write artifacts (T023) into `artifact_paths`; finalize `completed` **even if tests failed**; on a harness exception → `failed` + a redacted `notes` error (no fake metrics); set `completed_at`; commit (FR-015, FR-019, AC-15, AC-19, research.md Decision 8) (depends on T035, T023)
- [ ] T037 [US3] Implement the read functions in `backend/app/services/evaluation_service.py`: `list_runs(session, *, caller, filters, limit, offset)` (scope-gated, `area`/`status`/date filters, newest-first, `limit=min(limit, EVAL_RESULTS_MAX_LIMIT)`), `get_run(session, *, caller, run_id)` (404 `EVALUATION_RUN_NOT_FOUND` / 403 `CROSS_TENANT_FORBIDDEN`), `list_results(session, *, caller, run_id, limit, offset, passed=None)` (scope-gate via `get_run`, results `created_at asc`, optional `passed` filter), `summary(session, *, caller, area=None)` (latest completed run per area, scope-filtered) (FR-020, AC-12, AC-20, data-model.md) (depends on T035)
- [ ] T038 [P] [US1] Implement `POST /api/evaluations/runs` in `backend/app/api/v1/evaluations.py`: `require_role(EVAL_OWNER_ROLE)` (non-owner → 403 `INSUFFICIENT_ROLE`); validate `EvaluationRunCreate` (`split=train` → 422); call `service.create_run`; return `EvaluationRunResponse` **201** (a `completed` run even if some tests failed; a harness error returns a `failed` run, still 201) (contracts §1, FR-015, AC-15, AC-19) (depends on T036)
- [ ] T039 [P] [US3] Implement the read endpoints in `backend/app/api/v1/evaluations.py`: `GET /api/evaluations/runs` (`EvaluationRunListResponse`, filters + pagination, scope-gated), `GET /api/evaluations/runs/{run_id}` (full `EvaluationRunResponse`; 404/403), `GET /api/evaluations/runs/{run_id}/results` (`EvaluationResultListResponse`, paginated + `passed` filter; redacted), `GET /api/evaluations/summary` (`EvaluationSummaryResponse`, latest per area) — all `require_role(owner, manager, instructor)`, Platform Admin → 403; invalid filter/enum/pagination → 422 (contracts §2–5, FR-014, FR-020, AC-12, AC-14, AC-20) (depends on T037)
- [ ] T040 [P] [US3] Implement `GET /api/evaluations/runs/{run_id}/export?format=json|csv|markdown` in `backend/app/api/v1/evaluations.py`: scope-gate via `get_run`; stream the redacted artifact (`application/json`/`text/csv`/`text/markdown`); invalid `format` → 422; missing artifact → 404 `ARTIFACT_NOT_FOUND` (contracts §6, FR-013, AC-13, AC-16) (depends on T037, T023)
- [ ] T041 [P] [US1] Implement the optional per-area convenience triggers in `backend/app/api/v1/evaluations.py`: `POST /api/evaluations/classifier/run`, `/rag/run`, `/guardrails/run` — `require_role(EVAL_OWNER_ROLE)`, equivalent to `POST /runs` with the fixed area, default splits per contract (classifier→`test`, rag→`golden`, guardrail→`golden`) (contracts §7–9, FR-015) (depends on T036)
- [ ] T042 Mount the evaluations router at `/api` in `backend/app/main.py` **behind `EVAL_ENABLED`**; confirm **no** PATCH/PUT/DELETE route exists for `/api/evaluations/runs` or `/results` (immutable → any such method returns 405) (contracts §"No Write/Mutate Endpoints", plan.md #7) (depends on T038–T041)

**Checkpoint**: The owner can trigger a run (CLI or API, same runners); reads are scope-gated; exports stream redacted artifacts; runs/results are immutable (405 on mutate); harness error → `failed`, test failure → `completed`. Backend MVP complete.

---

## Phase 8: Optional Evaluation / Demo Dashboard (read-only)

**Purpose**: A read-only React dashboard surfacing the latest run per area — metric cards, confusion matrix, pass/fail grid, run list/detail, results table, export buttons. Owner-only trigger control; **no** edit/delete; manager/instructor read-only.

- [ ] T043 [P] Add TS types to `frontend/src/types/evaluation.ts`: `EvaluationArea`, `EvaluationStatus`, `EvaluationRun`, `EvaluationResult`, `EvaluationSummary` (data-model.md Frontend Types)
- [ ] T044 [P] Add the typed API client `frontend/src/api/evaluations.ts`: `triggerRun(payload)` (owner), `listRuns(filters)`, `getRun(id)`, `listResults(runId, page, passed?)`, `getSummary(area?)`, `exportRun(id, format)` — with the auth header (depends on T043)
- [ ] T045 [P] Implement the presentational components in `frontend/src/components/evaluation/`: `MetricCard.tsx` (accuracy/F1, hit@k/MRR, pass counts), `ConfusionMatrix.tsx` (matrix + label ordering), `PassFailGrid.tsx` (guardrail/isolation/e2e per-test grid), `RunList.tsx`, `RunDetail.tsx`, `ResultTable.tsx` (paginated, bounded sample) (plan.md Dashboard #4, AC-14) (depends on T043)
- [ ] T046 [US3] Implement `frontend/src/pages/EvaluationDashboardPage.tsx` at route `/evaluation` (read-only): latest run per area via `getSummary`, summary-metric cards, the confusion matrix, the scenario pass/fail grid, run list + detail + results table; export buttons (JSON/CSV/Markdown); loading / empty (no runs) / `running`/`failed` badges / 403 / 404 states; register the route in `frontend/src/App.tsx` and add an Evaluation nav item (owner/manager/instructor) (plan.md Dashboard #3 & #6, AC-14) (depends on T044, T045)
- [ ] T047 [US3] Add the owner-only "Run evaluation" trigger control to the dashboard, visible only to the `EVAL_OWNER_ROLE`; hidden/disabled for manager/instructor; **no** edit/delete or "reveal raw output" controls anywhere (FR-015, AC-15) (depends on T046)

**Checkpoint**: The dashboard renders the latest summary + confusion matrix + pass/fail grid read-only; only the owner sees a trigger; no edit/delete/reveal affordances; export buttons work.

---

## Phase 9: Security, Privacy & Tenant-Isolation Tests (cross-cutting)

**Purpose**: Prove the redaction/no-leak, no-pollution, owner-only-trigger, scope-gated-read, and immutability guarantees. `backend/tests/integration/test_evaluations.py`.

- [ ] T048 [P] No secrets/prompts/cross-tenant data in any result/log/artifact/export: scan stored `input_payload`/`actual_output`/`metadata` + the JSON/CSV/Markdown exports for secret/JWT/key/system-prompt/raw-PII/cross-tenant patterns → assert none (AC-16, SP-03)
- [ ] T049 [P] Leaked secret redacted + flagged: a guardrail/stub case whose component leaks a token → the stored `actual_output` is redacted AND that case is `passed=false` (the leak is the failure) (AC-17, SP-02)
- [ ] T050 [P] No production pollution: eval-created messages/scenarios do NOT appear in the real inbox (Spec 004) for a normal staff user; eval audit entries carry the `eval_run_id` tag (Spec 013) (AC-18, SP-07, SP-08)
- [ ] T051 [P] Owner-only trigger + side-effect-free reads: a manager/instructor `POST /api/evaluations/runs` → 403 `INSUFFICIENT_ROLE` (no run created); a read endpoint creates no new run/result (AC-15, SP-05); Platform Admin → 403 on all eval endpoints; unauthenticated → 401
- [ ] T052 [P] Tenant-scoped reads: a tenant-scoped run is readable only within its tenant; a cross-tenant `GET /runs/{id}`/`/results`/`/export` → 404/403; a client-supplied `tenant_id` on a read does not widen scope (AC-20, SP-04, FR-020)
- [ ] T053 [P] Immutable evidence: `PATCH`/`PUT`/`DELETE /api/evaluations/runs/{id}` and `DELETE /runs/{id}/results` → 405 `METHOD_NOT_ALLOWED`; re-running an area creates a **new** run with prior runs retained (no overwrite) (AC-21, contracts §"No Write/Mutate Endpoints")

**Checkpoint**: Redaction/no-leak, no-pollution, owner-only-trigger, scope-gated reads, and immutability are all proven.

---

## Phase 10: Evaluation Behaviour & Integration Tests

**Purpose**: Verify each area's metrics/pass-fail, run/result persistence, export-matches-summary, run-vs-test status, and the held-out discipline. `backend/tests/integration/test_evaluations.py` + units already in Phases 3–5.

- [ ] T054 [P] [US1] Classifier run → `completed` with `summary_metrics` keys (accuracy, macro_f1, weighted_f1, per-class P/R/F1, confusion_matrix + labels, golden_set_accuracy) + a JSON/Markdown artifact path; `split=train` → 422 (AC-01, AC-02 support) (depends on T038, T024)
- [ ] T055 [P] [US1] RAG run → `summary_metrics` with hit_at_1/3/5, mrr, source_tenant_correctness, source_document_correctness, refusal_correctness, `no_cross_tenant_source_rate == 1.0`; a refuse-all stub scores low on source-correctness (AC-03, AC-04, AC-05) (depends on T026, T016)
- [ ] T056 [P] [US1] Suggested-reply run → groundedness / no_unsupported_claims / source_usage per case + aggregate; an invented policy is counted ungrounded (AC-06) (depends on T027)
- [ ] T057 [P] [US2] Guardrail suite → per-category pass/fail (injection_blocked, disclosure_refused, unsupported_refused, pii_redacted, cross_tenant_blocked, invented_policy_blocked) + a `passed`/`total` summary; failures show expected vs actual (AC-07) (depends on T028)
- [ ] T058 [P] [US2] Isolation suite → per-entity pass (messages, documents, rag_sources, tasks, escalations, audit_logs) + `no_cross_tenant_source_rate == 1.0`; a forced leak is a hard `passed=false` (AC-08, SP-06) (depends on T029)
- [ ] T059 [P] [US3] Agent/workflow suite → high-risk **recommends** the correct action; asserts no auto-create/send side effect (AC-09) (depends on T030)
- [ ] T060 [P] [US3] End-to-end suite → 11 `EvaluationResult`s (one per scenario) with `passed` + `metadata.reason` + a total; unsupported→refuses, human-escalation→recommends, cross-tenant→blocked (AC-10) (depends on T031)
- [ ] T061 [P] Persistence: `EvaluationRun` persists all fields (nullable `tenant_id`, `created_by`, `summary_metrics`, `artifact_paths`, `notes`, timestamps) (AC-11); `EvaluationResult` persists all fields (input/expected/actual/passed/score/error_message/metadata) (AC-12) (depends on T036)
- [ ] T062 [P] [US3] Export JSON/CSV/Markdown matches the run summary (diff the export against `summary_metrics`); exports are redacted/clean (AC-13, AC-16) (depends on T040, T023)
- [ ] T063 [P] Run-vs-test status: a suite with a failing test leaves the run `completed` (failure surfaced with expected vs actual); a harness error (e.g., missing classifier artifact) marks the run `failed` with an `error_message`/`notes` and stores no fake metrics (AC-19, research.md Decision 8) (depends on T036)
- [ ] T064 [P] NaN-safe undefined metrics: a class with no support / an empty golden set for an area → per-class metric `null` and a "no golden cases" note, not a crash and not a fake 100% (AC-22, research.md Decision 4) (depends on T015, T024)

**Checkpoint**: All 22 acceptance criteria are covered by passing unit/integration tests; every area's metrics, persistence, export parity, status semantics, and held-out discipline verified.

---

## Phase 11: Frontend Tests

**Purpose**: Render/interaction tests for the read-only dashboard, owner-only trigger, and the no-edit/delete guarantee.

- [ ] T065 [P] `EvaluationDashboardPage`/`MetricCard`/`ConfusionMatrix`/`PassFailGrid` render test in `frontend/src/pages/__tests__/EvaluationDashboardPage.test.tsx`: renders the latest summary cards, the confusion matrix, and the scenario pass/fail grid; loading / empty (no runs) / `running`/`failed` badge / 403 / 404 states render; **no** edit/delete/reveal controls (AC-14) (depends on T046)
- [ ] T066 [P] Trigger-control test: the "Run evaluation" control renders for the owner role and is hidden/disabled for manager/instructor; export buttons (JSON/CSV/Markdown) render and call `exportRun` (AC-14, AC-15) (depends on T047)

**Checkpoint**: Dashboard states + the owner-only trigger + export buttons render; read-only/no-mutate guarantees confirmed in the UI.

---

## Phase 12: Quickstart & Manual Validation

**Purpose**: Execute the seven-step quickstart end to end (quickstart.md). Requires an owner account + a manager/instructor account, eval tenants seeded, and a trained classifier artifact.

- [ ] T067 Run migrations (`alembic upgrade head`); confirm the three eval tables created; `python -m eval.seed_fixtures` seeds the fixtures + eval tenants A/B and asserts golden∩train=∅ + fixtures secret-free; set `EVAL_ENABLED=true`; log in as owner + manager/instructor
- [ ] T068 Step 1 — classifier evaluation: `run_classifier --split test` (and via API) → `completed` with accuracy/macro_f1/weighted_f1/per-class/confusion_matrix+labels/golden_set_accuracy + artifact paths; `--split golden` notes "leakage check: passed"; `split=train` → 422 (AC-01, AC-02)
- [ ] T069 Step 2 — RAG evaluation over eval tenant A → hit@k/mrr/source/refusal metrics; `no_cross_tenant_source_rate == 1.0`; refusal scored separately from source-correctness (AC-03, AC-04, AC-05)
- [ ] T070 Step 3 — guardrail red-team → per-category pass counts (injection/disclosure/unsupported/PII/cross-tenant/invented-policy) + total; inspect `?passed=false` failures with expected vs actual (AC-07)
- [ ] T071 Step 4 + 5 — isolation suite (A vs B) → every per-entity probe passes + `no_cross_tenant_source_rate == 1.0`; e2e suite → 11 scenarios with per-scenario pass/fail (unsupported→refuse, human-escalation→recommend, cross-tenant→blocked) (AC-08, AC-09, AC-10)
- [ ] T072 Step 6 — view/export: export the classifier run as Markdown + CSV; manager/instructor reads `GET /summary` + opens `/evaluation` dashboard (read-only, no trigger); a manager `POST /runs` → 403 `INSUFFICIENT_ROLE` (AC-13, AC-14, AC-15)
- [ ] T073 Step 7 — no-secrets/no-pollution: grep results + exports for secret/JWT/prompt/contact patterns → 0; redact-and-flag white-box check (stub a leak → redacted + `passed=false`); the eval-tenant messages/scenarios do NOT appear in the real inbox and eval audit entries carry the `eval_run_id` tag (AC-16, AC-17, AC-18)

**Checkpoint**: Quickstart passes end to end; classifier/RAG/guardrail/isolation/e2e runs, view/export, and the no-secrets/no-pollution checks demonstrated live.

---

## Phase 13: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T074 Verify AC-01..AC-22 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T075 Walk `checklists/requirements.md` (Functional / Classifier / RAG / Suggested Reply / Guardrail / Tenant Isolation / End-to-End / API-Storage / Security-Privacy / Testing) and tick each implemented item; confirm the six hard guarantees (held-out only, redaction/no-leak, isolation-tested-not-assumed, run-vs-test status, no-autonomy/no-pollution, owner-triggers/oversight-reads)
- [ ] T076 Confirm Out-of-Scope items remain **unbuilt**: no CI evaluation gating; no model training / tuning / AutoML (the harness only loads existing artifacts and measures); no live A/B or online production metrics; no labeling/annotation UI; no external leaderboards/publishing; no editing/deleting runs/results (immutable, re-run instead); no exposing secrets/system prompts/JWTs/API keys/private tenant data; no using training data as test data (`split=train` rejected); no requiring eval in the production user workflow; no auto-sending replies / auto-creating tasks or escalations from the harness; no real WhatsApp API / calendar syncing / full CRM (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 015 verified against spec + checklist; the evaluation harness produces reproducible, redacted, held-out, report-ready evidence across all eight areas without polluting production or taking autonomous action.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/models/schemas)** → depends on Phase 1; **BLOCKS everything**.
- **Phase 3 (Fixtures/leakage/eval tenants)** → depends on Phase 2; blocks the runners.
- **Phase 4 (Metrics)** → depends on Phase 2; pure functions; blocks the runners.
- **Phase 5 (Redaction shim + export)** → depends on Phase 1 (redactor) + Phase 2; blocks storage in the runners/service.
- **Phase 6 (Runners + CLIs)** → depends on Phases 3–5; needs the service (Phase 7) for the CLI to persist (T033 depends on T036).
- **Phase 7 (Service + API)** → depends on Phases 2, 5, 6; **MVP backend deliverable**.
- **Phase 8 (Optional dashboard)** → depends on Phase 7 (reads/exports); read-only; can be deferred without blocking the MVP.
- **Phase 9 (Security/isolation tests)** + **Phase 10 (Behaviour tests)** → depend on Phases 6–7.
- **Phase 11 (Frontend tests)** → depends on Phase 8.
- **Phase 12 (Quickstart)** → depends on Phases 6–8.
- **Phase 13 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3 — model/RAG/reply metrics, safety/isolation pass-fail, e2e + view/export)

1. Phase 1: Setup (config + audit eval-tag + split/leakage source)
2. Phase 2: DB + models + schemas + migration (**CRITICAL**)
3. Phase 3: Fixtures + leakage check + two seeded eval tenants
4. Phase 4: Metrics (sklearn classification + RAG/reply/risk + pass/fail scorers, NaN-safe)
5. Phase 5: Redaction shim + export (redact-and-flag, JSON/CSV/Markdown)
6. Phase 6: Eight runners + CLIs (real services on the eval tenant; no autonomy/pollution)
7. Phase 7: Service (`create_run` role-gate/dispatch/persist/finalize) + API (trigger + reads + export; immutable 405)
8. **STOP and VALIDATE**: run the security + behaviour tests; confirm held-out-only, redaction/no-leak, isolation-tested, run-vs-test status, no-autonomy/no-pollution, owner-triggers/oversight-reads

### Incremental Delivery

1. Setup + DB + fixtures + metrics + redaction/export → foundation ready
2. US1 (classifier/RAG/reply runs on held-out + golden) → the headline "does the AI work?" numbers
3. US2 (guardrail red-team + tenant-isolation pass/fail) → the safety/trust evidence
4. US3 (11 e2e scenarios + view/export + dashboard) → the demo backbone + report artifacts
5. US4 (versioned golden sets, disjoint-checked, synthetic) → the durability/reproducibility layer
6. Optional dashboard → read-only summary cards + confusion matrix + pass/fail grid + export buttons
7. Tests + quickstart + acceptance → all 22 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- **Out-of-band** — the harness lives in `backend/eval/` (CLIs + notebook are primary); a thin `EvaluationService` lets optional endpoints + the dashboard call the **same** runners; no eval step is added to the live message pipeline (FR-001, FR-017, research.md Decision 1)
- **Held-out only** — model metrics use `validation`/`test`/`golden` splits; `split=train` is rejected at the schema (T009) and re-checked in the runner; golden∩train=∅ is asserted by id + content hash and fails loudly (FR-012, AC-02, T013). First hard guarantee
- **Redaction + leak-as-failure** — every stored `input_payload`/`actual_output`/`metadata` and every artifact passes the 014/013 redactor; a captured secret/PII is redacted in storage **and** sets the originating safety test `passed=false` (FR-016, SP-02, AC-16, AC-17, T021, T049). Second hard guarantee
- **Isolation is tested, not assumed** — the isolation runner actively probes A→B for messages/documents/rag_sources/tasks/escalations/audit_logs + a RAG query; any leak is a hard `passed=false`; `no_cross_tenant_source_rate` must be 1.0 (FR-009, SP-06, AC-05, AC-08, T029). Third hard guarantee
- **Run status vs test pass/fail** — `failed` = harness/execution error only (model missing, fixture unreadable) with an `error_message`/`notes`; a `completed` run may contain many `passed=false` results, surfaced with expected vs actual (FR-019, AC-19, T063, research.md Decision 8). Fourth hard guarantee
- **No autonomy / no pollution** — runners never auto-send a reply or auto-create a task/escalation (they assert the **recommendation**); eval data stays in the eval tenant/namespace and eval audit entries carry the `eval_run_id` tag so a real manager isn't misled (FR-010, FR-017, SP-07, SP-08, AC-09, AC-18, T032, research.md Decisions 9 & 12). Fifth hard guarantee
- **Owner triggers, oversight reads** — only `EVAL_OWNER_ROLE` can trigger a run; manager/instructor are read-only and reads are side-effect-free; reads are tenant-scoped where `tenant_id` is set, cross-tenant → 404/403; Platform Admin has no cross-tenant eval read (FR-015, FR-020, SP-04, SP-05, AC-15, AC-20, T036, T051, T052). Sixth hard guarantee
- **Refusal scored separately** — RAG `refusal_correctness` is independent of `source_*_correctness` so a "refuse-everything" or "always-answer" model can't game the score (FR-018, AC-04, T016, research.md Decision 6)
- **Immutable evidence** — `evaluation_runs`/`evaluation_results` are append-only (no `updated_at`, no PATCH/PUT/DELETE route → 405); re-running creates a new run; prior runs are retained for trend/regression comparison (AC-21, T053, research.md Decision 5)
- **NaN-safe metrics** — no-support classes / empty golden sets → `null` and a clear note, never a crash or a fake 100% (AC-22, T015, T064, research.md Decision 4)
- **Storage + artifacts** — structured records in Postgres (queryable, scope-gated, paginated for the dashboard) + report-ready JSON/CSV/Markdown files under `EVAL_ARTIFACT_DIR/<run_id>/`, paths recorded in `run.artifact_paths` (FR-013, AC-13, research.md Decision 10)
- **Real components on a dedicated eval tenant** — runners call the real 006–014 services so the evidence reflects the actual system; RAG/e2e/isolation use eval tenants A/B with synthetic documents; the classifier run may be global (`tenant_id=null`) (research.md Decision 3); lightweight stubs (e.g., refuse-all) are used only to test the harness itself (AC-04)
- **No model training/tuning here** — this feature **loads existing artifacts** (the chosen 006 model) and measures them; it never trains, tunes, or changes the model using test data (spec Out of Scope)
- This feature **observes/measures** 001–014 and produces the report/presentation evidence; it changes no production behavior and adds no step to the live pipeline
