# Data Model: Short-Term Conversation Memory

**Branch**: `016-short-term-memory` | **Phase**: 1 — Design

---

## Schema Changes

**No new Postgres tables.** Short-term memory is **ephemeral by design** (default 7-day TTL) and lives in **Redis** (FR-002, SP-03, AC-20). This document defines the **cache document schema** (`ConversationMemory`, `MemoryEntry`) and the **in-process Pydantic shapes** used by the service/endpoints — not SQL DDL. The only existing-table touch is additive: the Spec 013 audit writer accepts new string-backed `memory_*` event types (no enum-altering migration). `tenants`, `conversations`, and `messages` (001/003) are used as-is and are never modified.

> Why no table: persisting memory to Postgres would create a durable transcript and an over-retention risk the spec forbids. Redis TTLs give automatic expiry; the digest is small, bounded, redacted, and disposable.

---

## Enums

### `MemoryStatus`

```python
class MemoryStatus(str, Enum):
    active   = "active"     # a live digest exists and has not expired
    expired  = "expired"    # TTL elapsed; reads return cold/empty
    cleared  = "cleared"    # explicitly deleted (DELETE) before TTL
    disabled = "disabled"   # MEMORY_ENABLED=false or cache unavailable (degraded)
```

`status` is **derived at read time**, not stored as mutable state: a present non-expired key → `active`; a missing key after a known clear → `cleared`; a missing key otherwise (or TTL elapsed) → `expired`/cold; feature off / cache down → `disabled`. It exists so the API and dashboard can show *why* a memory is empty.

### `MemorySource`

```python
class MemorySource(str, Enum):
    inbound_message  = "inbound_message"   # derived from a client (inbound) message
    outbound_message = "outbound_message"  # derived from a staff/AI (outbound) message
    summary          = "summary"           # a rolling-summary-derived salient fact/anchor
    system_note      = "system_note"        # a system-tagged note (e.g., "deposit_paid: unverified")
```

`MemorySource` records **where a memory unit came from** so reference anchors and unverified claims are traceable without storing raw bodies. It aligns with `messages.direction` (003: `inbound`/`outbound`) for message-derived entries.

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `Tenant` (001) | the isolation boundary; `tenant_id` is part of every Redis key and every entry (SP-01) |
| `Conversation` (003) | the scope of a digest (`conversation_id`); resolved within the caller's tenant before any key is built |
| `Message` (003) | the source material; the bounded recent window is redacted/summarized; referenced by `id` (never copied raw) |
| `RagQuery`/sources (009) | the **source of truth** memory supports but never overrides |
| `SuggestedReply` (010) | the consumer of memory context (human-reviewed, never auto-sent) |
| `GuardrailDecision` (014) | redaction (`redact_text`) + grounding (`validate_rag_grounding`) before/after memory use |
| `AuditLog` (013) | redacted records of `memory_viewed`/`memory_refreshed`/`memory_cleared`/`memory_used_in_reply` |

All references are **loose** (ids only); memory rows own nothing and cascade nothing.

---

## Entity: `Tenant` (existing — 001)

The isolation root. Relevant invariants for memory:

| Field | Type | Note |
|-------|------|------|
| `id` | UUID | embedded as the first segment of every memory key (`mem:{tenant_id}:…`) |

A `tenant_id` mismatch between the JWT and a conversation's owner is a **404** (cross-tenant) and never reaches Redis.

## Entity: `Conversation` (existing — 003)

| Field | Type | Note |
|-------|------|------|
| `id` | UUID | the `conversation_id` scope of a digest |
| `tenant_id` | UUID | must equal the JWT tenant before a key is built (isolation guard) |
| `status` | enum | `open`/`closed`/`escalated` (003); memory is read/built regardless but never changes it |

## Entity: `Message` (existing — 003)

| Field | Type | Note |
|-------|------|------|
| `id` | UUID | referenced by `MemoryEntry.source_message_id` and in `recent_message_refs` |
| `conversation_id` | UUID | the recent window is selected per conversation |
| `tenant_id` | UUID | redundant tenant guard |
| `direction` | enum | `inbound`/`outbound` → maps to `MemorySource` |
| `body` | TEXT | read transiently to redact+summarize; **never copied raw** into the digest |
| `created_at` | TIMESTAMPTZ | orders the recent window (most-recent N) |

---

## New Entity (cache): `ConversationMemory`

