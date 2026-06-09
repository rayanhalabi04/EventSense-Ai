---

description: "Task list for Message Detail Page feature implementation"
---

# Tasks: Message Detail Page

**Branch**: `005-message-detail-page` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/005-message-detail-page/`

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `conversations` + `messages` tables; tenant-scoped service rules; cross-tenant 403 contract; `NotFoundError` / `ForbiddenError` → HTTP mapping
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`; Platform Admin block
- Spec 003 — Message Simulator: `messages.status` column (`unread`/`read`), `messages.direction` column (`inbound`/`outbound`)
- Spec 004 — Message Inbox: navigation entry point — `/conversations/:id` stub route in `App.tsx`; `total_unread` consumed by the inbox after mark-as-read

**Tech stack**: FastAPI + SQLAlchemy 2.x async + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**Schema migrations**: NONE required for entities. One **conditional** Alembic migration only if the composite index `messages(conversation_id, sent_at)` does not already exist from Spec 001/003 (see T002).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Dependency Review

**Purpose**: Confirm the reused 001–004 foundation is present and test infrastructure is ready. No new code yet.

- [ ] T001 Confirm reused models/dependencies exist and are imported correctly: `Conversation` and `Message` SQLAlchemy models (with `tenant_id`, `client_name`, `client_contact`, `status`, `created_at`, `updated_at` on conversation; `body`, `sent_at`, `direction`, `status`, `tenant_id`, `conversation_id` on message), `MessageDirection`/`MessageStatus` enums (Spec 003), `require_role` + `get_current_tenant_context` (Spec 002), and `NotFoundError`/`ForbiddenError` exceptions with their HTTP mapping (Spec 001). Record exact import paths for use in later tasks — do NOT redefine any of these.
- [ ] T002 Inspect existing Alembic migrations / `\d messages` for a composite index on `messages(conversation_id, sent_at)`. If present, no migration is added (note it). If absent, create `backend/alembic/versions/00xx_index_messages_conversation_sent_at.py` adding that index only (no column/table changes).
- [ ] T003 Verify `backend/tests/integration/` directory exists and contains `__init__.py`; create both if absent (required before the test file is added in Phase 3).

**Checkpoint**: Foundation confirmed reused; index decision made; test dir ready.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic response schemas and the conversation service are shared by the route handler and all integration tests. Nothing in Phases 3–5 can compile without them.

**⚠️ CRITICAL**: All user story phases depend on this phase completing first.

- [ ] T004 Create `MessageResponse` (`id`, `body`, `sent_at`, `direction`, `status`; `model_config = ConfigDict(from_attributes=True)`), `AiPlaceholder` (`available: bool = False`, `label: str`), `AiPlaceholders` (six defaulted fields: `intent`/`risk`/`rag_sources`/`suggested_reply`/`task_creation`/`escalation` with labels "AI Intent" / "Risk / Sentiment" / "Knowledge Sources" / "Suggested Reply" / "Create Task" / "Escalate"), and `ConversationDetailResponse` (`conversation_id`, `client_name`, `client_contact: str | None`, `conversation_status`, `created_at`, `updated_at`, `messages: list[MessageResponse]`, `ai_placeholders: AiPlaceholders = AiPlaceholders()`) in `backend/app/schemas/conversation.py`
- [ ] T005 Implement `mark_inbound_read(session, tenant_id, conversation_id) -> int` in `backend/app/services/conversation_service.py` — idempotent bulk `UPDATE Message SET status=read WHERE conversation_id == :id AND tenant_id == :tenant_id AND direction == inbound AND status == unread`; returns `result.rowcount`. No commit inside this function (caller commits).

**Checkpoint**: Schemas + mark-as-read helper importable — Phase 3 can begin.

---

## Phase 3: User Story 1 — View Full Conversation Thread (Priority: P1) 🎯 MVP

**Goal**: An authenticated staff or manager user opens `/conversations/{id}` for a conversation in their tenant and sees the header (client name, contact-or-"—", status badge) plus the full message thread in chronological order (`sent_at ASC`, tie-broken by `id ASC`), each message showing full untruncated body, timestamp, and direction. Cross-tenant access → 403; non-existent → 404; Platform Admin → 403; `tenant_id` is always derived from the JWT.

