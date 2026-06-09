# Implementation Plan: Follow-Up Tasks

**Branch**: `011-follow-up-tasks` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/011-follow-up-tasks/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenant isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT; `staff`/`manager`; assignee in-tenant; Platform Admin blocked
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): messages (`related_message_id`, `conversation_id`)
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): entry point; replaces the "Create Task" placeholder
- [Spec 006 / 007 / 010] (optional): intent / risk / suggested reply → inputs to the optional AI task suggestion

**Future integration**: the audit-log feature will log task actions (create/update/complete/cancel/reassign). Not implemented here; the data model exposes actor + action + timestamps for it.

---

## Summary

Add tenant-scoped follow-up tasks created from messages. A new `tasks` table stores `related_message_id`, `title`, `description`, `assigned_to`, `created_by`, `due_date`, `priority`, `status`, `conversation_id` (optional), and timestamps (`completed_at` on completion). A `TaskService` enforces tenant ownership (404/403, Specs 005–010 pattern), validates in-tenant references (message + assignee), and runs a status state machine (`open → in_progress → completed | cancelled`). Six REST endpoints cover create / list / get / update / complete / message-tasks (plus an optional suggestion endpoint that returns proposed details and **creates nothing**). On creation the related message may be set to `task_created`. The feature **sends no client message and creates no escalation**, and the AI may only *suggest* — never auto-create. Tasks surface on a Tasks page and the message detail page (replacing the "Create Task" placeholder).

---

## Technical Approach

- **Human-confirmed creation**: tasks are created only via an explicit authenticated `POST /api/tasks`. The optional suggestion endpoint is read-only (returns proposed fields), keeping "no auto-create" structural (FR-009, SR-08).
- **In-tenant reference validation**: on create/update, `related_message_id` and `assigned_to` are resolved within the JWT tenant; cross-tenant references → 404/403/422 before anything is written (SR-03).
- **Status state machine**: `open → in_progress → completed|cancelled`; `open → completed|cancelled` allowed; terminal states immutable; invalid transitions → 422.
- **Message status side effect**: on create, set the related message's status to `task_created` (non-destructive); isolated so a failure there never fails task creation.
- **Optional AI suggestion**: a `TaskSuggester` assembles message + intent (006) + risk (007) + suggested reply (010) and returns title/description/priority; behind an interface with a deterministic stub; failure → 503 but manual creation still works.
- **No side effects**: no endpoint/method sends a client message or creates an escalation (SR-06).

---

## Backend Tasks

1. **`schemas/task.py`** — Pydantic: `TaskCreateRequest`, `TaskUpdateRequest`, `TaskResponse`, `TaskListResponse`, `CompleteRequest` (none/optional), `TaskSuggestionResponse`, plus `TaskStatus` and `TaskPriority` enums.
2. **`services/task_service.py`**:
   - `create_task(session, tenant_id, user, data)` — validate title/priority, resolve message + assignee in-tenant, store status `open`, set `created_by`, set message `task_created` (isolated).
   - `list_tasks(session, tenant_id, filters)` — tenant-scoped list with status/priority/assignee/related_message filters.
   - `get_task(session, tenant_id, task_id)` — tenant-resolve (404/403).
   - `update_task(session, tenant_id, task_id, data)` — non-terminal; update allowed fields; validate assignee; guard transitions.
   - `complete_task(session, tenant_id, task_id)` — non-terminal → `completed`, set `completed_at`.
   - `cancel_task(...)` / status transition via update — `cancelled`.
   - `tasks_for_message(session, tenant_id, message_id)` — tenant-resolve message, return its tasks.
