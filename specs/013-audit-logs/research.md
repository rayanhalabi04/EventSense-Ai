# Research: Audit Logs

**Branch**: `013-audit-logs` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Single In-Process Write Path (`AuditService.log_event`)

**Decision**: All audit entries are appended through one function, `AuditService.log_event(...)`, called in-process by features 002–012. An internal HTTP write endpoint (`POST /api/internal/audit-logs`) is **optional** and, if built, is service-authenticated (not a tenant JWT) and runs the same path.

**Rationale**:
- Centralizing the write means redaction, validation, size-bounding, tenant stamping, and best-effort error handling are implemented and tested **once**. Call sites become one-liners that cannot bypass the guarantees.
- An in-process call avoids a network hop and an auth surface for the common case; the EventSense AI features all run in the same FastAPI app, so a function call is simpler and safer than a self-call HTTP endpoint.

**Alternatives considered**:
- HTTP-only internal endpoint: adds latency, a new auth surface, and a way to forge tenant/actor; rejected as the primary path (kept optional for true out-of-process writers).
- Per-feature ad-hoc inserts: duplicates redaction logic and invites leaks/immutability violations; rejected.

---

## Decision 2: Best-Effort / Non-Fatal Logging (log after business commit)

**Decision**: `log_event` never raises into the caller. It catches all exceptions, records them to application logs/metrics, and returns. For **state-changing** events it is called **after** the business transaction commits, using an isolated session/savepoint so a logging failure cannot roll back the caller's work and the caller's rollback cannot leave a misleading log.

