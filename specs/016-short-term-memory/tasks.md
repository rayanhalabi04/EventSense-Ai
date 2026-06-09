---
description: "Task list for Short-Term Conversation Memory feature implementation"
---

# Tasks: Short-Term Conversation Memory

**Branch**: `016-short-term-memory` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/016-short-term-memory/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement; this feature **enriches** them):
- Spec 001 — Multi-Tenant Workspace: `tenants`, `tenant_id` isolation boundary, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin`; tenant/role from JWT; platform admin has **no** tenant-content access by default
- Spec 003 — Message Simulator: `conversations`/`messages` (the source material; `direction` inbound/outbound; recent window per conversation)
- Spec 005 — Message Detail Page: the surface a memory-enriched reply is reviewed on (+ optional recent-context chip)
- Spec 009 — RAG Over Tenant Documents: `rag_service.query(...)` — the **source of truth** memory supports but never overrides
- Spec 010 — Suggested Replies: `suggested_reply_service.generate(...)` — the consumer of memory context (human-reviewed, never auto-sent)
- Spec 011 — Tasks / Spec 012 — Escalation: memory must **NOT** auto-create these (negative dependency)
- Spec 013 — Audit Logs: `AuditService.log_event(...)` + the audit redactor; accepts new string-backed `memory_*` event types (no enum migration)
- Spec 014 — Guardrails: `check_user_input` / `check_ai_output` / `redact_text` / `validate_rag_grounding` (redaction + grounding before/after memory use)
- Redis (new infra): the temporary cache backing the digest with a TTL

**Tech stack**: FastAPI + SQLAlchemy 2.x async + pydantic v2 + `redis.asyncio` (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (optional frontend chip) · **no Alembic migration** — memory is Redis-only

**No new schema**: memory is **ephemeral by design** and lives in **Redis** (default 7-day TTL) — **no new Postgres tables, no migration**. This feature defines the cache document schema (`ConversationMemory`, `MemoryEntry`) + in-process Pydantic shapes. The only additive existing-table touch is the Spec 013 audit writer accepting new string-backed `memory_*` event types (no enum-altering migration). `tenants`/`conversations`/`messages` are used as-is and never modified.

**Config defaults** (data-model.md Configuration): `MEMORY_ENABLED=true`, `MEMORY_TTL_SECONDS=604800` (7 days), `MEMORY_MAX_RECENT_MESSAGES=10`, `MEMORY_SUMMARY_MAX_CHARS=1000`, `REDIS_URL` (env).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–014 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` + tenant-scoped session context (001), `require_auth`/`get_current_tenant_context` + the platform-admin tenant-content block (002), `Conversation`/`Message` readers + the recent-window query (most-recent N by `created_at`, with `direction`) (003), `rag_service.query` (009), `suggested_reply_service.generate` + its prompt builder (010), `AuditService.log_event` + the audit redactor (013), `redact_text`/`check_user_input`/`check_ai_output`/`validate_rag_grounding` (014), and `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (001). Do NOT redefine any of these.
- [ ] T002 Add the `MEMORY_*` + `REDIS_URL` settings to `backend/app/core/config.py` with documented defaults: `MEMORY_ENABLED=true`, `MEMORY_TTL_SECONDS=604800`, `MEMORY_MAX_RECENT_MESSAGES=10`, `MEMORY_SUMMARY_MAX_CHARS=1000`, `REDIS_URL` (data-model.md Configuration)
- [ ] T003 Add the new string-backed `memory_*` event types to the Spec 013 `AuditEventType` (no enum-altering migration): `memory_viewed`, `memory_refreshed`, `memory_cleared`, `memory_used_in_reply` — additive, consistent with 013's closed-but-extensible approach (plan.md Guardrail/Audit Notes, research.md Decision 9)
- [ ] T004 Record the exact upstream accessor signatures memory will call — the recent-window message reader (tenant-scoped, ordered most-recent N, with `body`/`direction`/`created_at`), the 010 prompt builder's extension point for a memory block, and the conversation-resolve-within-tenant helper (mirroring 005–014's 404/403) — all read-only (FR-019, SP-01)
- [ ] T005 Verify `backend/tests/unit/` and `backend/tests/integration/` exist with `__init__.py`; confirm a test Redis is available (real or a fakeredis fixture) for the cache tests; create any missing test dirs

**Checkpoint**: Dependencies confirmed reused; config + Redis URL + audit `memory_*` events in place; recent-window/prompt accessors recorded; test Redis ready.

---

## Phase 2: Redis Client & Cache Configuration (Foundational — Blocking)

**Purpose**: The async Redis lifecycle, tenant-embedded key builders, TTL discipline, and the graceful-degradation wrapper that makes memory optional. **BLOCKS the cache adapter and service.**

**⚠️ CRITICAL**: Phases 4–8 cannot run without this phase.

- [ ] T006 Create the async Redis client lifecycle in `backend/app/core/redis.py`: a pooled `redis.asyncio` client created at app startup from `REDIS_URL`, closed on shutdown; a `get_redis()` accessor; wire startup/shutdown into `backend/app/main.py` (plan.md Redis #1)
- [ ] T007 Implement the tenant-embedded key builders (in `backend/app/services/memory_store.py`): `_mem_key(tenant_id, conversation_id) = f"mem:{tenant_id}:{conversation_id}"` and `_entries_key(...) = _mem_key + ":entries"` — **`tenant_id` is mandatory and first** so a `conversation_id` alone can never address another tenant's memory (FR-020, SP-01, AC-18, research.md Decision 2) (depends on T006)
- [ ] T008 Implement the graceful-degradation wrapper (in `backend/app/services/memory_store.py`): a decorator/util around every Redis op so a connection error or `MEMORY_ENABLED=false` → empty/no-op return, a logged warning, and **never** a raise into the request path (FR-016, AC-15, research.md Decision 7) (depends on T006)

**Checkpoint**: Redis client starts/stops with the app; tenant-embedded keys build correctly; all cache ops degrade gracefully instead of raising.

---

## Phase 3: Schemas & Enums (Foundational — Blocking)

**Purpose**: The cache-document/enum shapes and in-process Pydantic DTOs (redacted-only views) shared by the store, service, and endpoints. No SQL.

- [ ] T009 [P] Create the enums in `backend/app/schemas/memory.py`: `MemoryStatus` (`active`, `expired`, `cleared`, `disabled` — derived at read time, not stored), `MemorySource` (`inbound_message`, `outbound_message`, `summary`, `system_note`), and `MemoryEntryType` (`recent_message`, `rolling_summary`, `salient_fact`, `reference_anchor`) — per data-model.md
- [ ] T010 Add the Pydantic DTOs to `backend/app/schemas/memory.py` (redacted-only fields) per data-model.md: `MemoryEntryView` (`id`, `source_message_id`, `entry_type`, `content_summary` redacted, `pii_redacted`, `source`, `created_at`, `expires_at`, `metadata`), `ConversationMemoryView` (`tenant_id`, `conversation_id`, `memory_key`, `status`, `summary` redacted/capped, `recent_message_refs: list[MemoryEntryView]` bounded, `updated_at`/`expires_at` nullable, `metadata`), `MemoryContext` (internal: `conversation_id`, `summary`, `recent_refs: list[str]`, `anchors: dict`, `is_empty`), `MemoryRefreshRequest` (`max_recent_messages: int | None`), `MemoryRefreshResponse` (`conversation_id`, `status`, `updated_at`, `expires_at`, `entry_count`), `MemoryClearResponse` (`conversation_id`, `cleared`, `status`) (depends on T009)

**Checkpoint**: Enums + DTOs importable; all view fields are redacted-only — ready for the store + service.

---

## Phase 4: Cache Adapter (`memory_store.py`) (Foundational — Blocking)

**Purpose**: The Redis read/write/append/delete operations with TTL on every write and a bounded entries list. **BLOCKS the service.**

- [ ] T011 [US2] Implement `write_memory(doc)` + `read_memory(tenant_id, conversation_id)` in `backend/app/services/memory_store.py`: `write_memory` does `SET _mem_key value EX MEMORY_TTL_SECONDS` (JSON-serialized `ConversationMemory`, `expires_at` inside the doc mirrors the TTL); `read_memory` returns the parsed doc or `None` (missing key → cold). Both go through the T008 degradation wrapper (FR-002, AC-01) (depends on T007, T008, T010)
- [ ] T012 [US2] Implement `append_entry(tenant_id, conversation_id, entry)` + `delete_memory(tenant_id, conversation_id)` in `backend/app/services/memory_store.py`: `append_entry` does `LPUSH _entries_key` + `LTRIM 0 MEMORY_MAX_RECENT_MESSAGES-1` + `EXPIRE` (bounded recent-ref list); `delete_memory` does `DEL` on **both** the document and entries keys (idempotent — returns `true` whether or not a key existed) (FR-003, FR-017, AC-02, AC-16) (depends on T007, T008)

**Checkpoint**: The cache adapter writes with TTL, keeps the entries list bounded, reads cold on a missing key, and clears both keys idempotently — all degrading gracefully.

---

## Phase 5: Redact + Summarize (Foundational — Blocking, unit-tested)

**Purpose**: The redact-then-summarize helper that produces the bounded, length-capped, PII-free digest with reference anchors and unverified-claim tags. **BLOCKS the service.**

- [ ] T013 [US2] Implement `redact_and_summarize(messages) -> (summary, entries, pii_redacted)` in `backend/app/services/memory_service.py` per data-model.md / api-contracts §6: Step 1 — run each message `body` through the 014 `redact_text` (PII + secrets + prompt markers); Step 2 — build a **rolling summary** length-capped at `MEMORY_SUMMARY_MAX_CHARS`; Step 3 — build bounded `MemoryEntry`s (redacted `content_summary`, `entry_type`, `source_message_id`, `pii_redacted`, `source`); raw bodies are **never** copied into the digest; `pii_redacted=True` if any redaction occurred (FR-004, FR-007, SP-02, AC-03, research.md Decision 3 & 10) (depends on T010)
- [ ] T014 [US1][US2] Add reference-anchor + unverified-claim handling to `redact_and_summarize`: preserve antecedents for "that"/"it"/"the package"/"the guest count"/"the deposit" as `reference_anchor`/`salient_fact` entries (e.g. `metadata={"anchor":"guest_count","from":150,"to":220}`); tag unverifiable client claims `metadata={"fact":"deposit_paid","verified":false}` so downstream replies never fabricate a confirmation (AC-07, AC-10, research.md Decision 6) (depends on T013)
- [ ] T015 [P] [US2] Unit `backend/tests/unit/test_memory_redact_summarize.py`: a body with an email + phone → `[EMAIL_REDACTED]`/`[PHONE_REDACTED]` in summary + entries, `pii_redacted=True`, no raw PII; summary length ≤ `MEMORY_SUMMARY_MAX_CHARS`; entries ≤ `MEMORY_MAX_RECENT_MESSAGES` (AC-02, AC-03) (depends on T013)
- [ ] T016 [P] [US2] Unit `backend/tests/unit/test_memory_unverified_claim.py`: "I paid the deposit yesterday." → an entry tagged `metadata.verified=false`; the guest-count example yields an `anchor` entry (`from:150`,`to:220`) (AC-07, AC-10) (depends on T014)

**Checkpoint**: The digest is redacted, bounded, length-capped, anchor-aware, and unverified-claim-tagged; unit-tested.

---

## Phase 6: Memory Service (Foundational — Blocking)

**Purpose**: The single `MemoryService` enforcing tenant-scope resolution, redact-on-read, best-effort writes, TTL, and audit — used identically by the endpoints and the internal callers. **BLOCKS the API and the reply integration.**

- [ ] T017 [US1] Implement `get_context(session, *, tenant_id, conversation_id) -> MemoryContext` in `backend/app/services/memory_service.py`: if `MEMORY_ENABLED=false` → empty context; else `store.read_memory` (never raises — degraded → `None` → empty); redact-on-read (`redact_context` via 014 redactor, SP-04); return a `MemoryContext` (or `is_empty=True`). **Never raises** to the caller (FR-005, FR-016, FR-018, AC-04, AC-15, research.md Decision 7) (depends on T011, T013)
- [ ] T018 [US2] Implement `update_from_message(session, *, tenant_id, conversation_id, message_id) -> None` in `backend/app/services/memory_service.py`: no-op when disabled/cache-down; load the bounded recent window (most-recent `MEMORY_MAX_RECENT_MESSAGES`), `redact_and_summarize`, `store.write_memory` with refreshed TTL; **best-effort** (failures logged + swallowed); writes **only** the digest — no reply/task/escalation (FR-006, FR-019, SP-06, AC-05) (depends on T011, T013)
- [ ] T019 Implement `resolve_conversation_or_404(session, caller, conversation_id)` in `backend/app/services/memory_service.py`: load the conversation; **404 `CONVERSATION_NOT_FOUND`** if not in the caller's tenant; **403 `TENANT_CONTENT_FORBIDDEN`** for platform admin / no tenant-content access; **no Redis key is constructed** for a cross-tenant conversation (FR-014, SP-01, SP-07, AC-14, AC-19, research.md Decision 2) (depends on T001)
- [ ] T020 [US3] Implement `view(session, *, caller, conversation_id) -> ConversationMemoryView` in `backend/app/services/memory_service.py`: `resolve_conversation_or_404` first; `store.read_memory`; derive `status` (`active`/`expired`/`cleared`/`disabled`) at read time; return the redacted view; best-effort audit `memory_viewed` (FR-015, FR-018, AC-13, AC-17) (depends on T017, T019)
- [ ] T021 [US3] Implement `refresh(session, *, caller, conversation_id, max_recent_messages=None) -> MemoryRefreshResponse` in `backend/app/services/memory_service.py`: `resolve_conversation_or_404`; clamp/validate `max_recent_messages` to `1..MEMORY_MAX_RECENT_MESSAGES`; rebuild via `update_from_message` logic; advance `updated_at`/`expires_at`; best-effort audit `memory_refreshed`; degraded/disabled → `status="disabled"` response (FR-015, AC-13, AC-16) (depends on T018, T019)
- [ ] T022 [US3] Implement `clear(session, *, caller, conversation_id) -> MemoryClearResponse` in `backend/app/services/memory_service.py`: `resolve_conversation_or_404`; `store.delete_memory` (idempotent — `cleared=true` regardless); best-effort audit `memory_cleared`; clears **only** memory (never deletes messages/replies/tasks/escalations/audit logs) (FR-017, SP-06, AC-16) (depends on T012, T019)
- [ ] T023 No-side-effects + redacted-audit guarantee: ensure `backend/app/services/memory_service.py` imports/calls **no** reply-send (010), task-create (011), or escalation-create (012) path; audit calls pass only redacted ids/facts; back it with the Phase 12 test (FR-011, SP-06, SP-08, AC-11, research.md Decision 11) (depends on T017–T022)

**Checkpoint**: The service resolves tenant scope before any key, redacts in + out, writes with TTL best-effort, audits each action, and has no autonomous side effects.

---

## Phase 7: API Endpoints

**Purpose**: The three thin tenant-scoped endpoints (inspect / rebuild / clear) calling the same service. Platform admin → 403; cross-tenant → 404; cache down → 200-degraded. **No PATCH/per-entry routes (→405).**

- [ ] T024 [P] [US3] Implement `GET /api/conversations/{conversation_id}/memory` in `backend/app/api/v1/conversation_memory.py`: require authenticated tenant user (staff/manager); call `service.view`; return `ConversationMemoryView` **200** (active or cold/empty `disabled`); 422 on non-UUID, 404 cross-tenant, 403 platform admin (contracts §1, AC-13, AC-14, AC-19) (depends on T020)
- [ ] T025 [P] [US3] Implement `POST /api/conversations/{conversation_id}/memory/refresh` in `backend/app/api/v1/conversation_memory.py`: optional `MemoryRefreshRequest` (`max_recent_messages` 1..`MEMORY_MAX_RECENT_MESSAGES`, else 422); call `service.refresh`; return `MemoryRefreshResponse` **200** (or `disabled` when off/down); 404/403 as §1 (contracts §2, FR-015, AC-13) (depends on T021)
- [ ] T026 [P] [US3] Implement `DELETE /api/conversations/{conversation_id}/memory` in `backend/app/api/v1/conversation_memory.py`: call `service.clear`; return `MemoryClearResponse` **200** (`cleared:true`, idempotent); 404/403 as §1 (contracts §3, FR-017, AC-16) (depends on T022)
- [ ] T027 Mount the conversation-memory router at `/api` in `backend/app/main.py` **behind `MEMORY_ENABLED`**; confirm **no** PATCH/PUT or per-entry write route exists (any such method → 405 `METHOD_NOT_ALLOWED`) (contracts §"No Other Mutating Endpoints", plan.md #7) (depends on T024–T026)

**Checkpoint**: The three endpoints enforce tenant scope + the role matrix, return redacted digests / 200-degraded, and expose no mutate/per-entry route.

---

## Phase 8: RAG / Suggested-Reply Integration & Update Trigger

**Purpose**: Wire `get_context` into the existing 010 reply step as **supporting context** (RAG authoritative, RAG-wins on conflict), and trigger `update_from_message` best-effort after a message is stored/opened. This feature does **not** generate replies or retrieve documents — it enriches them.

- [ ] T028 [US1] Extend the 010 prompt builder in `backend/app/services/suggested_reply_service.py` to accept a `memory_context` block clearly labeled **advisory/supporting**, separate from the **authoritative** RAG `sources` block; the system instruction states policy/price/contract answers must come from sources and that on conflict the sources win (FR-008, FR-009, SP-09, research.md Decision 5) (depends on T010)
- [ ] T029 [US1] Wire `get_context` into `suggested_reply_service.generate(...)`: fetch the redacted `MemoryContext` and pass it into the prompt builder **alongside** (never instead of) `rag_service.query(...)`; an empty context (cold/disabled/cache-down) → generation proceeds exactly as pre-016 (FR-008, AC-06, AC-15) (depends on T017, T028)
- [ ] T030 [US1] Confirm grounding runs **after** memory use: `check_ai_output`/`validate_rag_grounding` (014) runs on the memory-assisted draft so an invented price/policy fails grounding regardless of what memory implied; an unverifiable claim yields a "check/confirm" reply, never a false confirmation (FR-010, FR-012, AC-08, AC-09, AC-10, AC-12, research.md Decision 8) (depends on T029)
- [ ] T031 [US2] Trigger `update_from_message` best-effort in the message stored/opened path (003–005) so the next reply has fresh context; it is **never** a blocking step and never auto-sends/creates anything (FR-019, SP-06, AC-05, research.md Decision 12) (depends on T018)
- [ ] T032 Best-effort `memory_used_in_reply` audit: when `get_context` returns a non-empty digest that informs a generated draft, log a redacted `memory_used_in_reply` audit event (ids/facts only); failure never breaks reply generation (FR-013, AC-17) (depends on T029)

**Checkpoint**: The reply step uses memory as supporting context with RAG authoritative and grounding after; updates trigger best-effort off the critical path; memory use is audited.

---

## Phase 9: Optional Frontend (Recent-Context Chip)

**Purpose**: An optional read-only redacted "recent context" chip on the message detail page (005), plus refresh/clear controls. No per-fact editing. (Spec marks the UI optional — include if building the visible memory surface.)

- [ ] T033 [P] Add TS types to `frontend/src/types/memory.ts`: `MemoryStatus`, `MemorySource`, `MemoryEntryView`, `ConversationMemoryView` (data-model.md Frontend shapes)
- [ ] T034 [P] Add the typed API client `frontend/src/api/conversationMemory.ts`: `getMemory(conversationId)`, `refreshMemory(conversationId, maxRecent?)`, `clearMemory(conversationId)` — with the auth header (depends on T033)
- [ ] T035 [US3] Implement `frontend/src/components/conversation/RecentContextChip.tsx`: a read-only redacted "recent context" chip (summary + bounded refs + an expiry indicator), with **refresh** and **clear** actions (tenant users only); loading / empty (cold) / error / `disabled` states; **no** per-fact edit control; render it on `frontend/src/pages/MessageDetailPage.tsx` (005) (plan.md Testing/Frontend, AC-13, AC-16) (depends on T034)

**Checkpoint**: The detail page shows a redacted recent-context chip with expiry + refresh/clear; no raw PII rendered; no per-fact editing.

---

## Phase 10: Tenant Isolation & Security Tests (cross-cutting)

**Purpose**: Prove tenant-embedded keys, conversation-scope resolution, platform-admin exclusion, and no-autonomy. `backend/tests/unit/test_memory_keys.py` + `backend/tests/integration/test_conversation_memory.py`.

- [ ] T036 [P] Unit `backend/tests/unit/test_memory_keys.py`: `_mem_key`/`_entries_key` embed `tenant_id` first (`mem:{tenant_id}:{conversation_id}`); the same `conversation_id` under two tenants yields two distinct keys — a `conversation_id` alone can't address another tenant's memory (AC-18, SP-01) (depends on T007)
- [ ] T037 [P] Cross-tenant memory read blocked: Tenant A GET/refresh/DELETE on a Tenant B conversation → 404 `CONVERSATION_NOT_FOUND`; assert **no** Redis key was constructed for the cross-tenant id (AC-14, FR-014, SP-01) (depends on T024)
- [ ] T038 [P] Platform admin blocked: a platform-admin token on GET/refresh/DELETE memory → 403 `TENANT_CONTENT_FORBIDDEN` (AC-19, SP-07) (depends on T024)
- [ ] T039 [P] Client-supplied tenant ignored: a `tenant_id` injected into the body/query does not change scope — the key/read uses the JWT tenant only (SP-01, FR-014) (depends on T024)
- [ ] T040 [P] No autonomy + no permanent storage: a memory update/refresh/use sends no reply (010), creates no task (011) / escalation (012); assert no `conversation_memory` Postgres table exists (memory is Redis-only) (AC-11, AC-20, SP-06) (depends on T023, T031)
- [ ] T041 [P] No-mutate routes: `PATCH /api/conversations/{id}/memory` and `POST /api/conversations/{id}/memory/entries` → 405 `METHOD_NOT_ALLOWED` (contracts §"No Other Mutating Endpoints") (depends on T027)

**Checkpoint**: Tenant isolation (keys + scope), platform-admin exclusion, client-tenant-ignored, no-autonomy, no-permanent-storage, and no-mutate-routes are all proven.

---

## Phase 11: Memory Behaviour & Integration Tests

**Purpose**: Verify TTL/storage, reference resolution, RAG-authoritative integration, grounding, degradation, clear/expiry, and audit. `backend/tests/integration/test_conversation_memory.py` + units.

- [ ] T042 [P] [US2] `update_from_message` writes a tenant-scoped digest under `mem:{tenant_id}:{conversation_id}` with TTL ≈ 604800 and `expires_at` ~7 days out; the recent-ref list is capped at `MEMORY_MAX_RECENT_MESSAGES` (AC-01, AC-02, AC-05) (depends on T018, T011)
- [ ] T043 [P] [US1] `get_context` returns the redacted digest scoped to tenant + conversation; reference resolution works for the guest-count ("that" → 150→220) and deposit ("it" → deposit, unverified) examples (AC-04, AC-07) (depends on T017, T014)
- [ ] T044 [P] [US1] Suggested reply (010) receives memory as **supporting context** while RAG (009) is still queried and authoritative; the draft resolves "that" but states no price unless a source supports it — no invented price (014 grounding) (AC-06, AC-08) (depends on T029, T030)
- [ ] T045 [P] [US1] Memory–RAG conflict → RAG policy wins: a contradictory memory claim ("you said the deposit is refundable") vs a non-refundable policy doc → the draft follows the document (AC-09, FR-009) (depends on T030)
- [ ] T046 [P] [US1] Unverifiable claim → no false confirmation: the deposit "confirm it?" example yields a "check/confirm" reply, never "payment confirmed" (AC-10) (depends on T030)
- [ ] T047 [P] [US1] Guardrails before + after: `check_user_input` runs before a message informs memory and `check_ai_output` runs on the memory-assisted draft (AC-12, FR-012) (depends on T030, T031)
- [ ] T048 [P] [US1] Optional/degradable: with Redis down (or `MEMORY_ENABLED=false`), a suggested reply is still generated (memory-less, RAG-grounded) and GET memory returns `status="disabled"` — **no 5xx** (AC-15, FR-016) (depends on T017, T029); also covered by unit `backend/tests/unit/test_memory_degraded.py` (cache error → empty context / no-op, no raise)
- [ ] T049 [P] [US3] GET/refresh/DELETE work, redacted + tenant-scoped (AC-13); clear then GET reads cold (`status` `cleared`/`expired`, empty); a refresh rebuilds with a new `expires_at` (AC-16) (depends on T024, T025, T026)
- [ ] T050 [P] [US3] Memory actions audited (redacted): `memory_viewed`/`memory_refreshed`/`memory_cleared`/`memory_used_in_reply` entries exist with ids/facts only and no raw PII; an audit failure never breaks the primary action (AC-17, FR-013) (depends on T020, T021, T022, T032)
- [ ] T051 [P] [US2] PII redacted in storage: a message with email/phone → the stored digest summary/refs contain placeholders only, `metadata.pii_redacted=true`, and a scan finds no raw `@example`/`+961`/secret patterns in the digest or the GET response (AC-03, SP-02, SP-04) (depends on T018, T024)

**Checkpoint**: All 20 acceptance criteria are covered by passing unit/integration tests; TTL/storage, reference resolution, RAG-authoritative, grounding, conflict/unverified handling, degradation, clear/expiry, isolation, and audit verified.

---

## Phase 12: Frontend Tests (optional — if Phase 9 built)

**Purpose**: Render/interaction tests for the recent-context chip and its refresh/clear actions.

- [ ] T052 [P] `RecentContextChip` render test in `frontend/src/components/conversation/__tests__/RecentContextChip.test.tsx`: renders the redacted summary + bounded refs + expiry indicator; empty (cold) / loading / error / `disabled` states render; no raw PII rendered (AC-13, AC-16) (depends on T035)
- [ ] T053 [P] Action test: the refresh action calls `refreshMemory` and the clear action calls `clearMemory` with the conversation id; after clear the chip shows the cold/empty state (AC-16) (depends on T035)

**Checkpoint**: Chip states + refresh/clear interactions verified; redacted/read-only guarantees confirmed in the UI.

---

## Phase 13: Quickstart & Manual Validation

**Purpose**: Execute the seven-step quickstart end to end (quickstart.md). Requires Redis running, two seeded tenants with staff + RAG documents.

- [ ] T054 Set `MEMORY_ENABLED=true` + the `MEMORY_*` defaults; confirm Redis reachable at `REDIS_URL`; log in as staff of both demo tenants (Tenant 1 = elegant-weddings, Tenant 2 = royal-events)
- [ ] T055 Steps 1–3 — create a conversation with "increase the guest count from 150 to 220", add "Will that affect the price?", then GET memory → `status:"active"`, summary mentions 150→220, a ref has `metadata.anchor="guest_count"` (from:150,to:220); the suggested reply resolves "that" as the guest-count increase (AC-01, AC-05, AC-07)
- [ ] T056 Step 4 — confirm RAG is still required: the reply's `sources` list the tenant's pricing/catering docs; no price is invented when the docs don't support it; a contradictory memory claim → the draft follows the document (RAG wins); the deposit "confirm it?" variant → `verified:false` and no false confirmation (AC-06, AC-08, AC-09, AC-10)
- [ ] T057 Step 5 — tenant isolation: Tenant 2 GET on Tenant 1's conversation memory → 404; `redis-cli KEYS "mem:*:$CONV"` shows exactly one tenant-1-prefixed key; a platform-admin token → 403 (AC-14, AC-18, AC-19)
- [ ] T058 Step 6 — expiry/clear/degraded: `redis-cli TTL` on the key ≈ 604800; DELETE memory → `cleared:true`; a later GET reads cold; refresh rebuilds with a +7d `expires_at`; stop Redis (or `MEMORY_ENABLED=false`) → a reply is still generated and GET returns `status:"disabled"`, no 5xx (AC-15, AC-16)
- [ ] T059 Step 7 — PII + audit + no-Postgres: a message with email/phone → `metadata.pii_redacted=true` and `[EMAIL_REDACTED]`/`[PHONE_REDACTED]` in summary/refs; a grep over the digest finds 0 raw PII/secret patterns; `\dt | grep memory` finds 0 tables; `memory_used_in_reply`/`memory_viewed`/`memory_refreshed`/`memory_cleared` audit entries exist (redacted) (AC-03, AC-17, AC-20)

**Checkpoint**: Quickstart passes end to end; reference resolution, RAG-required, tenant isolation, expiry/clear/degraded, PII redaction, and audit demonstrated live.

---

## Phase 14: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T060 Verify AC-01..AC-20 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T061 Walk `checklists/requirements.md` (Functional / Memory Behavior / Redis-TTL / AI Integration / RAG Grounding / Security-Privacy / Tenant Isolation / API-Service / Data / Testing) and tick each implemented item; confirm the six hard guarantees (tenant isolation, RAG is source of truth, temporary + minimized, no autonomy, optional/degradable, auditable)
- [ ] T062 Confirm Out-of-Scope items remain **unbuilt**: no long-term/permanent memory or durable transcript; no cross-conversation or cross-tenant memory; no memory as a source of truth for package/price/refund/cancellation/contract (RAG is); no auto-sending replies; no auto-creating tasks or escalations from memory; no vector/semantic long-term memory store; no CRM/personalization profiles; no storing raw PII or full message history (redacted bounded digest only); no per-entry memory editing / manual fact authoring UI; no real WhatsApp API / calendar syncing / billing (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 016 verified against spec + checklist; short-term memory enriches the 009→010 step with tenant-scoped, redacted, expiring, RAG-subordinate context that never acts autonomously and degrades gracefully.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (Redis client + keys + degradation)** → depends on Phase 1; **BLOCKS the store/service**.
- **Phase 3 (Schemas/enums)** → depends on Phase 1; blocks the store/service/API.
- **Phase 4 (Cache adapter)** → depends on Phases 2–3; blocks the service.
- **Phase 5 (Redact + summarize)** → depends on Phase 3 (+ 014 redactor); pure functions; blocks the service.
- **Phase 6 (Memory service)** → depends on Phases 4–5; **BLOCKS the API + reply integration**.
- **Phase 7 (API)** → depends on Phase 6; **MVP backend deliverable** (operability).
- **Phase 8 (RAG/reply integration + update trigger)** → depends on Phase 6; the core US1 value.
- **Phase 9 (Optional frontend)** → depends on Phase 7 (reads); optional, can be deferred.
- **Phase 10 (Isolation/security tests)** + **Phase 11 (Behaviour tests)** → depend on Phases 6–8.
- **Phase 12 (Frontend tests)** → depends on Phase 9.
- **Phase 13 (Quickstart)** → depends on Phases 7–8 (+ 9 for the UI walkthrough).
- **Phase 14 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 — reference resolution + safe construction)

1. Phase 1: Setup (config + Redis URL + audit `memory_*` events)
2. Phase 2: Redis client + tenant-embedded keys + graceful-degradation wrapper (**CRITICAL**)
3. Phase 3: Schemas + enums (redacted-only views)
4. Phase 4: Cache adapter (write/read/append/delete + TTL + bounded list)
5. Phase 5: Redact + summarize (PII-free, bounded, anchors + unverified-claim tags)
6. Phase 6: MemoryService (`get_context`/`update_from_message`/`view`/`refresh`/`clear`, tenant-scope, redact-on-read, best-effort audit, no side effects)
7. Phase 8: Wire `get_context` into 010 (supporting context, RAG authoritative, grounding after) + `update_from_message` trigger (best-effort)
8. **STOP and VALIDATE**: run isolation + behaviour tests; confirm tenant isolation, RAG-wins/no-invented-price, redaction in+out, TTL/expiry, degradation, no autonomy

### Incremental Delivery

1. Setup + Redis + schemas + cache adapter + redact/summarize → foundation ready
2. US1 (reference resolution improves a grounded reply) → the core AI value
3. US2 (memory built safely — redacted, bounded, expiring) → the privacy/safety construction
4. US3 (view/refresh/clear endpoints + optional chip) → operability + privacy controls
5. Guardrail/grounding wiring → memory inherits the 014 safety contract (before + after)
6. Tests + quickstart + acceptance → all 20 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id`/`user_id`/`role` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SP-01, FR-014); any client-supplied `tenant_id` is ignored (T039)
- **Tenant isolation** — Redis keys embed `tenant_id` first (`mem:{tenant_id}:{conversation_id}`); the conversation is resolved within the caller's tenant **before** any key is built (cross-tenant → 404, key never constructed); A never reads/derives B's memory; no cross-conversation bleed (FR-014, FR-020, SP-01, SP-05, AC-14, AC-18, T007, T019, T036, T037). First hard guarantee
- **RAG is the source of truth** — memory is injected as a labeled **advisory** block separate from the **authoritative** RAG `sources`; on conflict RAG wins; 014 grounding runs after memory use so an invented price/policy fails regardless of what memory implied; an unverifiable claim never becomes a false confirmation (FR-008, FR-009, FR-010, SP-09, AC-08, AC-09, AC-10, T028–T030, research.md Decisions 5 & 6). Second hard guarantee
- **Temporary + minimized** — Redis-only (no Postgres table), TTL on every write (default 7 days) + `expires_at`, clearable on demand, redacted before storage and again on read, bounded (≤ N refs + a length-capped summary); nothing stored forever (FR-002, FR-003, FR-004, SP-02, SP-03, SP-04, AC-01, AC-02, AC-03, AC-20, T011–T013, T040). Third hard guarantee
- **No autonomy** — the service imports no reply-send/task-create/escalation-create path; the strongest effect is writing/clearing the digest; updates are best-effort and never block ingestion (FR-011, FR-019, SP-06, AC-11, T023, T031). Fourth hard guarantee
- **Optional / degradable** — every Redis op is wrapped; cache down or `MEMORY_ENABLED=false` → `get_context` empty, `update_from_message` no-op, endpoints return 200-`disabled`; the RAG+reply pipeline always proceeds memory-less; **never a 5xx on the memory path** (FR-016, AC-15, T008, T048, research.md Decision 7). Fifth hard guarantee
- **Auditable** — `memory_viewed`/`memory_refreshed`/`memory_cleared`/`memory_used_in_reply` logged best-effort with redacted ids/facts only; an audit failure never breaks the primary action (FR-013, SP-08, AC-17, T003, T032, T050, research.md Decision 9). Sixth hard guarantee
- **Status is derived, not stored** — `active`/`expired`/`cleared`/`disabled` are computed at read time so the API/UI can explain *why* a memory is empty (data-model.md enums, T020)
- **Deterministic summarizer for the MVP** — extractive recent salient lines + entities/anchors, length-capped; an LLM summarizer can replace it behind the same `redact_and_summarize` interface later (output must still pass `redact_text` + the cap) (research.md Decision 10)
- **One memory code path** — endpoints and internal callers (010 reply, ingestion) all go through `MemoryService`, so isolation/redaction/TTL/audit are enforced once regardless of entry point (research.md Decision 11)
- **No new required ingestion step** — `update_from_message` is best-effort after a message is stored/opened; with the feature off, behavior equals pre-016 (FR-019, research.md Decision 12)
- **Frontend is optional** — the spec marks the recent-context chip optional; Phases 9 & 12 are included for the visible-memory surface and can be skipped without affecting the backend MVP
- This feature is an **enrichment layer** over 003–014: a Redis-backed memory service + three thin endpoints + one integration hook. It adds no permanent storage, no new required ingestion step, and no autonomous behavior
