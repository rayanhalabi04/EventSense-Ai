# Requirements Checklist: Evaluation

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (defensible evidence for the report/presentation) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Evaluation behavior, Security/privacy, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Evaluation harness runnable from scripts/notebooks/(optional) endpoints, separate from the production workflow (FR-001, AC-18)
- [ ] Eight areas supported, each recorded as an `EvaluationRun` (FR-002)
- [ ] `EvaluationRun` stores id, nullable tenant_id, run_name, area, status, started_at, completed_at, created_by, summary_metrics, artifact_paths, notes (FR-003, AC-11)
- [ ] `EvaluationResult` stores run id, nullable test_case_id, area, input/expected/actual, passed, score, error_message, metadata, created_at (FR-004, AC-12)
- [ ] Golden test sets supported per area, loaded from versioned fixtures, disjoint from training data (FR-012, AC-02)
- [ ] Results storable + exportable to JSON/CSV/Markdown; artifact_paths recorded; usable in report (FR-013, AC-13)
- [ ] Optional read-only dashboard shows latest summary + pass/fail grid + confusion matrix, no triggers (FR-014, AC-14)
- [ ] Triggering requires developer/owner; manager/instructor read-only; reads side-effect-free (FR-015, AC-15)
- [ ] No secrets/JWTs/API keys/system prompts/private tenant data in any result/log/artifact/export (FR-016, AC-16)
- [ ] Stored input_payload/actual_output pass through redactor; leaked secret redacted + flagged as failed test (FR-016, AC-17)
- [ ] Evaluation does not pollute production (synthetic/eval tenant; eval data not in real inbox; eval audit tagged) (FR-017, AC-18)
- [ ] Test failure leaves run `completed`; harness error marks run `failed` with error_message (FR-019, AC-19)
- [ ] Reads tenant-scoped where tenant_id set; cross-tenant run/result read → 404/403 (FR-020, AC-20)
- [ ] Re-running creates a new run; prior runs retained (no overwrite) (AC-21)

---

## Classifier Evaluation Requirements

- [ ] Computes accuracy, macro_f1, weighted_f1 (FR-005, AC-01)
- [ ] Computes per-class precision, recall, f1 (FR-005, AC-01)
- [ ] Produces confusion_matrix with label ordering (FR-005, AC-01)
- [ ] Computes golden_set_accuracy over the golden split (FR-005, AC-01)
- [ ] Golden set disjoint from training data (leakage check passes/fails loudly) (FR-012, AC-02)
- [ ] Uses validation/test/golden splits only — never training data (FR-012; `split=train` → 422)
- [ ] No-support class → NaN-safe per-class metric (null), not a crash (AC-22)

---

## RAG Evaluation Requirements

- [ ] Computes hit_at_1, hit_at_3, hit_at_5 (FR-006, AC-03)
- [ ] Computes mrr (FR-006, AC-03)
- [ ] Computes source_tenant_correctness and source_document_correctness (FR-006, AC-03)
- [ ] Computes refusal_correctness, scored separately from source correctness (FR-018, AC-04)
- [ ] Computes no_cross_tenant_source_rate = 1.0 (no Tenant B chunk for a Tenant A query) (FR-006, AC-05)
- [ ] No-source question → expected refusal counts as a pass (FR-006, AC-04)

---

## Suggested Reply Evaluation Requirements

- [ ] Reports groundedness per case + aggregate (FR-007, AC-06)
- [ ] Reports no_unsupported_claims (FR-007, AC-06)
- [ ] Reports source_usage (FR-007, AC-06)
- [ ] Groundedness reuses the 014 grounding validator (no invented policies/prices counted grounded)

---

## Guardrail Evaluation Requirements

