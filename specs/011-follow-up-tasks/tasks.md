---
description: "Task list for Follow-Up Tasks feature implementation"
---

# Tasks: Follow-Up Tasks

**Branch**: `011-follow-up-tasks` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/011-follow-up-tasks/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `get_current_tenant_context`, `conversations`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; Platform Admin block; `users` table (for `created_by`/`assigned_to` in-tenant validation)
- Spec 003 — Message Simulator: `messages` table + `status` field + optional `conversation_id`; the message a task links to
- Spec 005 — Message Detail Page: conversation/message detail page with the "Create Task" placeholder this feature replaces
- Spec 006 — Intent Classifier (optional): intent input to the optional AI task suggestion
- Spec 007 — Risk Detection (optional): risk level → suggested-priority hint
- Spec 010 — Suggested Replies (optional): suggested-reply context for the optional AI task suggestion

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `tasks` + one Alembic migration. `TaskStatus`/`TaskPriority` persisted as constrained strings (VARCHAR + app-boundary validation), not native PG enums (consistent with Specs 008–010). The related `messages.status` may gain a `task_created` value (migration or free-string, per the project's message-status model).

**Config defaults** (research.md Resolved Configuration): `TASK_MAX_TITLE_LEN=200`, `TASK_ALLOW_PAST_DUE=true`, `TASK_SUGGESTION_ENABLED=true`; default priority `medium`, default status `open`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US4]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–010 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant`/`tenants` (Spec 001), `User` + role enum + an "is user in tenant" lookup (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `Message`/`messages` + `status` + `conversation_id` (Spec 003), `conversations` (Spec 001/003), `NotFoundError`/`ForbiddenError` + their error→HTTP mapping (Spec 001), and the shared `error_code` envelope. Do NOT redefine any of these.
- [ ] T002 Add `TASK_MAX_TITLE_LEN` (200), `TASK_ALLOW_PAST_DUE` (true), and `TASK_SUGGESTION_ENABLED` (true) to `backend/app/core/config.py` with documented defaults (research.md)
- [ ] T003 Determine and document the `messages.status` model: is it a constrained enum (Spec 003/005) or a free string? Record whether the migration must add a `task_created` allowed value or whether no DB change is needed (data-model.md "Message status note")
- [ ] T004 Verify `backend/tests/unit/` and `backend/tests/integration/` exist with `__init__.py`; create any that are missing

**Checkpoint**: Dependencies confirmed reused; config in place; message-status approach decided.

---

## Phase 2: Database & Model (Foundational — Blocking)

**Purpose**: The `tasks` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–8 cannot run without this phase.

- [ ] T005 [P] Create the `TaskStatus` (`open`, `in_progress`, `completed`, `cancelled`) and `TaskPriority` (`low`, `medium`, `high`) string enums in `backend/app/schemas/task.py` (shared by service + API layers) — per data-model.md
- [ ] T006 Create the `Task` SQLAlchemy model in `backend/app/models/task.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `related_message_id` UUID FK→`messages.id` `ON DELETE CASCADE` NOT NULL indexed; `conversation_id` UUID FK→`conversations.id` NULL; `title` VARCHAR(200) NOT NULL; `description` TEXT NULL; `assigned_to` UUID FK→`users.id` NULL; `created_by` UUID FK→`users.id` NOT NULL; `due_date` TIMESTAMPTZ NULL; `priority` VARCHAR(10) NOT NULL default `medium`; `status` VARCHAR(20) NOT NULL default `open`; `created_at`/`updated_at` TIMESTAMPTZ (server_default now, updated_at onupdate now); `completed_at` TIMESTAMPTZ NULL; `message` + `assignee`(foreign_keys=[assigned_to]) + `creator`(foreign_keys=[created_by]) relationships; `Index("ix_tasks_tenant_status", "tenant_id", "status")`, `Index("ix_tasks_tenant_priority", "tenant_id", "priority")`, `Index("ix_tasks_tenant_assignee", "tenant_id", "assigned_to")`, `Index("ix_tasks_tenant_message", "tenant_id", "related_message_id")` — per data-model.md (depends on T005)
- [ ] T007 Create Alembic migration `backend/alembic/versions/00xx_create_tasks.py`: create `tasks` with all columns, the four FKs (`tenant_id`→`tenants.id`, `related_message_id`→`messages.id` ON DELETE CASCADE, `assigned_to`→`users.id`, `created_by`→`users.id`, `conversation_id`→`conversations.id`), defaults (`status='open'`, `priority='medium'`), and the four composite indexes; **if** `messages.status` is a constrained enum (per T003), add the `task_created` allowed value here (non-destructive); provide a correct `downgrade()` dropping the table + indexes (and reverting the enum value if added) (depends on T006, T003)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable; `messages.status` accepts `task_created`.

