# Implementation Plan: WhatsApp-Style Message Simulator

**Branch**: `003-message-simulator` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-message-simulator/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): `conversations`, `messages`, `audit_logs` tables; `TenantScopedRepository`; `AuditService`
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth; `staff`/`manager` role; `require_role` dependency; `get_current_tenant_context`

---

## Summary

Build a message injection tool that lets staff and demo operators create realistic inbound client messages inside a tenant workspace — without using the real WhatsApp Business API. A single `POST /api/v1/simulator/messages` endpoint resolves or creates a tenant-scoped conversation and appends an `inbound`/`unread` message. Five hard-coded presets cover the five key demo scenarios. All writes are tenant-isolated and audit-logged with `simulator_message_created`. The one schema change is adding a `status` column (`unread`/`read`) to the existing `messages` table.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2.x, Alembic, pydantic (validators for body/name checks)
- Frontend: React 18, Vite 5, Tailwind CSS, shadcn/ui (`Button`, `Input`, `Textarea`, `Select`, `Badge`)

**Storage**: PostgreSQL 15 — one additive migration (message status column)

**Testing**: pytest + pytest-asyncio (backend)

**Target Platform**: Linux server (backend), browser (frontend)

**Project Type**: Web application — FastAPI REST backend + React SPA frontend

**Performance Goals**: Standard web app targets. Simulator is a low-frequency demo tool.

**Constraints**:
- `tenant_id` must come from JWT only; never from request body
- `direction=inbound` and `status=unread` must be set by the backend, never by the client
- No real WhatsApp API calls; no media attachments; no outbound message creation
- Body: 1–4,000 chars; whitespace-only treated as empty

**Scale/Scope**: Two demo tenants; simulator is a dev/demo tool, not production traffic.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/003-message-simulator/
├── plan.md              # This file
├── research.md          # Phase 0: 8 design decisions
├── data-model.md        # Phase 1: schema change, Pydantic schemas, conversation resolve logic
├── quickstart.md        # Phase 1: curl test guide + UI walkthrough
├── contracts/
│   └── api-contracts.md # Phase 1: endpoint contracts + cross-cutting table
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files added by this feature:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── simulator.py               # POST /api/v1/simulator/messages
│   │                                  # GET  /api/v1/simulator/conversations
│   ├── services/
│   │   └── simulator_service.py       # SimulatorService: resolve_conversation + create_message
│   └── schemas/
│       └── simulator.py               # SimulatorMessageRequest, SimulatorMessageResponse
├── alembic/versions/
│   └── 0010_add_message_status.py     # ADD COLUMN status message_status NOT NULL DEFAULT 'unread'
└── tests/
    └── integration/
        └── test_simulator.py          # AC-01 through AC-12 integration tests

frontend/
└── src/
    ├── data/
    │   └── simulatorPresets.ts        # SIMULATOR_PRESETS constant (5 entries)
    ├── api/
    │   └── simulator.ts               # injectMessage(), listConversations()
    ├── pages/
    │   └── SimulatorPage.tsx          # /simulator route (ProtectedRoute + RoleGuard)
    └── components/simulator/
        ├── SimulatorForm.tsx          # Full form: client fields + preset picker + body + submit
        ├── PresetPicker.tsx           # Chip row for 5 presets; onClick populates body field
        ├── ConversationSelector.tsx   # Dropdown of existing conversations (GET /simulator/conversations)
        └── CharacterCounter.tsx       # Live counter: "x / 4000 characters"
```

Existing files modified:

```
backend/app/models/message.py          # ADD: MessageStatus enum + status column
backend/app/main.py                    # ADD: mount simulator router at /api/v1/simulator
backend/app/services/audit_service.py  # ADD: AuditAction.simulator_message_created constant
frontend/src/App.tsx                   # ADD: /simulator route with ProtectedRoute + RoleGuard
```

---

## In Scope for This Feature

| Area | What is built |
|------|--------------|
| Alembic migration | `0010_add_message_status`: adds `MessageStatus` enum and `status NOT NULL DEFAULT 'unread'` to `messages` |
| `MessageStatus` enum | `unread`, `read` — added to `backend/app/models/message.py` |
| Pydantic schemas | `SimulatorMessageRequest` (with validators), `SimulatorMessageResponse` in `backend/app/schemas/simulator.py` |
| `SimulatorService` | `resolve_or_create_conversation()` + `create_inbound_message()` + `list_tenant_conversations()` in `backend/app/services/simulator_service.py` |
| `POST /api/v1/simulator/messages` | Main endpoint; requires `staff`/`manager`; validates, resolves conversation, creates message, audit logs |
| `GET /api/v1/simulator/conversations` | Returns tenant's conversations for dropdown; requires `staff`/`manager` |
| `AuditAction.simulator_message_created` | Added to audit_service.py constants |
| `SIMULATOR_PRESETS` | TypeScript constant in `frontend/src/data/simulatorPresets.ts` |
| `simulator.ts` API module | `injectMessage()` and `listConversations()` |
| `SimulatorPage` | `/simulator` page with full form and confirmation display |
| `SimulatorForm` | Compound form component with client fields, preset picker, body textarea, submit |
| `PresetPicker` | Chip row; click populates `body` field |
| `ConversationSelector` | Dropdown backed by `GET /api/v1/simulator/conversations` |
| `CharacterCounter` | Live counter; red at > 4,000 chars |
| Route guard | `/simulator` wrapped in `ProtectedRoute` + `RoleGuard(["staff", "manager"])` |
| Integration tests | `test_simulator.py` — 12 tests covering all AC |

---

## Deferred to Later Features

| Item | Target |
|------|--------|
| Real WhatsApp Business API | WhatsApp Integration feature |
| Media attachments via simulator | Media Support feature |
| Bulk message injection | Demo Tools enhancement |
| Configurable presets per tenant | Demo Tools enhancement |
| `PATCH /messages/{id}/read` (mark as read) | Inbox / Message Handling feature |
| Full inbox page | Inbox feature |
| Suggested reply generation triggered by new message | AI Replies feature |

---

## Simulator Service Design (`backend/app/services/simulator_service.py`)

### `resolve_or_create_conversation`

```python
async def resolve_or_create_conversation(
    session: AsyncSession,
    tenant_id: UUID,
    client_name: str,
    client_contact: str | None,
    conversation_id: UUID | None,
    audit_service: AuditService,
    ctx: TenantContext,
) -> tuple[Conversation, bool]:   # (conversation, is_new)
    """
    Returns the target conversation and whether it was just created.
    Re-opens closed conversations. Raises ForbiddenError on cross-tenant conversation_id.
    """
