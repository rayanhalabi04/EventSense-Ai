# Feature Specification: Short-Term Conversation Memory

**Feature Branch**: `016-short-term-memory`

**Created**: 2026-06-08

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 007 — Risk Detection](../007-risk-detection/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 010 — Suggested Replies](../010-suggested-replies/spec.md)
- [Spec 011 — Follow-Up Tasks](../011-follow-up-tasks/spec.md)
- [Spec 012 — Escalation to Manager](../012-escalation-to-manager/spec.md)
- [Spec 013 — Audit Logs](../013-audit-logs/spec.md)
- [Spec 014 — Guardrails](../014-guardrails/spec.md)

**Input**: User description: "The system should maintain tenant-scoped short-term conversation memory so the AI can understand recent context in an ongoing client conversation, such as follow-up questions or references like 'that', 'the package', 'the guest count', or 'the deposit'. Memory should improve suggested replies but must remain safe, temporary, tenant-isolated, and human-reviewed."

---

## Goal

Give EventSense AI a **tenant-scoped, conversation-scoped, temporary short-term memory** so the AI can resolve recent references — "that", "the package", "the guest count", "the deposit", "it" — when generating suggested replies. Memory is a **supporting context layer**, never a source of truth: it stores a small, redacted, expiring digest of a conversation's recent turns (a rolling **summary** plus a bounded set of **recent message references**) in a fast cache (**Redis**, ~**7-day TTL**), and feeds that digest into RAG retrieval and suggested-reply generation (010) so follow-up questions are understood in context.

Memory **strengthens** the existing pipeline without changing its guarantees. **RAG documents (009) remain the source of truth** for package, pricing, refund, cancellation, and contract answers — if memory and RAG policy ever conflict, **RAG policy wins** and the AI must not invent unsupported facts. Memory **never** auto-sends a reply, **never** creates a task or escalation on its own, is **never** shared across tenants or conversations, **minimizes sensitive data** (PII redacted before storage, nothing kept forever), and every use is **auditable** (013). Guardrails (014) run **before** memory is built from input and **after** memory-assisted output is produced.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner/agent within a tenant. Benefits from better suggested replies that understand recent conversation context; can view, refresh, or clear a conversation's memory for conversations they may access. |
| **Manager** | A senior planner/manager within a tenant. Inherits Staff access; may review risky/escalated cases with the recent context attached. |
| **System / AI service** | Internal, non-human actor. Builds memory from new messages (redact + summarize), and retrieves recent context to enrich RAG queries and suggested-reply generation. Acts only within a single tenant + conversation; takes no autonomous side effects. |
| **Platform Admin** | Internal platform operator. **Cannot** read tenant conversation memory by default (no tenant content access), consistent with Spec 002. |

---

## User Stories

### User Story 1 — Follow-Up Reference Resolution Improves a Suggested Reply (Priority: P1)

A client writes, "We need to increase the guest count from 150 to 220," and later asks, "Will that affect the price?" When staff opens the second message and requests a suggested reply, the AI service retrieves the conversation's short-term memory, which records the earlier guest-count change. The reply generator now understands "that" refers to the guest-count increase. RAG (009) still retrieves the tenant's pricing/catering/package policy as the **source of truth**, and the suggested reply (010) combines the recent context ("you asked about increasing the guest count to 220") with the retrieved policy — **without inventing a price** the documents don't support.

**Why this priority**: This is the core value — resolving recent references so follow-up questions get coherent, grounded replies. Everything else exists to make this safe.

**Independent Test**: Seed a conversation with a guest-count-change message, then a "Will that affect the price?" message. Call the suggested-reply generation for the second message and assert the memory context (a) was retrieved tenant-and-conversation-scoped, (b) references the guest-count change, and (c) that the generated draft is still grounded in RAG sources (no price stated unless a source supports it).

**Acceptance Scenarios**:

