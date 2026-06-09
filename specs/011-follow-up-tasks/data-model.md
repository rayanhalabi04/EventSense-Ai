# Data Model: Follow-Up Tasks

**Branch**: `011-follow-up-tasks` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `tasks`. One Alembic migration. The related message's status may be set to `task_created` (reusing the Spec 003/005 `messages.status` field — add the value to that enum/allowed set; see below). No other column changes to existing tables.

---

## Enums

### `TaskStatus`

```python
class TaskStatus(str, Enum):
    open        = "open"          # created, not started
    in_progress = "in_progress"  # being worked on
    completed   = "completed"    # done (sets completed_at)
    cancelled   = "cancelled"    # no longer needed
```

### `TaskPriority`

```python
class TaskPriority(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"
```

**State machine**:

```
            create
(none) ───────────────▶ open ──── start ───▶ in_progress
                          │                       │
              complete /  │  complete / cancel    │ complete / cancel
               cancel     ▼                       ▼
                     completed (completed_at)   completed / cancelled
                     cancelled
   (completed / cancelled are TERMINAL — edits & transitions rejected: 422)
```

Allowed transitions:
- `open → in_progress | completed | cancelled`
- `in_progress → completed | cancelled` (and `in_progress → open` may be allowed for re-queue; default keep simple: forward only)
- `completed` / `cancelled` → **none** (terminal; edit/complete/cancel → 422 `INVALID_STATE_TRANSITION`)
- `completed` sets `completed_at`; clearing it is not allowed.

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | `tasks.tenant_id` scope |
| `users` (002) | `created_by`, `assigned_to` (both must be in-tenant); role gating |
| `messages` (003) | `related_message_id`; status may become `task_created`; provides `conversation_id` |
| `conversations` (001/003) | optional `conversation_id` metadata |

---

## New Entity: `Task`

### Table `tasks`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes all access |
| `related_message_id` | UUID | NOT NULL, FK → `messages.id`, `ON DELETE CASCADE`, indexed | source message |
| `conversation_id` | UUID | NULL, FK → `conversations.id` | optional metadata |
| `title` | VARCHAR(200) | NOT NULL | human-written/confirmed |
| `description` | TEXT | NULL | optional details |
| `assigned_to` | UUID | NULL, FK → `users.id` | in-tenant user (optional) |
| `created_by` | UUID | NOT NULL, FK → `users.id` | authenticated creator |
| `due_date` | TIMESTAMPTZ | NULL | optional; overdue derived in UI |
| `priority` | VARCHAR(10) | NOT NULL, default `medium` | one of `TaskPriority` |
| `status` | VARCHAR(20) | NOT NULL, default `open` | one of `TaskStatus` |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |
| `completed_at` | TIMESTAMPTZ | NULL | set when status → `completed` |

### Indexes

- `INDEX (tenant_id, status)` — status triage (open/in_progress queues).
- `INDEX (tenant_id, priority)` — high-priority view.
- `INDEX (tenant_id, assigned_to)` — "my tasks".
- `INDEX (tenant_id, related_message_id)` — a message's tasks.

### SQLAlchemy model (`backend/app/models/task.py`)

```python
class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    related_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message: Mapped["Message"] = relationship()
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_to])
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_tasks_tenant_priority", "tenant_id", "priority"),
        Index("ix_tasks_tenant_assignee", "tenant_id", "assigned_to"),
        Index("ix_tasks_tenant_message", "tenant_id", "related_message_id"),
    )
```

### Message status note

The related message's status may be set to `task_created`. If `messages.status` is a constrained enum (Spec 003/005), add `task_created` to its allowed values via the migration; if it is a free string, no migration is needed. Document the chosen approach in the migration. The transition is non-destructive and isolated from task creation success.

---

## Pydantic Schemas (`backend/app/schemas/task.py`)

```python
class TaskCreateRequest(BaseModel):
    related_message_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    assigned_to: UUID | None = None
    due_date: datetime | None = None
    priority: TaskPriority = TaskPriority.medium

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be blank")
        return v.strip()


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    assigned_to: UUID | None = None
    due_date: datetime | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None        # transitions guarded server-side


class TaskResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    related_message_id: UUID
    conversation_id: UUID | None
    title: str
    description: str | None
    assigned_to: UUID | None
    created_by: UUID
    due_date: datetime | None
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class TaskSuggestionResponse(BaseModel):
    title: str
    description: str
    priority: TaskPriority
    source: str = "ai_suggestion"   # advisory; creates nothing
```

---

## Service Logic (`backend/app/services/task_service.py`)

