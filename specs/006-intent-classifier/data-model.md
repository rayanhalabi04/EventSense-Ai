# Data Model: Intent Classifier

**Branch**: `006-intent-classifier` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `classification_results` (one row per message, one-to-one). Plus one new Alembic migration. No changes to `messages` or `conversations` columns — the link is via a FK + unique constraint on `message_id`.

---

## Enums

### `IntentLabel`

```python
class IntentLabel(str, Enum):
    booking_inquiry      = "booking_inquiry"
    pricing_request      = "pricing_request"
    availability_question = "availability_question"
    service_question     = "service_question"
    urgent_change        = "urgent_change"
    guest_count_change   = "guest_count_change"
    complaint            = "complaint"
    cancellation_request = "cancellation_request"
    payment_issue        = "payment_issue"
    human_escalation     = "human_escalation"
    other                = "other"
```

### `ClassificationStatus`

```python
class ClassificationStatus(str, Enum):
    classified   = "classified"    # confident model prediction
    needs_review = "needs_review"  # low confidence (label forced to other) or unclassifiable input
    reviewed     = "reviewed"      # a human confirmed/corrected the label
    failed       = "failed"        # classifier errored; label/confidence may be null
```

**State transitions**:

```
(new inbound message)
        │  classify_message()
        ▼
   confidence >= threshold ? ── yes ──▶ classified ──┐
        │ no                                          │ human review
        ▼                                             ▼
   needs_review ──────────── human review ───────▶ reviewed
        ▲                                             ▲
        │ classifier error                            │ (auto re-run is BLOCKED on reviewed)
      failed ◀── (model raised) ──(retry POST /classify)
```

- Auto path (`classify_message`) may write `classified` / `needs_review` / `failed`, but **never** overwrites a row already in `reviewed` (FR-013).
- `review_classification` is the only transition into `reviewed`.

---

## Existing Entities Used

### `messages` (Spec 001 + Spec 003)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | FK target; classification lookup |
| `tenant_id` | UUID | Tenant scoping (denormalised onto classification) |
| `body` | TEXT | The text classified |
| `direction` | ENUM (`inbound`/`outbound`) | Only `inbound` is classified |
| `status` | ENUM (`unread`/`read`) | Unaffected by this feature |

---

## New Entity: `ClassificationResult`

### Table `classification_results`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `message_id` | UUID | FK → `messages.id`, **UNIQUE**, `ON DELETE CASCADE` | one-to-one with message |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | denormalised from message for tenant-scoped queries |
| `label` | VARCHAR(40) | NOT NULL | one of `IntentLabel` |
| `confidence` | DOUBLE PRECISION | NULL allowed | top-class probability `[0,1]`; NULL when `failed` |
| `model_version` | VARCHAR(64) | NOT NULL | e.g. `tfidf-logreg-v1` |
| `status` | VARCHAR(20) | NOT NULL | one of `ClassificationStatus` |
| `reviewed_by` | UUID | NULL, FK → `users.id` | set on human review |
| `reviewed_at` | TIMESTAMPTZ | NULL | set on human review |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |

### Indexes

- `UNIQUE (message_id)` — enforces one-to-one and powers the per-message read.
- `INDEX (tenant_id, status)` — "all needs-review in my tenant" queries.
- `INDEX (tenant_id, label)` — future per-label analytics (read-only here).

### SQLAlchemy model (`backend/app/models/classification.py`)

```python
class ClassificationResult(Base):
    __tablename__ = "classification_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    message: Mapped["Message"] = relationship(back_populates="classification")

    __table_args__ = (
        Index("ix_classification_tenant_status", "tenant_id", "status"),
        Index("ix_classification_tenant_label", "tenant_id", "label"),
    )
```

`Message` gains: `classification: Mapped["ClassificationResult | None"] = relationship(back_populates="message", uselist=False, cascade="all, delete-orphan")`.

---

## Pydantic Schemas (`backend/app/schemas/classification.py`)

```python
class ClassificationResultResponse(BaseModel):
    message_id: UUID
    label: IntentLabel
    confidence: float | None
    model_version: str
    status: ClassificationStatus
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClassifyResponse(ClassificationResultResponse):
    """Returned by POST /classify — same shape as the read response."""


class ReviewRequest(BaseModel):
    label: IntentLabel                       # must be a valid label → 422 otherwise

    @field_validator("label")
    @classmethod
    def label_must_be_valid(cls, v: IntentLabel) -> IntentLabel:
        return v  # Enum coercion already rejects invalid values with 422


class ReviewResponse(ClassificationResultResponse):
    """Returned by PATCH review — reflects status=reviewed."""
```

