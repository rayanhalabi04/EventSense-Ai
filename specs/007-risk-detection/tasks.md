---

description: "Task list for Risk Detection feature implementation"
---

# Tasks: Risk Detection

**Branch**: `007-risk-detection` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/007-risk-detection/`

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `messages` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`; Platform Admin block; `users` table
- Spec 003 — Message Simulator: inbound message creation path; `MessageDirection` (`inbound`/`outbound`)
- Spec 004 — Message Inbox: `get_inbox()` inbox-item response (extended here with a `risk` summary)
- Spec 005 — Message Detail Page: `get_conversation_detail()` message response (extended here) + the "Risk / Sentiment" placeholder panel (replaced here)
- Spec 006 — Intent Classifier: `ClassificationResult` (label + confidence + status), `IntentLabel` enum, and the post-classification hook that risk chains onto

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `risk_assessments` (one-to-one with `messages`) + one Alembic migration. Persisted as constrained-string enums (not native PG enums).

**Config defaults** (research/plan): `RISK_RULES_VERSION=rules-v1` (+ any tunable keyword/threshold constants live in `risk/rules.py`).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–006 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Message` model + `MessageDirection` enum (Spec 003), `ClassificationResult` model + `IntentLabel` enum (Spec 006), `User` model (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `NotFoundError`/`ForbiddenError` (Spec 001), `get_inbox()` (Spec 004), `get_conversation_detail()` (Spec 005), and the Spec 006 post-classification hook site. Do NOT redefine any of these.
- [ ] T002 Add `RISK_RULES_VERSION` (`rules-v1`) and any tunable risk thresholds to `backend/app/core/config.py` with documented defaults (keyword lists themselves live in `risk/rules.py`, not config)
- [ ] T003 Verify `backend/tests/integration/` and `backend/tests/unit/` exist with `__init__.py`; create if absent (required before test files in later phases)

**Checkpoint**: Dependencies confirmed reused; config in place.

---

## Phase 2: Database & Models (Foundational — Blocking)

**Purpose**: The `risk_assessments` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–7 cannot run without this phase.

- [ ] T004 [P] Create `RiskLevel` (`low`/`medium`/`high`), `RiskFlag` (seven values), and `RiskAssessmentStatus` (`assessed`/`reviewed`/`failed`) string enums in `backend/app/schemas/risk.py` (shared by the engine, service, and API layers)
- [ ] T005 Create `RiskAssessment` SQLAlchemy model in `backend/app/models/risk.py`: `id` UUID PK; `message_id` UUID FK→`messages.id` UNIQUE `ON DELETE CASCADE`; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `level` VARCHAR(10) NOT NULL; `flag` VARCHAR(40) nullable; `reason` TEXT NOT NULL; `escalation_recommended` Boolean NOT NULL default false; `rules_version` VARCHAR(40) NOT NULL; `status` VARCHAR(20) NOT NULL; `reviewed_by` UUID FK→`users.id` nullable; `reviewed_at` TIMESTAMPTZ nullable; `created_at`/`updated_at` TIMESTAMPTZ; `Index("ix_risk_tenant_level", "tenant_id", "level")` and `Index("ix_risk_tenant_escalation", "tenant_id", "escalation_recommended")`; `message` relationship `back_populates="risk_assessment"`
- [ ] T006 Add the inverse relationship on `Message` (Spec 001/003 messages model): `risk_assessment: Mapped["RiskAssessment | None"] = relationship(back_populates="message", uselist=False, cascade="all, delete-orphan")` (depends on T005)
- [ ] T007 Create Alembic migration `backend/alembic/versions/00xx_create_risk_assessments.py` creating `risk_assessments` with all columns, the UNIQUE constraint on `message_id` (FK CASCADE), the `tenant_id` FK, and both composite indexes; provide a correct `downgrade()` dropping the table (depends on T005)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable.

---

## Phase 3: Risk Rule Engine (Foundational — Blocking)

**Purpose**: The pure, deterministic rule engine is the core of the feature (FR-004: separate from the classifier). Build and fully unit-test it in isolation before any DB/API wiring. **BLOCKS US1.**

- [ ] T008 Create versioned rule data in `backend/app/risk/rules.py`: `INTENT_BASELINE` map (booking/pricing/availability/service → `(low, None)`; `urgent_change` → `(high, urgent_change)`; `complaint` → `(high, complaint)`; `cancellation_request` → `(high, cancellation_risk)`; `human_escalation` → `(high, human_escalation_needed)`; `guest_count_change` → `(medium, guest_count_change)`; `payment_issue` → `(medium, payment_risk)`; `other` → `(medium, unsupported_or_unclear_request)`); `BASELINE_REASON` strings; keyword lists (`URGENCY_TERMS`, `REFUND_TERMS`, `CANCEL_TERMS`, `COMPLAINT_TERMS`, `ESCALATION_TERMS`); guest-count delta threshold; flag-priority order; `UNCLEAR_CONF`; `RULES_VERSION` from `RISK_RULES_VERSION` (depends on T004)
- [ ] T009 Implement `RiskOutcome` dataclass (`level`, `flag`, `reason`, `escalation_recommended`, `rules_version`) and `RiskEngine.assess(*, intent, confidence, body) -> RiskOutcome` in `backend/app/risk/engine.py`: baseline from intent → empty/unclear/low-confidence raise to ≥medium + unclear flag → ordered keyword modifiers that **only raise** level (`max` over ordered `low<medium<high`) → guest-count magnitude parse (`from X to Y`) → compound/escalation handling → primary flag by priority → `escalation_recommended = (level==high) or (flag==human_escalation_needed)` → `reason` composed from matched clauses → stamp `RULES_VERSION`. Pure, no DB/I/O, deterministic. Also define `FAILED_OUTCOME` (medium / unclear / "assessment failed") (depends on T008)

### Unit Tests for the Rule Engine

- [ ] T010 [P] Write `backend/tests/unit/test_risk_engine.py`: each intent baseline maps to the expected level/flag (AC-02 basis); `urgent_change`/`complaint`/`cancellation_request`/`human_escalation` → high + correct flag (AC-03); guest-count small→medium vs large-delta→high (AC-04); payment neutral→medium vs "paid but unconfirmed"/refund→high (AC-05); `other`/empty/low-confidence → medium + `unsupported_or_unclear_request` (AC-06); `escalation_recommended` true for high, false for low (AC-07); **no-lower guarantee** — high-intent + benign body stays high (AC-18); determinism (same input → same outcome); `rules_version` stamped; non-empty `reason` always (depends on T009)

**Checkpoint**: Rule engine produces correct, deterministic outcomes for every intent + modifier; unit tests pass without any DB.

---

## Phase 4: Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service, endpoints, and surfacing tasks.

- [ ] T011 Add Pydantic models to `backend/app/schemas/risk.py` (alongside the enums from T004): `RiskAssessmentResponse` (`message_id`, `level`, `flag`, `reason`, `escalation_recommended`, `rules_version`, `status`, `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`; `from_attributes=True`), `AssessResponse` (subclass), `AssessRequest` (`force: bool = False`), `RiskReviewRequest` (`level: RiskLevel`, `flag: RiskFlag | None = None`, `reason: str = Field(min_length=1, max_length=500)` — invalid level/flag or reason length → 422), `RiskReviewResponse` (subclass), and `RiskSummary` (`level: RiskLevel | None`, `flag: RiskFlag | None`, `reason: str | None`, `escalation_recommended: bool | None`) for embedding in inbox/detail (depends on T004)

**Checkpoint**: Schemas importable — service and API phases can begin.

---

## Phase 5: User Story 1 — Automatic Risk Assessment After Classification (Priority: P1) 🎯 MVP

**Goal**: After a message is intent-classified, the system automatically assesses risk — one `RiskAssessment` linked one-to-one, tenant-scoped, with a valid `level`, a primary `flag` (or none for clearly-low), a non-empty `reason`, and `escalation_recommended`. Rules raise but never silently lower an intent-implied high. Assessment failure never blocks message creation or classification. `GET`/`POST assess` expose the result; cross-tenant → 403, non-existent → 404, no assessment → 404 `NO_RISK_ASSESSMENT`, not classified → 409 `NOT_CLASSIFIED`, outbound → 409 `NOT_CLASSIFIABLE`.

**Independent Test**: Inject "I want to cancel the booking. Is the deposit refundable?" as Tenant A staff (classified `cancellation_request`) → one `RiskAssessment` linked, level `high`, flag `cancellation_risk`, non-empty reason; no assessment in Tenant B.

### Tests for User Story 1

> Write tests first; confirm they fail before implementing the Phase 5 backend tasks.

- [ ] T012 [US1] Write `test_classified_inbound_gets_one_assessment` (AC-01) in `backend/tests/integration/test_risk.py` — classify → assess → exactly one `RiskAssessment` linked, valid `level`/`flag` enums, non-empty `reason`
- [ ] T013 [P] [US1] Write `test_baseline_intents_map_to_low` (AC-02) in `backend/tests/integration/test_risk.py` — booking/pricing/availability/service → level `low`
- [ ] T014 [P] [US1] Write `test_high_risk_intents_and_flags` (AC-03) in `backend/tests/integration/test_risk.py` — `urgent_change`/`complaint`/`cancellation_request`/`human_escalation` → `high` + matching flag
- [ ] T015 [P] [US1] Write `test_guest_count_medium_vs_high` (AC-04) in `backend/tests/integration/test_risk.py` — small/neutral wording → `medium`; large delta ("from 150 to 220") → `high`, flag `guest_count_change`
- [ ] T016 [P] [US1] Write `test_payment_medium_vs_high` (AC-05) in `backend/tests/integration/test_risk.py` — neutral payment question → `medium`; "paid but unconfirmed"/refund → `high`, flag `payment_risk`
- [ ] T017 [P] [US1] Write `test_other_maps_medium_unclear` (AC-06) in `backend/tests/integration/test_risk.py` — `other` intent → `medium`, flag `unsupported_or_unclear_request`
- [ ] T018 [P] [US1] Write `test_escalation_recommended_by_level` (AC-07) in `backend/tests/integration/test_risk.py` — high → `escalation_recommended true`; low → `false`
- [ ] T019 [P] [US1] Write `test_no_lower_guarantee` (AC-18) in `backend/tests/integration/test_risk.py` — high-intent message with benign body → still `high`
- [ ] T020 [P] [US1] Write `test_assessment_is_tenant_scoped` (AC-08) in `backend/tests/integration/test_risk.py` — assess in Tenant A; `GET` as Tenant B → 403 `CROSS_TENANT_FORBIDDEN`, no data
- [ ] T021 [P] [US1] Write `test_get_returns_assessment` (AC-09) in `backend/tests/integration/test_risk.py` — in-tenant assessed message → 200 with all fields correct
- [ ] T022 [P] [US1] Write `test_get_404_when_no_assessment` (AC-10) in `backend/tests/integration/test_risk.py` — assessed-less message → 404 `NO_RISK_ASSESSMENT`
- [ ] T023 [P] [US1] Write `test_post_assess_runs_and_409_when_not_classified` (AC-11) in `backend/tests/integration/test_risk.py` — `POST` with classification → 200 + result; `POST` without classification → 409 `NOT_CLASSIFIED`
- [ ] T024 [P] [US1] Write `test_post_assess_outbound_returns_409` in `backend/tests/integration/test_risk.py` — `POST` on outbound message → 409 `NOT_CLASSIFIABLE`
- [ ] T025 [P] [US1] Write `test_assessment_failure_does_not_block_message_or_classification` (FR-014) in `backend/tests/integration/test_risk.py` — simulate engine exception → message + classification intact, message shown "not assessed", no crash
- [ ] T026 [P] [US1] Write `test_risk_produces_no_side_effects` (AC-16) in `backend/tests/integration/test_risk.py` — assert no task/escalation/reply/RAG records or calls result from risk assessment
- [ ] T027 [P] [US1] Write `test_message_not_found_returns_404` in `backend/tests/integration/test_risk.py` — random UUID on `GET`/`POST` → 404 `MESSAGE_NOT_FOUND`

### Backend Implementation for User Story 1

- [ ] T028 [US1] Implement `_resolve_message_or_raise(session, tenant_id, message_id)` (fetch message by id → `None` → `NotFoundError`; tenant mismatch → `ForbiddenError`, mirroring Specs 005/006), `_get_classification`, `_get_for_message`, and `_upsert` helpers in `backend/app/services/risk_service.py` (depends on T005, T006)
- [ ] T029 [US1] Implement `assess_message(session, message) -> RiskAssessment | None` in `backend/app/services/risk_service.py`: return `None` if `direction != inbound`; load classification → `None` → return `None` (auto path skips until classified); skip (return existing) if existing status is `reviewed`; `try` `engine.assess(intent, confidence, body)` → `status=assessed`; `except Exception` → `FAILED_OUTCOME` + `status=failed`; `_upsert`. Helper never raises into the caller (depends on T009, T028)
- [ ] T030 [US1] Implement `get_risk_assessment(session, tenant_id, message_id) -> RiskAssessment` in `backend/app/services/risk_service.py`: resolve message (404/403) → return assessment or raise `NoRiskAssessmentError` (404 `NO_RISK_ASSESSMENT`) (depends on T028)
- [ ] T031 [US1] Implement the `POST /risk-assessment` service path in `backend/app/services/risk_service.py`: resolve message (404/403); reject outbound → `NotClassifiableError` (409); require a classification → raise `NotClassifiedError` (409 `NOT_CLASSIFIED`) if none; honor `force` (preserve a `reviewed` row unchanged when `force=false`, overwrite when `force=true`); run engine + upsert; return result (depends on T029, T028)
- [ ] T032 [US1] Implement `GET /api/messages/{message_id}/risk-assessment` and `POST /api/messages/{message_id}/risk-assessment` routes in `backend/app/api/v1/risk.py` with `require_role(staff, manager)`, `tenant_id` from `get_current_tenant_context`, UUID path param (422 on malformed), `AssessRequest` body for POST; error→HTTP mapping: `NotFoundError`→404 `MESSAGE_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN`, `NoRiskAssessmentError`→404 `NO_RISK_ASSESSMENT`, `NotClassifiableError`→409 `NOT_CLASSIFIABLE`, `NotClassifiedError`→409 `NOT_CLASSIFIED` (depends on T030, T031)
- [ ] T033 [US1] Mount the risk router at `/api/v1` in `backend/app/main.py` (depends on T032)
- [ ] T034 [US1] Chain fail-safe auto-assessment after Spec 006 classification: in `backend/app/services/classification_service.py`, after `classify_message()` succeeds for an inbound message, call `assess_message()` inside a `try/except` that logs and swallows any error (FR-014) — message creation and classification must always succeed (depends on T029)

**Checkpoint**: US1 functional — classified inbound messages auto-assess (tenant-scoped, baseline+modifiers, fail-safe); `GET`/`POST assess` work with full error matrix; tests pass.

---

## Phase 6: User Story 2 — View Risk in Inbox and Detail Page (Priority: P1)

**Goal**: A colour-coded risk badge (low=muted, medium=amber, high=red) appears on each inbox row; the detail page shows level + primary flag + reason + an "escalation recommended" indicator (replacing the Spec 005 "Risk / Sentiment" placeholder). High-risk/escalation-recommended messages are emphasised; not-assessed shows a neutral "pending" indicator.

**Independent Test**: Assess a `complaint` message (high) → inbox shows a red/high badge; detail shows level `high`, flag `complaint`, reason. A `pricing_request` (low) → muted/low badge.

### Backend Surfacing (no N+1)

- [ ] T035 [US2] Extend `get_inbox()` (Spec 004 `inbox_service.py`) to include a `risk: RiskSummary | None` per inbox item (level, flag, reason, escalation_recommended), tenant-scoped via the message; `null` when not assessed; use an eager join/load to avoid N+1 — sits alongside the Spec 006 `classification` summary (depends on T005, T011)
- [ ] T036 [US2] Extend `get_conversation_detail()` (Spec 005 `conversation_service.py`) so each item in `messages[]` includes the same `risk: RiskSummary | None` object (alongside `classification`) (depends on T005, T011)
- [ ] T037 [P] [US2] Write `test_inbox_response_includes_risk_summary` and `test_detail_response_includes_risk_summary` in `backend/tests/integration/test_risk.py` — assert the compact `risk` block appears (and is `null` for not-assessed messages) and remains tenant-scoped (depends on T035, T036)

### Frontend Implementation for User Story 2

- [ ] T038 [P] [US2] Create `frontend/src/types/risk.ts` with `RiskLevel`, `RiskFlag`, `RiskAssessmentStatus`, `RiskAssessment`, and `RiskSummary` TS types mirroring the backend
- [ ] T039 [P] [US2] Create `frontend/src/api/risk.ts` typed client using the existing auth token interceptor: `getRiskAssessment(messageId)`, `assessMessage(messageId, force?)`, `reviewRiskAssessment(messageId, payload)` (depends on T038)
- [ ] T040 [US2] Create `RiskBadge` component in `frontend/src/components/risk/RiskBadge.tsx`: colour-coded by level (low=muted, medium=amber, high=red) + optional flag label; distinct "not assessed / pending" state for `null`; shadcn `Badge` (depends on T038)
- [ ] T041 [US2] Render `RiskBadge` on each inbox row in `frontend/src/components/inbox/InboxItem.tsx` (and/or `InboxPage`) using the `risk` summary now in the inbox response; emphasise high-risk rows; show "pending" when `null` (depends on T040)
- [ ] T042 [US2] Create `RiskPanel` in `frontend/src/components/risk/RiskPanel.tsx` showing level + primary flag + reason + an "escalation recommended" indicator (informational only — no action), with loading/null(not-assessed)/failed states; reviewed shows reviewer (depends on T040)
- [ ] T043 [US2] Replace the Spec 005 "Risk / Sentiment" placeholder panel with `RiskPanel` in `frontend/src/pages/ConversationDetailPage.tsx`, driven by each message's `risk` summary; the other placeholder panels remain unchanged (depends on T042)

**Checkpoint**: US1 + US2 functional — risk visible as colour-coded inbox badge and detail panel; high emphasised; not-assessed neutral; escalation shown as recommendation only.

---

## Phase 7: User Story 3 — Human Review and Correction (Priority: P2)

**Goal**: Staff/manager can correct a risk assessment's level, primary flag, and reason; the result becomes `reviewed`, recomputes `escalation_recommended` from the corrected level/flag, records `reviewed_by` + `reviewed_at`. Invalid level/flag or out-of-range reason → 422 (unchanged). The auto path never overwrites a `reviewed` row. Cross-tenant/admin blocked.

**Independent Test**: Take a `medium`/`unsupported_or_unclear_request` message; submit a review setting level `high`, flag `complaint`, with a reason → stored assessment updated, `status reviewed`, reviewer + time recorded; inbox/detail reflect the correction.

### Tests for User Story 3

- [ ] T044 [P] [US3] Write `test_review_updates_and_records_reviewer` (AC-12) in `backend/tests/integration/test_risk.py` — `PATCH review` with valid level/flag/reason → fields updated, `escalation_recommended` recomputed, `status reviewed`, `reviewed_by`+`reviewed_at` set
- [ ] T045 [P] [US3] Write `test_review_invalid_level_or_flag_rejected_422` (AC-13) in `backend/tests/integration/test_risk.py` — invalid level ("critical"), invalid flag, and out-of-range reason each → 422; stored assessment unchanged
- [ ] T046 [P] [US3] Write `test_auto_path_does_not_overwrite_reviewed` (AC-14) in `backend/tests/integration/test_risk.py` — review → `POST assess` (force=false) → reviewed result preserved unchanged
- [ ] T047 [P] [US3] Write `test_review_cross_tenant_rejected` in `backend/tests/integration/test_risk.py` — review a Tenant A message as Tenant B → 403/404 per SR-04, no change
- [ ] T048 [P] [US3] Write `test_force_assess_overwrites_reviewed` in `backend/tests/integration/test_risk.py` — `POST assess` with `force=true` on a reviewed row → overwrites with new engine result

### Implementation for User Story 3

- [ ] T049 [US3] Implement `review_risk_assessment(session, tenant_id, user, message_id, level, flag, reason) -> RiskAssessment` in `backend/app/services/risk_service.py`: resolve message (404/403); load assessment or raise `NoRiskAssessmentError` (404); set `level`/`flag`/`reason`; recompute `escalation_recommended = (level==high) or (flag==human_escalation_needed)`; set `status=reviewed`, `reviewed_by=user.id`, `reviewed_at=now`; commit; return (depends on T028)
- [ ] T050 [US3] Implement `PATCH /api/messages/{message_id}/risk-assessment/review` route in `backend/app/api/v1/risk.py` with `require_role(staff, manager)`, `RiskReviewRequest` body (invalid level/flag/reason → 422), tenant from JWT, calling `review_risk_assessment`; same error→HTTP mapping as T032 (depends on T049, T032)
- [ ] T051 [US3] Create `RiskReviewControl` component in `frontend/src/components/risk/RiskReviewControl.tsx`: level `Select` + flag `Select` (seven flags + none) + reason input + confirm button calling `reviewRiskAssessment`; visible to staff/manager; optimistic update + error handling; clears high-risk emphasis change on success (depends on T039, T042)
- [ ] T052 [US3] Wire `RiskReviewControl` into `RiskPanel` so an assessment can be corrected from the detail page; refresh the displayed level/flag/reason/status after success (depends on T051, T043)

**Checkpoint**: US1 + US2 + US3 functional — full assess → display → review loop; reviewed assessments protected from auto-overwrite.

---

## Phase 8: Frontend Tests

**Purpose**: Cover the inbox badge, detail panel, states, escalation-recommendation display, and review control (AC-17).

- [ ] T053 [P] Write `RiskBadge` render tests in `frontend/src/components/risk/RiskBadge.test.tsx` — colour-coded badge per level (low/medium/high); high emphasised; `null` shows "not assessed / pending" (AC-17)
- [ ] T054 [P] Write inbox-integration test in `frontend/src/components/inbox/InboxItem.test.tsx` — a row with a `risk` summary renders the `RiskBadge` with the correct level/colour (AC-17)
- [ ] T055 [P] Write detail `RiskPanel` test in `frontend/src/components/risk/RiskPanel.test.tsx` — renders level + flag + reason; "escalation recommended" indicator shows as **recommendation only** (no action/network triggered); loading/null/failed states render correctly (AC-17)
- [ ] T056 [P] Write `RiskReviewControl` test in `frontend/src/components/risk/RiskReviewControl.test.tsx` — selecting level/flag + reason and confirming calls `reviewRiskAssessment` and updates the displayed risk/status; error path surfaces an error without losing the prior values

**Checkpoint**: Frontend behavior verified for badge, panel, states, escalation-as-recommendation, and review.

---

## Phase 9: Tenant Isolation & Role Security (cross-cutting)

**Purpose**: Explicitly assert the security contract across all three endpoints (some overlap with US1/US3 tenant tests; this phase guarantees full coverage).

- [ ] T057 [P] Write `test_platform_admin_blocked_all_risk_endpoints` (AC-15) in `backend/tests/integration/test_risk.py` — platform admin token on `GET`/`POST`/`PATCH` → 403 `INSUFFICIENT_ROLE`
- [ ] T058 [P] Write `test_client_supplied_tenant_cannot_override_ownership` in `backend/tests/integration/test_risk.py` — any client-supplied tenant hint is ignored; tenancy is derived from the JWT and the message's tenant only (SR-01/SR-02)

**Checkpoint**: Platform Admin blocked everywhere; risk-assessment ownership cannot be overridden by client input.

---

## Phase 10: Quickstart & Manual Validation

**Purpose**: End-to-end validation against the running stack using the five demo messages.

- [ ] T059 Run `alembic upgrade head` (applies `create_risk_assessments`); confirm the risk router is mounted and `RISK_RULES_VERSION=rules-v1`
- [ ] T060 [P] Run `pytest backend/tests/unit/test_risk_engine.py -v` and `pytest backend/tests/integration/test_risk.py -v`; confirm all pass (AC-01–AC-16, AC-18)
- [ ] T061 [P] Run the frontend test suite; confirm `RiskBadge`/inbox/`RiskPanel`/`RiskReviewControl` tests pass (AC-17)
- [ ] T062 Execute the `quickstart.md` demo-message flows (each auto-classified then auto-assessed): "Can you send me your wedding package prices?" → `low`; "We need to change the guest count from 150 to 220." → `high` `guest_count_change`; "I want to cancel the booking. Is the deposit refundable?" → `high` `cancellation_risk`; "I paid the deposit but no one confirmed." → `medium`/`high` `payment_risk`; "I am very unhappy with the decoration sample and the wedding is next week." → `high` `complaint`. Note any mismatch
- [ ] T063 [P] Validate the supporting flows from quickstart: manual re-assess (200, status stays `assessed`); assess before classification → 409 `NOT_CLASSIFIED`; human review → `reviewed`; invalid level → 422; reviewed protected from auto-overwrite; cross-tenant 403; platform admin 403
- [ ] T064 Frontend manual check (quickstart "See It in the UI"): inbox shows colour-coded risk badge next to the Spec 006 intent badge (high emphasised); detail "Risk / Sentiment" panel shows level + flag + reason + escalation-recommended indicator (other placeholders still "coming soon"); review control updates the badge/panel and sets status "reviewed"
- [ ] T065 Only if T062–T064 reveal a doc mismatch: update `quickstart.md` to match implemented behavior (do not modify other features' specs)

**Checkpoint**: Feature validated end-to-end against quickstart and the five demo messages.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Database & Models (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **Rule Engine (Phase 3)**: Depends on enums (T004) — pure, testable in isolation — **BLOCKS US1**
- **Schemas (Phase 4)**: Depends on enums (T004)
- **US1 (Phase 5)**: Depends on Phases 2–4 and the Spec 006 classification hook (T034) — core assessment + GET/POST endpoints
- **US2 (Phase 6)**: Depends on the model + schemas (T005, T011) for surfacing; frontend depends on the response extensions (T035, T036)
- **US3 (Phase 7)**: Depends on US1 service helpers (T028) + API router (T032); frontend depends on `RiskPanel` (T042)
- **Frontend Tests (Phase 8)**: Depend on the frontend components (T040–T043, T051–T052)
- **Security (Phase 9)**: Depends on all three endpoints (T032, T050)
- **Quickstart & Validation (Phase 10)**: Depends on all prior phases

### Within Each Story

- Tests written (and confirmed failing) before the corresponding backend implementation
- Enums → rule data → engine → unit tests; model → migration; enums → schemas; engine + helpers → service → endpoint → router mount → chain hook
- Frontend: types → API client → `RiskBadge`/`RiskPanel` → inbox/detail integration → `RiskReviewControl`

### Parallel Opportunities

- T004 (enums) unblocks both T008 (rules) and T011 (schemas) in parallel branches
- T012–T027 (US1 tests) can run in parallel with each other (same file, distinct functions)
- T038 (types) → T039 (API client) feed parallel component work
- T044–T048 (US3 tests) can run in parallel
- T053–T056 (frontend tests) can run in parallel
- T057–T058 (security tests) can run in parallel
- T060 and T061 (test-suite runs) can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Run US1 integration tests in parallel (same file, different test functions):
Task T013: test_baseline_intents_map_to_low
Task T014: test_high_risk_intents_and_flags
Task T015: test_guest_count_medium_vs_high
Task T016: test_payment_medium_vs_high
Task T017: test_other_maps_medium_unclear
Task T018: test_escalation_recommended_by_level
Task T019: test_no_lower_guarantee
Task T020: test_assessment_is_tenant_scoped
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Phase 1: Setup & spec alignment (config)
2. Phase 2: DB + model + migration (CRITICAL)
3. Phase 3: rule data + engine + unit tests (the core — build/test in isolation first)
4. Phase 4: Schemas
5. Phase 5: US1 — auto-assess, fail-safe chain hook, GET/POST endpoints
6. **STOP and VALIDATE**: run engine unit tests + US1 integration tests; confirm tenant isolation, baseline/modifier behavior, no-lower guarantee, fail-safe chaining
7. Phase 6: US2 — surface badge + detail panel
8. **STOP and VALIDATE**: risk visible in both surfaces — usable triage MVP

### Incremental Delivery

1. Setup + DB + Engine + Schemas → foundation ready
2. US1 → automatic risk assessment + read endpoints (**MVP backend deliverable**)
3. US2 → inbox badge + detail panel (replaces Spec 005 Risk/Sentiment placeholder)
4. US3 → human review/correction loop
5. Security + frontend tests → full coverage
6. Quickstart & validation → all 18 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- Risk detection is a **separate component from the classifier** (FR-004) — the pure engine lives in `backend/app/risk/`, distinct from `backend/app/ml/`; it consumes the stored `ClassificationResult`, never re-runs the model
- `tenant_id` is always derived from the JWT (and, for the auto path, from the message's tenant) — never from client input (SR-01); the assessment inherits the message's tenant (SR-02)
- 404 (message not in tenant) vs 403 (message exists in another tenant) mirrors Specs 005/006 SR-04 via `_resolve_message_or_raise`
- Modifiers are **monotonic raises** over the intent baseline (`max` over ordered `low<medium<high`) — rules never silently lower an intent-implied high (FR-005, AC-18)
- The auto path never overwrites a `reviewed` row (FR-013); manual `POST assess` overwrites a reviewed row only with `force=true`
- Risk assessment is fail-safe: an engine error never fails message creation or classification (FR-014) — the chain hook swallows and logs; a `failed` status row may be recorded
- The engine takes **no** action — `escalation_recommended` and the `human_escalation_needed` flag are informational only; **no** task/escalation/reply/RAG side effects (FR-006, FR-007, AC-16). Acting on a recommendation is the separate, human-reviewed escalation feature
- `POST assess` requires an existing classification → 409 `NOT_CLASSIFIED`; outbound → 409 `NOT_CLASSIFIABLE`
- Enums persist as constrained strings (VARCHAR + app validation), not native PG enums, for rule evolvability; every assessment stamps `rules_version`
- Audit logging of risk actions is deferred to the later audit-log feature (013); this feature builds no audit system
