# Feature Specification: Message Inbox

**Feature Branch**: `004-message-inbox`

**Created**: 2026-06-03

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)

**Input**: User description: "Message Inbox — a tenant-scoped view of incoming client conversations and messages, with filtering, search, and navigation to a future detail page."

---

## Goal

Give staff and managers a single place to see all incoming client conversations for their agency. The inbox lists every conversation in the tenant, shows the most recent message as a preview, and surfaces unread status, conversation state, and client identity at a glance. Filters and search let staff quickly find the conversations that need attention. The inbox is the primary entry point into the client communication workflow — it surfaces what is waiting to be read, and will later anchor AI-suggested reply generation and task creation.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner who checks the inbox regularly to see new inbound client messages, identify unread conversations, and navigate into conversations to act on them. |
| **Manager** | A senior planner or agency head with the same inbox view as Staff. Managers also use the inbox to spot escalated conversations and oversee team workload. |

Platform Admin has no access to the inbox or any tenant content.

---

## User Stories

### User Story 1 — View Tenant Conversation List (Priority: P1)

A staff planner opens the inbox and sees a list of all conversations in their tenant, ordered by most recently updated. Each row shows the client name, optional contact detail, a preview of the most recent message, the time of the last message, the unread/read indicator, and the conversation status (open, closed, escalated).

**Why this priority**: Seeing the conversation list is the foundational capability of the inbox. Without it, staff have no way to know what client messages exist. All filtering, search, and navigation flows depend on this list being present and accurate.

**Independent Test**: Inject two simulator messages into different client conversations. Open the inbox as an authenticated Staff user. Verify both conversations appear, each showing the correct client name, most-recent message preview, and unread indicator. Verify a third tenant's conversations are completely absent.

**Acceptance Scenarios**:

1. **Given** an authenticated Staff user with at least one conversation in their tenant, **When** they open the inbox, **Then** they see a list of conversations ordered by most-recently-updated first.
2. **Given** a conversation in the list, **When** the inbox renders it, **Then** it shows: client name, client contact (if available), a truncated preview of the most recent message body (≤ 100 characters), the timestamp of the last message, the unread/read indicator, and the conversation status badge.
3. **Given** no conversations exist in the tenant, **When** the inbox is opened, **Then** a clear empty state is shown with a message directing staff to use the simulator.
4. **Given** an authenticated Platform Admin, **When** they attempt to access the inbox, **Then** they receive a permission-denied response — no conversation data is returned.

---

### User Story 2 — Filter Conversations (Priority: P1)

A staff planner wants to focus on unread messages. They apply the "unread" filter and the list updates to show only conversations that have at least one unread message. They can also filter by conversation status (open, closed, escalated) to find conversations in specific states.

**Why this priority**: An unfiltered inbox can quickly grow too long to scan. Filters let staff triage efficiently — particularly "show me only what I haven't responded to yet."

**Independent Test**: Create three conversations: one with an unread message (open), one with all messages read (open), one that is closed. Apply the "unread only" filter. Verify only the first conversation appears. Apply the "closed" status filter. Verify only the third conversation appears.

**Acceptance Scenarios**:

1. **Given** a mix of unread and read conversations, **When** the "unread only" filter is applied, **Then** only conversations with at least one unread message are shown.
2. **Given** conversations in multiple statuses, **When** a status filter (open / closed / escalated) is applied, **Then** only conversations matching that status are shown.
3. **Given** filters are applied, **When** no conversations match, **Then** the filtered empty state is shown (distinct from the all-empty state: "No conversations match your current filters").
4. **Given** a filter is active, **When** the user clears all filters, **Then** the full unfiltered list is restored.

---

### User Story 3 — Search Conversations (Priority: P2)

A staff planner wants to find a message from a client called "Alice". They type "Alice" into the search field. The list instantly narrows to conversations where the client name or any message body contains the search term.

**Why this priority**: As message volume grows, filtering alone is insufficient. Search allows staff to retrieve a specific client thread or message without manually scrolling.

**Independent Test**: Create conversations for "Alice Johnson" and "Bob Smith". Type "alice" into the search field. Verify only Alice's conversation appears. Type "deposit" into the search field. Verify only conversations whose message bodies contain "deposit" appear.

**Acceptance Scenarios**:

