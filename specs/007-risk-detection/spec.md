# Feature Specification: Risk Detection

**Feature Branch**: `007-risk-detection`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)

**Input**: User description: "The system should analyze each incoming client message and its intent classification to detect whether the message represents a planning, client, payment, cancellation, urgency, or escalation risk. The risk result should be stored, linked to the message, and displayed in the message inbox and message detail page."

---

## Goal

Automatically assess the risk of every incoming client message immediately after it has been intent-classified, producing a single risk **level** (`low` / `medium` / `high`), a single primary risk **flag**, and a short human-readable **reason**. The assessment is persisted, linked one-to-one to its message, scoped to the message's tenant, and surfaced as a badge in the inbox and a panel on the message detail page. Risk detection turns the structured intent signal (Spec 006) plus the message text into a triage priority so staff know what needs attention first, and managers can find high-risk cases. This feature **only assesses** — it never creates tasks, never escalates, and never sends anything. For high-risk messages it may set a *recommendation* to escalate, but acting on that recommendation is a separate, human-reviewed feature.

---

## Risk Levels

| Level | Meaning |
|-------|---------|
| `low` | Routine inquiry; no time pressure or dissatisfaction. Handle in normal flow. |
| `medium` | Needs attention soon; ambiguous, money-related, or a change that could grow. |
| `high` | Needs prompt attention; urgency, dissatisfaction, cancellation, or explicit escalation. |

## Risk Flags

The assessment records exactly one **primary** flag (highest-priority match):

| # | Flag | Typical trigger |
|---|------|-----------------|
| 1 | `urgent_change` | Time-sensitive change to an existing plan |
| 2 | `complaint` | Dissatisfaction / grievance |
| 3 | `cancellation_risk` | Client wants to cancel or is considering it |
| 4 | `payment_risk` | Payment, deposit, or refund problem |
| 5 | `guest_count_change` | Change in number of guests |
| 6 | `human_escalation_needed` | Explicit request for a human/manager, or compound high-risk |
| 7 | `unsupported_or_unclear_request` | Off-scope / unclear / unclassifiable request |

---

## Intent → Risk Mapping (baseline)

| Intent (Spec 006) | Baseline level | Primary flag | Notes |
|-------------------|----------------|--------------|-------|
| `booking_inquiry` | low | — | routine |
| `pricing_request` | low | — | routine |
| `availability_question` | low | — | routine |
| `service_question` | low | — | routine |
| `guest_count_change` | medium → high | `guest_count_change` | high if large delta / near event date / urgent wording |
| `urgent_change` | high | `urgent_change` | time-sensitive |
| `complaint` | high | `complaint` | dissatisfaction |
| `cancellation_request` | high | `cancellation_risk` | possible lost booking |
| `payment_issue` | medium → high | `payment_risk` | high if "paid but unconfirmed", refund dispute, or urgency |
| `human_escalation` | high | `human_escalation_needed` | explicit escalation request |
| `other` | medium | `unsupported_or_unclear_request` | unclear → needs a human look |

Keyword/business-rule modifiers can raise (escalate) the baseline level (e.g., "next week", "ASAP", "lawyer", "refund", large guest delta). Rules may raise risk; the design favours not silently lowering an intent-implied high.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner who sees the risk badge on each message, uses level + flag + reason to decide what to do first, and can correct a wrong assessment via review. |
| **Manager** | A senior planner who filters/reviews high-risk and escalation-recommended cases for oversight, and can also review assessments. |
| **System / AI service** | The backend risk engine that, after intent classification, produces the level, primary flag, and reason. Not a human actor; takes no action beyond storing the assessment. |

Platform Admin has no access to tenant messages, classifications, or risk results.

---

## User Stories

### User Story 1 — Automatic Risk Assessment After Classification (Priority: P1)

When a message has been intent-classified (Spec 006), the system automatically assesses its risk, producing a level, a primary flag, and a human-readable reason, and stores the result linked to that message. It happens without staff action, as the next step after classification.

