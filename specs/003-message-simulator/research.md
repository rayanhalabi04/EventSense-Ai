# Research: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Schema Changes — Message Status Column

**Decision**: Add a `MessageStatus` enum (`unread`, `read`) and a `status` column to the existing `messages` table via Alembic migration `0010_add_message_status`. Default value is `unread`. This is the only schema change introduced by this feature.

**Rationale**:
- Spec 001's `messages` table does not include a status column (confirmed from data-model.md). The inbox display feature (future) needs to distinguish read from unread messages.
- A PostgreSQL enum + NOT NULL column with a default is the right choice — it prevents null-status messages and keeps the schema self-describing.
- Only this feature's endpoint sets `status=unread` on creation. A future "mark as read" feature will update it to `read`.

**Alternatives considered**:
- Separate `message_reads` junction table (tracks which users have read which messages): more flexible for multi-reader scenarios, but overkill for MVP where "unread" simply means "not yet responded to". Deferred.
- Boolean `is_read` column: simpler, but doesn't allow future states (e.g., `archived`). Enum chosen for extensibility.

---

## Decision 2: Conversation Resolve Strategy

**Decision**: The simulator backend endpoint resolves the target conversation using this priority order:

```
1. If conversation_id supplied in request body:
     → Verify conversation.tenant_id == ctx.tenant_id (403 if mismatch)
     → Use that conversation
     → If status == "closed", re-open it

2. If no conversation_id:
     → Query: SELECT * FROM conversations
               WHERE tenant_id = :tid
               AND LOWER(client_name) = LOWER(:client_name)
               AND (client_contact = :contact OR (client_contact IS NULL AND :contact IS NULL))
               ORDER BY created_at DESC LIMIT 1
     → If found and open: use it
     → If found and closed: re-open it, use it
     → If not found: create new conversation (status=open, client_name, client_contact from request)
```

**Rationale**:
- Explicit `conversation_id` takes precedence — the caller is stating their intent precisely.
- Case-insensitive name matching prevents duplicate conversations from `"Alice"` vs `"alice"`.
- Contact-exact matching (nullable-aware) prevents false matches across unrelated clients with the same name.
- Re-opening closed conversations on new inbound messages is standard CRM behaviour (client has re-engaged).

**Alternatives considered**:
- Always create a new conversation: simpler, but produces duplicate conversations for the same client during demos. Rejected.
- Fuzzy name matching: too unpredictable for a deterministic simulator. Deferred.

---

## Decision 3: Simulator Endpoint Design

**Decision**: Single endpoint `POST /api/v1/simulator/messages`. Accepts `{ client_name, client_contact?, body, conversation_id? }`. Returns `{ message_id, conversation_id, is_new_conversation, conversation_status }`.

**Rationale**:
- A dedicated `/simulator/` prefix makes it immediately obvious that this is a non-production data injection route — easy to gate, audit, or remove later.
- Returning `is_new_conversation` lets the frontend show a contextual confirmation ("New conversation started for Alice" vs "Message added to existing conversation").
- `conversation_status` in the response tells the frontend whether a closed conversation was re-opened.

**Role guard**: `require_role(UserRole.staff, UserRole.manager)` — identical to the content route permission from Spec 002.

**Alternatives considered**:
- Two endpoints (`POST /simulator/conversations` + `POST /simulator/messages`): more RESTful, but creates an artificial two-step flow for what should be one user action. Single endpoint chosen.
- Reusing `POST /api/v1/conversations` + `POST /api/v1/conversations/{id}/messages`: would blur the line between real and simulated messages; simulator should have its own audit trail. Separate endpoint chosen.

---

## Decision 4: Audit Event Type

**Decision**: Use `simulator_message_created` as the `action` value in `audit_logs`. This is distinct from a hypothetical future `message_received` event that the real WhatsApp integration will use.

**Rationale**:
- Keeping simulator and real-channel audit events distinct allows managers and the platform team to filter simulator data out of AI performance metrics without needing a separate flag on the `messages` table.
- The spec explicitly names `simulator_message_created` as the required audit event.
- When the real WhatsApp integration is built, it will use `message_received` — the two events coexist in the same `audit_logs` table.

---

## Decision 5: Preset Message Storage

**Decision**: Five preset messages are hard-coded as a TypeScript constant in the frontend (`SIMULATOR_PRESETS`). They are not stored in the database.

```typescript
export const SIMULATOR_PRESETS = [
  { id: "price",    label: "Price enquiry",      body: "Can you send me your wedding package prices?" },
  { id: "count",    label: "Guest count change",  body: "We need to change the guest count from 150 to 220." },
  { id: "cancel",   label: "Cancellation query",  body: "I want to cancel. Is the deposit refundable?" },
  { id: "payment",  label: "Payment issue",       body: "I paid the deposit but no one confirmed." },
  { id: "complaint",label: "Complaint",           body: "I am unhappy with the decoration sample." },
];
```

**Rationale**:
- Hard-coding in the frontend is the simplest approach for MVP. No API needed; instant UX; no migration.
- Presets are a UX convenience — the stored message body is always plain text regardless of source.

**Alternatives considered**:
- Database table for configurable presets: makes sense post-MVP when tenants want their own presets. Deferred.
- Backend endpoint returning presets: unnecessary for static content. Rejected.

---

## Decision 6: Message Body Validation Strategy

**Decision**: Validation is enforced at both layers:

- **Frontend**: live character counter; submit button disabled when `body.trim().length === 0` or `body.length > 4000`; inline error messages
- **Backend** (authoritative): Pydantic `@validator` on `SimulatorMessageRequest.body` — `body.strip()` empty → 422; `len(body) > 4000` → 422; `client_name.strip()` empty → 422

**Rationale**:
- Frontend validation is UX; backend validation is security. Both are needed.
- Pydantic validators run before the route handler — clean and consistent with FastAPI patterns.
- 4,000-character cap mirrors real WhatsApp practical limits and prevents data abuse.

---

## Decision 7: Frontend Simulator Layout

**Decision**: The simulator lives at `/simulator` as a dedicated page (`SimulatorPage.tsx`), accessible from the sidebar nav. It consists of:

1. `ConversationSelector` — dropdown listing existing tenant conversations (client name + status); optional
2. `ClientFields` — client name (required) + client contact (optional); hidden when existing conversation is selected
3. `PresetPicker` — horizontal chip/button row with the 5 presets
4. `MessageBodyField` — textarea with live character counter
5. Submit button + inline confirmation/error display

**Rationale**:
- Dedicated page (vs modal) gives more room for the preset picker and confirmation feedback during demos.
- Hiding client fields when an existing conversation is selected reduces cognitive load.
- The form clears the body field after successful submission but retains the client selection for easy follow-up messages.

---

## Decision 8: Deferred Items

| Item | Reason deferred |
|------|----------------|
| Real WhatsApp Business API | Out of scope per spec |
| Media attachments | Out of scope per spec |
| Bulk message injection | Out of scope per spec |
| Configurable presets per tenant | Post-MVP |
| "Mark as read" message status update | Future inbox feature |
| Read receipts | Out of scope per spec |
| Fuzzy client name matching | Deferred, deterministic match sufficient for MVP |
