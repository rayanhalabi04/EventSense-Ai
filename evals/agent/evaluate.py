"""Deterministic evaluation for the dry-run agent orchestrator (Phase A/B).

The agent's decision is a pure function of a message's ``intent_label`` and
``risk_level``. This runner replays a golden set of (intent, risk) cases through
``AgentOrchestratorService.decide`` and asserts the recommendation fields match
the expected values exactly. Because the rules are deterministic, the pass-rate
threshold is 1.0 — any mismatch is a real behavior regression, not noise.

No database, no HTTP, no RAG/LLM, and no writes: this evaluates the decision
rules only. Run from the repository root:

    PYTHONPATH=backend:. python evals/agent/evaluate.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.message import Message  # noqa: E402
from app.services.agent_orchestrator_service import (  # noqa: E402
    AGENT_TRIGGER_INTENTS,
    AgentOrchestratorService,
)
from app.services.intent_classifier_service import INTENT_LABELS  # noqa: E402


GOLDEN_SET = Path(__file__).with_name("golden_set.json")
ARTIFACT_DIR = ROOT / "eval-artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "agent_eval.json"
PASS_RATE_THRESHOLD = 1.0

# Decision fields compared against the golden set's ``expected`` block.
COMPARE_FIELDS = (
    "ran",
    "skipped_reason",
    "recommended_task",
    "recommended_escalation",
    "human_review_required",
    "confidence",
)

# Coverage we require the golden set to exercise.
REQUIRED_NON_TRIGGER_INTENTS = {"booking_inquiry", "pricing_request", "service_question", "other"}


def load_cases() -> list[dict[str, Any]]:
    try:
        cases = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"golden set not found: {GOLDEN_SET}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"golden set is invalid JSON: {exc}") from exc

    if not isinstance(cases, list) or not cases:
        raise SystemExit("golden set must be a non-empty JSON array")

    required_fields = {"id", "text", "intent_label", "expected"}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise SystemExit(f"case {index} must be an object")
        missing = required_fields - set(case)
        if missing:
            raise SystemExit(f"case {case.get('id', index)} missing fields: {sorted(missing)}")
        if case["intent_label"] not in INTENT_LABELS:
            raise SystemExit(
                f"case {case['id']} has unknown intent_label={case['intent_label']}"
            )
        expected = case["expected"]
        if not isinstance(expected, dict):
            raise SystemExit(f"case {case['id']} expected must be an object")
        missing_expected = set(COMPARE_FIELDS) - set(expected)
        if missing_expected:
            raise SystemExit(
                f"case {case['id']} expected missing fields: {sorted(missing_expected)}"
            )
    return cases


def validate_coverage(cases: list[dict[str, Any]]) -> None:
    present = {case["intent_label"] for case in cases}
    missing_triggers = sorted(AGENT_TRIGGER_INTENTS - present)
    if missing_triggers:
        raise SystemExit(f"golden set is missing trigger intents: {missing_triggers}")
    missing_non_triggers = sorted(REQUIRED_NON_TRIGGER_INTENTS - present)
    if missing_non_triggers:
        raise SystemExit(f"golden set is missing non-trigger intents: {missing_non_triggers}")


def actual_decision(case: dict[str, Any]) -> dict[str, Any]:
    message = Message(
        intent_label=case["intent_label"],
        risk_level=case.get("risk_level"),
        risk_reason=case.get("risk_reason"),
    )
    decision = AgentOrchestratorService().decide(message)
    return {
        "ran": decision.ran,
        "skipped_reason": decision.skipped_reason,
        "recommended_task": decision.recommended_task.should_create,
        "recommended_escalation": decision.recommended_escalation.should_escalate,
        "human_review_required": decision.human_review_required,
        "confidence": decision.confidence,
    }


def evaluate() -> tuple[dict[str, Any], int]:
    cases = load_cases()
    validate_coverage(cases)

    per_intent_support: Counter[str] = Counter()
    per_intent_passed: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    failed_cases: list[dict[str, Any]] = []

    for case in cases:
        intent = str(case["intent_label"])
        expected = {field: case["expected"][field] for field in COMPARE_FIELDS}
        actual = actual_decision(case)

        mismatches = {
            field: {"expected": expected[field], "actual": actual[field]}
            for field in COMPARE_FIELDS
            if expected[field] != actual[field]
        }
        case_passed = not mismatches

        per_intent_support[intent] += 1
        if case_passed:
            per_intent_passed[intent] += 1

        record = {
            "id": case["id"],
            "intent_label": intent,
            "risk_level": case.get("risk_level"),
            "passed": case_passed,
            "mismatches": mismatches,
        }
        results.append(record)
        if not case_passed:
            failed_cases.append({**record, "scenario": case.get("scenario")})

    total = len(cases)
    passed = sum(per_intent_passed.values())
    failed = total - passed
    pass_rate = passed / total if total else 0.0
    overall_passed = pass_rate >= PASS_RATE_THRESHOLD

    per_intent = {
        intent: {
            "support": per_intent_support[intent],
            "passed": per_intent_passed[intent],
            "pass_rate": (
                per_intent_passed[intent] / per_intent_support[intent]
                if per_intent_support[intent]
                else 0.0
            ),
        }
        for intent in sorted(per_intent_support)
    }

    artifact = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "threshold": PASS_RATE_THRESHOLD,
        "overall_passed": overall_passed,
        "trigger_intents": sorted(AGENT_TRIGGER_INTENTS),
        "compared_fields": list(COMPARE_FIELDS),
        "per_intent": per_intent,
        "results": results,
        "failed_cases": failed_cases,
    }
    return artifact, 0 if overall_passed else 1


def main() -> int:
    artifact, exit_code = evaluate()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "overall_passed": artifact["overall_passed"],
        "pass_rate": artifact["pass_rate"],
        "threshold": artifact["threshold"],
        "total": artifact["total"],
        "passed": artifact["passed"],
        "failed": artifact["failed"],
        "artifact": str(ARTIFACT_PATH),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
