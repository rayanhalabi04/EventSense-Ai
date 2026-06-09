# Data Model: Audit Logs

**Branch**: `013-audit-logs` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `audit_logs`. One Alembic migration. The table is **append-only** — it has no `updated_at`, and the application exposes no update/delete path. References to other entities are **loose** (no cascade deletes onto audit rows) so deleting a business row never erases history. No column changes to existing tables.

---

## Enums

### `AuditActorType`

```python
class AuditActorType(str, Enum):
    user       = "user"          # a human (staff/manager); actor_user_id set
    system     = "system"        # system/workflow action; no human actor
    ai_service = "ai_service"    # an AI/ML component (classifier, risk, RAG, reply gen)
```

### `AuditSeverity`

```python
class AuditSeverity(str, Enum):
    info     = "info"        # normal expected activity
    warning  = "warning"     # notable, non-failing (gap / soft refusal)
    error    = "error"       # handled failure
    security = "security"    # security-relevant (cross-tenant block, guardrail)
```

### `AuditEntityType`

```python
class AuditEntityType(str, Enum):
    message               = "message"
    conversation          = "conversation"
    classification_result = "classification_result"
    risk_assessment       = "risk_assessment"
    document              = "document"
    rag_retrieval         = "rag_retrieval"
    suggested_reply       = "suggested_reply"
    task                  = "task"
    escalation            = "escalation"
    user                  = "user"
    session               = "session"
```

### `AuditEventType`

```python
class AuditEventType(str, Enum):
    message_received           = "message_received"
    message_created_by_simulator = "message_created_by_simulator"
    intent_classified          = "intent_classified"
    risk_detected              = "risk_detected"
    document_uploaded          = "document_uploaded"
    document_processed         = "document_processed"
    rag_retrieved              = "rag_retrieved"
    rag_no_source_found        = "rag_no_source_found"
    suggested_reply_generated  = "suggested_reply_generated"
    suggested_reply_edited     = "suggested_reply_edited"
    suggested_reply_approved   = "suggested_reply_approved"
    suggested_reply_rejected   = "suggested_reply_rejected"
    task_created               = "task_created"
    task_updated               = "task_updated"
    task_completed             = "task_completed"
    escalation_created         = "escalation_created"
    escalation_updated         = "escalation_updated"
    escalation_resolved        = "escalation_resolved"
    guardrail_refusal          = "guardrail_refusal"
    cross_tenant_access_blocked = "cross_tenant_access_blocked"
    unsupported_answer_refused = "unsupported_answer_refused"
    user_login                 = "user_login"
    user_logout                = "user_logout"   # optional
```

The enum is **closed-but-extensible**: validated at write time, but later features may add values without an enum-altering migration (string-backed). There is no state machine — entries are independent, append-only facts.

### Event → (actor, severity, entity) defaults

| Event type | Default actor | Default severity | Entity type | Key metadata (ids + facts) |
|------------|---------------|------------------|-------------|----------------------------|
| `message_received` | system | info | message | `message_id`, `conversation_id` |
| `message_created_by_simulator` | user / system | info | message | `message_id`, `conversation_id` |
| `intent_classified` | ai_service | info | classification_result | `classification_id`, `predicted_label`, `confidence` |
| `risk_detected` | ai_service | info / warning | risk_assessment | `risk_level`, short `risk_reason` |
| `document_uploaded` | user | info | document | `document_id`, `filename` (name only) |
| `document_processed` | system | info | document | `document_id`, `chunk_count` |
| `rag_retrieved` | ai_service | info | rag_retrieval | `source_document_ids`, `top_score` |
| `rag_no_source_found` | ai_service | warning | rag_retrieval | `message_id` (no answer text) |
| `suggested_reply_generated` | ai_service | info | suggested_reply | `suggested_reply_id` |
| `suggested_reply_edited` | user | info | suggested_reply | `suggested_reply_id` |
| `suggested_reply_approved` | user | info | suggested_reply | `suggested_reply_id` |
| `suggested_reply_rejected` | user | info | suggested_reply | `suggested_reply_id` |
| `task_created` | user | info | task | `task_id` |
| `task_updated` | user | info | task | `task_id`, `status_from`, `status_to` |
| `task_completed` | user | info | task | `task_id` |
| `escalation_created` | user | info | escalation | `escalation_id`, `priority` |
| `escalation_updated` | user | info | escalation | `escalation_id`, `status_from`, `status_to` |
| `escalation_resolved` | user | info | escalation | `escalation_id` |
| `guardrail_refusal` | ai_service | security | suggested_reply / rag_retrieval | `reason_code` (no refused text) |
| `cross_tenant_access_blocked` | user | security | (varies) | `attempted_route`, `attempted_entity_type` (no target data) |
| `unsupported_answer_refused` | ai_service | warning | rag_retrieval / suggested_reply | `message_id` (no answer text) |
| `user_login` | user | info | session / user | (no token) |
| `user_logout` | user | info | session / user | (optional) |

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | `audit_logs.tenant_id` scope |
| `users` (002) | `actor_user_id` (human actor); role gates read access |
| `messages` / conversations (003) | `message_id` / `conversation_id` references |
| `classification_results` (006) | `classification_id` + label/confidence in metadata |
| `risk_assessments` (007) | risk level/reason summary in metadata |
| `documents` (008) | `document_id` in metadata |
| `rag_retrievals` (009) | RAG event references (no answer text) |
| `suggested_replies` (010) | `suggested_reply_id` in metadata/entity |
| `tasks` (011) | `task_id` in metadata/entity |
| `escalations` (012) | `escalation_id` in metadata/entity |

