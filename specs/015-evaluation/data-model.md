# Data Model: Evaluation

**Branch**: `015-evaluation` | **Phase**: 1 — Design

---

## Schema Changes

**Three new tables** (+ one optional): `evaluation_runs`, `evaluation_results`, `evaluation_test_cases`, and optional `evaluation_metrics`. One Alembic migration. The run/result tables are **append-only** — no `updated_at`, no update/delete path (re-run instead). References to `tenants`/`users` are loose; deleting a tenant/user never erases past evidence (`SET NULL`). No column changes to existing tables (except an optional `eval_run_id` tag accepted by the Spec 013 audit writer).

---

## Enums

### `EvaluationArea`

```python
class EvaluationArea(str, Enum):
    classifier       = "classifier"        # 006 intent classifier quality
    risk_detection   = "risk_detection"    # 007 risk-level correctness
    rag_retrieval    = "rag_retrieval"     # 009 retrieval quality + grounding
    suggested_reply  = "suggested_reply"   # 010 reply groundedness/safety
    guardrail        = "guardrail"         # 014 red-team / safety
    tenant_isolation = "tenant_isolation"  # 001 cross-tenant containment
    agent_workflow   = "agent_workflow"    # 011/012 recommend-action behavior
    end_to_end       = "end_to_end"        # full named demo scenarios
```

### `EvaluationStatus`

```python
class EvaluationStatus(str, Enum):
    pending   = "pending"     # created/queued, not started
    running   = "running"     # execution in progress
    completed = "completed"   # finished; summary + results populated (may contain failed tests)
    failed    = "failed"      # the RUN errored (harness/execution error), not a test failure
```

The enums are **closed-but-extensible** (string-backed, validated at write). A test failing (`EvaluationResult.passed=false`) never sets the run to `failed`; `failed` is reserved for harness errors (with `EvaluationRun.notes`/result `error_message`).

### Area → primary metrics (stored in `summary_metrics`)

| Area | `summary_metrics` keys (examples) |
|------|-----------------------------------|
| `classifier` | `accuracy`, `macro_f1`, `weighted_f1`, `per_class_precision`, `per_class_recall`, `per_class_f1`, `confusion_matrix`, `labels`, `golden_set_accuracy` |
| `risk_detection` | `accuracy`, `per_level_precision`, `per_level_recall`, `high_risk_recall` |
| `rag_retrieval` | `hit_at_1`, `hit_at_3`, `hit_at_5`, `mrr`, `source_tenant_correctness`, `source_document_correctness`, `refusal_correctness`, `no_cross_tenant_source_rate` |
| `suggested_reply` | `groundedness`, `no_unsupported_claims`, `source_usage` |
| `guardrail` | `total`, `passed`, `failed`, per-category pass counts (`injection_blocked`, `disclosure_refused`, `unsupported_refused`, `pii_redacted`, `cross_tenant_blocked`, `invented_policy_blocked`) |
| `tenant_isolation` | `total`, `passed`, per-entity pass (`messages`, `documents`, `rag_sources`, `tasks`, `escalations`, `audit_logs`), `no_cross_tenant_source_rate` |
| `agent_workflow` | `total`, `passed`, `high_risk_recommends_action`, `action_correctness`, `no_autonomous_side_effect` |
| `end_to_end` | `total`, `passed`, `per_scenario` (11 booleans) |

---

## Existing Entities Used

| Entity (spec) | Used for |
|---------------|----------|
| `tenants` (001) | optional run scope (`evaluation_runs.tenant_id`); eval tenants A/B; isolation subject |
| `users` (002) | `created_by` (triggering owner); role gates trigger vs read |
| `messages` (003) | synthetic e2e/isolation fixtures (eval namespace) |
| `classification_results` (006) | classifier predictions scored against labels |
| `risk_assessments` (007) | risk-level predictions scored |
| `documents` (008) | eval-tenant documents retrieved over |
| `rag_retrievals` (009) | retrieval outputs scored (hit@k/source/refusal) |
| `suggested_replies` (010) | reply groundedness/source-usage scored |
| `tasks` (011) / `escalations` (012) | recommend-action workflow tests (not auto-created) |
| `audit_logs` (013) | isolation + PII-redaction-in-summary evidence; eval-tagged |
| `guardrail_decisions` (014) | red-team suite outcomes; redaction backstop for stored results |

