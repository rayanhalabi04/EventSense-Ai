# Requirements Checklist: Short-Term Conversation Memory

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (better, grounded suggested replies that resolve recent references) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Memory behavior, AI behavior, Security/privacy, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Short-term memory maintained per conversation, scoped to tenant + conversation id (FR-001, AC-01)
- [ ] Internal `memory.get_context(tenant_id, conversation_id)` returns the redacted digest or empty (FR-005, AC-04)
- [ ] Internal `memory.update_from_message(tenant_id, conversation_id, message_id)` redacts+summarizes + refreshes TTL (FR-006, AC-05)
- [ ] Internal `memory.redact_and_summarize(...)` produces redacted, length-capped summary + bounded entries (FR-007, AC-02, AC-03)
- [ ] `GET /memory` (inspect), `POST /memory/refresh` (rebuild), `DELETE /memory` (clear) all work, tenant-scoped (FR-015, AC-13)
- [ ] Memory is optional/degradable: cache down or `MEMORY_ENABLED=false` → pipeline still works, no hard error (FR-016, AC-15)
- [ ] Memory is used only as an enrichment of the existing RAG/reply step; no new required ingestion step (FR-019)
- [ ] Memory read/refresh/clear/use is auditable via Spec 013 (redacted) (FR-013, AC-17)

---

## Memory Behavior Requirements

- [ ] Digest = rolling `summary` + ≤ `MEMORY_MAX_RECENT_MESSAGES` recent refs (bounded, not full history) (FR-003, AC-02)
- [ ] Reference resolution: "that"/"it"/"the package"/"the guest count"/"the deposit" map to the recent antecedent (AC-07)
- [ ] Unverifiable claim ("I paid the deposit") tagged `verified:false`; reply never fabricates a confirmation (AC-10)
- [ ] Memory is supporting context only — never the source of truth for policy/price/contract (FR-008, SP-09)
- [ ] Memory–RAG conflict → RAG policy wins (FR-009, AC-09)
- [ ] Memory never auto-sends a reply or auto-creates a task/escalation (FR-011, AC-11)
- [ ] Memory status derived (`active`/`expired`/`cleared`/`disabled`), not mutable stored state

---

## Redis / TTL Requirements

- [ ] Memory stored in Redis (temporary cache), not Postgres (FR-002, AC-20)
- [ ] TTL default 7 days (`MEMORY_TTL_SECONDS=604800`) applied on every write; `expires_at` mirrors it (FR-002, AC-01)
- [ ] Redis key embeds `tenant_id`: `mem:{tenant_id}:{conversation_id}` (FR-020, AC-18)
- [ ] Recent-ref list bounded via cap (`LPUSH`+`LTRIM`) to `MEMORY_MAX_RECENT_MESSAGES` (FR-003, AC-02)
- [ ] Memory clearable on demand (`DELETE` → Redis `DEL`) and auto-expires at TTL; reads cold after (FR-017, AC-16)
- [ ] All Redis ops wrapped for graceful degradation (error → empty/no-op, log, never raise) (FR-016, AC-15)
- [ ] Nothing stored forever — no permanent transcript; only the expiring digest exists (SP-03, AC-20)

---

## AI Integration Requirements

- [ ] Suggested reply (010) receives memory as supporting context via `get_context` (FR-008, AC-06)
- [ ] Reply prompt separates advisory `[recent context]` (memory) from authoritative `[sources]` (RAG)
- [ ] AI resolves recent references using the digest (guest-count + deposit examples) (AC-07)
- [ ] AI does not invent a price/policy/commitment unsupported by sources, even with memory present (FR-010, AC-08)
- [ ] Memory update triggered after a message is stored/opened (best-effort, non-blocking) (FR-019)
- [ ] Empty context (cold/disabled/cache-down) → generation proceeds exactly as pre-016 (AC-15)

---

## RAG Grounding Requirements

- [ ] RAG (009) is still queried on every memory-enriched reply; sources are the source of truth (FR-008, AC-06)
- [ ] On memory vs RAG conflict, the draft follows the RAG document (FR-009, AC-09)
- [ ] No invented price/policy: 014 grounding (`validate_rag_grounding`) runs after memory use (FR-010, AC-08)
- [ ] RAG documents remain authoritative for package/pricing/refund/cancellation/contract answers (SP-09)

---

## Security / Privacy Requirements

- [ ] PII (email/phone/secret) redacted before storage via 014/013 redactor; `pii_redacted` recorded (FR-004, SP-02, AC-03)
- [ ] Digest redacted again on read before reaching a prompt/response (SP-04)
- [ ] No raw PII/secrets/system prompts/JWTs/cross-tenant data in any response, log, or prompt (FR-018, SP-02, SP-04)
- [ ] Memory is temporary: TTL + `expires_at` + clearable; not stored forever (SP-03, AC-20)
- [ ] No cross-conversation bleed — one conversation's digest never informs another (SP-05)
- [ ] No autonomy — never auto-send / auto-create (SP-06, AC-11)
- [ ] Platform admin cannot read tenant memory by default (SP-07, AC-19)
- [ ] Memory read/refresh/clear/use audited (redacted ids/facts only) (SP-08, AC-17)

---

## Tenant Isolation Requirements