All references are **loose** (ids carried in metadata or in `entity_id`/`message_id`); the audit row does not own or cascade-delete these.

---

## New Entity: `AuditLog`

### Table `audit_logs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes all access |
| `actor_user_id` | UUID | NULL, FK → `users.id` | set iff `actor_type = user` |
| `actor_type` | VARCHAR(16) | NOT NULL | one of `AuditActorType` |
| `event_type` | VARCHAR(48) | NOT NULL | one of `AuditEventType` (extensible) |
| `severity` | VARCHAR(12) | NOT NULL, default `info` | one of `AuditSeverity` |
| `entity_type` | VARCHAR(32) | NULL | one of `AuditEntityType` |
| `entity_id` | UUID | NULL | id of the related entity (plain UUID, no FK cascade) |
| `message_id` | UUID | NULL, FK → `messages.id` `ON DELETE SET NULL`, indexed | message reference |
| `conversation_id` | UUID | NULL | conversation reference |
| `metadata` | JSONB | NOT NULL, default `{}` | ids + minimal redacted facts |
| `redacted_summary` | TEXT | NULL | short human sentence (no sensitive payload) |
| `request_id` | VARCHAR(64) | NULL | optional correlation id (soft de-dup) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | server-assigned; ordering key |

**No `updated_at`** — entries are immutable (append-only).

### Indexes

- `INDEX (tenant_id, created_at DESC)` — primary newest-first list.
- `INDEX (tenant_id, event_type)` — filter by event.
- `INDEX (tenant_id, severity)` — filter by severity (e.g., `security`).
- `INDEX (tenant_id, actor_user_id)` — filter by actor.
- `INDEX (tenant_id, message_id)` — message-scoped reads.
- `INDEX (tenant_id, entity_type, entity_id)` — entity-scoped reads (e.g., escalation).

### Append-only enforcement

- The ORM model and service expose **no** update/delete; there is no PATCH/DELETE endpoint.
- **Recommended**: in the migration (or ops runbook) revoke `UPDATE, DELETE` on `audit_logs` from the application DB role, or add a `BEFORE UPDATE OR DELETE` trigger that raises. Documented as the immutability backstop (SR-03).

### SQLAlchemy model (`backend/app/models/audit_log.py`)

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="info")
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    redacted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])

    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_tenant_event", "tenant_id", "event_type"),
        Index("ix_audit_tenant_severity", "tenant_id", "severity"),
        Index("ix_audit_tenant_actor", "tenant_id", "actor_user_id"),
        Index("ix_audit_tenant_message", "tenant_id", "message_id"),
        Index("ix_audit_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )
```

> Note: the Python attribute is `metadata_` because `metadata` is reserved on the SQLAlchemy declarative base; the column name remains `metadata`.

---

## Pydantic Schemas (`backend/app/schemas/audit.py`)

```python
class AuditEventInput(BaseModel):
    """Internal DTO passed by features 002–012 to AuditService.log_event."""
    tenant_id: UUID
    actor_user_id: UUID | None = None
    actor_type: AuditActorType
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.info
    entity_type: AuditEntityType | None = None
    entity_id: UUID | None = None
    message_id: UUID | None = None
    conversation_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)     # redacted/size-bounded by the service
    redacted_summary: str | None = Field(default=None, max_length=500)
    request_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _actor_rule(self):
        if self.actor_type == AuditActorType.user and self.actor_user_id is None:
            raise ValueError("actor_user_id required for actor_type=user")
        if self.actor_type != AuditActorType.user and self.actor_user_id is not None:
            raise ValueError("actor_user_id must be null for system/ai_service")
        return self


