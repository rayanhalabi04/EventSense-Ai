---

description: "Task list for Message Inbox feature implementation"
---

# Tasks: Message Inbox

**Branch**: `004-message-inbox` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/004-message-inbox/`

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: tenant foundation, tenant-scoped service rules, cross-tenant 403 contract
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`
- Spec 003 — Message Simulator: `messages.status` column (`unread`/`read`)

**Tech stack**: FastAPI + SQLAlchemy 2.x async + pydantic v2 (backend) · React 18 + react-router-dom v6 + Tailwind + shadcn/ui (frontend)

**No schema migrations required** — this feature is read-only over existing tables.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US5]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup

**Purpose**: Verify test infrastructure is ready for integration tests.

- [ ] T001 Verify `backend/tests/integration/` directory exists and contains `__init__.py`; create both if absent (required before any test file can be added in Phase 3+)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic schemas and the preview helper are shared by the service, route handler, and all integration tests. Nothing in Phases 3–7 can compile without them.

**⚠️ CRITICAL**: All user story phases depend on this phase completing first.

- [ ] T002 Create `InboxFilters` (Pydantic v2 validators; normalize blank search to `None`), `InboxItemResponse`, `InboxResponse`, and `InboxSummaryResponse` in `backend/app/schemas/inbox.py`
- [ ] T003 [P] Implement `truncate_preview(body: str | None, max_len: int = 100) -> str | None` helper function in `backend/app/services/inbox_service.py`

**Checkpoint**: Schemas importable — Phase 3 can begin.

---

## Phase 3: User Story 1 — View Tenant Conversation List (Priority: P1) 🎯 MVP

**Goal**: An authenticated staff or manager user opens `/inbox` and sees all conversations in their tenant, ordered by `updated_at DESC`, each showing client name, contact, truncated message preview (≤ 100 chars), last-message timestamp, unread dot, and status badge. Platform Admin gets 403. Other tenants' conversations are never visible.

**Independent Test**: Inject two simulator messages into different conversations for Tenant A. Query `GET /api/v1/inbox` as Tenant A staff — verify both conversations appear in correct order with all fields populated. Query as Tenant B staff — verify empty list.

### Tests for User Story 1

> Write tests first; confirm they fail before implementing Phase 3 backend tasks.

- [ ] T004 [US1] Write `test_inbox_returns_all_tenant_conversations_ordered_by_updated_at` (AC-01) in `backend/tests/integration/test_inbox.py` — seeds 3 conversations, asserts all 3 returned in `updated_at DESC` order
- [ ] T005 [P] [US1] Write `test_inbox_item_fields_are_complete_and_correct` (AC-02) in `backend/tests/integration/test_inbox.py` — asserts all `InboxItemResponse` fields present and correct values
- [ ] T006 [P] [US1] Write `test_inbox_empty_for_fresh_tenant` (AC-03) in `backend/tests/integration/test_inbox.py` — fresh tenant returns `items=[]`, `total=0`, `total_unread=0`
- [ ] T007 [P] [US1] Write `test_platform_admin_blocked_from_inbox` (AC-04/AC-12) in `backend/tests/integration/test_inbox.py` — platform admin token → `GET /api/v1/inbox` → 403 with `INSUFFICIENT_ROLE`
- [ ] T008 [P] [US1] Write `test_tenant_a_inbox_empty_for_tenant_b_user` (AC-11) in `backend/tests/integration/test_inbox.py` — inject conversations for Tenant A, query as Tenant B staff, assert empty list

### Implementation for User Story 1

