# Requirements Checklist: Follow-Up Tasks

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (trackable follow-up actions) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI behavior, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Staff can create a task linked to a message, scoped to their tenant, with a human-written/confirmed title (FR-001, AC-01)
- [ ] Stored fields: id, tenant_id, related_message_id, title, description, assigned_to, created_by, due_date, priority, status, created_at, updated_at, completed_at (FR-002)
- [ ] New tasks created with status `open` (FR-003)
- [ ] Title/priority/status/due-date/assignee validated (FR-004, AC-02)
- [ ] Staff/manager can list (filtered) and fetch a single task (FR-005, AC-04, AC-06)
- [ ] Staff/manager can update fields; manager can reassign (FR-006, AC-07, AC-08)
- [ ] Staff can complete (sets completed_at) and cancel a task (FR-007, AC-09, AC-10)
- [ ] Invalid state transitions rejected (FR-008, AC-11)
- [ ] Task creation sends no client message (FR-010, AC-13)
- [ ] Task creation creates no escalation (FR-011, AC-13)
- [ ] Operations are tenant-scoped (FR-012, AC-03)
- [ ] Tasks appear on Tasks page + message tasks list (FR-013, AC-12, AC-17)
- [ ] On creation, related message may become `task_created` (FR-014, AC-16)
- [ ] `created_by` + timestamps recorded; `completed_at` on completion (FR-015)

---

## Task Workflow Requirements

- [ ] Status lifecycle: open → in_progress → completed | cancelled
- [ ] `open → completed|cancelled` directly allowed
- [ ] `completed`/`cancelled` are terminal; edits/transitions rejected (AC-11)
- [ ] `completed` sets `completed_at`; cannot be cleared
- [ ] Completed/cancelled tasks remain listed and filterable (AC-09/AC-10 + list)
- [ ] Priority defaults to `medium`; due date optional (overdue derived in UI)
- [ ] Multiple tasks per message allowed (independent)
- [ ] Reassignment updates `assigned_to` to an in-tenant user only (AC-08)

---

## Optional AI Task-Suggestion Requirements

- [ ] Suggestion endpoint returns proposed title/description/priority and creates NOTHING (FR-009, AC-14)
- [ ] Suggestion uses message + intent (006) + risk (007) + suggested reply (010) when available
- [ ] Suggested priority is informed by risk level; user can override
- [ ] No task is created without explicit human confirmation (SR-08)
- [ ] Suggestion-service failure → 503; manual creation still works
- [ ] Feature flag can disable suggestions cleanly

---

## Security Requirements

- [ ] `tenant_id` always derived from JWT — never from the client (SR-01)
- [ ] A task belongs to exactly one tenant (SR-02)
- [ ] `related_message_id` and `assigned_to` must resolve in the caller's tenant (SR-03, AC-18)
- [ ] Only `staff`/`manager` use task endpoints; Platform Admin → 403 (SR-04, AC-15)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent task/message → 404; cross-tenant → 403 (SR-05)
- [ ] Task creation/updates send no message and create no escalation (SR-06)
- [ ] `created_by` is the authenticated user; assignee cannot be cross-tenant (SR-07)
- [ ] AI cannot auto-create tasks (SR-08)

---

## Tenant Isolation Requirements

- [ ] Listing returns only the caller's tenant tasks (AC-03, AC-04)
- [ ] Tenant A cannot read/update/complete a Tenant B task (AC-06)
- [ ] Cross-tenant related message rejected on create (AC-18)
- [ ] Cross-tenant assignee rejected (AC-08, INVALID_ASSIGNEE)
- [ ] `GET /messages/{id}/tasks` is tenant-scoped (AC-12)
- [ ] A client-supplied `tenant_id` is ignored (tenant from JWT)
- [ ] No shared/cross-tenant tasks exist

---

## API Requirements

- [ ] `POST /api/tasks` creates a task (201); validates references + fields (AC-01, AC-02, AC-18)
- [ ] `GET /api/tasks` lists with status/priority/assignee/related_message filters (AC-04, AC-05)
- [ ] `GET /api/tasks/{id}` returns one task; cross-tenant → 404/403 (AC-06)
- [ ] `PATCH /api/tasks/{id}` updates fields/status/reassign; terminal → 422 (AC-07, AC-08, AC-11)
- [ ] `POST /api/tasks/{id}/complete` completes; terminal → 422 (AC-09, AC-11)
- [ ] `GET /api/messages/{id}/tasks` lists a message's tasks (AC-12)
- [ ] (Optional) `POST /api/messages/{id}/task-suggestion` returns proposal, creates nothing (AC-14)
- [ ] Role matrix enforced; Platform Admin 403 everywhere (AC-15)
- [ ] Error responses use consistent `error_code` values per the contract

---

## Data Requirements

- [ ] `tasks` table created via Alembic migration
- [ ] `related_message_id` FK (`ON DELETE CASCADE`) + index; `tenant_id` FK + index
- [ ] `created_by` FK → users; `assigned_to` nullable FK → users; optional `conversation_id`
- [ ] `TaskStatus` enum: open, in_progress, completed, cancelled
- [ ] `TaskPriority` enum: low, medium, high
- [ ] `status` defaults `open`; `priority` defaults `medium`; `completed_at` set only when completed
- [ ] Indexes on `(tenant_id, status)`, `(tenant_id, priority)`, `(tenant_id, assigned_to)`, `(tenant_id, related_message_id)`
- [ ] `messages.status` supports `task_created` (migration or free-string), non-destructive
- [ ] State machine enforced at the data/service layer

---

## Testing Requirements

- [ ] Unit: state machine (valid/invalid transitions), assignee in-tenant validation, due-date handling
- [ ] Unit: task suggester (priority-from-risk, deterministic stub, unavailable fallback)
- [ ] Integration: create + stored fields (AC-01); validation rejections (AC-02, AC-18)
- [ ] Integration: tenant isolation list/get (AC-03, AC-04, AC-06)
- [ ] Integration: filters (AC-05); update + updated_at (AC-07); reassign + out-of-tenant assignee (AC-08)
- [ ] Integration: complete + completed_at (AC-09); cancel (AC-10); invalid transitions (AC-11)
- [ ] Integration: message tasks list (AC-12); no message/escalation side effects (AC-13)
- [ ] Integration: suggestion returns details + creates nothing; confirm creates (AC-14)
- [ ] Integration: Platform Admin 403 (AC-15); message → task_created (AC-16)
- [ ] Frontend: Tasks page + message tasks list render; form validation; complete/cancel update; manager reassign (AC-17)
- [ ] Quickstart: all 5 scenarios (guest-count, payment, callback, isolation, completion)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No escalation workflow (task creation never escalates)
- [ ] No sending of any client message
- [ ] No auto-creation of tasks (human confirmation required)
- [ ] No audit-log implementation (named as a future integration/dependency)
- [ ] No calendar syncing / reminders / notifications
- [ ] No recurring tasks / subtasks / task dependencies
- [ ] No task comments / attachments
- [ ] No cross-tenant or shared tasks
- [ ] No full CRM / project management
- [ ] No real WhatsApp API

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build the service (with tenant + assignee validation + state machine) before the API; the AI suggester is optional and strictly read-only.
- Two hard guarantees to verify: (1) no auto-create — suggestion is read-only, creation is a separate confirmed POST; (2) no side effects — creation sends no message and creates no escalation.
- **Audit logging is a future integration** — this feature stores actor + action + timestamps for the later audit-log feature to consume; it does not implement logging.