---

## Phase 3: Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service and endpoints.

- [ ] T008 Add Pydantic models to `backend/app/schemas/task.py` (alongside the enums from T005) per data-model.md: `TaskCreateRequest` (`related_message_id: UUID`, `title` 1–200 + `field_validator` stripping/rejecting blank, `description: str | None = None`, `assigned_to: UUID | None = None`, `due_date: datetime | None = None`, `priority: TaskPriority = medium`), `TaskUpdateRequest` (all optional: `title` (≤200), `description`, `assigned_to`, `due_date`, `priority`, `status`), `TaskResponse` (`id`, `tenant_id`, `related_message_id`, `conversation_id`, `title`, `description`, `assigned_to`, `created_by`, `due_date`, `priority`, `status`, `created_at`, `updated_at`, `completed_at`; `from_attributes=True`), `TaskListResponse` (`items: list[TaskResponse]`, `total: int`), `MessageTasksResponse` (`message_id: UUID`, `items: list[TaskResponse]`, `total: int`), and `TaskSuggestionResponse` (`title`, `description`, `priority: TaskPriority`, `source: str = "ai_suggestion"`)

**Checkpoint**: Schemas importable — service phase can begin.

---

## Phase 4: Task Service (Foundational — Blocking)

**Purpose**: Tenant ownership resolution, in-tenant reference validation (message + assignee), the status state machine, the `task_created` message side effect, and the no-side-effects guarantee. **BLOCKS the API in Phase 5.**