**Rationale**:
- The hard constraint is "audit log failures should not break the main user workflow" (FR-014, SR-08). Swallowing the error and decoupling the transaction makes this structural, not incidental.
- Logging after commit means a logged event reflects a state that actually persisted (we don't log `escalation_resolved` if the resolve rolled back). The trade-off — a tiny window where the business action commits but the log fails — is acceptable because audit logging is explicitly best-effort.

**Alternatives considered**:
- Log inside the same transaction: a logging bug could roll back real user actions — directly violates FR-014; rejected.
- Outbox/queue for guaranteed delivery: stronger durability but adds infra (a queue + worker) beyond MVP scope; deferred. Best-effort + app-log visibility is sufficient for the MVP.

---

## Decision 3: Append-Only / Immutable Entries

**Decision**: `audit_logs` has **no** `updated_at`, no update/delete service method, and no update/delete endpoint. We recommend revoking UPDATE/DELETE on the table for the application DB role (or a trigger that raises); at minimum no code path mutates a row.

**Rationale**:
- The spec is explicit: users cannot edit or delete audit logs in the MVP (FR-004, SR-03). Removing the mutation surface entirely (no `updated_at`, no PATCH/DELETE) makes immutability the default, and DB-level revocation defends against accidental ORM writes.
- Loose references (`message_id` SET NULL, `entity_id` as a plain UUID, no cascading delete onto audit rows) ensure deleting a related business row never erases history.

**Alternatives considered**:
- Soft-delete / edit-with-history: contradicts "append-only"; rejected for MVP.
- Cryptographic hash-chaining / WORM storage: stronger tamper-evidence but out of scope (named in Out of Scope); app/DB append-only is sufficient for MVP.

---

## Decision 4: Redaction & Minimization at the Write Boundary

**Decision**: `log_event` runs a redactor before insert: (a) a forbidden-key **denylist** (`*token*`, `*secret*`, `*password*`, `*api_key*`, `*authorization*`, `prompt`, `system_prompt`, `jwt`) drops sensitive keys; (b) metadata is size-capped (`AUDIT_METADATA_MAX_BYTES`) and over-cap payloads are truncated with `metadata_truncated=true`; (c) `redacted_summary` is a short sanitized sentence that never quotes message/reply/document bodies. Callers are expected to pass **ids + minimal facts**, not verbatim content.

**Rationale**:
- The privacy rules (PR-01..06, SR-05, FR-011/FR-012) require minimization and forbid secrets/prompts/keys/cross-tenant/full bodies. Enforcing at the single write boundary means even a careless caller cannot leak: the denylist + size cap are a backstop on top of the "pass ids only" convention.
- Truncation (not rejection) keeps logging best-effort — an oversized payload still yields a (bounded) entry rather than a dropped/failed log.

**Alternatives considered**:
- Trust callers to redact: one careless call leaks secrets; rejected — defense in depth at the boundary.
- Allowlist-only metadata schema per event type: safest but rigid and heavy for MVP; the denylist + size cap + "ids only" convention is the pragmatic middle. (An allowlist can be layered later.)

---

## Decision 5: Cross-Tenant Block Logged in the Attempting Tenant Only

**Decision**: When a user is blocked from another tenant's data, `cross_tenant_access_blocked` (severity `security`, `actor_user_id` = the attempting user) is written **in the attempting user's tenant**, with metadata limited to the attempt (`attempted_route`, `attempted_entity_type`) and **no field from the target tenant**.

**Rationale**:
- The audit log itself must not become a cross-tenant leak (SR-02, SR-07, FR-013, Example 4). Writing in the attacker's tenant with only the attempt context records the security event without exposing the protected data — including not revealing whether the target id even exists in the other tenant.

**Alternatives considered**:
- Log in the target tenant: leaks the existence/identity of the attempting user to the victim tenant and vice-versa; rejected.
- Log in both tenants: doubles the leak surface; rejected.

---

## Decision 6: Closed-but-Extensible String Enums

**Decision**: `event_type`, `actor_type`, `severity`, and `entity_type` persist as application-level string enums in VARCHAR columns, validated at the write boundary. The `event_type` set is the defined list but new values can be added by later features without an enum-altering migration.

**Rationale**:
- Matches the Spec 012 enum pattern (portable + evolvable). As features are added, new event types ("contract_signed", etc.) can be logged without a DB migration; invalid values are still rejected at write time.

**Alternatives considered**:
- Native PG ENUM types: every new event type needs `ALTER TYPE`; rejected for evolvability.
- Free-form strings (no validation): typos/garbage in the dashboard filters; rejected — validate against the known set, allow controlled extension.

---

## Decision 7: Role-Gated Reads — Manager Tenant-Wide, Staff Message-Scoped

**Decision**: Managers read tenant-wide logs (list/get/entity-scoped). Staff read **message-scoped** logs only, and only when `AUDIT_STAFF_MESSAGE_VIEW_ENABLED` is true; `security`-severity entries are excluded from the staff view by default. Platform Admin and unauthenticated callers are blocked.

**Rationale**:
- Oversight is a manager responsibility; staff transparency is scoped to their own work (FR-015, SR-04, US4). Excluding security entries from staff prevents staff from seeing others' blocked-access/guardrail events.
- A config flag lets the staff view be turned off entirely for stricter deployments.

**Alternatives considered**:
- Staff read tenant-wide: over-exposes security/other-user activity; rejected.
- Manager-only (no staff view): loses the optional staff transparency; kept as a P2/config-gated capability instead.

---

## Decision 8: Pagination & Deterministic Ordering

**Decision**: Reads are paginated (`limit`/`offset`, bounded by `AUDIT_LIST_MAX_LIMIT`) and ordered `created_at` **desc**, `id` as a tiebreak. `created_at` is server-assigned.

**Rationale**:
- Audit logs grow without bound; an unpaginated list would be unsafe. Newest-first matches how a manager reviews "what just happened." A deterministic tiebreak (`id`) keeps pages stable when timestamps collide.

**Alternatives considered**:
- Cursor/keyset pagination: more robust for very large/deep scans; offset is simpler and adequate for MVP dashboard use (can upgrade later).
- Client-assigned timestamps: untrustworthy ordering; rejected — server time only.

---

## Decision 9: Metadata as JSONB of IDs + Minimal Facts

**Decision**: `metadata` is a JSONB object holding entity ids and short factual fields (e.g., `predicted_label`, `confidence`, `risk_level`, `document_id`, `task_id`, `escalation_id`, `suggested_reply_id`, `classification_id`, `status_from`/`status_to`, `attempted_route`, `metadata_truncated`). No verbatim bodies, prompts, or secrets.

**Rationale**:
- JSONB keeps the schema flexible across many event types without per-event columns, while the "ids + minimal facts" convention plus the redactor (Decision 4) keep it safe and small. Ids let the dashboard link back to the live entity (still tenant-scoped) without duplicating its content.

**Alternatives considered**:
- Wide typed columns per possible field: rigid, sparse, migration-heavy; rejected.
- Storing full snapshots in metadata: violates minimization (PR-01); rejected.

---

## Decision 10: Write Points — One `log_event` Call Per Action Completion

**Decision**: Each meaningful action in 002–012 emits exactly one entry at its completion point (after the business commit for state changes). Helper shims (`log_intent_classified`, `log_escalation_resolved`, `log_cross_tenant_blocked`, …) keep call sites to a single consistent line.

**Rationale**:
- One entry per action keeps the log readable and avoids duplicate/partial rows. Completion-point logging (not attempt-point) means the log reflects what actually happened. Shims standardize actor_type/severity/entity per event family so call sites can't get them wrong.

**Alternatives considered**:
- Decorator/middleware auto-logging every request: noisy, hard to map to domain events, and risks logging request bodies (leak); rejected in favor of explicit domain-event calls.
- Logging at attempt + at success: duplicates; an optional `request_id` already enables de-dup of genuine retries.

---

## Decision 11: No Retention / Export / Alerting / Tamper-Proofing (MVP)

**Decision**: The MVP does not implement retention/purge, bulk export/SIEM streaming, real-time alerting, or cryptographic tamper-proofing. Entries persist; the dashboard is the only surface.

**Rationale**:
- Explicitly listed in Out of Scope. The MVP goal is append-only recording + a tenant-scoped, filterable read surface. These capabilities add infra/policy decisions (TTL, key management, alert routing) better handled after the core log exists.

---

## Decision 12: De-Duplication via Optional `request_id` (no hard uniqueness)

**Decision**: Entries may carry an optional `request_id`/`correlation_id`. No DB uniqueness is enforced; readers may de-duplicate retried operations by `request_id`. The same `request_id` also correlates an action with its security/guardrail sub-events.

**Rationale**:
- A retried operation (e.g., a re-submitted classify) could emit two entries; a soft `request_id` lets the dashboard collapse them without risking a hard-uniqueness write failure that would (against best-effort) drop a log. Correlation also ties `rag_no_source_found` to the `suggested_reply_generated` it influenced.

**Alternatives considered**:
- Unique constraint on `(tenant_id, event_type, entity_id, request_id)`: a duplicate would raise — and best-effort would swallow the second log, but the constraint adds write-failure surface; soft de-dup at read time is safer for MVP.
