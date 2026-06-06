# Implementation Plan: Risk Detection

**Branch**: `007-risk-detection` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-risk-detection/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): `messages` table, tenant isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth, `staff`/`manager` roles, `require_role`, `get_current_tenant_context`
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): inbound message creation path
- [Spec 004 — Message Inbox](../004-message-inbox/plan.md): inbox surface for the risk badge
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): detail surface (replaces the "Risk / Sentiment" placeholder)
- [Spec 006 — Intent Classifier](../006-intent-classifier/plan.md): `ClassificationResult` consumed as the risk baseline driver; risk runs right after classification

---

## Summary

Add a rule-based risk assessment step that runs immediately after intent classification. A `RiskEngine` maps the stored intent to a baseline `level` + primary `flag`, then applies keyword/business-rule modifiers (urgency terms, refund/cancel terms, guest-count magnitude, compound-signal escalation) that may raise the level and compose a human-readable `reason`. Results are stored one-to-one in a new `risk_assessments` table with `level`, `flag`, `reason`, `escalation_recommended`, `rules_version`, `status`, and review metadata. Three REST endpoints mirror Spec 006: `POST /api/messages/{id}/risk-assessment` (re-run), `GET /api/messages/{id}/risk-assessment` (read), `PATCH /api/messages/{id}/risk-assessment/review` (human correction). The risk is surfaced as an inbox badge and a detail panel (replacing the Spec 005 "Risk / Sentiment" placeholder). The engine takes **no** action — it only assesses and may set an `escalation_recommended` flag. Failure is isolated so it can never break message creation or classification.

---

## Technical Approach

- **Runs after classification**: the same post-creation hook that triggers classification (Spec 006) chains risk assessment after a successful classification, in a fail-safe wrapper (a risk error never fails message creation or classification — FR-014).
- **Pure rule engine**: `RiskEngine.assess(classification, body) -> RiskOutcome(level, flag, reason, escalation_recommended)`. Deterministic, no I/O, fully unit-testable. Rules live in a versioned module (`rules_version`).
- **Baseline + modifiers**: intent → baseline (level, flag); then ordered keyword/business rules may *raise* the level and select the highest-priority flag. Rules never silently lower an intent-implied `high` (FR-005, AC-18).
- **Reason composition**: each contributing rule appends a short clause; the final `reason` is a concise human-readable sentence.
- **One-to-one storage** with reviewed-protection: `risk_assessments.message_id` is unique; auto re-assess refuses to overwrite a `reviewed` row (FR-013).
- **Tenant safety**: every endpoint resolves the message first (404/403, consistent with Specs 005/006); the assessment inherits `tenant_id` from the message.
- **Surfacing**: the inbox item (Spec 004) and detail message (Spec 005) responses are extended with a compact `risk` summary so the frontend renders badge/panel without extra round-trips.

---

## Backend Tasks

1. **`schemas/risk.py`** — Pydantic models: `RiskAssessmentResponse`, `AssessResponse`, `RiskReviewRequest`, `RiskReviewResponse`, plus `RiskLevel`, `RiskFlag`, `RiskAssessmentStatus` string enums.
2. **`risk/engine.py`** — `RiskEngine` + `RiskOutcome`: intent→baseline map, modifier rules, reason builder, `escalation_recommended` logic, `rules_version`. Pure function, no DB.
3. **`risk/rules.py`** — versioned rule data: `INTENT_BASELINE` map, keyword lists (urgency, refund/cancel, complaint cues), `guest_count_delta` parsing/thresholds, flag-priority order, `RULES_VERSION`.
4. **`services/risk_service.py`**:
   - `assess_message(session, message)` — load classification; if none → skip (auto) / 409 (manual); run engine; upsert (skip if existing `reviewed`); persist. Fail-safe for the auto caller.
   - `get_risk_assessment(session, tenant_id, message_id)` — tenant-resolve (404/403); return assessment or raise `NoRiskAssessment` (404).
   - `review_risk_assessment(session, tenant_id, user, message_id, level, flag, reason)` — validate, update, set `reviewed`, record reviewer + time.
