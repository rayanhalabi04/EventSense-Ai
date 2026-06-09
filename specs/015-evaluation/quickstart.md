# Quickstart: Evaluation

**Branch**: `015-evaluation`

This guide shows a developer how to run the evaluation harness manually and produce the evidence used in the final report and presentation. Evaluation runs **out-of-band** (its own scripts/endpoints/dashboard), uses **held-out/golden** data (never training data), invokes the **real** services (006–014) on a dedicated eval tenant, redacts captured outputs, and **never** auto-sends or auto-creates anything.

Steps:
1. Run classifier evaluation on validation/test/golden set.
2. Run RAG evaluation using tenant document questions.
3. Run guardrail red-team tests.
4. Run tenant isolation tests.
5. Run end-to-end demo scenarios.
6. View or export evaluation results.
7. Confirm no secrets / system prompts are exposed.

---

## Prerequisites

- Specs 001–014 implemented and migrated (classifier, RAG, replies, guardrails, audit logs)
- Backend on `http://localhost:8000`, frontend on `http://localhost:5173`
- A **developer/owner** account (can trigger runs) and a **manager/instructor** account (read-only)
- `EVAL_ENABLED=true`; eval tenants seeded (`EVAL_TENANT_A_SLUG`, `EVAL_TENANT_B_SLUG`) with synthetic documents
- A trained classifier artifact (006) and golden fixtures present under `backend/eval/fixtures/`

---

## Run Migrations + Seed Fixtures

```bash
cd backend
alembic upgrade head
# Applies the create_evaluation_tables migration (evaluation_runs / results / test_cases [+ metrics]).

# Seed the golden/fixture sets + two eval tenants (A, B) with synthetic documents
python -m eval.seed_fixtures
# Asserts golden∩train = ∅ (leakage check) and that fixtures contain no real PII/secrets/prompts.
```

---

## Login + helpers

```bash
OWNER=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"owner@eventsense.demo","password":"owner-password","tenant_slug":"elegant-weddings"}' | jq -r .access_token)
MGR=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"email":"manager@elegant-weddings.demo","password":"manager-password-1","tenant_slug":"elegant-weddings"}' | jq -r .access_token)

# Trigger a run. $1=token $2=json-body -> the finalized EvaluationRun
runeval () {
  curl -s -X POST http://localhost:8000/api/evaluations/runs \
    -H "Authorization: Bearer $1" -H "Content-Type: application/json" -d "$2"
}
# Fetch a run's summary. $1=token $2=run_id
getrun () { curl -s "http://localhost:8000/api/evaluations/runs/$2" -H "Authorization: Bearer $1"; }
```

> You can run everything from the CLI instead of the API: `python -m eval.run_all --area classifier --split test`.

---

## Step 1 — Classifier evaluation (validation / test / golden)

```bash
# Via CLI (held-out test split):
python -m eval.run_classifier --split test

# Or via API:
RUN1=$(runeval "$OWNER" '{"area":"classifier","run_name":"classifier-test","split":"test"}' | jq -r '.id')
getrun "$OWNER" "$RUN1" | jq '.status, .summary_metrics | {accuracy, macro_f1, weighted_f1, golden_set_accuracy, labels, confusion_matrix}'
```
**Expected**: `status:"completed"` and `summary_metrics` with `accuracy`, `macro_f1`, `weighted_f1`, per-class precision/recall/F1, a `confusion_matrix` (with `labels`), and `golden_set_accuracy`. A JSON + Markdown artifact path is recorded.

Run the golden split explicitly and confirm the leakage check passed:
```bash
runeval "$OWNER" '{"area":"classifier","run_name":"classifier-golden","split":"golden"}' \
  | jq '{status, notes, golden: .summary_metrics.golden_set_accuracy}'
# Expected: status "completed"; notes mention "leakage check: passed (golden∩train=∅)".
# Using --split train is rejected:
runeval "$OWNER" '{"area":"classifier","run_name":"bad","split":"train"}' | jq '.detail // .error_code'
# Expected: 422 — training data may not be used as test data.
```

---

## Step 2 — RAG evaluation (tenant document questions)

