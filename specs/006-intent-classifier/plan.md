# Implementation Plan: Intent Classifier

**Branch**: `006-intent-classifier` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-intent-classifier/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): `messages` table, `tenant_id` isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth, `staff`/`manager` roles, `require_role`, `get_current_tenant_context`
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): inbound message creation path (the classification hook point)
- [Spec 004 — Message Inbox](../004-message-inbox/plan.md): inbox surface for the intent badge
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): detail surface for label + confidence (replaces the "AI Intent" placeholder panel)

---

## Summary

Add a synchronous, tenant-safe intent classification step to the inbound-message creation path. A `ClassificationService` loads a versioned TF-IDF + Logistic Regression artifact once at startup and, for each new inbound message, predicts one of eleven labels with a confidence score. A new `classification_results` table (one row per message, one-to-one) stores `label`, `confidence`, `model_version`, `status`, and review metadata. Three REST endpoints expose the result: `POST /api/messages/{id}/classify` (re-run), `GET /api/messages/{id}/classification` (read), and `PATCH /api/messages/{id}/classification/review` (human correction). Low-confidence predictions are stored as `other` + `needs_review`. Classification failure is isolated so it can never fail message creation. The intent label is surfaced as an inbox badge and replaces the Spec 005 "AI Intent" placeholder on the detail page. No tasks, escalations, replies, or retrieval are produced.

---

## Technical Approach

- **Decoupled, fail-safe hook**: message creation (Spec 003) calls `classify_message()` inside a `try/except` that swallows classifier errors (logs them) so message creation always succeeds. For MVP this runs synchronously in-request; the call site is structured so it can be moved to a background task later without API changes.
- **Model loaded once**: the TF-IDF vectoriser + Logistic Regression model + label index are loaded at application startup into a singleton `ClassifierModel` wrapper. Inference is pure and deterministic (`predict_proba` → argmax → confidence).
- **Threshold → routing**: a configurable `INTENT_CONFIDENCE_THRESHOLD` (default `0.45`, documented in research) decides confident vs `needs_review`. `confidence >= threshold` is confident.
- **One-to-one storage**: `classification_results.message_id` is unique. Re-classification upserts the row, but the auto path refuses to overwrite a `reviewed` row (FR-013).
- **Tenant safety**: every read/write resolves the message first (tenant check → 404/403, consistent with Spec 005), and the classification inherits `tenant_id` from the message.
- **Surfacing**: the inbox list response (Spec 004) and the detail response (Spec 005) are extended with a compact `classification` object so the frontend renders the badge/label without extra round-trips.

---

## Backend Tasks

1. **`schemas/classification.py`** — Pydantic models: `ClassificationResultResponse`, `ClassifyResponse`, `ReviewRequest`, `ReviewResponse`, plus the `IntentLabel` and `ClassificationStatus` string enums (shared with the model layer).
2. **`ml/classifier_model.py`** — `ClassifierModel` wrapper: load artifact (vectoriser, model, label list, `model_version`) from a configured path; `predict(text) -> (label, confidence)`; bounded input length; deterministic.
3. **`ml/loader.py`** — startup loader/singleton + health check (`is_loaded`); raises a typed `ModelUnavailable` when absent.
4. **`services/classification_service.py`**:
   - `classify_message(session, message)` — predict, apply threshold, upsert `ClassificationResult` (skip if existing is `reviewed`), set status, persist. Returns the result. Wrapped to never raise into the message-creation caller.
   - `get_classification(session, tenant_id, message_id)` — tenant-resolve message (404/403), return classification or raise `NoClassification` (404).
   - `review_classification(session, tenant_id, user, message_id, new_label)` — validate label, update label, set `status=reviewed`, record `reviewed_by` + `reviewed_at`.