**Why this priority**: Risk triage is the core value — it tells staff what to handle first. Without an automatic assessment there is nothing to display or filter on, and the MVP workflow (classify → risk → …) breaks. Every other story depends on an assessment existing.

**Independent Test**: Inject "I want to cancel the booking. Is the deposit refundable?" as Tenant A staff (classified `cancellation_request`). Verify a `RiskAssessment` is created and linked, with level `high`, flag `cancellation_risk`, and a non-empty reason. Verify no assessment exists in Tenant B.

**Acceptance Scenarios**:

1. **Given** a message has a classification, **When** risk detection runs, **Then** exactly one `RiskAssessment` is stored linked one-to-one to the message, with a `level` ∈ {low, medium, high}, one `flag` (or none for clearly-low), and a non-empty `reason`.
2. **Given** an intent with a baseline mapping, **When** no escalating keywords are present, **Then** the stored level matches the baseline for that intent.
3. **Given** an intent of `cancellation_request`, `urgent_change`, `complaint`, or `human_escalation`, **When** assessed, **Then** the level is `high` and the flag matches the intent.
4. **Given** assessment of a Tenant A message, **When** the result is stored, **Then** it is scoped to Tenant A via the message's `tenant_id` and is never visible to Tenant B.

---

### User Story 2 — View Risk in Inbox and Detail Page (Priority: P1)

A staff planner sees a risk badge (colour-coded by level) on each message in the inbox, and on the detail page sees the level, the primary flag, and the human-readable reason. High-risk and escalation-recommended messages are visually emphasised so they stand out.

**Why this priority**: A stored risk that is invisible delivers no triage value. Surfacing it in the two existing read surfaces is what lets staff prioritise and lets managers spot high-risk cases. Equal to US1 because the feature is only useful when both exist.

**Independent Test**: Assess a `complaint` message (high). Open the inbox — verify a red/high risk badge on that message. Open the detail page — verify it shows level `high`, flag `complaint`, and the reason text. Assess a `pricing_request` (low) — verify a muted/low badge.

**Acceptance Scenarios**:

1. **Given** a message has a risk assessment, **When** the inbox renders it, **Then** a risk badge colour-coded by level is shown.
2. **Given** a message has a risk assessment, **When** the detail page renders it, **Then** the level, primary flag, and reason are displayed.
3. **Given** an assessment recommends escalation, **When** it is shown, **Then** an "escalation recommended" indicator is displayed (informational only — no action is triggered).
4. **Given** a message has no risk assessment yet, **When** it is shown, **Then** a neutral "not assessed / pending" indicator is shown rather than a misleading level.

---

### User Story 3 — Human Review and Correction of a Risk Assessment (Priority: P2)

A staff or manager user can correct a risk assessment — change the level and/or primary flag, optionally edit the reason — when the rules got it wrong. The corrected assessment is stored, marked human-reviewed, records who reviewed it, and is shown going forward.

**Why this priority**: Rule-based risk will misjudge edge cases. Human correction keeps the displayed risk trustworthy and produces feedback for tuning the rules. Lower than P1 because automatic assessment + display already deliver standalone triage value.

**Independent Test**: Take a message assessed `medium` / `unsupported_or_unclear_request`. As staff, submit a review setting level `high` and flag `complaint` with a reason. Verify the stored assessment is updated, `status` is `reviewed`, reviewer + time recorded, and the inbox/detail page reflect the corrected risk.

**Acceptance Scenarios**:

1. **Given** a message with an existing assessment, **When** a staff/manager submits a review with a valid level and valid flag, **Then** the assessment is updated, `status` becomes `reviewed`, and reviewer identity + review time are recorded.
2. **Given** a review with an invalid level or invalid flag, **When** submitted, **Then** it is rejected with a validation error and the stored assessment is unchanged.
3. **Given** a review for a message in another tenant, **When** submitted, **Then** it is rejected (404/403 per tenant rules) and no change is made.
4. **Given** an assessment with `status` `reviewed`, **When** automatic re-assessment runs, **Then** the reviewed result is preserved (auto path does not overwrite a human decision).