1. **Given** a conversation with a prior "increase guest count 150→220" message, **When** a "Will that affect the price?" message is processed for a suggested reply, **Then** `memory.get_context` returns a digest mentioning the guest-count change, scoped to that tenant + conversation.
2. **Given** that memory context, **When** the reply is generated, **Then** RAG is still queried and the policy sources are used as the source of truth; memory is passed only as supporting context.
3. **Given** the tenant documents do not state a price for 220 guests, **When** the reply is generated, **Then** the draft does **not** invent a price (guardrail grounding from 014 still applies) and instead reflects what the sources support or asks to confirm.
4. **Given** Redis is unavailable, **When** the reply is generated, **Then** the pipeline still produces a (memory-less) grounded reply and the failure is handled gracefully (memory is optional, never blocking).

---

### User Story 2 — Memory Is Built Safely From New Messages (Redacted, Bounded, Expiring) (Priority: P1)

As messages arrive in a conversation, the system updates that conversation's short-term memory: it **redacts PII** (emails, phone numbers, secrets) from the captured content, **summarizes** the recent turns into a compact rolling summary, keeps only a **bounded** set of recent message references (not unlimited history), and stores the digest in Redis with a **7-day TTL** and an `expires_at`. Nothing sensitive is stored in raw form, and nothing is kept forever.

**Why this priority**: Memory that grows without bound or stores raw PII is a privacy and safety liability. Bounded, redacted, expiring storage is what makes the feature acceptable. Equal P1.

**Independent Test**: Post a message containing an email/phone, trigger `memory.update_from_message`, and assert the stored summary/entries are PII-redacted (`pii_redacted=true`, `[EMAIL_REDACTED]`/`[PHONE_REDACTED]`), the recent-message-ref count is capped at the configured maximum, and `expires_at` is ~7 days out.

**Acceptance Scenarios**:

1. **Given** a new inbound message with an email and phone number, **When** memory updates, **Then** the stored `summary`/`content_summary` contain redaction placeholders and no raw PII, and `pii_redacted=true`.
2. **Given** more than the configured maximum of recent messages, **When** memory updates, **Then** only the most recent N references are retained and older ones roll into/are dropped from the summary (bounded).
3. **Given** a memory write, **When** it is stored, **Then** `expires_at = now + MEMORY_TTL_SECONDS` (default 7 days) and the Redis key carries that TTL.
4. **Given** memory older than its TTL, **When** it is read, **Then** it is absent/expired (not returned) and treated as a cold start.

---

### User Story 3 — View, Refresh, and Clear Conversation Memory (Priority: P2)

Staff (and managers) can inspect a conversation's current short-term memory (the redacted summary + recent refs + expiry), **refresh** it (rebuild from the latest messages), and **clear** it (delete the memory immediately, e.g., on a privacy request or a stale context). All three operations are tenant-and-conversation scoped, audited, and side-effect-free beyond the memory itself (no replies/tasks/escalations created).

**Why this priority**: Operability and privacy controls (inspect/rebuild/forget) make the feature trustworthy and demonstrable, but the AI value (US1) and safe construction (US2) come first. P2.

**Independent Test**: As a tenant user, GET the memory for a conversation (assert redacted digest + expiry), POST refresh (assert the digest rebuilds from recent messages), DELETE it (assert it is gone and a subsequent GET shows empty/cold), and confirm each action wrote an audit entry; attempt the same on another tenant's conversation and assert 404/403.

**Acceptance Scenarios**:

1. **Given** a conversation with memory, **When** a tenant user GETs it, **Then** the redacted summary, bounded recent refs, `updated_at`, and `expires_at` are returned (no raw PII, no cross-tenant data).
2. **Given** new messages since the last build, **When** the user POSTs refresh, **Then** the memory is rebuilt (redact + summarize) and `updated_at` advances.
3. **Given** a memory, **When** the user DELETEs it, **Then** the Redis entry is removed immediately and a later GET returns an empty/cold memory.
4. **Given** any of these operations, **When** it completes, **Then** an audit entry (013) records the memory action (redacted), and a cross-tenant attempt is blocked (404/403).

---

### Edge Cases

