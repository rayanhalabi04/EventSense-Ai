# Implementation Plan: Message Detail Page

**Branch**: `005-message-detail-page` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-message-detail-page/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): `conversations`, `messages` tables; `TenantScopedRepository`; cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): `messages.status` column (`unread`/`read`), `direction` column (`inbound`/`outbound`)
- [Spec 004 — Message Inbox](../004-message-inbox/plan.md): navigation entry point (`/conversations/:id` stub becomes this page); `total_unread` consumed after mark-as-read

---

## Summary

Build a read-only tenant-scoped conversation detail page. A single `GET /api/v1/conversations/{conversation_id}` endpoint returns the conversation header (client name, contact, status) plus the full chronologically ordered message thread. As a side effect of the GET, all unread **inbound** messages in that conversation are marked `read` in the same transaction — so the inbox `total_unread` badge stays accurate without any explicit action. The endpoint distinguishes **404** (conversation does not exist in this tenant) from **403** (conversation exists but belongs to another tenant) to prevent tenant enumeration. The frontend `ConversationDetailPage` replaces the Spec 004 stub route, renders a `ClientHeader` + `MessageThread`, and lays out six **non-functional** AI placeholder panels (intent, risk, RAG sources, suggested reply, task creation, escalation) so future specs slot in without a redesign. One Alembic migration is added only if an index on `messages(conversation_id, sent_at)` is not already present; otherwise zero schema changes.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2.x async, pydantic v2, Alembic
- Frontend: React 18, `react-router-dom` v6 (`useParams`, `useNavigate`), Vite 5, Tailwind CSS, shadcn/ui (`Badge`, `Card`, `Skeleton`, `Alert`, `Button`, `Separator`)

**Storage**: PostgreSQL 15 — no new tables; reuses `conversations` + `messages`

**Testing**: pytest + pytest-asyncio (backend integration tests)

**Target Platform**: Linux server (backend), browser (frontend)

**Project Type**: Web application — FastAPI REST backend + React SPA frontend

**Performance Goals**: Standard web app targets. Detail page (≤ 50 messages) loads within standard user expectations.

**Constraints**:
- `tenant_id` from JWT only — detail query always filters `WHERE conversations.tenant_id = :tenant_id`
- 404 vs 403 must be distinguishable yet leak-free: non-existent → 404; wrong-tenant → 403 (see SR-04)
- Mark-as-read is scoped to `direction = inbound AND status = unread` within the authenticated tenant; idempotent
- Messages ordered `sent_at ASC` (oldest first)
- Platform Admin receives 403
- AI placeholder panels are presentational only — no backend fields, no network calls

**Scale/Scope**: MVP — two demo tenants; full thread loaded per request (no thread pagination).

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/005-message-detail-page/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions
├── data-model.md        # Phase 1: query logic, mark-as-read, Pydantic schemas, frontend state
├── quickstart.md        # Phase 1: curl guide + 404/403 + mark-as-read verification
├── contracts/
│   └── api-contracts.md # Phase 1: endpoint contract + error matrix
├── checklists/
│   └── requirements.md  # Spec quality checklist (already present)
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files added by this feature:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── conversations.py            # GET /api/v1/conversations/{conversation_id}
│   ├── services/
│   │   └── conversation_service.py     # get_conversation_detail() + mark_inbound_read()
│   └── schemas/
│       └── conversation.py             # MessageResponse, ConversationDetailResponse, AiPlaceholders
└── tests/
    └── integration/
        └── test_conversation_detail.py # AC-01 through AC-14 integration tests

