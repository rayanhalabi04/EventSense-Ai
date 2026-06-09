# Feature Specification: Message Detail Page

**Feature Branch**: `005-message-detail-page`

**Created**: 2026-06-03

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)

**Input**: User description: "Message Detail Page — allow staff and managers to open a tenant-scoped conversation from the inbox and view the full conversation thread, client information, message history, and basic actions/placeholders for future AI workflow."

---

## Goal

Give staff and managers a single page where they can open a client conversation, read the complete message thread in chronological order, see client identity and conversation status at a glance, and understand what actions will be available when AI features are introduced. Opening the page marks unread messages as read so the inbox badge stays accurate. The detail page is the bridge between the read-only inbox and the future AI-powered response workflow — it surfaces everything a planner needs to understand the conversation before acting on it.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner who clicks a conversation from the inbox to read the full thread, confirm client details, and prepare to reply or escalate. |
| **Manager** | A senior planner or agency head who reviews conversation history, monitors client sentiment, and oversees escalated conversations. |

Platform Admin has no access to conversation detail or any tenant message content.

---

## User Stories

### User Story 1 — View Full Conversation Thread (Priority: P1)

A staff planner clicks a conversation row in the inbox. The detail page opens and shows the complete message thread for that conversation in chronological order. Each message displays its body, the time it was sent, and whether it came from the client (inbound) or the agency (outbound). The client's name, contact detail, and conversation status are shown in a header panel. All content belongs to the authenticated user's tenant — no other tenant's conversations are ever accessible.

**Why this priority**: Reading the full thread is the core purpose of the detail page. Without it, staff cannot understand the conversation context, respond appropriately, or hand off to colleagues. Every other user story and future AI feature depends on this view being present and accurate.

**Independent Test**: Inject three simulator messages into one conversation for Tenant A (two inbound, one outbound). Navigate to `/conversations/{id}` as an authenticated Tenant A staff user. Verify all three messages appear in sent-at order, each showing the correct body, timestamp, and direction indicator. Navigate to the same URL as a Tenant B staff user — verify a permission-denied response with no conversation data exposed.

**Acceptance Scenarios**:

1. **Given** an authenticated Staff user navigates to `/conversations/{id}` for a conversation in their tenant, **When** the page loads, **Then** the full message thread is shown in chronological order (oldest first) with each message displaying its body, sent timestamp, and direction (inbound/outbound).
2. **Given** a conversation with a client name, optional contact detail, and a status, **When** the detail page renders, **Then** the header shows client name, client contact (if available), and a conversation status badge (open / closed / escalated).
3. **Given** an authenticated Staff user from Tenant B navigates directly to a Tenant A conversation URL, **When** the request is processed, **Then** they receive a permission-denied response with no conversation content returned.
4. **Given** an authenticated Platform Admin navigates to any conversation detail URL, **When** the request is processed, **Then** they receive a permission-denied response with no conversation content returned.
5. **Given** the conversation ID does not exist in the system, **When** the detail page is requested, **Then** a not-found response is returned.

---

### User Story 2 — Mark Unread Messages as Read on Open (Priority: P1)

When a staff planner opens the conversation detail page, all unread inbound messages in that conversation are automatically marked as read. The inbox unread badge count decreases accordingly. Staff do not need to take any explicit action — opening the conversation is sufficient to clear the unread indicator.

**Why this priority**: Without automatic read-marking, the unread badge would never decrease and staff would have no reliable way to track which conversations they have reviewed. This is the standard inbox UX contract — opening a conversation means you have seen it.

**Independent Test**: Inject two unread inbound messages into a conversation. Note the inbox `total_unread` count before opening the detail page. Open `/conversations/{id}`. Return to the inbox and verify the unread dot on that conversation is gone and `total_unread` has decremented by 1 (one conversation cleared, not two messages — the count is at the conversation level).

**Acceptance Scenarios**:

1. **Given** a conversation has at least one unread inbound message, **When** an authenticated staff user opens the detail page, **Then** all unread inbound messages in that conversation are marked as read.
2. **Given** those messages are now read, **When** the inbox is subsequently loaded, **Then** the conversation no longer shows an unread indicator and `total_unread` reflects the updated count.
3. **Given** a conversation already has all messages read, **When** the detail page is opened, **Then** no status changes occur and the page loads normally.
4. **Given** outbound messages exist in the conversation, **When** the detail page is opened, **Then** outbound messages are not affected by the mark-as-read operation (only inbound messages transition from unread to read).

---

### User Story 3 — AI Workflow Placeholder Sections (Priority: P2)