- [ ] T009 [US1] Implement `get_inbox(session, tenant_id, filters) -> InboxResponse` in `backend/app/services/inbox_service.py` with: correlated subquery for latest message per conversation including `Message.tenant_id == tenant_id`; correlated subquery for unread count; base query joining `conversations LEFT JOIN messages`; `WHERE conversations.tenant_id = :tenant_id`; `ORDER BY updated_at DESC`; pagination; `COUNT(*)` for `total`; `COUNT(DISTINCT conversation_id)` for `total_unread`; response mapping with `truncate_preview()`
- [ ] T010 [US1] Implement `GET /api/v1/inbox` route handler with `require_role(staff, manager)`, `InboxFilters` query param injection, and `InboxService.get_inbox()` call in `backend/app/api/v1/inbox.py` (depends on T009)
- [ ] T011 [US1] Mount inbox router at `/api/v1` prefix in `backend/app/main.py` (depends on T010)
- [ ] T012 [P] [US1] Implement `getInbox(params: InboxQueryParams): Promise<InboxResponse>` Axios call with typed query params and response interface in `frontend/src/api/inbox.ts`
- [ ] T013 [US1] Implement `useInbox` hook with `useSearchParams` read on mount, `getInbox` call, `isLoading`/`error` state, and URL-param-derived `filters` object in `frontend/src/hooks/useInbox.ts` (depends on T012)
- [ ] T014 [P] [US1] Create `InboxItem` component showing client name, optional contact badge (shadcn `Badge`), truncated preview, last-message timestamp, unread dot indicator, conversation status badge; clicking the row calls `navigate('/conversations/' + conversation_id)` in `frontend/src/components/inbox/InboxItem.tsx`
- [ ] T015 [P] [US1] Create `InboxEmptyState` component with `variant` prop accepting `"global"` — renders "No client messages yet. Use the Message Simulator to inject a test message." in `frontend/src/components/inbox/InboxEmptyState.tsx`
- [ ] T016 [US1] Create `InboxList` component that maps `items` array to `InboxItem` rows and renders `InboxEmptyState variant="global"` when `items.length === 0` and no filters are active in `frontend/src/components/inbox/InboxList.tsx` (depends on T014, T015)
- [ ] T017 [US1] Create `InboxPage` at `/inbox` with `ProtectedRoute` and `RoleGuard(["staff", "manager"])` assembling `InboxSearch`, `InboxFilters`, `InboxList`, and `InboxPagination` sub-components; passes `useInbox` state as props in `frontend/src/pages/InboxPage.tsx` (depends on T013, T016)
- [ ] T018 [US1] Register `/inbox` route pointing to `InboxPage` in `frontend/src/App.tsx` (depends on T017)

**Checkpoint**: US1 fully functional — `GET /api/v1/inbox` returns tenant-scoped list; inbox page renders; tenant isolation and role guard confirmed by tests.

---

## Phase 4: User Story 2 — Filter Conversations (Priority: P1)

**Goal**: Staff applies "unread only" toggle and/or selects a conversation status (open / closed / escalated). The backend narrows the result set using SQL-level filtering so pagination counts remain accurate. Clearing filters restores the full list.

**Independent Test**: Create three conversations — one unread+open, one read+open, one closed. Apply `unread_only=true` → only the first appears. Apply `status=closed` → only the third appears.

### Tests for User Story 2

- [ ] T019 [P] [US2] Write `test_unread_only_filter_excludes_read_conversations` (AC-04) in `backend/tests/integration/test_inbox.py` — mix of read/unread; `?unread_only=true` returns only unread conversations
- [ ] T020 [P] [US2] Write `test_status_filter_returns_only_matching_conversations` (AC-05) in `backend/tests/integration/test_inbox.py` — `?status=closed` returns only closed conversations
- [ ] T021 [P] [US2] Write `test_combined_unread_and_status_filter` (AC-06) in `backend/tests/integration/test_inbox.py` — `?unread_only=true&status=open` returns only conversations matching both criteria
- [ ] T022 [P] [US2] Write `test_no_match_returns_empty_items_with_nonzero_total_unread` (AC-10) in `backend/tests/integration/test_inbox.py` — filter with no matching conversations returns `items=[]`, `total=0`, but `total_unread > 0` (tenant-wide)

### Implementation for User Story 2

