# Research: Risk Detection

**Branch**: `007-risk-detection` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Rule-Based Engine (not ML) for the First Generation

**Decision**: Implement risk detection as a deterministic rule engine: intent→risk baseline mapping + keyword lists + simple business logic. No ML model in this feature.

**Rationale**:
- The feature goal explicitly calls for intent-based rules, keyword rules, and simple business logic.
- Risk is a triage signal where explainability matters — a rule engine produces a clear, human-readable reason directly, satisfying the "human-readable reason" requirement.
- Deterministic rules are trivially unit-testable across the spec's intent→risk examples.
- Keeps risk fully separate from the classifier (FR-004) — it consumes the classification but adds no model.

**Alternatives considered**:
- ML risk classifier: better at nuance but opaque (hard to produce a faithful reason), needs labelled risk data we don't have yet, and would blur the line with Spec 006. Deferred; the `rules_version` field allows a future ML generation to slot in.
- Pure intent passthrough (level = intent baseline only): too coarse — misses urgency/refund/compound signals the spec calls out. Rejected.

---

## Decision 2: Baseline-from-Intent + Monotonic Raising Modifiers

**Decision**: Derive a baseline (level, flag) from the intent, then apply ordered keyword/business modifiers that may only **raise** the level (low→medium→high), never lower it below an intent-implied high.

**Rationale**:
- Matches the spec's mapping table and the explicit rule "rules may raise risk; do not silently lower an intent-implied high" (FR-005, AC-18).
- Monotonic raising is safe-by-default: when signals conflict, the system errs toward more attention, which is the correct bias for client-facing risk.
- Ordered modifiers + a flag-priority list make compound cases deterministic.

**Alternatives considered**:
- Additive scoring (sum weights → bucket): flexible but harder to explain and to keep monotonic; the reason becomes a number, not a sentence. Deferred; can back a future ML/scoring generation.
- Allowing modifiers to lower risk: rejected — risks hiding genuine high-risk cases.

---

## Decision 3: Single Level + Single Primary Flag

**Decision**: Store exactly one `level` and one primary `flag` (the highest-priority matched flag). Secondary signals are mentioned in the `reason` but not stored as separate flags.

**Rationale**:
- A single primary flag keeps the inbox badge and detail panel simple and unambiguous for triage.
- A flag-priority order (e.g., `human_escalation_needed` > `cancellation_risk` > `complaint` > `payment_risk` > `urgent_change` > `guest_count_change` > `unsupported_or_unclear_request`) resolves compound cases deterministically.
- The reason carries the nuance for the human without a multi-flag data model.

**Alternatives considered**:
- Multi-flag array: richer but complicates UI and review; deferred. The reason string covers the need for MVP.

---

## Decision 4: Runs After Classification; Chained Fail-Safe Hook

**Decision**: Risk assessment is chained after a successful intent classification in the same post-message-creation hook, wrapped so a risk error cannot fail message creation or classification. The manual `POST /risk-assessment` requires an existing classification (409 `NOT_CLASSIFIED` otherwise).

**Rationale**:
- The MVP workflow is classify → risk; the baseline needs the intent, so risk must run after classification.
- FR-014 requires that risk failure never breaks upstream steps — the fail-safe wrapper guarantees message + classification remain intact.
- Requiring a classification for manual assessment keeps the baseline well-defined and surfaces ordering mistakes clearly (409) instead of guessing.

**Alternatives considered**:
- Run risk independently of classification (text-only): loses the intent baseline the spec is built around; rejected.
- Background queue now: more robust under load but adds infra not justified at demo scale; the single chained call site allows a later async move without API change.

---

## Decision 5: One-to-One Storage with Reviewed-Protection

**Decision**: `risk_assessments.message_id` is UNIQUE (one assessment per message). Re-assessment upserts; the **auto** path never overwrites a `reviewed` row, and manual `POST` overwrites a `reviewed` row only with explicit `force=true`.

**Rationale**:
- One current risk per message keeps reads/joins simple and the inbox/detail badge unambiguous.
- Human corrections are ground truth and must survive rule re-runs (FR-013) — protecting `reviewed` preserves trust and yields clean feedback for rule tuning.

