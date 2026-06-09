# Data Model: Guardrails

**Branch**: `014-guardrails` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `guardrail_decisions`. One Alembic migration. The table is **append-only** — it has no `updated_at`, and the application exposes no update/delete path (mirrors Spec 013 audit logs). References to `messages` and `suggested_replies` are **loose** (`ON DELETE SET NULL`) so deleting a business row never erases the safety trail. No column changes to existing tables.

---

## Enums

### `GuardrailCategory`

```python
class GuardrailCategory(str, Enum):
    prompt_injection             = "prompt_injection"
    system_prompt_disclosure     = "system_prompt_disclosure"
    cross_tenant_access          = "cross_tenant_access"
    unsupported_answer           = "unsupported_answer"
    pii_redaction                = "pii_redaction"
    unsafe_or_unprofessional_reply = "unsafe_or_unprofessional_reply"
    secret_or_token_exposure     = "secret_or_token_exposure"
    human_review_required        = "human_review_required"
```

### `GuardrailAction`

```python
class GuardrailAction(str, Enum):
    allow                = "allow"                 # passed all checks; proceed
    warn                 = "warn"                  # allowed, non-blocking concern noted
    redact               = "redact"                # allowed after PII/secret spans removed
    refuse               = "refuse"                # blocked; output not shown; professional refusal
    require_human_review = "require_human_review"  # held; a human must review before use
```

### `GuardrailSeverity`

```python
class GuardrailSeverity(str, Enum):
    info     = "info"        # normal pass / benign note
    low      = "low"         # minor concern, optional human glance
    medium   = "medium"      # notable; reply held for review
    high     = "high"        # serious; blocked output (e.g., secret exposure)
    security = "security"    # security event; blocked + audited as security
```

The enums are **closed-but-extensible**: validated at write time, but later features may add values without an enum-altering migration (string-backed). There is no state machine — decisions are independent, append-only facts.

### Category → (default action, severity) and audit mapping

| Category | Stage | Default action | Default severity | Spec 013 audit event |
|----------|-------|----------------|------------------|----------------------|
| `prompt_injection` | input | `refuse` | `security` | `guardrail_refusal` |
| `system_prompt_disclosure` | input/output | `refuse` | `security` | `guardrail_refusal` |
| `cross_tenant_access` | input | `refuse` | `security` | `cross_tenant_access_blocked` |
| `unsupported_answer` | output | `refuse` / `require_human_review` | `medium` | `unsupported_answer_refused` |
| `secret_or_token_exposure` | output | `refuse` / `redact` | `high` | `guardrail_refusal` |
| `unsafe_or_unprofessional_reply` | output | `require_human_review` / `refuse` | `medium` | `guardrail_refusal` |
| `pii_redaction` | input/output | `redact` | `info` | *(none required; redaction noted in metadata)* |
| `human_review_required` | input/output | `require_human_review` | `low` | *(optional `guardrail_refusal` if held)* |

> A clean pass is `category=null` (or `human_review_required` low) with `action=allow`; persisting trivial allows is gated by `GUARDRAIL_LOG_ALLOW_DECISIONS`.

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | `guardrail_decisions.tenant_id` scope; tenant registry for cross-tenant detection |
| `users` (002) | the staff/manager in context; role gates the read surface (no `user_id` column required, but `metadata.actor_user_id` may be recorded) |
| `messages` (003) | `message_id` reference; original body stored as-is, redacted only in summaries |
| `rag_retrievals` / sources (009) | grounding validation input; `source_document_ids` (ids only) in metadata |
| `suggested_replies` (010) | `suggested_reply_id` reference; the checked draft; never auto-sent |
| `audit_logs` (013) | each decision writes a `guardrail_refusal` / `cross_tenant_access_blocked` / `unsupported_answer_refused` entry (best-effort) |

All references are **loose** (ids in columns or metadata); the decision row does not own or cascade-delete these.

---

## New Entity: `GuardrailDecision`