**Independent Test**: Inject three simulator messages into one Tenant A conversation (two inbound, one outbound). `GET /api/v1/conversations/{id}` as Tenant A staff → all three returned in `sent_at` order with correct body/timestamp/direction. Same request as Tenant B staff → 403, no content. Random UUID → 404.

### Tests for User Story 1

> Write tests first; confirm they fail before implementing the Phase 3 backend tasks.

- [ ] T006 [US1] Write `test_detail_returns_messages_in_chronological_order` (AC-01) in `backend/tests/integration/test_conversation_detail.py` — seed 3 messages out of order; assert returned in `sent_at ASC` (id ASC tie-break)
- [ ] T007 [P] [US1] Write `test_message_fields_complete_body_timestamp_direction` (AC-02) in `backend/tests/integration/test_conversation_detail.py` — assert each `MessageResponse` has full body, `sent_at`, and correct `direction`
- [ ] T008 [P] [US1] Write `test_header_returns_client_name_contact_status` (AC-03) in `backend/tests/integration/test_conversation_detail.py` — assert `client_name`, `client_contact`, `conversation_status` present and correct
- [ ] T009 [P] [US1] Write `test_cross_tenant_conversation_returns_403` (AC-04) in `backend/tests/integration/test_conversation_detail.py` — Tenant B token + Tenant A conversation id → 403 with `error_code = CROSS_TENANT_FORBIDDEN`; assert no conversation content (client_name/messages) in body
- [ ] T010 [P] [US1] Write `test_nonexistent_conversation_returns_404` (AC-05) in `backend/tests/integration/test_conversation_detail.py` — random UUID → 404 with `error_code = CONVERSATION_NOT_FOUND`
- [ ] T011 [P] [US1] Write `test_platform_admin_blocked_with_403` (AC-06) in `backend/tests/integration/test_conversation_detail.py` — platform admin token → 403 with `error_code = INSUFFICIENT_ROLE`
- [ ] T012 [P] [US1] Write `test_conversation_with_no_messages_returns_empty_thread` (AC-11) in `backend/tests/integration/test_conversation_detail.py` — conversation with zero messages → 200, `messages == []`, header still populated
- [ ] T013 [P] [US1] Write `test_tenant_id_query_param_is_ignored` (AC-14) in `backend/tests/integration/test_conversation_detail.py` — own-tenant conversation with bogus `?tenant_id=<other>` query param → 200 using JWT tenant (param ignored)

### Backend Implementation for User Story 1

- [ ] T014 [US1] Implement `get_conversation_detail(session, tenant_id, conversation_id) -> ConversationDetailResponse` in `backend/app/services/conversation_service.py`: (1) `session.get(Conversation, conversation_id)` WITHOUT tenant filter; (2) `None` → raise `NotFoundError`; (3) `conv.tenant_id != tenant_id` → raise `ForbiddenError` (no data); (4) call `mark_inbound_read()` (same transaction); (5) `SELECT Message WHERE conversation_id == :id ORDER BY sent_at ASC, id ASC`; (6) `session.commit()`; (7) build `ConversationDetailResponse` with `AiPlaceholders()` (depends on T004, T005)
- [ ] T015 [US1] Implement `GET /api/v1/conversations/{conversation_id}` route handler in `backend/app/api/v1/conversations.py` with `require_role(staff, manager)`, `conversation_id: UUID` path param (422 on malformed), `tenant_id` from `get_current_tenant_context`, calling `get_conversation_detail()`; map `NotFoundError`→404/`CONVERSATION_NOT_FOUND`, `ForbiddenError`→403/`CROSS_TENANT_FORBIDDEN` (depends on T014)
- [ ] T016 [US1] Mount the conversations router at the `/api/v1` prefix in `backend/app/main.py` (depends on T015)

### Frontend Implementation for User Story 1

