# Requirements Checklist: Intent Classifier

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI behavior, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Every new **inbound** message is automatically classified after creation (FR-001)
- [ ] Exactly one `ClassificationResult` is stored per message, linked one-to-one (FR-002)
- [ ] Each result stores `label`, `confidence` ∈ [0,1], `model_version`, `status`, timestamps (FR-003)
- [ ] Predictions below the confidence threshold are stored as `other` + `needs_review` (FR-004)
- [ ] Outbound messages are never classified (FR-005)
- [ ] Classification is readable via API and surfaced in inbox + detail page (FR-006)
- [ ] Staff/manager can review (correct/confirm) a classification (FR-007)
- [ ] A review records reviewer identity + timestamp and sets `status=reviewed` (FR-008)
- [ ] Invalid review labels are rejected with a validation error (FR-009)
- [ ] Classifier creates no tasks, escalations, replies, or retrieval (FR-011, AC-15)
- [ ] Message creation never fails due to a classifier error (FR-012, AC-14)
- [ ] Auto-classification never overwrites a `reviewed` result (FR-013, AC-12)

---

## AI Requirements

- [ ] Model is TF-IDF + Logistic Regression (first-generation), loaded once at startup
- [ ] Exactly one label (argmax) is predicted per message — no multi-label output
- [ ] Confidence is the top-class probability in [0, 1]
- [ ] Configurable confidence threshold; `>= threshold` is treated as confident
- [ ] Low confidence routes to `other` + `needs_review`
- [ ] Inference is deterministic for the same model version + input
- [ ] Every result records the `model_version`
- [ ] Empty/whitespace body → `other` + `needs_review` without crashing
- [ ] Input is bounded/truncated before vectorisation (no failure on very long bodies)
- [ ] Model never auto-sends a reply or auto-takes any action
- [ ] `human_escalation` is a label only — it triggers no escalation here

---

## Security Requirements

- [ ] `tenant_id` is always derived from the JWT / the message's tenant — never from the client (SR-01)
- [ ] Each classification inherits and is scoped to its message's tenant (SR-02)
- [ ] Only `staff` and `manager` may read/review; Platform Admin → 403 (SR-03, AC-11)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent message → 404; cross-tenant message → 403 (SR-04, AC-05)
- [ ] Only staff/manager of the message's tenant may review; reviewer = authenticated user (SR-05)
- [ ] No cross-tenant text is ever used for inference (SR-06)

---

## API Requirements

- [ ] `POST /api/messages/{message_id}/classify` runs/re-runs classification and returns the result (AC-08)
- [ ] `POST /classify` respects `force` flag; preserves `reviewed` unless forced
- [ ] `POST /classify` on outbound → 409 `NOT_CLASSIFIABLE`
- [ ] `POST /classify` when model unavailable → 503 `MODEL_UNAVAILABLE`
- [ ] `GET /api/messages/{message_id}/classification` returns the stored result (AC-06)
- [ ] `GET` returns 404 `NO_CLASSIFICATION` when none exists (AC-07)
- [ ] `PATCH /api/messages/{message_id}/classification/review` updates label + sets reviewed (AC-09)
- [ ] `PATCH review` with invalid label → 422, no change (AC-10)
- [ ] All endpoints enforce role + tenant resolution (404/403) consistently
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] Inbox + detail responses embed a compact `classification` summary (no N+1)

---

## Data Requirements

- [ ] `classification_results` table created via Alembic migration
- [ ] `message_id` is a UNIQUE FK with `ON DELETE CASCADE` (one-to-one)
- [ ] `tenant_id` denormalised + indexed for tenant-scoped queries
- [ ] `IntentLabel` enum has exactly the eleven specified labels
- [ ] `ClassificationStatus` enum: `classified`, `needs_review`, `reviewed`, `failed`
- [ ] `confidence` is nullable (NULL when `failed`)
- [ ] `reviewed_by` / `reviewed_at` populated only on human review
- [ ] Index on `(tenant_id, status)` for needs-review queries
- [ ] State transitions enforce that auto path cannot move out of `reviewed`

---

## Testing Requirements

- [ ] Integration: auto-classify on inbound creation (AC-01, AC-02, AC-03)
- [ ] Integration: outbound not classified (AC-04)
- [ ] Integration: tenant isolation A↔B (AC-05)
- [ ] Integration: `GET` returns result / 404 when none (AC-06, AC-07)
- [ ] Integration: `POST /classify` runs + overwrites model result (AC-08)
- [ ] Integration: `PATCH review` updates + records reviewer (AC-09); invalid label 422 (AC-10)
- [ ] Integration: Platform Admin blocked (AC-11)
- [ ] Integration: auto path does not overwrite `reviewed` (AC-12)
- [ ] Integration: classifier failure does not block message creation (AC-14)
- [ ] Integration: no task/escalation/reply/RAG side effects (AC-15)
- [ ] Unit: threshold routing, empty body, bounded input, determinism, `model_version` stamping
- [ ] Frontend: intent badge in inbox + label/confidence in detail; needs-review distinct (AC-13)
- [ ] Quickstart end-to-end walkthrough passes

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No risk detection
- [ ] No RAG / document retrieval
- [ ] No suggested reply generation
- [ ] No task creation
- [ ] No escalation workflow
- [ ] No audit-log system (logging is added by the later audit feature)
- [ ] No model training pipeline / retraining UI (only load + infer + version)
- [ ] No real WhatsApp API, no calendar syncing, no full CRM
- [ ] No auto-send / auto-action of any kind

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order).