3. **`ai/task_suggester.py`** (optional) — `suggest(message, intent, risk, reply) -> (title, description, priority)`; interface + deterministic stub; raises `SuggestionUnavailable`.
4. **`api/v1/tasks.py`** — six task endpoints + optional suggestion endpoint, with `require_role(staff, manager)` + error→HTTP + state-machine guards.
5. **Reuse upstream** — read message (003), and (for suggestion) intent (006)/risk (007)/reply (010); validate assignee against users (002).
6. **Config** — `TASK_MAX_TITLE_LEN`, `TASK_ALLOW_PAST_DUE` (default true), `TASK_SUGGESTION_ENABLED` in settings.
7. **Router mount** — register the tasks router at `/api` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `tasks`:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL FK → tenants, indexed
   - `related_message_id` UUID NOT NULL FK → messages, `ON DELETE CASCADE`, indexed
   - `conversation_id` UUID NULL FK → conversations (optional metadata)
   - `title` VARCHAR(200) NOT NULL
   - `description` TEXT NULL
   - `assigned_to` UUID NULL FK → users
   - `created_by` UUID NOT NULL FK → users
   - `due_date` TIMESTAMPTZ NULL
   - `priority` VARCHAR(10) NOT NULL default `medium`
   - `status` VARCHAR(20) NOT NULL default `open`
   - `created_at`, `updated_at` TIMESTAMPTZ
   - `completed_at` TIMESTAMPTZ NULL
2. **Indexes**: `(tenant_id, status)`, `(tenant_id, priority)`, `(tenant_id, assigned_to)`, `(tenant_id, related_message_id)` for filtered listing.
3. **SQLAlchemy model** `Task` in `models/task.py` with relationships to `Message`, `User` (creator + assignee), optional `Conversation`.
4. **Enums** `TaskStatus`/`TaskPriority` as constrained strings, validated at the boundary.
5. **Message status** — reuse Spec 003/005 `messages.status`; add/allow a `task_created` value (or a separate flag) per the project's message-status model; document the choice in data-model.

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/tasks` | POST | staff, manager | Create a task (human-confirmed) |
| `/api/tasks` | GET | staff, manager | List tenant tasks (filters) |
| `/api/tasks/{task_id}` | GET | staff, manager | Get one task |
| `/api/tasks/{task_id}` | PATCH | staff, manager | Update fields / status / reassign |
| `/api/tasks/{task_id}/complete` | POST | staff, manager | Mark completed |
| `/api/messages/{message_id}/tasks` | GET | staff, manager | List a message's tasks |
| `/api/messages/{message_id}/task-suggestion` | POST | staff, manager | (Optional) propose task details; creates nothing |

- All resolve tenant first (404/403) per SR-05; `tenant_id`/`created_by` from JWT only.
- Assignee validated in-tenant; transitions guarded (422).
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/tasks.ts`** — typed client: `createTask`, `listTasks(filters)`, `getTask(id)`, `updateTask(id, payload)`, `completeTask(id)`, `tasksForMessage(messageId)`, `suggestTask(messageId)`.
2. **`types/task.ts`** — `TaskStatus`, `TaskPriority`, `Task`, `TaskSuggestion` TS types.
3. **`pages/TasksPage.tsx`** — `/tasks` route; lists tenant tasks with status/priority/assignee filters; staff + manager.
4. **`components/tasks/TaskList.tsx`** + `TaskRow.tsx` — table/cards: title, status badge, priority badge, assignee, due date (overdue highlight), related message link.
5. **`components/tasks/TaskForm.tsx`** — create/edit: title, description, assignee select (in-tenant users), due date, priority; optional "Suggest with AI" button (prefills from suggestion; user edits + confirms).
6. **`components/tasks/TaskDetail.tsx`** — view + actions: edit, progress (in_progress), complete, cancel, reassign (manager).
7. **Detail-page integration (Spec 005)** — replace the "Create Task" placeholder with a "Create Task" control opening `TaskForm` prefilled from the message (and optional suggestion); show the message's existing tasks.
8. **States** — loading, empty, validation errors (422 inline), forbidden (admin), not-found, suggestion-unavailable (fall back to manual), terminal-state (disable edits).

---

## Optional AI Task-Suggestion Tasks