---

### Edge Cases

- **No classification yet**: risk detection requires a classification. If none exists, the assessment endpoint returns a clear error (the message is "not assessed"); the auto path runs only after classification completes.
- **Classification is `needs_review` / low confidence**: still assessable — the `other` intent maps to `medium` / `unsupported_or_unclear_request`. The reason notes the low-confidence basis.
- **Empty/whitespace body**: assessed as `medium` / `unsupported_or_unclear_request` (cannot judge → human look). No crash.
- **Compound high-risk** (e.g., complaint + "next week" + "refund"): level stays `high`; the primary flag is the highest-priority match; the reason mentions the contributing signals.
- **Outbound (agency) message**: never assessed (no classification, no risk).
- **Conflicting signals** (e.g., `pricing_request` intent but body says "cancel"): keyword rules may raise the level above the intent baseline; rules never silently drop an intent-implied high.
- **Guest count delta wording**: "from 150 to 220" (large) → high; "add one guest" (small) → medium. Magnitude/urgency wording drives medium vs high.
- **Re-assessment after rule changes**: `POST /risk-assessment` re-runs rules and overwrites the rule-generated result, but never a `reviewed` result unless explicitly forced.
- **Concurrent reviews**: last write wins; both succeed; final state consistent.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST assess risk for a message automatically after its intent classification completes.
- **FR-002**: The system MUST store each assessment as a `RiskAssessment` linked one-to-one to its message.
- **FR-003**: Each assessment MUST include a `level` ∈ {low, medium, high}, a primary `flag` (one of seven, or none when clearly low), a non-empty human-readable `reason`, an `escalation_recommended` boolean, the `rules_version`, a `status`, and timestamps.
- **FR-004**: Risk detection MUST be a separate component from the intent classifier (Spec 006) — it consumes the classification but is not part of it.
- **FR-005**: The system MUST derive the baseline level/flag from the intent and MAY raise the level via keyword/business rules; rules MUST NOT silently lower an intent-implied `high`.
- **FR-006**: The system MUST set `escalation_recommended = true` for `high` level (and explicit `human_escalation_needed`) but MUST NOT perform any escalation.
- **FR-007**: The system MUST NOT create tasks, MUST NOT create escalations, MUST NOT generate replies, and MUST NOT perform document retrieval.
- **FR-008**: The system MUST expose the assessment via a read endpoint and surface it in the inbox and message detail page.
- **FR-009**: Staff and manager users MUST be able to review (correct/confirm) an assessment, updating level/flag/reason and marking it reviewed.
- **FR-010**: A review MUST record the reviewing user's identity and the review timestamp, and set `status` to `reviewed`.
- **FR-011**: The system MUST reject reviews with an invalid level or invalid flag (validation error).
- **FR-012**: The system MUST scope every assessment to the tenant of its related message; cross-tenant access MUST be blocked.
- **FR-013**: The automatic re-assessment path MUST NOT overwrite an assessment whose `status` is `reviewed`.
- **FR-014**: Risk detection failure MUST NOT block message creation or classification — message and classification remain intact and the message is shown "not assessed".

### Key Entities