- [ ] Memory keys embed `tenant_id`; a `conversation_id` alone can't address another tenant's memory (FR-020, AC-18)
- [ ] Conversation resolved within the caller's tenant before any key is built; cross-tenant → 404 (FR-014, AC-14)
- [ ] Tenant A cannot read/derive Tenant B memory via any endpoint or internal call (FR-014, AC-14)
- [ ] Tenant A memory never mixes with Tenant B context in a digest or a prompt (SP-01, SP-05)

---

## API / Service Requirements

- [ ] `GET /api/conversations/{conversation_id}/memory` → redacted digest or cold/empty; tenant-scoped (AC-13)
- [ ] `POST /api/conversations/{conversation_id}/memory/refresh` → rebuild; `max_recent_messages` validated/clamped (FR-015)
- [ ] `DELETE /api/conversations/{conversation_id}/memory` → clear immediately; idempotent (FR-017, AC-16)
- [ ] Internal `memory.get_context` never raises; returns empty on cold/disabled/cache-down (FR-005, FR-016)
- [ ] Internal `memory.update_from_message` best-effort, non-blocking, no-op when disabled/down (FR-006, FR-016)
- [ ] Internal `memory.redact_and_summarize` returns `(summary, entries, pii_redacted)`; never raw PII (FR-007)
- [ ] All endpoints require an authenticated tenant user; platform admin → 403 (SP-07, AC-19)
- [ ] No PATCH/per-entry write routes; mutate attempts → 405; no reply/task/escalation side effects (SP-06)
- [ ] Error mapping: 401 auth, 403 platform-admin, 404 cross-tenant, 422 invalid params, 200-degraded on cache down

---

## Data Requirements

- [ ] No new Postgres tables; memory is Redis-only (cache schema documented) (AC-20)
- [ ] `ConversationMemory` document holds tenant_id, conversation_id, memory_key, summary, recent_message_refs, expires_at, updated_at, metadata
- [ ] `MemoryEntry` holds id, tenant_id, conversation_id, source_message_id (nullable), entry_type, content_summary, pii_redacted, created_at, expires_at, metadata
- [ ] `MemoryStatus` enum: active / expired / cleared / disabled
- [ ] `MemorySource` enum: inbound_message / outbound_message / summary / system_note
- [ ] Raw message bodies are referenced by id, never copied into the digest (SP-02, AC-20)
- [ ] New `memory_*` AuditEventType values added (string-backed, no enum migration) (013)

---

## Testing Requirements

- [ ] Unit: PII redacted + `pii_redacted=true`; summary length cap; ref cap (AC-02, AC-03)
- [ ] Unit: key format embeds tenant; cross-tenant key isolation (AC-18)
- [ ] Unit: cache error / feature off → empty context / no-op, no raise (AC-15)
- [ ] Unit: unverifiable claim tagged `verified:false` (AC-10)
- [ ] Integration: `update_from_message` writes tenant-scoped digest with ~7-day TTL + `expires_at` (AC-01, AC-05)
- [ ] Integration: `get_context` reference resolution for guest-count + deposit examples (AC-04, AC-07)
- [ ] Integration: suggested reply uses memory as supporting context; RAG queried + authoritative (AC-06); no invented price (AC-08); RAG-wins on conflict (AC-09)
- [ ] Integration: no auto-send / no task / no escalation from memory (AC-11); guardrails before + after (AC-12)
- [ ] Integration: GET/refresh/DELETE redacted + tenant-scoped (AC-13); cross-tenant → 404, key never built (AC-14); platform admin → 403 (AC-19)
- [ ] Integration: cache down / feature off → pipeline still works (AC-15); clear + TTL-expiry read cold (AC-16)
- [ ] Integration: memory actions audited (redacted) (AC-17); no Postgres persistence of raw memory (AC-20)
- [ ] Quickstart: all 7 steps (guest-count resolution, RAG-required, tenant isolation, expiry/clear, PII redaction)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No long-term / permanent memory or durable transcript
- [ ] No cross-conversation or cross-tenant memory
- [ ] No memory as a source of truth for package/price/refund/cancellation/contract (RAG is)
- [ ] No auto-sending replies
- [ ] No auto-creating tasks or escalations from memory
- [ ] No vector/semantic long-term memory store (pgvector is for documents, not conversation memory here)
- [ ] No CRM/personalization profiles or client history dossiers
- [ ] No storing raw PII or full message history (redacted, bounded digest only)
- [ ] No per-entry memory editing / manual fact authoring UI
- [ ] No real WhatsApp API, no calendar syncing, no billing/subscriptions

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order): config + Redis client → cache adapter → schemas/enums → redact+summarize → MemoryService → endpoints → RAG/reply integration → guardrail/grounding wiring → tests → quickstart validation.
- Hard guarantees to verify: (1) **tenant isolation** — keys embed `tenant_id`, conversation resolved within the caller's tenant, A never reads B; (2) **RAG is the source of truth** — memory is supporting context, RAG wins conflicts, no invented prices; (3) **temporary + minimized** — Redis TTL (7 days), redacted in + out, clearable, nothing stored forever; (4) **no autonomy** — never auto-send/auto-create; (5) **optional/degradable** — cache down/off → empty context, pipeline still works; (6) **auditable** — view/refresh/clear/use logged (redacted).
- This feature is an **enrichment layer** over 003–014: a Redis-backed memory service + three thin endpoints + one integration hook. It adds no permanent storage, no new required ingestion step, and no autonomous behavior.