1. **Given** a search term is entered, **When** the inbox updates, **Then** only conversations whose client name contains the term (case-insensitive) or whose message bodies contain the term are shown.
2. **Given** no conversations match the search term, **When** the search result renders, **Then** a "No conversations match your search" empty state is shown.
3. **Given** a search term is entered alongside an active status filter, **When** the inbox updates, **Then** both criteria are applied simultaneously — conversations must match both the filter and the search.
4. **Given** the search field is cleared, **When** the inbox updates, **Then** the full list (respecting any active filters) is restored.

---

### User Story 4 — Navigate to Conversation Detail (Priority: P2)

A staff planner clicks on a conversation row in the inbox. The application navigates them to the conversation detail page where they will be able to read the full message thread and take action. The detail page itself is not part of this feature, but the navigation from the inbox must be in place.

**Why this priority**: The inbox is only useful if staff can act on what they see. Navigation to the detail page completes the read-side workflow and is required before AI reply suggestions can be triggered from the inbox.

**Independent Test**: Click a conversation row in the inbox. Verify the browser navigates to `/conversations/{id}`. Verify the URL contains the correct conversation ID. (The detail page may render a placeholder at this stage.)

**Acceptance Scenarios**:

1. **Given** a conversation is visible in the inbox, **When** the user clicks the row, **Then** they are navigated to the conversation detail URL (`/conversations/{id}`).
2. **Given** the conversation ID belongs to a different tenant, **When** the detail URL is accessed directly, **Then** the user receives a permission-denied response (enforced by the existing cross-tenant guard from Spec 001, not by this feature).
3. **Given** the user navigates back from the detail page to the inbox, **When** the inbox renders, **Then** any previously active filters and search term are still applied (state is preserved).

---

### User Story 5 — Inbox Shows Correct Unread Count (Priority: P3)

A staff planner sees a badge or indicator on the inbox navigation item showing the total number of conversations with unread messages in their tenant. This helps them know at a glance whether there is work waiting before they even open the inbox page.

**Why this priority**: A running unread count is a standard inbox UX pattern. It reduces the need to open the inbox to check for new messages. Lower priority because the inbox itself (US1–US4) must exist first.

**Independent Test**: Inject one unread simulator message. Verify the inbox navigation item shows "1". Inject a second unread message for a different client. Verify the badge updates to "2". Mark one conversation as read (when that feature exists). Verify the badge decrements.

**Acceptance Scenarios**:

1. **Given** two conversations have unread messages, **When** the user views the navigation sidebar, **Then** the inbox link shows a badge with the count "2".
2. **Given** no conversations have unread messages, **When** the user views the navigation sidebar, **Then** no badge is shown (or badge shows "0" — hidden).
3. **Given** the unread count changes (e.g., a new message arrives via simulator), **When** the user opens the inbox, **Then** the badge count reflects the current state.

---

### Edge Cases

- What if two conversations exist with the same client name but different contact details? Both appear as separate rows — the inbox does not merge them.
- What if the message preview contains a very long unbroken string (no spaces)? Preview is hard-truncated at 100 characters regardless — ellipsis appended.
- What if a conversation has no messages at all (was created without a message)? The preview field shows "No messages yet" and the timestamp shows the conversation creation time.
- What if pagination results in a very large list? The inbox paginates at 20 conversations per page; a "Load more" or page navigation control is shown when there are more than 20.
- What if the search term is fewer than 2 characters? Short search terms (less than 2 characters) are ignored — no search is triggered until 2+ characters are typed.

---

## MVP Scope

- Inbox page accessible to `staff` and `manager` roles only
- List of all tenant conversations ordered by `updated_at` descending
- Each row displays: client name, client contact (if present), truncated message preview (≤ 100 chars), last message timestamp, unread/read indicator, conversation status badge
- Filter by read status: all / unread only
- Filter by conversation status: all / open / closed / escalated
- Text search across client name and message bodies (minimum 2 characters to trigger)
- Filters and search can be combined
- Empty state for no conversations (with simulator hint)
- Filtered/searched empty state (distinct message)
- Click a row navigates to `/conversations/{id}` (detail page is a stub/placeholder)
- Unread badge count on inbox navigation item via lightweight inbox summary endpoint
- Pagination: 20 conversations per page
- Tenant isolation enforced by backend; Platform Admin blocked
- Backend derives `tenant_id` from authenticated session only