- [ ] T023 [US2] Extend `get_inbox()` in `backend/app/services/inbox_service.py` to apply `status` filter (`WHERE conversations.status == filters.status`) and `unread_only` filter (`WHERE unread_sq > 0`) when set (depends on T009)
- [ ] T024 [P] [US2] Add `variant="filtered"` to `InboxEmptyState` rendering "No conversations match your current filters." with a "Clear filters" button that calls `clearFilters()` in `frontend/src/components/inbox/InboxEmptyState.tsx`
- [ ] T025 [US2] Create `InboxFilters` component with shadcn `Switch` for unread-only toggle and shadcn `Select` dropdown for conversation status (All / Open / Closed / Escalated); calls `setFilter` on change in `frontend/src/components/inbox/InboxFilters.tsx`
- [ ] T026 [US2] Extend `useInbox` with `setFilter(key, value)` writing to `URLSearchParams` and resetting `page` to 1, and `clearFilters()` resetting all params; update `InboxList` to pass `hasActiveFilters` to `InboxEmptyState` to select the correct variant; wire `InboxFilters` into `InboxPage` in `frontend/src/hooks/useInbox.ts`, `frontend/src/components/inbox/InboxList.tsx`, and `frontend/src/pages/InboxPage.tsx`

**Checkpoint**: US1 + US2 both functional — filters narrow the list server-side; pagination counts stay accurate under filters.

---

## Phase 5: User Story 3 — Search Conversations (Priority: P2)

**Goal**: Staff types a search term (≥ 2 characters) into the search field. The backend returns only conversations whose `client_name`, `client_contact`, or any `messages.body` matches the term (case-insensitive ILIKE). Search can be combined with active filters.

**Independent Test**: Create "Alice Johnson" (message: "package prices") and "Bob Smith" (message: "guest count"). Search `alice` → only Alice's conversation. Search `cancel` → only conversations containing that word in any message body.

### Tests for User Story 3

- [ ] T027 [P] [US3] Write `test_search_by_client_name_case_insensitive` (AC-07) in `backend/tests/integration/test_inbox.py` — `?search=alice` matches "Alice Johnson" conversation (case-insensitive)
- [ ] T028 [P] [US3] Write `test_search_by_message_body` (AC-08) in `backend/tests/integration/test_inbox.py` — `?search=deposit` matches conversation containing that word in message body
- [ ] T029 [P] [US3] Write `test_search_and_filter_combined` (AC-09) in `backend/tests/integration/test_inbox.py` — `?search=alice&unread_only=true` returns only unread conversations matching "alice"

### Implementation for User Story 3

- [ ] T030 [US3] Extend `get_inbox()` in `backend/app/services/inbox_service.py` to apply ILIKE search when `filters.search` is set: `OR(conversations.client_name.ilike(pattern), conversations.client_contact.ilike(pattern), EXISTS(messages subquery with body.ilike(pattern) AND tenant_id filter))` (depends on T023)
- [ ] T031 [P] [US3] Create `InboxSearch` component with a shadcn `Input`, 300ms debounced `onChange`, frontend behavior that ignores 0-1 character terms, and X clear button resetting the field in `frontend/src/components/inbox/InboxSearch.tsx`
- [ ] T032 [US3] Extend `useInbox` with `setSearch(term)` that stores the raw term in local state and only writes 2+ character terms to `URLSearchParams` (or clears the param for 0-1 chars) after 300ms debounce; wire `InboxSearch` into `InboxPage` in `frontend/src/hooks/useInbox.ts` and `frontend/src/pages/InboxPage.tsx`

**Checkpoint**: US1 + US2 + US3 all functional — search narrows list within the active filter scope.

---

## Phase 6: User Story 4 — Navigate to Conversation Detail (Priority: P2)

**Goal**: Clicking any conversation row navigates the browser to `/conversations/{id}`. A stub page renders at that URL. On returning to the inbox (browser back), all previously active filters and search terms are restored from URL search params.

**Independent Test**: Click a conversation row — verify URL changes to `/conversations/{conversation_id}`. Press browser back — verify inbox URL still contains the original `?status=open&search=alice` params.