All references are **loose** (ids in columns/metadata); evaluation rows do not own or cascade-delete these.

---

## New Entity: `EvaluationRun`

### Table `evaluation_runs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NULL, FK → `tenants.id` `ON DELETE SET NULL`, indexed | null for global/system runs; set for tenant-scoped |
| `run_name` | VARCHAR(160) | NOT NULL | human label (e.g., "classifier-test-2026-06-08") |
| `area` | VARCHAR(32) | NOT NULL | one of `EvaluationArea` |
| `status` | VARCHAR(16) | NOT NULL, default `pending` | one of `EvaluationStatus` |
| `started_at` | TIMESTAMPTZ | NULL | set when `running` |
| `completed_at` | TIMESTAMPTZ | NULL | set when `completed`/`failed` |
| `created_by` | UUID | NULL, FK → `users.id` `ON DELETE SET NULL` | the triggering owner |
| `summary_metrics` | JSONB | NOT NULL, default `{}` | aggregated metrics (see table above) |
| `artifact_paths` | JSONB | NOT NULL, default `{}` | `{ "json": "...", "csv": "...", "markdown": "..." }` |
| `notes` | TEXT | NULL | free-text (config, dataset version, harness error summary) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | server-assigned; ordering key |

**No `updated_at`** beyond the lifecycle stamps (`started_at`/`completed_at` are set once during execution); the row is otherwise immutable — re-run to produce a new run.

### Indexes

- `INDEX (tenant_id, created_at DESC)` — tenant-scoped newest-first list.
- `INDEX (area, created_at DESC)` — latest-per-area for the dashboard summary.
- `INDEX (status)` — filter `running`/`failed`.
- `INDEX (created_by)` — runs by owner.

---

## New Entity: `EvaluationResult`

### Table `evaluation_results`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `evaluation_run_id` | UUID | NOT NULL, FK → `evaluation_runs.id` `ON DELETE CASCADE`, indexed | parent run |
| `test_case_id` | UUID | NULL, FK → `evaluation_test_cases.id` `ON DELETE SET NULL` | the golden/fixture case (nullable) |
| `area` | VARCHAR(32) | NOT NULL | one of `EvaluationArea` (denormalized for query) |
| `input_payload` | JSONB | NOT NULL, default `{}` | the (redacted) case input |
| `expected_output` | JSONB | NOT NULL, default `{}` | the expected result/label |
| `actual_output` | JSONB | NOT NULL, default `{}` | the (redacted) actual result |
| `passed` | BOOLEAN | NOT NULL | did the case meet its expectation? |
| `score` | DOUBLE PRECISION | NULL | optional numeric (e.g., reciprocal rank, groundedness) |
| `error_message` | TEXT | NULL | per-case execution error (if any) |
| `metadata` | JSONB | NOT NULL, default `{}` | ids + short facts (matched doc ids, category, reason) — redacted |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | server-assigned |

> `input_payload`, `actual_output`, and `metadata` are passed through the 014/013 **redactor** before insert (SP-02). They never contain real secrets/JWTs/API keys/system prompts/raw PII/cross-tenant data. A captured leak is redacted here **and** sets `passed=false` for the originating safety test.

### Indexes

- `INDEX (evaluation_run_id)` — per-run results (primary read).
- `INDEX (evaluation_run_id, passed)` — failed-only filter.
- `INDEX (area)` — cross-run area queries.

`ON DELETE CASCADE` from the run is for referential tidiness only; the app exposes **no** delete path (immutable evidence).

---

## New Entity: `EvaluationTestCase`