- [ ] T017 [P] [US1] Define TypeScript interfaces (`MessageResponse`, `AiPlaceholder`, `ConversationDetailResponse`) and implement `getConversationDetail(id: string): Promise<ConversationDetailResponse>` typed Axios call using the existing auth token interceptor in `frontend/src/api/conversations.ts`
- [ ] T018 [US1] Implement `useConversationDetail(id)` hook with `data`/`isLoading`/`error`/`isForbidden` (403)/`isNotFound` (404) state, `useEffect` keyed on `id`, mapping `err.response?.status` to the right flag in `frontend/src/hooks/useConversationDetail.ts` (depends on T017)
- [ ] T019 [P] [US1] Create `ConversationStates` component rendering exactly one of: loading skeleton (header + thread placeholders), 403 "You don't have access to this conversation." + inbox link, 404 "Conversation not found." + "Back to inbox" button, generic error + retry affordance in `frontend/src/components/conversation/ConversationStates.tsx`
- [ ] T020 [P] [US1] Create `ClientHeader` component showing client name, client contact (render "—" when null), and a status badge (shadcn `Badge`: open / closed / escalated) in `frontend/src/components/conversation/ClientHeader.tsx`
- [ ] T021 [P] [US1] Create `MessageBubble` component rendering the full untruncated body, formatted `sent_at` timestamp, and inbound (left) / outbound (right) alignment + direction label in `frontend/src/components/conversation/MessageBubble.tsx`
- [ ] T022 [US1] Create `MessageThread` component mapping `messages` (already ordered by the API) to `MessageBubble`s; renders "No messages in this conversation yet." empty state when `messages.length === 0` in `frontend/src/components/conversation/MessageThread.tsx` (depends on T021)
- [ ] T023 [US1] Create `ConversationDetailPage` at `/conversations/:id` with `ProtectedRoute` + `RoleGuard(["staff", "manager"])`, reading `id` via `useParams`, consuming `useConversationDetail`, short-circuiting through `ConversationStates` (loading → forbidden → notFound → error) and otherwise rendering `ClientHeader` + `MessageThread` + the six placeholder panels in `frontend/src/pages/ConversationDetailPage.tsx` (depends on T018, T019, T020, T022; placeholder panels from T026)
- [ ] T024 [US1] In `frontend/src/App.tsx`, change the existing `/conversations/:id` route target from the Spec 004 stub to `ConversationDetailPage` (route already registered — only the component changes) (depends on T023)

**Checkpoint**: US1 functional — endpoint returns tenant-scoped detail with 404/403 distinction; detail page renders header + thread + state views; tenant isolation and role guard confirmed by tests.

---

## Phase 4: User Story 2 — Mark Unread Messages as Read on Open (Priority: P1)

**Goal**: Opening the detail page marks all unread **inbound** messages in that conversation as read, in the same transaction as the GET and before the thread is read back (so the response already reflects `read`). Outbound messages are never touched. The operation is idempotent. The inbox `total_unread` decrements on the next inbox load.

**Independent Test**: Inject two unread inbound messages. Note inbox `total_unread`. Open `/conversations/{id}` → response shows both inbound as `read`. Re-open → 200, zero rows changed. Reload inbox → `total_unread` decremented by 1 (conversation-level).

> The mark-as-read mechanism itself (`mark_inbound_read`, wired into `get_conversation_detail`) is implemented in Phase 2/3 (T005, T014). This phase verifies its behavior contract.

### Tests for User Story 2

- [ ] T025 [P] [US2] Write `test_open_marks_unread_inbound_as_read` (AC-07) in `backend/tests/integration/test_conversation_detail.py` — 2 unread inbound → open detail → assert both `status == read` in response and in DB
- [ ] T026a [P] [US2] Write `test_outbound_messages_not_marked_read` (AC-08) in `backend/tests/integration/test_conversation_detail.py` — 1 unread inbound + 1 outbound → open detail → assert only the inbound changed; outbound untouched
- [ ] T027 [P] [US2] Write `test_mark_read_is_idempotent_on_already_read` (AC-09) in `backend/tests/integration/test_conversation_detail.py` — fully-read conversation → open detail → assert 200, no state change, no error
- [ ] T028 [P] [US2] Write `test_inbox_total_unread_decrements_after_open` (AC-10) in `backend/tests/integration/test_conversation_detail.py` — capture inbox `total_unread` → open detail → re-fetch `GET /api/v1/inbox` → assert `total_unread` decremented

**Checkpoint**: US1 + US2 functional — mark-as-read is correctly scoped (inbound only), idempotent, and consistent with the inbox badge.

---

## Phase 5: User Story 3 — AI Workflow Placeholder Sections (Priority: P2)

**Goal**: The detail page shows six clearly labelled, non-functional placeholder panels (AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, Escalate), each rendering a "Coming soon" body with no interactive elements and no backend calls. Panels are driven by the response `ai_placeholders` block.