- [ ] Prompt injection blocked (pass/fail) (FR-008, AC-07)
- [ ] System-prompt disclosure refused (no prompt text in output) (FR-008, AC-07)
- [ ] Unsupported answer refused (FR-008, AC-07)
- [ ] PII redacted in audit summaries ([EMAIL_REDACTED]/[PHONE_REDACTED]) (FR-008, AC-07)
- [ ] Cross-tenant request blocked (FR-008, AC-07)
- [ ] Invented policy blocked or flagged (FR-008, AC-07)
- [ ] Each case yields an `EvaluationResult` with expected vs actual; run summary reports pass count

---

## Tenant Isolation Evaluation Requirements

- [ ] Tenant A cannot see Tenant B messages (FR-009, AC-08)
- [ ] Tenant A cannot retrieve Tenant B documents (FR-009, AC-08)
- [ ] Tenant A RAG never returns Tenant B chunks (no_cross_tenant_source_rate=1.0) (FR-009, AC-05, AC-08)
- [ ] Tenant A cannot see Tenant B tasks (FR-009, AC-08)
- [ ] Tenant A cannot see Tenant B escalations (FR-009, AC-08)
- [ ] Tenant A cannot see Tenant B audit logs (FR-009, AC-08)
- [ ] Any leak is a hard failure (passed=false), surfaced, not a warning (SP-06)

---

## End-to-End Scenario Requirements

- [ ] 11 named scenarios run with per-scenario pass/fail + total (FR-011, AC-10)
- [ ] Pricing request scenario asserts correct intent/handling
- [ ] Booking inquiry / availability / guest-count change scenarios asserted
- [ ] Urgent change / complaint scenarios asserted
- [ ] Cancellation request / payment issue scenarios asserted
- [ ] Human escalation scenario passes only if high-risk **recommends** action (no auto-create/send) (FR-010, AC-09)
- [ ] Unsupported question scenario passes only if the system refuses (no fabrication)
- [ ] Cross-tenant attack scenario passes only if blocked + no Tenant B data
- [ ] Agent/workflow suite asserts no autonomous side effects (FR-010, AC-09)

---

## API / Storage Requirements

- [ ] `POST /api/evaluations/runs` owner-only; `split=train` → 422; tests-failed still `completed` (FR-015, AC-15, AC-19)
- [ ] `GET /api/evaluations/runs` list with filters + pagination, scope-gated (FR-020, AC-20)
- [ ] `GET /api/evaluations/runs/{id}` full summary + artifact paths; cross-tenant → 404/403 (AC-20)
- [ ] `GET /api/evaluations/runs/{id}/results` paginated per-case results (redacted) (FR-004, AC-12)
- [ ] `GET /api/evaluations/summary` latest per area for dashboard (FR-014, AC-14)
- [ ] `GET /api/evaluations/runs/{id}/export` JSON/CSV/Markdown; export matches summary; redacted (FR-013, AC-13, AC-16)
- [ ] Optional per-area triggers (`/classifier/run`, `/rag/run`, `/guardrails/run`) owner-only (FR-015)
- [ ] No update/delete routes; mutate attempts → 405 (immutable evidence)
- [ ] Three tables created via Alembic (evaluation_runs/results/test_cases [+ metrics]); append-only
- [ ] Run/result fields persisted exactly per data-model; NaN-safe metrics stored as null (AC-11, AC-12, AC-22)
- [ ] Artifacts written to `EVAL_ARTIFACT_DIR/<run_id>/` with paths in `artifact_paths`

---

## Security / Privacy Requirements

- [ ] Fixtures/golden sets contain no real secrets/JWTs/API keys/system prompts (synthetic/redacted only) (SP-01)
- [ ] Captured input_payload/actual_output redacted before storage; leak → redacted + failed test (SP-02, AC-17)
- [ ] No private tenant data in exports/dashboard (synthetic eval-tenant data) (SP-03, AC-16)
- [ ] Tenant-scoped reads; cross-tenant run/result read blocked (SP-04, AC-20)
- [ ] Trigger is privileged (owner); manager/instructor read-only; reads cause no writes (SP-05, AC-15)
- [ ] Isolation is actively probed for every entity + a RAG query; leak is a hard failure (SP-06, AC-05, AC-08)
- [ ] Eval audit entries tagged/eval-namespaced (SP-07, AC-18)
- [ ] No production pollution: eval data confined to eval tenant/namespace, not in real inbox/dashboards (SP-08, AC-18)
- [ ] No secrets/JWTs/system prompts/API keys in evaluation logs (FR-016, AC-16)