5. **`api/v1/classification.py`** — three routes with `require_role(staff, manager)` and error→HTTP mapping.
6. **Hook into Spec 003 message creation** — call `classify_message()` after the inbound message is committed, in a fail-safe wrapper.
7. **Extend Spec 004 inbox + Spec 005 detail responses** — include a compact `classification` block (label, confidence, status) per message/conversation.
8. **Config** — add `INTENT_MODEL_PATH`, `INTENT_MODEL_VERSION`, `INTENT_CONFIDENCE_THRESHOLD`, `INTENT_MAX_CHARS` to settings.
9. **Router mount** — register the classification router at `/api/v1` in `main.py`; trigger model load on startup.

---

## Database Tasks

1. **Alembic migration** — create `classification_results`:
   - `id` UUID PK
   - `message_id` UUID FK → `messages.id`, **UNIQUE**, `ON DELETE CASCADE`
   - `tenant_id` UUID (denormalised from message for fast tenant-scoped queries + index)
   - `label` VARCHAR / enum (the eleven `IntentLabel` values)
   - `confidence` DOUBLE PRECISION (NULL allowed for `failed`)
   - `model_version` VARCHAR
   - `status` VARCHAR / enum (`classified`/`needs_review`/`reviewed`/`failed`)
   - `reviewed_by` UUID FK → users (nullable)
   - `reviewed_at` TIMESTAMPTZ (nullable)
   - `created_at`, `updated_at` TIMESTAMPTZ
2. **Indexes**: unique on `message_id`; index on `(tenant_id, status)` for needs-review queries; index on `(tenant_id, label)` for future analytics.
3. **SQLAlchemy model** `ClassificationResult` in `models/classification.py` with relationship back to `Message`.
4. **Enums** persisted as constrained strings (portable, easy to extend) rather than native PG enums, to allow future label additions without a migration churn.

---

## ML / Model-Serving Tasks

1. **Artifact format** — a single versioned bundle (e.g., a joblib/pickle dir) containing: fitted `TfidfVectorizer`, fitted `LogisticRegression`, ordered label list, and a `model_version` string. Stored under a path given by `INTENT_MODEL_PATH` (not committed if large — documented placeholder + a tiny demo artifact for local dev).
2. **Load-once singleton** — loaded at startup; subsequent requests reuse the in-memory model. Thread-safe read-only inference.
3. **Inference contract** — `predict(text) -> (IntentLabel, float)`: lowercase/normalise, truncate to `INTENT_MAX_CHARS`, vectorise, `predict_proba`, argmax → label + top probability as confidence.
4. **Threshold application** — done in the service layer (not the model) so the threshold is configurable and testable independently.
5. **Graceful unavailability** — if the artifact is missing, the loader marks the model unavailable; auto-classify is skipped (message still created), and `POST /classify` returns 503 `MODEL_UNAVAILABLE`.
6. **Determinism + versioning** — no randomness at inference; `model_version` stamped on every result.
7. **Demo artifact** — provide a small training script (`ml/train_demo.py`) and/or a tiny pre-built artifact so the feature is testable locally without a full training pipeline (training pipeline itself is out of scope).

---

## API Tasks

