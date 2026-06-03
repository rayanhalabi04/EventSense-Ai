# Data Model: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Phase**: 1 — Design

---

## Schema Changes from Spec 001

This feature introduces **one schema change**: a `status` column on the existing `messages` table. No new tables are created.

---

## Alembic Migration

### `0010_add_message_status`

Add `MessageStatus` enum and `status` column to `messages`:

```sql
CREATE TYPE message_status AS ENUM ('unread', 'read');

ALTER TABLE messages
  ADD COLUMN status message_status NOT NULL DEFAULT 'unread';
```

**Rationale**: All existing messages (if any exist before this migration) receive `status='unread'` as a safe default. The future inbox feature will add a `PATCH /messages/{id}/read` endpoint to transition messages to `'read'`.

---

## Updated `Message` Model (additive change to Spec 001)

The `Message` SQLAlchemy model in `backend/app/models/message.py` gains one field:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `status` | ENUM(`message_status`) | NOT NULL, DEFAULT `'unread'` | Added by migration 0010 |

All other columns unchanged from Spec 001.

---

## Pydantic Schemas (new, in `backend/app/schemas/simulator.py`)

### `SimulatorMessageRequest`

```python
class SimulatorMessageRequest(BaseModel):
    client_name: str          # required; stripped; min 1 char after strip
    client_contact: str | None = None   # optional phone or email
    body: str                 # required; stripped; 1–4000 chars after strip
    conversation_id: UUID | None = None # optional; if supplied, skip name-lookup

    @validator("body")
    def body_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Message body cannot be empty or whitespace only")
        if len(v) > 4000:
            raise ValueError("Message body cannot exceed 4000 characters")
        return v

    @validator("client_name")
    def client_name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Client name cannot be empty")
        return v
```

### `SimulatorMessageResponse`

```python
class SimulatorMessageResponse(BaseModel):
    message_id: UUID
    conversation_id: UUID
    is_new_conversation: bool
    conversation_status: str   # "open" (always open after this operation)
    tenant_id: UUID
```

---

## Conversation Resolve Logic (state diagram)

```
Input: { client_name, client_contact?, body, conversation_id? }
  │
  ├── conversation_id supplied?
  │     ├── YES → fetch conversation
  │     │         ├── tenant_id mismatch → 403 + audit(cross_tenant_access_attempt)
  │     │         ├── status == "closed" → set status="open", use it (is_new=False)
  │     │         └── status == "open"  → use it as-is (is_new=False)
  │     │
  │     └── NO  → query conversations WHERE tenant_id=:tid
  │                 AND LOWER(client_name)=LOWER(:name)
  │                 AND contact matches (exact, nullable-aware)
  │                 ORDER BY created_at DESC LIMIT 1
  │                 ├── Found, open   → use it (is_new=False)
  │                 ├── Found, closed → set status="open", use it (is_new=False)
  │                 └── Not found     → CREATE conversation (is_new=True)
  │
  └── Create message:
        direction=inbound, status=unread, sender_user_id=None,
        tenant_id=ctx.tenant_id, conversation_id=resolved_id, body=body, sent_at=now()
```

---

## MessageStatus Enum

```python
class MessageStatus(str, enum.Enum):
    unread = "unread"
    read   = "read"
```

Added to `backend/app/models/message.py`.

---

## Frontend Data Structures

### Preset constant (`frontend/src/data/simulatorPresets.ts`)

```typescript
export interface SimulatorPreset {
  id: string;
  label: string;
  body: string;
}

export const SIMULATOR_PRESETS: SimulatorPreset[] = [
  { id: "price",     label: "Price enquiry",     body: "Can you send me your wedding package prices?" },
  { id: "count",     label: "Guest count change", body: "We need to change the guest count from 150 to 220." },
  { id: "cancel",    label: "Cancellation query", body: "I want to cancel. Is the deposit refundable?" },
  { id: "payment",   label: "Payment issue",      body: "I paid the deposit but no one confirmed." },
  { id: "complaint", label: "Complaint",          body: "I am unhappy with the decoration sample." },
];
```

### API call type (`frontend/src/api/simulator.ts`)

```typescript
export interface SimulatorMessagePayload {
  client_name: string;
  client_contact?: string;
  body: string;
  conversation_id?: string;
}

export interface SimulatorMessageResult {
  message_id: string;
  conversation_id: string;
  is_new_conversation: boolean;
  conversation_status: string;
  tenant_id: string;
}
```

---

## Existing Entities Used (from Spec 001 — no changes)

| Entity | Used by | How |
|--------|---------|-----|
| `Conversation` | Simulator service | Created or reused; `status` may be updated from `closed` → `open` |
| `Message` | Simulator service | Created with `direction=inbound`, `status=unread` |
| `AuditLog` | `AuditService.log()` | `simulator_message_created` event written on success |
| `TenantScopedRepository` | Simulator service | All DB reads/writes use the tenant-filtered repo |
| `TenantContext` | Route dependency | `ctx.tenant_id` and `ctx.role` extracted from JWT |
| `require_role` | Route guard | `require_role(UserRole.staff, UserRole.manager)` |