### Table `guardrail_decisions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes all access |
| `message_id` | UUID | NULL, FK → `messages.id` `ON DELETE SET NULL`, indexed | the checked message (nullable) |
| `suggested_reply_id` | UUID | NULL, FK → `suggested_replies.id` `ON DELETE SET NULL` | the checked draft (nullable) |
| `category` | VARCHAR(40) | NOT NULL | one of `GuardrailCategory` |
| `action` | VARCHAR(24) | NOT NULL | one of `GuardrailAction` |
| `severity` | VARCHAR(12) | NOT NULL, default `info` | one of `GuardrailSeverity` |
| `reason` | TEXT | NULL | short human-readable, redacted reason |
| `redacted_text` | TEXT | NULL | PII/secret-minimized snippet (never raw) |
| `metadata` | JSONB | NOT NULL, default `{}` | ids + minimal facts (redacted) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | server-assigned; ordering key |

**No `updated_at`** — decisions are immutable (append-only).

### Field notes

- `message_id` / `suggested_reply_id` are **both nullable**: an input check on a free-text staff query may have a message but no reply yet; an output check has both.
- `reason` is a short sentence (e.g., "Input attempted to override system instructions.") — **never** the offending text, the system prompt, or a secret.
- `redacted_text` is optional and only present for `redact`/`refuse` where a minimized snippet is useful; it passes through `redact_text` (PII + secret + prompt markers).
- `metadata` examples (ids + facts only): `{"stage": "input", "matched_rule": "instruction_override", "grounded": false, "partial": true, "source_document_ids": [...], "also_flagged": ["pii_redaction"], "attempted_route": "...", "attempted_entity_type": "document"}` — **never** target-tenant data, prompts, secrets, or raw PII.

### Indexes

- `INDEX (tenant_id, created_at DESC)` — primary newest-first list.
- `INDEX (tenant_id, category)` — filter by category.
- `INDEX (tenant_id, action)` — filter by action.
- `INDEX (tenant_id, severity)` — filter by severity.
- `INDEX (tenant_id, message_id)` — message-scoped reads.

### Append-only enforcement

- The ORM model and service expose **no** update/delete; there is no PATCH/DELETE endpoint.
- **Recommended** (mirror Spec 013): revoke `UPDATE, DELETE` on `guardrail_decisions` for the app DB role, or add a `BEFORE UPDATE OR DELETE` trigger that raises.

### SQLAlchemy model (`backend/app/models/guardrail_decision.py`)

```python
class GuardrailDecision(Base):
    __tablename__ = "guardrail_decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    suggested_reply_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("suggested_replies.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="info")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_guardrail_tenant_created", "tenant_id", "created_at"),
        Index("ix_guardrail_tenant_category", "tenant_id", "category"),
        Index("ix_guardrail_tenant_action", "tenant_id", "action"),
        Index("ix_guardrail_tenant_severity", "tenant_id", "severity"),
        Index("ix_guardrail_tenant_message", "tenant_id", "message_id"),
    )
```

> Note: the Python attribute is `metadata_` because `metadata` is reserved on the SQLAlchemy declarative base; the column name remains `metadata`.

---

## Pydantic Schemas (`backend/app/schemas/guardrails.py`)

