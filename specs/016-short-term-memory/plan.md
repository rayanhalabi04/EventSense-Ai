# Implementation Plan: Short-Term Conversation Memory

**Branch**: `016-short-term-memory` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/016-short-term-memory/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation boundary; `tenant_id` in every key/entry
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): tenant/role from JWT; platform admin excluded from tenant memory
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): `conversations`/`messages` source material
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): the surface a memory-enriched reply is reviewed on
- [Spec 009 — RAG](../009-rag-over-tenant-documents/plan.md): **source of truth**; `rag_service.query(...)`
- [Spec 010 — Suggested Replies](../010-suggested-replies/plan.md): `suggested_reply_service.generate(...)` — the consumer of memory context
- [Spec 011 — Tasks](../011-follow-up-tasks/plan.md) / [Spec 012 — Escalation](../012-escalation-to-manager/plan.md): memory must NOT auto-create these
- [Spec 013 — Audit Logs](../013-audit-logs/plan.md): `audit_service.log_event(...)` + `redact(...)`
- [Spec 014 — Guardrails](../014-guardrails/plan.md): `check_user_input` / `check_ai_output` / `redact_text` / `validate_rag_grounding`

**Note**: This feature is an **enrichment layer**. It adds a Redis-backed `MemoryService`, three thin endpoints, and a single integration hook into the existing RAG/suggested-reply step. It introduces **no permanent storage**, **no new required ingestion step**, and **no autonomous behavior**.

---

## Summary

Add a tenant- and conversation-scoped **short-term memory** backed by **Redis** (default **7-day TTL**). On new messages, `MemoryService.update_from_message` redacts (014/013 redactor) and summarizes the bounded recent window into a `ConversationMemory` digest (`summary` + ≤ N `recent_message_refs`) stored under `mem:{tenant_id}:{conversation_id}`. When a suggested reply is generated (010), `MemoryService.get_context` returns the redacted digest as **supporting context**; **RAG (009) remains the source of truth** and wins any conflict; guardrails (014) run **before** memory build and **after** memory-assisted output; the AI never invents unsupported prices/policies and never fabricates confirmations. Three thin endpoints let tenant users inspect (`GET`), rebuild (`POST .../refresh`), and clear (`DELETE`) a conversation's memory; all reads are redacted, tenant-scoped, audited (013), and side-effect-free (no auto-send, no task/escalation). Memory is **optional/degradable**: cache down or feature off → empty context, the pipeline still works. Nothing is stored forever — only the expiring, redacted digest exists.

---

## Technical Approach

- **Memory lives in Redis, not Postgres.** The digest is ephemeral by design (FR-002, SP-03, AC-20). The canonical store is a Redis JSON document (or hash) per conversation; **no raw memory is persisted to Postgres**. Data-model.md documents the cache schema (and the in-process Pydantic shapes), not new SQL tables.
- **Key scheme embeds the tenant (SP-01, FR-020).** `mem:{tenant_id}:{conversation_id}` for the `ConversationMemory` document; `mem:{tenant_id}:{conversation_id}:entries` for the bounded `MemoryEntry` list (a capped Redis list). A `conversation_id` alone can never address another tenant's memory, and the service resolves the conversation within the caller's tenant (404 otherwise) **before** constructing any key.
- **Thin service, single integration point.** `MemoryService` exposes `get_context`, `update_from_message`, `redact_and_summarize`, `clear`, and `view`. The only pipeline change is that `suggested_reply_service.generate(...)` (010) calls `get_context` and passes the digest into the prompt builder alongside the RAG sources; ingestion calls `update_from_message` opportunistically (best-effort, never blocking).
- **Redact-then-summarize (SP-02).** `redact_and_summarize` first runs each message body through the 014 `redact_text` (PII + secrets + prompt markers), then builds a length-capped rolling summary and bounded recent refs. `pii_redacted` is set when any redaction occurred. Raw bodies are **never** copied into the digest.
- **Supporting-context, RAG-wins prompt contract (FR-008, FR-009).** The reply prompt clearly separates `[recent context]` (memory, advisory) from `[sources]` (RAG, authoritative). The system instruction states that policy/price/contract answers must come from sources; memory may only resolve references. 014 grounding (`validate_rag_grounding`) still runs on the output, so an invented price fails grounding regardless of memory.
- **Guardrails before and after (FR-012).** `check_user_input` runs before a message informs memory; `check_ai_output` runs on the memory-assisted draft. Memory never bypasses either.
- **Optional/degradable (FR-016).** Every Redis call is wrapped: on connection error or `MEMORY_ENABLED=false`, `get_context` returns an empty digest and `update_from_message` is a no-op; the reply pipeline proceeds memory-less. Memory is **never** on the critical path.
- **Auditable (FR-013).** `view`/`refresh`/`clear`/`use` emit best-effort redacted 013 audit events (`memory_*`) with ids/facts only.
- **No autonomy (SP-06).** The service has no code path to send a reply (010) or create a task (011)/escalation (012); a test asserts it imports none of those write paths.

