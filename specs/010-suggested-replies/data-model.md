# Data Model: Suggested Replies

**Branch**: `010-suggested-replies` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `suggested_replies` (many per message over time; one active draft shown). One Alembic migration. No column changes to existing tables — it references `messages`, `tenants`, `users`, and (for provenance) `rag_queries` (Spec 009) via FKs and stores source id lists.

---

## Enums

### `SuggestedReplyStatus`

```python
class SuggestedReplyStatus(str, Enum):
    draft_generated = "draft_generated"   # AI produced a draft; awaiting review
    edited          = "edited"            # staff modified the text (not yet approved/sent)
    approved        = "approved"          # human-accepted (NOT sent)
    rejected        = "rejected"          # will not be used
```

**State machine**:

```
                 edit
draft_generated ───────▶ edited
      │                    │
      │ approve            │ approve
      ▼                    ▼
   approved ◀──────────────┘        (terminal — content immutable)
      ▲
      │ (NO transition out; cannot un-approve)

draft_generated / edited ── reject ──▶ rejected   (terminal — content immutable)
```

Allowed transitions:
- `draft_generated → edited` (edit), `→ approved` (approve), `→ rejected` (reject)
- `edited → edited` (re-edit), `→ approved` (approve), `→ rejected` (reject)
- `approved` / `rejected` → **none** (terminal; edit/approve/reject all 422 `INVALID_STATE_TRANSITION`)
- Regeneration does not transition a row — it creates a **new** `draft_generated` row.

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | `tenant_id` scope via the message |
| `users` (002) | `approved_by`; `staff`/`manager` gating |
| `messages` (003) | the message being replied to; tenant resolution |
| `classification_results` (006) | intent input to generation (precondition) |
| `risk_assessments` (007) | risk level/flag → tone + escalation note (precondition) |
| `rag_queries` / `rag_retrieval_results` (009) | grounding sources + status; `rag_query_id` provenance; source ids |

---

## New Entity: `SuggestedReply`

### Table `suggested_replies`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | denormalised from message |
| `message_id` | UUID | NOT NULL, FK → `messages.id`, `ON DELETE CASCADE`, indexed | the replied-to message |
| `generated_text` | TEXT | NOT NULL | immutable original AI draft |
| `edited_text` | TEXT | NULL | staff edit; effective text if present |
| `status` | VARCHAR(20) | NOT NULL, default `draft_generated` | one of `SuggestedReplyStatus` |
| `source_document_ids` | JSONB (UUID list) | NOT NULL, default `[]` | RAG source documents used (empty = ungrounded/refusal) |
| `source_chunk_ids` | JSONB (UUID list) | NOT NULL, default `[]` | RAG source chunks used |
| `grounded` | BOOLEAN | NOT NULL, default false | true iff source ids non-empty |
| `model_name` | VARCHAR(80) | NOT NULL | generation model identifier |
| `prompt_version` | VARCHAR(40) | NOT NULL | prompt set version |
| `rag_query_id` | UUID | NULL, FK → `rag_queries.id` | provenance link to the retrieval used |
| `approved_by` | UUID | NULL, FK → `users.id` | reviewer on approval |
| `approved_at` | TIMESTAMPTZ | NULL | approval time |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |

### Indexes

- `INDEX (tenant_id, message_id)` — per-message listing within tenant.
- `INDEX (message_id, created_at DESC)` — newest draft first.
- `INDEX (tenant_id, status)` — review queues (e.g., all `draft_generated`).

### SQLAlchemy model (`backend/app/models/suggested_reply.py`)

```python
class SuggestedReply(Base):
    __tablename__ = "suggested_replies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft_generated")
    source_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    rag_query_id: Mapped[UUID | None] = mapped_column(ForeignKey("rag_queries.id"), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    message: Mapped["Message"] = relationship()

    __table_args__ = (
        Index("ix_reply_tenant_message", "tenant_id", "message_id"),
        Index("ix_reply_message_created", "message_id", "created_at"),
        Index("ix_reply_tenant_status", "tenant_id", "status"),
    )

    @property
    def effective_text(self) -> str:
        return self.edited_text if self.edited_text is not None else self.generated_text
```

---

## Pydantic Schemas (`backend/app/schemas/suggested_reply.py`)

```python
class ReplySource(BaseModel):
    document_id: UUID
    document_title: str
    document_type: str
    chunk_id: UUID
    snippet: str

class GenerateRequest(BaseModel):
    force: bool = False                  # create a new draft even if one exists

class SuggestedReplyResponse(BaseModel):
    id: UUID
    message_id: UUID
    generated_text: str
    edited_text: str | None
    effective_text: str
    status: SuggestedReplyStatus
    grounded: bool
    sources: list[ReplySource]           # assembled from source ids (tenant-scoped)
    model_name: str
    prompt_version: str
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SuggestedReplyListResponse(BaseModel):
    items: list[SuggestedReplyResponse]
    total: int

class EditRequest(BaseModel):
    edited_text: str = Field(min_length=1, max_length=4000)

    @field_validator("edited_text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Reply text must not be blank")
        return v
```