### Table `evaluation_test_cases`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | stable id (also present in the fixture file) |
| `area` | VARCHAR(32) | NOT NULL | one of `EvaluationArea` |
| `tenant_id` | UUID | NULL, FK → `tenants.id` `ON DELETE SET NULL` | eval tenant for tenant-scoped cases (null for global) |
| `name` | VARCHAR(160) | NOT NULL | e.g., "e2e: cross-tenant attack", "injection: ignore-instructions" |
| `input` | JSONB | NOT NULL | the case input (synthetic/redacted) |
| `expected_output` | JSONB | NOT NULL | the expected label/outcome |
| `labels` | JSONB | NOT NULL, default `{}` | e.g., `{ "split": "golden", "intent": "pricing_request" }` |
| `content_hash` | VARCHAR(64) | NOT NULL, indexed | for the train-disjointness/leakage check |
| `version` | VARCHAR(32) | NOT NULL | fixture version tag |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

> Fixtures contain **only synthetic/redacted** content (no real PII, secrets, JWTs, or system-prompt text) — enforced by a fixture-scan test (SP-01). `content_hash` enables the golden∩train = ∅ leakage check (FR-012, AC-02).

### Indexes

- `INDEX (area, version)` — load a fixture set.
- `INDEX (content_hash)` — leakage/disjointness check.

---

## New Entity (optional): `EvaluationMetric`

A normalized (name, value) row per run for easy charting/querying alongside the `summary_metrics` JSON.

### Table `evaluation_metrics`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `evaluation_run_id` | UUID | NOT NULL, FK → `evaluation_runs.id` `ON DELETE CASCADE`, indexed | parent run |
| `name` | VARCHAR(64) | NOT NULL | e.g., `macro_f1`, `hit_at_3`, `no_cross_tenant_source_rate` |
| `value` | DOUBLE PRECISION | NULL | numeric value (NaN-safe → null) |
| `label` | VARCHAR(64) | NULL | optional sub-key (e.g., a per-class label) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

> Optional: the canonical metrics live in `evaluation_runs.summary_metrics`; this table is a flattened convenience for trend charts. `value` is `null` for undefined/no-support metrics (AC-22).

---

## SQLAlchemy Models (`backend/app/models/evaluation.py`)

```python
class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    run_name: Mapped[str] = mapped_column(String(160), nullable=False)
    area: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    summary_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_paths: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_eval_run_tenant_created", "tenant_id", "created_at"),
        Index("ix_eval_run_area_created", "area", "created_at"),
        Index("ix_eval_run_status", "status"),
        Index("ix_eval_run_created_by", "created_by"),
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    evaluation_run_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[UUID | None] = mapped_column(ForeignKey("evaluation_test_cases.id", ondelete="SET NULL"), nullable=True)
    area: Mapped[str] = mapped_column(String(32), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expected_output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    actual_output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_eval_result_run", "evaluation_run_id"),
        Index("ix_eval_result_run_passed", "evaluation_run_id", "passed"),
        Index("ix_eval_result_area", "area"),
    )
```

> The Python attribute is `metadata_` (the column name remains `metadata`) because `metadata` is reserved on the SQLAlchemy declarative base. `EvaluationTestCase`/`EvaluationMetric` follow the same conventions.

---

## Pydantic Schemas (`backend/app/schemas/evaluation.py`)

