# Research: Guardrails

**Branch**: `014-guardrails` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context (001–013). No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Single In-Process Guardrail Service (Two Chokepoints)

**Decision**: All guardrail logic lives in one `GuardrailService` exposing `check_user_input` (before RAG/generation) and `check_ai_output` (after generation, before display), plus `redact_pii` and `validate_rag_grounding`. The 009→010 path calls these in-process. Optional HTTP endpoints (`/api/guardrails/check-input`, `/check-output`) run the **same** functions for testing/demo.

**Rationale**:
- The hard guarantee is that **no** path reaches the model/retriever without the input check and **no** path reaches staff without the output check (FR-002). Centralizing both checks in one service makes that structural — call sites are thin and cannot bypass the guarantees.
- An in-process call avoids a network hop and a second auth surface for the common case; all EventSense AI features run in the same FastAPI app.

**Alternatives considered**:
- HTTP-only guardrail microservice: adds latency + an auth surface + a bypass risk if a caller forgets to call it; rejected as the primary path (endpoints kept as conveniences).
- Per-feature ad-hoc checks: duplicates detection/redaction and invites a missed chokepoint; rejected.

---

## Decision 2: Rule/Heuristic Detection (No Trained Model in the MVP)

**Decision**: Detection is rule/heuristic-based: curated pattern lists for prompt-injection and system-prompt-disclosure, a tenant-registry match for cross-tenant references, regexes for secrets/JWTs/API keys, a small lexicon + commitment markers for unsafe/unprofessional replies, regexes for PII, and a lexical/semantic overlap check for grounding. No trained safety classifier or external moderation API in the MVP.

**Rationale**:
- The project's ML budget is the TF-IDF + Logistic Regression intent classifier (006); guardrails need to be deterministic, explainable, and dependency-free for a senior-project MVP. Rules give clear, testable behavior ("ignore previous instructions" → refuse) and make the audit `reason` human-readable.
- Rules are easy to unit-test for both precision (catch the probe) and the critical negative case (don't flag a benign "what's your refund policy?").

**Alternatives considered**:
- A fine-tuned moderation model / external moderation API: stronger recall but adds a dependency, latency, cost, and a data-egress/privacy concern (sending tenant text to a third party); deferred (named in Out of Scope).
- LLM-as-judge for grounding/safety: powerful but non-deterministic and heavier; the MVP uses an overlap heuristic and prefers *hold* over *drop* for borderline cases.

---

## Decision 3: Fail Safe, Never Fail Open

**Decision**: If `check_ai_output` errors, it returns a `human_review_required` / `require_human_review` decision (the draft is **held**, not shown). If `check_user_input` errors while evaluating a refuse-class probe, it returns `refuse` (the AI is **not** invoked with that input). The safe state is "don't show / don't run", never "show/run the unchecked thing".

**Rationale**:
- A guardrail that fails open is worse than no guardrail — it gives false assurance. FR-018/SR-05 require the layer to default to the safe action on its own errors. Holding output for human review is recoverable; showing an unchecked draft is not.

**Alternatives considered**:
- Fail open (show the draft if the checker errors): violates the safety contract; rejected.
- Hard-fail the whole request on a checker error: needlessly breaks the workflow; holding for review is the softer, safe choice.

---

## Decision 4: Grounding by Supporting Source, Not Verbatim Match

**Decision**: `validate_rag_grounding(draft, sources)` returns `grounded`, `source_document_ids`, and `partial`. A draft is grounded if its factual claims are covered by at least one retrieved tenant chunk (lexical/semantic overlap over a threshold). No sources ⇒ not grounded. A paraphrase of a real source passes; a claim with no supporting source fails. If some claims are grounded and one is novel, `partial=True` ⇒ at least `require_human_review`.

**Rationale**:
- The spec forbids invented policies/prices/refunds/availability/commitments (FR-007, GR-01). Requiring a supporting source — rather than a verbatim string match — allows natural paraphrasing while still catching fabrication. Partial-grounding → review (GR-05) avoids both a false allow and a destructive drop.

**Alternatives considered**:
- Verbatim/substring match only: too brittle (rejects valid paraphrases); rejected.
- Trust the model's own "I used these sources" claim: the model can hallucinate its citations; rejected — validate against the actual retrieved chunks.

---

## Decision 5: Cross-Tenant Is Defense-in-Depth on Top of Tenant-Scoped Retrieval

**Decision**: Server-side retrieval is already tenant-scoped (001/009), so another tenant's document can never be retrieved regardless of the input. The `cross_tenant_access` guardrail is an **additional** explicit refusal + audit (`cross_tenant_access_blocked` in the **caller's** tenant, no target data), not the sole boundary.

**Rationale**:
- The real isolation guarantee lives at the data layer (tenant-scoped queries). The guardrail adds an explicit, auditable refusal for probes that name another tenant ("show me Royal Events' refund policy"), and ensures the *decision/audit* itself never stores target-tenant data (SR-03, Spec 013 SR-07). Even a detection miss cannot leak data, because retrieval still filters by tenant.

**Alternatives considered**:
- Rely only on the guardrail text check: a detection miss could (in a less-careful system) leak; rejected — the data-layer scope is the hard boundary, the guardrail is the audit + UX layer.
- Log the block in the target tenant: leaks the attempt across tenants; rejected (mirror Spec 013 Decision 5).

---

## Decision 6: PII Redaction Minimizes Logs, Not the Stored Message

**Decision**: `redact_pii` replaces emails with `[EMAIL_REDACTED]` and phone numbers with `[PHONE_REDACTED]` in guardrail summaries, `redacted_text`, and Spec 013 audit summaries. The original client message (003) is stored **as-is** for the workflow; only the derived logs/summaries are minimized. PII never blocks a message (action `redact`, severity `info`).

