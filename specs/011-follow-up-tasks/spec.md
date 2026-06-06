# Feature Specification: Follow-Up Tasks

**Feature Branch**: `011-follow-up-tasks`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 007 — Risk Detection](../007-risk-detection/spec.md)
- [Spec 010 — Suggested Replies](../010-suggested-replies/spec.md)

**Input**: User description: "The system should allow staff users to create follow-up tasks from client messages so that important client requests become trackable operational actions. Tasks should be linked to the original message, tenant, client/conversation if available, assigned user, due date, and status."

---

## Goal

Let staff turn an important client message into a trackable operational task — with a title, description, assignee, due date, priority, and status — so client requests don't fall through the cracks. A task is created from the message detail page, keeps a link back to the original message, and is scoped to the tenant. The system **may suggest** task details from the message + intent (006) + risk (007) + suggested reply (010), but a human must confirm/edit before the task is created — nothing is auto-created. Creating a task sends no message to the client and never escalates the case (escalation is a separate feature). Tasks appear on a Tasks page and can be assigned, prioritised, progressed, completed, or cancelled. Every task is tenant-scoped; Tenant A can never access Tenant B tasks.

---

## Task Statuses

| Status | Meaning |
|--------|---------|
| `open` | Created, not yet started |
| `in_progress` | Someone is working on it |
| `completed` | Done (records `completed_at`) |
| `cancelled` | No longer needed |

## Task Priority

| Priority | Meaning |
|----------|---------|
| `low` | Routine; no urgency |
| `medium` | Should be handled soon |
| `high` | Urgent / important; handle first |

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | Creates tasks from messages, writes/edits title + description, assigns, sets due date + priority, progresses and completes tasks. The primary actor. |
| **Manager** | Views all tenant tasks, monitors high-priority/overdue tasks, and reassigns tasks between team members. |
| **System / AI service** | May *suggest* a task title/description/priority from the message context, but never creates a task without explicit human confirmation. Not a human actor. |

Platform Admin has no access to tenant tasks.

---

## User Stories

### User Story 1 — Create a Follow-Up Task from a Message (Priority: P1)

A staff planner, viewing a client message, creates a follow-up task. They write (or accept a suggestion for) a title and description, optionally set an assignee, due date, and priority, and save. The task is stored linked to the message, scoped to the tenant, with status `open` and `created_by` = the staff user.

**Why this priority**: Capturing a message as a trackable task is the feature's core purpose — without creation there is nothing to track. Every other story operates on tasks created here.

**Independent Test**: From an Elegant Weddings message "We need to change the guest count from 150 to 220.", create a task titled "Check catering capacity for updated guest count". Verify a `Task` is stored in the Elegant Weddings tenant, linked to that message, status `open`, priority as set, `created_by` = the user, timestamps set. Verify it is not visible to Royal Events Agency.

**Acceptance Scenarios**:

1. **Given** an authenticated staff user viewing a message in their tenant, **When** they submit a task with a valid title, **Then** a `Task` is created linked to the message (`related_message_id`), scoped to the tenant, with status `open`, `created_by` = the user, and timestamps set.
2. **Given** a task submission missing a title, with an over-length title, an invalid priority/status, an assignee outside the tenant, or a non-existent message, **When** it is submitted, **Then** it is rejected with a validation error and nothing is stored.
3. **Given** a staff user in Tenant A, **When** they create a task, **Then** it is scoped to Tenant A and never visible to Tenant B.
4. **Given** a task is created from a message, **When** creation succeeds, **Then** the message status may be updated to `task_created` (see Assumptions) and the task appears on the Tasks page and the message's tasks list.

---

### User Story 2 — View and Manage Tasks (Priority: P1)

Staff and managers see a Tasks page listing the tenant's tasks with title, status, priority, assignee, due date, and the related message. They filter by status/priority/assignee, open a task, update its fields (assignee, due date, priority, description), and move it through statuses. Managers can reassign.

**Why this priority**: Tasks are only useful if they can be tracked and worked. Listing + updating is the operational backbone. Equal P1 because creating tasks with no way to manage them delivers little value.

**Independent Test**: With several tasks in a tenant, list tasks as a staff user — verify only that tenant's tasks appear with full metadata. Filter by `priority=high` — verify the subset. Open a task and change its assignee and status to `in_progress` — verify changes persist and `updated_at` refreshes. As a manager, reassign a task — verify the new assignee.