---

## Out of Scope

- Conversation detail page and message thread view (separate feature)
- Marking messages or conversations as read/unread from the inbox (separate feature — requires a dedicated action)
- Real-time updates or push notifications when new messages arrive
- Sorting options beyond most-recently-updated (e.g., sort by client name, unread count)
- Bulk actions (bulk mark as read, bulk close conversations)
- Assigning conversations to specific staff members
- Real WhatsApp API integration
- Exporting or printing the inbox

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Read status filter | UI filter control | `all` (default) or `unread` |
| Conversation status filter | UI filter control | `all` (default), `open`, `closed`, or `escalated` |
| Search term | Search input | Frontend ignores 0-1 character terms; 2+ characters search against client name and message bodies |
| Page number | Pagination control | Defaults to page 1; 20 items per page |

---

## Outputs

| Output | Description |
|--------|-------------|
| Conversation list | Paginated list of tenant conversations with preview data, ordered by `updated_at` descending |
| Inbox summary | Tenant-scoped counts for navbar badge, including unread/new count |
| Filtered/searched list | Subset of conversations matching active filter + search criteria |
| Empty state | Friendly message when list is empty (global empty or filtered empty — distinct messages) |
| Navigation target | `/conversations/{id}` URL on row click |
| 403 Forbidden | Returned for Platform Admin access attempts or cross-tenant requests |

---

## Main Workflow

1. **Staff opens the inbox** — Navigates to the inbox page (e.g., from the sidebar). The page loads with no active filters and the full conversation list.
2. **Conversations load** — The backend returns all conversations for the authenticated tenant, ordered by most-recently-updated, with the latest message preview and unread status for each.
3. **Staff scans the list** — Each row shows client identity, message preview, timestamp, and status. Unread conversations are visually distinguished (bold name or unread dot).
4. **Staff optionally filters or searches** — Applies a read-status filter, a conversation-status filter, or types a search term. The list updates to reflect the criteria.
5. **Staff clicks a conversation** — Navigated to `/conversations/{id}` to view the full thread and take action.
6. **Badge updates** — The unread count badge on the inbox nav item reflects the current number of conversations with unread messages.

---

## Alternative Workflows

### Empty Inbox

1. Staff opens the inbox.
2. No conversations exist in the tenant.
3. The page shows a friendly empty state: "No client messages yet. Use the Message Simulator to inject a test message."
4. A button or link to the simulator may be present.

### No Matches After Filter / Search

1. Staff applies a filter or enters a search term.
2. No conversations match the criteria.
3. The list area shows: "No conversations match your current filters." with a "Clear filters" action.
4. The empty state is visually distinct from the global empty state.

### Filters Combined with Search

1. Staff applies the "unread only" filter and types "Alice" in the search.
2. The backend returns only conversations that are both unread AND match "Alice" in client name or message body.
3. If one criterion matches but not the other, the conversation is excluded.

### Platform Admin Access Attempt

1. An authenticated Platform Admin navigates to the inbox URL.
2. The page renders the role guard and shows a 403 Forbidden message.
3. No conversation data is loaded or exposed.

### Direct URL Access with Expired Session

