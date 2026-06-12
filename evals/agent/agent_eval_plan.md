# Agent Evaluation Scaffold

Offline, deterministic evaluation for the **dry-run agent orchestrator**
(`AgentOrchestratorService`). It checks that the bounded agent recommends the
right action for each intent/risk combination — and, crucially, that it does
**not** run for non-risky intents.

## Purpose

The agent must not run freely and must produce predictable recommendations for
risky/complex messages. This eval pins that behavior: it replays a golden set of
`(intent_label, risk_level)` cases through the pure `decide()` method and asserts
the recommendation fields match expectations exactly. It guards against silent
rule drift as the orchestrator evolves.

This evaluates **decision rules only** — no database, no HTTP endpoint, no RAG,
no LLM, no writes. The `apply=true` path is intentionally out of scope.

## Labels / triggers tested

Trigger intents (agent runs):

| Intent | Expected recommendation |
|--------|--------------------------|
| `complaint` | escalation |
| `cancellation_request` | escalation |
| `payment_issue` | task (task **and** escalation when risk is high) |
| `urgent_change` | task **and** escalation |
| `guest_count_change` | task |
| `human_escalation` | escalation |

Non-trigger intents (agent skips with `skipped_reason="intent_not_in_trigger_set"`):
`booking_inquiry`, `pricing_request`, `service_question`, `other`.

Edge rules also covered:
- **High risk forces escalation** even for a task-only intent (`payment_issue` high → task + escalation).
- **Missing/unclear `risk_level`** on a trigger intent → `human_review_required=true`, `confidence="low"`.

## Command

Run from the repository root:

```bash
PYTHONPATH=backend:. python evals/agent/evaluate.py
```

(Or inside the dockerized stack with the repo mounted, e.g.
`docker compose run --rm --no-deps -v "$PWD":/repo -w /repo api \
  bash -lc 'PYTHONPATH=backend:. python evals/agent/evaluate.py'`.)

The runner writes `eval-artifacts/agent_eval.json` and exits non-zero if the
pass rate is below the threshold (so it can gate CI later).

## Metrics

- **total / passed / failed** — per-case results; a case passes only when *all*
  compared fields match.
- **pass_rate** — `passed / total`; **threshold = 1.0** (deterministic rules,
  so any mismatch is a real regression).
- **per_intent** — support and pass rate broken down by intent.
- Compared fields: `ran`, `skipped_reason`, `recommended_task.should_create`,
  `recommended_escalation.should_escalate`, `human_review_required`, `confidence`.
- **failed_cases** — full mismatch detail (expected vs actual) for any failure.

The runner also validates coverage: every trigger intent and every required
non-trigger intent must appear in the golden set, or it aborts.

## Limitations

- Tests the **decision rules**, not the HTTP endpoint, auth, or tenant isolation
  (those are covered by `tests/integration/test_agent_run.py`).
- Cases are driven by pre-set `intent_label`/`risk_level`; this does **not**
  evaluate the intent classifier or risk detector themselves (see the classifier
  and RAG eval scaffolds for those).
- No RAG grounding, suggested-reply quality, or `apply=true` execution is
  assessed — all out of scope for the dry-run agent.
- Determinism means the threshold is strict (1.0); if rules intentionally change,
  update the golden set's `expected` blocks in the same change.