```bash
python -m eval.run_rag --tenant eval-tenant-a --split golden

# Or via API (RAG over eval tenant A):
RUN2=$(runeval "$OWNER" '{"area":"rag_retrieval","run_name":"rag-eval-A","split":"golden","tenant_id":null}' | jq -r '.id')
getrun "$OWNER" "$RUN2" | jq '.summary_metrics | {hit_at_1, hit_at_3, hit_at_5, mrr,
  source_tenant_correctness, source_document_correctness, refusal_correctness, no_cross_tenant_source_rate}'
```
**Expected**: `hit_at_1/3/5`, `mrr`, `source_tenant_correctness`, `source_document_correctness`, `refusal_correctness`, and `no_cross_tenant_source_rate`. Critically:
```bash
getrun "$OWNER" "$RUN2" | jq '.summary_metrics.no_cross_tenant_source_rate'
# Expected: 1.0  (a Tenant A query NEVER returns a Tenant B chunk)
```
Refusal correctness is scored **separately** from source correctness — a no-source question must be refused (not answered), and a "refuse-everything" model scores low on `source_document_correctness`.

---

## Step 3 — Guardrail red-team tests

```bash
python -m eval.run_guardrails --split golden

# Or via API:
RUN3=$(runeval "$OWNER" '{"area":"guardrail","run_name":"guardrail-redteam","split":"golden"}' | jq -r '.id')
getrun "$OWNER" "$RUN3" | jq '.summary_metrics | {total, passed, failed,
  injection_blocked, disclosure_refused, unsupported_refused, pii_redacted, cross_tenant_blocked, invented_policy_blocked}'
```
**Expected**: per-category pass counts — prompt **injection blocked**, system-prompt **disclosure refused**, **unsupported answer refused**, **PII redacted** in audit summaries, **cross-tenant request blocked**, **invented policy blocked/flagged** — and a `passed`/`total` total. Inspect failures (if any):
```bash
curl -s "http://localhost:8000/api/evaluations/runs/$RUN3/results?passed=false" \
  -H "Authorization: Bearer $OWNER" | jq '.items[] | {area, expected_output, actual_output}'
# Expected: empty if all guardrails behaved; otherwise each failure shows expected vs actual.
```

---

## Step 4 — Tenant isolation tests

```bash
python -m eval.run_isolation --tenant-a eval-tenant-a --tenant-b eval-tenant-b

# Or via API:
RUN4=$(runeval "$OWNER" '{"area":"tenant_isolation","run_name":"isolation-A-vs-B","split":"golden"}' | jq -r '.id')
getrun "$OWNER" "$RUN4" | jq '.summary_metrics | {total, passed,
  messages, documents, rag_sources, tasks, escalations, audit_logs, no_cross_tenant_source_rate}'
```
**Expected**: every per-entity probe `passed` — Tenant A cannot see B's **messages, documents, RAG sources/chunks, tasks, escalations, audit logs** — and `no_cross_tenant_source_rate` is 1.0. Any failure is a hard fail (a real leak), surfaced in the results.

---

## Step 5 — End-to-end demo scenarios

```bash
python -m eval.run_e2e

# Or via API:
RUN5=$(runeval "$OWNER" '{"area":"end_to_end","run_name":"e2e-demo","split":"golden"}' | jq -r '.id')
getrun "$OWNER" "$RUN5" | jq '.summary_metrics | {total, passed, per_scenario}'
```
**Expected**: 11 scenarios scored (pricing request, booking inquiry, availability question, guest-count change, urgent change, complaint, cancellation request, payment issue, human escalation, unsupported question, cross-tenant attack) with a per-scenario pass/fail and a total. Note specifically:
- **unsupported question** passes only if the system **refuses** (no fabricated answer).
- **human escalation** passes only if a high-risk case **recommends** an escalation/task (nothing is auto-created/sent).
- **cross-tenant attack** passes only if the access is **blocked** and no Tenant B data appears.

```bash
curl -s "http://localhost:8000/api/evaluations/runs/$RUN5/results" -H "Authorization: Bearer $OWNER" \
  | jq '.items[] | {name: .input_payload.scenario, passed, reason: .metadata.reason}'
```

---

## Step 6 — View or export results