The detail page includes clearly labelled placeholder sections for future AI-powered capabilities: inferred client intent, risk or sentiment indicator, RAG knowledge sources used, suggested reply, task creation, and escalation trigger. These sections are visible but non-functional — they display a "coming soon" message or a locked/greyed state so staff understand what is planned without being confused by missing functionality.

**Why this priority**: Placeholder sections serve two purposes: they communicate the product roadmap to staff ("this is where the AI reply will appear") and they establish the page layout and navigation structure so future features slot in without requiring a full redesign. Lower priority than the core thread and read-marking because staff can use the page productively without placeholders.

**Independent Test**: Open any conversation detail page. Verify that the following labelled sections are visible in the page layout: "AI Intent", "Risk / Sentiment", "Knowledge Sources", "Suggested Reply", "Create Task", and "Escalate". Verify each section renders a placeholder message (e.g., "Coming soon") and no interactive elements are active. Verify clicking within any placeholder section does not trigger any action.

**Acceptance Scenarios**:

1. **Given** the detail page is open, **When** the page fully renders, **Then** six placeholder sections are visible: AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, and Escalate.
2. **Given** any placeholder section is visible, **When** a staff member interacts with it, **Then** no action is triggered and a "coming soon" or "not yet available" label is shown.
3. **Given** the placeholder sections are visible, **When** the staff member inspects the page, **Then** each section has a clear, meaningful label so staff understand the intended future function.

---

### Edge Cases

- What if a conversation has no messages at all (created without a message)? The thread area shows "No messages in this conversation yet." and client header info is still displayed.
- What if the message body is extremely long (e.g., thousands of characters)? The message body renders in full — no truncation on the detail page (truncation only applies to the inbox preview). The page scrolls vertically.
- What if two staff members open the same conversation simultaneously? Both see the thread; both trigger the mark-as-read operation. Idempotency: marking an already-read message as read has no effect and no error is returned.
- What if the conversation has hundreds of messages? Messages are displayed in a single scrollable thread ordered chronologically. Pagination within the thread is out of scope for MVP — all messages are loaded for the initial release.
- What if the client contact field is empty? The header shows "—" or omits the contact row rather than showing a blank or null value.
- What if the user navigates directly to `/conversations/{id}` with an expired session? The session check detects the expired token and redirects the user to the login page. After re-authentication, they are returned to the detail page.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST display the complete, chronologically ordered message thread (oldest message first) for the requested conversation.
- **FR-002**: Each message in the thread MUST show its full body text, sent timestamp, and direction (inbound from client / outbound from agency).
- **FR-003**: The page header MUST display the conversation's client name, client contact (if present), and current status badge (open / closed / escalated).
- **FR-004**: The system MUST derive `tenant_id` from the authenticated session only — no `tenant_id` accepted from URL parameters or request body.
- **FR-005**: The system MUST return a 403 Forbidden response if the requested conversation belongs to a different tenant.
- **FR-006**: The system MUST return a 404 Not Found response if the conversation ID does not exist.
- **FR-007**: The system MUST restrict detail page access to `staff` and `manager` roles; Platform Admin receives 403.
- **FR-008**: The system MUST mark all unread inbound messages in the opened conversation as read when an authenticated user loads the detail page.
- **FR-009**: The mark-as-read operation MUST be idempotent — applying it to already-read messages produces no error and no state change.
- **FR-010**: The frontend MUST display six clearly labelled placeholder sections for future AI features: AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, and Escalate.
- **FR-011**: Each placeholder section MUST be non-functional and display a "coming soon" indicator; no placeholder section may trigger any backend action.
- **FR-012**: The system MUST NOT expose full message bodies in the inbox list endpoint — full bodies are available only via the detail page (preview truncation remains in effect in the inbox).

### Key Entities

- **Conversation**: A tenant-scoped client interaction thread identified by UUID. Has client name, optional contact, status (open/closed/escalated), and timestamps. Contains zero or more messages.
- **Message**: An individual message within a conversation. Has body text, sent timestamp, direction (inbound/outbound), and read status (unread/read). Belongs to exactly one conversation and one tenant.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: A staff user can open a conversation from the inbox and read the full message thread in a single page load without additional navigation.
- **SC-002**: After opening a conversation, the inbox unread badge reflects the updated read state the next time the inbox is loaded — no manual refresh required.
- **SC-003**: A cross-tenant access attempt (Tenant B staff accessing Tenant A conversation) always results in a permission-denied response — zero data exposure in all tested scenarios.
- **SC-004**: The six AI placeholder sections are visible on every detail page load, correctly labelled, and produce no errors or unintended side effects when interacted with.
- **SC-005**: Conversation detail loads within standard web application response-time expectations for a page with up to 50 messages.
- **SC-006**: Opening the same conversation simultaneously from two sessions produces no errors and leaves all messages in a consistent read state.