- **Message** (existing, Spec 001/003): the message being assessed.
- **ClassificationResult** (existing, Spec 006): the intent + confidence that the risk engine reads as input.
- **RiskAssessment** (new): the stored risk output for one message — level, primary flag, reason, escalation recommendation, rules version, status, reviewer info, timestamps.
- **RiskLevel** (enum): `low`, `medium`, `high`.
- **RiskFlag** (enum): the seven flags.
- **RiskAssessmentStatus** (enum): lifecycle (`assessed`, `reviewed`, `failed`).

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Classified inbound message | Spec 006 completion | Triggers automatic risk assessment |
| Intent label + confidence | `ClassificationResult` (Spec 006) | Baseline mapping driver |
| Message body text | `messages.body` | Keyword/business-rule evaluation |
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by client |
| Manual assess trigger | `POST /api/messages/{id}/risk-assessment` | Re-run rules on a specific message |
| Review submission | `PATCH /api/messages/{id}/risk-assessment/review` | Staff/manager corrected level/flag/reason |
| Rules configuration | Backend rules module/config | Intent map, keyword lists, thresholds, `rules_version` |

---

## Outputs

| Output | Description |
|--------|-------------|
| Stored assessment | A `RiskAssessment` row linked to the message, tenant-scoped |
| Risk level | `low` / `medium` / `high`, colour-coded in UI |
| Primary risk flag | One of the seven flags (or none for clearly-low) |
| Human-readable reason | Short text explaining why the level/flag was chosen |
| Escalation recommendation | Boolean indicator (informational; no action) |
| Inbox badge | Risk level badge per message in the inbox |
| Detail panel | Level + flag + reason + escalation-recommended on the detail page |
| Review record | Reviewer identity + timestamp on the assessment |
| 403 / 404 | Cross-tenant / platform-admin / missing message or classification |
| 422 | Invalid review level/flag or malformed request |

---

## Main Workflow

1. **Message classified** — Spec 006 produces a `ClassificationResult` for a new inbound message.
2. **Risk detection triggered** — Immediately after classification, the risk engine runs for that message.
3. **Baseline from intent** — The engine maps the intent label to a baseline level + primary flag.
4. **Rule modifiers applied** — Keyword/business rules (urgency words, refund/cancel terms, guest-count magnitude, compound signals) may raise the level and refine the flag; a reason string is composed.
5. **Escalation recommendation** — `escalation_recommended` is set for `high` / explicit escalation (recommendation only).
6. **Result stored** — A `RiskAssessment` is saved, linked to the message, scoped to the tenant.
7. **Surfaced to users** — Inbox badge + detail panel show level, flag, reason; high/escalation cases emphasised.
8. **Optional human review** — Staff/manager corrects level/flag/reason; assessment becomes `reviewed` with reviewer + time.

---

## Alternative Workflows

### Manual Re-Assessment

1. A staff user (or developer in testing) calls `POST /api/messages/{id}/risk-assessment`.
2. The engine re-runs rules using the current classification.
3. If the current assessment is `reviewed`, the manual auto-assess preserves it unless `force=true`; otherwise it overwrites and returns the new result.

### Assess Before Classification Exists

1. `POST /risk-assessment` is called for a message with no classification.
2. The engine cannot derive a baseline → returns 409 `NOT_CLASSIFIED` (assess after classifying).
3. The message is shown "not assessed" until a classification exists.

### Compound High-Risk

1. A `complaint` message also contains "next week" and "refund".
2. Baseline is already `high`; rules keep it `high`, choose `complaint` as primary flag, and the reason cites urgency + refund signals.
3. `escalation_recommended = true`.

### Rule Engine Failure

1. The rules engine raises during evaluation.
2. No assessment is stored (or a `failed` row is recorded); message + classification are unaffected.
3. The message shows "not assessed"; a later `POST /risk-assessment` can retry.

### Cross-Tenant Access Attempt

