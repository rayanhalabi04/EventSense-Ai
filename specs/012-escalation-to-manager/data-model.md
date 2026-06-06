# Data Model: Escalation to Manager

**Branch**: `012-escalation-to-manager` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `escalations`. One Alembic migration. The related message's status may be set to `escalated` (reusing the Spec 003/005 `messages.status` field — add the value to its allowed set; see below). No other column changes to existing tables.

---

## Enums

### `EscalationStatus`

```python
class EscalationStatus(str, Enum):
    open      = "open"        # created by staff; awaiting manager
    in_review = "in_review"   # manager actively reviewing
    resolved  = "resolved"    # manager finished (sets resolved_at)
    cancelled = "cancelled"   # withdrawn / not needed
```

### `EscalationPriority`

```python
class EscalationPriority(str, Enum):
    medium = "medium"
    high   = "high"
    urgent = "urgent"
```

**State machine**:

```
            create (staff)
(none) ──────────────────────▶ open ──── manager picks up ───▶ in_review
                                 │                                  │
              resolve / cancel   │   resolve / cancel               │
               (manager)         ▼        (manager)                 ▼
                            resolved (resolved_at)            resolved / cancelled
                            cancelled
   (resolved / cancelled are TERMINAL — edits & transitions rejected: 422)
```

Allowed transitions (manager-only mutations):
- `open → in_review | resolved | cancelled`
- `in_review → resolved | cancelled` (and `in_review → open` for re-queue may be allowed; default forward-only)
- `resolved` / `cancelled` → **none** (terminal; edit/resolve/cancel → 422 `INVALID_STATE_TRANSITION`)
- `resolved` sets `resolved_at`. No auto-resolve.

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | `escalations.tenant_id` scope |
| `users` (002) | `created_by` (staff), `assigned_manager_id` (role `manager`, in-tenant); role gating |
| `messages` (003) | `message_id`; status may become `escalated` |
| `classification_results` (006) | snapshot `intent_label` |
| `risk_assessments` (007) | snapshot `risk_level` + `risk_reason`; `escalation_recommended` drives UI |
| `rag_retrieval_results` (009) | snapshot `source_document_ids`/`source_chunk_ids` |
| `suggested_replies` (010) | `suggested_reply_id` (live link; independent lifecycle) |

---

## New Entity: `Escalation`

### Table `escalations`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes all access |
| `message_id` | UUID | NOT NULL, FK → `messages.id`, `ON DELETE CASCADE`, indexed | escalated message |
| `created_by` | UUID | NOT NULL, FK → `users.id` | staff creator |
| `assigned_manager_id` | UUID | NULL, FK → `users.id` | in-tenant manager (optional) |
| `intent_label` | VARCHAR(40) | NULL | snapshot of Spec 006 intent |
| `risk_level` | VARCHAR(10) | NULL | snapshot of Spec 007 level |
| `risk_reason` | TEXT | NULL | snapshot of Spec 007 reason |
| `ai_summary` | TEXT | NULL | optional AI case summary |
| `suggested_reply_id` | UUID | NULL, FK → `suggested_replies.id` | live link (independent lifecycle) |
| `source_document_ids` | JSONB (UUID list) | NOT NULL, default `[]` | snapshot of RAG source docs |
| `source_chunk_ids` | JSONB (UUID list) | NOT NULL, default `[]` | snapshot of RAG source chunks |
| `status` | VARCHAR(20) | NOT NULL, default `open` | one of `EscalationStatus` |
| `priority` | VARCHAR(10) | NOT NULL, default `medium` | one of `EscalationPriority` |
| `manager_notes` | TEXT | NULL | manager review notes |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |
| `resolved_at` | TIMESTAMPTZ | NULL | set when status → `resolved` |

### Indexes

- `INDEX (tenant_id, status)` — queue by status.
- `INDEX (tenant_id, priority)` — urgent/high triage.
- `INDEX (tenant_id, assigned_manager_id)` — "my escalations".
- `INDEX (tenant_id, message_id)` — a message's escalations.

### SQLAlchemy model (`backend/app/models/escalation.py`)

