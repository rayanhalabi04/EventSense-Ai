# API Contracts: Short-Term Conversation Memory

**Branch**: `016-short-term-memory` | **Phase**: 1 — Design

**Auth (all HTTP endpoints)**: Bearer JWT. `tenant_id`, `user_id`, and `role` are derived from the token — **never** from the client. All three endpoints require an authenticated **tenant user** (staff/manager); **platform admin is forbidden** from tenant memory by default (403). The `conversation_id` is resolved **within the caller's tenant first** (404 if it belongs to another tenant — consistent with Specs 005–014); the Redis key is **never constructed** for a cross-tenant conversation. Every read/refresh/clear is **side-effect-free beyond the memory itself** (no replies sent, no tasks/escalations created) and is **audited** (013, redacted). **No endpoint ever returns raw PII, secrets, system prompts, JWTs, or cross-tenant data** — the digest is redacted before storage and again on read. Memory is **optional/degradable**: if the cache is unavailable or `MEMORY_ENABLED=false`, reads return an empty `disabled` digest with **200** (never a 5xx).

---

## 1. GET /api/conversations/{conversation_id}/memory

Return the conversation's current short-term memory digest (redacted), or a cold/empty digest if none exists. **Tenant user (staff/manager).**

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `conversation_id` | UUID | The conversation whose memory is read (resolved within the caller's tenant). |

**Request body**: none.

**Response 200** (active memory):
```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "conversation_id": "c0000000-0000-0000-0000-000000000001",
  "memory_key": "mem:11111111-1111-1111-1111-111111111111:c0000000-0000-0000-0000-000000000001",
  "status": "active",
  "summary": "Client wants to raise the guest count from 150 to 220 and is asking whether that affects pricing. Client also claims the deposit was paid yesterday (unverified).",
  "recent_message_refs": [
    {
      "id": "e1000000-0000-0000-0000-000000000010",
      "source_message_id": "m0000000-0000-0000-0000-000000000003",
      "entry_type": "salient_fact",
      "content_summary": "Client asked to increase guest count 150 -> 220.",
      "pii_redacted": false,
      "source": "inbound_message",
      "created_at": "2026-06-08T10:00:00Z",
      "expires_at": "2026-06-15T10:00:00Z",
      "metadata": { "anchor": "guest_count", "from": 150, "to": 220 }
    },
    {
      "id": "e1000000-0000-0000-0000-000000000011",
      "source_message_id": "m0000000-0000-0000-0000-000000000005",
      "entry_type": "salient_fact",
      "content_summary": "Client claims deposit paid yesterday (unverified).",
      "pii_redacted": true,
      "source": "inbound_message",
      "created_at": "2026-06-08T10:02:00Z",
      "expires_at": "2026-06-15T10:00:00Z",
      "metadata": { "fact": "deposit_paid", "verified": false }
    }
  ],
  "updated_at": "2026-06-08T10:02:00Z",
  "expires_at": "2026-06-15T10:00:00Z",
  "metadata": { "pii_redacted": true, "entry_count": 2, "unverified_claims": ["deposit_paid"] }
}
```

**Response 200** (cold / cleared / expired / disabled):
```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "conversation_id": "c0000000-0000-0000-0000-000000000001",
  "memory_key": "mem:11111111-...:c0000000-...",
  "status": "disabled",
  "summary": "",
  "recent_message_refs": [],
  "updated_at": null,
  "expires_at": null,
  "metadata": {}
}
```
> `status` is one of `active` / `expired` / `cleared` / `disabled` (derived at read time). A missing key after a known clear → `cleared`; otherwise cold → `expired`; feature off / cache down → `disabled`.

**Validation rules**:
- `conversation_id` must be a UUID (else 422) and must belong to the caller's tenant (else 404).
- The response is **always redacted** — `summary`/`content_summary` contain placeholders (`[EMAIL_REDACTED]`, `[PHONE_REDACTED]`) where PII was present, never raw values.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform admin / role without tenant-content access | `TENANT_CONTENT_FORBIDDEN` |
| 404 | Conversation not in the caller's tenant | `CONVERSATION_NOT_FOUND` |
| 422 | `conversation_id` not a UUID | validation detail |

---

## 2. POST /api/conversations/{conversation_id}/memory/refresh

Rebuild the conversation's memory from its latest messages (redact + summarize), refresh the TTL, and return the new digest summary. **Tenant user (staff/manager).** Idempotent in effect (last-write-wins).

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `conversation_id` | UUID | The conversation to rebuild memory for. |

**Request body** (optional):
```json
{ "max_recent_messages": 10 }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_recent_messages` | int | no | Override the recent-window size for this rebuild (1 ≤ n ≤ `MEMORY_MAX_RECENT_MESSAGES`); default = config |

**Response 200**:
```json
{
  "conversation_id": "c0000000-0000-0000-0000-000000000001",
  "status": "active",
  "updated_at": "2026-06-08T10:05:00Z",
  "expires_at": "2026-06-15T10:05:00Z",
  "entry_count": 2
}
```

**Response 200** (feature off / cache down):
```json
{ "conversation_id": "c0000000-...", "status": "disabled", "updated_at": null, "expires_at": null, "entry_count": 0 }
```

**Validation rules**:
- `conversation_id` must be a UUID and in the caller's tenant.
- `max_recent_messages`, if provided, must be `1 ≤ n ≤ MEMORY_MAX_RECENT_MESSAGES` (else 422); larger requests are clamped/rejected so the digest stays bounded (FR-003).
- The rebuilt digest is redacted; raw PII/secrets are never stored or returned.
- Refresh creates/updates **only** the memory digest — it sends no reply and creates no task/escalation (SP-06).

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform admin / no tenant-content access | `TENANT_CONTENT_FORBIDDEN` |
| 404 | Conversation not in the caller's tenant | `CONVERSATION_NOT_FOUND` |
| 422 | Invalid `conversation_id` / `max_recent_messages` out of range | validation detail |

---

## 3. DELETE /api/conversations/{conversation_id}/memory

Clear (delete) the conversation's memory digest immediately (e.g., a privacy request or stale context). **Tenant user (staff/manager).** Idempotent — clearing an already-empty memory still succeeds.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `conversation_id` | UUID | The conversation whose memory is cleared. |

**Request body**: none.

**Response 200**:
```json
{ "conversation_id": "c0000000-0000-0000-0000-000000000001", "cleared": true, "status": "cleared" }
```
> A later GET returns a cold/empty digest. Clearing is immediate (Redis `DEL` on both the document and entries keys). `cleared` is `true` whether or not a key existed (idempotent).

**Validation rules**:
- `conversation_id` must be a UUID and in the caller's tenant.
- Clearing removes **only** the memory; it never deletes messages, replies, tasks, escalations, or audit logs.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform admin / no tenant-content access | `TENANT_CONTENT_FORBIDDEN` |
| 404 | Conversation not in the caller's tenant | `CONVERSATION_NOT_FOUND` |
| 422 | `conversation_id` not a UUID | validation detail |

---

## Internal Service Contracts (not HTTP)

These are in-process functions on `MemoryService`, called by the RAG/suggested-reply step (010) and the message path (003–005). They are **not** exposed as routes. All are tenant-scoped and never raise on cache errors (graceful degradation).

### 4. `memory.get_context(tenant_id, conversation_id) -> MemoryContext`

Return the redacted memory context for a conversation, or an **empty** context when cold/disabled/cache-down.

**Inputs**:

| Arg | Type | Description |
|-----|------|-------------|
| `tenant_id` | UUID | from the authenticated caller (already trusted) |
| `conversation_id` | UUID | the conversation scope |

**Returns** (`MemoryContext`):
```json
{
  "conversation_id": "c0000000-...",
  "summary": "Client wants guest count 150 -> 220 and asks if that affects pricing. Deposit-paid claim is unverified.",
  "recent_refs": ["guest count 150 -> 220", "deposit paid (unverified)"],
  "anchors": { "that": "guest_count 150->220", "it": "deposit (unverified)" },
  "is_empty": false
}
```

**Behavior / rules**:
- Reads `mem:{tenant_id}:{conversation_id}`; redacts on read (SP-04); returns `is_empty=true` if missing/disabled/cache error.
- **Never raises** to the caller; a cache failure yields an empty context (FR-016).
- Returned content is **supporting context only** — the reply generator must keep RAG sources (009) authoritative (FR-008, FR-009).
- Caller is responsible for having already established `tenant_id` from the JWT; `get_context` does not re-resolve auth but only ever touches the tenant-embedded key.

### 5. `memory.update_from_message(tenant_id, conversation_id, message_id) -> None`

Update the conversation digest from the latest messages (redact + summarize), writing it to Redis with a refreshed TTL. **Best-effort**, called after a message is stored/opened.

**Inputs**:

| Arg | Type | Description |
|-----|------|-------------|
| `tenant_id` | UUID | authenticated tenant |
| `conversation_id` | UUID | the conversation scope |
| `message_id` | UUID | the new message that triggered the update |

**Behavior / rules**:
- Loads the bounded recent window (most-recent `MEMORY_MAX_RECENT_MESSAGES`), runs `redact_and_summarize`, and `write_memory` with `EX MEMORY_TTL_SECONDS` (FR-006, AC-05).
- No-op when `MEMORY_ENABLED=false` or the cache is unavailable (FR-016); never blocks ingestion (FR-019).
- Writes **only** the digest — no reply/task/escalation (SP-06). Raw bodies are never stored (SP-02).
- Returns nothing; failures are logged best-effort and swallowed.

### 6. `memory.redact_and_summarize(messages) -> (summary, entries, pii_redacted)`

Produce the redacted, length-capped summary + bounded entries from raw messages. Pure/deterministic (MVP); shared by `update_from_message` and `refresh`.

**Inputs**:

| Arg | Type | Description |
|-----|------|-------------|
| `messages` | list[Message] | the recent window (most-recent N, ordered) |

**Returns**:

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | redacted rolling summary, ≤ `MEMORY_SUMMARY_MAX_CHARS` |
| `entries` | list[MemoryEntry] | redacted, bounded (≤ `MEMORY_MAX_RECENT_MESSAGES`); anchors + unverified-claim tags |
| `pii_redacted` | bool | `true` if any PII/secret was redacted |

**Behavior / rules**:
- Step 1: each `body` → 014 `redact_text` (PII + secrets + prompt markers) (SP-02).
- Step 2: build the rolling summary (length-capped) preserving reference anchors ("that"/"it"/"the package"/"the guest count"/"the deposit") (AC-07).
- Step 3: build entries; tag unverifiable claims `verified=false` so replies never fabricate a confirmation (AC-10).
- **Never** returns raw PII; `pii_redacted` reflects whether redaction occurred.

---

## No Other Mutating Endpoints

Memory has no create/update endpoint beyond `refresh` and no per-entry edit/delete; operators **inspect, rebuild, or clear** a conversation's memory — they do not hand-author individual facts (MVP scope).

| Attempted method | Result |
|------------------|--------|
| `PATCH /api/conversations/{id}/memory` | 405 `METHOD_NOT_ALLOWED` (no route) |
| `POST /api/conversations/{id}/memory/entries` | 405 `METHOD_NOT_ALLOWED` (no route) |
| Any memory write that sends a reply / creates a task / escalation | not possible — no such code path (SP-06) |

---

## Cross-Cutting Behaviour

| Scenario | HTTP / result | Side effect |
|----------|---------------|-------------|
| Tenant user GETs own conversation memory | 200 redacted digest | audit `memory_viewed` |
| Tenant user POSTs refresh | 200 rebuilt summary | digest rewritten + TTL; audit `memory_refreshed` |
| Tenant user DELETEs memory | 200 `cleared` | Redis key removed; audit `memory_cleared` |
| Cross-tenant `conversation_id` | 404 | none; key never built (SP-01) |
| Platform admin reads tenant memory | 403 | none (SP-07) |
| Cache unavailable / `MEMORY_ENABLED=false` (read/refresh) | 200 `disabled` empty | none (FR-016) |
| Reply generation uses memory | (internal) | RAG still authoritative; output grounded (014); audit `memory_used_in_reply` |
| Memory implies a price the docs don't support | (internal) | grounding (014) blocks the invented price (AC-08) |
| Memory contradicts RAG policy | (internal) | RAG policy wins (AC-09) |
| Unverifiable claim ("confirm it?") | (internal) | reply suggests checking; no false confirmation (AC-10) |

---

## Role Matrix

| Endpoint | staff | manager | platform_admin |
|----------|-------|---------|----------------|
| GET /api/conversations/{id}/memory | ✅ | ✅ | ❌ 403 |
| POST /api/conversations/{id}/memory/refresh | ✅ | ✅ | ❌ 403 |
| DELETE /api/conversations/{id}/memory | ✅ | ✅ | ❌ 403 |

> Access is further limited to conversations within the caller's tenant (404 otherwise). Staff/manager access follows the same conversation-scoping as the message detail page (005). Platform admin has no tenant-content access by default (002).

---

## Non-Goals (contract-level)

These endpoints/contracts never: add a required step to message ingestion (memory is best-effort enrichment); auto-send a reply or auto-create a task/escalation (SP-06); use memory as a source of truth for package/price/refund/cancellation/contract answers (RAG is — FR-008/FR-009); return raw PII, secrets, system prompts, JWTs, or cross-tenant data (redacted in + out); persist raw memory to Postgres or keep it past TTL (ephemeral only); or expose another tenant's memory (tenant-embedded keys + scope resolution). Long-term memory, cross-conversation memory, CRM profiles, real WhatsApp API, and calendar syncing are **out of scope**.