| Endpoint | Purpose |
|----------|---------|
| `POST /api/messages/{message_id}/classify` | Re-run classification for one in-tenant message; returns the result (won't overwrite a `reviewed` row unless `force=true`) |
| `GET /api/messages/{message_id}/classification` | Read the stored classification; 404 if none |
| `PATCH /api/messages/{message_id}/classification/review` | Human correction: set label, mark `reviewed`, record reviewer |

- All require `staff` or `manager`; Platform Admin → 403.
- All resolve the message tenant first (404 not-in-tenant / 403 cross-tenant), per SR-04.
- Validation via Pydantic (label must be a valid `IntentLabel`).
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/classification.ts`** — typed client: `getClassification(messageId)`, `classifyMessage(messageId)`, `reviewClassification(messageId, label)`.
2. **`types/classification.ts`** — `IntentLabel`, `ClassificationStatus`, `ClassificationResult` TS types mirroring the backend.
3. **`components/classification/IntentBadge.tsx`** — small badge mapping each label to a colour/label text; a distinct "needs review" and "unclassified/pending" visual.
4. **Inbox integration (Spec 004)** — render `IntentBadge` on each inbox row using the `classification` block now in the inbox response.
5. **Detail integration (Spec 005)** — replace the "AI Intent" placeholder panel with a real `IntentPanel` showing label + confidence + review state; the other five placeholders stay.
6. **`components/classification/ReviewControl.tsx`** — a label `Select` + confirm button that calls `reviewClassification`; visible to staff/manager; optimistic update + error handling.
7. **States** — loading/pending, classified, needs-review (highlighted), reviewed (shows reviewer), unclassified, and model-unavailable messaging.

---

## Testing Tasks

**Backend (pytest + pytest-asyncio)** — `tests/integration/test_classification.py`:
- Auto-classify on inbound creation (AC-01, AC-02, AC-03)
- Outbound not classified (AC-04)
- Tenant isolation (AC-05)
- `GET` returns result / 404 when none (AC-06, AC-07)
- `POST /classify` runs + overwrites model result (AC-08)
- `PATCH review` updates + records reviewer (AC-09); invalid label 422 (AC-10)
- Platform Admin 403 (AC-11)
- Auto path does not overwrite reviewed (AC-12)
- Classifier failure does not block message creation (AC-14)
- No task/escalation/reply/RAG side effects (AC-15)

**Unit tests** — `tests/unit/test_classifier_model.py`: threshold routing, bounded input, empty body → `other`/`needs_review`, deterministic output, `model_version` stamping.

**Frontend** — render tests: `IntentBadge` per label + needs-review/unclassified; inbox + detail show the label (AC-13); review control submits and updates.

---

## Build Order

1. **DB + models** — Alembic migration + `ClassificationResult` model + enums (Database Tasks).
2. **ML layer** — `ClassifierModel`, loader, demo artifact + train script, unit tests (ML Tasks).
3. **Schemas** — Pydantic models + enums (Backend Task 1).
4. **Service** — `classification_service` (classify / get / review) with unit coverage of threshold + reviewed-protection.
5. **API** — three endpoints + router mount + error mapping; integration tests.
6. **Creation hook** — wire fail-safe `classify_message()` into Spec 003 message creation; failure-isolation test.
7. **Response surfacing** — extend inbox (Spec 004) + detail (Spec 005) responses with the `classification` block.
8. **Frontend** — types + API client → `IntentBadge` → inbox integration → detail panel (replace placeholder) → review control → states.
9. **Validation** — run quickstart end-to-end; confirm all 15 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/006-intent-classifier/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── classification.py            # 3 endpoints
│   ├── services/
│   │   └── classification_service.py    # classify / get / review
│   ├── ml/
│   │   ├── classifier_model.py          # TF-IDF + LogReg wrapper
│   │   ├── loader.py                     # startup singleton + availability
│   │   └── train_demo.py                 # small demo training script
│   ├── models/
│   │   └── classification.py             # ClassificationResult ORM model
│   └── schemas/
│       └── classification.py             # Pydantic + IntentLabel/ClassificationStatus enums
├── alembic/versions/
│   └── 00xx_create_classification_results.py
├── models/                               # trained artifact dir (INTENT_MODEL_PATH)
│   └── intent/                           #   vectoriser + model + labels + version
└── tests/
    ├── integration/
    │   └── test_classification.py
    └── unit/
        └── test_classifier_model.py

frontend/
└── src/
    ├── api/
    │   └── classification.ts
    ├── types/
    │   └── classification.ts
    └── components/classification/
        ├── IntentBadge.tsx
        ├── IntentPanel.tsx               # replaces Spec 005 AI Intent placeholder
        └── ReviewControl.tsx
```

Modified files:

```
backend/app/main.py                       # mount router + model load on startup
backend/app/<spec003 message create path> # add fail-safe classify hook
backend/app/services/inbox_service.py     # add classification block to inbox items
backend/app/services/conversation_service.py # add classification to detail messages
backend/app/core/config.py                # INTENT_* settings
frontend/src/pages/InboxPage / InboxItem  # render IntentBadge
frontend/src/pages/ConversationDetailPage # render IntentPanel (replace placeholder)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–005. New `backend/app/ml/` package isolates model-serving from the API/service layers.
