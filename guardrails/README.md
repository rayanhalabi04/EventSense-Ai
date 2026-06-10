# EventSense AI Guardrails

Feature 014 adds deterministic input, retrieval, and output rails around RAG and suggested replies.

The implementation lives in `backend/app/services/guardrail_service.py` and is intentionally rule-based by default so local tests and demos do not require paid LLM APIs. The policy shape mirrors NeMo Guardrails concepts without adding the heavy runtime dependency.

## Rails

- Input rails block prompt injection, system prompt disclosure, cross-tenant data requests, destructive data requests, and unsafe unsupported requests before retrieval or reply generation.
- Retrieval rails scan tenant-scoped RAG snippets, redact emails/phones/long numbers, and filter snippets that contain embedded instructions.
- Output rails redact PII from drafted replies and replace unsafe leakage with a staff-review refusal.
- Audit mode records guardrail decisions in `audit_logs` with `guardrail_*` event types.

## Evaluation

Run the deterministic red-team set:

```bash
PYTHONPATH=backend:. python3 evals/guardrails/evaluate.py
```