**Acceptance Scenarios**:

1. **Given** tasks exist in a tenant, **When** a staff/manager lists tasks, **Then** only that tenant's tasks are returned with title, status, priority, `assigned_to`, `due_date`, `related_message_id`, timestamps.
2. **Given** filters (status, priority, assignee, related message), **When** the list is requested with them, **Then** only matching tenant tasks are returned.
3. **Given** a task in the caller's tenant, **When** a staff/manager updates allowed fields (title, description, assignee, due date, priority, status), **Then** changes persist and `updated_at` refreshes.
4. **Given** a manager, **When** they reassign a task to another in-tenant user, **Then** `assigned_to` updates.
5. **Given** a task or assignee from another tenant, **When** referenced, **Then** it is blocked (404/403) and no change occurs.

---

### User Story 3 — Complete or Cancel a Task (Priority: P1)

A staff user marks a task `completed` (recording when) once the follow-up is done, or `cancelled` if it is no longer needed. Completed/cancelled tasks remain listed (filterable) for record-keeping.

**Why this priority**: Closing the loop is essential — open tasks that can never be completed are noise. Equal P1 because the task lifecycle is incomplete without a terminal transition.

**Independent Test**: Take an `open` task, mark it `completed` — verify status `completed` and `completed_at` set. Take another and `cancelled` — verify status `cancelled`. Verify both still appear when listing with the appropriate status filter, and that completing an already-completed task is rejected.

**Acceptance Scenarios**:

1. **Given** an `open`/`in_progress` task, **When** a staff user completes it, **Then** status becomes `completed` and `completed_at` is recorded.
2. **Given** an `open`/`in_progress` task, **When** a staff user cancels it, **Then** status becomes `cancelled`.
3. **Given** a `completed`/`cancelled` task, **When** a user attempts to complete/cancel/edit it again, **Then** the request is rejected (invalid state transition) — terminal states are immutable.
4. **Given** completed/cancelled tasks, **When** the Tasks page is listed, **Then** they remain visible and filterable by status.

---

### User Story 4 — AI-Suggested Task Details (Optional) (Priority: P2)

When creating a task from a message, a staff user may request a suggestion: the system proposes a title, description, and priority based on the message, its intent, risk, and any suggested reply. The staff user edits or accepts it, then confirms — the task is only created on confirmation.

**Why this priority**: Suggestions speed up task capture and improve consistency, but the feature is fully usable with manual entry (US1). Lower priority and explicitly optional; never auto-creates.

**Independent Test**: For "I paid the deposit but no one confirmed." request a task suggestion — verify a proposed title/description/priority is returned (e.g., "Verify deposit payment confirmation", high/medium) **without** creating a task. Confirm the suggestion → verify a task is then created with the (possibly edited) values.

**Acceptance Scenarios**:

1. **Given** a message with intent/risk (and optionally a suggested reply), **When** a staff user requests a task suggestion, **Then** the system returns a proposed title, description, and priority **without** creating any task.
2. **Given** a returned suggestion, **When** the staff user edits and confirms it, **Then** a task is created with the confirmed values (status `open`).
3. **Given** a suggestion is requested, **When** the user does not confirm, **Then** no task is created.
4. **Given** the suggestion service is unavailable, **When** a suggestion is requested, **Then** the user can still create the task manually (suggestion failure does not block creation).

---

### Edge Cases