---

## Backend Tasks

1. **`schemas/memory.py`** — Pydantic DTOs + enums: `MemoryStatus`, `MemorySource`; `ConversationMemoryView`, `MemoryEntryView`, `MemoryContext` (internal), `MemoryRefreshResponse`, `MemoryClearResponse`. All view fields are redacted-only.
2. **`services/memory_service.py`** — the core service:
   - `get_context(session, *, tenant_id, conversation_id) -> MemoryContext` — read digest (redact-on-read), or empty; never raises on cache error.
   - `update_from_message(session, *, tenant_id, conversation_id, message_id) -> None` — load recent window, `redact_and_summarize`, write digest with TTL; best-effort.
   - `redact_and_summarize(messages) -> (summary, entries, pii_redacted)` — 014 redactor + length-capped rolling summary + bounded refs.
   - `view(session, *, caller, conversation_id) -> ConversationMemoryView` — tenant-resolve conversation (404/403), return redacted digest + `status`/`expires_at`.
   - `refresh(session, *, caller, conversation_id) -> MemoryRefreshResponse` — rebuild from latest messages.
   - `clear(session, *, caller, conversation_id) -> MemoryClearResponse` — delete the key(s).
3. **`services/memory_store.py`** (Redis adapter) — `read_memory`, `write_memory`, `append_entry`, `delete_memory`, key builders (`_mem_key`, `_entries_key`); TTL applied on every write; all wrapped for graceful degradation.
4. **`api/v1/conversation_memory.py`** — `GET`/`POST refresh`/`DELETE` endpoints with `require_auth`, tenant-scope resolution, and 013 audit calls.
5. **Integration hook** — modify `services/suggested_reply_service.py` (010) to fetch `get_context` and pass it into the prompt builder; modify the message-ingestion/open path (003–005) to call `update_from_message` best-effort.
6. **Config** — `MEMORY_ENABLED`, `MEMORY_TTL_SECONDS=604800`, `MEMORY_MAX_RECENT_MESSAGES`, `MEMORY_SUMMARY_MAX_CHARS`, `REDIS_URL` in `core/config.py`.
7. **Router mount** — register the conversation-memory router at `/api` (behind `MEMORY_ENABLED`) in `main.py`.

---

## Redis / Cache Tasks

1. **Redis client/lifecycle** — an async Redis client (e.g., `redis.asyncio`) created at app startup, pooled, closed on shutdown; `REDIS_URL` from config.
2. **Key builders** — `_mem_key(tenant_id, conversation_id) = f"mem:{tenant_id}:{conversation_id}"`; `_entries_key(...) = mem_key + ":entries"`. **Tenant id is mandatory** in every key (FR-020, SP-01).
3. **TTL on every write** — `SET key value EX MEMORY_TTL_SECONDS` (default 604800); `expires_at` stored inside the document mirrors the Redis TTL (FR-002).
4. **Bounded entries** — `LPUSH` + `LTRIM 0 MEMORY_MAX_RECENT_MESSAGES-1` keeps the recent-ref list capped (FR-003, AC-02); the same TTL applied to the entries key.
5. **Graceful degradation** — a `try/except` wrapper around all Redis ops: connection error → treat as empty/no-op, log a warning, never raise to the request path (FR-016, AC-15).
6. **Clear/expire** — `DEL` both keys on clear; rely on Redis TTL for auto-expiry; a read of a missing key returns the empty digest (cold) (FR-017, AC-16).
7. **Isolation guard** — the service resolves the conversation's tenant (003) and asserts it equals the JWT tenant **before** any key is built; a mismatch is a 404 (cross-tenant) and never touches Redis (SP-01, AC-14).

---

## Memory Summarization Tasks