```python
class CheckInputRequest(BaseModel):
    text: str = Field(min_length=0, max_length=20_000)
    message_id: UUID | None = None


class CheckOutputRequest(BaseModel):
    draft_text: str = Field(max_length=20_000)
    message_id: UUID | None = None
    suggested_reply_id: UUID | None = None
    source_document_ids: list[UUID] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)   # retrieved chunk texts (not persisted)


class CheckResult(BaseModel):
    """Returned to the caller (010) to apply the action."""
    category: GuardrailCategory | None
    action: GuardrailAction
    severity: GuardrailSeverity
    reason: str | None = None
    proceed: bool                       # input: may call AI/RAG?  output: may show draft?
    display_text: str | None = None     # safe/redacted text or the professional refusal message
    decision_id: UUID | None = None     # the persisted GuardrailDecision id (if persisted)
    metadata: dict = Field(default_factory=dict)


class GuardrailDecisionFilters(BaseModel):
    category: GuardrailCategory | None = None
    action: GuardrailAction | None = None
    severity: GuardrailSeverity | None = None
    message_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


class GuardrailDecisionListItem(BaseModel):
    id: UUID
    created_at: datetime
    category: GuardrailCategory
    action: GuardrailAction
    severity: GuardrailSeverity
    message_id: UUID | None
    suggested_reply_id: UUID | None
    reason: str | None
    model_config = ConfigDict(from_attributes=True)


class GuardrailDecisionResponse(GuardrailDecisionListItem):
    redacted_text: str | None
    metadata: dict


class GuardrailDecisionListResponse(BaseModel):
    items: list[GuardrailDecisionListItem]
    total: int
    limit: int
    offset: int
```

---

## Service Logic (`backend/app/services/guardrail_service.py`)