class AuditLogFilters(BaseModel):
    event_type: AuditEventType | None = None
    actor_type: AuditActorType | None = None
    actor_user_id: UUID | None = None
    severity: AuditSeverity | None = None
    entity_type: AuditEntityType | None = None
    entity_id: UUID | None = None
    message_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


class AuditLogListItem(BaseModel):
    id: UUID
    created_at: datetime
    event_type: AuditEventType
    actor_type: AuditActorType
    actor_user_id: UUID | None
    severity: AuditSeverity
    entity_type: AuditEntityType | None
    entity_id: UUID | None
    message_id: UUID | None
    redacted_summary: str | None
    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(AuditLogListItem):
    conversation_id: UUID | None
    metadata: dict
    request_id: str | None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogListItem]
    total: int
    limit: int
    offset: int
```

---

## Service Logic (`backend/app/services/audit_service.py`)

```python
async def log_event(session, *, tenant_id, actor_user_id, actor_type, event_type,
                    severity=AuditSeverity.info, entity_type=None, entity_id=None,
                    message_id=None, conversation_id=None, metadata=None,
                    summary=None, request_id=None) -> None:
    """The one write path. BEST-EFFORT: never raises into the caller (FR-014, SR-08)."""
    try:
        clean_meta, clean_summary, truncated = redact(metadata or {}, summary)   # PR/SR redaction
        if truncated:
            clean_meta["metadata_truncated"] = True
        evt = AuditEventInput(                                                    # enum + actor-rule validation
            tenant_id=tenant_id, actor_user_id=actor_user_id, actor_type=actor_type,
            event_type=event_type, severity=severity, entity_type=entity_type,
            entity_id=entity_id, message_id=message_id, conversation_id=conversation_id,
            metadata=clean_meta, redacted_summary=clean_summary, request_id=request_id,
        )
        row = AuditLog(**evt.model_dump(by_alias=False))
        async with _independent_session() as s:        # isolated; failure can't roll back caller
            s.add(row); await s.commit()
    except Exception as exc:                            # noqa: BLE001 — best-effort
        logger.warning("audit_log_failed", event_type=str(event_type), error=str(exc))
        audit_failures_counter.inc()
        return                                          # swallow; primary action unaffected


async def list_audit_logs(session, tenant_id, filters: AuditLogFilters, *, limit, offset):
    limit = min(limit, settings.AUDIT_LIST_MAX_LIMIT)
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)                # SR-02
    if filters.event_type:    stmt = stmt.where(AuditLog.event_type == filters.event_type.value)
    if filters.actor_type:    stmt = stmt.where(AuditLog.actor_type == filters.actor_type.value)
    if filters.actor_user_id: stmt = stmt.where(AuditLog.actor_user_id == filters.actor_user_id)
    if filters.severity:      stmt = stmt.where(AuditLog.severity == filters.severity.value)
    if filters.entity_type:   stmt = stmt.where(AuditLog.entity_type == filters.entity_type.value)
    if filters.entity_id:     stmt = stmt.where(AuditLog.entity_id == filters.entity_id)
    if filters.message_id:    stmt = stmt.where(AuditLog.message_id == filters.message_id)
    if filters.created_from:  stmt = stmt.where(AuditLog.created_at >= filters.created_from)
    if filters.created_to:    stmt = stmt.where(AuditLog.created_at <= filters.created_to)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())          # deterministic
    total = await _count(session, stmt)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return rows, total


async def get_audit_log(session, tenant_id, audit_log_id) -> AuditLog:
    row = await session.get(AuditLog, audit_log_id)
    if row is None: raise NotFoundError()                 # 404 AUDIT_LOG_NOT_FOUND
    if row.tenant_id != tenant_id: raise ForbiddenError() # 403 CROSS_TENANT_FORBIDDEN
    return row


async def audit_logs_for_message(session, tenant_id, message_id, *, staff_view=False):
    await _resolve_message_or_raise(session, tenant_id, message_id)               # 404/403
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id,
                                  AuditLog.message_id == message_id)
    if staff_view:
        stmt = stmt.where(AuditLog.severity != AuditSeverity.security.value)      # SR-04
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return (await session.execute(stmt)).scalars().all()


async def audit_logs_for_entity(session, tenant_id, entity_type, entity_id):
    stmt = (select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id,
                   AuditLog.entity_type == entity_type.value,
                   AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()))
    return (await session.execute(stmt)).scalars().all()