**Independent Test**: Open any conversation detail page → all six labelled panels visible, each "Coming soon", none interactive; clicking inside a panel triggers no network request and no error.

### Backend Test for User Story 3

- [ ] T029 [US3] Write `test_response_includes_six_ai_placeholders` (AC-12 backend half) in `backend/tests/integration/test_conversation_detail.py` — assert `ai_placeholders` has all six keys, each `{ available: false, label: <title> }`

### Frontend Implementation for User Story 3

- [ ] T030 [US3] Create reusable `AiPlaceholderPanel` component (props: `title`) rendering the title + a muted "Coming soon" body, fully non-interactive (no buttons, no handlers, no network) using shadcn `Card` in `frontend/src/components/conversation/AiPlaceholderPanel.tsx`
- [ ] T031 [US3] Render `AiPlaceholderPanel` six times inside `ConversationDetailPage`, driven by `data.ai_placeholders` (one panel per entry, using each entry's `label`) in `frontend/src/pages/ConversationDetailPage.tsx` (depends on T023, T030)

**Checkpoint**: US1 + US2 + US3 functional — full read-only detail page with placeholder panels in place for future AI specs.

---

## Phase 6: Frontend Tests

**Purpose**: Cover navigation, state views, thread rendering, and placeholder behavior (AC-12 DOM render + AC-13 no side effects).

- [ ] T032 [P] Write navigation test: render an inbox item (Spec 004) inside a router, click the row, assert URL becomes `/conversations/{id}` and `ConversationDetailPage` mounts in `frontend/src/pages/ConversationDetailPage.test.tsx`
- [ ] T033 [P] Write loading-state test: mock `getConversationDetail` pending → assert skeleton from `ConversationStates` renders in `frontend/src/pages/ConversationDetailPage.test.tsx`
- [ ] T034 [P] Write error/forbidden/not-found tests: mock 403 → "don't have access" view; mock 404 → "Conversation not found" + back-to-inbox; mock network error → generic error + retry in `frontend/src/pages/ConversationDetailPage.test.tsx`
- [ ] T035 [P] Write thread-render test: mock response with 2 inbound + 1 outbound messages → assert all bodies render full, ordered, with correct direction alignment; mock empty `messages` → assert "No messages in this conversation yet." in `frontend/src/pages/ConversationDetailPage.test.tsx`
- [ ] T036 [P] Write placeholder tests (AC-12 + AC-13): assert all six labelled panels (AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, Escalate) are in the DOM; click/hover each → assert no network request fired and no error thrown in `frontend/src/pages/ConversationDetailPage.test.tsx`

**Checkpoint**: Frontend behavior verified for navigation, all state views, thread, and placeholders.

---

## Phase 7: Quickstart Validation & Polish

**Purpose**: End-to-end validation against the running stack and a final quality pass.

- [ ] T037 [P] Run `pytest backend/tests/integration/test_conversation_detail.py -v` and confirm all backend AC tests pass (AC-01–AC-11, AC-12 backend half, AC-14)
- [ ] T038 [P] Run the frontend test suite and confirm all `ConversationDetailPage` tests pass (AC-12 DOM render, AC-13 no side effects, navigation, loading/error/forbidden/not-found, thread render)
- [ ] T039 Execute all `quickstart.md` flows against the running dev environment: seed a conversation, confirm unread in inbox, open detail (status now `read`), verify mark-as-read in inbox, idempotency re-open (200), 404 (random UUID), 403 cross-tenant, 403 platform admin, and `tenant_id` query-param-ignored. Note any mismatch.
- [ ] T040 Frontend manual check (quickstart "Frontend Check"): click an inbox row → URL `/conversations/{id}`, header + oldest-first thread + six "Coming soon" panels render; return to inbox → unread dot cleared; visit a bogus id → "Conversation not found" view.
- [ ] T041 Only if T039/T040 reveal a doc mismatch: update `quickstart.md` to match the implemented behavior (do not modify other features' specs).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — core of the feature
- **US2 (Phase 4)**: Mechanism implemented in Phase 2/3 (T005, T014); this phase adds behavior tests — depends on T014, T016 and the inbox endpoint (Spec 004) for AC-10
- **US3 (Phase 5)**: Frontend panels depend on `ConversationDetailPage` (T023); backend placeholder test depends on T015
- **Frontend Tests (Phase 6)**: Depend on the frontend page + components (T017–T024, T030–T031) and Spec 004 inbox item for navigation (T032)
- **Quickstart & Polish (Phase 7)**: Depends on all prior phases

### Within Each User Story

- Tests MUST be written (and confirmed to fail) before implementing the corresponding backend task
- Schema (T004) before service (T005, T014) before route (T015) before router mount (T016)
- API client (T017) before hook (T018) before page (T023) before route change (T024)
- Leaf components (`MessageBubble` T021, `ClientHeader` T020, `ConversationStates` T019, `AiPlaceholderPanel` T030) before `MessageThread` (T022) / `ConversationDetailPage` (T023)

### Parallel Opportunities

- T006–T013 (US1 backend tests) can run in parallel with each other (same file, distinct test functions)
- T017 (API client), T019 (ConversationStates), T020 (ClientHeader), T021 (MessageBubble) can run in parallel within US1
- T025–T028 (US2 tests) can run in parallel
- T030 (AiPlaceholderPanel) can run in parallel with any other component work
- T032–T036 (frontend tests) can run in parallel with each other
- T037 and T038 (test-suite runs) can run in parallel

---

## Parallel Example: User Story 1 Backend Tests

```bash
# Run US1 backend tests in parallel (same file, different test functions):
Task T006: test_detail_returns_messages_in_chronological_order
Task T007: test_message_fields_complete_body_timestamp_direction
Task T008: test_header_returns_client_name_contact_status
Task T009: test_cross_tenant_conversation_returns_403
Task T010: test_nonexistent_conversation_returns_404
Task T011: test_platform_admin_blocked_with_403
Task T012: test_conversation_with_no_messages_returns_empty_thread
Task T013: test_tenant_id_query_param_is_ignored

# Then build US1 frontend leaf components in parallel:
Task T017: getConversationDetail() API client → frontend/src/api/conversations.ts
Task T019: ConversationStates → frontend/src/components/conversation/ConversationStates.tsx
Task T020: ClientHeader → frontend/src/components/conversation/ClientHeader.tsx
Task T021: MessageBubble → frontend/src/components/conversation/MessageBubble.tsx
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup & dependency review (confirm 001–004 reuse; index decision)
2. Complete Phase 2: Foundational — schemas + `mark_inbound_read` (CRITICAL)
3. Complete Phase 3: US1 — endpoint (404/403/200) + detail page with header, thread, state views
4. **STOP and VALIDATE**: run US1 tests; verify the page renders real data and tenant isolation holds
5. Complete Phase 4: US2 — verify mark-as-read scope, idempotency, and inbox `total_unread` decrement
6. **STOP and VALIDATE**: run US1 + US2 tests
7. The detail page is now a usable MVP (thread + read-marking)

### Incremental Delivery

1. Setup + Foundational → schemas + service helper ready
2. US1 → endpoint + detail page (**MVP deliverable**)
3. US2 → mark-as-read behavior confirmed end-to-end with the inbox
4. US3 → six AI placeholder panels in place
5. Frontend tests → navigation/state/thread/placeholder coverage
6. Quickstart & Polish → full suite green, quickstart validated

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- **No entity schema migrations** — only the conditional `messages(conversation_id, sent_at)` index (T002), added solely if absent
- `tenant_id` is always derived from the JWT (`get_current_tenant_context`) — never from path, query, or body (FR-004, SR-01, AC-14)
- 404 (does not exist) vs 403 (exists, wrong tenant) is achieved by fetching the conversation WITHOUT a tenant filter then comparing `tenant_id` (SR-04); the 403 path returns no conversation content
- Mark-as-read runs server-side as a side effect of GET, inside the same transaction, before the thread SELECT — strictly `direction=inbound AND status=unread`, idempotent (FR-008/009, AC-07/08/09)
- The detail page is **read-only** for MVP — no reply, no status mutation, no task/escalation actions; the six AI panels are presentational only and trigger nothing (FR-010/011, AC-13)
- Full untruncated bodies are returned only by this detail endpoint; the inbox list keeps preview truncation (SR-05, FR-012)
- The `/conversations/:id` route already exists from Spec 004 — this feature only swaps the stub component for `ConversationDetailPage` (no new route registration)