```

Resolution steps (in order):

1. **If `conversation_id` supplied**: fetch from DB. If `tenant_id` mismatch → `ForbiddenError` + audit log. If `status == "closed"` → set `status = "open"`. Return `(conv, False)`.

2. **If no `conversation_id`**: query `conversations WHERE tenant_id=:tid AND LOWER(client_name)=LOWER(:name) AND client_contact IS NOT DISTINCT FROM :contact ORDER BY created_at DESC LIMIT 1`.
   - Found, open → return `(conv, False)`
   - Found, closed → set `status="open"`, return `(conv, False)`
   - Not found → `INSERT` new conversation → return `(new_conv, True)`

### `create_inbound_message`

```python
async def create_inbound_message(
    session: AsyncSession,
    tenant_id: UUID,
    conversation_id: UUID,
    body: str,
    user_id: UUID,
) -> Message:
    """
    Creates a message with direction=inbound, status=unread, sender_user_id=None.
    Updates conversation.updated_at via SQLAlchemy on_update trigger.
    """
```

---

## Tenant Isolation Rules

1. `POST /api/v1/simulator/messages` is guarded by `require_role(UserRole.staff, UserRole.manager)`. The `ctx.tenant_id` from the JWT is the only tenant scope used.
2. If `conversation_id` is supplied, `SimulatorService` verifies `conversation.tenant_id == ctx.tenant_id` before using it. Mismatch → 403 + `cross_tenant_access_attempt` audit event.
3. `GET /api/v1/simulator/conversations` uses `TenantScopedRepository.list(tenant_id=ctx.tenant_id)` — the tenant filter is unconditional.
4. Created messages receive `tenant_id=ctx.tenant_id` injected by the service — the client cannot supply a different value.

---

## Validation Rules (authoritative — backend)

| Field | Rule | HTTP response on failure |
|-------|------|--------------------------|
| `body` | `body.strip()` must be non-empty | 422 Unprocessable Entity |
| `body` | `len(body)` ≤ 4,000 characters | 422 Unprocessable Entity |
| `client_name` | `client_name.strip()` must be non-empty | 422 Unprocessable Entity |
| `conversation_id` | If supplied, must belong to `ctx.tenant_id` | 403 Forbidden |
| Auth | Bearer token must be valid and non-expired | 401 Unauthorized |
| Role | Must be `staff` or `manager` | 403 Forbidden |

---

## Audit Logging

`AuditService.log()` is called on every successful message creation:

```python
audit_service.log(
    tenant_id=ctx.tenant_id,
    action=AuditAction.simulator_message_created,
    outcome=AuditOutcome.allowed,
    actor_user_id=ctx.user_id,
    resource_type="message",
    resource_id=message.id,
    detail={
        "conversation_id": str(conversation.id),
        "client_name": request.client_name,
        "is_new_conversation": is_new,
        "reopened": was_closed,
    },
)
```

No audit event is written for validation failures (422 responses). Permission failures (403) are audit-logged by `require_role` and `ForbiddenError` handlers from Spec 001/002.

---

## Test Coverage (`tests/integration/test_simulator.py`)

| Test | Acceptance Criterion |
|------|---------------------|
| `test_simulator_creates_inbound_message_with_correct_fields` | AC-01, AC-08 |
| `test_simulator_creates_new_conversation_for_unknown_client` | AC-02 |
| `test_simulator_appends_to_existing_conversation` | AC-03 |
| `test_simulator_reopens_closed_conversation` | AC-04 |
| `test_simulator_rejects_empty_body` | AC-05 |
| `test_simulator_rejects_whitespace_only_body` | AC-06 |
| `test_simulator_rejects_body_exceeding_4000_chars` | AC-07 |
| `test_simulator_writes_audit_log_on_success` | AC-09 |
| `test_simulator_message_invisible_to_other_tenant` | AC-10 |
| `test_simulator_conversation_list_scoped_to_tenant` | AC-10 (GET endpoint) |
| `test_simulator_cross_tenant_conversation_id_returns_403` | SR-03, AC-12 |
| `test_simulator_platform_admin_returns_403` | SR-02 |
