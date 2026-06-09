# Research: Follow-Up Tasks

**Branch**: `011-follow-up-tasks` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Human-Confirmed Creation; AI Suggestion Is Read-Only

**Decision**: Tasks are created only via an explicit authenticated `POST /api/tasks`. The optional AI suggestion is a separate **read-only** endpoint that returns proposed fields and creates nothing.

**Rationale**:
- The hard constraint is "no auto-create without staff confirmation" (FR-009, SR-08). Making suggestion a read-only endpoint and creation a distinct write makes this structural, not a matter of discipline.
- Staff can always create manually; the suggestion is additive convenience.

**Alternatives considered**:
- A single "generate-and-create" endpoint with a confirm flag: easy to misuse / accidentally auto-create; rejected.
- AI creates a `draft` task awaiting approval: introduces a task pre-state and lifecycle complexity not needed for MVP; the read-only suggestion + explicit create is simpler and equally safe.

---

## Decision 2: Status State Machine with Terminal Immutability

**Decision**: `TaskStatus` = `open → in_progress → completed | cancelled`, with `open → completed|cancelled` also allowed. `completed`/`cancelled` are terminal; edits/transitions on terminal tasks are rejected (422). `completed_at` is set on completion.

**Rationale**:
- A small explicit machine prevents nonsensical transitions (e.g., editing a completed task, un-cancelling) and gives a clean record for the future audit feature.
- Terminal immutability keeps closed tasks trustworthy; reopening is out of scope for MVP.

**Alternatives considered**:
- Free-form status field: error-prone; rejected.
- Allow reopening completed tasks: useful but adds transitions + audit nuance; deferred.

---

## Decision 3: Task Links to a Message; Conversation Optional

**Decision**: `related_message_id` is required (every task originates from a message). `conversation_id` is optional metadata stored when the message has one.

**Rationale**:
- The feature's purpose is turning a *message* into an action, so the message link is the anchor (and supports `GET /messages/{id}/tasks`).
- Not all messages have a conversation in every flow; making conversation optional avoids blocking task creation while still capturing it when present.

**Alternatives considered**:
- Require conversation: would block tasks for message-only contexts; rejected.
- Link to conversation instead of message: loses the precise message provenance the spec wants; rejected.

---

## Decision 4: In-Tenant Reference Validation (message + assignee)

**Decision**: On create/update, resolve `related_message_id` and `assigned_to` within the JWT tenant before writing. Cross-tenant message → 404/403; cross-tenant/invalid assignee → 422 `INVALID_ASSIGNEE`.

**Rationale**:
- Tenancy must hold for *every* referenced entity, not just the task row (SR-03, SR-07). Validating references up front prevents creating a task that points across tenants.
- Consistent with the Specs 005–010 resolve-first pattern.

**Alternatives considered**:
- Trust client-provided ids: unsafe; rejected.
- Allow unassigned only: too restrictive; assignment to in-tenant users is core to the workflow.

---

## Decision 5: Message Status → `task_created` (non-destructive side effect)

**Decision**: On task creation, set the related message's status to `task_created` (reusing the Spec 003/005 message-status model). The update is isolated so a failure there never fails task creation, and it does not block creating further tasks from the same message.

**Rationale**:
- Gives inbox/detail a visible signal that a message has been actioned (FR-014, AC-16).
- Non-destructive + isolated keeps the primary action (task creation) robust.

**Alternatives considered**:
- A separate boolean flag on the message instead of a status value: viable; the spec calls for a `task_created` status, so we reuse the status field (documented in data-model). Either is acceptable; status chosen for spec alignment.
- No message signal: loses useful inbox context; rejected.

---

## Decision 6: No Side Effects — No Send, No Escalation

**Decision**: No task endpoint or service method sends a client message or creates an escalation. Escalation is a separate feature; messaging is out of scope entirely.

**Rationale**:
- Direct scope boundary (FR-010, FR-011, SR-06). Keeping tasks a pure tracking entity means the future escalation feature can consume tasks/risk without entanglement, and there is no accidental client communication.

---

## Decision 7: Enums as Constrained Strings

**Decision**: `TaskStatus` and `TaskPriority` persist as application-level string enums in VARCHAR columns, validated at the boundary (Pydantic/SQLAlchemy).

**Rationale**:
- Portable + evolvable (e.g., a future `blocked` status) without enum-altering migrations; invalid values are rejected at the API (422) so the DB never stores them.

---

## Decision 8: Priority Defaults + Risk-Informed Suggestion

**Decision**: `priority` defaults to `medium`. The optional AI suggestion maps the Spec 007 risk level to a suggested priority (high risk → `high`, medium → `medium`, low → `low`/`medium`), which the staff user can override.

**Rationale**:
- A sensible default keeps manual creation fast. Tying suggested priority to existing risk reuses upstream signal and matches the examples (guest-count/payment → high/medium).
- Override preserves human control (the suggestion is advisory).

---

## Decision 9: Filtering + Indexing for the Tasks Page

**Decision**: Support listing filtered by `status`, `priority`, `assigned_to`, and `related_message_id`, all within the tenant. Add composite indexes `(tenant_id, status)`, `(tenant_id, priority)`, `(tenant_id, assigned_to)`, `(tenant_id, related_message_id)`.

**Rationale**:
- These are the natural triage views (my open tasks, high-priority, a message's tasks). Tenant-leading composite indexes serve them efficiently while keeping the tenant filter first.

---

## Decision 10: Audit Logging Is a Future Integration, Not Built Here

**Decision**: This feature does not implement audit logging. It records enough on each task (actor `created_by`/`approved` semantics via `assigned_to`, timestamps, status) for the later audit-log feature to record create/update/complete/cancel/reassign events.

**Rationale**:
- Explicitly requested. Keeping audit out avoids premature coupling; the audit feature will hook task service events when built. Named as a dependency/future integration in the spec.

---

## Decision 11: Due Date Stored, Overdue Is UI-Derived

**Decision**: `due_date` is an optional timestamp. Past due dates are allowed by default (`TASK_ALLOW_PAST_DUE = true`); "overdue" is computed in the UI (due_date < now and status not terminal). No calendar sync, no reminders.

**Rationale**:
- Staff sometimes backdate or set tight deadlines; blocking past dates is annoying and rarely desired. Overdue as a derived state keeps the data simple and avoids scope creep (no calendar/notifications).

---

## Resolved Configuration Defaults

| Setting | Default | Purpose |
|---------|---------|---------|
| `TASK_MAX_TITLE_LEN` | `200` | Title length cap |
| `TASK_ALLOW_PAST_DUE` | `true` | Permit past due dates (overdue flagged in UI) |
| `TASK_SUGGESTION_ENABLED` | `true` | Toggle the optional AI suggestion endpoint |
| Default priority | `medium` | When not specified |
| Default status | `open` | On creation |
