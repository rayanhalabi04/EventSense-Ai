# Research: Intent Classifier

**Branch**: `006-intent-classifier` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Model — TF-IDF + Logistic Regression (first generation)

**Decision**: Use a scikit-learn pipeline of `TfidfVectorizer` → `LogisticRegression` for multi-class (eleven labels) single-label classification. The model exposes `predict_proba`; the prediction is the argmax label and the confidence is that class's probability.

**Rationale**:
- Specified by the project's technology direction as the first model.
- Fast, deterministic, CPU-only inference — no GPU, no external API, fits synchronous in-request classification for MVP.
- `predict_proba` gives a natural confidence in `[0, 1]` for the threshold routing the spec requires.
- Small artifact, trivially versioned and loaded once at startup.

**Alternatives considered**:
- Transformer / LLM classifier: higher accuracy but heavier, slower, and non-deterministic; deferred to a future model generation. The data model stamps `model_version` so a swap is non-breaking.
- Rule/keyword matching only: brittle across the eleven nuanced labels; rejected as the primary classifier (could be a future fallback).

---

## Decision 2: Confidence Threshold and Low-Confidence Routing

**Decision**: A single configurable threshold `INTENT_CONFIDENCE_THRESHOLD`, default **0.45**. If the top-class probability `>= threshold`, store the predicted label with `status = classified`; otherwise store label `other` with `status = needs_review`. Equality counts as confident.

**Rationale**:
- The spec mandates that low-confidence predictions become `other` and are routed to humans. A configurable cutoff makes the model conservative and keeps the displayed intent trustworthy.
- 0.45 is a sensible starting point for an 11-class problem (chance ≈ 0.09); it can be tuned from review data without code changes.
- Threshold is applied in the **service** layer, not the model, so it is independently testable and tunable.

**Alternatives considered**:
- Per-label thresholds: more precise but premature without evaluation data; deferred.
- Margin-based (top1 − top2): more robust but more complex; revisit after collecting reviewed data.

---

## Decision 3: One-to-One Storage with Reviewed-Protection

**Decision**: `classification_results` has a UNIQUE `message_id` (one classification per message). Re-classification upserts the row. The **automatic** path refuses to overwrite a row whose `status = reviewed`; the manual `POST /classify` may overwrite only with an explicit `force=true`.

**Rationale**:
- A message has exactly one current intent — one-to-one keeps reads simple and the inbox/detail joins cheap.
- Human corrections are ground truth; auto re-runs must never clobber them (FR-013). Protecting `reviewed` preserves trust and yields clean labelled data for future training.

**Alternatives considered**:
- Append-only history table (many results per message): good for auditability/retrain analysis, but heavier than MVP needs. The single-row design keeps `created_at`/`updated_at` + `model_version`; a history table is a clean post-MVP add (audit-log feature territory).

---

## Decision 4: Synchronous, Fail-Safe Classification Hook

**Decision**: Classification runs synchronously right after the inbound message is committed in the Spec 003 creation path, wrapped in a `try/except` that logs and swallows any classifier error so it can never fail message creation. The call site is a single function (`classify_message`) so it can later be dispatched to a background worker without changing the API.

**Rationale**:
- MVP simplicity: no queue/broker to operate; the model is fast enough for in-request inference.
- FR-012 requires message creation to never fail because of the classifier — isolation via the wrapper guarantees this.
- Encapsulating the hook in one function preserves a clean migration path to async (Celery/RQ/FastAPI BackgroundTasks) post-MVP.

**Alternatives considered**:
- Background queue now: more robust under load and isolates latency, but adds infrastructure not justified for the demo scale. Deferred.
- DB trigger / event: hides logic in the DB and complicates tenant/model handling; rejected.

---

## Decision 5: Tenant Scoping (inherit from message; 404 vs 403)