- [ ] T009 Define typed errors in `backend/app/services/task_service.py` (or the shared errors module): `InvalidAssignee` (→422 `INVALID_ASSIGNEE`), `InvalidStateTransition` (→422 `INVALID_STATE_TRANSITION`); reuse `NotFoundError`/`ForbiddenError` (Spec 001) for 404/403 (data-model.md error→HTTP mapping)
- [ ] T010 Implement `_resolve_message_or_raise(session, tenant_id, message_id)` and `get_task(session, tenant_id, task_id)` in `backend/app/services/task_service.py`: load the row, `NotFoundError` (404) if absent, `ForbiddenError` (403) if in another tenant — mirroring Specs 005–010 SR-05 (depends on T006)
- [ ] T011 Implement `_assert_in_tenant_user(session, tenant_id, user_id)` in `backend/app/services/task_service.py`: raise `InvalidAssignee` (422) if the user does not exist or is not in the caller's tenant (SR-03, SR-07) (depends on T009)
- [ ] T012 Implement `_assert_not_terminal(task)` and `_apply_transition(task, new_status)` in `backend/app/services/task_service.py`: terminal = `status ∈ {completed, cancelled}` → `InvalidStateTransition`; `_apply_transition` enforces allowed moves (`open → in_progress|completed|cancelled`, `in_progress → completed|cancelled`) and sets `completed_at` when moving to `completed` (data-model.md state machine; FR-008) (depends on T009)
- [ ] T013 Implement `_mark_message_task_created(session, message)` in `backend/app/services/task_service.py`: set the related message's status to `task_created` (non-destructive); **isolated** so a failure here never fails task creation (FR-014, research.md Decision 5) (depends on T006)
- [ ] T014 [US1] Implement `create_task(session, tenant_id, user, data: TaskCreateRequest) -> Task` in `backend/app/services/task_service.py`: resolve message (404/403); if `assigned_to` set, `_assert_in_tenant_user` (422 `INVALID_ASSIGNEE`); build `Task` with `tenant_id`, `related_message_id`, `conversation_id` from the message (if any), title/description/due_date/priority, `created_by=user.id`, `status=open`; flush; `_mark_message_task_created`; commit (transactional — no partial task on failure). **Sends no client message, creates no escalation** (FR-001..FR-004, FR-010, FR-011, FR-015, AC-01, AC-13, AC-16) (depends on T010, T011, T013)
- [ ] T015 [US2] Implement `list_tasks(session, tenant_id, *, status=None, priority=None, assigned_to=None, related_message_id=None) -> (items, total)` in `backend/app/services/task_service.py`: `WHERE tenant_id` (SR-02) + optional filters; order by `created_at DESC` (FR-005, AC-04, AC-05) (depends on T006)
- [ ] T016 [US2] Implement `update_task(session, tenant_id, task_id, data: TaskUpdateRequest) -> Task` in `backend/app/services/task_service.py`: `get_task` (404/403); `_assert_not_terminal`; if `assigned_to` set, `_assert_in_tenant_user`; apply non-null `title`(stripped)/`description`/`due_date`/`priority`/`assigned_to`; if `status` set, `_apply_transition` (guards + `completed_at`); commit; `updated_at` refreshes (FR-006, AC-07, AC-08, AC-11) (depends on T010, T011, T012)
- [ ] T017 [US3] Implement `complete_task(session, tenant_id, task_id) -> Task` in `backend/app/services/task_service.py`: `get_task` (404/403); `_assert_not_terminal`; set status `completed`, `completed_at=now`; commit (FR-007, AC-09, AC-11) (depends on T010, T012)
- [ ] T018 [US3] Implement cancellation via `update_task` `status=cancelled` (the contract cancels through PATCH); confirm `_apply_transition` sets `cancelled` from non-terminal and leaves `completed_at` null (FR-007, AC-10, AC-11) (depends on T016)
- [ ] T019 [US2] Implement `tasks_for_message(session, tenant_id, message_id) -> (items, total)` in `backend/app/services/task_service.py`: resolve message (404/403); return tasks `WHERE tenant_id AND related_message_id ORDER BY created_at DESC` (FR-013, AC-12) (depends on T010)

**Checkpoint**: Service complete; tenant scoping, in-tenant reference validation, state machine, and the isolated `task_created` side effect all enforced; no send/escalation anywhere.

---

## Phase 5: API Endpoints (User Stories 1–3)

**Purpose**: Expose the six task endpoints with `require_role("staff", "manager")` and error→HTTP mapping. `tenant_id` and `created_by` are always derived from the JWT; any client-supplied tenant is ignored. **🎯 MVP backend deliverable. No send/escalation endpoint exists.**