The per-conversation digest. **Stored in Redis** under `mem:{tenant_id}:{conversation_id}` as a JSON document with a TTL equal to `MEMORY_TTL_SECONDS` (default **604800** = 7 days).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `tenant_id` | UUID | required | isolation owner; also encoded in the key (SP-01) |
| `conversation_id` | UUID | required | the conversation this digest belongs to |
| `memory_key` | string | required | the Redis key `mem:{tenant_id}:{conversation_id}` (self-describing) |
| `summary` | string | redacted, length-capped (`MEMORY_SUMMARY_MAX_CHARS`) | rolling summary of salient facts/anchors (PII-free) |
| `recent_message_refs` | array | bounded (`MEMORY_MAX_RECENT_MESSAGES`) | most-recent message references (ids + redacted `content_summary` + source) |
| `expires_at` | datetime (ISO) | required | `now + MEMORY_TTL_SECONDS`; mirrors the Redis TTL (FR-002) |
| `updated_at` | datetime (ISO) | required | last rebuild time; advances on `update_from_message`/`refresh` |
| `metadata` | object (JSON) | default `{}` | redacted facts only — e.g., `{ "pii_redacted": true, "entry_count": 6, "source_message_count": 6, "unverified_claims": ["deposit_paid"] }` — never raw PII/prompts/cross-tenant data |

**Redis representation**:
- Key: `mem:{tenant_id}:{conversation_id}` → JSON-serialized `ConversationMemory`.
- TTL: `EX MEMORY_TTL_SECONDS` set on **every** write (FR-002, AC-01).
- A missing key reads as a **cold/empty** digest (status `expired`/`cleared`/`disabled` per Decision in enums).

**Invariants**:
- `summary` and every `recent_message_refs[].content_summary` are **redacted** (no raw email/phone/secret) — `metadata.pii_redacted` reflects whether any redaction occurred.
- `len(recent_message_refs) ≤ MEMORY_MAX_RECENT_MESSAGES`; `len(summary) ≤ MEMORY_SUMMARY_MAX_CHARS` (FR-003, AC-02).
- `tenant_id` always matches the key's first segment and the caller's JWT tenant (SP-01).

---

## New Entity (cache): `MemoryEntry`

A single redacted unit of memory — a recent-message reference or a salient/system fact. **Stored in Redis** as elements of a bounded list under `mem:{tenant_id}:{conversation_id}:entries` (capped via `LPUSH` + `LTRIM`), and/or inlined as `recent_message_refs` in the document.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | required | stable entry id |
| `tenant_id` | UUID | required | isolation owner |
| `conversation_id` | UUID | required | the conversation scope |
| `source_message_id` | UUID \| null | nullable | the message this entry was derived from (null for summary/system entries) |
| `entry_type` | string (`MemoryEntryType`) | required | `recent_message` / `rolling_summary` / `salient_fact` / `reference_anchor` |
| `content_summary` | string | redacted, length-bounded | the redacted gist (e.g., "client asked to raise guest count 150→220") — **never** raw body |
| `pii_redacted` | boolean | required | `true` if any PII/secret was redacted from the source content |
| `source` | string (`MemorySource`) | required | `inbound_message` / `outbound_message` / `summary` / `system_note` |
| `created_at` | datetime (ISO) | required | when the entry was built |
| `expires_at` | datetime (ISO) | required | `now + MEMORY_TTL_SECONDS`; matches the list-key TTL |
| `metadata` | object (JSON) | default `{}` | redacted facts only — e.g., `{ "anchor": "guest_count", "from": 150, "to": 220 }` or `{ "fact": "deposit_paid", "verified": false }` |

### `MemoryEntryType` (supporting enum)

```python
class MemoryEntryType(str, Enum):
    recent_message   = "recent_message"     # a redacted reference to a recent message
    rolling_summary  = "rolling_summary"    # the compact summary unit
    salient_fact     = "salient_fact"       # an extracted fact/anchor ("guest count 150→220")
    reference_anchor = "reference_anchor"   # an antecedent for "that"/"it"/"the package"/"the deposit"
```

**Invariants**:
- `content_summary` is always redacted; raw message bodies are never stored.
- `pii_redacted=true` whenever redaction occurred; the digest's `metadata.pii_redacted` is the OR of its entries.
- The entries list is bounded to `MEMORY_MAX_RECENT_MESSAGES` (recent-message entries); summary/anchor entries are folded into the rolling summary so total size stays bounded (FR-003).
- Unverifiable claims carry `metadata.verified=false` so replies never fabricate a confirmation (AC-10).