frontend/
└── src/
    ├── api/
    │   └── conversations.ts            # getConversationDetail(id) Axios call
    ├── hooks/
    │   └── useConversationDetail.ts    # fetch by id; loading/error/forbidden/notFound state
    ├── pages/
    │   └── ConversationDetailPage.tsx  # /conversations/:id route (REPLACES Spec 004 stub)
    └── components/conversation/
        ├── ClientHeader.tsx            # client name + contact + status badge
        ├── MessageThread.tsx           # chronological list or empty-thread state
        ├── MessageBubble.tsx           # single message; inbound/outbound styling; timestamp
        ├── AiPlaceholderPanel.tsx      # reusable "coming soon" panel (title + locked body)
        └── ConversationStates.tsx      # loading / error / forbidden / not-found views
```

Existing files modified:

```
backend/app/main.py            # ADD: mount conversations router at /api/v1
frontend/src/App.tsx           # CHANGE: /conversations/:id → ConversationDetailPage (was stub from Spec 004)
```

Optional migration (only if the index does not already exist from Spec 001/003):

```
backend/alembic/versions/
  00xx_index_messages_conversation_sent_at.py  # index on messages(conversation_id, sent_at)
```

---

## In Scope for This Feature

| Area | What is built |
|------|--------------|
| `conversation.py` (schema) | `MessageResponse`, `AiPlaceholders`, `ConversationDetailResponse` |
| `conversation_service.py` | `get_conversation_detail()` — fetch + tenant check (404/403) + ordered messages; `mark_inbound_read()` — idempotent UPDATE |
| `GET /api/v1/conversations/{id}` | Route: `require_role(staff, manager)`; calls service; 200 / 403 / 404 |
| Router mount | Registered at `/api/v1` in `main.py` |
| `conversations.ts` (API) | `getConversationDetail(id)` typed Axios call |
| `useConversationDetail.ts` (hook) | Fetch by id; `isLoading`, `error`, `isForbidden`, `isNotFound`, `data` |
| `ConversationDetailPage.tsx` | `/conversations/:id`; ProtectedRoute + RoleGuard; assembles header, thread, placeholders, state views |
| `ClientHeader.tsx` | Client name, contact (or "—"), status badge |
| `MessageThread.tsx` | Maps messages → `MessageBubble`; empty-thread state |
| `MessageBubble.tsx` | Body (full, untruncated), timestamp, inbound/outbound alignment + label |
| `AiPlaceholderPanel.tsx` | Reusable non-functional panel; rendered 6× with distinct titles |
| `ConversationStates.tsx` | Loading skeleton, generic error, 403 forbidden, 404 not-found |
| Route change | `/conversations/:id` now renders the real page (replaces Spec 004 placeholder) |
| Integration tests | `test_conversation_detail.py` — AC-01 through AC-14 |

---

## Deferred to Later Features

| Item | Target |
|------|--------|
| AI intent classification | Future AI spec — placeholder only here |
| Risk / sentiment detection | Future AI spec — placeholder only here |
| RAG knowledge-source retrieval | Future AI spec — placeholder only here |
| Suggested reply generation | Future AI spec — placeholder only here |
| Task creation | Future spec — placeholder only here |
| Escalation workflow | Future spec — placeholder only here |
| Reply / compose from detail page | Post-MVP |
| Manual mark unread / mark individual message read | Post-MVP |
| Status mutation (close/escalate) from detail page | Post-MVP — status is displayed, not editable |
| Thread pagination | Post-MVP — full thread loaded for now |
| Real-time updates (WebSocket) | Post-MVP |
| Real WhatsApp API | Out of scope entirely |

---

## Conversation Service Design

### `mark_inbound_read(session, tenant_id, conversation_id) -> int`

Idempotent bulk update. Returns rows affected (0 when nothing was unread).

```python
async def mark_inbound_read(session, tenant_id, conversation_id) -> int:
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
```

### `get_conversation_detail(session, tenant_id, conversation_id) -> ConversationDetailResponse`

Key steps (full code in `data-model.md`):
1. Fetch conversation by `id` **without** tenant filter to distinguish 404 from 403.
2. If row is `None` → raise `NotFoundError` (→ 404).
3. If `conversation.tenant_id != tenant_id` → raise `ForbiddenError` (→ 403). No data returned.
4. Run `mark_inbound_read()` (same transaction, before reading messages so the response reflects post-read state).
5. Load all messages `WHERE conversation_id = :id ORDER BY sent_at ASC`.
6. Build `ConversationDetailResponse` including static `AiPlaceholders`.

> The deliberate "fetch then compare tenant_id" (rather than `WHERE tenant_id` in the lookup) is what enables the 404/403 distinction. Both branches still leak nothing: a wrong-tenant request never receives client_name, contact, or any message body.

---

## Frontend Hook Design (`useConversationDetail`)

```typescript
const { id } = useParams<{ id: string }>();
const [state, setState] = useState<{
  data: ConversationDetailResponse | null;
  isLoading: boolean;
  error: string | null;
  isForbidden: boolean;   // 403
  isNotFound: boolean;    // 404
}>({ data: null, isLoading: true, error: null, isForbidden: false, isNotFound: false });

