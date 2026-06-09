---

description: "Task list for Intent Classifier feature implementation"
---

# Tasks: Intent Classifier

**Branch**: `006-intent-classifier` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/006-intent-classifier/`

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `messages` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager` roles; `require_role`; `get_current_tenant_context`; Platform Admin block; `users` table
- Spec 003 — Message Simulator: inbound message creation path (the classification hook point); `MessageDirection` (`inbound`/`outbound`)
- Spec 004 — Message Inbox: `get_inbox()` inbox-item response (extended here with a `classification` summary)
- Spec 005 — Message Detail Page: `get_conversation_detail()` message response (extended here) + the "AI Intent" placeholder panel (replaced here)

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 + scikit-learn/joblib (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `classification_results` (one-to-one with `messages`) + one Alembic migration. Persisted as constrained-string enums (not native PG enums).

**Config defaults** (research): `INTENT_MODEL_PATH=backend/models/intent/`, `INTENT_MODEL_VERSION=tfidf-logreg-v1`, `INTENT_CONFIDENCE_THRESHOLD=0.45` (`>=` is confident), `INTENT_MAX_CHARS=2000`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Artifact Review

**Purpose**: Confirm reused 001–005 dependencies, define config + model-artifact path, and decide fallback behavior when the artifact is missing. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Message` model + `MessageDirection` enum (Spec 003), `User` model (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `NotFoundError`/`ForbiddenError` (Spec 001), `get_inbox()` (Spec 004), `get_conversation_detail()` (Spec 005). Do NOT redefine any of these.
- [ ] T002 Add `INTENT_MODEL_PATH`, `INTENT_MODEL_VERSION` (`tfidf-logreg-v1`), `INTENT_CONFIDENCE_THRESHOLD` (`0.45`), `INTENT_MAX_CHARS` (`2000`) settings in `backend/app/core/config.py` with documented defaults
- [ ] T003 Verify `backend/tests/integration/` and `backend/tests/unit/` exist with `__init__.py`; create if absent (required before test files in later phases)
- [ ] T004 Confirm the model-artifact contract and fallback: artifact bundle lives at `INTENT_MODEL_PATH` (`vectorizer.joblib`, `model.joblib`, `labels.json`, `meta.json`); document that a missing/corrupt artifact marks the model unavailable (auto-classify skipped, `POST /classify` → 503 `MODEL_UNAVAILABLE`, message creation unaffected). Add `backend/models/intent/` to `.gitignore` if large; a small demo artifact is generated in Phase 3 (T011).

**Checkpoint**: Dependencies confirmed reused; config + artifact path + fallback policy defined.

---

## Phase 2: Database & Models (Foundational — Blocking)

**Purpose**: The `classification_results` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–7 cannot run without this phase.

- [ ] T005 Create `ClassificationResult` SQLAlchemy model in `backend/app/models/classification.py`: `id` UUID PK; `message_id` UUID FK→`messages.id` UNIQUE `ON DELETE CASCADE`; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `label` VARCHAR(40); `confidence` Float nullable; `model_version` VARCHAR(64); `status` VARCHAR(20); `reviewed_by` UUID FK→`users.id` nullable; `reviewed_at` TIMESTAMPTZ nullable; `created_at`/`updated_at` TIMESTAMPTZ; `Index("ix_classification_tenant_status", "tenant_id", "status")` and `Index("ix_classification_tenant_label", "tenant_id", "label")`; `message` relationship `back_populates="classification"`
- [ ] T006 Add the inverse relationship on `Message` in the Spec 001/003 messages model: `classification: Mapped["ClassificationResult | None"] = relationship(back_populates="message", uselist=False, cascade="all, delete-orphan")` (depends on T005)
- [ ] T007 Create Alembic migration `backend/alembic/versions/00xx_create_classification_results.py` creating `classification_results` with all columns, the UNIQUE constraint on `message_id` (FK CASCADE), the `tenant_id` FK, and both composite indexes; provide a correct `downgrade()` dropping the table (depends on T005)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable.

---

## Phase 3: ML Layer (Foundational — Blocking)

**Purpose**: The classifier wrapper + loader provide the deterministic `predict(text) -> (label, confidence)` interface the service depends on. **BLOCKS US1.**

- [ ] T008 Implement `ClassifierModel` in `backend/app/ml/classifier_model.py`: loads `vectorizer.joblib`, `model.joblib`, `labels.json`, `meta.json` from `INTENT_MODEL_PATH`; `predict(text) -> (IntentLabel, float)` that normalises (`(text or "").strip().lower()[:INTENT_MAX_CHARS]`), short-circuits empty → `(IntentLabel.other, 0.0)`, else `vectorizer.transform` → `predict_proba` → argmax label + top probability; deterministic, read-only (depends on T002, schemas enum T012)
- [ ] T009 Implement loader/singleton in `backend/app/ml/loader.py`: load the artifact once at startup into a module singleton; `is_loaded()` health check; raise typed `ModelUnavailable` when the artifact is absent/corrupt; expose `get_model()` used by the service
- [ ] T010 Wire model load into startup in `backend/app/main.py`: attempt load on startup, log `intent model loaded: <model_version>` on success, log a warning and continue (app stays up) on failure (depends on T009)
- [ ] T011 [P] Implement `backend/app/ml/train_demo.py`: a small script that fits a `TfidfVectorizer` + `LogisticRegression` on a tiny built-in labelled sample covering all eleven labels and writes `vectorizer.joblib`, `model.joblib`, `labels.json`, `meta.json` (`model_version=tfidf-logreg-v1`) to `INTENT_MODEL_PATH`, so the feature is testable locally (training pipeline itself is out of scope)
- [ ] T012 [P] Create `IntentLabel` (eleven values) and `ClassificationStatus` (`classified`/`needs_review`/`reviewed`/`failed`) string enums in `backend/app/schemas/classification.py` (shared by the model, service, and API layers)

### Unit Tests for the ML Layer

- [ ] T013 [P] Write `backend/tests/unit/test_classifier_model.py`: deterministic output (same input → same label+confidence); bounded input (very long body truncated to `INTENT_MAX_CHARS`, no error); empty/whitespace body → `(other, 0.0)`; `predict` returns a valid `IntentLabel` and confidence in `[0,1]`; `model_version` reads from `meta.json` (depends on T008, T011)

**Checkpoint**: `python -m app.ml.train_demo` produces an artifact; `ClassifierModel.predict()` works deterministically; unit tests pass.

---

## Phase 4: Schemas (Foundational — Blocking)

**Purpose**: Pydantic response/request models shared by the service, endpoints, and surfacing tasks.

- [ ] T014 Add Pydantic models to `backend/app/schemas/classification.py` (alongside the enums from T012): `ClassificationResultResponse` (`message_id`, `label`, `confidence`, `model_version`, `status`, `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`; `from_attributes=True`), `ClassifyResponse` (subclass), `ClassifyRequest` (`force: bool = False`), `ReviewRequest` (`label: IntentLabel` — Enum coercion rejects invalid → 422), `ReviewResponse` (subclass), and `ClassificationSummary` (`label: IntentLabel | None`, `confidence: float | None`, `status: ClassificationStatus | None`) for embedding in inbox/detail (depends on T012)

**Checkpoint**: Schemas importable — service and API phases can begin.

---

## Phase 5: User Story 1 — Automatic Classification of Incoming Messages (Priority: P1) 🎯 MVP

**Goal**: Every new **inbound** message is automatically classified into one of eleven labels with a confidence in `[0,1]`, stored one-to-one and tenant-scoped, immediately after creation. Confidence ≥ threshold → predicted label + `classified`; below → `other` + `needs_review`. Outbound messages are never classified. Classifier failure never blocks message creation. `GET`/`POST classify` expose the stored result; cross-tenant → 403, non-existent → 404, no classification → 404 `NO_CLASSIFICATION`, model down → 503.

**Independent Test**: Inject "How much does your gold wedding package cost?" as Tenant A staff → one `ClassificationResult` linked, label `pricing_request`, confidence in `[0,1]`; no result in Tenant B.

### Tests for User Story 1

> Write tests first; confirm they fail before implementing the Phase 5 backend tasks.

- [ ] T015 [US1] Write `test_inbound_message_gets_one_classification` (AC-01) in `backend/tests/integration/test_classification.py` — create inbound message → exactly one `ClassificationResult` linked, `label` in enum, `0 <= confidence <= 1`
- [ ] T016 [P] [US1] Write `test_high_confidence_stores_predicted_label_classified` (AC-02) in `backend/tests/integration/test_classification.py` — high-confidence message → `label == predicted`, `status == classified`
- [ ] T017 [P] [US1] Write `test_low_confidence_stores_other_needs_review` (AC-03) in `backend/tests/integration/test_classification.py` — force confidence below threshold → `label == other`, `status == needs_review`
- [ ] T018 [P] [US1] Write `test_outbound_message_not_classified` (AC-04) in `backend/tests/integration/test_classification.py` — create outbound message → no `ClassificationResult`
- [ ] T019 [P] [US1] Write `test_classification_is_tenant_scoped` (AC-05) in `backend/tests/integration/test_classification.py` — classify in Tenant A; `GET` as Tenant B → 403 `CROSS_TENANT_FORBIDDEN`, no data
- [ ] T020 [P] [US1] Write `test_get_classification_returns_result` (AC-06) in `backend/tests/integration/test_classification.py` — in-tenant classified message → 200 with all fields correct
- [ ] T021 [P] [US1] Write `test_get_returns_404_when_no_classification` (AC-07) in `backend/tests/integration/test_classification.py` — message with no classification → 404 `NO_CLASSIFICATION`
- [ ] T022 [P] [US1] Write `test_post_classify_runs_and_overwrites_model_result` (AC-08) in `backend/tests/integration/test_classification.py` — `POST /classify` → 200 + result; re-run overwrites the model result
- [ ] T023 [P] [US1] Write `test_classify_outbound_returns_409` in `backend/tests/integration/test_classification.py` — `POST /classify` on outbound message → 409 `NOT_CLASSIFIABLE`
- [ ] T024 [P] [US1] Write `test_classify_model_unavailable_returns_503` in `backend/tests/integration/test_classification.py` — model marked unavailable → `POST /classify` → 503 `MODEL_UNAVAILABLE`
- [ ] T025 [P] [US1] Write `test_classifier_failure_does_not_block_message_creation` (AC-14) in `backend/tests/integration/test_classification.py` — simulate classifier exception → message still created, no crash, message is "unclassified"
- [ ] T026 [P] [US1] Write `test_classifier_produces_no_side_effects` (AC-15) in `backend/tests/integration/test_classification.py` — assert no task/escalation/reply/RAG records or calls result from classification
- [ ] T027 [P] [US1] Write `test_message_not_found_returns_404` in `backend/tests/integration/test_classification.py` — random UUID on `GET`/`POST` → 404 `MESSAGE_NOT_FOUND`

### Backend Implementation for User Story 1

- [ ] T028 [US1] Implement `classify_message(session, message) -> ClassificationResult | None` in `backend/app/services/classification_service.py`: return `None` if `direction != inbound`; skip (return existing) if existing status is `reviewed`; `try` model `predict()` → apply `INTENT_CONFIDENCE_THRESHOLD` (`>=` confident → `classified`; else `other`+`needs_review`); `except ModelUnavailable` → return `None`; `except Exception` → `(other, None, failed)`; `_upsert` row stamping `model_version`. Helper never raises into the caller (depends on T005, T009, T014)
- [ ] T029 [US1] Implement `_resolve_message_or_raise(session, tenant_id, message_id)` (fetch message by id → `None` → `NotFoundError`; tenant mismatch → `ForbiddenError`, mirroring Spec 005), `_get_for_message`, and `_upsert` helpers in `backend/app/services/classification_service.py` (depends on T005)
- [ ] T030 [US1] Implement `get_classification(session, tenant_id, message_id) -> ClassificationResult` in `backend/app/services/classification_service.py`: resolve message (404/403) → return classification or raise `NoClassificationError` (404 `NO_CLASSIFICATION`) (depends on T029)
- [ ] T031 [US1] Implement the `POST /classify` service path: resolve message (404/403); reject outbound → `NotClassifiableError` (409); if model unavailable → raise `ModelUnavailable` (503); honor `force` (preserve a `reviewed` row unchanged when `force=false`, overwrite when `force=true`); run + upsert; return result, in `backend/app/services/classification_service.py` (depends on T028, T029)
- [ ] T032 [US1] Implement `GET /api/messages/{message_id}/classification` and `POST /api/messages/{message_id}/classify` routes in `backend/app/api/v1/classification.py` with `require_role(staff, manager)`, `tenant_id` from `get_current_tenant_context`, UUID path param (422 on malformed), `ClassifyRequest` body for POST; error→HTTP mapping: `NotFoundError`→404 `MESSAGE_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN`, `NoClassificationError`→404 `NO_CLASSIFICATION`, `NotClassifiableError`→409 `NOT_CLASSIFIABLE`, `ModelUnavailable`→503 `MODEL_UNAVAILABLE` (depends on T030, T031)
- [ ] T033 [US1] Mount the classification router at `/api/v1` in `backend/app/main.py` (depends on T032)
- [ ] T034 [US1] Hook fail-safe auto-classification into the Spec 003 inbound message-creation path: after the inbound message is committed, call `classify_message()` inside a `try/except` that logs and swallows any error (FR-012) — message creation must always succeed (depends on T028)

**Checkpoint**: US1 functional — inbound messages auto-classify (tenant-scoped, threshold-routed, fail-safe); `GET`/`POST classify` work with full error matrix; tests pass.

---

## Phase 6: User Story 2 — View Intent in Inbox and Detail Page (Priority: P1)

**Goal**: The intent label appears as a badge on each inbox row and as a label + confidence on the message detail page (replacing the Spec 005 "AI Intent" placeholder). Needs-review classifications are visually distinct; unclassified/pending shows a neutral indicator rather than a wrong label.

**Independent Test**: Classify a message as `complaint` → inbox shows a `complaint` badge; detail shows `complaint` + confidence. A low-confidence message shows an `other`/"needs review" indicator in both surfaces.

### Backend Surfacing (no N+1)

- [ ] T035 [US2] Extend `get_inbox()` (Spec 004 `inbox_service.py`) to include a `classification: ClassificationSummary | None` per inbox item (label, confidence, status), tenant-scoped via the message; `null` when unclassified — use an eager join/load to avoid N+1 (depends on T005, T014)
- [ ] T036 [US2] Extend `get_conversation_detail()` (Spec 005 `conversation_service.py`) so each item in `messages[]` includes the same `classification: ClassificationSummary | None` object (depends on T005, T014)
- [ ] T037 [P] [US2] Write `test_inbox_response_includes_classification_summary` and `test_detail_response_includes_classification_summary` in `backend/tests/integration/test_classification.py` — assert the compact `classification` block appears (and is `null` for unclassified messages) and remains tenant-scoped (depends on T035, T036)

### Frontend Implementation for User Story 2

- [ ] T038 [P] [US2] Create `frontend/src/types/classification.ts` with `IntentLabel`, `ClassificationStatus`, `ClassificationResult`, and `ClassificationSummary` TS types mirroring the backend
- [ ] T039 [P] [US2] Create `frontend/src/api/classification.ts` typed client using the existing auth token interceptor: `getClassification(messageId)`, `classifyMessage(messageId, force?)`, `reviewClassification(messageId, label)` (depends on T038)
- [ ] T040 [US2] Create `IntentBadge` component in `frontend/src/components/classification/IntentBadge.tsx`: maps each `IntentLabel` to a colour + display text; distinct visuals for `needs_review` and for `null`/unclassified ("pending"); shadcn `Badge` (depends on T038)
- [ ] T041 [US2] Render `IntentBadge` on each inbox row in `frontend/src/components/inbox/InboxItem.tsx` (and/or `InboxPage`) using the `classification` summary now in the inbox response; show "unclassified/pending" when `null` (depends on T040)
- [ ] T042 [US2] Create `IntentPanel` in `frontend/src/components/classification/IntentPanel.tsx` showing label + confidence + review state (needs-review highlighted, reviewed shows reviewer), with loading/null/model-unavailable messaging (depends on T040)
- [ ] T043 [US2] Replace the Spec 005 "AI Intent" placeholder panel with `IntentPanel` in `frontend/src/pages/ConversationDetailPage.tsx`, driven by each message's `classification` summary; the other five placeholder panels remain unchanged (depends on T042)

**Checkpoint**: US1 + US2 functional — intent visible as inbox badge and detail panel; needs-review distinct; unclassified neutral.

---

## Phase 7: User Story 3 — Human Review and Correction (Priority: P2)

**Goal**: Staff/manager can correct or confirm a classification's label; the result becomes `reviewed`, records `reviewed_by` + `reviewed_at`, and clears the needs-review flag. Invalid labels → 422 (unchanged). The auto path never overwrites a `reviewed` row. Cross-tenant/admin blocked.

**Independent Test**: Take an `other`/`needs_review` message; submit a review setting `pricing_request` → stored label `pricing_request`, `status reviewed`, reviewer + time recorded; inbox/detail reflect the corrected label with no needs-review flag.

### Tests for User Story 3

- [ ] T044 [P] [US3] Write `test_review_updates_label_sets_reviewed_records_reviewer` (AC-09) in `backend/tests/integration/test_classification.py` — `PATCH review` with valid label → label updated, `status reviewed`, `reviewed_by`+`reviewed_at` set; needs-review flag cleared
- [ ] T045 [P] [US3] Write `test_review_invalid_label_rejected_422_no_change` (AC-10) in `backend/tests/integration/test_classification.py` — `PATCH` bad label → 422; stored classification unchanged
- [ ] T046 [P] [US3] Write `test_auto_path_does_not_overwrite_reviewed` (AC-12) in `backend/tests/integration/test_classification.py` — review a message → `POST /classify` (force=false) → reviewed label preserved unchanged
- [ ] T047 [P] [US3] Write `test_review_cross_tenant_rejected` in `backend/tests/integration/test_classification.py` — review a Tenant A message as Tenant B → 403/404 per SR-04, no change
- [ ] T048 [P] [US3] Write `test_force_classify_overwrites_reviewed` in `backend/tests/integration/test_classification.py` — `POST /classify` with `force=true` on a reviewed row → overwrites with new model result

### Implementation for User Story 3

- [ ] T049 [US3] Implement `review_classification(session, tenant_id, user, message_id, new_label) -> ClassificationResult` in `backend/app/services/classification_service.py`: resolve message (404/403); load classification or raise `NoClassificationError` (404); set `label`, `status=reviewed`, `reviewed_by=user.id`, `reviewed_at=now`; commit; return (depends on T029)
- [ ] T050 [US3] Implement `PATCH /api/messages/{message_id}/classification/review` route in `backend/app/api/v1/classification.py` with `require_role(staff, manager)`, `ReviewRequest` body (invalid label → 422), tenant from JWT, calling `review_classification`; same error→HTTP mapping as T032 (depends on T049, T032)
- [ ] T051 [US3] Create `ReviewControl` component in `frontend/src/components/classification/ReviewControl.tsx`: label `Select` (eleven labels) + confirm button calling `reviewClassification`; visible to staff/manager; optimistic update + error handling; clears needs-review highlight on success (depends on T039, T042)
- [ ] T052 [US3] Wire `ReviewControl` into `IntentPanel` so a needs-review (or any) classification can be corrected from the detail page; refresh the displayed label/status after success (depends on T051, T043)

**Checkpoint**: US1 + US2 + US3 functional — full classify → display → review loop; reviewed labels protected from auto-overwrite.

---

## Phase 8: Frontend Tests

**Purpose**: Cover the inbox badge, detail panel, states, and review control (AC-13).

- [ ] T053 [P] Write `IntentBadge` render tests in `frontend/src/components/classification/IntentBadge.test.tsx` — a badge renders per label; `needs_review` shows the distinct indicator; `null`/unclassified shows "pending" (AC-13)
- [ ] T054 [P] Write inbox-integration test in `frontend/src/components/inbox/InboxItem.test.tsx` — a row with a `classification` summary renders the `IntentBadge` with the correct label (AC-13)
- [ ] T055 [P] Write detail `IntentPanel` test in `frontend/src/components/classification/IntentPanel.test.tsx` — renders label + confidence + status; needs-review highlighted; reviewed shows reviewer; loading/null/model-unavailable states render correctly (AC-13)
- [ ] T056 [P] Write `ReviewControl` test in `frontend/src/components/classification/ReviewControl.test.tsx` — selecting a label and confirming calls `reviewClassification` and updates the displayed label/status; error path surfaces an error without losing the prior label

**Checkpoint**: Frontend behavior verified for badge, panel, states, and review.

---

## Phase 9: Tenant Isolation & Role Security (cross-cutting)

**Purpose**: Explicitly assert the security contract across all three endpoints (some overlaps with US1/US3 tenant tests; this phase guarantees full coverage).

- [ ] T057 [P] Write `test_platform_admin_blocked_all_classification_endpoints` (AC-11) in `backend/tests/integration/test_classification.py` — platform admin token on `GET`/`POST`/`PATCH` → 403 `INSUFFICIENT_ROLE`
- [ ] T058 [P] Write `test_client_supplied_tenant_cannot_override_ownership` in `backend/tests/integration/test_classification.py` — any client-supplied tenant hint is ignored; tenancy is derived from the JWT and the message's tenant only (SR-01/SR-02)

**Checkpoint**: Platform Admin blocked everywhere; classification ownership cannot be overridden by client input.

---

## Phase 10: Quickstart & Manual Validation

**Purpose**: End-to-end validation against the running stack using the sample messages.

- [ ] T059 Build the demo model: `cd backend && python -m app.ml.train_demo`; run `alembic upgrade head`; confirm the startup log shows `intent model loaded: tfidf-logreg-v1`
- [ ] T060 [P] Run `pytest backend/tests/integration/test_classification.py -v` and `pytest backend/tests/unit/test_classifier_model.py -v`; confirm all pass (AC-01–AC-12, AC-14, AC-15)
- [ ] T061 [P] Run the frontend test suite; confirm `IntentBadge`/inbox/`IntentPanel`/`ReviewControl` tests pass (AC-13)
- [ ] T062 Execute the `quickstart.md` flows: seed + auto-classify "How much does your gold wedding package cost?" → `pricing_request`; verify low-confidence "ok 👍" → `other`/`needs_review`; human-review it; invalid label → 422; reviewed label protected from auto-overwrite; outbound not classified (404); cross-tenant 403; platform admin 403
- [ ] T063 [P] Manual classifier sanity check on the documented sample messages: "Can you send me your wedding package prices?" → `pricing_request`; "We need to change the guest count from 150 to 220." → `guest_count_change` (or `urgent_change`); "I want to cancel the booking. Is the deposit refundable?" → `cancellation_request`; "I paid the deposit but no one confirmed." → `payment_issue`; "I want to speak to a manager." → `human_escalation`. Note any mismatch (demo-model accuracy is acceptable for MVP; needs-review routing covers misses)
- [ ] T064 Frontend manual check (quickstart "See It in the UI"): inbox badges render; detail "AI Intent" panel shows real label + confidence (other five panels still "coming soon"); review control updates the badge/panel and clears the needs-review highlight
- [ ] T065 Only if T062–T064 reveal a doc mismatch: update `quickstart.md` to match implemented behavior (do not modify other features' specs)

**Checkpoint**: Feature validated end-to-end against quickstart and sample messages.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Database & Models (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **ML Layer (Phase 3)**: Depends on Phase 1 (config) + enums (T012) — **BLOCKS US1**
- **Schemas (Phase 4)**: Depends on enums (T012)
- **US1 (Phase 5)**: Depends on Phases 2–4 — core classification + auto hook + GET/POST endpoints
- **US2 (Phase 6)**: Depends on the model + schemas (T005, T014) for surfacing; frontend depends on the response extensions (T035, T036)
- **US3 (Phase 7)**: Depends on US1 service helpers (T029) + API router (T032); frontend depends on `IntentPanel` (T042)
- **Frontend Tests (Phase 8)**: Depend on the frontend components (T040–T043, T051–T052)
- **Security (Phase 9)**: Depends on all three endpoints (T032, T050)
- **Quickstart & Validation (Phase 10)**: Depends on all prior phases

### Within Each Story

- Tests written (and confirmed failing) before the corresponding backend implementation
- DB model → migration; enums → schemas; model → service → endpoint → router mount → creation hook
- Frontend: types → API client → `IntentBadge`/`IntentPanel` → inbox/detail integration → `ReviewControl`

### Parallel Opportunities

- T011 (train_demo) and T012 (enums) can run in parallel within Phase 3
- T015–T027 (US1 tests) can run in parallel with each other (same file, distinct functions)
- T038 (types) and T039 (API client, after types) feed parallel component work
- T044–T048 (US3 tests) can run in parallel
- T053–T056 (frontend tests) can run in parallel
- T057–T058 (security tests) can run in parallel
- T060 and T061 (test-suite runs) can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Run US1 integration tests in parallel (same file, different test functions):
Task T015: test_inbound_message_gets_one_classification
Task T016: test_high_confidence_stores_predicted_label_classified
Task T017: test_low_confidence_stores_other_needs_review
Task T018: test_outbound_message_not_classified
Task T019: test_classification_is_tenant_scoped
Task T020: test_get_classification_returns_result
Task T021: test_get_returns_404_when_no_classification
Task T022: test_post_classify_runs_and_overwrites_model_result
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Phase 1: Setup & artifact review (config, fallback policy)
2. Phase 2: DB + model + migration (CRITICAL)
3. Phase 3: ML layer + demo artifact + unit tests
4. Phase 4: Schemas
5. Phase 5: US1 — auto-classify, fail-safe hook, GET/POST endpoints
6. **STOP and VALIDATE**: run US1 tests; confirm tenant isolation, threshold routing, fail-safe creation
7. Phase 6: US2 — surface badge + detail panel
8. **STOP and VALIDATE**: intent visible in both surfaces — usable MVP

### Incremental Delivery

1. Setup + DB + ML + Schemas → foundation ready
2. US1 → automatic classification + read endpoints (**MVP backend deliverable**)
3. US2 → inbox badge + detail panel (replaces Spec 005 AI Intent placeholder)
4. US3 → human review/correction loop
5. Security + frontend tests → full coverage
6. Quickstart & validation → all 15 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` is always derived from the JWT (and, for auto-classify, from the message's tenant) — never from client input (SR-01); classification inherits the message's tenant (SR-02)
- 404 (message not in tenant) vs 403 (message exists in another tenant) mirrors Spec 005 SR-04 via `_resolve_message_or_raise`
- The auto path never overwrites a `reviewed` row (FR-013); manual `POST /classify` overwrites a reviewed row only with `force=true`
- Classification is fail-safe: a classifier error never fails message creation (FR-012) — the hook swallows and logs
- The classifier is a pure labelling function — **no** task/escalation/reply/RAG side effects (FR-011, AC-15); `human_escalation` is a label only, it triggers no escalation here
- Enums persist as constrained strings (VARCHAR + app validation), not native PG enums, for label evolvability
- The demo artifact (`train_demo.py`) makes the feature testable locally; the training pipeline itself is out of scope — only loading + inference + versioning are built here
- Audit logging of classification actions is deferred to the later audit-log feature (013); this feature builds no audit system