1. **Suggester interface** — `TaskSuggester.suggest(context) -> {title, description, priority}`; LLM/heuristic impl + deterministic stub.
2. **Context assembly** — message text + intent (006) + risk (007) + suggested reply (010) when available; tenant-scoped only.
3. **Priority hint** — map risk level → suggested priority (high risk → high), user-overridable.
4. **Read-only guarantee** — the suggestion endpoint creates nothing; task creation remains a separate confirmed POST.
5. **Graceful fallback** — `SuggestionUnavailable` → 503; UI falls back to manual entry.
6. **Feature flag** — `TASK_SUGGESTION_ENABLED` to disable cleanly.

---

## Testing Tasks

**Backend integration** — `tests/integration/test_tasks.py`:
- Create linked to message + stored fields (AC-01); validation rejections (AC-02, AC-18)
- Tenant isolation list/get (AC-03, AC-04, AC-06)
- Filters (AC-05); update + updated_at (AC-07); reassign + out-of-tenant assignee (AC-08)
- Complete + completed_at (AC-09); cancel (AC-10); invalid transitions (AC-11)
- Message tasks list (AC-12); no client message / no escalation side effects (AC-13)
- Optional suggestion returns details + creates nothing; confirm creates (AC-14)
- Platform Admin 403 (AC-15); message status → task_created (AC-16)

**Unit** — `tests/unit/test_task_service.py`: state machine (valid/invalid transitions), assignee in-tenant validation, due-date handling; `tests/unit/test_task_suggester.py`: priority-from-risk, deterministic stub, unavailable fallback.

**Frontend** — render/interaction: Tasks page lists tenant tasks; form validation surfaces 422; complete/cancel update; manager reassign; suggestion prefill then confirm (AC-17).

---

## Build Order

1. **DB + model** — Alembic migration + `Task` model + enums; confirm `messages.status` supports `task_created`.
2. **Schemas** — Pydantic models + enums.
3. **Service** — `task_service` (create/list/get/update/complete/cancel/message-tasks) with tenant + assignee validation + state machine + message-status side effect.
4. **API** — six endpoints + router mount + error/state mapping; integration tests.
5. **Optional suggester** — `task_suggester` + suggestion endpoint (read-only) + unit tests.
6. **Frontend** — types + API client → Tasks page → list → form (manual + optional suggest) → detail (update/complete/cancel/reassign) → detail-page "Create Task" integration → states.
7. **Validation** — run the 5-scenario quickstart (guest-count, payment, callback, tenant isolation, completion); confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/011-follow-up-tasks/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── tasks.py                     # 6 task endpoints + optional suggestion
│   ├── services/
│   │   └── task_service.py              # create / list / get / update / complete / cancel / message-tasks
│   ├── ai/
│   │   └── task_suggester.py            # optional suggestion (interface + stub)
│   ├── models/
│   │   └── task.py                      # Task ORM model
│   └── schemas/
│       └── task.py                      # Pydantic + TaskStatus/TaskPriority enums
├── alembic/versions/
│   └── 00xx_create_tasks.py
└── tests/
    ├── integration/
    │   └── test_tasks.py
    └── unit/
        ├── test_task_service.py
        └── test_task_suggester.py

frontend/
└── src/
    ├── api/
    │   └── tasks.ts
    ├── types/
    │   └── task.ts
    ├── pages/
    │   └── TasksPage.tsx
    └── components/tasks/
        ├── TaskList.tsx
        ├── TaskRow.tsx
        ├── TaskForm.tsx
        └── TaskDetail.tsx
```

Modified files:

```
backend/app/main.py                          # mount tasks router
backend/app/core/config.py                   # TASK_* settings
backend/app/services/<message status owner>  # allow messages.status = task_created
frontend/src/App.tsx                         # add /tasks route
frontend/src/pages/ConversationDetailPage    # replace "Create Task" placeholder with real control + message tasks
frontend/src/components/NavBar (or Sidebar)  # add Tasks nav item
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–010. Task creation is a deliberate, human-confirmed `POST`; the optional AI suggester lives in `backend/app/ai/` and is strictly read-only, keeping the "no auto-create / no auto-escalate / no send" guarantees in the service layer.