```python
class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_manager_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    intent_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_reply_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("suggested_replies.id"), nullable=True
    )
    source_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    manager_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message: Mapped["Message"] = relationship()
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_manager_id])
    suggested_reply: Mapped["SuggestedReply | None"] = relationship()

    __table_args__ = (
        Index("ix_esc_tenant_status", "tenant_id", "status"),
        Index("ix_esc_tenant_priority", "tenant_id", "priority"),
        Index("ix_esc_tenant_assignee", "tenant_id", "assigned_manager_id"),
        Index("ix_esc_tenant_message", "tenant_id", "message_id"),
    )
```

### Message status note

The related message's status may be set to `escalated`. If `messages.status` is a constrained enum, add `escalated` via the migration; if free string, no migration needed. The transition is non-destructive and isolated from escalation creation success. (Consistent with Spec 011's `task_created`.)

---

## Pydantic Schemas (`backend/app/schemas/escalation.py`)

```python
class EscalationCreateRequest(BaseModel):
    message_id: UUID
    priority: EscalationPriority | None = None      # defaulted from risk if omitted
    reason: str | None = None                        # optional staff note (stored into manager_notes? no -> separate; kept as creation context)
    assigned_manager_id: UUID | None = None          # optional in-tenant manager

class EscalationUpdateRequest(BaseModel):
    status: EscalationStatus | None = None           # manager-only transitions
    priority: EscalationPriority | None = None
    assigned_manager_id: UUID | None = None
    manager_notes: str | None = Field(default=None, max_length=4000)

class ResolveRequest(BaseModel):
    manager_notes: str | None = Field(default=None, max_length=4000)

class EscalationListItem(BaseModel):
    id: UUID
    message_id: UUID
    status: EscalationStatus
    priority: EscalationPriority
    intent_label: str | None
    risk_level: str | None
    assigned_manager_id: UUID | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    model_config = ConfigDict(from_attributes=True)

class EscalationResponse(EscalationListItem):
    risk_reason: str | None
    ai_summary: str | None
    suggested_reply_id: UUID | None
    source_document_ids: list[UUID]
    source_chunk_ids: list[UUID]
    manager_notes: str | None

class EscalationListResponse(BaseModel):
    items: list[EscalationListItem]
    total: int
```

---

## Service Logic (`backend/app/services/escalation_service.py`)

```python
async def create_escalation(session, tenant_id, user, data: EscalationCreateRequest) -> Escalation:
    msg = await _resolve_message_or_raise(session, tenant_id, data.message_id)        # 404/403
    classification = await _get_classification(session, tenant_id, msg.id)            # snapshot source (006)
    risk = await _get_risk(session, tenant_id, msg.id)                                # snapshot source (007)
    reply = await _get_latest_reply(session, tenant_id, msg.id)                       # optional (010)
    rag = await _get_latest_rag(session, tenant_id, msg.id)                           # optional (009)

    if data.assigned_manager_id is not None:
        await _assert_in_tenant_manager(session, tenant_id, data.assigned_manager_id) # 422 INVALID_ASSIGNEE

    priority = (data.priority or _priority_from_risk(risk)).value
    summary = None
    try:
        summary = summarizer.summarize(msg, classification, risk, rag, reply)         # optional, non-fatal
    except SummaryUnavailable:
        summary = None

    esc = Escalation(
        tenant_id=tenant_id, message_id=msg.id, created_by=user.id,
        assigned_manager_id=data.assigned_manager_id,
        intent_label=(classification.label if classification else None),
        risk_level=(risk.level if risk else None),
        risk_reason=(risk.reason if risk else None),
        ai_summary=summary,
        suggested_reply_id=(reply.id if reply else None),
        source_document_ids=([s.document_id for s in rag.sources] if rag else []),
        source_chunk_ids=([s.chunk_id for s in rag.sources] if rag else []),
        status=EscalationStatus.open.value, priority=priority,
        manager_notes=None,
    )
    session.add(esc); await session.flush()
    await _mark_message_escalated(session, msg)        # isolated; failure does not fail creation
    await session.commit()
    return esc


async def list_escalations(session, tenant_id, *, status=None, priority=None, assigned_manager_id=None):
    stmt = select(Escalation).where(Escalation.tenant_id == tenant_id)                # SR-02
    if status:              stmt = stmt.where(Escalation.status == status.value)
    if priority:            stmt = stmt.where(Escalation.priority == priority.value)
    if assigned_manager_id: stmt = stmt.where(Escalation.assigned_manager_id == assigned_manager_id)
    stmt = stmt.order_by(_priority_rank_desc(), Escalation.created_at.asc())          # urgent/open first
    return (await session.execute(stmt)).scalars().all()


async def get_escalation(session, tenant_id, escalation_id) -> Escalation:
    esc = await session.get(Escalation, escalation_id)
    if esc is None: raise NotFoundError()              # 404 ESCALATION_NOT_FOUND
    if esc.tenant_id != tenant_id: raise ForbiddenError()  # 403 CROSS_TENANT_FORBIDDEN
    return esc


async def update_escalation(session, tenant_id, user, escalation_id, data) -> Escalation:
    _require_manager(user)                             # 403 if staff (manager-only mutations)
    esc = await get_escalation(session, tenant_id, escalation_id)   # 404/403
    _assert_not_terminal(esc)                          # 422 INVALID_STATE_TRANSITION
    if data.assigned_manager_id is not None:
        await _assert_in_tenant_manager(session, tenant_id, data.assigned_manager_id)
        esc.assigned_manager_id = data.assigned_manager_id
    if data.priority is not None:      esc.priority = data.priority.value
    if data.manager_notes is not None: esc.manager_notes = data.manager_notes
    if data.status is not None:        _apply_transition(esc, data.status)  # sets resolved_at on resolved
    await session.commit(); return esc


async def resolve_escalation(session, tenant_id, user, escalation_id, notes=None) -> Escalation:
    _require_manager(user)
    esc = await get_escalation(session, tenant_id, escalation_id)
    _assert_not_terminal(esc)
    if notes is not None: esc.manager_notes = notes
    esc.status = EscalationStatus.resolved.value
    esc.resolved_at = func.now()
    await session.commit(); return esc


async def escalations_for_message(session, tenant_id, message_id) -> list[Escalation]:
    await _resolve_message_or_raise(session, tenant_id, message_id)   # 404/403
    stmt = (select(Escalation)
            .where(Escalation.tenant_id == tenant_id, Escalation.message_id == message_id)
            .order_by(Escalation.created_at.desc()))
    return (await session.execute(stmt)).scalars().all()
```