1. **`redact_and_summarize` (FR-007)** — input: the bounded recent window (most-recent `MEMORY_MAX_RECENT_MESSAGES` messages). Step 1: run each body through 014 `redact_text` (PII + secrets + prompt markers). Step 2: build a **rolling summary** (length-capped at `MEMORY_SUMMARY_MAX_CHARS`) capturing salient facts/anchors ("guest count 150→220", "deposit paid claim — unconfirmed"). Step 3: build `MemoryEntry`s (redacted `content_summary`, `entry_type`, `source_message_id`, `pii_redacted`).
2. **Reference anchors** — the summarizer preserves the antecedents follow-ups refer to ("that"/"it"/"the package"/"the guest count"/"the deposit") so `get_context` can resolve them (AC-07).
3. **Unverifiable-claim tagging** — a claim like "I paid the deposit" is summarized as an **unconfirmed** claim (e.g., `{"fact":"deposit_paid","verified":false}`), so downstream replies don't fabricate a confirmation (AC-10).
4. **Summarizer choice** — MVP uses a deterministic/extractive summarizer (recent salient lines + key entities) to stay cheap and predictable; an optional LLM summarizer can replace it behind the same interface (output must still pass `redact_text`). Either way the output is redacted and length-capped.
5. **No raw retention** — only redacted summaries/refs are stored; raw bodies are read from `messages` (003) transiently and never copied into the digest (SP-02, AC-20).

---

## API / Internal Service Tasks

1. **`GET /api/conversations/{conversation_id}/memory`** — return the redacted `ConversationMemoryView` (or cold/empty); tenant-scoped; audit `memory_viewed`.
2. **`POST /api/conversations/{conversation_id}/memory/refresh`** — rebuild from latest messages; return `MemoryRefreshResponse`; audit `memory_refreshed`.
3. **`DELETE /api/conversations/{conversation_id}/memory`** — clear the digest; return `MemoryClearResponse`; audit `memory_cleared`.
4. **Internal `memory.get_context(tenant_id, conversation_id)`** — used by 010; returns `MemoryContext` (redacted) or empty; never raises.
5. **Internal `memory.update_from_message(tenant_id, conversation_id, message_id)`** — used by ingestion/open path; best-effort; refreshes TTL.
6. **Internal `memory.redact_and_summarize(...)`** — shared helper used by `update_from_message` and `refresh`.
7. **Role/scope gating** — all endpoints require an authenticated tenant user (staff/manager); platform admin → 403 (no tenant content); conversation resolves within the caller's tenant (404 otherwise).

---

## RAG / Suggested Reply Integration Tasks

1. **Prompt contract** — extend the 010 reply prompt builder to accept a `memory_context` block, clearly labeled **supporting/advisory**, separate from the **authoritative** RAG `sources` block (FR-008).
2. **RAG remains source of truth** — `suggested_reply_service.generate(...)` still calls `rag_service.query(...)`; memory is added **alongside**, never instead of, RAG (FR-008, AC-06).
3. **Conflict resolution** — the system instruction encodes "if recent context conflicts with sources, follow the sources"; 014 `validate_rag_grounding` enforces it on the output (FR-009, AC-09).
4. **No invented facts** — grounding (014) runs after memory use; an invented price/policy fails grounding and is refused/flagged regardless of memory (FR-010, AC-08).
5. **Graceful empty context** — if `get_context` is empty (cold/disabled/cache-down), generation proceeds exactly as pre-016 (AC-15).
6. **Update trigger** — `update_from_message` is invoked after a message is stored/opened (best-effort), so the next reply has fresh context; it is never a blocking step (FR-019).

---

## Guardrail / Audit Integration Notes

- **Before memory build**: the incoming message passes 014 `check_user_input` before it informs memory; injection/PII handling happens upstream (FR-012).
- **Before storage**: `redact_and_summarize` runs `redact_text` so no raw PII/secret/prompt enters the digest (SP-02).
- **On read**: `get_context`/`view` redact again before the digest reaches a prompt or response (SP-04).
- **After memory-assisted output**: 014 `check_ai_output` (grounding + PII) runs on the draft; an ungrounded/invented claim is refused/flagged (FR-012, AC-08, AC-12).
- **Audit (013)**: `memory_viewed`, `memory_refreshed`, `memory_cleared`, and `memory_used_in_reply` events are logged best-effort with redacted metadata (ids/facts only); a failed audit never breaks the primary action (FR-013, AC-17).
- **New audit event values** added to `AuditEventType` (string-backed, extensible — no enum migration): `memory_viewed`, `memory_refreshed`, `memory_cleared`, `memory_used_in_reply`.

---

## Testing Tasks

**Backend unit** — `tests/unit/test_memory_redact_summarize.py`: PII redacted + `pii_redacted=true`, summary length cap, ref cap (AC-02, AC-03); `tests/unit/test_memory_keys.py`: key format embeds tenant; cross-tenant key isolation (AC-18); `tests/unit/test_memory_degraded.py`: cache error → empty context / no-op (AC-15); `tests/unit/test_memory_unverified_claim.py`: deposit claim tagged unverified (AC-10).