5. **`api/v1/risk.py`** — three routes with `require_role(staff, manager)` + error→HTTP mapping.
6. **Chain into the classification hook** — after Spec 006 classification succeeds for an inbound message, call `assess_message()` in a fail-safe wrapper.
7. **Extend inbox + detail responses** — add a compact `risk` block (level, flag, reason, escalation_recommended) per message/conversation.
8. **Config** — add `RISK_RULES_VERSION` (and any tunable thresholds) to settings.
9. **Router mount** — register the risk router at `/api/v1` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `risk_assessments`:
   - `id` UUID PK
   - `message_id` UUID FK → `messages.id`, **UNIQUE**, `ON DELETE CASCADE`
   - `tenant_id` UUID NOT NULL, FK → `tenants.id`, indexed (denormalised from message)
   - `level` VARCHAR (one of `RiskLevel`)
   - `flag` VARCHAR NULL (one of `RiskFlag`, null when clearly low)
   - `reason` TEXT NOT NULL
   - `escalation_recommended` BOOLEAN NOT NULL default false
   - `rules_version` VARCHAR NOT NULL
   - `status` VARCHAR (one of `RiskAssessmentStatus`)
   - `reviewed_by` UUID NULL FK → users
   - `reviewed_at` TIMESTAMPTZ NULL
   - `created_at`, `updated_at` TIMESTAMPTZ
2. **Indexes**: unique on `message_id`; `(tenant_id, level)` for high-risk filtering; `(tenant_id, escalation_recommended)` for the future escalation queue.
3. **SQLAlchemy model** `RiskAssessment` in `models/risk.py` with relationship back to `Message`.
4. **Enums** persisted as constrained strings (portable + evolvable), validated at the app boundary.

---

## Risk-Rule Tasks

1. **Intent baseline map** — encode the spec's Intent→Risk table (`booking/pricing/availability/service → low`; `urgent_change/complaint/cancellation_request/human_escalation → high`; `guest_count_change/payment_issue → medium`; `other → medium`).
2. **Flag mapping** — map each intent/condition to its primary `RiskFlag`; define a deterministic flag-priority order for compound cases.
3. **Keyword/urgency rules** — lists for urgency ("asap", "urgent", "today", "next week", "tomorrow"), money/refund ("refund", "deposit", "chargeback", "not confirmed"), cancellation ("cancel", "call off"), complaint cues ("unhappy", "disappointed", "unacceptable"), escalation ("manager", "speak to someone", "lawyer").
4. **Guest-count magnitude** — parse "from X to Y" / numeric deltas; large delta or near-event urgency → raise `guest_count_change` to high; small/neutral → medium.
5. **Compound escalation** — multiple high-signals or explicit escalation → ensure `high` + set `human_escalation_needed` when appropriate; `escalation_recommended = true`.
6. **Reason builder** — compose a concise sentence from the matched baseline + modifiers.
7. **Versioning** — stamp `RULES_VERSION` on every outcome; keep rules in one module for testable evolution.
8. **No-lower guarantee** — implement modifiers as monotonic raises over the intent baseline (AC-18).

---

## API Tasks

| Endpoint | Purpose |
|----------|---------|
| `POST /api/messages/{message_id}/risk-assessment` | Re-run rules for one in-tenant message; 409 if not yet classified; won't overwrite `reviewed` unless `force=true` |
| `GET /api/messages/{message_id}/risk-assessment` | Read the stored assessment; 404 if none |
| `PATCH /api/messages/{message_id}/risk-assessment/review` | Human correction: set level/flag/reason, mark `reviewed`, record reviewer |

- All require `staff`/`manager`; Platform Admin → 403.
- All resolve the message tenant first (404/403) per SR-04.
- Pydantic validation (level/flag must be valid enums); consistent `error_code` payloads.

---

## Frontend Integration Tasks

1. **`api/risk.ts`** — typed client: `getRiskAssessment(messageId)`, `assessMessage(messageId)`, `reviewRiskAssessment(messageId, payload)`.
2. **`types/risk.ts`** — `RiskLevel`, `RiskFlag`, `RiskAssessmentStatus`, `RiskAssessment` TS types.
3. **`components/risk/RiskBadge.tsx`** — colour-coded level badge (low=muted, medium=amber, high=red) + flag label; distinct "not assessed/pending" state.
4. **Inbox integration (Spec 004)** — render `RiskBadge` on each inbox row from the embedded `risk` block; emphasise high.
5. **Detail integration (Spec 005)** — replace the "Risk / Sentiment" placeholder panel with a real `RiskPanel` (level + flag + reason + escalation-recommended indicator); other placeholders stay.
6. **`components/risk/RiskReviewControl.tsx`** — level `Select` + flag `Select` + reason input + confirm; calls `reviewRiskAssessment`; staff/manager only; optimistic update + error handling.
7. **States** — pending/not-assessed, assessed, reviewed (shows reviewer), failed, and "escalation recommended" indicator (informational only).