```python
class EvaluationRunCreate(BaseModel):
    area: EvaluationArea
    run_name: str = Field(min_length=1, max_length=160)
    split: Literal["validation", "test", "golden"] = "test"   # never "train"
    tenant_id: UUID | None = None                              # eval tenant or null (global)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("split")
    @classmethod
    def _no_train(cls, v):
        if v == "train":
            raise ValueError("training data may not be used as test data")
        return v


class EvaluationRunFilters(BaseModel):
    area: EvaluationArea | None = None
    status: EvaluationStatus | None = None
    tenant_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


class EvaluationRunListItem(BaseModel):
    id: UUID
    run_name: str
    area: EvaluationArea
    status: EvaluationStatus
    tenant_id: UUID | None
    created_by: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EvaluationRunResponse(EvaluationRunListItem):
    summary_metrics: dict
    artifact_paths: dict
    notes: str | None


class EvaluationResultResponse(BaseModel):
    id: UUID
    evaluation_run_id: UUID
    test_case_id: UUID | None
    area: EvaluationArea
    input_payload: dict
    expected_output: dict
    actual_output: dict
    passed: bool
    score: float | None
    error_message: str | None
    metadata: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunListItem]
    total: int
    limit: int
    offset: int


class EvaluationResultListResponse(BaseModel):
    items: list[EvaluationResultResponse]
    total: int
    limit: int
    offset: int


class EvaluationSummaryResponse(BaseModel):
    """Latest run per area for the dashboard."""
    areas: dict[str, dict]   # area -> { run_id, status, completed_at, summary_metrics }
```

---

## Service Logic (`backend/app/services/evaluation_service.py`)

```python
AREA_RUNNERS = {
    EvaluationArea.classifier:       run_classifier,
    EvaluationArea.risk_detection:   run_risk,
    EvaluationArea.rag_retrieval:    run_rag,
    EvaluationArea.suggested_reply:  run_reply,
    EvaluationArea.guardrail:        run_guardrail,
    EvaluationArea.tenant_isolation: run_isolation,
    EvaluationArea.agent_workflow:   run_agent_workflow,
    EvaluationArea.end_to_end:       run_end_to_end,
}

async def create_run(session, *, user_id, role, payload: EvaluationRunCreate) -> EvaluationRun:
    if role != settings.EVAL_OWNER_ROLE:                      # SP-05 / FR-015
        raise ForbiddenError("INSUFFICIENT_ROLE")
    run = EvaluationRun(tenant_id=payload.tenant_id, run_name=payload.run_name,
                        area=payload.area.value, status=EvaluationStatus.running.value,
                        created_by=user_id, started_at=func.now(), notes=payload.notes)
    session.add(run); await session.flush()
    try:
        runner = AREA_RUNNERS[payload.area]
        outcome = await runner(session, run=run, split=payload.split, tenant_id=payload.tenant_id)
        for r in outcome.results:                            # each redacted before storage (SP-02)
            session.add(_to_result_row(run.id, r))
        run.summary_metrics = outcome.summary
        run.artifact_paths = write_artifacts(run, outcome)   # JSON/CSV/Markdown (FR-013)
        run.status = EvaluationStatus.completed.value        # completed even if tests failed (FR-019)
    except Exception as exc:                                 # harness error → failed (FR-019)
        run.status = EvaluationStatus.failed.value
        run.notes = (run.notes or "") + f"\n[harness_error] {redact_text(str(exc))[0]}"
    run.completed_at = func.now()
    await session.commit()
    return run


async def list_runs(session, *, caller, filters, limit, offset):
    limit = min(limit, settings.EVAL_RESULTS_MAX_LIMIT)
    stmt = select(EvaluationRun)
    stmt = _scope_runs(stmt, caller)                         # tenant-scoped / global (FR-020)
    if filters.area:    stmt = stmt.where(EvaluationRun.area == filters.area.value)
    if filters.status:  stmt = stmt.where(EvaluationRun.status == filters.status.value)
    if filters.created_from: stmt = stmt.where(EvaluationRun.created_at >= filters.created_from)
    if filters.created_to:   stmt = stmt.where(EvaluationRun.created_at <= filters.created_to)
    stmt = stmt.order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
    total = await _count(session, stmt)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return rows, total


async def get_run(session, *, caller, run_id) -> EvaluationRun:
    row = await session.get(EvaluationRun, run_id)
    if row is None: raise NotFoundError("EVALUATION_RUN_NOT_FOUND")          # 404
    if not _can_read(caller, row): raise ForbiddenError("CROSS_TENANT_FORBIDDEN")  # 403
    return row


async def list_results(session, *, caller, run_id, limit, offset):
    run = await get_run(session, caller=caller, run_id=run_id)               # scope-gate
    stmt = (select(EvaluationResult)
            .where(EvaluationResult.evaluation_run_id == run.id)
            .order_by(EvaluationResult.created_at.asc(), EvaluationResult.id.asc()))
    total = await _count(session, stmt)
    rows = (await session.execute(stmt.limit(min(limit, settings.EVAL_RESULTS_MAX_LIMIT)).offset(offset))).scalars().all()
    return rows, total


async def summary(session, *, caller, area=None):
    """Latest completed run per area, scope-filtered, for the dashboard."""
    ...
```

