# Feature Specification: Intent Classifier

**Feature Branch**: `006-intent-classifier`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)

**Input**: User description: "The system should classify each incoming WhatsApp-style client message into one EventSense AI intent label. The result should be stored, linked to the message, and displayed in the message inbox and message detail page."

---

## Goal

Automatically classify every incoming client message into exactly one of eleven EventSense AI intent labels, with a confidence score, immediately after the message is created by the simulator. The classification is persisted, linked to its message, scoped to the message's tenant, and surfaced in both the inbox (as a badge) and the message detail page (as a label with confidence). When the model is not confident enough, the message is labelled `other` and flagged for human review so staff can correct it. This is the first AI step in the EventSense workflow — it turns raw inbound text into a structured signal that later features (risk detection, RAG, suggested replies, tasks, escalation) build on. This feature classifies only; it never creates tasks, escalations, replies, or performs retrieval.

---

## Intent Labels

The classifier predicts exactly one of these eleven labels:

| # | Label | Meaning |
|---|-------|---------|
| 1 | `booking_inquiry` | Client wants to book or asks about starting a booking |
| 2 | `pricing_request` | Client asks about prices, packages, or quotes |
| 3 | `availability_question` | Client asks whether a date/venue/service is available |
| 4 | `service_question` | Client asks what services/options are offered (non-price) |
| 5 | `urgent_change` | Client requests a time-sensitive change to an existing plan |
| 6 | `guest_count_change` | Client wants to change the number of guests |
| 7 | `complaint` | Client expresses dissatisfaction or a grievance |
| 8 | `cancellation_request` | Client wants to cancel a booking or service |
| 9 | `payment_issue` | Client raises a problem about payment, deposit, or refund |
| 10 | `human_escalation` | Client explicitly asks to speak to a human/manager |
| 11 | `other` | None of the above, or model confidence is below threshold |

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | A planner who reviews classified messages in the inbox/detail page, relies on the intent label to triage, and corrects wrong or low-confidence labels via human review. |
| **Manager** | A senior planner who reviews messages flagged `human_escalation` or low-confidence classifications, and can also correct labels. |
| **System / AI service** | The backend classification service that runs the model on each new inbound message and persists the result. Not a human actor. |

Platform Admin has no access to tenant messages or classifications.

---

## User Stories

### User Story 1 — Automatic Classification of Incoming Messages (Priority: P1)

When a new inbound client message is created by the simulator, the system automatically classifies it into one intent label with a confidence score and stores the result linked to that message. Staff do not trigger this manually — it happens as part of message creation.

**Why this priority**: This is the core capability. Without automatic classification, there is no intent signal for staff to triage on and no foundation for the downstream AI workflow. Every other story depends on a classification existing.

**Independent Test**: Inject a message "How much does your gold wedding package cost?" via the simulator as Tenant A staff. Verify that a classification result is created and linked to that message, with label `pricing_request` and a confidence score between 0 and 1. Verify no classification is created in Tenant B.

**Acceptance Scenarios**:

1. **Given** a new inbound message is created in a tenant, **When** the message is persisted, **Then** the system classifies it into exactly one of the eleven labels and stores a `ClassificationResult` linked to that message with a confidence score in `[0, 1]`.
2. **Given** a message whose predicted confidence is at or above the confidence threshold, **When** classification completes, **Then** the stored label is the predicted label and `status` is `classified`.
3. **Given** a message whose predicted confidence is below the threshold, **When** classification completes, **Then** the stored label is `other` and `status` is `needs_review`.
4. **Given** classification of a message in Tenant A, **When** the result is stored, **Then** it is scoped to Tenant A via the message's `tenant_id` and is never visible to Tenant B.

---

### User Story 2 — View Intent in Inbox and Detail Page (Priority: P1)

A staff planner sees the intent label on each conversation/message in the inbox and the full label plus confidence on the message detail page. Low-confidence / needs-review messages are visually distinguished so staff know to check them.