1. Tenant B staff requests the risk assessment of a Tenant A message.
2. The backend resolves the message tenant from the JWT, sees a mismatch, returns 403 (or 404 if not in tenant).
3. No risk data is exposed.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | A classified inbound message receives exactly one assessment with valid level, flag, and non-empty reason | Integration test: classify → assess → assert one RiskAssessment linked, valid enums, reason non-empty |
| AC-02 | Baseline intents map to expected levels (booking/pricing/availability/service → low) | Integration test: assert level=low for each |
| AC-03 | `urgent_change`, `complaint`, `cancellation_request`, `human_escalation` → high with matching flag | Integration test: assert level=high + correct flag for each |
| AC-04 | `guest_count_change` is medium for small/neutral wording, high for large-delta/urgent wording | Integration test: two messages, assert medium vs high |
| AC-05 | `payment_issue` is medium normally, high for "paid but unconfirmed"/refund/urgency | Integration test: assert medium vs high |
| AC-06 | `other` → medium with flag `unsupported_or_unclear_request` | Integration test: assert medium + flag |
| AC-07 | `escalation_recommended` is true for high-level assessments and false for low | Integration test: assert boolean per level |
| AC-08 | Assessment is tenant-scoped; Tenant B cannot read Tenant A assessment | Integration test: assess in A; GET as B → 404/403, no data |
| AC-09 | `GET /api/messages/{id}/risk-assessment` returns the stored assessment | Integration test: assert 200 + fields |
| AC-10 | `GET` returns 404 when no assessment exists | Integration test: unassessed message → 404 NO_RISK_ASSESSMENT |
| AC-11 | `POST /risk-assessment` (re)runs rules and returns the result; 409 if not yet classified | Integration test: assert 200 with classification; 409 NOT_CLASSIFIED without |
| AC-12 | `PATCH .../review` updates level/flag/reason, sets status reviewed, records reviewer + time | Integration test: review → assert updates + reviewer + reviewed_at |
| AC-13 | Review with invalid level/flag is rejected (422), assessment unchanged | Integration test: bad level/flag → 422, no change |
| AC-14 | Auto re-assessment does not overwrite a `reviewed` assessment | Integration test: review → POST assess → assert reviewed result preserved |
| AC-15 | Platform Admin blocked from all risk endpoints (403) | Integration test: admin token → 403 INSUFFICIENT_ROLE |
| AC-16 | Risk detection produces no tasks, escalations, replies, or retrieval | Code/integration test: assert no such side effects |
| AC-17 | Risk level + flag + reason displayed in inbox and detail; high emphasised | Frontend test: assert badge + panel rendering |
| AC-18 | Rules never silently lower an intent-implied high | Integration test: high-intent + benign body → still high |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | `messages` table, tenant isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT auth, `staff`/`manager` roles, Platform Admin blocked |
| Spec 003 — Message Simulator | Required | Creates inbound messages |
| Spec 004 — Message Inbox | Required | Surface for the risk badge |
| Spec 005 — Message Detail Page | Required | Surface for the risk panel (replaces the Spec 005 "Risk / Sentiment" placeholder) |
| Spec 006 — Intent Classifier | Required | Provides the `ClassificationResult` (intent + confidence) the risk engine reads |

---

## AI / Rule Behavior