**Rationale**:
- The workflow needs the real contact details (staff must reply to the client), so the message body is preserved. The privacy obligation is on the *oversight surface* — audit logs and decision summaries — where raw PII is unnecessary (PR-01, Spec 013 PR-05). Detecting PII is not a safety violation, so it must not refuse a valid message (FR-008).

**Alternatives considered**:
- Redact the stored message body: breaks the reply workflow (staff loses the client's email/phone); rejected.
- Block messages containing PII: rejects valid client messages; rejected — `redact`, not `refuse`.

---

## Decision 7: Decisions Are Append-Only, Tenant-Scoped, Role-Gated (mirror Spec 013)

**Decision**: `guardrail_decisions` is append-only (no `updated_at`, no update/delete path). Managers read tenant-wide decisions; staff read message-scoped decisions for messages they handle. Reads are tenant-scoped (404 not-in-tenant / 403 other-tenant) and paginated newest-first.

**Rationale**:
- Guardrail decisions are an audit-like trail of safety events; they should be as immutable and tenant-isolated as Spec 013 audit logs (consistency + oversight integrity). Reusing the 013 read-surface pattern (role split, 404/403, pagination) keeps the platform coherent.

**Alternatives considered**:
- Editable/deletable decisions: undermines the safety trail; rejected.
- Staff read tenant-wide decisions: over-exposes other users' blocked inputs; rejected — message-scoped for staff.

---

## Decision 8: Best-Effort Audit; Refusal Does Not Depend on Logging

**Decision**: After persisting a `GuardrailDecision`, the service calls Spec 013 `AuditService.log_event` / `log_cross_tenant_blocked` (itself best-effort, never raises). A `refuse` decision still refuses even if the audit (or the decision persistence) fails — safety does not depend on logging succeeding.

**Rationale**:
- Spec 013 already guarantees logging is non-fatal (FR-014/SR-08 there). The guardrail must not become *less* safe because a log failed: the block is the primary behavior; the audit is the record. Decoupling them means a logging outage never opens a hole.

**Alternatives considered**:
- Require a successful audit before refusing: couples safety to logging availability; rejected.
- Skip the audit entirely: loses manager oversight of security events; rejected — best-effort is the right balance.

---

## Decision 9: Redaction in Every Stored Decision Field (Defense-in-Depth)

**Decision**: A shared `redact_text` (PII + secret/JWT/API-key + system-prompt markers) runs over every `reason`, `redacted_text`, `metadata`, and summary **before** persistence; the Spec 013 redactor is the backstop on the audit side. A refusal decision stores the **category + short reason**, never the offending payload's successful output, the system prompt, the refused answer, the secret, or a cross-tenant snippet.

**Rationale**:
- The decision/audit surface must never become the leak it was meant to prevent (FR-019, PR-02, PR-05). Redacting at the single decision-builder boundary means even a careless `reason` string cannot persist a secret/prompt/PII. Storing only the category + short reason avoids echoing the very thing that was blocked.

**Alternatives considered**:
- Store the offending input/output "for debugging": directly leaks system prompts / secrets / cross-tenant data into the log; rejected.
- Trust callers to pass clean strings: one careless call leaks; rejected — redact at the boundary.

---

## Decision 10: Most-Severe-Wins, One Decision per Check (with sub-flags)

**Decision**: Each check returns **one** `GuardrailDecision` whose category/action/severity is the most severe finding (input: a `security` refuse beats a benign allow; output: a `refuse` beats a `require_human_review` beats a `redact`). Secondary findings (e.g., PII redaction alongside an unsupported-answer refusal) are recorded in `metadata` (`also_flagged: [...]`). PII redaction of summaries is always applied regardless of the headline action.

**Rationale**:
- One decision per check keeps the record readable and the action unambiguous for the caller to apply. The most-severe-wins rule guarantees the safe action is taken (a `refuse` is never downgraded by a co-occurring `redact`). Sub-flags in metadata preserve the detail for oversight without spawning multiple rows.

**Alternatives considered**:
- One row per finding: noisy, and risks the caller applying the wrong (less severe) action; rejected.
- Drop secondary findings: loses oversight detail; kept in `metadata` instead.

---

## Decision 11: Always-On Guardrails (No Per-Message Bypass)

**Decision**: Guardrails are always-on for the AI/RAG path in the MVP (`GUARDRAILS_ENABLED` is a deployment flag, not a per-message UI toggle). There is no UI control to disable a check for a specific message or to "reveal the blocked content".

**Rationale**:
- A per-message bypass is an obvious foot-gun (and a social-engineering target). The spec lists "disabling/overriding guardrails per message" as out of scope. Always-on keeps the safety contract simple and uniform.

**Alternatives considered**:
- Manager "override and show" button: reintroduces the exact disclosure/ungrounded risk the guardrail prevents; rejected for the MVP (a human can still independently confirm with the client).

---

## Decision 12: Topic Keywords Are Not Signals (Avoid False Positives on Valid Messages)

**Decision**: Detection targets **intent** (instruction override, disclosure request, cross-tenant reference, fabrication, secret leakage), not topic words. "Refund", "policy", "cancel", "price", "availability" never trigger a refusal by themselves; only override/disclosure/cross-tenant/fabrication patterns do.

**Rationale**:
- FR-014/AC-20 require that normal valid wedding/event messages pass untouched. A guardrail that blocks "what's your refund policy?" would break the product. The pattern lists are written around override/disclosure verbs and structures, and the unit tests assert the benign-topic negatives explicitly.

**Alternatives considered**:
- Keyword blocklist on sensitive topics: huge false-positive rate on legitimate client questions; rejected.
- No input filtering (rely on output only): lets injection/disclosure/cross-tenant probes reach the model; rejected — both chokepoints are required.