- [ ] T033 [P] [US4] Create `ConversationDetailPage` placeholder component rendering "Conversation detail coming soon." in `frontend/src/pages/ConversationDetailPage.tsx`
- [ ] T034 [US4] Register `/conversations/:id` route pointing to `ConversationDetailPage` in `frontend/src/App.tsx`; add frontend navigation test that renders an inbox item, clicks the row, and asserts URL changes to `/conversations/{conversation_id}` in `frontend/src/components/inbox/InboxItem.test.tsx` (depends on T033)

**Checkpoint**: US1–US4 all functional — full read-side workflow: list → filter/search → click → navigate back with state.

---

## Phase 7: User Story 5 — Inbox Shows Correct Unread Count (Priority: P3)

**Goal**: The inbox nav item displays a badge showing the number of tenant conversations with at least one unread message. The count is fetched from `GET /api/v1/inbox/summary` before the inbox page loads. Pagination controls allow navigating beyond page 1.

**Independent Test**: Inject 2 unread conversations → nav badge shows "2". Apply a status filter that hides one — badge still shows "2" (tenant-wide, not filter-scoped). Inject 25 total conversations → page 1 shows 20, page 2 shows 5.

### Tests for User Story 5

- [ ] T035 [P] [US5] Write `test_inbox_summary_returns_tenant_counts` (AC-13) in `backend/tests/integration/test_inbox.py` — 2 unread conversations; `GET /api/v1/inbox/summary` returns `unread_or_new=2`, `total_open`, and `high_risk_placeholder=0`
- [ ] T036 [P] [US5] Write `test_pagination_page_1_returns_20_items` (AC-15) in `backend/tests/integration/test_inbox.py` — 25 conversations; `?page=1` returns 20 items, `total=25`, `total_pages=2`
- [ ] T037 [P] [US5] Write `test_pagination_page_2_returns_remaining_items` (AC-15) in `backend/tests/integration/test_inbox.py` — 25 conversations; `?page=2` returns 5 items

### Implementation for User Story 5

- [ ] T038 [P] [US5] Create `InboxPagination` component with shadcn `Button` for previous and next; disabled when on first/last page; renders "Page {page} of {totalPages}" in `frontend/src/components/inbox/InboxPagination.tsx`
- [ ] T039 [US5] Extend `useInbox` with `setPage(n)` writing `page` to URLSearchParams; wire `InboxPagination` into `InboxPage` with `page`, `totalPages`, and `setPage` props in `frontend/src/hooks/useInbox.ts` and `frontend/src/pages/InboxPage.tsx` (depends on T038)
- [ ] T040 [US5] Implement `getInboxSummary()` API call and wire `summary.unread_or_new` to the inbox nav item badge in `frontend/src/components/NavBar.tsx` (or `Sidebar.tsx`) — show badge when count > 0, hide when 0

**Checkpoint**: All 5 user stories functional — full MVP complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, error display, and overall quality pass.

- [ ] T041 [P] Run `pytest backend/tests/integration/test_inbox.py -v` and confirm all 15 AC tests pass (AC-01 through AC-15)
- [ ] T042 [P] Validate all `quickstart.md` curl flows against the running dev environment: seed 3 conversations, verify inbox response, test unread/status filters, search by client name and body, tenant isolation, platform admin 403, and pagination with 25 conversations
- [ ] T043 Add frontend error display for API validation errors such as invalid status/page values; short search terms should be handled client-side by clearing/ignoring the search param, not by surfacing a 422 in `frontend/src/hooks/useInbox.ts`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on other user stories
- **US2 (Phase 4)**: Depends on US1 backend service (T009) and US1 frontend hook (T013); extends both
- **US3 (Phase 5)**: Depends on US2 service extension (T023); extends it further
- **US4 (Phase 6)**: Depends on US1 frontend (`InboxItem` T014, `App.tsx` T018); adds stub route
- **US5 (Phase 7)**: Depends on US1 hook (T013) for `totalUnread`; adds pagination UI and nav badge
- **Polish (Phase 8)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on other stories
- **US2 (P1)**: Can start after US1 backend is complete (T009); frontend can start after T013
- **US3 (P2)**: Can start after US2 backend extension (T023) is complete
- **US4 (P2)**: Can start in parallel with US2/US3 — only touches `App.tsx` and a new page stub
- **US5 (P3)**: Can start after US1 backend (total_unread already in response); frontend pagination can start after T013

