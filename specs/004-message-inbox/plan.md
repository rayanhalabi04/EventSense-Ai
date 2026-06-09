# Implementation Plan: Message Inbox

**Branch**: `004-message-inbox` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-message-inbox/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant foundation, tenant context, tenant-scoped service rules, cross-tenant 403 contract
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): `conversations`, `messages`, and `messages.status` (`unread`/`read`); provides the data the inbox displays

---

## Summary

Build a read-only tenant-scoped inbox that lists conversations with latest-message previews, unread indicators, and status badges. `GET /api/v1/inbox` handles filtering (unread/read, conversation status), search (client name, contact, message body), and pagination (20/page). `GET /api/v1/inbox/summary` provides lightweight navbar badge counts before the inbox page loads. The frontend `InboxPage` synchronises filter state to URL search params for browser-nav compatibility. Zero schema changes — this feature reads Spec 003 conversations/messages.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2.x async, pydantic v2 (validators), python-math (built-in)
- Frontend: React 18, `react-router-dom` v6 (`useSearchParams`), Vite 5, Tailwind CSS, shadcn/ui (`Badge`, `Input`, `Select`, `Button`, `Skeleton`)

**Storage**: PostgreSQL 15 — **no migrations needed**

**Testing**: pytest + pytest-asyncio (backend)

**Target Platform**: Linux server (backend), browser (frontend)

**Project Type**: Web application — FastAPI REST backend + React SPA frontend

**Performance Goals**: Standard web app targets. Inbox loads within standard user expectations for page render.

**Constraints**:
- `tenant_id` from JWT only — inbox query always has `WHERE conversations.tenant_id = :tenant_id`
- Preview truncated server-side to 100 chars — client never receives full message bodies from the list endpoint
- `total_unread` always reflects tenant-wide state, independent of active filters
- Frontend ignores 0-1 character search terms; backend treats omitted/blank search as no search
- Platform Admin receives 403

**Scale/Scope**: MVP — two demo tenants; ILIKE search sufficient; no full-text index needed.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/004-message-inbox/
├── plan.md              # This file
├── research.md          # Phase 0: 9 design decisions
├── data-model.md        # Phase 1: SQL query logic, Pydantic schemas, frontend state shape
├── quickstart.md        # Phase 1: curl guide + pagination + isolation tests
├── contracts/
│   └── api-contracts.md # Phase 1: endpoint contract + filter interaction table
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files added by this feature:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── inbox.py                   # GET /api/v1/inbox route handler
│   ├── services/
│   │   └── inbox_service.py           # get_inbox() + truncate_preview() + total_unread query
│   └── schemas/
│       └── inbox.py                   # InboxFilters, InboxItemResponse, InboxResponse
└── tests/
    └── integration/
        └── test_inbox.py              # AC-01 through AC-15 integration tests

frontend/
└── src/
    ├── api/
    │   └── inbox.ts                   # getInbox(params: InboxQueryParams) Axios call
    ├── hooks/
    │   └── useInbox.ts                # filter state, URLSearchParams sync, fetch, error
    ├── pages/
    │   └── InboxPage.tsx              # /inbox route; orchestrates sub-components
    └── components/inbox/
        ├── InboxFilters.tsx           # unread toggle + conversation status select
        ├── InboxSearch.tsx            # debounced text input (300ms, ignores 0-1 char terms)
        ├── InboxList.tsx              # renders list or delegates to InboxEmptyState
        ├── InboxItem.tsx              # single conversation card; click → /conversations/{id}
        ├── InboxEmptyState.tsx        # global-empty vs filtered-empty variants
        └── InboxPagination.tsx        # previous/next buttons + "Page X of Y" text
```

Existing files modified:

```
backend/app/main.py           # ADD: mount inbox router at /api/v1
frontend/src/App.tsx          # ADD: /inbox route; /conversations/:id stub route
frontend/src/components/
  NavBar.tsx (or Sidebar.tsx) # ADD: unread badge on inbox nav link (reads totalUnread from useInbox)
