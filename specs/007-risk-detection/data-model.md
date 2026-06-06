# Data Model: Risk Detection

**Branch**: `007-risk-detection` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `risk_assessments` (one row per message, one-to-one). One new Alembic migration. No column changes to `messages`, `conversations`, or `classification_results` — the link is a FK + unique constraint on `message_id`.

---

## Enums

### `RiskLevel`

```python
class RiskLevel(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"
```

### `RiskFlag`

```python
class RiskFlag(str, Enum):
    urgent_change                  = "urgent_change"
    complaint                      = "complaint"
    cancellation_risk              = "cancellation_risk"
    payment_risk                   = "payment_risk"
    guest_count_change             = "guest_count_change"
    human_escalation_needed        = "human_escalation_needed"
    unsupported_or_unclear_request = "unsupported_or_unclear_request"
```

### `RiskAssessmentStatus`

```python
class RiskAssessmentStatus(str, Enum):
    assessed = "assessed"   # produced by the rule engine
    reviewed = "reviewed"   # a human confirmed/corrected it
    failed   = "failed"     # engine errored; level/flag may be defaulted
```

**State transitions**:

```
(message classified)
        │  assess_message()
        ▼
   rule engine ──ok──▶ assessed ───── human review ─────▶ reviewed
        │                                                    ▲
        │ engine error                                       │ (auto re-assess BLOCKED on reviewed)
        ▼                                                     │
      failed ──(retry POST /risk-assessment)──▶ assessed ─────┘
```

- Auto path (`assess_message`) may write `assessed` / `failed`, but **never** overwrites a row already in `reviewed` (FR-013).
- `review_risk_assessment` is the only transition into `reviewed`.

---

## Existing Entities Used

### `messages` (Spec 001 + Spec 003)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | FK target; assessment lookup |
| `tenant_id` | UUID | Tenant scoping (denormalised onto assessment) |
| `body` | TEXT | Keyword/business-rule evaluation |
| `direction` | ENUM (`inbound`/`outbound`) | Only `inbound` is assessed |

### `classification_results` (Spec 006)

| Column | Type | Used for |
|--------|------|----------|
| `message_id` | UUID | Join to find the message's intent |
| `label` | VARCHAR (IntentLabel) | Baseline level/flag driver |
| `confidence` | DOUBLE | Low-confidence → unclear handling note in reason |
| `status` | VARCHAR | A `reviewed` classification is trusted input |

---

## New Entity: `RiskAssessment`

### Table `risk_assessments`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `message_id` | UUID | FK → `messages.id`, **UNIQUE**, `ON DELETE CASCADE` | one-to-one with message |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | denormalised from message |
| `level` | VARCHAR(10) | NOT NULL | one of `RiskLevel` |
| `flag` | VARCHAR(40) | NULL | one of `RiskFlag`; NULL only for clearly-low |
| `reason` | TEXT | NOT NULL | short human-readable explanation |
| `escalation_recommended` | BOOLEAN | NOT NULL, default false | informational; no behavior here |
| `rules_version` | VARCHAR(40) | NOT NULL | e.g. `rules-v1` |
| `status` | VARCHAR(20) | NOT NULL | one of `RiskAssessmentStatus` |
| `reviewed_by` | UUID | NULL, FK → `users.id` | set on human review |
| `reviewed_at` | TIMESTAMPTZ | NULL | set on human review |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |

### Indexes

- `UNIQUE (message_id)` — enforces one-to-one and powers the per-message read.
- `INDEX (tenant_id, level)` — high-risk triage queries within a tenant.
- `INDEX (tenant_id, escalation_recommended)` — seam for the future escalation queue.

### SQLAlchemy model (`backend/app/models/risk.py`)

```python
class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    flag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    escalation_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    message: Mapped["Message"] = relationship(back_populates="risk_assessment")

    __table_args__ = (
        Index("ix_risk_tenant_level", "tenant_id", "level"),
        Index("ix_risk_tenant_escalation", "tenant_id", "escalation_recommended"),
    )
```

`Message` gains: `risk_assessment: Mapped["RiskAssessment | None"] = relationship(back_populates="message", uselist=False, cascade="all, delete-orphan")`.

---

## Pydantic Schemas (`backend/app/schemas/risk.py`)

```python
class RiskAssessmentResponse(BaseModel):
    message_id: UUID
    level: RiskLevel
    flag: RiskFlag | None
    reason: str
    escalation_recommended: bool
    rules_version: str
    status: RiskAssessmentStatus
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssessResponse(RiskAssessmentResponse):
    """Returned by POST /risk-assessment — same shape as the read response."""


class RiskReviewRequest(BaseModel):
    level: RiskLevel                         # invalid → 422
    flag: RiskFlag | None = None             # invalid → 422
    reason: str = Field(min_length=1, max_length=500)

class RiskReviewResponse(RiskAssessmentResponse):
    """Returned by PATCH review — reflects status=reviewed."""
```

### Compact block embedded in inbox + detail responses

```python
class RiskSummary(BaseModel):
    level: RiskLevel | None              # null when not assessed
    flag: RiskFlag | None
    reason: str | None
    escalation_recommended: bool | None
```

- Added to each Spec 004 inbox item (`risk: RiskSummary | None`).
- Added to each Spec 005 detail message (`risk: RiskSummary | None`).
- `None`/null level → frontend shows "not assessed / pending".

---

## Rule Engine Contract (`backend/app/risk/engine.py`)