def log_cross_tenant_blocked(session, *, attempting_tenant_id, attempting_user_id,
                             attempted_route, attempted_entity_type):
    """Writes in the ATTEMPTING tenant only; never any target-tenant field (SR-07, FR-013)."""
    return log_event(session, tenant_id=attempting_tenant_id,
                     actor_user_id=attempting_user_id, actor_type=AuditActorType.user,
                     event_type=AuditEventType.cross_tenant_access_blocked,
                     severity=AuditSeverity.security, entity_type=None, entity_id=None,
                     metadata={"attempted_route": attempted_route,
                               "attempted_entity_type": attempted_entity_type},
                     summary="Cross-tenant access blocked.")
```

`redact(...)` lives in `audit_redaction.py`. `_independent_session` opens a session not joined to the caller's transaction so an audit failure cannot roll back business work and vice-versa (Decision 2). `_resolve_message_or_raise` mirrors Specs 005–012 (404 / 403).

### Redaction (`backend/app/services/audit_redaction.py`)

```python
FORBIDDEN_KEY_PATTERNS = ("token", "secret", "password", "api_key",
                          "authorization", "jwt", "prompt")

def redact(metadata: dict, summary: str | None) -> tuple[dict, str | None, bool]:
    clean = {k: v for k, v in metadata.items()
             if not any(p in k.lower() for p in FORBIDDEN_KEY_PATTERNS)}
    blob = json.dumps(clean, default=str)
    truncated = False
    if len(blob.encode()) > settings.AUDIT_METADATA_MAX_BYTES:
        clean = _truncate_to_cap(clean, settings.AUDIT_METADATA_MAX_BYTES)
        truncated = True
    clean_summary = (summary or "")[:500] or None       # short, no body quoting (caller convention)
    return clean, clean_summary, truncated
```

### Error → HTTP mapping (read endpoints)

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (audit/message) | 404 | `AUDIT_LOG_NOT_FOUND` / `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| staff requests tenant-wide list | 403 | `INSUFFICIENT_ROLE` |
| staff message-view disabled | 403 | `STAFF_AUDIT_DISABLED` |
| invalid filter / pagination / enum | 422 | validation detail |
| update/delete attempt (no route) | 405 | `METHOD_NOT_ALLOWED` |
| (role guard) Platform Admin | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

> `log_event` (write) never maps to an HTTP error — it is best-effort and returns `None` even on failure.

---

## Frontend Types (`frontend/src/types/audit.ts`)

```typescript
type AuditActorType = "user" | "system" | "ai_service";
type AuditSeverity = "info" | "warning" | "error" | "security";
type AuditEntityType =
  | "message" | "conversation" | "classification_result" | "risk_assessment"
  | "document" | "rag_retrieval" | "suggested_reply" | "task" | "escalation"
  | "user" | "session";
type AuditEventType =
  | "message_received" | "message_created_by_simulator" | "intent_classified"
  | "risk_detected" | "document_uploaded" | "document_processed"
  | "rag_retrieved" | "rag_no_source_found"
  | "suggested_reply_generated" | "suggested_reply_edited"
  | "suggested_reply_approved" | "suggested_reply_rejected"
  | "task_created" | "task_updated" | "task_completed"
  | "escalation_created" | "escalation_updated" | "escalation_resolved"
  | "guardrail_refusal" | "cross_tenant_access_blocked"
  | "unsupported_answer_refused" | "user_login" | "user_logout";

interface AuditLog {
  id: string;
  tenant_id: string;
  actor_user_id: string | null;
  actor_type: AuditActorType;
  event_type: AuditEventType;
  severity: AuditSeverity;
  entity_type: AuditEntityType | null;
  entity_id: string | null;
  message_id: string | null;
  conversation_id: string | null;
  metadata: Record<string, unknown>;
  redacted_summary: string | null;
  request_id: string | null;
  created_at: string;
}
```

---

## Invariants

- **Tenant scope**: every read/write filters by `tenant_id`; `cross_tenant_access_blocked` is written in the attempting tenant only, with no target-tenant field.
- **Append-only**: entries are never updated or deleted; no `updated_at`, no mutate path; DB-level UPDATE/DELETE revocation recommended.
- **Actor rule**: `actor_type=user` ⇒ `actor_user_id` set; `system`/`ai_service` ⇒ `actor_user_id` null.
- **Redaction**: `metadata`/`redacted_summary` never contain secrets, prompts, JWTs, API keys, passwords, full bodies, or cross-tenant data; metadata is size-bounded (`metadata_truncated` when capped).
- **Best-effort**: `log_event` never raises into the caller; a failed append is logged to app logs/metrics and the primary action proceeds.
- **Role split**: managers read tenant-wide; staff read message-scoped (security excluded) when enabled; Platform Admin/unauthenticated blocked.
- **Ordering**: `created_at` desc, `id` desc tiebreak; `created_at` server-assigned; reads paginated + bounded.