---

## Testing Requirements

- [ ] Unit: classification metrics correctness + NaN-safety (AC-01, AC-22)
- [ ] Unit: RAG hit@k/MRR + refusal-separation (refuse-all scores low on source-correctness) (AC-04)
- [ ] Unit: golden∩train disjointness fails on overlap (AC-02)
- [ ] Unit: captured secret/PII redacted + flagged as failed test (AC-17)
- [ ] Unit: fixtures contain no secrets/prompts/real-PII (SP-01)
- [ ] Integration: classifier run → summary keys + artifact (AC-01); RAG run → metrics incl. no_cross_tenant_source_rate=1.0 (AC-03, AC-05); reply metrics (AC-06)
- [ ] Integration: guardrail suite per-case pass/fail (AC-07); isolation suite per-entity (AC-08); agent recommends + no autonomy (AC-09); e2e 11 scenarios (AC-10)
- [ ] Integration: run/result persistence with all fields (AC-11, AC-12); export JSON/CSV/Markdown matches summary (AC-13)
- [ ] Integration: no secrets/prompts/cross-tenant in results/exports (AC-16); no prod pollution / eval audit tagged (AC-18)
- [ ] Integration: run `completed` on test failure vs `failed` on harness error (AC-19); tenant-scoped reads + cross-tenant 404/403 (AC-20); re-run new run (AC-21)
- [ ] Integration: non-owner trigger → 403; read side-effect-free (AC-15)
- [ ] Frontend: dashboard renders summary cards + confusion matrix + pass/fail grid; owner-only trigger control; no edit/delete; export buttons (AC-14)
- [ ] Quickstart: all 7 steps (classifier, RAG, guardrail, isolation, e2e, view/export, no-secrets check)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No continuous/automated CI evaluation gating
- [ ] No model training / hyperparameter tuning / AutoML
- [ ] No live A/B testing or online production metrics
- [ ] No real-user labeling / annotation UI
- [ ] No public benchmark leaderboards / external result publishing
- [ ] No editing or deleting evaluation runs/results (immutable; re-run instead)
- [ ] No exposing secrets, system prompts, JWTs, API keys, or private tenant data
- [ ] No using training data as final test data (held-out/golden only, disjoint-checked)
- [ ] No requiring evaluation in the production user workflow (out-of-band only)
- [ ] No auto-sending replies / auto-creating tasks or escalations from the harness
- [ ] No real WhatsApp API, no calendar syncing, no full CRM

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order): fixtures + leakage check → metrics → redaction + export → runners + service → CLIs/notebook → API → optional dashboard.
- Hard guarantees to verify: (1) **held-out only** — golden∩train = ∅, `split=train` rejected; (2) **redaction** — no secrets/JWTs/keys/system prompts/private tenant data in any result/log/artifact/export, and a captured leak is redacted **and** fails its safety test; (3) **tenant isolation is tested, not assumed** — every entity + a RAG query probed, `no_cross_tenant_source_rate=1.0`; (4) **run vs test status** — harness error → `failed`, test failure → `completed` with `passed=false` surfaced; (5) **no autonomy / no pollution** — never auto-send/create; eval data confined + eval audit tagged; (6) **owner triggers, oversight reads** — reads are side-effect-free.
- This feature **observes/measures** features 001–014 and produces the report/presentation evidence; it changes no production behavior and adds no step to the live pipeline.
