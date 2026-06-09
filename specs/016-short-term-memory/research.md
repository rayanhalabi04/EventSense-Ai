# Research: Short-Term Conversation Memory

**Branch**: `016-short-term-memory` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context (001–015). No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Redis as the Temporary Store (Not Postgres)

**Decision**: Short-term memory lives in **Redis** as an ephemeral per-conversation document with a TTL; **no raw memory is persisted to Postgres**. The data model documents the cache schema and in-process shapes, not new SQL tables.

**Rationale**:
- The spec requires memory to be **temporary** (default 7-day TTL), bounded, and "not stored forever" (FR-002, SP-03, AC-20). Redis TTLs make expiry automatic and free; a Postgres table would invite permanent retention and a reaper job.
- Redis is already the project's chosen "memory store for short-term memory" in the stack. Reads/writes are sub-millisecond, so memory never adds meaningful latency to the reply path.

**Alternatives considered**:
- A Postgres `conversation_memory` table with an `expires_at` + cron purge: durable transcript risk, more code, slower; rejected — the point is ephemerality.
- In-process memory (per-worker dict): lost on restart, not shared across workers, no TTL semantics; rejected.

---

## Decision 2: Tenant-Embedded Key Scheme (`mem:{tenant_id}:{conversation_id}`)

**Decision**: Every Redis key embeds the `tenant_id` first: `mem:{tenant_id}:{conversation_id}` (and `…:entries`). The service resolves the conversation **within the caller's tenant** (404 otherwise) **before** any key is constructed.

**Rationale**:
- Tenant isolation is the platform's hardest rule (001). Embedding `tenant_id` in the key means a `conversation_id` alone can **never** address another tenant's memory, even on a bug (FR-020, SP-01, AC-18). Resolving the conversation's tenant first is defense-in-depth: a cross-tenant id 404s and never touches Redis.

**Alternatives considered**:
- Key by `conversation_id` only: a leaked/guessed id could read another tenant's memory if scoping ever slipped; rejected — tenant must be in the key.
- One big hash keyed by tenant with conversation sub-fields: harder to TTL per conversation; rejected — per-conversation keys TTL cleanly.

---

## Decision 3: Redact-Then-Summarize Before Storage; Redact Again on Read

**Decision**: `redact_and_summarize` runs each message body through the 014 `redact_text` (PII + secrets + prompt markers) **first**, then builds a length-capped rolling summary + bounded refs. The digest is redacted **again** at read time before it reaches a prompt or response.

**Rationale**:
- Memory must minimize sensitive data and never store raw PII (FR-004, SP-02). Redacting before storage means the cache itself never holds raw emails/phones/secrets; redacting again on read is belt-and-suspenders against any residue and matches the 013/014 redaction discipline (SP-04).
- Reusing the existing redactor keeps behavior consistent with audit logs (013) and guardrails (014) instead of inventing a second PII policy.

**Alternatives considered**:
- Store raw, redact only on display: the cache becomes a PII store and a leak target; rejected.
- Redact once (storage only): a stored value that later flows to a model should still be re-checked; rejected — redact on read too.

---

## Decision 4: Bounded Digest — Rolling Summary + Capped Recent Refs

**Decision**: Memory stores a **length-capped rolling summary** plus at most `MEMORY_MAX_RECENT_MESSAGES` recent message references (a capped Redis list via `LPUSH` + `LTRIM`), not unlimited full history.

**Rationale**:
- Unbounded history is a privacy liability and a token-cost problem, and most reference resolution only needs the last few turns (FR-003, AC-02). A rolling summary preserves older salient anchors compactly while the recent refs give precise, current detail.

**Alternatives considered**:
- Keep the full transcript in Redis: large, costly, and an over-retention risk; rejected.
- Summary only (no refs): loses precise recent detail needed to resolve "that"/"it"; rejected — keep a small ref window too.

---

## Decision 5: Memory Is Supporting Context; RAG Remains the Source of Truth

**Decision**: Memory is injected into the 010 reply prompt as a clearly labeled **advisory** block, separate from the **authoritative** RAG `sources` block. The system instruction states policy/price/contract answers must come from sources; on conflict, **sources win**. 014 grounding enforces it on the output.

**Rationale**:
- The spec is explicit: RAG documents are the source of truth for package/pricing/refund/cancellation/contract; memory must never override them (FR-008, FR-009, AC-09). Separating the prompt blocks + keeping grounding (014) on the output means an invented price fails grounding regardless of what memory implied (FR-010, AC-08).

**Alternatives considered**:
- Blend memory and sources into one context blob: invites the model to treat a client's claim as policy; rejected — keep them labeled and ranked.
- Let memory answer policy questions when RAG is empty: that is exactly the fabrication risk the platform forbids; rejected — refuse/ask instead.

---

## Decision 6: Tag Unverifiable Claims; Never Fabricate Confirmations

**Decision**: Claims a client asserts but the system cannot verify (e.g., "I paid the deposit yesterday") are summarized as **unverified** facts (`{"fact":"deposit_paid","verified":false}`). A later "Can you confirm it?" resolves "it" = the deposit but the reply suggests **checking/confirming**, never states the payment is confirmed unless verified by available data.