---

## MVP Scope

- Conversation detail page accessible to `staff` and `manager` roles only at `/conversations/{id}`
- Header panel: client name, client contact (if present), conversation status badge
- Full chronological message thread (oldest first): message body, sent timestamp, direction indicator (inbound/outbound)
- Automatic mark-as-read for all unread inbound messages on page load
- Six non-functional AI placeholder sections: AI Intent, Risk / Sentiment, Knowledge Sources, Suggested Reply, Create Task, Escalate
- 403 Forbidden for cross-tenant access and Platform Admin
- 404 Not Found for non-existent conversation ID
- Empty thread state when conversation has no messages
- Tenant isolation enforced by backend; `tenant_id` derived from JWT only

---

## Out of Scope

- Replying to a message from the detail page (requires a separate reply/compose feature)
- Manually marking individual messages as read or unread
- AI intent detection, risk scoring, RAG retrieval, or suggested reply generation (future features)
- Task creation or escalation workflow (future features)
- Real-time updates when new messages arrive (WebSocket / push notifications)
- Message editing or deletion
- Attaching files or media to conversations
- Exporting or printing the conversation thread
- Pagination within the message thread (all messages loaded for MVP)
- Real WhatsApp API integration

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Conversation ID | URL path parameter | UUID of the conversation to display (`/conversations/{id}`) |
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client for tenant resolution |

---

## Outputs

| Output | Description |
|--------|-------------|
| Conversation header | Client name, contact (if present), and status badge |
| Message thread | All messages in chronological order; each with body, timestamp, and direction |
| Read-state update | All unread inbound messages in the conversation transitioned to read |
| 403 Forbidden | Returned for cross-tenant access or Platform Admin access attempts |
| 404 Not Found | Returned when the conversation ID does not exist |
| AI placeholder sections | Six visible, non-functional sections labelled for future AI features |

---

## Main Workflow

1. **Staff clicks a conversation row in the inbox** — Navigated to `/conversations/{id}`.
2. **Detail page loads** — The backend verifies the JWT, derives `tenant_id`, confirms the conversation belongs to that tenant, and returns the full conversation data including all messages.
3. **Unread messages marked as read** — All unread inbound messages in the conversation are marked as read as part of the page load response.
4. **Staff reads the thread** — Messages are displayed oldest-first in a scrollable thread. Each message is visually distinguished by direction (client messages on one side, agency messages on the other).
5. **Staff reviews client info and status** — The header shows who the client is, their contact, and the current conversation state.
6. **Staff notes AI placeholders** — Placeholder sections for AI features are visible below or alongside the thread, each labelled with its future purpose.

---

## Alternative Workflows

### Cross-Tenant Direct URL Access

1. Tenant B staff copies a Tenant A conversation URL and navigates to it directly.
2. The backend verifies the JWT, derives Tenant B's `tenant_id`, and finds the conversation belongs to Tenant A.
3. A 403 Forbidden response is returned. No conversation content is exposed.
4. The frontend displays a permission-denied error page or redirects to the inbox.

### Non-Existent Conversation

1. Staff navigates to a URL with a conversation ID that does not exist (e.g., a deleted or mistyped ID).
2. The backend returns 404 Not Found.
3. The frontend displays a "conversation not found" error page with a link back to the inbox.

### Platform Admin Access Attempt

1. An authenticated Platform Admin navigates to any conversation detail URL.
2. The role guard rejects the request with 403 Forbidden.
3. No conversation data is loaded or exposed.

### Expired Session on Direct URL

1. Staff opens the detail page URL directly with an expired JWT.
2. The session check detects the expired token and returns 401 Unauthorized.
3. The frontend redirects to the login page.
4. After re-authentication, the user is returned to the conversation detail page.

### Conversation with No Messages