```python
@dataclass(frozen=True)
class RiskOutcome:
    level: RiskLevel
    flag: RiskFlag | None
    reason: str
    escalation_recommended: bool
    rules_version: str


class RiskEngine:
    def assess(self, *, intent: IntentLabel, confidence: float | None, body: str) -> RiskOutcome:
        text = (body or "").strip().lower()

        # 1. Baseline from intent
        level, flag = INTENT_BASELINE[intent]          # e.g. cancellation_request -> (high, cancellation_risk)
        clauses = [BASELINE_REASON[intent]]

        # 2. Empty / unclear -> at least medium + unclear flag
        if not text or intent == IntentLabel.other or (confidence is not None and confidence < UNCLEAR_CONF):
            level = max(level, RiskLevel.medium)        # monotonic raise
            flag = flag or RiskFlag.unsupported_or_unclear_request
            clauses.append("request is unclear or low-confidence")

        # 3. Keyword/business modifiers (raise only)
        if matches(text, URGENCY_TERMS):
            level = max(level, RiskLevel.high); clauses.append("urgency wording")
        if matches(text, REFUND_TERMS) and flag in (None, RiskFlag.payment_risk):
            level = max(level, RiskLevel.high); flag = RiskFlag.payment_risk; clauses.append("refund/payment dispute")
        if matches(text, CANCEL_TERMS):
            level = max(level, RiskLevel.high); flag = pick(flag, RiskFlag.cancellation_risk); clauses.append("cancellation language")
        if intent == IntentLabel.guest_count_change:
            delta = parse_guest_delta(text)
            if is_large(delta): level = RiskLevel.high; clauses.append(f"large guest change ({delta})")
        if matches(text, ESCALATION_TERMS):
            level = RiskLevel.high; flag = RiskFlag.human_escalation_needed; clauses.append("explicit escalation request")

        # 4. Primary flag by priority for compound cases
        flag = highest_priority(flag, candidates_from(clauses))

        # 5. Escalation recommendation + reason
        escalation = level == RiskLevel.high or flag == RiskFlag.human_escalation_needed
        return RiskOutcome(level, flag, build_reason(clauses), escalation, RULES_VERSION)
```

`max()` over `RiskLevel` uses an ordered ranking (`low<medium<high`) so modifiers only **raise** (FR-005, AC-18). The engine is pure (no DB, no I/O) and deterministic.

---

## Service Logic (`backend/app/services/risk_service.py`)

```python
async def assess_message(session, message) -> RiskAssessment | None:
    """Fail-safe for the auto caller; requires a classification."""
    if message.direction != MessageDirection.inbound:
        return None
    classification = await _get_classification(session, message.id)
    if classification is None:
        return None                          # auto path: skip until classified (manual path -> 409)

    existing = await _get_for_message(session, message.id)
    if existing and existing.status == RiskAssessmentStatus.reviewed:
        return existing                      # FR-013: never clobber a human decision

    try:
        outcome = engine.assess(
            intent=IntentLabel(classification.label),
            confidence=classification.confidence,
            body=message.body,
        )
        status = RiskAssessmentStatus.assessed
    except Exception:
        outcome = FAILED_OUTCOME             # medium / unclear / reason="assessment failed"
        status = RiskAssessmentStatus.failed

    return await _upsert(session, message, outcome, status)


async def get_risk_assessment(session, tenant_id, message_id) -> RiskAssessment:
    await _resolve_message_or_raise(session, tenant_id, message_id)    # 404 / 403
    result = await _get_for_message(session, message_id)
    if result is None:
        raise NoRiskAssessmentError()        # -> 404 NO_RISK_ASSESSMENT
    return result


async def review_risk_assessment(session, tenant_id, user, message_id, level, flag, reason) -> RiskAssessment:
    await _resolve_message_or_raise(session, tenant_id, message_id)    # 404 / 403
    result = await _get_for_message(session, message_id)
    if result is None:
        raise NoRiskAssessmentError()        # -> 404
    result.level = level                     # enum-validated upstream (422 if invalid)
    result.flag = flag
    result.reason = reason
    result.escalation_recommended = (level == RiskLevel.high) or (flag == RiskFlag.human_escalation_needed)
    result.status = RiskAssessmentStatus.reviewed
    result.reviewed_by = user.id
    result.reviewed_at = func.now()
    await session.commit()
    return result
```

`_resolve_message_or_raise` mirrors Specs 005/006: fetch message by id → `None`→404; tenant mismatch→403.

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (message) | 404 | `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `NoRiskAssessmentError` | 404 | `NO_RISK_ASSESSMENT` |
| `NotClassifiedError` (POST, no classification) | 409 | `NOT_CLASSIFIED` |
| invalid level/flag | 422 | validation detail |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/risk.ts`)

```typescript
type RiskLevel = "low" | "medium" | "high";

type RiskFlag =
  | "urgent_change" | "complaint" | "cancellation_risk" | "payment_risk"
  | "guest_count_change" | "human_escalation_needed" | "unsupported_or_unclear_request";

type RiskAssessmentStatus = "assessed" | "reviewed" | "failed";

interface RiskAssessment {
  message_id: string;
  level: RiskLevel;
  flag: RiskFlag | null;
  reason: string;
  escalation_recommended: boolean;
  rules_version: string;
  status: RiskAssessmentStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface RiskSummary {
  level: RiskLevel | null;
  flag: RiskFlag | null;
  reason: string | null;
  escalation_recommended: boolean | null;
}
```