useEffect(() => {
  getConversationDetail(id)
    .then(data => setState({ data, isLoading: false, error: null, isForbidden: false, isNotFound: false }))
    .catch(err => {
      const status = err.response?.status;
      setState({
        data: null, isLoading: false,
        error: status ? null : "Something went wrong",
        isForbidden: status === 403,
        isNotFound: status === 404,
      });
    });
}, [id]);
```

`ConversationDetailPage` switches on the hook state: loading → skeleton; isForbidden → 403 view; isNotFound → 404 view; error → generic error; data → header + thread + placeholders.

---

## AI Placeholder Panels (presentational only)

Rendered via one reusable `AiPlaceholderPanel` with a `title` prop. Six instances:

| Panel title | Future feature |
|-------------|----------------|
| AI Intent | intent classification |
| Risk / Sentiment | risk + sentiment scoring |
| Knowledge Sources | RAG source retrieval |
| Suggested Reply | AI reply generation |
| Create Task | task creation |
| Escalate | escalation workflow |

Each panel shows a `title` + a muted "Coming soon" body and is non-interactive (no buttons, no handlers, no network). The backend mirrors these as a static `ai_placeholders` object so the frontend can drive the panels from the response and future specs can replace the static block with live fields without a contract break.

---

## Validation Rules (authoritative — backend)

| Parameter | Rule | On violation |
|-----------|------|-------------|
| `conversation_id` | Must be a valid UUID (path param) | 422 |
| Conversation existence | Must exist in the system | 404 |
| Conversation tenancy | `conversation.tenant_id` must equal JWT `tenant_id` | 403 |
| Auth | Bearer token valid and non-expired | 401 |
| Role | `staff` or `manager` | 403 |
| `tenant_id` | Always from JWT — never from request | — |

---

## Test Coverage (`tests/integration/test_conversation_detail.py`)

| Test | Acceptance Criterion |
|------|---------------------|
| `test_detail_returns_messages_in_chronological_order` | AC-01 |
| `test_message_fields_complete_body_timestamp_direction` | AC-02 |
| `test_header_returns_client_name_contact_status` | AC-03 |
| `test_cross_tenant_conversation_returns_403` | AC-04 |
| `test_nonexistent_conversation_returns_404` | AC-05 |
| `test_platform_admin_blocked_with_403` | AC-06 |
| `test_open_marks_unread_inbound_as_read` | AC-07 |
| `test_outbound_messages_not_marked_read` | AC-08 |
| `test_mark_read_is_idempotent_on_already_read` | AC-09 |
| `test_inbox_total_unread_decrements_after_open` | AC-10 |
| `test_conversation_with_no_messages_returns_empty_thread` | AC-11 |
| `test_response_includes_six_ai_placeholders` | AC-12 (backend half) |
| `test_tenant_id_query_param_is_ignored` | AC-14 |

> AC-12 (DOM render) and AC-13 (placeholders trigger nothing) are verified in the frontend layer; the backend test confirms the `ai_placeholders` block is present in the response.