**Why this priority**: A classification that is stored but never shown delivers no user value. Surfacing the intent in the two existing read surfaces (inbox + detail) is what lets staff triage. Equal priority to US1 because the feature is only useful when both exist.

**Independent Test**: Classify a message as `complaint`. Open the inbox — verify the conversation/message shows a `complaint` badge. Open the detail page — verify it shows the `complaint` label and the confidence score. Classify a low-confidence message — verify it shows an `other` / "needs review" indicator in both places.

**Acceptance Scenarios**:

1. **Given** a message has a classification, **When** the inbox renders that conversation/message, **Then** the intent label is displayed as a badge.
2. **Given** a message has a classification, **When** the detail page renders the message, **Then** the intent label and its confidence score are displayed.
3. **Given** a message's classification `status` is `needs_review`, **When** it is shown in the inbox or detail page, **Then** it is visually distinguished as needing review.
4. **Given** a message has no classification yet (classification pending or failed), **When** it is shown, **Then** a neutral "unclassified" / "pending" indicator is shown rather than a wrong label.

---

### User Story 3 — Human Review and Correction of a Classification (Priority: P2)

A staff or manager user can correct a classification — change the label and/or clear the needs-review flag — when the model got it wrong or flagged it. The corrected label is stored, marked as human-reviewed, and shown going forward.

**Why this priority**: The first model (TF-IDF + Logistic Regression) will make mistakes, and low-confidence messages are deliberately routed to humans. Correction keeps the displayed intent trustworthy and produces labelled data for future model improvement. Lower than P1 because automatic classification + display already deliver standalone value.

**Independent Test**: Take a message classified as `other` / `needs_review`. As a staff user, submit a review setting the label to `pricing_request`. Verify the stored classification now has label `pricing_request`, `status` `reviewed`, records who reviewed it, and the inbox/detail page reflect the corrected label with no needs-review flag.

**Acceptance Scenarios**:

1. **Given** a message with an existing classification, **When** a staff or manager user submits a review with a valid label, **Then** the classification's label is updated, `status` becomes `reviewed`, and the reviewer identity and review time are recorded.
2. **Given** a classification with `status` `needs_review`, **When** a user reviews and confirms or changes the label, **Then** the needs-review flag is cleared.
3. **Given** a review request with a label that is not one of the eleven valid labels, **When** it is submitted, **Then** the request is rejected with a validation error and the stored classification is unchanged.
4. **Given** a review request for a message in another tenant, **When** it is submitted, **Then** it is rejected (403/404 per tenant rules) and no change is made.

---

### Edge Cases

- **Empty or whitespace-only message body**: cannot meaningfully classify → stored as label `other`, `status` `needs_review`.
- **Very long message body**: classifier processes a bounded prefix (e.g., first N characters used for vectorisation); the full body is unchanged. No error.
- **Non-English or emoji-only message**: the first model may be unconfident → likely `other` / `needs_review`. No crash; confidence reflects uncertainty.
- **Outbound (agency) message**: only **inbound** messages are classified. Outbound messages are never sent to the classifier and have no classification.
- **Duplicate classification request**: classifying a message that already has a classification re-runs and overwrites the model-generated result, but never overwrites a human `reviewed` result unless explicitly forced (the auto path skips already-reviewed messages).
- **Model file missing / fails to load**: classification fails gracefully → no result stored (or result with `status` `failed`); message still appears in inbox as "unclassified"; the message creation itself is not blocked.
- **Confidence exactly equal to threshold**: treated as confident (`>= threshold` is confident).
- **Two staff review the same classification simultaneously**: last write wins; both receive a successful response; the final stored label is consistent.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST classify every new **inbound** message into exactly one of the eleven intent labels after the message is created.
- **FR-002**: The system MUST store each classification as a `ClassificationResult` linked one-to-one to its message.
- **FR-003**: Each classification MUST include the predicted `label`, a `confidence` score in `[0, 1]`, the `model_version`, a `status`, and timestamps.
- **FR-004**: The system MUST apply a configurable confidence threshold; predictions below the threshold MUST be stored as label `other` with `status` `needs_review`.
- **FR-005**: The system MUST NOT classify outbound messages.
- **FR-006**: The system MUST expose the classification for a message via a read endpoint and surface it in the inbox and message detail page.
- **FR-007**: Staff and manager users MUST be able to review (correct/confirm) a classification, updating the label and clearing the needs-review flag.
- **FR-008**: A review MUST record the reviewing user's identity and the review timestamp, and set `status` to `reviewed`.
- **FR-009**: The system MUST reject review requests whose label is not one of the eleven valid labels (validation error).
- **FR-010**: The system MUST scope every classification to the tenant of its related message; cross-tenant access MUST be blocked.
- **FR-011**: The classifier MUST NOT create tasks, escalations, suggested replies, or perform document retrieval.
- **FR-012**: The system MUST not block or fail message creation if classification fails — message creation and classification are decoupled such that a classifier error leaves the message present and "unclassified".
- **FR-013**: The automatic classification path MUST NOT overwrite a classification whose `status` is `reviewed`.