---

## In-Process Pydantic Shapes (`backend/app/schemas/memory.py`)

```python
class MemorySource(str, Enum):
    inbound_message = "inbound_message"; outbound_message = "outbound_message"
    summary = "summary"; system_note = "system_note"

class MemoryStatus(str, Enum):
    active = "active"; expired = "expired"; cleared = "cleared"; disabled = "disabled"

class MemoryEntryView(BaseModel):
    id: UUID
    source_message_id: UUID | None
    entry_type: str                       # MemoryEntryType
    content_summary: str                  # redacted
    pii_redacted: bool
    source: MemorySource
    created_at: datetime
    expires_at: datetime
    metadata: dict = Field(default_factory=dict)   # redacted facts only

class ConversationMemoryView(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    memory_key: str
    status: MemoryStatus
    summary: str                          # redacted, length-capped (may be "")
    recent_message_refs: list[MemoryEntryView]    # bounded
    updated_at: datetime | None
    expires_at: datetime | None
    metadata: dict = Field(default_factory=dict)

class MemoryContext(BaseModel):
    """Internal shape passed to RAG/reply generation (010). Empty when cold/disabled."""
    conversation_id: UUID
    summary: str = ""
    recent_refs: list[str] = Field(default_factory=list)   # redacted one-line gists
    anchors: dict = Field(default_factory=dict)            # e.g., {"that": "guest_count 150->220"}
    is_empty: bool = True

class MemoryRefreshResponse(BaseModel):
    conversation_id: UUID
    status: MemoryStatus
    updated_at: datetime
    expires_at: datetime
    entry_count: int

class MemoryClearResponse(BaseModel):
    conversation_id: UUID
    cleared: bool
    status: MemoryStatus       # "cleared"
```

---

## Service / Store Shapes

### Redis adapter (`backend/app/services/memory_store.py`)

```python
def _mem_key(tenant_id: UUID, conversation_id: UUID) -> str:
    return f"mem:{tenant_id}:{conversation_id}"           # tenant FIRST (SP-01, FR-020)

def _entries_key(tenant_id: UUID, conversation_id: UUID) -> str:
    return _mem_key(tenant_id, conversation_id) + ":entries"

async def read_memory(tenant_id, conversation_id) -> ConversationMemoryDoc | None: ...
async def write_memory(doc) -> None:        # SET key json EX MEMORY_TTL_SECONDS
    ...
async def append_entry(tenant_id, conversation_id, entry) -> None:  # LPUSH + LTRIM 0 N-1 + EXPIRE
    ...
async def delete_memory(tenant_id, conversation_id) -> bool:        # DEL key + entries key
    ...
# Every op is wrapped: on redis error or MEMORY_ENABLED=false -> empty/no-op, log, never raise.
```

### Service (`backend/app/services/memory_service.py`)

```python
async def get_context(session, *, tenant_id, conversation_id) -> MemoryContext:
    if not settings.MEMORY_ENABLED: return MemoryContext(conversation_id=conversation_id, is_empty=True)
    doc = await store.read_memory(tenant_id, conversation_id)         # never raises (degraded -> None)
    if not doc: return MemoryContext(conversation_id=conversation_id, is_empty=True)
    redacted = redact_context(doc)                                    # redact-on-read (SP-04)
    return to_context(redacted)

async def update_from_message(session, *, tenant_id, conversation_id, message_id) -> None:
    if not settings.MEMORY_ENABLED: return
    msgs = await load_recent_window(session, tenant_id, conversation_id, n=settings.MEMORY_MAX_RECENT_MESSAGES)
    summary, entries, pii = redact_and_summarize(msgs)               # 014 redact_text + cap
    doc = build_doc(tenant_id, conversation_id, summary, entries, pii, ttl=settings.MEMORY_TTL_SECONDS)
    await store.write_memory(doc)                                    # best-effort

def redact_and_summarize(messages) -> tuple[str, list[MemoryEntry], bool]:
    cleaned = [redact_text(m.body) for m in messages]               # SP-02 (PII/secret/prompt markers)
    summary = cap(build_rolling_summary(cleaned, messages), settings.MEMORY_SUMMARY_MAX_CHARS)
    entries = build_entries(cleaned, messages)                      # bounded; tag unverified claims (AC-10)
    return summary, entries, any(c.redacted for c in cleaned)

async def view(session, *, caller, conversation_id) -> ConversationMemoryView:
    conv = await resolve_conversation_or_404(session, caller, conversation_id)  # tenant-scope first (SP-01)
    doc = await store.read_memory(caller.tenant_id, conversation_id)
    await audit.log_event(..., event_type="memory_viewed")          # redacted, best-effort
    return to_view(conv, doc)                                       # status derived; redacted

async def refresh(session, *, caller, conversation_id) -> MemoryRefreshResponse: ...   # rebuild + audit
async def clear(session, *, caller, conversation_id) -> MemoryClearResponse:           # delete + audit
    conv = await resolve_conversation_or_404(session, caller, conversation_id)
    ok = await store.delete_memory(caller.tenant_id, conversation_id)
    await audit.log_event(..., event_type="memory_cleared")
    return MemoryClearResponse(conversation_id=conversation_id, cleared=ok, status=MemoryStatus.cleared)
```