- **Rule-based engine** (not an ML model in this feature): intent→risk baseline mapping + keyword lists + simple business logic (guest-count magnitude, urgency terms, refund/cancel terms, compound-signal escalation).
- **Reads classification, not raw model**: the engine consumes the stored `ClassificationResult` (intent + confidence) plus the message body; it does not re-run the classifier.
- **Single level + single primary flag**: exactly one `level` and one primary `flag` (highest-priority match) are stored; the reason may mention secondary signals.
- **Deterministic**: same rules version + same inputs → same level, flag, and reason. No randomness.
- **Conservative**: rules may raise risk but do not silently lower an intent-implied high; uncertainty (`other`, empty, unclear) → at least `medium`.
- **Versioned**: every assessment records `rules_version` so results can be compared as rules evolve, and reviewed data can tune rules.
- **Human-readable reason**: every assessment includes a short reason string explaining the decision (e.g., "Cancellation intent with refund mention near event date").
- **Recommendation only**: `escalation_recommended` flags high-risk for a human; it triggers no escalation, task, reply, or retrieval. No auto-actions, no auto-send.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the JWT (and, for the auto path, from the message's tenant). No client-supplied tenant is accepted. |
| **SR-02: Assessment inherits message tenant** | A `RiskAssessment` is bound to its message's tenant. Tenant A can never read or modify Tenant B assessments. |
| **SR-03: Role restriction** | Only `staff` and `manager` may read or review assessments. Platform Admin → 403. Unauthenticated → 401. |
| **SR-04: Not Found vs Forbidden** | A message not in the caller's tenant → 404; a message in another tenant → 403 (consistent with Specs 005/006). Endpoints never confirm cross-tenant content. |
| **SR-05: Review authorisation** | Only `staff`/`manager` of the message's tenant may review; the recorded reviewer is the authenticated user. |
| **SR-06: No cross-tenant rule data** | The engine evaluates only the message body + its own classification within the tenant boundary; no cross-tenant data is read. |
| **SR-07: No autonomous action** | The engine performs no escalation, task creation, reply, or retrieval — only assessment + a recommendation flag. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| No classification for the message | `POST /risk-assessment` → 409 `NOT_CLASSIFIED`; auto path runs only after classification; message shown "not assessed". |
| Rules engine raises during evaluation | No result stored (or `status` `failed`); message + classification unaffected; error logged; retry via `POST`. |
| Empty/whitespace body | Assessed `medium` / `unsupported_or_unclear_request` (no crash). |
| `GET` for a message with no assessment | 404 `NO_RISK_ASSESSMENT`. |
| `PATCH` review with invalid level/flag | 422 validation error; no change. |
| Any endpoint, cross-tenant message | 404/403 per SR-04; no data exposed. |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE`. |
| Auto re-assess on an already-`reviewed` message | No overwrite; reviewed result preserved (FR-013). |

---

## Edge Cases (summary)

- Low-confidence/`needs_review` classification → still assessable; `other` → `medium`.
- Empty body → `medium` / `unsupported_or_unclear_request`.
- Compound high-risk → stays high; primary flag = highest priority; reason cites signals.
- Conflicting intent vs keywords → rules may raise, never silently lower an implied high.
- Guest-count magnitude/urgency drives medium vs high.
- Outbound message → never assessed.
- Concurrent reviews → last write wins; consistent.

---

## Out of Scope

- **Intent classification** — done in Spec 006; this feature only consumes it.
- **RAG / document retrieval** — separate, later feature.
- **Suggested reply generation** — separate, later feature.
- **Task creation** — separate, later feature; risk never creates a task.
- **Escalation workflow** — separate, later feature; this feature only *recommends* escalation, never performs it, and never escalates without staff/manager review.
- **Audit logging** — added by the later audit-log feature; not built here.
- **ML-based risk scoring / training pipeline** — this feature is rule-based; an ML risk model is a future generation (the `rules_version` field allows evolution).
- **Sentiment analysis as a separate score** — sentiment cues feed the rules but are not a separate stored output.
- **Real WhatsApp API integration** — out of scope entirely.
- **Calendar syncing** — out of scope.
- **Full CRM** — out of scope.
- **Auto-creating tasks / auto-escalating / auto-sending anything** — explicitly excluded.

---

## Assumptions

- A message has at most one risk assessment (one-to-one). Re-assessment overwrites the rule-generated result in place (never a `reviewed` one).
- Risk detection runs after, and depends on, intent classification (Spec 006).
- The rules engine runs synchronously after classification for MVP, wrapped so its failure cannot fail message creation/classification; the call site allows a later move to background processing.
- The rules (intent map, keyword lists, thresholds) live in a versioned configuration/module identified by `rules_version`.
- Only inbound messages are assessed.
- The detail page's "Risk / Sentiment" placeholder panel from Spec 005 is replaced by the real risk display in this feature; the remaining placeholders stay placeholders.
- `escalation_recommended` is informational metadata for the future escalation feature; it has no behavior here.
- "Reason" is a short, human-readable string (not a structured rule trace) for MVP.