### Key Entities

- **Message** (existing, Spec 001/003): the inbound client message being classified. Owns `tenant_id`, `body`, `direction`, `status`. One message has at most one classification.
- **ClassificationResult** (new): the stored output of the classifier for one message. Holds `label`, `confidence`, `model_version`, `status`, reviewer info, and timestamps. Scoped to a tenant via its message.
- **IntentLabel** (enum): the eleven valid labels.
- **ClassificationStatus** (enum): lifecycle of a classification (`classified`, `needs_review`, `reviewed`, `failed`).

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| New inbound message | Message Simulator (Spec 003) | Triggers automatic classification on creation |
| Message body text | `messages.body` | The text the model vectorises and classifies |
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by client |
| Manual classify trigger | `POST /api/messages/{id}/classify` | Re-runs classification on a specific message (idempotent overwrite of model results) |
| Review submission | `PATCH /api/messages/{id}/classification/review` | Staff/manager corrected label |
| Confidence threshold | Backend configuration | Cutoff below which label becomes `other` / `needs_review` |

---

## Outputs

| Output | Description |
|--------|-------------|
| Stored classification | A `ClassificationResult` row linked to the message, tenant-scoped |
| Intent label | One of the eleven labels, with confidence score |
| Inbox badge | Intent label shown per conversation/message in the inbox |
| Detail page label | Intent label + confidence + review state on the message detail page |
| Needs-review flag | Visual indicator on low-confidence / unreviewed classifications |
| Review record | Reviewer identity + timestamp stored on the classification |
| 403 / 404 | Returned for cross-tenant or platform-admin access attempts |
| 422 | Returned for invalid review label or malformed request |

---

## Main Workflow

1. **Client message arrives** — The simulator (Spec 003) creates a new inbound message in a tenant.
2. **Classification triggered** — Immediately after the message is persisted, the system invokes the classification service for that message.
3. **Model predicts** — The production model (a **Calibrated Linear SVM**; baseline: TF-IDF + Logistic Regression) vectorises the message body and predicts a label with a calibrated probability/confidence. See **Advanced Requirements Update** below for model selection and artifact details.
4. **Threshold applied** — If confidence ≥ threshold, the predicted label is kept and `status` = `classified`. Otherwise label = `other` and `status` = `needs_review`.
5. **Result stored** — A `ClassificationResult` is saved, linked to the message, scoped to the tenant.
6. **Surfaced to users** — The label appears as a badge in the inbox and as a label + confidence on the message detail page. Needs-review items are visually distinguished.
7. **Optional human review** — Staff or manager corrects/confirms the label; the classification becomes `reviewed` with reviewer + timestamp; the UI updates.

---

## Alternative Workflows

### Manual Re-Classification

1. A staff user (or a developer during testing) calls `POST /api/messages/{id}/classify`.
2. The service re-runs the model on that message.
3. If the message's current classification is `reviewed`, the manual auto-classify does not overwrite it unless explicitly forced; otherwise the result is overwritten and returned.

### Low-Confidence Routing