### Compact block embedded in inbox + detail responses

```python
class ClassificationSummary(BaseModel):
    label: IntentLabel | None          # null when unclassified
    confidence: float | None
    status: ClassificationStatus | None
```

- Added to each Spec 004 inbox item (`classification: ClassificationSummary | None`).
- Added to each Spec 005 detail message (`classification: ClassificationSummary | None`).
- `None` / null label → frontend shows "unclassified / pending".

---

## Service Logic (`backend/app/services/classification_service.py`)

```python
async def classify_message(session, message) -> ClassificationResult | None:
    """Fail-safe: never raises into the message-creation caller."""
    if message.direction != MessageDirection.inbound:
        return None
    existing = await _get_for_message(session, message.id)
    if existing and existing.status == ClassificationStatus.reviewed:
        return existing                      # FR-013: never clobber a human label

    try:
        label, confidence = model.predict(message.body)         # may short-circuit empty→other
        if confidence < settings.INTENT_CONFIDENCE_THRESHOLD:
            label, status = IntentLabel.other, ClassificationStatus.needs_review
        else:
            status = ClassificationStatus.classified
    except ModelUnavailable:
        return None                          # message stays "unclassified"
    except Exception:
        label, confidence, status = IntentLabel.other, None, ClassificationStatus.failed

    return await _upsert(session, message, label, confidence,
                         settings.INTENT_MODEL_VERSION, status)


async def get_classification(session, tenant_id, message_id) -> ClassificationResult:
    await _resolve_message_or_raise(session, tenant_id, message_id)   # 404 / 403
    result = await _get_for_message(session, message_id)
    if result is None:
        raise NoClassificationError()        # -> 404 NO_CLASSIFICATION
    return result


async def review_classification(session, tenant_id, user, message_id, new_label) -> ClassificationResult:
    await _resolve_message_or_raise(session, tenant_id, message_id)   # 404 / 403
    result = await _get_for_message(session, message_id)
    if result is None:
        raise NoClassificationError()        # -> 404
    result.label = new_label                 # Enum-validated upstream (422 if invalid)
    result.status = ClassificationStatus.reviewed
    result.reviewed_by = user.id
    result.reviewed_at = func.now()
    await session.commit()
    return result
```

`_resolve_message_or_raise` mirrors Spec 005: fetch message by id → `None` → 404; `tenant_id` mismatch → 403.

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (message) | 404 | `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `NoClassificationError` | 404 | `NO_CLASSIFICATION` |
| `ModelUnavailable` (on POST) | 503 | `MODEL_UNAVAILABLE` |
| invalid label | 422 | validation detail |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/classification.ts`)

```typescript
type IntentLabel =
  | "booking_inquiry" | "pricing_request" | "availability_question"
  | "service_question" | "urgent_change" | "guest_count_change"
  | "complaint" | "cancellation_request" | "payment_issue"
  | "human_escalation" | "other";

type ClassificationStatus = "classified" | "needs_review" | "reviewed" | "failed";

interface ClassificationResult {
  message_id: string;
  label: IntentLabel;
  confidence: number | null;
  model_version: string;
  status: ClassificationStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ClassificationSummary {
  label: IntentLabel | null;
  confidence: number | null;
  status: ClassificationStatus | null;
}
```

---

## ML Artifact Shape (`INTENT_MODEL_PATH`)

```
backend/models/intent/
├── vectorizer.joblib     # fitted TfidfVectorizer
├── model.joblib          # fitted LogisticRegression
├── labels.json           # ordered list of the 11 IntentLabel strings
└── meta.json             # { "model_version": "tfidf-logreg-v1", "trained_at": "..." }
```

`ClassifierModel.predict(text)`:
1. `text = (text or "").strip().lower()[:INTENT_MAX_CHARS]`
2. if empty → return `(IntentLabel.other, 0.0)` (service routes to needs_review)
3. `X = vectorizer.transform([text])`
4. `probs = model.predict_proba(X)[0]`
5. `idx = argmax(probs)` → `label = labels[idx]`, `confidence = float(probs[idx])`
6. return `(label, confidence)` — deterministic.
