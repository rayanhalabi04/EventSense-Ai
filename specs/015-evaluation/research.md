# Research: Evaluation

**Branch**: `015-evaluation` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context (001–014). No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Out-of-Band Harness (Scripts + Thin Service), Not a Pipeline Step

**Decision**: The evaluation harness lives in its own package (`backend/eval/`) as CLI scripts + a notebook, with a thin `EvaluationService` that lets optional endpoints and a dashboard call the **same** runners. Evaluation is never a required step in the live message pipeline.

**Rationale**:
- The spec is explicit: evaluation must not be mixed with the production workflow (FR-001, FR-017). Scripts/notebooks are how a developer actually produces report numbers, and they're the most reproducible. A thin service over the same runners gives the optional endpoints/dashboard without a second code path that could drift.
- Keeping the harness out of the request path means it can seed an eval tenant, run slow suites, and write artifacts without touching production latency or data.

**Alternatives considered**:
- Endpoints-first (harness logic inside FastAPI handlers): couples long-running eval to HTTP timeouts and a request context; rejected — runners are plain functions, endpoints are a thin trigger.
- Eval baked into the pipeline (score every live message): pollutes production, adds latency, and conflates eval with serving; explicitly forbidden.

---

## Decision 2: Golden Sets Are Versioned Fixtures, Disjoint-Checked from Training

**Decision**: Golden test sets are versioned fixture files (`backend/eval/fixtures/*.jsonl`), separate from the classifier's training data (006). A `leakage.py` check asserts golden/test ∩ train = ∅ by stable id **and** content hash, failing loudly on any overlap.

**Rationale**:
- Using training data as test data inflates metrics and is explicitly forbidden. A disjointness check by id + hash catches both accidental duplication and near-duplicate copy-paste, making `golden_set_accuracy` trustworthy (FR-012, AC-02).
- Versioned fixtures make runs reproducible and let the report cite a specific golden-set version.

**Alternatives considered**:
- Trust a manual train/test split without a check: silent leakage is the most common eval bug; rejected — assert it programmatically.
- Generate golden cases at runtime from the same distribution as training: risks leakage and non-reproducibility; rejected — curated, versioned fixtures.

---

## Decision 3: Invoke the Real Services on a Dedicated Eval Tenant

**Decision**: Runners call the **real** production service functions (classifier predict, RAG retrieve, reply generate, `guardrails.check_*`) so evidence reflects the actual system. RAG/e2e/isolation runs use a dedicated **eval tenant A (+ B for isolation)** seeded with synthetic documents; the classifier run may be global (`tenant_id=null`) on a shared labeled split.

**Rationale**:
- Mocking the components would prove nothing about the real system. Running them on a separate eval tenant keeps production data clean (FR-017) while still exercising the genuine retrieval/guardrail/grounding code paths the report claims work.
- Two eval tenants give real cross-tenant separation to probe for the isolation suite (SP-06).

**Alternatives considered**:
- Re-implement lightweight stand-ins for speed: diverges from production behavior; rejected for the headline evidence (stubs are used only to test the harness itself, e.g., a "refuse-all" stub for AC-04).
- Run against a real tenant's data: privacy + pollution risk; rejected — synthetic eval tenant only.

---

## Decision 4: scikit-learn for Classification Metrics, Custom Scorers for the Rest

**Decision**: Classification metrics (accuracy, macro/weighted-F1, per-class P/R/F1, confusion matrix with label ordering) use scikit-learn (already in the stack for 006). RAG (hit@k, MRR, source/tenant/refusal correctness, no-cross-tenant-source rate), reply (groundedness/unsupported/source-usage), and pass/fail scorers (guardrail/isolation/agent/e2e) are small custom functions in `metrics.py`. All are NaN-safe.

**Rationale**:
- sklearn's `classification_report`/`confusion_matrix` are correct, well-understood, and match what a report/instructor expects; reusing the 006 dependency avoids new infra.
- RAG/guardrail/isolation metrics are domain-specific and simple to compute deterministically; custom functions keep them transparent and unit-testable (and let refusal-correctness be scored separately — Decision 6).

**Alternatives considered**:
- A heavyweight eval framework (e.g., a full RAG-eval library / LLM-as-judge): adds dependencies, cost, and non-determinism; deferred — deterministic metrics are more defensible for a senior project.
- Hand-rolling classification metrics: error-prone (macro vs weighted F1, label ordering); rejected — use sklearn.

---

## Decision 5: Immutable Runs; Re-Run Instead of Edit/Delete

**Decision**: `evaluation_runs` and `evaluation_results` are append-only (no `updated_at`, no update/delete path). Re-running creates a new `EvaluationRun`; prior runs are retained so trends/regressions are visible.

**Rationale**:
- Evaluation evidence must be trustworthy and comparable over time; editable results undermine that. Immutability mirrors Spec 013/014 records and lets the report show improvement across runs (AC-21).

**Alternatives considered**:
- Overwrite the "latest" run per area: loses history and invites cherry-picking; rejected.
- Allow deleting a bad run: a `failed` run with an `error_message` is more honest than a hole; rejected (keep the record).

---

## Decision 6: Score Refusal Correctness Separately from Source Correctness

**Decision**: RAG evaluation scores `refusal_correctness` (did it correctly refuse when **no** source exists?) **separately** from `source_*_correctness` (did it return the right source when one exists?). A model that refuses everything scores high on refusal but **low** on source-correctness, and vice-versa.