**Backend integration** — `tests/integration/test_conversation_memory.py`:
- `update_from_message` writes a tenant-scoped digest with ~7-day TTL + `expires_at` (AC-01, AC-05)
- `get_context` returns the redacted digest; reference resolution for guest-count + deposit examples (AC-04, AC-07)
- Suggested reply (010) uses memory as supporting context; RAG still queried + authoritative (AC-06); no invented price (AC-08); RAG-wins on conflict (AC-09)
- No auto-send / no task / no escalation from memory (AC-11); guardrails before + after (AC-12)
- GET/refresh/DELETE endpoints work, redacted, tenant-scoped (AC-13); cross-tenant → 404/403, key never built (AC-14); platform admin → 403 (AC-19)
- Cache down / feature disabled → pipeline still works (AC-15); clear + TTL-expiry read cold (AC-16)
- Memory actions audited (redacted) (AC-17); no permanent Postgres persistence of raw memory (AC-20)

**Frontend (optional)** — message-detail (005) shows a small, read-only "recent context" chip sourced from the redacted digest; a "refresh/clear context" control for tenant users (no edit of individual facts).

---

## Build Order

1. **Config + Redis client** — `MEMORY_*` settings + async Redis lifecycle + key builders (tenant-embedded).
2. **Cache adapter (`memory_store.py`)** — read/write/append/delete with TTL + bounded list + graceful-degradation wrapper.
3. **Schemas + enums** — `MemoryStatus`/`MemorySource` + view/context DTOs (redacted-only).
4. **Redact + summarize** — `redact_and_summarize` (014 redactor + capped rolling summary + bounded refs + unverified-claim tagging); unit-tested.
5. **MemoryService** — `get_context`/`update_from_message`/`view`/`refresh`/`clear` with tenant-scope resolution; best-effort + audit.
6. **Endpoints** — GET/refresh/DELETE + router mount (behind `MEMORY_ENABLED`) + role/scope gating + 013 audit.
7. **Integration** — wire `get_context` into 010 prompt building (supporting context; RAG authoritative) + `update_from_message` into the message path (best-effort).
8. **Guardrail/grounding wiring** — confirm 014 before/after; grounding blocks invented facts even with memory.
9. **Tests** — unit (redact/summarize, keys, degraded, unverified claim) + integration (AC-01..AC-20).
10. **Validation** — run the 7-step quickstart (guest-count example, RAG-required, tenant isolation, expiry/clear, PII redaction); confirm all 20 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/016-short-term-memory/
├── plan.md
├── research.md
├── spec.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── conversation_memory.py          # GET / POST refresh / DELETE memory
│   ├── services/
│   │   ├── memory_service.py               # get_context / update_from_message / redact_and_summarize / view / refresh / clear
│   │   └── memory_store.py                 # Redis adapter: read/write/append/delete + key builders + TTL + graceful degradation
│   ├── schemas/
│   │   └── memory.py                        # MemoryStatus / MemorySource enums + view/context DTOs
│   └── core/
│       └── redis.py                         # async Redis client lifecycle (if not already present)
└── tests/
    ├── integration/
    │   └── test_conversation_memory.py
    └── unit/
        ├── test_memory_redact_summarize.py
        ├── test_memory_keys.py
        ├── test_memory_degraded.py
        └── test_memory_unverified_claim.py

frontend/                                    # optional
└── src/
    ├── api/
    │   └── conversationMemory.ts
    ├── types/
    │   └── memory.ts
    └── components/conversation/
        └── RecentContextChip.tsx            # read-only redacted "recent context" on the detail page (005)
```

Modified files:

```
backend/app/services/suggested_reply_service.py (010)   # fetch get_context; pass memory as supporting context (RAG authoritative)
backend/app/services/<message ingestion/open path> (003–005)  # best-effort update_from_message after a message is stored/opened
backend/app/services/audit_service.py (013)             # accept new memory_* AuditEventType values (string-backed, no migration)
backend/app/core/config.py                              # MEMORY_* + REDIS_URL settings
backend/app/main.py                                     # mount conversation-memory router (behind MEMORY_ENABLED); Redis lifecycle
frontend/src/pages/MessageDetailPage.tsx (005)          # optional: render the read-only recent-context chip
```

**Structure Decision**: Web application — FastAPI backend + React SPA, matching Specs 001–015. Short-term memory is an **enrichment layer**: a Redis-backed `MemoryService` (no Postgres persistence of raw memory), three thin tenant-scoped endpoints, and one integration hook into the existing RAG/suggested-reply step. The tenant-embedded key scheme, redact-then-summarize, redact-on-read, RAG-wins prompt contract, before/after guardrails, best-effort audit, and graceful degradation all live in the service so the guarantees hold no matter who calls it. No new required ingestion step, no permanent storage, no autonomous behavior.
