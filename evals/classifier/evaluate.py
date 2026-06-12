from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.intent_classifier_service import (  # noqa: E402
    INTENT_LABELS,
    IntentClassifierService,
    get_classifier_status,
)


GOLDEN_SET = Path(__file__).with_name("golden_set.json")
ARTIFACT_DIR = ROOT / "eval-artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "classifier_eval.json"
ACCURACY_THRESHOLD = 0.80


def load_cases() -> list[dict[str, Any]]:
    try:
        cases = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"golden set not found: {GOLDEN_SET}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"golden set is invalid JSON: {exc}") from exc

    if not isinstance(cases, list) or not cases:
        raise SystemExit("golden set must be a non-empty JSON array")

    required_fields = {"id", "text", "expected_label"}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise SystemExit(f"case {index} must be an object")
        missing = required_fields - set(case)
        if missing:
            raise SystemExit(f"case {case.get('id', index)} missing fields: {sorted(missing)}")
        if case["expected_label"] not in INTENT_LABELS:
            raise SystemExit(
                f"case {case['id']} has unknown expected_label={case['expected_label']}"
            )
    return cases


def validate_label_coverage(cases: list[dict[str, Any]]) -> None:
    present = {case["expected_label"] for case in cases}
    missing = sorted(INTENT_LABELS - present)
    if missing:
        raise SystemExit(f"golden set is missing required labels: {missing}")


def evaluate() -> tuple[dict[str, Any], int]:
    cases = load_cases()
    validate_label_coverage(cases)

    status = get_classifier_status()
    per_label_support: Counter[str] = Counter()
    per_label_correct: Counter[str] = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    failed_examples: list[dict[str, Any]] = []
    fallback_count = 0
    predictions_outside_allowed: list[dict[str, str]] = []

    for case in cases:
        expected = str(case["expected_label"])
        classification = IntentClassifierService.classify(str(case["text"]))
        predicted = classification.label
        if predicted not in INTENT_LABELS:
            predictions_outside_allowed.append(
                {
                    "id": str(case["id"]),
                    "predicted_label": predicted,
                    "expected_label": expected,
                }
            )
        if classification.used_fallback:
            fallback_count += 1

        per_label_support[expected] += 1
        if predicted == expected:
            per_label_correct[expected] += 1
        else:
            confusion[(expected, predicted)] += 1
            failed_examples.append(
                {
                    "id": case["id"],
                    "text": case["text"],
                    "expected_label": expected,
                    "predicted_label": predicted,
                    "confidence": classification.confidence,
                    "used_fallback": classification.used_fallback,
                    "scenario": case.get("scenario"),
                }
            )

    total = len(cases)
    correct = sum(per_label_correct.values())
    accuracy = correct / total if total else 0.0
    per_label = {
        label: {
            "support": per_label_support[label],
            "correct": per_label_correct[label],
            "accuracy": (
                per_label_correct[label] / per_label_support[label]
                if per_label_support[label]
                else 0.0
            ),
        }
        for label in sorted(INTENT_LABELS)
    }
    confusion_pairs = [
        {"expected_label": expected, "predicted_label": predicted, "count": count}
        for (expected, predicted), count in sorted(confusion.items())
    ]
    passed = (
        not predictions_outside_allowed
        and accuracy >= ACCURACY_THRESHOLD
        and not (INTENT_LABELS - set(per_label_support))
    )

    artifact = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": {
            "loaded": status.loaded,
            "model_version": status.model_version,
            "artifact_path": status.artifact_path,
            "artifact_hash": status.artifact_hash,
        },
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "threshold": ACCURACY_THRESHOLD,
        "passed": passed,
        "fallback_used": fallback_count > 0,
        "fallback_count": fallback_count,
        "per_label": per_label,
        "confusion_pairs": confusion_pairs,
        "failed_examples": failed_examples,
        "predictions_outside_allowed": predictions_outside_allowed,
    }
    return artifact, 0 if passed else 1


def main() -> int:
    artifact, exit_code = evaluate()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "passed": artifact["passed"],
        "accuracy": artifact["accuracy"],
        "threshold": artifact["threshold"],
        "total": artifact["total"],
        "fallback_count": artifact["fallback_count"],
        "artifact": str(ARTIFACT_PATH),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