```

---

## In Scope for This Feature

| Area | What is built |
|------|--------------|
| `inbox.py` (schema) | `InboxFilters` with Pydantic v2 validators, `InboxItemResponse`, `InboxResponse`, `InboxSummaryResponse` |
| `inbox_service.py` | `get_inbox()` and `get_summary()` — tenant-scoped latest message, unread count, summary count queries; `truncate_preview()` |
| `GET /api/v1/inbox` | Route handler: `require_role(staff, manager)`; calls `InboxService.get_inbox()`; returns `InboxResponse` |
| `GET /api/v1/inbox/summary` | Route handler: `require_role(staff, manager)`; returns navbar counts |
| Router mount | Registered at `/api/v1` prefix in `main.py` |
| `inbox.ts` (API) | `getInbox(params)` function with typed query params and response |
| `useInbox.ts` (hook) | Filter state; `useSearchParams` sync; debounced search (300ms); `getInbox` call; `isLoading`/`error` state |
| `InboxPage.tsx` | `/inbox` route; ProtectedRoute + RoleGuard; assembles all sub-components |
| `InboxFilters.tsx` | Unread-only toggle (shadcn Toggle/Switch) + status Select dropdown |
| `InboxSearch.tsx` | Text input with 300ms debounce; clears on X button |
| `InboxList.tsx` | Maps `items` to `InboxItem` rows; shows `InboxEmptyState` when empty |
| `InboxItem.tsx` | Card/row: client name + contact badge; preview; timestamp; unread dot; status badge; click → `navigate('/conversations/' + id)` |
| `InboxEmptyState.tsx` | Two variants: global empty ("No messages yet — use the simulator") and filtered empty ("No conversations match your filters — clear filters") |
| `InboxPagination.tsx` | Previous/next buttons; disabled when on first/last page; "Page X of Y" |
| Nav badge | `GET /api/v1/inbox/summary` drives the nav item before inbox load; `totalUnread` from `useInbox` updates after inbox fetch |
| `/conversations/:id` stub | Placeholder route rendering "Conversation detail coming soon" (Spec 005 placeholder) |
| Integration tests | `test_inbox.py` — 15 tests covering AC-01 through AC-15 |

---

## Deferred to Later Features

| Item | Target |
|------|--------|
| Message detail page | Spec 005 — Conversation Detail |
| Mark as read / mark as unread | Post-inbox feature (requires `PATCH /messages/{id}/read`) |
| Real-time inbox updates (WebSocket) | Post-MVP |
| PostgreSQL full-text search | Post-MVP performance enhancement |
| Sorting options beyond updated_at DESC | Out of scope per spec |
| Bulk actions | Out of scope per spec |
| Assigning conversations | Post-MVP |

---

## Inbox Service Design

### `truncate_preview(body, max_len=100) -> str | None`

```python
def truncate_preview(body: str | None, max_len: int = 100) -> str | None:
    if body is None:
        return None
    return body[:max_len] + ("…" if len(body) > max_len else "")
```

### `get_inbox(session, tenant_id, filters) -> InboxResponse`

Key steps (see `data-model.md` for full SQLAlchemy code):
1. Build correlated subquery for latest message ID per conversation
2. Build correlated subquery for unread message count per conversation
3. Construct base query: `conversations LEFT JOIN messages ON latest-message subquery`
4. Apply filters: status, unread_only, search (ILIKE on client_name, client_contact, messages.body via EXISTS)
5. Count total for pagination (`SELECT COUNT(*) FROM subquery`)
6. Apply `ORDER BY updated_at DESC`, `LIMIT page_size`, `OFFSET (page-1)*page_size`
7. Run separate `total_unread` query (tenant-wide, ignores filters)
8. Build and return `InboxResponse`

---

## Frontend Hook Design (`useInbox`)

```typescript
// Reads from URLSearchParams on mount; writes back on every change
const [searchParams, setSearchParams] = useSearchParams();

// Derived filter state
const filters: InboxFilters = {
  unreadOnly: searchParams.get("unread_only") === "true",
  status: (searchParams.get("status") as ConversationStatus) || null,
  search: searchParams.get("search") || "",
  page: parseInt(searchParams.get("page") || "1"),
};

// Debounced search: only updates URLSearchParams (and triggers fetch) after 300ms idle
const debouncedSearch = useDebounce(searchTerm, 300);

// Fetch on mount + on filter change
useEffect(() => {
  fetchInbox(filters);
}, [filters.unreadOnly, filters.status, debouncedSearch, filters.page]);

// setFilter writes the new value to URLSearchParams and resets page to 1
const setFilter = (key, value) => {
  setSearchParams(prev => { prev.set(key, value); prev.set("page", "1"); return prev; });
};
```

---

## Validation Rules (authoritative — backend)

| Parameter | Rule | On violation |
|-----------|------|-------------|
| `search` | Blank/omitted becomes no search; backend only applies search when length ≥ 2 | 200 |
| `status` | Must be `open`, `closed`, `escalated`, or absent | 422 |
| `page` | Integer ≥ 1 | 422 |
| Auth | Bearer token valid and non-expired | 401 |
| Role | `staff` or `manager` | 403 |
| `tenant_id` | Always from JWT — no request param accepted | — |

---

## Test Coverage (`tests/integration/test_inbox.py`)

| Test | Acceptance Criterion |
|------|---------------------|
| `test_inbox_returns_all_tenant_conversations_ordered_by_updated_at` | AC-01 |
| `test_inbox_item_fields_are_complete_and_correct` | AC-02 |
| `test_inbox_empty_for_fresh_tenant` | AC-03 |
| `test_platform_admin_blocked_from_inbox` | AC-04, AC-12 |
| `test_unread_only_filter_excludes_read_conversations` | AC-04 |
| `test_status_filter_returns_only_matching_conversations` | AC-05 |
| `test_combined_unread_and_status_filter` | AC-06 |
| `test_search_by_client_name_case_insensitive` | AC-07 |
| `test_search_by_message_body` | AC-08 |
| `test_search_and_filter_combined` | AC-09 |
| `test_no_match_returns_empty_items_with_nonzero_total_unread` | AC-10 |
| `test_tenant_a_inbox_empty_for_tenant_b_user` | AC-11 |
| `test_total_unread_reflects_tenant_wide_state_ignoring_filters` | AC-13 |
| `test_pagination_page_1_returns_20_items` | AC-15 |
| `test_pagination_page_2_returns_remaining_items` | AC-15 |
