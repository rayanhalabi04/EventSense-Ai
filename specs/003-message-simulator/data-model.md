# Data Model: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Phase**: 1 — Design

---

## Schema Changes from Spec 001

This feature introduces the basic `conversations` and `messages` tenant-owned tables if they do not already exist, plus a `status` column on `messages`. Spec 001 defines the tenant foundation only; the simulator is the first feature that needs message data.

---

## Alembic Migration

### `0010_create_conversations_messages`

Create the minimum conversation/message schema needed by the simulator and inbox:

```sql
CREATE TYPE message_status AS ENUM ('unread', 'read');
CREATE TYPE conversation_status AS ENUM ('open', 'closed', 'escalated');
CREATE TYPE message_direction AS ENUM ('inbound', 'outbound');

CREATE TABLE conversations (... tenant_id UUID NOT NULL REFERENCES tenants(id), ...);
CREATE TABLE messages (... tenant_id UUID NOT NULL REFERENCES tenants(id), conversation_id UUID NOT NULL REFERENCES conversations(id), status message_status NOT NULL DEFAULT 'unread', ...);
```

**Rationale**: Simulated inbound messages must be stored in the same structure future real WhatsApp ingestion will use. The future inbox feature reads these rows.

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
    client_name: str | None = None      # required only when conversation_id is omitted
    client_contact: str | None = None   # optional phone or email
    body: str                 # required; stripped; 1–4000 chars after strip
    conversation_id: UUID | None = None # if supplied, skip name-lookup

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v: str):
        if not v.strip():
            raise ValueError("Message body cannot be empty or whitespace only")
        if len(v) > 4000:
            raise ValueError("Message body cannot exceed 4000 characters")
        return v

    @model_validator(mode="after")
    def conversation_or_client_name_required(self):
        if self.conversation_id is None and not (self.client_name and self.client_name.strip()):
            raise ValueError("Client name cannot be empty")
        return self
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
  client_name?: string;
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
| Future audit log | simulator event hook | `simulator_message_created` event emitted/recorded on success if audit infrastructure exists |
| `TenantScopedRepository` | Simulator service | All DB reads/writes use the tenant-filtered repo |
| `TenantContext` | Route dependency | `ctx.tenant_id` and `ctx.role` extracted from JWT |
| `require_role` | Route guard | `require_role(UserRole.staff, UserRole.manager)` |
