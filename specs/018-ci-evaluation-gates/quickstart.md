# Quickstart: CI Evaluation Gates

**Branch**: `018-ci-evaluation-gates`

Run the same quality + safety gate locally that CI runs on every push/PR, and understand what makes a build fail.

Steps:
1. Run the gate locally.
2. Read the per-gate result.
3. Tune a threshold.
4. Understand zero-tolerance safety gates.

---

## Prerequisites

- Specs 015 (Evaluation) and 017 (Dockerized Stack) implemented and runnable headlessly.
- Docker + Docker Compose v2 (for the stack + smoke).
- Python for the gate script; committed eval fixtures/golden sets (synthetic/redacted).

---

## 1. Run the gate locally

```bash
make ci
```

This runs, in order: backend unit + integration tests → `docker compose up` (Spec 017) → Docker smoke test → Spec 015 eval suites (`classifier`, `rag_retrieval`, `guardrail`, `tenant_isolation`, `agent_workflow`) → the gate check (`scripts/ci_gate.py`). It exits non-zero if any gate fails — exactly like CI.

Artifacts land in `eval-artifacts/` (Spec 015 JSON/Markdown + `docker_smoke.json` + `gate_summary.md`).

## 2. Read the per-gate result

`scripts/ci_gate.py` prints a table and writes `eval-artifacts/gate_summary.md`:

```
GATE              RESULT   DETAIL
tests             PASS
docker_smoke      PASS
classifier        PASS     macro_f1=0.86 (floor 0.80)
rag_retrieval     FAIL     hit_at_3=0.62 (floor 0.70)
guardrail         PASS     12/12 red-team cases
tenant_isolation  PASS     6/6 probes
agent_workflow    PASS
=> BUILD FAILED (rag_retrieval below floor)
```

## 3. Tune a threshold

All floors live in **one committed file** — `eval/thresholds.yaml`:

```yaml
classifier:
  macro_f1_floor: 0.80
  accuracy_floor: 0.82
rag_retrieval:
  hit_at_3_floor: 0.70
  mrr_floor: 0.60
  refusal_correctness_floor: 0.90
safety:
  guardrail_zero_tolerance: true
  isolation_zero_tolerance: true
```

Change a floor → it's a reviewable diff → it takes effect on the next run. Nothing is hidden in the workflow YAML or code.

## 4. Zero-tolerance safety gates

`guardrail`, `tenant_isolation`, and the agent's no-autonomous-side-effect check are **zero-tolerance**: a single failing red-team case or a single cross-tenant leak fails the build, regardless of the quality metrics. Loosening them requires an explicit, reviewed change to `safety:` in the config — never a silent default.

---

## What fails a build

| Gate | Fails when |
|------|-----------|
| `tests` | any unit/integration test fails |
| `docker_smoke` | the Spec 017 smoke test exits non-zero |
| `classifier` | macro-F1 or accuracy below floor |
| `rag_retrieval` | hit@3 / MRR / refusal-correctness below floor, or any cross-tenant source |
| `guardrail` | any red-team case fails (zero tolerance) |
| `tenant_isolation` | any A-reads-B probe fails (zero tolerance) |
| `agent_workflow` | wrong action, bound breach, or any autonomous side effect |
| config/metric gap | threshold file missing/malformed or a required metric absent (fail closed) |

---

## In CI

- Triggers on push/PR (`.github/workflows/ci.yml`); a nightly workflow runs the fuller suite.
- Uploads `eval-artifacts/**` and writes the per-gate summary to the job summary.
- Core gates need **no secrets**; forked PRs never receive production secrets (secret stages are gated to trusted runs).
- Artifacts/logs carry no secrets/prompts/cross-tenant data (Spec 015 redaction).