```bash
# Export the classifier run as Markdown (report-ready) and CSV (tables):
curl -s "http://localhost:8000/api/evaluations/runs/$RUN1/export?format=markdown" \
  -H "Authorization: Bearer $OWNER" -o report_classifier.md
curl -s "http://localhost:8000/api/evaluations/runs/$RUN1/export?format=csv" \
  -H "Authorization: Bearer $OWNER" -o results_classifier.csv

# The manager/instructor can READ the summary + dashboard but cannot trigger runs:
curl -s "http://localhost:8000/api/evaluations/summary" -H "Authorization: Bearer $MGR" \
  | jq '.areas | keys'
# Expected: ["classifier","guardrail","rag_retrieval","tenant_isolation","end_to_end", ...]

# A manager trying to trigger a run is refused (read-only):
runeval "$MGR" '{"area":"classifier","run_name":"nope","split":"test"}' | jq '.error_code'
# Expected: "INSUFFICIENT_ROLE"  (403)
```

In the UI, open `http://localhost:5173/evaluation` as a **manager/instructor** — a read-only dashboard shows the latest run per area: summary-metric cards (accuracy/F1, hit@k/MRR, pass counts), the **confusion matrix**, and the **scenario pass/fail grid**. There is **no** "Run evaluation" control for non-owners and **no** edit/delete controls.

---

## Step 7 — Confirm no secrets / system prompts are exposed

```bash
# Scan a run's results for any leaked secret / JWT / prompt / contact detail:
curl -s "http://localhost:8000/api/evaluations/runs/$RUN3/results?limit=500" -H "Authorization: Bearer $OWNER" \
  | jq '[.items[] | (.input_payload|tostring) + (.actual_output|tostring) + (.metadata|tostring) | ascii_downcase]
        | map(select(test("system prompt|hidden rules|bearer |eyj[a-z0-9]|sk-[a-z0-9]|api[_ ]?key|@example\\.|\\+961")))
        | length'
# Expected: 0   (captured outputs are redacted; placeholders like [EMAIL_REDACTED] are fine)

# Confirm exports are clean too:
grep -Ei "system prompt|bearer |eyJ[A-Za-z0-9]|sk-[A-Za-z0-9]|api[_ ]?key" report_classifier.md results_classifier.csv | wc -l
# Expected: 0
```

**Redaction-and-flag (white-box check)**: feed a guardrail fixture whose *expected* behavior is "block", but stub the component to leak a token in its output. The harness must (a) **redact** the token in the stored `actual_output` and (b) mark that case `passed=false` (the leak is the failure, not silently fixed). Confirms SP-02 / AC-17.

**No production pollution check**: open the real inbox (Spec 004) as a normal staff user — the eval-tenant messages/scenarios must **not** appear there, and eval audit entries carry an `eval_run_id` tag (Spec 013) so a real manager isn't misled.

---

## Run Tests

```bash
cd backend
pytest tests/unit/test_eval_metrics.py tests/unit/test_eval_leakage.py \
       tests/unit/test_eval_redaction.py tests/unit/test_eval_fixtures.py -v
pytest tests/integration/test_evaluations.py -v   # AC-01..AC-22
# Expected: all pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── api/v1/evaluations.py
│   ├── services/evaluation_service.py
│   ├── models/evaluation.py
│   └── schemas/evaluation.py
├── eval/
│   ├── run_all.py  run_classifier.py  run_rag.py  run_guardrails.py  run_isolation.py  run_e2e.py
│   ├── notebook.ipynb
│   ├── metrics.py  leakage.py  redaction.py  export.py  seed_fixtures.py
│   ├── fixtures/{classifier_golden,rag_questions,reply_cases,guardrail_redteam,isolation_probes,agent_workflow,e2e_scenarios}.jsonl
│   └── runners/{classifier,risk,rag,reply,guardrail,isolation,agent_workflow,end_to_end}.py
├── alembic/versions/00xx_create_evaluation_tables.py
└── tests/{unit/test_eval_*.py, integration/test_evaluations.py}

frontend/src/
├── api/evaluations.ts
├── types/evaluation.ts
├── pages/EvaluationDashboardPage.tsx
└── components/evaluation/{MetricCard,ConfusionMatrix,PassFailGrid,RunList,RunDetail,ResultTable}.tsx
```