**Rationale**:
- Memory remembering a claim is not the same as the claim being true. Falsely confirming a payment is a serious trust/financial error (AC-10). Tagging verification status lets the reply resolve the reference while staying honest.

**Alternatives considered**:
- Store claims as plain facts: the model may later assert them as confirmed; rejected — track verification status.
- Drop unverifiable claims entirely: then "Can you confirm it?" loses its antecedent; rejected — keep the reference, mark it unverified.

---

## Decision 7: Memory Is Optional and Degradable (Never on the Critical Path)

**Decision**: All cache operations are wrapped; on a Redis error or `MEMORY_ENABLED=false`, `get_context` returns an empty digest and `update_from_message` is a no-op. The RAG + suggested-reply pipeline proceeds memory-less with no hard error.

**Rationale**:
- Memory is an enrichment, not a dependency (FR-016, AC-15). A cache outage must not break reply generation or message ingestion. Making it best-effort keeps the platform's core flow resilient and lets the feature ship behind a flag.

**Alternatives considered**:
- Treat a cache miss/error as a 5xx: couples core flow to an optional cache; rejected.
- Synchronous, blocking memory build during ingestion: adds latency and a failure point to the hot path; rejected — best-effort, off the critical path.

---

## Decision 8: Guardrails Before and After Memory Use

**Decision**: 014 `check_user_input` runs **before** a message informs memory; 014 `check_ai_output` (grounding + PII) runs on the memory-assisted draft **after**. Memory never bypasses either check.

**Rationale**:
- Memory could otherwise become a side channel for injection or ungrounded output. Keeping the existing guardrails on both ends (FR-012, AC-12) means memory inherits the platform's safety contract rather than weakening it.

**Alternatives considered**:
- Trust memory content (already redacted) and skip output grounding: an invented price could still slip through via the memory-enriched prompt; rejected — always ground the output.

---

## Decision 9: Best-Effort, Redacted Audit of Memory Actions

**Decision**: `memory_viewed`, `memory_refreshed`, `memory_cleared`, and `memory_used_in_reply` are logged via the 013 audit service (best-effort, redacted, ids/facts only). These are new string-backed `AuditEventType` values — no enum-altering migration.

**Rationale**:
- Memory use should be reviewable later (FR-013, AC-17), consistent with the platform's audit-everything posture, but an audit failure must never break the primary action (013's best-effort design). String-backed event types let 016 extend the enum without a migration, matching 013's "closed-but-extensible" approach.

**Alternatives considered**:
- No audit for memory: loses oversight of an AI context source; rejected.
- Hard-fail the action if audit fails: 013 already establishes best-effort, non-blocking audit; rejected — follow that.

---

## Decision 10: Deterministic Summarizer for the MVP (LLM Optional Behind the Interface)

**Decision**: The MVP summarizer is **deterministic/extractive** (recent salient lines + key entities/anchors), length-capped. An LLM summarizer can replace it behind the same `redact_and_summarize` interface later; either way the output passes `redact_text` and the length cap.

**Rationale**:
- A deterministic summarizer is cheap, fast, predictable, and easy to test (AC-02, AC-07) — ideal for a defensible MVP and a live demo. The interface boundary keeps the door open for an LLM summary without changing callers or the safety contract.

**Alternatives considered**:
- LLM summary from day one: adds cost, latency, and non-determinism to a hot-ish path and complicates redaction guarantees; deferred behind the interface.
- No summary (refs only): loses compact older context; rejected — keep a small rolling summary.

---

## Decision 11: Thin Endpoints + Internal Service (One Memory Code Path)

**Decision**: The authoritative logic is `MemoryService`; the three endpoints (`GET`/`POST refresh`/`DELETE`) and the internal callers (010 reply generation, ingestion) all go through the **same** service. No duplicate memory logic in handlers.

**Rationale**:
- A single service means isolation, redaction, TTL, and audit are enforced **once** regardless of entry point (matches the 013/014/015 "guarantees live in the service" pattern). Endpoints are thin trigger/IO; the integration hook is one call.

**Alternatives considered**:
- Memory logic inside the reply service only (no endpoints): loses inspect/refresh/clear operability and privacy controls; rejected.
- Logic duplicated in handlers and the reply service: drift risk on the safety rules; rejected — one service.

---

## Decision 12: No New Required Ingestion Step; Enrich the Existing RAG/Reply Step

**Decision**: Memory adds **no** new required step to message ingestion. `update_from_message` is invoked best-effort after a message is stored/opened, and `get_context` enriches the **existing** 009/010 step. With the feature off, behavior equals pre-016.

**Rationale**:
- The spec requires memory to be used "only after the basic message flow, RAG, and suggested replies exist" and to remain optional (FR-019, FR-016). Hooking into the existing step (rather than adding a mandatory pipeline stage) keeps ingestion simple and the feature fully removable behind a flag.

**Alternatives considered**:
- A mandatory "build memory" stage in ingestion: adds a failure point and latency to the hot path and makes the feature non-optional; rejected — best-effort enrichment of the existing step.