```python
async def check_user_input(session, *, tenant_id, user_id, role, text, message_id=None) -> CheckResult:
    """Runs BEFORE RAG/generation. Fail-safe: a probe-class error → refuse (don't invoke AI)."""
    try:
        text = (text or "")[: settings.GUARDRAIL_MAX_SCAN_CHARS]
        if not text.strip():
            return CheckResult(category=None, action=GuardrailAction.allow,
                               severity=GuardrailSeverity.info, proceed=True)

        if detect_injection(text):
            return await _decide(session, tenant_id, message_id, None,
                                 GuardrailCategory.prompt_injection, GuardrailAction.refuse,
                                 GuardrailSeverity.security,
                                 reason="Input attempted to override system instructions.",
                                 proceed=False, display_text=REFUSAL_INJECTION,
                                 audit_event="guardrail_refusal")
        if detect_disclosure(text):
            return await _decide(session, tenant_id, message_id, None,
                                 GuardrailCategory.system_prompt_disclosure, GuardrailAction.refuse,
                                 GuardrailSeverity.security,
                                 reason="Input attempted to reveal hidden instructions.",
                                 proceed=False, display_text=REFUSAL_DISCLOSURE,
                                 audit_event="guardrail_refusal")
        other = detect_cross_tenant(text, _tenant_registry(session, exclude=tenant_id))
        if other is not None:
            return await _decide(session, tenant_id, message_id, None,
                                 GuardrailCategory.cross_tenant_access, GuardrailAction.refuse,
                                 GuardrailSeverity.security,
                                 reason="Input referenced another tenant's data.",
                                 proceed=False, display_text=REFUSAL_CROSS_TENANT,
                                 metadata={"attempted_entity_type": "tenant_data"},   # no target id/name
                                 audit_event="cross_tenant_access_blocked")

        return CheckResult(category=None, action=GuardrailAction.allow,
                           severity=GuardrailSeverity.info, proceed=True)
    except Exception:                                   # FAIL SAFE — never fail open
        logger.warning("guardrail_input_error", exc_info=True)
        return CheckResult(category=GuardrailCategory.human_review_required,
                           action=GuardrailAction.refuse, severity=GuardrailSeverity.medium,
                           proceed=False, display_text=REFUSAL_GENERIC)


async def check_ai_output(session, *, tenant_id, user_id, draft_text, sources,
                          source_document_ids, message_id, suggested_reply_id) -> CheckResult:
    """Runs AFTER generation, BEFORE display. Fail-safe: any error → require_human_review (hold)."""
    try:
        grounding = validate_rag_grounding(draft_text, sources)
        if not grounding.grounded:
            return await _decide(session, tenant_id, message_id, suggested_reply_id,
                                 GuardrailCategory.unsupported_answer,
                                 GuardrailAction.refuse, GuardrailSeverity.medium,
                                 reason="Draft is not grounded in your tenant documents.",
                                 proceed=False, display_text=REFUSAL_UNSUPPORTED,
                                 metadata={"grounded": False,
                                           "source_document_ids": [str(i) for i in source_document_ids]},
                                 audit_event="unsupported_answer_refused")
        if detect_secret(draft_text) or detect_disclosure(draft_text):
            cleaned, _ = redact_text(draft_text)
            return await _decide(session, tenant_id, message_id, suggested_reply_id,
                                 GuardrailCategory.secret_or_token_exposure,
                                 GuardrailAction.refuse, GuardrailSeverity.high,
                                 reason="Draft contained a secret or internal instruction.",
                                 proceed=False, display_text=REFUSAL_SECRET,
                                 redacted_text=cleaned, audit_event="guardrail_refusal")
        if detect_unsafe(draft_text):
            return await _decide(session, tenant_id, message_id, suggested_reply_id,
                                 GuardrailCategory.unsafe_or_unprofessional_reply,
                                 GuardrailAction.require_human_review, GuardrailSeverity.medium,
                                 reason="Draft may be unsafe or make an unauthorized commitment.",
                                 proceed=False, display_text=draft_text,   # held, not auto-ready
                                 audit_event="guardrail_refusal")
        if grounding.partial:
            return await _decide(session, tenant_id, message_id, suggested_reply_id,
                                 GuardrailCategory.unsupported_answer,
                                 GuardrailAction.require_human_review, GuardrailSeverity.medium,
                                 reason="Some claims are not supported by your documents.",
                                 proceed=False, display_text=draft_text,
                                 metadata={"partial": True,
                                           "source_document_ids": [str(i) for i in source_document_ids]})
        # clean: PII-redact the summary only; the draft is shown (still 010 human-approve)
        return CheckResult(category=None, action=GuardrailAction.allow,
                           severity=GuardrailSeverity.info, proceed=True, display_text=draft_text)
    except Exception:                                   # FAIL SAFE — hold, never show unchecked
        logger.warning("guardrail_output_error", exc_info=True)
        return CheckResult(category=GuardrailCategory.human_review_required,
                           action=GuardrailAction.require_human_review,
                           severity=GuardrailSeverity.medium, proceed=False,
                           display_text=None)


async def _decide(session, tenant_id, message_id, suggested_reply_id, category, action,
                  severity, *, reason, proceed, display_text=None, redacted_text=None,
                  metadata=None, audit_event=None) -> CheckResult:
    """Build + redact + persist the decision, then write a best-effort Spec 013 audit log."""
    clean_reason, _ = redact_text(reason or "")
    clean_meta = redact_metadata(metadata or {})
    row = GuardrailDecision(tenant_id=tenant_id, message_id=message_id,
                            suggested_reply_id=suggested_reply_id, category=category.value,
                            action=action.value, severity=severity.value, reason=clean_reason,
                            redacted_text=(redact_text(redacted_text)[0] if redacted_text else None),
                            metadata_=clean_meta)
    session.add(row); await session.flush()             # decision persisted (safety primary)
    if audit_event:                                     # best-effort (Spec 013 never raises)
        await _write_audit(session, tenant_id, message_id, audit_event, category, clean_meta)
    return CheckResult(category=category, action=action, severity=severity, reason=clean_reason,
                       proceed=proceed, display_text=display_text, decision_id=row.id,
                       metadata=clean_meta)


async def list_guardrail_decisions(session, tenant_id, filters: GuardrailDecisionFilters, *, limit, offset):
    limit = min(limit, settings.GUARDRAIL_DECISIONS_MAX_LIMIT)
    stmt = select(GuardrailDecision).where(GuardrailDecision.tenant_id == tenant_id)   # SR-01
    if filters.category:     stmt = stmt.where(GuardrailDecision.category == filters.category.value)
    if filters.action:       stmt = stmt.where(GuardrailDecision.action == filters.action.value)
    if filters.severity:     stmt = stmt.where(GuardrailDecision.severity == filters.severity.value)
    if filters.message_id:   stmt = stmt.where(GuardrailDecision.message_id == filters.message_id)
    if filters.created_from:  stmt = stmt.where(GuardrailDecision.created_at >= filters.created_from)
    if filters.created_to:    stmt = stmt.where(GuardrailDecision.created_at <= filters.created_to)
    stmt = stmt.order_by(GuardrailDecision.created_at.desc(), GuardrailDecision.id.desc())
    total = await _count(session, stmt)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return rows, total


async def get_guardrail_decision(session, tenant_id, decision_id) -> GuardrailDecision:
    row = await session.get(GuardrailDecision, decision_id)
    if row is None: raise NotFoundError()                  # 404 GUARDRAIL_DECISION_NOT_FOUND
    if row.tenant_id != tenant_id: raise ForbiddenError()  # 403 CROSS_TENANT_FORBIDDEN
    return row


async def decisions_for_message(session, tenant_id, message_id, *, staff_view=False):
    await _resolve_message_or_raise(session, tenant_id, message_id)   # 404/403
    stmt = (select(GuardrailDecision)
            .where(GuardrailDecision.tenant_id == tenant_id,
                   GuardrailDecision.message_id == message_id)
            .order_by(GuardrailDecision.created_at.desc(), GuardrailDecision.id.desc()))
    return (await session.execute(stmt)).scalars().all()
```