`_scope_runs`/`_can_read` enforce: a tenant-scoped run is readable only within its tenant (and by authorized roles); global runs (`tenant_id=null`) per role/config (FR-020, SP-04). `write_artifacts` and the runners live in `backend/eval/`.

### Error → HTTP mapping (endpoints)

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| non-owner triggers a run | 403 | `INSUFFICIENT_ROLE` |
| `NotFoundError` (run/result) | 404 | `EVALUATION_RUN_NOT_FOUND` / `EVALUATION_RESULT_NOT_FOUND` |
| `ForbiddenError` (cross-tenant read) | 403 | `CROSS_TENANT_FORBIDDEN` |
| invalid area/split/format/filter/pagination | 422 | validation detail |
| update/delete attempt (no route) | 405 | `METHOD_NOT_ALLOWED` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

> A run whose tests failed is a **200/`completed`** response (with `summary_metrics` showing the failures); only a harness error yields `status="failed"` (still a 200 read).

---

## Frontend Types (`frontend/src/types/evaluation.ts`)

```typescript
type EvaluationArea =
  | "classifier" | "risk_detection" | "rag_retrieval" | "suggested_reply"
  | "guardrail" | "tenant_isolation" | "agent_workflow" | "end_to_end";
type EvaluationStatus = "pending" | "running" | "completed" | "failed";

interface EvaluationRun {
  id: string;
  tenant_id: string | null;
  run_name: string;
  area: EvaluationArea;
  status: EvaluationStatus;
  started_at: string | null;
  completed_at: string | null;
  created_by: string | null;
  summary_metrics: Record<string, unknown>;
  artifact_paths: Record<string, string>;
  notes: string | null;
  created_at: string;
}

interface EvaluationResult {
  id: string;
  evaluation_run_id: string;
  test_case_id: string | null;
  area: EvaluationArea;
  input_payload: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  actual_output: Record<string, unknown>;
  passed: boolean;
  score: number | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}
```

---

## Invariants

- **Immutable evidence**: runs/results are append-only (no update/delete path); re-running creates a new run; prior runs retained.
- **Held-out only**: model metrics use `validation`/`test`/`golden` splits — never `train`; golden∩train = ∅ (id + hash) is asserted.
- **Redaction in stored fields**: `input_payload`/`actual_output`/`metadata` and all artifacts pass the 014/013 redactor — no secrets/JWTs/keys/system prompts/raw PII/cross-tenant data; a captured leak is redacted **and** fails its safety test.
- **Run status vs test pass/fail**: `failed` = harness error only; a `completed` run may contain `passed=false` results.
- **Refusal scored separately**: RAG `refusal_correctness` is independent of `source_*_correctness` (no gaming).
- **No autonomy / no pollution**: runners never auto-send or auto-create; eval data stays in the eval tenant/namespace; eval audit entries are tagged.
- **Privileged trigger, scoped reads**: only the owner triggers; reads are side-effect-free and tenant-scoped where `tenant_id` is set; cross-tenant read → 404/403.
- **NaN-safe metrics**: no-support classes / empty golden sets → `null`, never a crash or a fake 100%.
- **Ordering**: runs `created_at` desc; results `created_at` asc (case order); reads paginated + bounded.