```python
async def create_task(session, tenant_id, user, data: TaskCreateRequest) -> Task:
    msg = await _resolve_message_or_raise(session, tenant_id, data.related_message_id)  # 404/403
    if data.assigned_to is not None:
        await _assert_in_tenant_user(session, tenant_id, data.assigned_to)              # 422 INVALID_ASSIGNEE
    task = Task(
        tenant_id=tenant_id,
        related_message_id=msg.id,
        conversation_id=getattr(msg, "conversation_id", None),
        title=data.title, description=data.description,
        assigned_to=data.assigned_to, created_by=user.id,
        due_date=data.due_date, priority=data.priority.value,
        status=TaskStatus.open.value,
    )
    session.add(task)
    await session.flush()
    await _mark_message_task_created(session, msg)   # isolated; failure does not fail creation
    await session.commit()
    return task


async def list_tasks(session, tenant_id, *, status=None, priority=None, assigned_to=None, related_message_id=None):
    stmt = select(Task).where(Task.tenant_id == tenant_id)            # SR-02
    if status:             stmt = stmt.where(Task.status == status.value)
    if priority:           stmt = stmt.where(Task.priority == priority.value)
    if assigned_to:        stmt = stmt.where(Task.assigned_to == assigned_to)
    if related_message_id: stmt = stmt.where(Task.related_message_id == related_message_id)
    stmt = stmt.order_by(Task.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def get_task(session, tenant_id, task_id) -> Task:
    task = await session.get(Task, task_id)
    if task is None: raise NotFoundError()           # 404 TASK_NOT_FOUND
    if task.tenant_id != tenant_id: raise ForbiddenError()   # 403 CROSS_TENANT_FORBIDDEN
    return task


async def update_task(session, tenant_id, task_id, data: TaskUpdateRequest) -> Task:
    task = await get_task(session, tenant_id, task_id)               # 404/403
    _assert_not_terminal(task)                                       # 422 INVALID_STATE_TRANSITION
    if data.assigned_to is not None:
        await _assert_in_tenant_user(session, tenant_id, data.assigned_to)
    for f in ("title", "description", "due_date"):
        v = getattr(data, f)
        if v is not None: setattr(task, f, v.strip() if f == "title" else v)
    if data.priority is not None: task.priority = data.priority.value
    if data.assigned_to is not None: task.assigned_to = data.assigned_to
    if data.status is not None:
        _apply_transition(task, data.status)        # guards + sets completed_at on completed
    await session.commit()
    return task


async def complete_task(session, tenant_id, task_id) -> Task:
    task = await get_task(session, tenant_id, task_id)
    _assert_not_terminal(task)
    task.status = TaskStatus.completed.value
    task.completed_at = func.now()
    await session.commit(); return task


async def tasks_for_message(session, tenant_id, message_id) -> list[Task]:
    await _resolve_message_or_raise(session, tenant_id, message_id)  # 404/403
    stmt = (select(Task)
            .where(Task.tenant_id == tenant_id, Task.related_message_id == message_id)
            .order_by(Task.created_at.desc()))
    return (await session.execute(stmt)).scalars().all()
```

`_assert_not_terminal` → 422 when status ∈ {`completed`, `cancelled`}. `_apply_transition` enforces allowed moves and sets `completed_at` on `completed`. `_assert_in_tenant_user` → 422 `INVALID_ASSIGNEE` if the user is not in the tenant. `_resolve_message_or_raise` mirrors Specs 005–010 (404 / 403).

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (task/message) | 404 | `TASK_NOT_FOUND` / `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `InvalidAssignee` | 422 | `INVALID_ASSIGNEE` |
| `InvalidStateTransition` | 422 | `INVALID_STATE_TRANSITION` |
| invalid title/priority/status | 422 | validation detail |
| `SuggestionUnavailable` (optional endpoint) | 503 | `SUGGESTION_UNAVAILABLE` |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/task.ts`)

```typescript
type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";
type TaskPriority = "low" | "medium" | "high";

interface Task {
  id: string;
  tenant_id: string;
  related_message_id: string;
  conversation_id: string | null;
  title: string;
  description: string | null;
  assigned_to: string | null;
  created_by: string;
  due_date: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

interface TaskSuggestion {
  title: string;
  description: string;
  priority: TaskPriority;
  source: "ai_suggestion";
}
```

---

## Invariants

- **Tenant scope**: every read/write filters by `tenant_id`; `related_message_id` + `assigned_to` resolve in-tenant.
- **Creation**: status `open`, `created_by` = authenticated user; only via explicit `POST` (no auto-create).
- **Terminal immutability**: `completed`/`cancelled` reject further edits/transitions (422).
- **`completed_at`** set iff status is `completed`.
- **No side effects**: creation/updates send no client message and create no escalation; only the related message's status may flip to `task_created` (isolated).