1. A message is classified but the top-label confidence is below threshold.
2. The stored label is `other`, `status` = `needs_review`.
3. The inbox and detail page show a "needs review" indicator.
4. A human reviews and sets the correct label (US3).

### Classifier Failure

1. The model fails to load or errors during prediction.
2. No model label is produced; the message is left unclassified (or a `failed` status result is recorded).
3. Message creation is unaffected — the message still appears in the inbox as "unclassified".
4. A later `POST /classify` can retry once the model is available.

### Cross-Tenant Access Attempt

1. Tenant B staff requests the classification of a Tenant A message.
2. The backend derives the tenant from the JWT, sees the message is not in that tenant, and returns 404 (not found in tenant) or 403 per the established rules.
3. No classification data is exposed.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | A new inbound message receives exactly one classification with a label and confidence in [0,1] | Integration test: create message → assert one ClassificationResult linked, label in enum, 0 ≤ confidence ≤ 1 |
| AC-02 | Confidence ≥ threshold stores the predicted label with status `classified` | Integration test: high-confidence message → assert label = predicted, status = classified |
| AC-03 | Confidence < threshold stores label `other` with status `needs_review` | Integration test: force low confidence → assert label = other, status = needs_review |
| AC-04 | Outbound messages are never classified | Integration test: create outbound message → assert no ClassificationResult |
| AC-05 | Classification is tenant-scoped; Tenant B cannot read Tenant A classification | Integration test: classify in A; GET as B → 404/403, no data |
| AC-06 | `GET /api/messages/{id}/classification` returns the stored classification for an in-tenant message | Integration test: assert 200 + correct fields |
| AC-07 | `GET` returns 404 when the message has no classification | Integration test: unclassified message → 404 with NO_CLASSIFICATION |
| AC-08 | `POST /api/messages/{id}/classify` (re)runs classification and returns the result | Integration test: assert 200 + result; re-run overwrites model result |
| AC-09 | `PATCH .../classification/review` updates label, sets status `reviewed`, records reviewer + time | Integration test: review → assert label updated, status reviewed, reviewer + reviewed_at set |
| AC-10 | Review with an invalid label is rejected (422) and stored classification unchanged | Integration test: PATCH bad label → 422; assert no change |
| AC-11 | Platform Admin is blocked from all classification endpoints (403) | Integration test: admin token → 403 INSUFFICIENT_ROLE |
| AC-12 | Auto-classification does not overwrite a `reviewed` classification | Integration test: review a message → POST /classify → assert reviewed label preserved |
| AC-13 | Intent label is displayed in the inbox and detail page; needs-review is visually distinct | Frontend test: render inbox/detail → assert badge present; needs-review indicator present |
| AC-14 | Classifier failure does not block message creation | Integration test: simulate model error → assert message created, no crash, message is "unclassified" |
| AC-15 | The classifier produces no tasks, escalations, replies, or retrieval calls | Code/integration test: assert no task/escalation/reply/RAG side effects occur |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | `messages` table, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT auth, `staff`/`manager` roles, Platform Admin blocked |
| Spec 003 — Message Simulator | Required | Creates inbound messages; classification hooks into this creation path |
| Spec 004 — Message Inbox | Required | Surface for the intent badge |
| Spec 005 — Message Detail Page | Required | Surface for the intent label + confidence (replaces the AI Intent placeholder panel) |
| Calibrated Linear SVM model (baseline: TF-IDF + Logistic Regression) | Required | Production classifier; trained **offline**, saved as a **joblib** artifact + **model card**, loaded by the backend. See Advanced Requirements Update. |

---

## AI Behavior