- **Message has no conversation/client**: the task still links to the message; `conversation_id` is optional metadata when available.
- **Assignee not provided**: task is created unassigned (`assigned_to` null); can be assigned later.
- **Assignee in another tenant**: rejected (assignee must be a user in the caller's tenant).
- **Due date in the past**: allowed but flagged as overdue in the UI (no hard block) — or rejected per a configurable rule; default allows it and marks overdue.
- **Empty/whitespace title**: rejected (validation).
- **Duplicate tasks for one message**: allowed — multiple tasks may stem from one message; each is independent.
- **Creating a task does not change the suggested reply or send anything**: task creation is isolated from messaging/escalation.
- **Completing a task twice / editing a completed task**: rejected (terminal-state immutability).
- **Reassign a completed task**: rejected (terminal).
- **Cross-tenant id guessing**: requesting/modifying another tenant's task or referencing another tenant's message/assignee → 404/403.
- **Concurrent updates**: last write wins for fields; terminal transitions are guarded.

---

## Requirements

### Functional Requirements

- **FR-001**: Staff MUST be able to create a task linked to a message (`related_message_id`), scoped to their tenant, with a human-written (or human-confirmed) title.
- **FR-002**: The system MUST store task fields: `id`, `tenant_id`, `related_message_id`, `title`, `description`, `assigned_to`, `created_by`, `due_date`, `priority`, `status`, `created_at`, `updated_at`, `completed_at`.
- **FR-003**: New tasks MUST be created with status `open`.
- **FR-004**: The system MUST validate title (non-empty, length-bounded), priority (valid enum), status transitions, due date, and that `assigned_to` (if set) is a user in the caller's tenant.
- **FR-005**: Staff and managers MUST be able to list tasks in their tenant, filtered by status, priority, assignee, and related message, and fetch a single task.
- **FR-006**: Staff/managers MUST be able to update allowed task fields (title, description, assignee, due date, priority, status); managers MUST be able to reassign.
- **FR-007**: Staff MUST be able to complete a task (status `completed`, set `completed_at`) and cancel a task (status `cancelled`).
- **FR-008**: The system MUST reject invalid state transitions (editing/completing/cancelling a terminal task; completing a cancelled task).
- **FR-009**: The system MAY suggest task title/description/priority from message + intent + risk + suggested reply, but MUST NOT create a task without explicit human confirmation.
- **FR-010**: Task creation MUST NOT send any message to the client.
- **FR-011**: Task creation MUST NOT create an escalation (escalation is a separate feature).
- **FR-012**: The system MUST scope every task operation to the caller's tenant; cross-tenant access MUST be blocked.
- **FR-013**: Tasks MUST appear on a Tasks page/list and on the related message's tasks list.
- **FR-014**: On task creation, the related message's status MAY be updated to `task_created` (non-destructive; see Assumptions).
- **FR-015**: The system MUST record `created_by` (authenticated user) and maintain `created_at`/`updated_at` (and `completed_at` on completion).

### Key Entities

- **Tenant** (Spec 001): scopes all tasks.
- **User** (Spec 002): `created_by`, `assigned_to`; role gates actions; assignee must be in-tenant.
- **Message** (Spec 003): the source message (`related_message_id`); provides optional `conversation_id`.
- **Task** (new): the follow-up action with its lifecycle.
- **TaskStatus** (enum): `open`, `in_progress`, `completed`, `cancelled`.
- **TaskPriority** (enum): `low`, `medium`, `high`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Related message | `POST /api/tasks` | The message the task is created from (`related_message_id`) |
| Title / description | Create/update request | Human-written or human-confirmed text |
| Assignee | Create/update request | An in-tenant user (optional) |
| Due date | Create/update request | Optional date/time |
| Priority | Create/update request | `low` / `medium` / `high` |
| Status change | Update / complete / cancel | Lifecycle transition |
| Suggestion request (optional) | `POST /api/messages/{id}/task-suggestion` | Asks AI for proposed task details (creates nothing) |
| Filters | List request | status / priority / assignee / related_message |

---

## Outputs

| Output | Description |
|--------|-------------|
| Created task | Stored task linked to the message, status `open` |
| Task list | Tenant-scoped list with full metadata, filterable |
| Single task | One in-tenant task |
| Updated task | Reflecting edited fields + refreshed `updated_at` |
| Completed/cancelled task | Terminal status (+ `completed_at` on completion) |
| Task suggestion (optional) | Proposed title/description/priority — no task created |
| Message status change | Related message may become `task_created` |
| 403 / 404 | Cross-tenant / platform-admin / missing message/task/assignee |
| 422 | Invalid field / invalid transition |

---

## Main Workflow

1. **Staff views a message** on the detail page (Spec 005).
2. **Staff initiates a task** — optionally requests an AI suggestion (title/description/priority from message + intent + risk + suggested reply).
3. **Staff writes/edits + confirms** — title, description, assignee, due date, priority. Nothing is created until confirmation.
4. **Task created** — `POST /api/tasks` stores the task linked to the message, status `open`, `created_by` set, tenant-scoped.
5. **Message marked** — the related message may be set to `task_created`.
6. **Task tracked** — it appears on the Tasks page and the message's tasks list; staff/managers filter, open, update, and reassign.
7. **Task progressed** — `open → in_progress`, then `completed` (with `completed_at`) or `cancelled`.

No message is sent to the client and no escalation is created at any step.

---

## Alternative Workflows

### Manual Task (no AI)

1. Staff creates a task by typing the title/description directly.
2. No suggestion is requested; the task is created on confirmation.

### AI-Suggested Task (optional)

1. Staff requests a suggestion for a message.
2. The system returns proposed title/description/priority (no task created).
3. Staff edits and confirms → the task is created with confirmed values.
4. If the suggestion service is down, staff falls back to manual entry.

### Reassign (manager)

1. A manager views the Tasks page and opens a task.
2. They change `assigned_to` to another in-tenant user.
3. The change persists; the new assignee sees it in their filtered list.

### Complete / Cancel

1. Staff finishes the follow-up → marks the task `completed` (`completed_at` set).
2. Or the task is no longer needed → `cancelled`.
3. Terminal tasks remain listed but cannot be edited further.

### Cross-Tenant Attempt

1. A Tenant B user requests/edits a Tenant A task, or assigns a Tenant A user to a Tenant B task.
2. Tenant resolution returns 404/403; no data exposed; no change made.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Staff can create a task linked to a message; stored in tenant with status `open`, created_by, timestamps | Integration test: POST → assert fields |
| AC-02 | Missing/over-length title, invalid priority/status, out-of-tenant assignee, non-existent message → 422/404; nothing stored | Integration test: each bad input |
| AC-03 | Tasks are tenant-scoped; Tenant B cannot list/read Tenant A tasks | Integration test: create in A; list/get as B → not present / 404-403 |
| AC-04 | Listing returns only the caller's tenant tasks with full metadata | Integration test: tasks in A + B → list in A returns only A |
| AC-05 | List filters by status, priority, assignee, related_message work within the tenant | Integration test: assert filtered subsets |
| AC-06 | `GET /api/tasks/{id}` returns the task; cross-tenant → 404/403 | Integration test |
| AC-07 | Updating allowed fields persists and refreshes `updated_at` | Integration test: PATCH → assert changes |
| AC-08 | Manager can reassign a task to an in-tenant user; out-of-tenant assignee rejected | Integration test: reassign ok; cross-tenant assignee → 422/403 |
| AC-09 | Completing sets status `completed` + `completed_at` | Integration test: complete → assert |
| AC-10 | Cancelling sets status `cancelled` | Integration test: cancel → assert |
| AC-11 | Invalid transitions rejected (edit/complete/cancel a terminal task) | Integration test: each → 422 INVALID_STATE_TRANSITION |
| AC-12 | `GET /api/messages/{id}/tasks` returns the message's tenant-scoped tasks | Integration test: assert tasks; cross-tenant → 404/403 |
| AC-13 | Task creation sends no client message and creates no escalation | Code/integration test: assert no such side effects |
| AC-14 | Optional suggestion returns proposed details without creating a task; confirm then creates | Integration test: suggestion → no task; confirm → task |
| AC-15 | Platform Admin blocked from all task endpoints (403) | Integration test: admin → 403 INSUFFICIENT_ROLE |
| AC-16 | On creation, related message status may become `task_created` | Integration test: create → assert message status |
| AC-17 | Tasks page + message tasks list display tasks with metadata | Frontend test: assert rendering |
| AC-18 | A non-existent or cross-tenant related message is rejected on create | Integration test: bad message → 404/403 |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenants, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT; `staff`/`manager` actions; assignee must be in-tenant; Platform Admin blocked |
| Spec 003 — Message Simulator | Required | The message a task links to; provides `conversation_id` |
| Spec 004 — Message Inbox | Required (light) | May show a "task created" indicator |
| Spec 005 — Message Detail Page | Required | Entry point for task creation; replaces the "Create Task" placeholder |
| Spec 006 — Intent Classifier | Optional | Input to AI task suggestion |
| Spec 007 — Risk Detection | Optional | Input to AI task suggestion (priority hint) |
| Spec 010 — Suggested Replies | Optional | Input to AI task suggestion (context) |
| Audit Log (future feature) | Future integration | Task actions (create/update/complete/cancel/reassign) will be logged by the later audit-log feature; **not implemented here** |

---

## AI Behavior

- **Suggestion only, never autonomous**: the system may propose a task title, description, and priority from the message text, intent (006), risk (007), and suggested reply (010). It returns a proposal; it **never** creates a task without explicit human confirmation (FR-009).
- **Priority hint from risk**: the suggested priority is informed by the risk level (e.g., high risk → suggested `high`), but the staff user can override it.
- **No side effects from suggesting**: requesting a suggestion creates nothing, sends nothing, and escalates nothing.
- **Graceful fallback**: if the suggestion service is unavailable, manual task creation still works (suggestion is optional, not a dependency for creation).
- **Provenance (optional)**: a suggestion may note it was AI-proposed, but the stored task records the human `created_by` (the confirming user), not the AI.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the JWT. No client-supplied tenant accepted. Tasks are created/queried only within the session tenant. |
| **SR-02: Task tenancy** | A task belongs to exactly one tenant. Tenant A can never list/read/update/complete Tenant B tasks. |
| **SR-03: In-tenant references** | `related_message_id` and `assigned_to` must resolve within the caller's tenant; cross-tenant references are rejected (404/403). |
| **SR-04: Role restriction** | Only `staff` and `manager` may use task endpoints. Platform Admin → 403. Unauthenticated → 401. Reassignment is a manager (and staff) capability per the role matrix. |
| **SR-05: Not Found vs Forbidden** | A task/message not in the caller's tenant → 404; one in another tenant → 403 (consistent with Specs 005–010). |
| **SR-06: No autonomous actions** | Task creation/updates send no client message (SR/FR-010) and create no escalation (FR-011). |
| **SR-07: Creator/assignee integrity** | `created_by` is the authenticated user; `assigned_to` must be a valid in-tenant user; neither can be spoofed to another tenant. |
| **SR-08: No AI auto-create** | The AI may only suggest; task creation always requires an authenticated human confirmation. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Missing/empty/whitespace title | 422 validation; nothing stored |
| Title too long | 422 validation; nothing stored |
| Invalid priority/status value | 422 validation; nothing stored |
| `assigned_to` not an in-tenant user | 422 `INVALID_ASSIGNEE` (or 404/403); nothing stored |
| `related_message_id` non-existent / cross-tenant | 404 / 403; nothing stored |
| Invalid state transition (edit/complete/cancel terminal task) | 422 `INVALID_STATE_TRANSITION`; no change |
| Cross-tenant task access | 404/403 per SR-05; no data exposed |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE` |
| Suggestion service unavailable | Suggestion endpoint returns 503; manual creation still works |
| Storage write fails | 5xx; no partial task persisted (transactional create) |

---

## Edge Cases (summary)

- No conversation/client → task still links to the message; conversation optional.
- No assignee → unassigned; assign later.
- Past due date → allowed, flagged overdue (default) or per config.
- Duplicate tasks per message → allowed; independent.
- Terminal-state edits/completes → 422.
- Cross-tenant id/assignee → 404/403.
- Concurrent updates → last write wins; terminal transitions guarded.

---

## Out of Scope

- **Escalation workflow** — separate, later feature; task creation never escalates.
- **Sending any message to the client** — no WhatsApp/email/SMS; nothing transmitted.
- **Auto-creating tasks** — every task requires explicit human confirmation.
- **Audit logging** — task actions will be logged by the later audit-log feature; **not implemented here** (named as a future integration/dependency).
- **Calendar syncing / reminders / notifications** — out of scope (due dates are stored, not synced to calendars).
- **Recurring tasks / subtasks / dependencies between tasks** — out of scope for MVP.
- **Task comments / attachments** — out of scope for MVP.
- **Cross-tenant or shared tasks** — explicitly forbidden.
- **Full CRM / project management** — out of scope.
- **Real WhatsApp API** — out of scope entirely.

---

## Assumptions

- A task always links to exactly one message (`related_message_id`) and belongs to one tenant; `conversation_id` is optional metadata stored when the message has one.
- Multiple tasks may be created from one message; they are independent.
- The related message's status may be set to `task_created` on creation; this is non-destructive and reversible by other features and does not block creating more tasks.
- `created_by` is the authenticated user; `assigned_to` is optional and must be an in-tenant user.
- Due dates are stored as timestamps; overdue is a UI-derived state (no calendar integration).
- AI task suggestion is optional and additive; the feature is fully functional with manual entry. Suggestion uses 006/007/010 outputs when available.
- Terminal statuses (`completed`, `cancelled`) are immutable for fields; reopening is out of scope for MVP.
- The detail page's "Create Task" placeholder from Spec 005 is replaced by the real task-creation control; the "Escalate" placeholder remains a placeholder.
- Audit logging is a future integration; this feature exposes enough data (actor, action, timestamps) for that feature to log later, but does not implement logging itself.