**Rationale**:
- A single blended retrieval score can be gamed: "always refuse" would look safe but useless, and "always answer" would look helpful but unsafe. Separating the two (FR-018, AC-04) makes both failure modes visible and keeps the no-source guarantee (014 GR-02) honestly measured.

**Alternatives considered**:
- One combined accuracy: hides the gaming; rejected.
- Only measure refusal (safety) or only hit@k (retrieval): each alone is incomplete; rejected — report both.

---

## Decision 7: Redact Captured Outputs Before Storage; a Leak Is a Failed Test

**Decision**: Every stored `input_payload`/`actual_output`/`metadata` passes through the 014/013 redactor before persistence. If a captured output unexpectedly contains a secret/JWT/API-key/PII/system-prompt, it is redacted in storage **and** the originating safety test is marked `passed=false` — the leak is the failure, not a silent fix.

**Rationale**:
- The evaluation store/export must never become the leak it was meant to detect (FR-016, SP-02, AC-17). Redacting at the storage boundary is defense-in-depth; flagging the test failure means the evidence honestly shows the system leaked, rather than hiding it behind redaction.

**Alternatives considered**:
- Store raw outputs "for debugging": directly leaks secrets/PII/prompts into artifacts; rejected.
- Redact but don't flag: hides a real safety failure; rejected — redact **and** fail the test.

---

## Decision 8: Run Status vs Test Pass/Fail Are Distinct

**Decision**: An `EvaluationRun.status` of `failed` means the **harness/execution** errored (model missing, fixture unreadable). A **test** failing (`EvaluationResult.passed=false`) does **not** fail the run — a `completed` run can contain many failed tests, surfaced with expected vs actual.

**Rationale**:
- Conflating the two would either hide test failures (if a failed test failed the run and got retried away) or mislabel a working harness as broken. The distinction (FR-019, AC-19) keeps the evidence precise: "the suite ran fine; 2/12 safety tests failed" is a meaningful, honest result.

**Alternatives considered**:
- Any failed test → run `failed`: loses the per-test evidence and the pass-count summary; rejected.
- Swallow harness errors as test failures: hides infra problems as if the model were wrong; rejected.

---

## Decision 9: No Autonomy in the Agent/Workflow Suite

**Decision**: The `agent_workflow` suite asserts that high-risk cases **recommend** the correct action (task/escalation); runners never auto-send a reply or auto-create a task/escalation. A test asserts no runner imports/calls the send/create paths.

**Rationale**:
- The platform's contract (010/011/012/014) is human-in-the-loop; evaluation must respect it and must not create real side effects while measuring. Checking "recommends the right action" (FR-010, AC-09) measures the agent logic without taking the action.

**Alternatives considered**:
- Let the suite actually create tasks/escalations to "test end-to-end": pollutes data and violates the no-autonomy contract; rejected — assert the recommendation, not the side effect.

---

## Decision 10: Storage in Postgres + File Artifacts (JSON/CSV/Markdown)

**Decision**: Structured records live in two Postgres tables (`evaluation_runs`, `evaluation_results`, + optional `evaluation_metrics`); human/report artifacts are written to `EVAL_ARTIFACT_DIR/<run_id>/` as JSON (full), CSV (per-case table), and Markdown (report-ready summary + confusion matrix + pass/fail grid), with paths recorded in `run.artifact_paths`.

**Rationale**:
- The DB gives queryable, paginated, tenant-scoped reads for the dashboard; files give the exact artifacts the final report/presentation needs (Markdown to paste, CSV for tables, JSON for completeness). Recording `artifact_paths` ties the two together (FR-013, AC-13).

**Alternatives considered**:
- Files only (no DB): no dashboard/queries/scope-gating; rejected.
- DB only (no files): awkward to drop into a report; rejected — provide both.

---

## Decision 11: Privileged Trigger, Read-Only Oversight, Tenant-Scoped Reads

**Decision**: Only the developer/owner role (or a service/admin context) can **trigger** a run; managers/instructors are **read-only**; reads are side-effect-free. Runs with a `tenant_id` are readable only within that tenant (and by authorized roles); global runs (`tenant_id=null`) are visible per role/config.

**Rationale**:
- Triggering runs the real components and writes data; it should be privileged (FR-015, SP-05). Oversight (manager/instructor) needs to *see* the evidence during the demo without being able to launch runs or read another tenant's data (FR-020, SP-04).

**Alternatives considered**:
- Anyone authenticated can trigger: risks accidental/abusive runs and pollution; rejected.
- All runs global/visible to everyone: leaks tenant-scoped eval data; rejected — scope reads by tenant.

---

## Decision 12: Eval Audit Entries Are Tagged / Namespaced

**Decision**: Audit entries (013) created during an evaluation carry an `eval_run_id` tag (and/or live under the eval tenant) so they are distinguishable from real activity; eval-created messages/documents/tasks stay in the eval tenant/namespace and never surface in the real inbox or dashboards.

**Rationale**:
- Running the real pipeline produces real-looking audit/inbox entries; without tagging, a real manager could be misled and the production surfaces polluted (FR-017, SP-07, SP-08, AC-18). A tag + eval tenant keeps evaluation honest and contained.

**Alternatives considered**:
- Suppress audit logging during eval: loses the ability to test audit isolation + PII-redaction-in-summary (which the eval needs to verify); rejected — log, but tag.
- Run eval in the real tenants: pollution + privacy risk; rejected — dedicated eval tenant.