1. Staff opens the inbox URL directly with an expired token.
2. The session check detects the expired token.
3. Staff is redirected to the login page.
4. After re-authenticating, they are returned to the inbox.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Inbox shows all conversations for the authenticated tenant, ordered by most-recently-updated | Integration test: inject 3 conversations; verify all 3 appear in correct order |
| AC-02 | Each inbox row shows client name, contact (if available), message preview (≤ 100 chars), timestamp, unread indicator, and status badge | Integration test + visual check: assert all fields present in API response |
| AC-03 | Empty inbox displays a tenant-specific empty state with simulator hint | Integration test: fresh tenant + GET inbox → assert empty-state response |
| AC-04 | "Unread only" filter returns only conversations with at least one unread message | Integration test: mix of read/unread conversations; assert filter excludes read-only conversations |
| AC-05 | Conversation status filter returns only conversations matching the selected status | Integration test: assert `?status=closed` returns only closed conversations |
| AC-06 | Filters can be combined: applying both unread and status filters narrows the list correctly | Integration test: unread + open filter applied together; assert only matching conversations returned |
| AC-07 | Search by client name (case-insensitive) returns matching conversations | Integration test: "alice" search matches "Alice Johnson" conversation |
| AC-08 | Search by message body content returns matching conversations | Integration test: "deposit" search matches conversation containing that word |
| AC-09 | Search and filter can be combined | Integration test: "alice" + unread filter returns only unread Alice conversations |
| AC-10 | No-match empty state is shown with a "clear filters" affordance | Integration test: search for non-existent term → assert no-results payload |
| AC-11 | Tenant A inbox contains no data from Tenant B | Integration test: inject for Tenant A; query inbox as Tenant B; assert empty list |
| AC-12 | Platform Admin role is blocked from the inbox endpoint with 403 | Integration test: platform admin token → GET /inbox → 403 with INSUFFICIENT_ROLE |
| AC-13 | Unread badge count equals number of conversations with at least one unread message | Integration test: 2 unread conversations → badge count = 2 |
| AC-14 | Clicking a conversation row navigates to `/conversations/{id}` | Front-end test: click row, assert URL changes to correct conversation path |
| AC-15 | Pagination returns 20 conversations per page; subsequent pages return the next batch | Integration test: 25 conversations → page 1 = 20 items, page 2 = 5 items |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Provides tenant isolation rules, tenant context, and tenant-scoped service pattern |
| Spec 002 — Authentication and Roles | Required | Provides JWT auth, `staff`/`manager` role access, `require_role` dependency. Platform Admin is blocked from the inbox. |
| Spec 003 — WhatsApp-Style Message Simulator | Required | Provides `conversations`, `messages`, and the `messages.status` field (`unread`/`read`) that drives the unread filter and badge count. The inbox is only useful once the simulator has populated data. |

---

## AI Behavior

The inbox itself does not invoke AI. However, it is the entry point through which AI features will be accessed. The following design decisions ensure compatibility:

- Each conversation row in the inbox will later include an indicator of whether a suggested reply is available. This field is not part of this spec but the row data structure must be extensible to include it.
- When the AI reply suggestion feature is built, it will be triggered from the conversation detail page (reached via inbox row click) — not from the inbox list itself.
- The inbox's unread/read filtering will remain meaningful even after AI suggestions are introduced, because "unread" reflects whether a staff member has opened the conversation, not whether the AI has processed it.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the authenticated JWT. Any `tenant_id` sent as a query parameter or request body is discarded. The inbox will never serve conversations from a different tenant. |
| **SR-02: Role restriction** | Only `staff` and `manager` roles may access the inbox. Platform Admin receives 403. Unauthenticated requests receive 401. |
| **SR-03: No cross-tenant data exposure** | The backend's tenant filter is unconditional on all inbox queries. Even if a conversation ID is guessed and embedded in a URL, the cross-tenant guard from Spec 001 blocks access. |
| **SR-04: Search is tenant-scoped** | Full-text search against message bodies is always executed within a `WHERE tenant_id = :tenant_id` boundary. Search cannot traverse tenant boundaries. |
| **SR-05: Filter parameters are not trusted blindly** | Filter values (`status`, `unread`) are validated server-side as enum members. Unknown or malformed filter values return a 422 validation error — they do not silently fall back to returning all data. |

---

## Assumptions

- The inbox operates on the `conversations` table (not the `messages` table directly). Each conversation row aggregates its most-recent message for the preview.
- "Unread" at the conversation level means: the conversation has at least one message with `status=unread`. This definition may evolve once a "mark as read" feature exists.
- Pagination defaults to page 1, 20 items per page. The page size is fixed for MVP — user-configurable page size is out of scope.
- The inbox is a read-only page. No status changes, message replies, or task creation happen from the inbox list — those require navigating into the conversation detail.
- Search triggers after the user has typed at least 2 characters (debounced client-side; enforced server-side by rejecting 0–1 character search terms).
- The unread badge count is fetched from `GET /api/v1/inbox/summary` before the inbox page loads. The full inbox response also includes `total_unread` and should match the summary count.
- Conversation preview truncation to 100 characters is applied server-side so the client does not receive full message bodies in the list response.
- Filter state (active filters + search term) is preserved in the URL as query parameters so the browser back button and page refresh restore the same view.