---

## Testing Tasks

**Backend integration** — `tests/integration/test_risk.py`:
- Auto-assess after classification; baseline levels (AC-01, AC-02)
- High-risk intents + flags (AC-03); guest-count medium vs high (AC-04); payment medium vs high (AC-05); other → medium (AC-06)
- `escalation_recommended` per level (AC-07)
- Tenant isolation (AC-08)
- `GET` result / 404 (AC-09, AC-10)
- `POST assess` runs + 409 when not classified (AC-11)
- `PATCH review` updates + records reviewer (AC-12); invalid level/flag 422 (AC-13)
- Auto path preserves `reviewed` (AC-14); Platform Admin 403 (AC-15)
- No task/escalation/reply/RAG side effects (AC-16); no-lower guarantee (AC-18)

**Unit** — `tests/unit/test_risk_engine.py`: each intent baseline, each keyword modifier, guest-count parsing, compound escalation, reason composition, determinism, `rules_version` stamping, monotonic no-lower.

**Frontend** — render tests: `RiskBadge` per level + not-assessed; inbox + detail show level/flag/reason (AC-17); review control submits and updates.

---

## Build Order

1. **DB + models** — Alembic migration + `RiskAssessment` model + enums.
2. **Rule data + engine** — `risk/rules.py` + `risk/engine.py` with full unit coverage (the core of the feature; build and test in isolation first).
3. **Schemas** — Pydantic models + enums.
4. **Service** — `risk_service` (assess / get / review) with reviewed-protection + not-classified handling.
5. **API** — three endpoints + router mount + error mapping; integration tests.
6. **Chain hook** — wire fail-safe `assess_message()` after Spec 006 classification; failure-isolation test.
7. **Response surfacing** — extend inbox (Spec 004) + detail (Spec 005) responses with the `risk` block.
8. **Frontend** — types + API client → `RiskBadge` → inbox integration → detail panel (replace placeholder) → review control → states.
9. **Validation** — run quickstart with the five demo messages; confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/007-risk-detection/
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
│   │   └── risk.py                      # 3 endpoints
│   ├── services/
│   │   └── risk_service.py              # assess / get / review
│   ├── risk/
│   │   ├── engine.py                    # RiskEngine + RiskOutcome (pure)
│   │   └── rules.py                     # versioned rule data (baseline map, keywords, thresholds)
│   ├── models/
│   │   └── risk.py                      # RiskAssessment ORM model
│   └── schemas/
│       └── risk.py                      # Pydantic + RiskLevel/RiskFlag/RiskAssessmentStatus enums
├── alembic/versions/
│   └── 00xx_create_risk_assessments.py
└── tests/
    ├── integration/
    │   └── test_risk.py
    └── unit/
        └── test_risk_engine.py

frontend/
└── src/
    ├── api/
    │   └── risk.ts
    ├── types/
    │   └── risk.ts
    └── components/risk/
        ├── RiskBadge.tsx
        ├── RiskPanel.tsx                # replaces Spec 005 "Risk / Sentiment" placeholder
        └── RiskReviewControl.tsx
```

Modified files:

```
backend/app/main.py                          # mount risk router
backend/app/services/classification_service.py # chain fail-safe assess_message() after classify
backend/app/services/inbox_service.py         # add risk block to inbox items
backend/app/services/conversation_service.py  # add risk to detail messages
backend/app/core/config.py                    # RISK_* settings
frontend/src/pages/InboxPage / InboxItem      # render RiskBadge
frontend/src/pages/ConversationDetailPage     # render RiskPanel (replace placeholder)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–006. A dedicated `backend/app/risk/` package keeps the pure rule engine separate from the API/service/persistence layers and from the classifier (`backend/app/ml/`), satisfying FR-004 (risk is separate from the classifier).