**Alternatives considered**:
- Append-only history (many assessments per message): great for auditing rule evolution, heavier than MVP needs; `created_at`/`updated_at` + `rules_version` cover basic provenance. A history table is a clean post-MVP/audit-feature add.

---

## Decision 6: Tenant Scoping (inherit from message; 404 vs 403)

**Decision**: Every endpoint resolves the message first with the Spec 005/006 pattern (fetch by id; `None`→404; tenant mismatch→403), then operates on its assessment. `risk_assessments.tenant_id` is denormalised from the message for fast tenant-scoped queries (e.g., high-risk queue).

**Rationale**:
- Consistency with the established cross-tenant contract — no new security model.
- Denormalised `tenant_id` lets `(tenant_id, level)` and `(tenant_id, escalation_recommended)` indexes serve triage/escalation-queue queries directly without a join. Safe because a message never changes tenant.

---

## Decision 7: Enums as Constrained Strings

**Decision**: Persist `RiskLevel`, `RiskFlag`, `RiskAssessmentStatus` as application-level string enums in VARCHAR columns, validated at the boundary (Pydantic/SQLAlchemy), not native PG enums.

**Rationale**:
- Flags/levels may evolve as rules mature; VARCHAR + app validation avoids enum-altering migrations.
- Review requests with invalid level/flag are rejected at the API boundary (422), so the DB never sees invalid values.

---

## Decision 8: Escalation Recommendation Is Metadata Only

**Decision**: `escalation_recommended` (boolean) is set `true` for `high` level and explicit `human_escalation_needed`, and stored as plain metadata. It triggers nothing — no escalation, task, reply, or retrieval.

**Rationale**:
- The spec forbids autonomous escalation and reserves the escalation workflow for a separate, human-reviewed feature.
- Storing the recommendation now (and indexing it) lets the future escalation feature build a queue without re-running risk — a clean seam, no behavior here.

---

## Decision 9: Guest-Count Magnitude and Urgency Parsing

**Decision**: A lightweight parser extracts numeric deltas (e.g., "from 150 to 220") and detects urgency/time terms. Large delta (configurable threshold, default absolute change ≥ 50 or ≥ ~30%) or near-event urgency raises `guest_count_change` from medium to high; small/neutral stays medium. Urgency terms similarly raise other intents.

**Rationale**:
- The spec explicitly distinguishes medium vs high guest-count changes "depending on wording"; a simple, explainable parser captures this and feeds the reason ("guest count increase of 70").
- Thresholds are configurable so behaviour can be tuned without code changes.

**Alternatives considered**:
- NLP magnitude estimation: overkill; the demo messages are simple numeric/temporal cues. Deferred.

---

## Decision 10: Surfacing in Inbox + Detail (no N+1)

**Decision**: Embed a compact `risk` summary (`level`, `flag`, `reason`, `escalation_recommended`) in the Spec 004 inbox item and Spec 005 detail message responses; keep the standalone `GET /risk-assessment` for targeted reads and the review flow.

**Rationale**:
- The inbox/detail already list messages; piggy-backing risk avoids N extra calls and makes the badge instantly available alongside the Spec 006 intent badge.

**Alternatives considered**:
- Frontend fetches each assessment separately: N+1 calls in the inbox; rejected.

---

## Decision 11: Empty / Unclear / Low-Confidence Handling

**Decision**: Empty/whitespace body or `other`/low-confidence classification → at least `medium` with flag `unsupported_or_unclear_request`; the reason notes the unclear basis. Never crash; never default to `low` on uncertainty.

**Rationale**: Uncertainty deserves a human look; defaulting unclear cases to `low` would hide them. Biasing to `medium` matches the spec's "other → medium if unclear".

---

## Resolved Configuration Defaults

| Setting | Default | Purpose |
|---------|---------|---------|
| `RISK_RULES_VERSION` | `rules-v1` | Stamped on every assessment |
| `RISK_GUEST_DELTA_ABS_HIGH` | `50` | Absolute guest delta to raise to high |
| `RISK_GUEST_DELTA_PCT_HIGH` | `0.30` | Relative guest delta to raise to high |
| Flag priority order | `human_escalation_needed > cancellation_risk > complaint > payment_risk > urgent_change > guest_count_change > unsupported_or_unclear_request` | Deterministic primary-flag selection |