### Detection (`backend/app/services/guardrail_rules.py`)

```python
INJECTION_PATTERNS = [
    r"ignore (all )?(the )?previous instructions",
    r"disregard (the )?above",
    r"forget (your|the) (instructions|rules)",
    r"you are now\b", r"\bact as\b.*\b(system|developer|admin)\b",
    r"^\s*(system|developer)\s*:",
]
DISCLOSURE_PATTERNS = [
    r"(show|reveal|print|repeat|tell me).{0,30}(system )?(prompt|hidden (rules|instructions)|internal (policy|policies))",
    r"what (are|is) your (system )?(prompt|instructions|rules)",
]
SECRET_PATTERNS = [
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",  # JWT
    r"sk-[A-Za-z0-9]{16,}", r"AKIA[0-9A-Z]{16}",                        # API keys
    r"(api[_-]?key|secret|password|bearer)\s*[:=]\s*\S+",
]
UNSAFE_LEXICON = ["idiot", "stupid", "shut up", "guaranteed refund", "i promise you", "definitely free"]
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PHONE_RE = r"(\+?\d[\d\s().-]{6,}\d)"

def detect_injection(text): ...
def detect_disclosure(text): ...
def detect_cross_tenant(text, tenant_registry): ...   # returns matched other-tenant or None
def detect_secret(text): ...
def detect_unsafe(text): ...
```

### Redaction (`backend/app/services/guardrail_redaction.py`)

```python
def redact_pii(text: str) -> tuple[str, bool]:
    found = False
    out = re.sub(EMAIL_RE, "[EMAIL_REDACTED]", text)
    if out != text: found = True
    text2 = out
    out = re.sub(PHONE_RE, "[PHONE_REDACTED]", text2)
    if out != text2: found = True
    return out, found

def redact_text(text: str) -> tuple[str, dict]:
    """PII + secret/JWT/key + prompt-marker stripping for any stored field (FR-019)."""
    out, pii = redact_pii(text or "")
    for pat in SECRET_PATTERNS:
        out = re.sub(pat, "[SECRET_REDACTED]", out, flags=re.I)
    return out, {"pii": pii}

def redact_metadata(meta: dict) -> dict:
    """Drop forbidden keys; never store target-tenant data / prompts / secrets / raw PII."""
    forbidden = ("token", "secret", "password", "api_key", "authorization", "jwt", "prompt",
                 "target_tenant", "other_tenant")
    return {k: v for k, v in meta.items()
            if not any(p in k.lower() for p in forbidden)}
```

### Grounding (`backend/app/services/guardrail_grounding.py`)