1. Staff opens a conversation that was created but has no messages yet.
2. The header renders client name, contact, and status normally.
3. The thread area shows "No messages in this conversation yet."
4. AI placeholder sections are still visible.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Detail page shows all messages for the conversation in chronological order | Integration test: inject 3 messages; verify all 3 returned in sent-at ASC order |
| AC-02 | Each message shows full body, sent timestamp, and direction (inbound/outbound) | Integration test: assert all fields present and correct in API response |
| AC-03 | Header shows client name, client contact (if present), and status badge | Integration test + visual check: assert all header fields in response |
| AC-04 | Accessing a conversation from another tenant returns 403 | Integration test: Tenant B token + Tenant A conversation ID → 403 |
| AC-05 | Accessing a non-existent conversation returns 404 | Integration test: random UUID → 404 |
| AC-06 | Platform Admin token returns 403 on any conversation detail request | Integration test: platform admin token → 403 with INSUFFICIENT_ROLE |
| AC-07 | Opening the detail page marks all unread inbound messages as read | Integration test: 2 unread inbound messages → open detail → assert both have status=read |
| AC-08 | Outbound messages are not affected by mark-as-read | Integration test: 1 unread inbound + 1 outbound → open detail → assert only inbound changed to read |
| AC-09 | Mark-as-read is idempotent — opening an already-fully-read conversation causes no error | Integration test: all-read conversation → open detail → assert 200, no state change |
| AC-10 | `total_unread` in the next inbox response reflects the updated read state | Integration test: open detail → fetch inbox → assert total_unread decremented |
| AC-11 | Conversation with no messages returns empty thread with no error | Integration test: conversation with no messages → assert items=[], 200 response |
| AC-12 | Six AI placeholder sections are rendered on the detail page | Front-end test: verify all six labelled sections are present in the DOM |
| AC-13 | No placeholder section triggers any backend call or state change when interacted with | Front-end test: click/hover each placeholder → assert no network requests, no errors |
| AC-14 | `tenant_id` is always derived from JWT — not from any request parameter | Security test: inject arbitrary tenant_id query param → assert it is ignored; result uses JWT tenant |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Provides `conversations` and `messages` tables, `tenant_id` isolation, cross-tenant 403 blocking |
| Spec 002 — Authentication and Roles | Required | Provides JWT auth, `staff`/`manager` role access, `require_role` dependency, Platform Admin block |
| Spec 003 — WhatsApp-Style Message Simulator | Required | Provides `messages.status` column (`unread`/`read`) and the data that populates the thread |
| Spec 004 — Message Inbox | Required | Entry point for navigation to the detail page; `total_unread` is consumed by the inbox after read-marking |

---

## AI Behavior

The detail page does not invoke AI in this feature. It is, however, the designated surface where AI features will be activated in future specs. Design decisions made here to ensure compatibility:

- The conversation detail API response is structured to be extensible: a future AI feature can add `ai_intent`, `risk_score`, `suggested_reply`, and `rag_sources` fields to the response without breaking the current schema.
- The six placeholder sections are positioned in the layout now so that future AI features can replace placeholders with live components without requiring a layout redesign.
- The mark-as-read operation runs on page load (not on an explicit staff action) to ensure that "unread = not yet seen by a human" semantics are preserved even after AI processing is introduced — the AI will process messages independently of their read status.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the authenticated JWT. Any `tenant_id` sent as a URL parameter or request body is discarded. The detail endpoint always filters by the session tenant. |
| **SR-02: Role restriction** | Only `staff` and `manager` roles may access the conversation detail. Platform Admin receives 403. Unauthenticated requests receive 401. |
| **SR-03: Cross-tenant isolation** | If the requested conversation's `tenant_id` does not match the JWT's `tenant_id`, the endpoint returns 403 — no conversation data is included in the response. |
| **SR-04: Not Found vs Forbidden distinction** | A conversation that does not exist in the system returns 404. A conversation that exists but belongs to another tenant returns 403. This prevents tenant enumeration: a 404 does not confirm whether a conversation exists in a different tenant. |
| **SR-05: Full bodies on detail only** | Full message bodies are returned only by the conversation detail endpoint. The inbox list endpoint returns truncated previews only. This limits the blast radius if the inbox response is logged or cached. |
| **SR-06: Mark-as-read scope** | The mark-as-read operation is scoped to the authenticated tenant's conversation. It cannot affect messages in another tenant's conversation regardless of the request parameters. |

---

## Assumptions

- The `messages` table has a `status` column with values `unread` and `read`, added by Spec 003. No schema changes are needed for read-marking — only a `WHERE status = 'unread' AND direction = 'inbound'` update on the existing column.
- "Marking as read" applies to inbound messages only. Outbound messages (sent by the agency) are considered inherently seen and do not carry an unread status that needs to be cleared.
- The detail page is read-only for MVP. No reply, status change, or task creation happens from this page — those require future dedicated features.
- All messages in a conversation are loaded in a single request for MVP. Pagination within the thread is deferred until message volume per conversation warrants it.
- The page is accessed via the inbox row click as the primary entry point, but direct URL navigation (with a valid session) is also supported.
- The six AI placeholder sections are purely presentational. Their exact content, label wording, and visual style are implementation decisions left to the planning phase.
- Conversation status changes (e.g., closing or escalating a conversation from the detail page) are out of scope for this feature even though status is displayed. Status mutation requires a future dedicated action.
