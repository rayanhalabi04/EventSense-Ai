# Data Model: Message Detail Page

**Branch**: `005-message-detail-page` | **Phase**: 1 — Design

---

## Schema Changes

**None required for entities.** This feature reads existing tables from Spec 001 (`conversations`, `messages`) and uses the `status` (`unread`/`read`) and `direction` (`inbound`/`outbound`) columns from Spec 003. Mark-as-read is a plain `UPDATE` on the existing `status` column.

**Conditional migration**: ensure a composite index `messages(conversation_id, sent_at)` exists. Add one Alembic migration only if it is not already present from Spec 001/003.

---

## Existing Entities Used

### `conversations` (Spec 001)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | Lookup target (`/conversations/{id}`) |
| `tenant_id` | UUID | Tenant check (404/403 decision) |
| `client_name` | VARCHAR(255) | Header display |
| `client_contact` | VARCHAR(320) | Header display (nullable) |
| `status` | ENUM | Header status badge (`open`/`closed`/`escalated`) |
| `created_at` | TIMESTAMPTZ | Header metadata |
| `updated_at` | TIMESTAMPTZ | Header metadata |

### `messages` (Spec 001 + Spec 003)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | Message identity; stable sort tie-breaker |
| `tenant_id` | UUID | Scoping the mark-as-read UPDATE |
| `conversation_id` | UUID | Thread filter + join key |
| `body` | TEXT | Full message body (untruncated) |
| `sent_at` | TIMESTAMPTZ | Chronological ordering (ASC) + display |
| `direction` | ENUM (`inbound`/`outbound`) | Bubble alignment; mark-read scope (inbound only) |
| `status` | ENUM (`unread`/`read`) | Mark-as-read target |

---

## Pydantic Schemas (`backend/app/schemas/conversation.py`)

### Message Response

```python
class MessageResponse(BaseModel):
    id: UUID
    body: str                # full, untruncated
    sent_at: datetime
    direction: str           # "inbound" | "outbound"
    status: str              # "unread" | "read" (will be "read" for inbound after open)

    model_config = ConfigDict(from_attributes=True)
```

### AI Placeholder Block (static)

```python
class AiPlaceholder(BaseModel):
    available: bool = False
    label: str

class AiPlaceholders(BaseModel):
    intent:          AiPlaceholder = AiPlaceholder(label="AI Intent")
    risk:            AiPlaceholder = AiPlaceholder(label="Risk / Sentiment")
    rag_sources:     AiPlaceholder = AiPlaceholder(label="Knowledge Sources")
    suggested_reply: AiPlaceholder = AiPlaceholder(label="Suggested Reply")
    task_creation:   AiPlaceholder = AiPlaceholder(label="Create Task")
    escalation:      AiPlaceholder = AiPlaceholder(label="Escalate")
```

### Conversation Detail Response

```python
class ConversationDetailResponse(BaseModel):
    conversation_id: UUID
    client_name: str
    client_contact: str | None
    conversation_status: str        # "open" | "closed" | "escalated"
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
    ai_placeholders: AiPlaceholders = AiPlaceholders()
```

---

## Service Logic (`backend/app/services/conversation_service.py`)

```python
async def mark_inbound_read(
    session: AsyncSession,
    tenant_id: UUID,
    conversation_id: UUID,
) -> int:
    """Idempotent: marks all unread INBOUND messages read. Returns rows affected."""
    stmt = (
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == tenant_id,
            Message.direction == MessageDirection.inbound,
            Message.status == MessageStatus.unread,
        )
        .values(status=MessageStatus.read)
    )
    result = await session.execute(stmt)
    return result.rowcount


async def get_conversation_detail(
    session: AsyncSession,
    tenant_id: UUID,
    conversation_id: UUID,
) -> ConversationDetailResponse:

    # 1. Fetch WITHOUT tenant filter to distinguish 404 vs 403
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversation not found")           # -> 404
    if conv.tenant_id != tenant_id:
        raise ForbiddenError("Conversation belongs to another tenant")  # -> 403

    # 2. Mark unread inbound messages read (same transaction, before SELECT)
    await mark_inbound_read(session, tenant_id, conversation_id)

    # 3. Load full thread, oldest first (stable tie-breaker on id)
    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sent_at.asc(), Message.id.asc())
    )
    messages = (await session.execute(msg_stmt)).scalars().all()

    await session.commit()  # persist the mark-as-read

    # 4. Build response (post-read state)
    return ConversationDetailResponse(
        conversation_id=conv.id,
        client_name=conv.client_name,
        client_contact=conv.client_contact,
        conversation_status=conv.status.value,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
        ai_placeholders=AiPlaceholders(),
    )
```

### Error → HTTP mapping (route handler)

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` | 404 | `CONVERSATION_NOT_FOUND` |
| `ForbiddenError` | 403 | `CROSS_TENANT_FORBIDDEN` |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth dependency) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend State Shape (`useConversationDetail` hook)

```typescript
interface MessageResponse {
  id: string;
  body: string;
  sent_at: string;
  direction: "inbound" | "outbound";
  status: "unread" | "read";
}

interface AiPlaceholder { available: boolean; label: string; }

interface ConversationDetailResponse {
  conversation_id: string;
  client_name: string;
  client_contact: string | null;
  conversation_status: "open" | "closed" | "escalated";
  created_at: string;
  updated_at: string;
  messages: MessageResponse[];
  ai_placeholders: {
    intent: AiPlaceholder;
    risk: AiPlaceholder;
    rag_sources: AiPlaceholder;
    suggested_reply: AiPlaceholder;
    task_creation: AiPlaceholder;
    escalation: AiPlaceholder;
  };
}

interface UseConversationDetailResult {
  data: ConversationDetailResponse | null;
  isLoading: boolean;
  error: string | null;
  isForbidden: boolean;   // 403
  isNotFound: boolean;    // 404
}
```

---

## Frontend Component Tree

```
ConversationDetailPage              /conversations/:id
├── ConversationStates             loading / error / forbidden / not-found (early returns)
├── ClientHeader                   client name + contact + status badge
├── MessageThread
│   ├── MessageBubble × N          inbound (left) / outbound (right); body + timestamp
│   └── (empty-thread state)       "No messages in this conversation yet."
└── AiPlaceholderPanel × 6         AI Intent · Risk/Sentiment · Knowledge Sources
                                   · Suggested Reply · Create Task · Escalate
```

- `ConversationStates` short-circuits rendering: while `isLoading` show skeleton; if `isForbidden` show 403 view; if `isNotFound` show 404 view + "Back to inbox"; if `error` show generic error + retry.
- `AiPlaceholderPanel` is reused six times, driven by `data.ai_placeholders`. Each is non-interactive ("Coming soon").
- `MessageBubble` renders the full body (no truncation) and aligns by `direction`.