`resolve_conversation_or_404` mirrors Specs 005–014 (404 if the conversation is not in the caller's tenant; 403 for platform admin / no tenant-content access). No key is constructed for a cross-tenant conversation (SP-01, AC-14).

### Error → HTTP mapping (endpoints)

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| conversation not in caller's tenant | 404 | `CONVERSATION_NOT_FOUND` |
| platform admin / no tenant-content access | 403 | `TENANT_CONTENT_FORBIDDEN` |
| invalid `conversation_id` / params | 422 | validation detail |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| cache unavailable (read/refresh) | 200 (degraded) | empty digest, `status="disabled"` (never a 5xx — FR-016) |

---

## Configuration

| Setting | Default | Purpose |
|---------|---------|---------|
| `MEMORY_ENABLED` | `true` | master switch; off → pre-016 behavior, endpoints return `disabled` |
| `MEMORY_TTL_SECONDS` | `604800` (7 days) | digest + entries TTL / `expires_at` (FR-002) |
| `MEMORY_MAX_RECENT_MESSAGES` | `10` | cap on recent refs / entries list (FR-003) |
| `MEMORY_SUMMARY_MAX_CHARS` | `1000` | rolling-summary length cap (FR-003) |
| `REDIS_URL` | env | the temporary cache backing memory |

---

## Relationships

```
Tenant 1──* Conversation 1──* Message
                  │
                  └── (cache) ConversationMemory 1──* MemoryEntry      [Redis, TTL ~7d]
                                   │
                                   ├─ supports ─▶ RagQuery/sources (009)  [RAG = source of truth]
                                   ├─ enriches ─▶ SuggestedReply (010)     [human-reviewed]
                                   ├─ checked by ─▶ GuardrailDecision (014) [before + after]
                                   └─ recorded by ─▶ AuditLog (013)         [redacted]
```

- A `ConversationMemory` belongs to exactly one `(Tenant, Conversation)` and holds many bounded `MemoryEntry`s.
- It references `Message` ids loosely (never copies raw bodies).
- It is **supporting context** to RAG/replies; it owns no policy and overrides no source.

---

## Invariants

- **No permanent storage**: memory exists only in Redis with a TTL; no raw transcript or PII is persisted to Postgres (FR-002, SP-03, AC-20).
- **Tenant-embedded keys**: `mem:{tenant_id}:{conversation_id}`; a `conversation_id` alone can't address another tenant's memory; conversation resolved within the caller's tenant before any key is built (SP-01, FR-020, AC-18).
- **Redacted in + out**: bodies are redacted before storage and the digest is redacted again on read; raw PII/secrets/prompts never enter the cache or a prompt/response (SP-02, SP-04).
- **Bounded**: ≤ `MEMORY_MAX_RECENT_MESSAGES` refs and a ≤ `MEMORY_SUMMARY_MAX_CHARS` rolling summary (FR-003).
- **Supporting, not authoritative**: RAG is the source of truth; on conflict RAG wins; memory never answers policy/price/contract alone (FR-008, FR-009, SP-09).
- **No autonomy**: memory never auto-sends a reply or auto-creates a task/escalation (SP-06).
- **Optional/degradable**: cache down or feature off → empty digest, pipeline still works, never a 5xx on the memory path (FR-016, AC-15).
- **Auditable**: view/refresh/clear/use logged (redacted) via 013 (FR-013).
- **Status is derived**: `active`/`expired`/`cleared`/`disabled` computed at read time, not mutable stored state.
