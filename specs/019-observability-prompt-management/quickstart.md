# Quickstart: Observability and Prompt Management

**Branch**: `019-observability-prompt-management`

Trace a request through the AI pipeline, read the metrics, and change a prompt as a versioned diff.

Steps:
1. Trace a request by correlation id.
2. Scrape `/metrics`.
3. Inspect the prompt registry.
4. Change a prompt (versioned).
5. Confirm output → prompt traceability.

---

## Prerequisites

- Specs 006/009/010/012/013/014 implemented (the AI pipeline + audit + guardrails/redactor).
- Backend running (locally or via Spec 017 stack).
- A demo user + tenant to drive a request.

---

## 1. Trace a request by correlation id

Send a request (optionally supplying a correlation id):

```bash
curl -s -X POST http://localhost:8000/api/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: demo-trace-001" \
  -d '{"conversation_id":"...","body":"Is the deposit refundable if I cancel?","direction":"inbound"}'
```

Then grep the structured logs for that id:

```bash
docker compose logs api | grep demo-trace-001 | jq
```

You should see one JSON line per AI step (classifier → risk → RAG → reply → guardrail), each with `request_id=demo-trace-001`, the `component`, `latency_ms`, and `outcome` — and **no** message body, secret, system prompt, or cross-tenant data (redacted). The resulting audit/guardrail/agent records carry the same `request_id`.

If no `X-Request-Id` is supplied, the backend generates one and returns it in the `X-Request-Id` response header.

## 2. Scrape `/metrics`

```bash
curl -s http://localhost:8000/metrics    # operator/owner-restricted
```

Expect Prometheus text with aggregate series, e.g.:

```
ai_calls_total{component="classifier"} 12
ai_calls_total{component="rag"} 9
ai_latency_ms_bucket{component="reply",le="500"} 7
guardrail_refusals_total{category="unsupported_answer"} 2
cross_tenant_blocks_total 1
agent_runs_total 3
agent_tool_calls_total{tool="rag_search"} 5
```

Labels are bounded (`component`/`category`/`tool`) — never `tenant_id` or message ids. `/metrics` is restricted to operator/owner and exposes no tenant content.

## 3. Inspect the prompt registry

Prompts live as versioned, hashed templates under `backend/app/prompts/`:

```
backend/app/prompts/
├── suggested_reply.system.yaml      # prompt_id: suggested_reply.system, version: 1.0.0, hash: ...
├── agent.system.yaml
├── agent.tool_router.yaml
└── escalation.summary.yaml
```

Each entry has `prompt_id`, `version`, `hash`, `template` (named variables), and `metadata`. Services load the active template by `prompt_id` — no hardcoded prompt strings. A missing id or a hash that doesn't match the template **fails fast** at startup.

## 4. Change a prompt (versioned)

1. Edit `template` in `suggested_reply.system.yaml`.
2. Bump `version` (e.g., `1.0.0` → `1.1.0`) and update `hash` (a helper recomputes it, or the loader rejects a stale hash).
3. Commit — the change is a single reviewable diff.
4. The reply service uses the new version on the next run.

## 5. Confirm output → prompt traceability

Generate a suggested reply, then inspect its record / audit line:

```bash
curl -s http://localhost:8000/api/messages/<id>/suggested-reply -H "Authorization: Bearer $TOKEN" | jq '.prompt_ref'
# => "suggested_reply.system@1.1.0#<hash-prefix>"
```

The output records the `prompt_id@version` (+ hash) that produced it, alongside the classifier's `model_version` (Spec 006) — so the output is reproducible and reviewable. The ref carries only id/version/hash, never content.

---

## Notes

- Verbose AI-step logging is gated by `AI_TRACE_ENABLED` / `LOG_LEVEL`; errors are always logged.
- All log/metric fields pass through the Spec 014 redactor — no secrets/PII/system prompts/cross-tenant data are ever emitted.
- This feature adds no new business actions and changes no tenant boundary — it instruments and parameterizes the existing pipeline.