- [ ] T020 [US1] Implement `POST /api/tasks` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; validate `TaskCreateRequest`; call `service.create_task`; return `TaskResponse` **201**. Map `NotFoundError`→404 `MESSAGE_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN`, `InvalidAssignee`→422 `INVALID_ASSIGNEE`, invalid title/priority→422 (contracts §1, AC-01, AC-02, AC-18) (depends on T014)
- [ ] T021 [US2] Implement `GET /api/tasks` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; parse `status`/`priority`/`assigned_to`/`related_message_id` query params; call `service.list_tasks`; return `TaskListResponse` (200); invalid filter value → 422 (contracts §2, AC-04, AC-05) (depends on T015)
- [ ] T022 [US2] Implement `GET /api/tasks/{task_id}` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; call `service.get_task`; return `TaskResponse` (200); missing → 404 `TASK_NOT_FOUND`, cross-tenant → 403 `CROSS_TENANT_FORBIDDEN` (contracts §3, AC-06) (depends on T010)
- [ ] T023 [US2] Implement `PATCH /api/tasks/{task_id}` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; validate `TaskUpdateRequest`; call `service.update_task`; return updated `TaskResponse` (200); terminal/illegal transition → 422 `INVALID_STATE_TRANSITION`, cross-tenant assignee → 422 `INVALID_ASSIGNEE` (contracts §4, AC-07, AC-08, AC-10, AC-11) (depends on T016)
- [ ] T024 [US3] Implement `POST /api/tasks/{task_id}/complete` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; optional ignored `{note}` body; call `service.complete_task`; return `TaskResponse` (200) with `completed_at`; terminal → 422 `INVALID_STATE_TRANSITION` (contracts §5, AC-09, AC-11) (depends on T017)
- [ ] T025 [US2] Implement `GET /api/messages/{message_id}/tasks` in `backend/app/api/v1/tasks.py`: `require_role("staff", "manager")`; call `service.tasks_for_message`; return `MessageTasksResponse` (`message_id`, `items`, `total`) (200); cross-tenant → 404/403 (contracts §6, AC-12) (depends on T019)
- [ ] T026 Mount the tasks router at `/api` in `backend/app/main.py` so all routes resolve (plan.md Backend Tasks #7) (depends on T020–T025)

**Checkpoint**: All six endpoints return per the contract; role matrix + tenant resolution + state machine enforced. Backend MVP complete.

---

## Phase 6: Optional AI Task Suggestion (User Story 4 — P2, read-only)

**Purpose**: A strictly **read-only** suggestion endpoint that proposes task details and **creates nothing**. Gated by `TASK_SUGGESTION_ENABLED`. Suggestion failure must not block manual creation.

- [ ] T027 [US4] Implement the `TaskSuggester` interface in `backend/app/ai/task_suggester.py`: `suggest(message, intent, risk, reply) -> {title, description, priority}`; a heuristic/LLM impl plus a **deterministic stub** for tests; map risk level → suggested priority (high→`high`, medium→`medium`, low→`low`/`medium`); raise typed `SuggestionUnavailable` on failure (research.md Decisions 1 & 8, plan.md Optional AI tasks)
- [ ] T028 [US4] Implement `suggest_for_message(session, tenant_id, message_id) -> TaskSuggestionResponse` in `backend/app/services/task_service.py`: resolve message (404/403); read intent (006)/risk (007)/suggested reply (010) for the message when available (tenant-scoped, optional); call the suggester; **creates no task, sends nothing, escalates nothing** (FR-009, SR-08, AC-14) (depends on T010, T027)
- [ ] T029 [US4] Implement `POST /api/messages/{message_id}/task-suggestion` in `backend/app/api/v1/tasks.py`: gated by `TASK_SUGGESTION_ENABLED`; `require_role("staff", "manager")`; call `service.suggest_for_message`; return `TaskSuggestionResponse` (200); `SuggestionUnavailable` → 503 `SUGGESTION_UNAVAILABLE`; cross-tenant → 404/403 (contracts §7, AC-14) (depends on T028, T026)

**Checkpoint**: Suggestion endpoint returns a proposal and creates nothing; disabling the flag removes it cleanly; failure falls back to manual creation.

---

## Phase 7: Frontend Integration (User Stories 1–3 + optional suggest)

**Purpose**: Add a Tasks page and replace the Spec 005 "Create Task" placeholder with a real task-creation control + the message's tasks list.

- [ ] T030 [P] Add TS types to `frontend/src/types/task.ts`: `TaskStatus`, `TaskPriority`, `Task`, `TaskSuggestion` (data-model.md Frontend Types)
- [ ] T031 [P] Add the typed API client `frontend/src/api/tasks.ts`: `createTask(payload)`, `listTasks(filters)`, `getTask(id)`, `updateTask(id, payload)`, `completeTask(id)`, `tasksForMessage(messageId)`, `suggestTask(messageId)` — calling the endpoints with the auth header (depends on T030)
- [ ] T032 [P] Implement status/priority badge components in `frontend/src/components/tasks/` (e.g. `TaskStatusBadge.tsx`, `TaskPriorityBadge.tsx`): colored badges for each `TaskStatus`/`TaskPriority` value (AC-17) (depends on T030)
- [ ] T033 Implement `frontend/src/components/tasks/TaskRow.tsx` + `TaskList.tsx`: a row/table showing title, status badge, priority badge, assignee, due date (overdue highlight when `due_date < now` and not terminal), related message link; empty state (plan.md Frontend #4, AC-17) (depends on T031, T032)
- [ ] T034 Implement `frontend/src/components/tasks/TaskForm.tsx`: create/edit form — title, description, assignee select (in-tenant users), due date, priority; optional "Suggest with AI" button that calls `suggestTask` and prefills fields (user edits + confirms; never auto-creates); inline 422 validation errors (plan.md Frontend #5, FR-009, AC-14) (depends on T031)
- [ ] T035 Implement `frontend/src/components/tasks/TaskDetail.tsx`: view + actions — edit fields, progress to `in_progress`, complete, cancel, reassign (manager); buttons disabled in terminal states; calls the correct API methods (plan.md Frontend #6, AC-07, AC-09, AC-10, AC-11) (depends on T031, T032)
- [ ] T036 Implement `frontend/src/pages/TasksPage.tsx` at route `/tasks`: lists tenant tasks via `TaskList` with status/priority/assignee filters; loading/empty/error states; register the route in `frontend/src/App.tsx` and add a Tasks nav item (plan.md Frontend #3, AC-17) (depends on T033)
- [ ] T037 Replace the Spec 005 "Create Task" placeholder in `frontend/src/pages/ConversationDetailPage`: a "Create Task" control opening `TaskForm` prefilled from the message (optionally via "Suggest with AI"); show the message's existing tasks (via `tasksForMessage`); leave the "Escalate" placeholder untouched (plan.md Frontend #7, FR-013, AC-17) (depends on T034, T033)

**Checkpoint**: Tasks page lists tenant tasks with badges/filters; the message detail page can create tasks and show a message's tasks; terminal tasks are read-only in the UI.

---

## Phase 8: Frontend Tests

**Purpose**: Render/interaction tests for the list, form, badges, and complete action.

- [ ] T038 [P] `TaskList`/`TasksPage` render tests in `frontend/src/components/tasks/__tests__/TaskList.test.tsx`: renders tenant tasks with status + priority badges, assignee, due date; empty + loading + error states render (AC-17)
- [ ] T039 [P] `TaskForm` test: the create form renders from message detail; successful creation updates the UI (calls `createTask` and reflects the new task); "Suggest with AI" prefills fields without creating a task; inline validation error renders on empty title (AC-14, AC-17) (depends on T034)
- [ ] T040 [P] `TaskDetail` + badge test: status/priority badges render the correct label/color; the Complete action calls `completeTask` and reflects `completed`; actions disabled for terminal tasks (AC-09, AC-17) (depends on T035, T032)

**Checkpoint**: Frontend states + interactions verified.

---

## Phase 9: Tenant Isolation & Role Security Tests (cross-cutting)

**Purpose**: Prove Tenant A never accesses Tenant B tasks/messages/assignees, `tenant_id`/`created_by` come only from the JWT, and the role matrix holds. `backend/tests/integration/test_tasks.py`.

- [ ] T041 [P] Staff creates an own-tenant task from a message → 201, task `tenant_id` = caller's tenant, `created_by` = caller, linked to the message (AC-01); manager creates an own-tenant task → 201 (role matrix)
- [ ] T042 [P] Tenant isolation on list: tasks created in A and B → listing as A returns only A's tasks (B absent) (AC-03, AC-04)
- [ ] T043 [P] Tenant A cannot read/update/complete a Tenant B task: `GET`/`PATCH`/`POST .../complete` on a B task as A → 403 `CROSS_TENANT_FORBIDDEN` (or 404), no change (AC-06, SR-02)
- [ ] T044 [P] Tenant A cannot create a task for a Tenant B message: `related_message_id` of a B message → 404/403; nothing stored (AC-18, SR-03)
- [ ] T045 [P] Cross-tenant assignee rejected: creating/updating with an `assigned_to` user from another tenant → 422 `INVALID_ASSIGNEE`; nothing stored/changed (AC-08, SR-03, SR-07)
- [ ] T046 [P] Client-supplied `tenant_id`/`created_by` ignored: values injected into the body do not change ownership — task scopes to the JWT tenant and `created_by` is the JWT user (SR-01, SR-07)
- [ ] T047 [P] Platform Admin → 403 `INSUFFICIENT_ROLE` on **all** task endpoints (create, list, get, patch, complete, message-tasks, suggestion) (AC-15, SR-04); unauthenticated → 401 on each
- [ ] T048 [P] Both `staff` and `manager` can use the task endpoints within their tenant; manager can reassign to an in-tenant user (AC-08, role matrix)

**Checkpoint**: Tenant isolation and the role matrix are proven; no cross-tenant task/message/assignee access; no client-spoofable ownership.

---

## Phase 10: Task Behaviour & Integration Tests

**Purpose**: Verify CRUD, validation, the state machine, completion, no-side-effects, the message side effect, and the optional suggestion. `backend/tests/integration/test_tasks.py` + `backend/tests/unit/`.

- [ ] T049 [P] Unit `backend/tests/unit/test_task_service.py`: state machine valid transitions (`open→in_progress→completed`, `open→cancelled`, `in_progress→cancelled`) and invalid ones (edit/complete/cancel a terminal task → `InvalidStateTransition`); `_assert_in_tenant_user` rejects out-of-tenant; `completed_at` set only on completion (FR-008, AC-11)
- [ ] T050 [P] Unit `backend/tests/unit/test_task_suggester.py`: priority-from-risk mapping (high→high etc.); deterministic stub output; `SuggestionUnavailable` propagates (research.md Decision 8) (depends on T027)
- [ ] T051 [P] Create stores all fields linked to the message with status `open`, `created_by`, timestamps; `conversation_id` copied from the message when present (AC-01, FR-002)
- [ ] T052 [P] Validation rejections on create: missing/whitespace title, over-length title, invalid priority, out-of-tenant assignee, non-existent message → 422/404/403; nothing stored (AC-02, AC-18)
- [ ] T053 [P] List filters by `status`, `priority`, `assigned_to`, `related_message_id` return the correct in-tenant subsets (AC-05)
- [ ] T054 [P] Update allowed fields persists and refreshes `updated_at`; manager reassign to an in-tenant user updates `assigned_to` (AC-07, AC-08)
- [ ] T055 [P] Status progression `open → in_progress → completed` works; completing sets `completed_at` (AC-09); cancelling sets status `cancelled` (AC-10); completed/cancelled tasks remain listed and filterable by status (US3)
- [ ] T056 [P] Invalid transitions rejected: edit/complete/cancel a `completed` or `cancelled` task → 422 `INVALID_STATE_TRANSITION`; completing an already-completed task → 422 (AC-11)
- [ ] T057 [P] `GET /api/messages/{id}/tasks` returns the message's tenant-scoped tasks; cross-tenant message → 404/403 (AC-12)
- [ ] T058 [P] No side effects: creating/updating/completing a task sends **no client message** and creates **no escalation** — assert no such records/effects exist (AC-13, FR-010, FR-011, SR-06)
- [ ] T059 [P] On creation, the related message's status becomes `task_created`; creating a second task from the same message still succeeds (multiple tasks per message allowed) (AC-16, FR-014)
- [ ] T060 [P] Optional suggestion: `POST /api/messages/{id}/task-suggestion` returns a proposed title/description/priority and **creates no task**; a follow-up `POST /api/tasks` with the (edited) values then creates the task; suggestion-service unavailable → 503 `SUGGESTION_UNAVAILABLE` while manual creation still works (AC-14, FR-009) (depends on T029)

**Checkpoint**: All 18 acceptance criteria covered by tests; CRUD, state machine, no-side-effects, message side effect, and the read-only suggestion verified.

---

## Phase 11: Quickstart & Manual Validation

**Purpose**: Execute the five-scenario quickstart end to end (quickstart.md).

- [ ] T061 Run migrations (`alembic upgrade head`); confirm `tasks` created and `messages.status` accepts `task_created`; log in as staff of both demo tenants
- [ ] T062 Scenario 1 — guest-count change message → create task "Check catering capacity for updated guest count" (high), `status:open`, linked to the message; confirm `GET /messages/{id}/tasks` shows it; optionally fetch an AI suggestion first and confirm it creates nothing
- [ ] T063 Scenario 2 — payment issue message ("I paid the deposit but no one confirmed.") → create task "Verify deposit payment confirmation" (high), `status:open`
- [ ] T064 Scenario 3 — callback request message ("Can someone call me today?") → create task "Call client today" (medium)
- [ ] T065 Scenario 4 — tenant isolation: create a Royal Events task; as Elegant Weddings, list tasks (RE task absent) and `GET` the RE task by id → 403 `CROSS_TENANT_FORBIDDEN`; creating an EW task assigned to an RE user → 422 `INVALID_ASSIGNEE`
- [ ] T066 Scenario 5 — completion: PATCH a task to `in_progress`, then `POST .../complete` → `completed` + `completed_at`; completing again → 422 `INVALID_STATE_TRANSITION`; completed task still appears under `?status=completed`; cancel another task via PATCH `status=cancelled`
- [ ] T067 Role + no-side-effect checks: Platform Admin `GET /api/tasks` → `INSUFFICIENT_ROLE`; blank title → 422; non-existent related message → 404; confirm creating a task sends no client message and creates no escalation; verify the UI Tasks page + message-detail "Create Task" control

**Checkpoint**: Quickstart passes end to end; creation, tracking, completion, and tenant isolation demonstrated live.

---

## Phase 12: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T068 Verify AC-01..AC-18 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T069 Walk `checklists/requirements.md` Functional / Task Workflow / Optional AI Suggestion / Security / Tenant Isolation / API / Data / Testing sections and tick each implemented item
- [ ] T070 Confirm Out-of-Scope items remain **unbuilt**: no escalation workflow, no sending of any client message, no auto-creation of tasks (human confirmation required; suggestion is read-only), no audit-log persistence/API/UI (future integration only), no calendar syncing/reminders/notifications, no recurring tasks/subtasks/dependencies, no task comments/attachments, no cross-tenant/shared tasks, no full CRM, no real WhatsApp API (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 011 verified against spec + checklist; trackable follow-up tasks delivered with the two hard guarantees (no auto-create, no side effects) proven.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/model)** → depends on Phase 1 (incl. the T003 message-status decision); **BLOCKS everything**.
- **Phase 3 (Schemas)** → depends on T005; blocks service + API.
- **Phase 4 (Service)** → depends on Phases 2–3; blocks the API.
- **Phase 5 (API)** → depends on Phase 4; **MVP backend deliverable**.
- **Phase 6 (Optional suggestion)** → depends on Phase 5 (and Spec 006/007/010 readers); strictly read-only; can be deferred without blocking the MVP.
- **Phase 7 (Frontend)** → depends on Phase 5 (consumes the endpoints); the "Suggest with AI" control also needs Phase 6.
- **Phase 8 (Frontend tests)** → depends on Phase 7.
- **Phase 9 (Isolation/role tests)** + **Phase 10 (Behaviour tests)** → depend on Phase 5 (Phase 10's suggestion test needs Phase 6).
- **Phase 11 (Quickstart)** → depends on Phases 5–7.
- **Phase 12 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3 — create, manage, complete/cancel)

1. Phase 1: Setup (config + message-status decision)
2. Phase 2: DB + model + migration (**CRITICAL**)
3. Phase 3: Schemas
4. Phase 4: Service (tenant resolution → in-tenant reference validation → state machine → isolated `task_created` side effect)
5. Phase 5: API (six endpoints + router mount + error/state mapping)
6. **STOP and VALIDATE**: run isolation + behaviour tests; confirm tenant scoping, in-tenant assignee/message validation, state machine, no send/escalation, `task_created`, client-tenant override ignored
7. Phase 9 + 10: full isolation + behaviour coverage (AC-01..AC-18, minus the optional suggestion AC-14 until Phase 6)

### Incremental Delivery

1. Setup + DB + schemas + service → foundation ready
2. US1 (create from message) → messages become trackable tasks (**creation MVP**)
3. US2 (list/get/update/reassign + message-tasks) → the operational backbone
4. US3 (complete/cancel + state machine) → the task lifecycle closes
5. US4 (optional read-only AI suggestion) → faster, consistent task capture (additive, P2)
6. Frontend → Tasks page + badges + form + detail + message-detail "Create Task" integration
7. Tests + quickstart + acceptance → all 18 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` and `created_by` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01, SR-07); any `tenant_id`/`created_by` in the body/query is ignored (T046)
- **No auto-create** — the AI suggestion endpoint is strictly read-only (creates nothing); task creation is a separate explicit `POST /api/tasks` (FR-009, SR-08, research.md Decision 1). This is the first hard guarantee
- **No side effects** — no endpoint or service method sends a client message or creates an escalation; the only side effect is flipping the related message's status to `task_created`, which is non-destructive and isolated so it never fails task creation (FR-010, FR-011, SR-06, T013, T058). This is the second hard guarantee
- In-tenant reference validation is mandatory: `related_message_id` and `assigned_to` must resolve within the JWT tenant before any write (SR-03, T044, T045)
- 404 (task/message not in tenant) vs 403 (exists in another tenant) mirrors Specs 005–010 SR-05 via the `_resolve_message_or_raise`/`get_task` helpers
- `TaskStatus`/`TaskPriority` persist as constrained VARCHARs (app-boundary validation), not native PG enums, for evolvability (consistent with Specs 008–010)
- State machine: `open → in_progress → completed | cancelled` (and `open → completed|cancelled`); `completed`/`cancelled` are terminal and field-immutable; invalid transitions → 422 `INVALID_STATE_TRANSITION` (T012, T056). `completed_at` is set iff status is `completed`
- Cancellation goes through `PATCH {"status":"cancelled"}` (no dedicated `/cancel` endpoint in the contract) (T018, T023)
- Multiple tasks may be created from one message; each is independent (T059)
- Due dates are stored as timestamps; **overdue is UI-derived** (`due_date < now` and not terminal) — no calendar sync, no reminders/notifications (research.md Decision 11)
- The optional AI suggestion (Phase 6) maps Spec 007 risk → suggested priority, uses Spec 006/007/010 outputs when available, is gated by `TASK_SUGGESTION_ENABLED`, and falls back to manual creation on failure (503) — it is additive and does not block the MVP
- **Audit logging is out of scope for 011** — it is a **future integration** (the later audit-log feature, 013). This feature records actor (`created_by`), action (status), and timestamps for that feature to consume later; it builds no audit persistence, API, or UI here
- Calendar syncing, reminders/notifications, recurring tasks/subtasks, task comments/attachments, full CRM, and real WhatsApp API are all **out of scope** (spec Out of Scope)