---

## Service Logic (`backend/app/services/suggested_reply_service.py`)

```python
async def generate(session, tenant_id, user, message_id, force=False) -> SuggestedReply:
    msg = await _resolve_message_or_raise(session, tenant_id, message_id)     # 404/403
    if not msg.body or not msg.body.strip():
        raise PreconditionError("empty message")                             # 422

    classification = await _get_classification(session, tenant_id, message_id)
    risk = await _get_risk(session, tenant_id, message_id)
    if classification is None or risk is None:
        raise PreconditionNotMet()                                           # 409 PRECONDITION_NOT_MET

    rag = await rag_service.query(session, tenant_id, msg.body, message_id=message_id)  # tenant-scoped (Spec 009)

    needs_policy = _is_policy_or_package(classification.label)
    if needs_policy and rag.status in (RetrievalStatus.no_source, RetrievalStatus.no_documents):
        text = reply_prompt.refusal(msg, risk)                               # GR-02: no invented facts
        sources, grounded = [], False
    else:
        try:
            text = generator.generate(reply_prompt.grounded(msg, classification, risk, rag.sources))
        except GenerationUnavailable:
            raise ModelUnavailableError()                                    # 503
        # GR-05: keep only sources that were actually retrieved
        sources = _validate_sources(rag.sources)
        grounded = bool(sources)

    reply = SuggestedReply(
        tenant_id=tenant_id, message_id=message_id,
        generated_text=text, status=SuggestedReplyStatus.draft_generated.value,
        source_document_ids=[s.document_id for s in sources],
        source_chunk_ids=[s.chunk_id for s in sources],
        grounded=grounded,
        model_name=generator.model_name, prompt_version=reply_prompt.PROMPT_VERSION,
        rag_query_id=rag.query_id,
    )
    session.add(reply); await session.commit()
    return reply


async def edit(session, tenant_id, reply_id, edited_text) -> SuggestedReply:
    reply = await get(session, tenant_id, reply_id)                          # 404/403
    _assert_not_terminal(reply)                                             # 422 INVALID_STATE_TRANSITION
    reply.edited_text = edited_text
    reply.status = SuggestedReplyStatus.edited.value
    await session.commit(); return reply


async def approve(session, tenant_id, user, reply_id) -> SuggestedReply:
    reply = await get(session, tenant_id, reply_id)
    _assert_not_terminal(reply)
    reply.status = SuggestedReplyStatus.approved.value
    reply.approved_by = user.id
    reply.approved_at = func.now()
    await session.commit(); return reply                                    # NO send (SR-06)


async def reject(session, tenant_id, reply_id) -> SuggestedReply:
    reply = await get(session, tenant_id, reply_id)
    _assert_not_terminal(reply)
    reply.status = SuggestedReplyStatus.rejected.value
    await session.commit(); return reply
```

`_assert_not_terminal` raises `InvalidStateTransition` (422) when status ∈ {`approved`, `rejected`}.
`_resolve_message_or_raise` / `get` mirror Specs 005–009: not found → 404; cross-tenant → 403.

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (message/reply) | 404 | `MESSAGE_NOT_FOUND` / `REPLY_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `PreconditionNotMet` (no intent/risk/RAG) | 409 | `PRECONDITION_NOT_MET` |
| `PreconditionError` (empty body) | 422 | validation detail |
| `InvalidStateTransition` | 422 | `INVALID_STATE_TRANSITION` |
| empty edit text | 422 | `EMPTY_REPLY_TEXT` |
| `ModelUnavailableError` | 503 | `MODEL_UNAVAILABLE` |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/suggestedReply.ts`)

```typescript
type SuggestedReplyStatus = "draft_generated" | "edited" | "approved" | "rejected";

interface ReplySource {
  document_id: string;
  document_title: string;
  document_type: string;
  chunk_id: string;
  snippet: string;
}

interface SuggestedReply {
  id: string;
  message_id: string;
  generated_text: string;
  edited_text: string | null;
  effective_text: string;
  status: SuggestedReplyStatus;
  grounded: boolean;
  sources: ReplySource[];
  model_name: string;
  prompt_version: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}
```

---

## Effective-Text & Grounding Rules (invariants)

- **Effective text** = `edited_text` if non-null, else `generated_text`.
- **`generated_text` is immutable** after creation; only `edited_text` changes.
- **`grounded` = `len(source_document_ids) > 0`**; refusal drafts have empty source lists and `grounded = false`.
- **Cited sources ⊆ retrieval result** (GR-05): the service never stores a source id absent from the RAG result.
- **Terminal immutability**: `approved`/`rejected` rows reject further edit/approve/reject (422).
- **No send**: there is no field, status, or endpoint representing "sent".
