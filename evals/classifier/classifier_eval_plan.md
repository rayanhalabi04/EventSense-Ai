# Classifier Evaluation Plan

## Purpose

This eval checks the EventSense AI intent classifier against a small deterministic
golden set of WhatsApp-style wedding and event planning messages. It is meant to
catch obvious regressions in the served classifier path used by the simulator,
not to replace a full offline training evaluation.

## Labels

The golden set must cover every MVP intent label:

- `booking_inquiry`
- `pricing_request`
- `availability_question`
- `service_question`
- `urgent_change`
- `guest_count_change`
- `complaint`
- `cancellation_request`
- `payment_issue`
- `human_escalation`
- `other`

## Golden Set Format

Cases live in `evals/classifier/golden_set.json`.

Each case has:

- `id`: stable case identifier
- `text`: client message to classify
- `expected_label`: one of the required labels
- `scenario`: short human-readable context for failures

## Command

Run from the repository root:

```bash
PYTHONPATH=backend:. uv run --with-requirements backend/requirements.txt python evals/classifier/evaluate.py
```

The runner writes:

```text
eval-artifacts/classifier_eval.json
```

## Metrics

The artifact includes:

- timestamp
- classifier model status, version, artifact path, and artifact hash
- total examples
- accuracy and threshold
- pass/fail
- fallback usage count
- per-label support, correct count, and accuracy
- confusion pairs
- failed examples
- predictions outside the allowed label list

## Failure Conditions

The eval exits non-zero when:

- the golden set is missing any required label
- a case uses an unknown expected label
- the classifier predicts a label outside the allowed label list
- accuracy is below the configured threshold
- the script crashes or the golden set is invalid

## Limitations

This is a compact smoke-style classifier eval with three examples per label. It
does not measure production distribution quality, calibration, edge cases,
multi-label ambiguity, or training/validation performance. The classifier service
may use a trained artifact when available or fall back to deterministic keyword
rules; fallback use is reported in the artifact through `fallback_used` and
`fallback_count`.