```python
@dataclass
class GroundingResult:
    grounded: bool
    source_document_ids: list
    partial: bool

def validate_rag_grounding(draft_text: str, sources: list[str]) -> GroundingResult:
    if not sources:                                     # GR-02: no source ⇒ not grounded
        return GroundingResult(grounded=False, source_document_ids=[], partial=False)
    coverage = _claim_coverage(draft_text, sources)     # lexical/semantic overlap (Decision 4)
    grounded = coverage.supported_ratio >= settings.GUARDRAIL_GROUNDING_THRESHOLD
    partial = grounded and coverage.has_unsupported_claim
    return GroundingResult(grounded=grounded,
                           source_document_ids=coverage.matched_doc_ids, partial=partial)
```

`_resolve_message_or_raise` mirrors Specs 005–013 (404 / 403). `_write_audit` calls Spec 013 `AuditService.log_event` / `log_cross_tenant_blocked` and never raises into the guardrail.

### Error → HTTP mapping (read + check endpoints)

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (decision/message) | 404 | `GUARDRAIL_DECISION_NOT_FOUND` / `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| staff requests tenant-wide list | 403 | `INSUFFICIENT_ROLE` |
| invalid filter / pagination / payload / enum | 422 | validation detail |
| update/delete attempt (no route) | 405 | `METHOD_NOT_ALLOWED` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

> A guardrail **refuse** is a successful HTTP response (the check ran and returned a decision); it is **not** an error status. The check endpoints return `200` with a `CheckResult` whether the action is `allow` or `refuse`.

---

## Frontend Types (`frontend/src/types/guardrails.ts`)

```typescript
type GuardrailCategory =
  | "prompt_injection" | "system_prompt_disclosure" | "cross_tenant_access"
  | "unsupported_answer" | "pii_redaction" | "unsafe_or_unprofessional_reply"
  | "secret_or_token_exposure" | "human_review_required";
type GuardrailAction = "allow" | "warn" | "redact" | "refuse" | "require_human_review";
type GuardrailSeverity = "info" | "low" | "medium" | "high" | "security";

interface GuardrailDecision {
  id: string;
  tenant_id: string;
  message_id: string | null;
  suggested_reply_id: string | null;
  category: GuardrailCategory;
  action: GuardrailAction;
  severity: GuardrailSeverity;
  reason: string | null;
  redacted_text: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface CheckResult {
  category: GuardrailCategory | null;
  action: GuardrailAction;
  severity: GuardrailSeverity;
  reason: string | null;
  proceed: boolean;
  display_text: string | null;   // safe/redacted text or the professional refusal
  decision_id: string | null;
}
```

---

## Invariants

- **Tenant scope**: every read/write filters by `tenant_id`; `cross_tenant_access` decisions store no target-tenant field; the audit block is written in the caller's tenant only.
- **Append-only**: decisions are never updated or deleted; no `updated_at`, no mutate path; DB-level UPDATE/DELETE revocation recommended.
- **Two chokepoints**: `check_user_input` precedes RAG/generation; `check_ai_output` precedes display; no path skips either.
- **Fail safe**: output-check error → `require_human_review` (hold); input probe-path error → `refuse` (no AI invocation); never fail open.
- **Redaction**: `reason`/`redacted_text`/`metadata` and every audit summary are redacted — no system prompt, secret, JWT, API key, raw PII, or cross-tenant data.
- **Grounded-only**: a shown draft's claims are supported by retrieved tenant sources; no source / ungrounded ⇒ refuse or hold.
- **No autonomous side effects**: the guardrail path never auto-sends, creates tasks, or escalates; at most `require_human_review`.
- **PII non-blocking**: PII → `redact`/`info`, never `refuse`; the stored message body is unchanged.
- **Best-effort audit**: a refuse decision stands even if the audit (or decision persistence backstop) logging fails.
- **Ordering**: `created_at` desc, `id` desc tiebreak; `created_at` server-assigned; reads paginated + bounded.