`_require_manager` → 403 `INSUFFICIENT_ROLE` for staff. `_assert_not_terminal` → 422 for `resolved`/`cancelled`. `_apply_transition` enforces allowed moves + sets `resolved_at`. `_assert_in_tenant_manager` → 422 `INVALID_ASSIGNEE` if not an in-tenant manager. `_resolve_message_or_raise` mirrors Specs 005–011 (404 / 403).

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (escalation/message) | 404 | `ESCALATION_NOT_FOUND` / `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `InvalidAssignee` (not in-tenant manager) | 422 | `INVALID_ASSIGNEE` |
| `InvalidStateTransition` | 422 | `INVALID_STATE_TRANSITION` |
| invalid priority/status | 422 | validation detail |
| staff attempts manager-only action | 403 | `INSUFFICIENT_ROLE` |
| `SummaryUnavailable` | (non-fatal) | escalation created without summary |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/escalation.ts`)

```typescript
type EscalationStatus = "open" | "in_review" | "resolved" | "cancelled";
type EscalationPriority = "medium" | "high" | "urgent";

interface Escalation {
  id: string;
  tenant_id: string;
  message_id: string;
  created_by: string;
  assigned_manager_id: string | null;
  intent_label: string | null;
  risk_level: string | null;
  risk_reason: string | null;
  ai_summary: string | null;
  suggested_reply_id: string | null;
  source_document_ids: string[];
  source_chunk_ids: string[];
  status: EscalationStatus;
  priority: EscalationPriority;
  manager_notes: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
```

---

## Invariants

- **Tenant scope**: every read/write filters by `tenant_id`; `message_id`, `suggested_reply_id`, `assigned_manager_id` resolve in-tenant (assignee must be a `manager`).
- **Creation**: status `open`, `created_by` = authenticated staff/manager; only via explicit `POST` (no auto-create).
- **Snapshot**: `intent_label`/`risk_level`/`risk_reason`/`ai_summary`/source ids captured at creation; not mutated by later upstream changes.
- **Role split**: only `manager` may resolve/cancel/assign/add notes; `staff` create + view.
- **Terminal immutability**: `resolved`/`cancelled` reject further edits/transitions (422); `resolved_at` set only on resolve (no auto-resolve).
- **No side effects**: creation/updates send no client message, do not approve/send the suggested reply, and create no task; only the message's status may flip to `escalated` (isolated).