### Within Each User Story

- Tests MUST be written (and confirmed to fail) before implementing the corresponding backend task
- Schemas before service before route
- API client before hook before page before route registration
- Core component before list wrapper before page

### Parallel Opportunities

- T003 (truncate_preview) can run in parallel with T002 (schemas)
- T004–T008 (US1 tests) can all run in parallel with each other
- T012 (API client), T014 (InboxItem), T015 (InboxEmptyState) can run in parallel within US1
- T019–T022 (US2 tests) can all run in parallel
- T024 (InboxEmptyState update) can run in parallel with T025 (InboxFilters component)
- T027–T029 (US3 tests) can all run in parallel
- T033 (ConversationDetailPage) can run in parallel with any US2/US3 work
- T035–T037 (US5 tests) can all run in parallel
- T038 (InboxPagination component) can run in parallel with T035–T037
- T041 and T042 (validation tasks) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Run US1 tests in parallel (all target the same test file but different test functions):
Task T004: test_inbox_returns_all_tenant_conversations_ordered_by_updated_at
Task T005: test_inbox_item_fields_are_complete_and_correct
Task T006: test_inbox_empty_for_fresh_tenant
Task T007: test_platform_admin_blocked_from_inbox
Task T008: test_tenant_a_inbox_empty_for_tenant_b_user

# Then build US1 frontend components in parallel:
Task T012: getInbox() API client → frontend/src/api/inbox.ts
Task T014: InboxItem component → frontend/src/components/inbox/InboxItem.tsx
Task T015: InboxEmptyState component → frontend/src/components/inbox/InboxEmptyState.tsx
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — schemas + helper (CRITICAL)
3. Complete Phase 3: US1 — core list, tenant isolation, role guard, all fields
4. **STOP and VALIDATE**: run US1 tests, verify inbox page renders with real data
5. Complete Phase 4: US2 — filters
6. **STOP and VALIDATE**: run US1 + US2 tests, verify filters work with accurate pagination counts
7. Deploy/demo if ready — the inbox is usable with the core list + filters

### Incremental Delivery

1. Setup + Foundational → schemas ready
2. US1 → basic inbox page with full list and tenant isolation (**MVP deliverable**)
3. US2 → filter by unread/status → test independently
4. US3 → search → test independently
5. US4 → navigation stub → confirm back-nav state preservation
6. US5 → pagination UI + nav badge → test independently
7. Polish → full 15-test suite passes, quickstart validated

### Parallel Team Strategy

With multiple developers (after Phase 2 completes):
- Developer A: US1 backend (T009–T011) → US2 backend (T023) → US3 backend (T030)
- Developer B: US1 frontend (T012–T018) → US2 frontend (T024–T026) → US3 frontend (T031–T032)
- Developer C: Write all integration tests (T004–T008, T019–T022, T027–T029, T035–T037) and US4 stub (T033–T034)

---

## Notes

- `[P]` tasks write to different files and have no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a specific user story for traceability and independent testing
- No schema migrations — zero `alembic` commands needed for this feature
- Each user story phase is independently completable and testable before moving to the next
- `GET /api/v1/inbox/summary` drives the US5 nav badge before the inbox page loads; `total_unread` remains in `get_inbox()` for consistency after page fetch
- Search is tenant-scoped at the SQL level (`AND messages.tenant_id = :tenant_id` inside the EXISTS subquery) — search cannot cross tenant boundaries
- Filter state lives in `URLSearchParams` — browser back/refresh always restores the same filtered view (no local state to lose)
- Inbox is read-only — no `PATCH`, `POST`, or `DELETE` operations in this feature