**Decision**: Every endpoint resolves the message first using the same 404-vs-403 logic as Spec 005 (fetch by id; `None` → 404; tenant mismatch → 403), then operates on its classification. `classification_results.tenant_id` is denormalised from the message for fast tenant-scoped queries (e.g., "all needs-review in my tenant").

**Rationale**:
- Consistency with the established cross-tenant contract (Spec 005 SR-04) — no new security model to reason about.
- Denormalising `tenant_id` avoids a join to `messages` for tenant filters and lets indexes serve needs-review/analytics queries directly. It is safe because a message never changes tenant.

**Alternatives considered**:
- Derive tenant only via join to `messages` every time: correct but slower for list/analytics queries; the denormalised column is cheap and write-once.

---

## Decision 6: Enums as Constrained Strings

**Decision**: Persist `IntentLabel` and `ClassificationStatus` as application-level string enums stored in VARCHAR columns (with a CHECK or app-level validation), not native PostgreSQL `ENUM` types.

**Rationale**:
- The eleven labels may evolve as the product matures; native PG enums require a migration to add a value, while VARCHAR + app validation lets the model/label set grow with less migration churn.
- Pydantic + SQLAlchemy enforce validity at the application boundary (review requests with invalid labels → 422).

**Alternatives considered**:
- Native PG enum: stronger DB-level guarantees but rigid; rejected for label evolvability.
- Integer codes: compact but opaque in queries/debugging; rejected.

---

## Decision 7: Inference Input Bounding and Normalisation

**Decision**: Before vectorising, normalise the body (lowercase, strip) and truncate to `INTENT_MAX_CHARS` (default **2000**). Empty/whitespace bodies short-circuit to `other` + `needs_review` without calling the model.

**Rationale**:
- TF-IDF is bag-of-words — a bounded prefix captures intent while protecting against pathological very-long inputs (edge case in spec).
- Empty bodies cannot be classified meaningfully; routing them to needs-review is honest and avoids a misleading label.

---

## Decision 8: Surfacing in Inbox + Detail (no extra round-trips)

**Decision**: Extend the existing Spec 004 inbox-item response and Spec 005 detail message response with a compact `classification` object (`label`, `confidence`, `status`) rather than requiring the frontend to call `GET /classification` per message.

**Rationale**:
- The inbox already lists conversations and the detail already lists messages; piggy-backing the intent avoids N extra requests and keeps the badge instantly available.
- The standalone `GET /api/messages/{id}/classification` still exists for targeted reads and for the review flow.

**Alternatives considered**:
- Frontend fetches each classification separately: simple but N+1 network calls; rejected for the inbox.

---

## Decision 9: Model Unavailability Handling

**Decision**: A startup loader attempts to load the artifact. If absent/corrupt, the model is marked unavailable: auto-classification is skipped (messages still created, shown "unclassified"), and `POST /classify` returns **503 `MODEL_UNAVAILABLE`**. A small demo artifact + `train_demo.py` are provided so local dev always has a working model.

**Rationale**:
- Decouples deployment of code from availability of the model file; the app stays up and usable even without a model.
- The demo artifact makes the feature testable end-to-end locally without a training pipeline (which is out of scope).

---

## Decision 10: Explicit Non-Goals (enforced in design)

**Decision**: The classifier produces only a label + confidence. It performs **no** task creation, escalation, reply generation, or document retrieval, and never auto-sends anything. `human_escalation` is a label only — it triggers no escalation in this feature.

**Rationale**: Direct scope boundary from the feature request. Keeping the classifier a pure labelling function makes it composable: later features consume the label; they are not entangled with it. AC-15 asserts the absence of these side effects.

---

## Resolved Configuration Defaults

| Setting | Default | Purpose |
|---------|---------|---------|
| `INTENT_MODEL_PATH` | `backend/models/intent/` | Location of the artifact bundle |
| `INTENT_MODEL_VERSION` | `tfidf-logreg-v1` | Stamped on every result |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.45` | Below → `other` + `needs_review` |
| `INTENT_MAX_CHARS` | `2000` | Input truncation bound |
