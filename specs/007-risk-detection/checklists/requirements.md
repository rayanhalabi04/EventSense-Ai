# Requirements Checklist: Risk Detection

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (triage) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI/rule behavior, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Risk is assessed automatically after intent classification completes (FR-001)
- [ ] Exactly one `RiskAssessment` is stored per message, linked one-to-one (FR-002)
- [ ] Each assessment stores level, primary flag (or none for clearly-low), non-empty reason, `escalation_recommended`, `rules_version`, status, timestamps (FR-003)
- [ ] Risk detection is a separate component from the classifier (FR-004)
- [ ] Baseline derives from intent; rules may raise but never silently lower an intent-implied high (FR-005, AC-18)
- [ ] `escalation_recommended` is set for high but no escalation is performed (FR-006)
- [ ] No tasks, escalations, replies, or retrieval are produced (FR-007, AC-16)
- [ ] Assessment is readable via API and surfaced in inbox + detail page (FR-008)
- [ ] Staff/manager can review (correct/confirm) an assessment (FR-009)
- [ ] A review records reviewer identity + timestamp and sets `status=reviewed` (FR-010)
- [ ] Invalid review level/flag is rejected (FR-011)
- [ ] Assessment is tenant-scoped; cross-tenant access blocked (FR-012)
- [ ] Auto re-assessment never overwrites a `reviewed` assessment (FR-013, AC-14)
- [ ] Risk failure never blocks message creation or classification (FR-014)

---

## Risk-Rule Requirements

- [ ] Intent baseline map matches the spec table (booking/pricing/availability/service → low)
- [ ] `urgent_change`, `complaint`, `cancellation_request`, `human_escalation` → high with matching flag (AC-03)
- [ ] `guest_count_change` → medium for small/neutral, high for large delta / urgency (AC-04)
- [ ] `payment_issue` → medium normally, high for "paid but unconfirmed"/refund/urgency (AC-05)
- [ ] `other` → medium with flag `unsupported_or_unclear_request` (AC-06)
- [ ] Exactly one primary flag stored; compound cases resolved by a deterministic flag-priority order
- [ ] Keyword lists cover urgency, refund/payment, cancellation, complaint, escalation terms
- [ ] Guest-count delta parsing drives medium vs high via configurable thresholds
- [ ] `escalation_recommended` true for high (and explicit escalation), false for low (AC-07)
- [ ] Every assessment includes a non-empty human-readable reason
- [ ] Engine is deterministic and stamps `rules_version`
- [ ] Modifiers are monotonic (raise only) — no silent lowering of an implied high (AC-18)
- [ ] Empty/unclear/low-confidence input → at least medium + unclear flag (no crash)

---

## Security Requirements

- [ ] `tenant_id` is always derived from the JWT / message tenant — never from the client (SR-01)
- [ ] Each assessment inherits and is scoped to its message's tenant (SR-02)
- [ ] Only `staff` and `manager` may read/review; Platform Admin → 403 (SR-03, AC-15)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent message → 404; cross-tenant message → 403 (SR-04, AC-08)
- [ ] Only staff/manager of the message's tenant may review; reviewer = authenticated user (SR-05)
- [ ] No cross-tenant data is read during rule evaluation (SR-06)
- [ ] Engine performs no autonomous action (SR-07, AC-16)

---

## API Requirements

- [ ] `POST /api/messages/{message_id}/risk-assessment` runs/re-runs rules and returns the result (AC-11)
- [ ] `POST` returns 409 `NOT_CLASSIFIED` when no classification exists (AC-11)
- [ ] `POST` returns 409 `NOT_CLASSIFIABLE` for outbound messages
- [ ] `POST` respects `force`; preserves `reviewed` unless forced
- [ ] `GET /api/messages/{message_id}/risk-assessment` returns the stored assessment (AC-09)
- [ ] `GET` returns 404 `NO_RISK_ASSESSMENT` when none exists (AC-10)
- [ ] `PATCH /api/messages/{message_id}/risk-assessment/review` updates level/flag/reason + marks reviewed (AC-12)
- [ ] `PATCH review` with invalid level/flag → 422, no change (AC-13)
- [ ] All endpoints enforce role + tenant resolution (404/403) consistently
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] Inbox + detail responses embed a compact `risk` summary (no N+1)

---

## Data Requirements

- [ ] `risk_assessments` table created via Alembic migration
- [ ] `message_id` is a UNIQUE FK with `ON DELETE CASCADE` (one-to-one)
- [ ] `tenant_id` denormalised + indexed for tenant-scoped queries
- [ ] `RiskLevel` enum: `low`, `medium`, `high`
- [ ] `RiskFlag` enum has exactly the seven specified flags
- [ ] `RiskAssessmentStatus` enum: `assessed`, `reviewed`, `failed`
- [ ] `reason` is NOT NULL; `flag` nullable (only for clearly-low)
- [ ] `escalation_recommended` boolean stored
- [ ] `reviewed_by` / `reviewed_at` populated only on human review
- [ ] Index on `(tenant_id, level)` and `(tenant_id, escalation_recommended)`
- [ ] State transitions enforce that the auto path cannot move out of `reviewed`

---

## Testing Requirements

- [ ] Unit: each intent baseline level/flag
- [ ] Unit: each keyword modifier (urgency, refund/payment, cancellation, complaint, escalation)
- [ ] Unit: guest-count delta parsing (small→medium, large→high)
- [ ] Unit: compound escalation + flag-priority resolution
- [ ] Unit: reason composition, determinism, `rules_version` stamping, monotonic no-lower
- [ ] Integration: auto-assess after classification + baseline levels (AC-01, AC-02)
- [ ] Integration: high-risk intents + flags (AC-03)
- [ ] Integration: guest-count medium vs high (AC-04); payment medium vs high (AC-05); other → medium (AC-06)
- [ ] Integration: `escalation_recommended` per level (AC-07)
- [ ] Integration: tenant isolation A↔B (AC-08)
- [ ] Integration: `GET` result / 404 (AC-09, AC-10)
- [ ] Integration: `POST` runs + 409 when not classified (AC-11)
- [ ] Integration: `PATCH review` updates + records reviewer (AC-12); invalid 422 (AC-13)
- [ ] Integration: auto path preserves `reviewed` (AC-14); Platform Admin 403 (AC-15)
- [ ] Integration: no task/escalation/reply/RAG side effects (AC-16)
- [ ] Frontend: badge + panel render level/flag/reason; high emphasised (AC-17)
- [ ] Quickstart: all five demo messages produce expected levels/flags

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No intent classification (consumed from Spec 006, not re-implemented)
- [ ] No RAG / document retrieval
- [ ] No suggested reply generation
- [ ] No task creation
- [ ] No escalation workflow (only an informational recommendation flag)
- [ ] No auto-escalation without staff/manager review
- [ ] No audit-log system (logging added by the later audit feature)
- [ ] No ML risk model / training pipeline (rule-based only; `rules_version` allows future evolution)
- [ ] No standalone sentiment score (sentiment cues feed rules only)
- [ ] No real WhatsApp API, no calendar syncing, no full CRM
- [ ] No auto-creating tasks / auto-sending anything

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build and unit-test the pure rule engine (`risk/engine.py` + `risk/rules.py`) first.