- **Model**: TF-IDF vectoriser + **Calibrated Linear SVM** classifier (the final selected EventSense model; the earlier TF-IDF + Logistic Regression is retained as the documented **baseline**). It outputs a calibrated probability distribution over the eleven labels; the top label and its probability become the prediction and confidence. Model selection, training, artifact, and documentation requirements are in the **Advanced Requirements Update** section.
- **Single label**: exactly one label is stored per message (the argmax), never multiple.
- **Confidence threshold**: a configurable cutoff (default documented in research). Below it → `other` + `needs_review`. This makes the model conservative and routes uncertainty to humans.
- **Determinism**: the same model version + same input produces the same label and confidence (no randomness at inference).
- **Versioning**: every result records the `model_version` so results can be compared across retrains and reviewed data can be used to improve future models.
- **Human-in-the-loop**: the model never takes an action. It only labels. Humans review and correct. No task creation, escalation, reply, or retrieval is triggered by the classifier.
- **No auto-actions / no auto-send**: the classifier does not send replies and does not auto-escalate. Those are separate, later, human-reviewed features.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the authenticated JWT (and, for auto-classification, from the message's tenant). No `tenant_id` is accepted from the client. |
| **SR-02: Classification inherits message tenant** | A `ClassificationResult` is bound to its message's tenant. Tenant A can never read or modify Tenant B classifications. |
| **SR-03: Role restriction** | Only `staff` and `manager` may read or review classifications. Platform Admin receives 403. Unauthenticated requests receive 401. |
| **SR-04: Not Found vs Forbidden** | A message that does not exist in the caller's tenant returns 404; a message that exists in another tenant returns 403 (consistent with Spec 005). Classification endpoints never confirm cross-tenant content. |
| **SR-05: Review authorisation** | Only `staff` and `manager` of the message's tenant may submit a review. The reviewer identity recorded is the authenticated user. |
| **SR-06: No model data leakage** | The classifier operates only on the message body within the tenant boundary. No cross-tenant text is ever used for inference, and no training/inference call sends one tenant's data into another's context. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Model artifact missing or fails to load | Classification skipped; message left unclassified; message creation succeeds; error logged. `POST /classify` returns 503 `MODEL_UNAVAILABLE`. |
| Prediction raises an exception | No result stored (or `status` `failed`); message creation unaffected; error logged. |
| Empty/whitespace message body | Stored as `other` + `needs_review` (no crash). |
| `GET` classification for a message with none | 404 `NO_CLASSIFICATION`. |
| `PATCH` review with invalid label | 422 validation error; no change. |
| `PATCH`/`GET`/`POST` for cross-tenant message | 404/403 per SR-04; no data exposed, no change. |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE`. |
| Re-classify an already-`reviewed` message via auto path | No overwrite; reviewed label preserved (FR-013). |

---

## Edge Cases (summary)

- Empty/whitespace body → `other` / `needs_review`.
- Very long body → bounded prefix vectorised; no error.
- Non-English / emoji-only → likely `other` / low confidence; no crash.
- Outbound message → never classified.
- Duplicate classify → overwrites model result, never a reviewed result.
- Confidence == threshold → treated as confident.
- Concurrent reviews → last write wins; consistent final state.

---

## Out of Scope

- **Risk detection** — separate feature; the classifier does not score risk.
- **RAG / document retrieval** — separate, later feature.
- **Suggested reply generation** — separate, later feature.
- **Task creation** — separate, later feature.
- **Escalation workflow** — separate, later feature; `human_escalation` is only a *label*, it triggers no escalation here.
- **Audit logging** — classification actions will be logged by the later audit-log feature; this feature does not build the audit system.
- **Model training pipeline / retraining UI** — the trained artifact is assumed available; training tooling is out of scope (only loading + inference + versioning here).
- **Multi-label classification** — exactly one label per message.
- **Real WhatsApp API integration** — out of scope entirely.
- **Calendar syncing** — out of scope.
- **Full CRM** — out of scope.
- **Auto-sending any reply or auto-taking any action** — explicitly excluded.

---

## Assumptions

- A trained model artifact (vectoriser + **Calibrated Linear SVM** classifier + label mapping; baseline TF-IDF + Logistic Regression also retained) is **trained offline** and saved as a **joblib** artifact available to the backend at a known path, versioned by `model_version` and traceable by content hash.
- The confidence threshold has a sensible documented default and is configurable without code changes.
- Classification runs synchronously within the message-creation request flow for MVP (a background queue is a post-MVP optimisation), but is wrapped so its failure cannot fail message creation.
- Each message has at most one classification (one-to-one). Re-classification overwrites the existing model-generated result in place.
- Only inbound messages are classified; outbound messages are agency-authored and need no intent.
- The detail page's "AI Intent" placeholder panel from Spec 005 is replaced by the real intent display in this feature; the other five placeholder panels remain placeholders.
- Confidence is the model's top-class probability in `[0, 1]`.

---

## Advanced Requirements Update (Updated Brief — 2026-06)

The updated brief finalizes the production intent model and the artifacts that document it. TF-IDF + Logistic Regression (the model described in the body) is retained as the **baseline**; the **final selected model is a Calibrated Linear SVM**. Inference, threshold routing, tenant scoping, the review flow, and all existing FR/AC are unchanged — only the underlying estimator and its documentation artifacts change.

### Model Selection

- **Baseline**: TF-IDF vectoriser → `LogisticRegression` (multi-class, `predict_proba`). Metrics recorded in `data/intent_classifier/reports/baseline_metrics.json`.
- **Final selected model**: TF-IDF vectoriser → **Calibrated Linear SVM** (`LinearSVC` wrapped in `CalibratedClassifierCV` so calibrated probabilities back the confidence threshold). Selected for best held-out macro-F1 while keeping deterministic, CPU-only, small-artifact inference.
- Both are scikit-learn pipelines; the calibrated SVM exposes `predict_proba`, so the existing confidence-threshold routing (`>= INTENT_CONFIDENCE_THRESHOLD` → label, else `other` / `needs_review`) is preserved unchanged.

### Functional Requirements (additional)

- **FR-014**: The system MUST serve the **Calibrated Linear SVM** as the production classifier, with TF-IDF + Logistic Regression retained as the documented baseline for comparison.
- **FR-015**: The model MUST be **trained offline** (out-of-band script/notebook; no training in the request path) and saved as a **joblib** artifact (vectoriser + calibrated classifier + label mapping) loaded by the backend at startup.
- **FR-016**: The artifact MUST be accompanied by a **model card** documenting the algorithm, training-data reference (DATA_CARD / Spec 015), intended use, the eleven labels, evaluation metrics, latency, limitations, and the confidence-threshold behavior.
- **FR-017**: The backend MUST record the loaded artifact's **content hash** (e.g., SHA-256) and `model_version` at load time so the served model is traceable and provably matches the evaluated artifact.
- **FR-018**: The reports / model card MUST document **evaluation metrics** (accuracy, macro-F1, weighted-F1, per-class P/R/F1, confusion matrix — final vs. baseline) and **inference latency** (per message), produced by the offline training/eval run and consumed by Spec 015.

### Acceptance Criteria (additional)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-16 | Production classifier is the Calibrated Linear SVM; baseline LogReg metrics recorded for comparison | Reports review (baseline + final metrics) |
| AC-17 | Model loaded from a joblib artifact; backend records its content hash + `model_version` at load | Integration test: assert hash + version recorded |
| AC-18 | A MODEL_CARD documenting algorithm, metrics, latency, labels, and limitations exists alongside the artifact | Artifact/doc review |
| AC-19 | Calibrated probabilities feed the existing confidence threshold unchanged (low-confidence → `other`/`needs_review`) | Integration test (existing AC-02/AC-03 still pass with the SVM) |

### Artifacts

- Trained artifact: `data/intent_classifier/` (joblib model: vectoriser + calibrated SVM + label map).
- Reports: `data/intent_classifier/reports/` — `baseline_metrics.json` (TF-IDF + LogReg, present), final metrics JSON, confusion matrix.
- Model card: `data/intent_classifier/reports/MODEL_CARD.md` (algorithm, metrics, latency, artifact hash, `model_version`, limitations).

> `INTENT_CLASSIFIER_ARTIFACT_PATH` / `INTENT_CLASSIFIER_MODEL_VERSION` (config) point at the **calibrated SVM** artifact in production; the baseline artifact remains available for comparison.
