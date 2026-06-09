# API Contracts: Follow-Up Tasks

**Branch**: `011-follow-up-tasks` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT; requires `staff` or `manager`. Platform Admin → 403. `tenant_id` and `created_by` are always derived from the JWT; any client-supplied tenant is ignored. Every endpoint resolves the task/message tenant first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–010). Referenced `related_message_id` and `assigned_to` must resolve within the caller's tenant. **No endpoint sends a client message or creates an escalation.**

---

## 1. POST /api/tasks

Create a follow-up task from a message. `staff`/`manager`. Human-confirmed (the only creation path).

**Request body**:
```json
{
  "related_message_id": "b1000000-0000-0000-0000-000000000010",
  "title": "Check catering capacity for updated guest count",
  "description": "Confirm whether catering, seating, and venue setup can support 220 guests.",
  "assigned_to": "c2000000-0000-0000-0000-000000000045",
  "due_date": "2026-06-10T17:00:00Z",
  "priority": "high"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `related_message_id` | UUID | yes | The message the task is created from (must be in tenant) |
| `title` | string | yes | 1–200 chars, non-blank |
| `description` | string | no | Optional details |
| `assigned_to` | UUID | no | An in-tenant user; omit for unassigned |
| `due_date` | datetime | no | Optional; past dates allowed (overdue flagged in UI) |
| `priority` | string (TaskPriority) | no | `low`/`medium`/`high`; default `medium` |

**Validation rules**:
- `title` non-empty, ≤ 200 chars → 422.
- `priority` ∈ `TaskPriority` → 422.
- `related_message_id` resolves in tenant → 404/403.
- `assigned_to` (if set) is an in-tenant user → 422 `INVALID_ASSIGNEE`.

**Response 201**:
```json
{
  "id": "f3000000-0000-0000-0000-000000000001",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "related_message_id": "b1000000-0000-0000-0000-000000000010",
  "conversation_id": "a0000000-0000-0000-0000-000000000007",
  "title": "Check catering capacity for updated guest count",
  "description": "Confirm whether catering, seating, and venue setup can support 220 guests.",
  "assigned_to": "c2000000-0000-0000-0000-000000000045",
  "created_by": "c2000000-0000-0000-0000-000000000045",
  "due_date": "2026-06-10T17:00:00Z",
  "priority": "high",
  "status": "open",
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z",
  "completed_at": null
}
```
Side effect: the related message's status may become `task_created`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Related message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Related message does not exist | `MESSAGE_NOT_FOUND` |
| 422 | Invalid title/priority | validation detail |
| 422 | Assignee not in tenant | `INVALID_ASSIGNEE` |

---

## 2. GET /api/tasks

List tasks in the caller's tenant. `staff`/`manager`.

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string (TaskStatus) | — | Filter by status |
| `priority` | string (TaskPriority) | — | Filter by priority |
| `assigned_to` | UUID | — | Filter by assignee |
| `related_message_id` | UUID | — | Filter by source message |

**Response 200**:
```json
{
  "items": [ { "...": "TaskResponse (see POST)" } ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 422 | Invalid filter value | validation detail |

---

## 3. GET /api/tasks/{task_id}

Fetch a single task in the caller's tenant. `staff`/`manager`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | UUID | The task to fetch. |

**Response 200**: a `TaskResponse` (see POST).

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Task in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Task does not exist | `TASK_NOT_FOUND` |
| 422 | `task_id` not a UUID | validation detail |

---

## 4. PATCH /api/tasks/{task_id}

Update a task (fields, status transition, reassign). `staff`/`manager`. Allowed only on non-terminal tasks.

**Request body** (all optional):
```json
{
  "title": "Confirm catering for 220 guests",
  "description": "Updated note.",
  "assigned_to": "c2000000-0000-0000-0000-000000000099",
  "due_date": "2026-06-11T12:00:00Z",
  "priority": "medium",
  "status": "in_progress"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | New title (1–200) |
| `description` | string | New description |
| `assigned_to` | UUID | Reassign to an in-tenant user |
| `due_date` | datetime | New due date |
| `priority` | string (TaskPriority) | New priority |
| `status` | string (TaskStatus) | Transition (`open`/`in_progress`/`completed`/`cancelled`) |

**Validation rules**:
- `task_id` valid UUID; task resolves in tenant → 404/403.
- Task non-terminal → else 422 `INVALID_STATE_TRANSITION`.
- `status` transition allowed by the state machine → else 422 `INVALID_STATE_TRANSITION`.
- `assigned_to` (if set) in-tenant → 422 `INVALID_ASSIGNEE`.
- Setting `status=completed` sets `completed_at`.

**Response 200**: updated `TaskResponse` with refreshed `updated_at`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Task in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Task does not exist | `TASK_NOT_FOUND` |
| 422 | Invalid field value | validation detail |
| 422 | Terminal task / illegal transition | `INVALID_STATE_TRANSITION` |
| 422 | Assignee not in tenant | `INVALID_ASSIGNEE` |

---

## 5. POST /api/tasks/{task_id}/complete

Mark a task completed. `staff`/`manager`. Allowed only on non-terminal tasks. Sets `completed_at`.

**Request body**: none (or optional `{ "note": "..." }`, not used for any action).

**Validation rules**:
- `task_id` valid UUID; task resolves in tenant → 404/403.
- Task non-terminal → else 422 `INVALID_STATE_TRANSITION`.

**Response 200**: `TaskResponse` with `status` `completed`, `completed_at` set.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Task in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Task does not exist | `TASK_NOT_FOUND` |
| 422 | Already `completed`/`cancelled` | `INVALID_STATE_TRANSITION` |

> Cancelling is done via `PATCH {"status":"cancelled"}` (a dedicated `/cancel` endpoint may mirror this; both go through the same guarded transition).

---

## 6. GET /api/messages/{message_id}/tasks

List the tasks created from a specific message, tenant-scoped. `staff`/`manager`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The source message. |

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000010",
  "items": [ { "...": "TaskResponse" } ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 422 | `message_id` not a UUID | validation detail |

---

## 7. (Optional) POST /api/messages/{message_id}/task-suggestion

Return proposed task details for a message from its intent (006), risk (007), and suggested reply (010). `staff`/`manager`. **Creates nothing.**

**Request body**: none.

**Response 200**:
```json
{
  "title": "Verify deposit payment confirmation",
  "description": "Check payment records and confirm the deposit status with the client.",
  "priority": "high",
  "source": "ai_suggestion"
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 503 | Suggestion service unavailable | `SUGGESTION_UNAVAILABLE` |

> The suggestion is advisory. To create the task, the client calls `POST /api/tasks` with the (possibly edited) values. There is no path where a suggestion becomes a task without that explicit call.

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Create task | 201 | Task stored `open`; related message may become `task_created` |
| Create with cross-tenant message/assignee | 404/403/422 | none |
| List / get | 200 | none (tenant-scoped) |
| Update fields / reassign | 200 | `updated_at` refreshed |
| Transition to in_progress | 200 | status change |
| Complete | 200 | status `completed`, `completed_at` set |
| Cancel (PATCH status) | 200 | status `cancelled` |
| Edit/complete/cancel a terminal task | 422 | none |
| Message tasks list | 200 | none |
| Suggestion (optional) | 200 | **no task created** |
| Any endpoint, Platform Admin | 403 | none |
| Task creation | (always) | **no client message sent; no escalation created** |

---

## Role Matrix

| Endpoint | staff | manager | platform_admin |
|----------|-------|---------|----------------|
| POST /api/tasks | ✅ | ✅ | ❌ 403 |
| GET /api/tasks | ✅ | ✅ | ❌ 403 |
| GET /api/tasks/{id} | ✅ | ✅ | ❌ 403 |
| PATCH /api/tasks/{id} | ✅ | ✅ (incl. reassign) | ❌ 403 |
| POST /api/tasks/{id}/complete | ✅ | ✅ | ❌ 403 |
| GET /api/messages/{id}/tasks | ✅ | ✅ | ❌ 403 |
| POST /api/messages/{id}/task-suggestion | ✅ | ✅ | ❌ 403 |

---

## Non-Goals (contract-level)

These endpoints never: send a client message, create or perform an escalation, auto-create a task from a suggestion, or write audit logs. Audit logging of task actions is a **future integration** (separate audit-log feature). `task_created` on the message is the only side effect, and it is non-destructive.