- **Redis/cache unavailable**: memory is treated as empty; RAG + suggested replies still work (degraded but functional); the failure is logged, not surfaced as a hard error to the user (memory is optional, never on the critical path).
- **Cold conversation (no memory yet)**: `get_context` returns an empty digest; the reply is generated from the current message + RAG only.
- **Reference with no antecedent** ("Will that affect the price?" with no prior context): memory returns nothing relevant; the reply asks for clarification rather than guessing what "that" means.
- **Memory conflicts with RAG policy** (e.g., a client earlier said "you told me the deposit is refundable" but the policy doc says non-refundable): **RAG policy wins**; the draft follows the document and does not adopt the client's claim as fact.
- **Unverifiable claim in memory** ("I paid the deposit yesterday" → "Can you confirm it?"): memory resolves "it" = the deposit, but the system **must not** state the payment is confirmed unless verified by available data; it suggests checking/confirming instead.
- **PII slips through redaction**: the digest still passes the 014 redactor at read time before it reaches the prompt; any residual secret/PII is redacted, not sent to the model raw.
- **Very long conversation**: only the bounded recent window + rolling summary are kept; the summary is length-capped; older detail is intentionally forgotten.
- **Conversation spans > 7 days**: memory expires between sessions; on the next message it rebuilds from the recent window (no permanent transcript).
- **Wrong-tenant conversation id**: a conversation id that belongs to another tenant resolves to 404 (not found in caller's scope) — the memory key is never even constructed for it.
- **Memory key collision**: keys embed `tenant_id` + `conversation_id`; a `conversation_id` alone can never address another tenant's memory.
- **Disabled feature flag**: with memory disabled, the pipeline behaves exactly as 009/010 did before this feature (no context injected, endpoints return a disabled/empty state).
- **Concurrent updates**: two messages updating memory near-simultaneously converge on a bounded, consistent digest (last-write-wins on the rolling summary; refs deduplicated by message id).

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST maintain a **short-term memory per conversation**, scoped to the conversation's **tenant** and **conversation id**, derived from recent messages (003).
- **FR-002**: Memory MUST be stored in a **temporary cache (Redis or equivalent)** with a **TTL** (default **7 days** / `MEMORY_TTL_SECONDS`) and an explicit `expires_at`; nothing is stored permanently.
- **FR-003**: Memory MUST store a **bounded** digest — a rolling `summary` plus at most `MEMORY_MAX_RECENT_MESSAGES` recent message references — **not** unlimited full history.
- **FR-004**: Memory content MUST be **PII-minimized**: emails, phone numbers, and secrets are **redacted** (via the 014/013 redactor) before storage; `pii_redacted` is recorded; raw PII is never stored in the digest.
- **FR-005**: The system MUST expose an **internal** `memory.get_context(tenant_id, conversation_id)` that returns the redacted digest (or empty) for use by RAG (009) and suggested replies (010).
- **FR-006**: The system MUST expose an **internal** `memory.update_from_message(tenant_id, conversation_id, message_id)` that redacts + summarizes the latest messages and updates the digest (with refreshed TTL).
- **FR-007**: The system MUST expose an **internal** `memory.redact_and_summarize(...)` helper that produces the redacted, length-capped summary/entries from raw messages.
- **FR-008**: Suggested-reply generation (010) MUST pass memory context as **supporting context only**; RAG sources (009) remain the **source of truth** for package/pricing/refund/cancellation/contract answers.
- **FR-009**: When memory and RAG policy **conflict**, **RAG policy MUST win**; the AI MUST NOT adopt a memory-derived claim as an authoritative policy/price/contract fact.
- **FR-010**: The AI MUST NOT **invent** a price/policy/commitment that the RAG sources do not support, even when memory implies one (014 grounding still applies after memory use).
- **FR-011**: Memory MUST NOT **auto-send** any reply and MUST NOT **create** tasks (011) or escalations (012) by itself; it only supplies context to human-reviewed drafts.
- **FR-012**: **Guardrails (014) MUST apply before and after memory use**: input is checked before it informs memory; memory-assisted output is grounding/PII-checked before display.
- **FR-013**: Memory read/refresh/clear/use MUST be **auditable** via Spec 013 (redacted audit entries with conversation/tenant ids only).
- **FR-014**: Memory MUST be **tenant-isolated** and **conversation-isolated**: a request resolves the conversation within the caller's tenant first; Tenant A memory is never readable/derivable by Tenant B, and one conversation's memory never bleeds into another.
- **FR-015**: The system MUST provide `GET /api/conversations/{conversation_id}/memory` (inspect), `POST .../memory/refresh` (rebuild), and `DELETE .../memory` (clear) — all tenant-scoped and side-effect-free beyond memory.
- **FR-016**: Memory MUST be **optional/degradable**: if the cache is unavailable or the feature is disabled, RAG + suggested replies still function with no memory context (no hard failure).
- **FR-017**: Memory MUST be **clearable on demand** (DELETE) and MUST expire automatically at TTL; a cleared/expired memory reads as cold/empty.
- **FR-018**: Reads/refresh MUST return only **redacted** content; no endpoint or internal call exposes raw PII, secrets, system prompts, JWTs, or cross-tenant data.
- **FR-019**: Memory updates MUST be triggered **after** the basic message flow exists (003–005) and only enrich the **existing** RAG (009) + suggested-reply (010) steps; memory adds **no** new required step to message ingestion.
- **FR-020**: The Redis **key** for a conversation's memory MUST embed the `tenant_id` (e.g., `mem:{tenant_id}:{conversation_id}`) so a `conversation_id` alone can never address another tenant's memory.

### Key Entities

- **Tenant** (001): owns all memory; the isolation boundary; `tenant_id` is part of every key and every entry.
- **Conversation** (003): the scope of a memory digest (`conversation_id`).
- **Message** (003): the source material; recent messages are redacted/summarized into the digest; referenced by id.
- **ConversationMemory** (new, cache): the per-conversation digest — `memory_key`, `summary`, `recent_message_refs`, `expires_at`, `updated_at`, `metadata`.
- **MemoryEntry** (new, cache): a single redacted unit of memory (a recent-message ref or a salient fact) — `entry_type`, `content_summary`, `pii_redacted`, `source_message_id?`, `created_at`, `expires_at`, `metadata`.
- **MemoryStatus** (enum): `active`, `expired`, `cleared`, `disabled`.
- **MemorySource** (enum): `inbound_message`, `outbound_message`, `summary`, `system_note`.
- Consumed by: **RagQuery** (009) and **SuggestedReply** (010) as supporting context; **GuardrailDecision** (014) and **AuditLog** (013) as safety/oversight.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `user_id`, `role`, `tenant_id`; tenant is taken from the token, never the client |
| `conversation_id` | Path / internal call | The conversation whose memory is read/built/cleared; resolved within the caller's tenant |
| `message_id` | Internal trigger | The new message that updates memory (`update_from_message`) |
| Recent messages | `messages` (003) | The bounded recent window summarized/redacted into the digest |
| Memory config | Settings | `MEMORY_ENABLED`, `MEMORY_TTL_SECONDS` (default 604800), `MEMORY_MAX_RECENT_MESSAGES`, `MEMORY_SUMMARY_MAX_CHARS`, `REDIS_URL` |
| RAG sources | 009 | The source of truth that memory supports but never overrides |

---

## Outputs

| Output | Description |
|--------|-------------|
| Memory context (internal) | Redacted digest (`summary` + bounded `recent_message_refs`) for RAG/reply generation |
| Memory view (GET) | Redacted `summary`, recent refs, `updated_at`, `expires_at`, `status` |
| Refresh result (POST) | Rebuilt digest + new `updated_at`/`expires_at` |
| Clear result (DELETE) | Confirmation that memory was removed (now cold/empty) |
| Enriched suggested reply | A 010 draft that resolves recent references yet stays RAG-grounded |
| Audit entries | Redacted records of memory read/refresh/clear/use (013) |
| 401 / 403 | Unauthenticated / cross-tenant or platform-admin tenant-content access |
| 404 | Conversation not found in caller's tenant scope |
| 422 | Invalid `conversation_id` / params |
| 503-degraded (internal) | Cache unavailable → memory empty; pipeline still succeeds without it |

---

## Main Workflow

1. **A message arrives / is opened** in a conversation (003–005). The normal pipeline runs: classify (006), risk (007).
2. **Guardrails check the input** (014) **before** it informs memory.
3. **Memory updates** (`memory.update_from_message`): the recent window is **redacted + summarized** into the conversation's digest; the digest is written to Redis under `mem:{tenant_id}:{conversation_id}` with a 7-day TTL and `expires_at`.
4. **Suggested-reply generation (010) requests context**: `memory.get_context(tenant_id, conversation_id)` returns the redacted digest (or empty).
5. **RAG runs as usual (009)** — tenant-scoped retrieval is the **source of truth**; memory is added only as **supporting context** to the prompt.
6. **The reply is generated** resolving recent references (e.g., "that" = the guest-count change) but **grounded** in RAG sources.
7. **Guardrails check the output** (014) **after** memory use: grounding + PII redaction; an ungrounded/invented claim is refused/flagged.
8. **The human reviews** the draft (010) — nothing is auto-sent; no task/escalation is auto-created.
9. **Audit (013)** records the memory use (redacted).
10. **Memory expires** at TTL (or is cleared on demand); a cold conversation simply rebuilds from the recent window next time.

Memory is never a required step in ingestion and never blocks the pipeline; if it is unavailable, steps 4–6 proceed with empty context.

---

## Alternative Workflows

### Inspect / Refresh / Clear (operator actions)

1. A tenant user GETs `/api/conversations/{id}/memory` → redacted digest + expiry (or cold/empty).
2. POSTs `/memory/refresh` → memory rebuilt from the latest recent window (redact + summarize); `updated_at` advances.
3. DELETEs `/memory` → the Redis entry is removed; later GET reads cold; an audit entry is written.

### Unverifiable Claim ("Can you confirm it?")

1. Earlier: "I paid the deposit yesterday." Later: "Can you confirm it?"
2. `get_context` resolves "it" = the deposit.
3. The reply suggests **checking/confirming** the payment; it does **not** assert the payment is confirmed unless verified by available data (no fabricated confirmation).

### Memory–Policy Conflict (RAG wins)

1. Memory holds a client claim ("you said the deposit is refundable").
2. RAG policy says deposits are non-refundable.
3. The draft follows the **document**; memory does not override policy; grounding (014) blocks adopting the client's claim as fact.

### Degraded Cache

1. Redis is down when a reply is requested.
2. `get_context` returns empty; RAG + reply proceed memory-less; the cache error is logged (not shown as a user error).

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Memory is stored per conversation, tenant-scoped, in Redis with a 7-day TTL and `expires_at` | Integration: update → assert key `mem:{tenant}:{conv}`, TTL ≈ 604800, `expires_at` set |
| AC-02 | Digest is bounded: ≤ `MEMORY_MAX_RECENT_MESSAGES` refs + a length-capped rolling summary | Integration: post N+ messages → assert ref cap + summary length |
| AC-03 | PII redacted before storage; `pii_redacted=true`; no raw email/phone/secret in the digest | Integration: PII message → assert placeholders only |
| AC-04 | `memory.get_context` returns the redacted digest scoped to tenant + conversation (or empty) | Unit/integration |
| AC-05 | `memory.update_from_message` redacts+summarizes recent messages and refreshes TTL | Integration |
| AC-06 | Suggested reply (010) receives memory as supporting context; RAG (009) remains source of truth | Integration: assert RAG queried; memory passed as context only |
| AC-07 | Reference resolution works: "that"/"it"/"the package" map to the recent antecedent | Integration: guest-count + deposit examples |
| AC-08 | AI does not invent a price/policy the sources don't support, even with memory present | Integration: no-source price → draft has no invented price (014 grounding) |
| AC-09 | Memory–RAG conflict → RAG policy wins | Integration: contradictory memory vs policy → draft follows policy |
| AC-10 | Unverifiable claim → no false confirmation; suggests checking instead | Integration: deposit "confirm it?" example |
| AC-11 | Memory never auto-sends a reply or auto-creates a task/escalation | Integration: assert no 010 send / 011 / 012 side effects |
| AC-12 | Guardrails (014) run before memory build and after memory-assisted output | Integration: assert input + output checks present |
| AC-13 | GET/POST-refresh/DELETE memory endpoints work, tenant-scoped, redacted | Integration |
| AC-14 | Cross-tenant memory access blocked: Tenant A cannot read/derive Tenant B memory | Integration: A → B conversation → 404/403; key never built |
| AC-15 | Memory is optional: cache down or `MEMORY_ENABLED=false` → pipeline still works, no hard error | Integration: disable Redis → reply still generated |
| AC-16 | Memory clearable (DELETE) and auto-expires at TTL; cleared/expired reads cold | Integration |
| AC-17 | Memory read/refresh/clear/use audited (redacted) via 013 | Integration: assert audit entries, no raw PII |
| AC-18 | Redis key embeds `tenant_id`; a `conversation_id` alone can't address another tenant's memory | Unit: key format + isolation |
| AC-19 | Platform admin cannot read tenant memory by default | Integration: admin → 403 |
| AC-20 | Nothing stored forever: no permanent transcript; only the expiring digest exists | Code/design: no Postgres persistence of raw memory |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenant isolation boundary; `tenant_id` in every key/entry |
| Spec 002 — Authentication and Roles | Required | Tenant/role from JWT; platform admin excluded from tenant memory |
| Spec 003 — Message Simulator | Required | `conversations`/`messages` are the source material |
| Spec 004 — Message Inbox / 005 — Detail | Required | The basic flow memory enriches must already exist |
| Spec 006 — Intent Classifier / 007 — Risk | Used | Intent/risk available alongside memory context for the prompt |
| Spec 009 — RAG Over Tenant Documents | Required | **Source of truth**; memory is supporting context, never an override |
| Spec 010 — Suggested Replies | Required | The consumer of memory context; human-reviewed, never auto-sent |
| Spec 011 — Tasks / 012 — Escalation | Required (negative) | Memory must NOT auto-create these |
| Spec 013 — Audit Logs | Required | Memory actions/use are audited (redacted) |
| Spec 014 — Guardrails | Required | Redaction + grounding before/after memory use |
| Redis (new infra) | Required | Temporary cache backing the digest with TTL |

This feature is an **enrichment layer** over 003–014: it adds a cache-backed memory service, three thin endpoints, and an integration hook into RAG/reply generation. It changes no policy source, adds no autonomous behavior, and adds no permanent storage.

---

## Memory Behavior

- **Tenant- and conversation-scoped**: every digest belongs to exactly one `(tenant_id, conversation_id)`; keys embed the tenant; reads resolve the conversation within the caller's tenant first (FR-001, FR-014, FR-020).
- **Temporary**: Redis-backed, default **7-day TTL**, explicit `expires_at`; expired/cleared memory reads cold; nothing is stored forever (FR-002, FR-017, AC-20).
- **Bounded + redacted**: a rolling, length-capped `summary` + ≤ N recent refs; PII/secrets redacted before storage (FR-003, FR-004).
- **Supporting, not authoritative**: memory enriches RAG/reply prompts; **RAG remains the source of truth**; on conflict, RAG wins (FR-008, FR-009).
- **Optional/degradable**: cache down or feature off → empty context, pipeline still works (FR-016, AC-15).
- **Audited**: read/refresh/clear/use recorded (redacted) (FR-013).

## AI Behavior

- **Resolves recent references** ("that", "it", "the package", "the guest count", "the deposit") using the digest (AC-07).
- **Stays grounded**: never invents a price/policy/commitment the sources don't support, even when memory implies one (FR-010, AC-08).
- **Never fabricates confirmations**: an unverifiable claim ("I paid the deposit") yields a "let's check/confirm" reply, not a false "payment confirmed" (AC-10).
- **Human-in-the-loop**: memory only supplies context to a **drafted** reply; no auto-send, no auto task/escalation (FR-011, AC-11).
- **Guardrailed**: input checked before memory build; output grounding/PII-checked after memory use (FR-012, AC-12).

---

## Security / Privacy Rules

| Rule | Description |
|------|-------------|
| **SP-01: Tenant isolation absolute** | Memory keys embed `tenant_id`; a conversation resolves within the caller's tenant first; Tenant A memory is never readable/derivable by Tenant B (FR-014, FR-020, AC-14, AC-18). |
| **SP-02: PII minimized before storage** | Emails/phones/secrets are redacted (014/013 redactor) before any digest is written; `pii_redacted` recorded; raw PII never persisted (FR-004, AC-03). |
| **SP-03: Temporary by design** | TTL (default 7 days) + `expires_at`; no permanent transcript; clearable on demand; expired/cleared reads cold (FR-002, FR-017, AC-20). |
| **SP-04: Redacted on read** | The digest passes the redactor again at read time before it reaches a prompt or a response (FR-018). |
| **SP-05: No cross-conversation bleed** | One conversation's digest never informs another; refs are keyed to the conversation (FR-014). |
| **SP-06: No autonomy** | Memory never auto-sends a reply or auto-creates a task/escalation (FR-011, AC-11). |
| **SP-07: Platform admin excluded** | Platform admin cannot read tenant memory by default (Spec 002) (FR-014, AC-19). |
| **SP-08: Auditable** | Memory read/refresh/clear/use is audited (redacted ids/facts only) (FR-013, AC-17). |
| **SP-09: Not a policy source** | Memory is never the basis for a package/price/refund/cancellation/contract answer; RAG documents are (FR-008, FR-009). |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Redis/cache unavailable | `get_context` returns empty; RAG + reply proceed memory-less; error logged, not user-facing (FR-016, AC-15) |
| Feature disabled (`MEMORY_ENABLED=false`) | No context injected; endpoints return disabled/empty; pipeline = pre-016 behavior |
| Cross-tenant conversation id | 404 (not in caller's scope); key never constructed (SP-01, AC-14) |
| Platform admin reads tenant memory | 403 (no tenant content access) (SP-07, AC-19) |
| PII residue in a captured message | Redacted before storage and again at read; `pii_redacted=true` (SP-02, SP-04) |
| Memory contradicts RAG policy | RAG policy wins; draft follows the document (FR-009, AC-09) |
| Reference with no antecedent | Empty/irrelevant context; reply asks to clarify, doesn't guess (Edge cases) |
| Unverifiable client claim | No fabricated confirmation; suggests checking (AC-10) |
| Memory expired/cleared | Reads cold; rebuilds from the recent window next time (FR-017, AC-16) |
| Invalid conversation_id / params | 422 validation |

---

## Edge Cases (summary)

- Cache down / feature off → empty memory, pipeline still works.
- Cold conversation → empty digest, reply from current message + RAG.
- Reference with no antecedent → ask to clarify, don't guess.
- Memory vs RAG conflict → RAG wins.
- Unverifiable claim → suggest checking, never falsely confirm.
- PII residue → redacted before storage and at read.
- Long conversation → bounded window + length-capped summary; older detail forgotten.
- > 7 days → expires; rebuilds from recent window.
- Wrong-tenant conversation id → 404; key never built.
- Concurrent updates → bounded, consistent digest (last-write-wins summary; refs deduped by id).

---

## Out of Scope

- **Long-term / permanent memory** — no durable transcript, profile memory, or cross-conversation client history; memory is short-term and expiring only.
- **Cross-conversation or cross-tenant memory** — strictly one tenant + one conversation per digest.
- **Memory as a source of truth** — never authoritative for package/pricing/refund/cancellation/contract answers; RAG documents are.
- **Auto-sending replies** — memory only enriches human-reviewed drafts (010); nothing is auto-sent.
- **Auto-creating tasks/escalations** — memory never triggers 011/012 on its own.
- **Vector/semantic long-term memory store** — short-term cache only; pgvector (009) is for tenant documents, not conversation memory in this MVP.
- **Personalization/CRM profiles** — no client preference profiles, history dossiers, or marketing memory; full CRM is out of scope.
- **Real WhatsApp API, calendar syncing, billing/subscriptions** — out of scope entirely.
- **Storing raw PII or full message history** — only a redacted, bounded, expiring digest is stored.
- **Memory editing UI / manual fact authoring** — operators may inspect/refresh/clear, not hand-edit individual memory facts in the MVP.

---

## Assumptions

- The basic message flow (003–005), RAG (009), and suggested replies (010) already exist; memory only enriches them.
- Redis (or an equivalent temporary cache) is available; if not, memory is simply empty and the system degrades gracefully.
- The default TTL is **7 days** (`MEMORY_TTL_SECONDS=604800`), tunable via config; the recent-ref cap and summary length are configurable.
- Memory stores a **redacted, bounded** digest (rolling summary + recent refs), never raw full history and never raw PII.
- RAG documents remain the **source of truth**; memory is supporting context and loses any conflict with policy.
- Memory takes **no autonomous action** (no auto-send, no task/escalation) and every use is auditable.
- Tenant + role come from the JWT; platform admin has no tenant memory access by default.
- Memory is **not** a required step in message ingestion; it is an optional enrichment of the existing RAG/reply step.
