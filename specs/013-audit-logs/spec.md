# Feature Specification: Audit Logs

**Feature Branch**: `013-audit-logs`

**Created**: 2026-06-08

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 007 — Risk Detection](../007-risk-detection/spec.md)
- [Spec 008 — Document Upload](../008-document-upload/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 010 — Suggested Replies](../010-suggested-replies/spec.md)
- [Spec 011 — Follow-Up Tasks](../011-follow-up-tasks/spec.md)
- [Spec 012 — Escalation to Manager](../012-escalation-to-manager/spec.md)

**Input**: User description: "The system should record important AI, system, and staff actions in a tenant-scoped audit log so managers can review what happened, when it happened, who did it, and which message/document/task/escalation it relates to. Audit logs provide traceability, transparency, and safety for the EventSense AI workflow."

---

## Goal

Give every tenant an append-only, tenant-scoped record of the important things that happen in its EventSense AI workspace — what the AI did, what the system did, and what staff/managers did — so a manager can answer "what happened, when, who did it, and which message/document/task/escalation does it relate to?" Audit logs are written by an internal logging service that the existing features (003–012) call when meaningful events occur (a message arrives, intent is classified, risk is detected, a document is processed, RAG retrieves or finds nothing, a reply is generated/edited/approved/rejected, a task or escalation changes state, a guardrail refuses, a cross-tenant access is blocked). Each entry captures a tenant id, an actor (a human user, the system, or the AI service), an event type, a severity, the related entity, optional message/conversation references, a small redacted metadata payload, and a human-readable redacted summary. Managers read their tenant's logs through an Audit Logs dashboard with filtering (event type, actor, date range, related entity, severity); staff may read a limited slice tied to messages they handle. Logs are **append-only and immutable in the MVP** — no one edits or deletes them. Tenant A can never see Tenant B's logs, and metadata never contains secrets, system prompts, JWTs, API keys, or cross-tenant data. Audit logging is best-effort from the caller's perspective: a logging failure is handled safely and never breaks the primary user workflow. This closes the EventSense AI MVP loop with traceability, transparency, and safety.

---

## Audit Actor Types

| Actor type | Meaning |
|------------|---------|
| `user` | A human (staff or manager) performed the action; `actor_user_id` is set |
| `system` | A system/workflow action with no human actor (e.g., simulator ingestion, document processing) |
| `ai_service` | An AI/ML component performed the action (classifier, risk engine, RAG, reply generator) |

## Audit Severity Levels

| Severity | Meaning | Typical events |
|----------|---------|----------------|
| `info` | Normal, expected activity | message_received, intent_classified, task_created |
| `warning` | Notable but non-failing (a gap or soft refusal) | rag_no_source_found, unsupported_answer_refused |
| `error` | A failed operation (handled) | document_processing_failed (internal), generation_error |
| `security` | A security-relevant event | cross_tenant_access_blocked, guardrail_refusal |

---

## Logged Event Types

Grouped by source feature. Each event is written once, at the point the action completes.

| Event type | Actor (typical) | Severity | Entity | Source spec |
|------------|-----------------|----------|--------|-------------|
| `message_received` | system | info | message | 003 |
| `message_created_by_simulator` | user / system | info | message | 003 |
| `intent_classified` | ai_service | info | classification_result | 006 |
| `risk_detected` | ai_service | info / warning | risk_assessment | 007 |
| `document_uploaded` | user | info | document | 008 |
| `document_processed` | system | info | document | 008/009 |
| `rag_retrieved` | ai_service | info | rag_retrieval | 009 |
| `rag_no_source_found` | ai_service | warning | rag_retrieval | 009 |
| `suggested_reply_generated` | ai_service | info | suggested_reply | 010 |
| `suggested_reply_edited` | user | info | suggested_reply | 010 |
| `suggested_reply_approved` | user | info | suggested_reply | 010 |
| `suggested_reply_rejected` | user | info | suggested_reply | 010 |
| `task_created` | user | info | task | 011 |
| `task_updated` | user | info | task | 011 |
| `task_completed` | user | info | task | 011 |
| `escalation_created` | user | info | escalation | 012 |
| `escalation_updated` | user | info | escalation | 012 |
| `escalation_resolved` | user | info | escalation | 012 |
| `guardrail_refusal` | ai_service | security | suggested_reply / rag_retrieval | 009/010 |
| `cross_tenant_access_blocked` | user | security | (varies) | 001–012 |
| `unsupported_answer_refused` | ai_service | warning | rag_retrieval / suggested_reply | 009/010 |
| `user_login` | user | info | user | 002 |
| `user_logout` *(optional)* | user | info | user | 002 |

The enum is closed (validated at write time), but new event types may be added in later features without a schema migration (string-backed enum).

---

## Main Users

| Role | Description |
|------|-------------|
| **Manager** | Primary reader. Views the full tenant-scoped audit log dashboard; filters by event type, actor, date range, related entity, and severity; opens a single entry's detail. Cannot edit or delete entries. |
| **Staff** | Limited reader. May view audit entries related to messages/conversations they handle (when allowed by config), scoped to their tenant. Cannot edit or delete; cannot see security/admin-only entries by default. |
| **System / AI service** | Writers only (never readers). The simulator, classifier, risk engine, document pipeline, RAG, reply generator, task/escalation services, and guardrails call the internal audit logging service to append entries. Not a human actor. |

Platform Admin has no access to tenant audit logs (no cross-tenant reading).

---

## User Stories

### User Story 1 — System/AI/Staff Actions Are Recorded (Priority: P1)

As EventSense AI processes a client message, each meaningful step appends an audit entry: the message arrives (`message_received`/`message_created_by_simulator`), the classifier predicts an intent (`intent_classified`), the risk engine flags risk (`risk_detected`), RAG retrieves or finds nothing (`rag_retrieved`/`rag_no_source_found`), a reply is generated/edited/approved/rejected, and tasks/escalations change state. Every entry is tenant-scoped, append-only, carries an actor (user/system/ai_service), an event type, a severity, the related entity reference, optional message/conversation ids, redacted metadata, and a redacted summary.

**Why this priority**: Without writes there is nothing to read. The logging service and its call sites are the foundation; the dashboard (US2) only displays what this story records. This is the core of the feature.

**Independent Test**: Drive a message through the pipeline in the Elegant Weddings tenant. Verify audit entries exist for `message_created_by_simulator`, `intent_classified` (actor `ai_service`, metadata includes predicted label + confidence), and `risk_detected`. Verify each row carries `tenant_id` (Elegant Weddings), `event_type`, `actor_type`, `severity`, `entity_type`, `entity_id`, and `created_at`, and that none of them are visible to Royal Events Agency.

**Acceptance Scenarios**:

1. **Given** the simulator ingests a client message, **When** ingestion completes, **Then** a `message_created_by_simulator` (or `message_received`) entry is appended with `actor_type` `user`/`system`, `entity_type` `message`, `message_id` set, `severity` `info`, scoped to the tenant.
2. **Given** the classifier predicts an intent, **When** classification completes, **Then** an `intent_classified` entry is appended with `actor_type` `ai_service`, `entity_type` `classification_result`, and metadata containing `predicted_label` + `confidence` (no raw model internals, no prompt).
3. **Given** the risk engine assesses a message, **When** it completes, **Then** a `risk_detected` entry is appended (`ai_service`, severity `info`/`warning`) with the risk level/reason summary in metadata.
4. **Given** a staff user edits/approves/rejects a suggested reply, **When** the action completes, **Then** the corresponding `suggested_reply_*` entry is appended with `actor_type` `user`, `actor_user_id` set, `entity_type` `suggested_reply`.
5. **Given** any logged action, **When** the entry is written, **Then** it is **append-only** — no later write updates or deletes it.

---

### User Story 2 — Manager Reviews the Audit Log Dashboard (Priority: P1)

A manager opens the Audit Logs dashboard and sees their tenant's entries newest-first: timestamp, event type, actor (human name or "System"/"AI service"), severity, related entity, and a redacted summary. They filter by event type, actor, date range, related entity (e.g., a specific `message_id` or `escalation_id`), and severity, and open a single entry to see its metadata and references.

**Why this priority**: The dashboard is how the feature delivers value — traceability and transparency for managers. Equal P1 because logs no one can read provide no oversight.

**Independent Test**: With entries from US1 present, list logs as a manager — verify only the tenant's entries appear, ordered newest-first, with the expected columns. Filter `severity=security` and `event_type=intent_classified` and a `date_range`; verify the filtered subsets. Open one entry — verify its full (redacted) metadata + references. Confirm a manager in another tenant sees none of these.

**Acceptance Scenarios**:

1. **Given** audit entries exist in a tenant, **When** a manager lists logs, **Then** only that tenant's entries are returned, newest-first, with event_type, actor, severity, entity reference, message/conversation refs, and redacted summary.
2. **Given** filters (event_type, actor_type/actor_user_id, date range, entity_type/entity_id, severity), **When** the list is requested with them, **Then** only matching tenant entries are returned.
3. **Given** an entry id in the caller's tenant, **When** a manager fetches it, **Then** the full entry (redacted metadata + all references) is returned.
4. **Given** an entry from another tenant, **When** referenced by id, **Then** the request is blocked (404 not-found / 403 cross-tenant) and no data is exposed.
5. **Given** results may be large, **When** logs are listed, **Then** the response is paginated (limit/offset or cursor) and bounded.

---

### User Story 3 — Security Events Are Captured (cross-tenant, guardrail, refusal) (Priority: P1)

When a user attempts to access another tenant's data, the block is recorded as `cross_tenant_access_blocked` (severity `security`, `actor_user_id` = the attempting user) with metadata that does **not** leak the target tenant's data. When a guardrail refuses (e.g., an unsupported/ungrounded answer), a `guardrail_refusal` / `unsupported_answer_refused` entry is recorded. RAG finding no source records `rag_no_source_found` (severity `warning`) without storing any unsupported answer text.

**Why this priority**: Security traceability is a primary purpose of the audit log (the spec calls these out explicitly). Capturing blocks and refusals — safely, without leaking the very data that was protected — is core, not optional. Equal P1.

**Independent Test**: As an Elegant Weddings user, attempt to read a Royal Events escalation (cross-tenant). Verify the request is blocked **and** a `cross_tenant_access_blocked` entry is appended in the **attempting user's** tenant (Elegant Weddings), severity `security`, `actor_user_id` set, with metadata referencing the attempted action but containing **no** Royal Events data. Trigger a RAG query with no grounded source — verify `rag_no_source_found` (warning) with the query/message id but no unsupported answer text.

**Acceptance Scenarios**:

1. **Given** a user attempts cross-tenant access, **When** the access is blocked, **Then** a `cross_tenant_access_blocked` entry (severity `security`, `actor_user_id` set) is appended in the **attempting** user's tenant, with metadata describing the attempt but **no** target-tenant data.
2. **Given** a guardrail refuses an ungrounded/unsupported answer, **When** the refusal occurs, **Then** a `guardrail_refusal` / `unsupported_answer_refused` entry is appended (severity `security`/`warning`) without storing the refused answer text.
3. **Given** RAG finds no grounded source, **When** retrieval completes, **Then** a `rag_no_source_found` entry (severity `warning`) is appended with the query/message reference but no fabricated/unsupported answer.
4. **Given** any security entry, **When** it is written or read, **Then** it never contains secrets, system prompts, JWTs, API keys, or another tenant's data.

---

### User Story 4 — Staff See Limited, Message-Scoped History (Optional) (Priority: P2)

When enabled, a staff user viewing a message/conversation can see the audit entries for that message (e.g., classified, risk detected, reply generated/approved, task/escalation created) so they understand what the system did. Staff do not see tenant-wide logs or security/admin-only entries by default.

**Why this priority**: Improves staff transparency on their own work but is not required for manager oversight (US2). Lower priority and gated by config; it reuses the message-scoped read path.

**Independent Test**: As a staff user, open a message they handle and request its audit entries — verify only that message's tenant-scoped, staff-visible entries are returned (no security/admin-only entries unless allowed), and that the tenant-wide list endpoint is not available to staff (or returns a restricted subset per config).

**Acceptance Scenarios**:

1. **Given** staff message-scoped audit is enabled, **When** a staff user requests a message's audit entries, **Then** only that message's tenant-scoped, staff-visible entries are returned.
2. **Given** a `security`-severity entry, **When** a staff user requests message audit, **Then** it is excluded by default (manager-only) unless explicitly configured otherwise.
3. **Given** staff message-scoped audit is disabled, **When** a staff user requests message audit, **Then** access is restricted (403) per config.

---

### Edge Cases

- **Logging failure must not break the workflow**: if appending an audit entry fails (DB error, serialization error), the primary action (classify, reply, escalate, etc.) still succeeds; the failure is swallowed safely and surfaced via application logs/metrics, not to the end user.
- **Oversized / unexpected metadata**: metadata is size-bounded and schema-light; oversized payloads are truncated and a `metadata_truncated` flag is set rather than rejected.
- **Sensitive content in source text**: message bodies, reply drafts, and document text are **not** copied verbatim into metadata; only minimal references (ids) + a redacted summary are stored.
- **Missing actor**: AI/system events have `actor_user_id` null and `actor_type` `system`/`ai_service`; human events must set `actor_user_id`.
- **Related entity not yet known**: if an event has no single entity (e.g., a login), `entity_type` is `user`/`session` and entity-specific refs may be null.
- **Cross-tenant access attempt logging**: the entry is written in the **attempting** user's tenant, never the target's, and contains no target-tenant fields.
- **Duplicate events**: a retried operation may emit a duplicate; an optional `request_id`/`correlation_id` lets readers de-duplicate (no hard uniqueness enforced in MVP).
- **Clock/order**: ordering is by `created_at` (server time); ties broken by `id`.
- **Append-only enforcement**: there is no update/delete API; any attempt is rejected (405/404). DB-level immutability is recommended (no UPDATE/DELETE grants) but at minimum no code path mutates entries.
- **Large date-range query**: bounded by pagination + a max range; very large exports are out of scope for MVP.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide an internal audit logging service that appends a tenant-scoped `AuditLog` entry for a given event, callable by features 002–012 without blocking their primary action.
- **FR-002**: Each entry MUST record: `id`, `tenant_id`, `actor_user_id` (nullable), `actor_type` (`user`/`system`/`ai_service`), `event_type`, `severity` (`info`/`warning`/`error`/`security`), `entity_type`, `entity_id` (nullable), `message_id` (nullable), `conversation_id` (nullable), `metadata` (JSON), `redacted_summary`, `created_at`, and an optional `request_id`/`correlation_id`.
- **FR-003**: The system MUST write entries for the defined event types when those actions occur: `message_received`, `message_created_by_simulator`, `intent_classified`, `risk_detected`, `document_uploaded`, `document_processed`, `rag_retrieved`, `rag_no_source_found`, `suggested_reply_generated`, `suggested_reply_edited`, `suggested_reply_approved`, `suggested_reply_rejected`, `task_created`, `task_updated`, `task_completed`, `escalation_created`, `escalation_updated`, `escalation_resolved`, `guardrail_refusal`, `cross_tenant_access_blocked`, `unsupported_answer_refused`, `user_login` (and optionally `user_logout`).
- **FR-004**: Entries MUST be **append-only**: no API or service path updates or deletes an existing entry; attempts MUST be rejected.
- **FR-005**: For human actions, `actor_type` MUST be `user` and `actor_user_id` MUST be set; for system/AI actions, `actor_type` MUST be `system`/`ai_service` and `actor_user_id` MUST be null.
- **FR-006**: Entries MUST include related entity references when available: `entity_type` + `entity_id`, plus `message_id`/`conversation_id`, and entity ids carried in metadata (`document_id`, `task_id`, `escalation_id`, `suggested_reply_id`, `classification_id`) as applicable.
- **FR-007**: Managers MUST be able to list their tenant's entries with filtering by `event_type`, actor (`actor_type` and/or `actor_user_id`), date range (`created_from`/`created_to`), related entity (`entity_type`/`entity_id`, `message_id`), and `severity`, newest-first and paginated.
- **FR-008**: Managers MUST be able to fetch a single entry in their tenant with full (redacted) metadata + references.
- **FR-009**: The system MUST provide message-scoped audit retrieval (`GET /api/messages/{message_id}/audit-logs`) returning that message's tenant-scoped entries; entity-scoped retrieval (e.g., escalation) MUST be supported for managers.
- **FR-010**: The system MUST scope every read to the caller's tenant; cross-tenant reads MUST be blocked (404/403). A client-supplied `tenant_id` MUST be ignored.
- **FR-011**: `metadata` and `redacted_summary` MUST NOT contain secrets, system prompts, JWTs, API keys, raw passwords, or any other tenant's data; sensitive source text MUST be minimized/redacted (ids + short summary, not verbatim bodies).
- **FR-012**: `metadata` MUST be size-bounded; oversized payloads MUST be truncated (with a `metadata_truncated` indicator) rather than rejected.
- **FR-013**: A `cross_tenant_access_blocked` entry MUST be written in the **attempting** user's tenant with `actor_user_id` set and metadata that contains no target-tenant data.
- **FR-014**: Audit logging MUST be best-effort from the caller's perspective: a logging failure MUST NOT fail or roll back the primary action; failures are handled safely and observable via application logs/metrics.
- **FR-015**: Role enforcement MUST allow managers to read tenant-wide logs and, when enabled, staff to read message-scoped logs; Platform Admin and unauthenticated callers MUST be blocked (403/401). Security-severity entries are manager-only by default.
- **FR-016**: `created_at` MUST be server-assigned; ordering MUST be deterministic (`created_at` desc, `id` tiebreak); `event_type`/`actor_type`/`severity` MUST be validated against their enums at write time.
- **FR-017**: An optional internal write endpoint (`POST /api/internal/audit-logs`) MAY exist for system/AI writers; if present it MUST be internal-only (service auth, not a tenant user) and subject to the same redaction/validation rules. The primary mechanism is the in-process logging service function.

### Key Entities

- **Tenant** (001): scopes all entries (`audit_logs.tenant_id`).
- **User** (002): `actor_user_id` for human actions; role gates read access.
- **Message / Conversation** (003): `message_id` / `conversation_id` references.
- **ClassificationResult** (006): `classification_id` in metadata for `intent_classified`.
- **RiskAssessment** (007): risk summary in metadata for `risk_detected`.
- **Document** (008): `document_id` in metadata for `document_*`.
- **RAG retrieval** (009): `rag_retrieved` / `rag_no_source_found` references.
- **SuggestedReply** (010): `suggested_reply_id` for `suggested_reply_*` / guardrail refusals.
- **Task** (011): `task_id` for `task_*`.
- **Escalation** (012): `escalation_id` for `escalation_*`.
- **AuditLog** (new): the append-only entry.
- **AuditEventType** (enum): the closed-but-extensible event-type set.
- **AuditActorType** (enum): `user`, `system`, `ai_service`.
- **AuditSeverity** (enum): `info`, `warning`, `error`, `security`.
- **AuditEntityType** (enum): `message`, `conversation`, `classification_result`, `risk_assessment`, `document`, `rag_retrieval`, `suggested_reply`, `task`, `escalation`, `user`, `session`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id`, `actor_user_id`, and `role`; never supplied by the client |
| Logged event | Internal service call (002–012) | `event_type`, `actor_type`, `severity`, `entity_type`/`entity_id`, optional message/conversation ids, metadata, summary |
| Filters | Dashboard list request | event_type, actor_type/actor_user_id, date range, entity_type/entity_id, message_id, severity |
| Pagination | List request | `limit` / `offset` (or cursor), bounded |
| Entry id | Detail request | A single in-tenant entry to fetch |
| Message/entity id | Scoped read | Message-scoped or escalation-scoped audit listing |

---

## Outputs

| Output | Description |
|--------|-------------|
| Appended audit entry | Tenant-scoped, append-only, with actor/event/severity/entity/refs/metadata/summary/timestamp |
| Audit log list | Tenant-scoped, newest-first, filtered + paginated list of entries |
| Single audit entry | Full (redacted) metadata + references for one in-tenant entry |
| Message-scoped audit list | A message's tenant-scoped entries (staff-visible subset when staff) |
| Entity-scoped audit list | An escalation's (or other entity's) tenant-scoped entries (manager) |
| 401 / 403 | Unauthenticated / Platform Admin / staff over-reach / cross-tenant |
| 404 | Entry/message/entity not in caller's tenant |
| 422 | Invalid filter / invalid event_type/severity / invalid pagination |
| 405 | Attempt to update/delete an entry (append-only) |

---

## Main Workflow

1. **An action occurs** in a feature (002–012): a message is ingested, intent is classified, risk is detected, a document is processed, RAG retrieves/finds-nothing, a reply is generated/edited/approved/rejected, a task/escalation changes state, a guardrail refuses, or a cross-tenant access is blocked.
2. **The feature calls the audit logging service** with `event_type`, `actor_type`, `severity`, `entity_type`/`entity_id`, optional `message_id`/`conversation_id`, a small `metadata` object (ids + minimal facts), and a `redacted_summary`.
3. **The service redacts + validates** — drops/avoids secrets, prompts, JWTs, keys, cross-tenant data; truncates oversized metadata; validates enums — and **appends** the entry with the JWT/service `tenant_id` and server `created_at`.
4. **On logging failure** — the error is swallowed safely (logged to app logs/metrics); the primary action is unaffected.
5. **A manager opens the dashboard** — lists the tenant's entries newest-first, filters (event/actor/date/entity/severity), paginates, and opens a single entry for full redacted detail.
6. **(Optional) A staff user** opens a message and sees that message's staff-visible audit entries.

No entry is ever edited or deleted; no cross-tenant data is ever written or read.

---

## Alternative Workflows

### Cross-Tenant Access Attempt (security)

1. A Tenant A user requests a Tenant B escalation/message/document.
2. The owning feature blocks it (404/403 per its own rules).
3. It calls the audit service to append `cross_tenant_access_blocked` (severity `security`, `actor_user_id` = the Tenant A user) **in Tenant A**, with metadata describing the attempt (the attempted route/entity-type) but **no** Tenant B data.

### Guardrail Refusal / Unsupported Answer

1. RAG (009) finds no grounded source, or the reply guardrail (010) refuses an ungrounded answer.
2. The feature appends `rag_no_source_found` (warning) or `guardrail_refusal`/`unsupported_answer_refused` (security/warning) with the query/message reference — **without** storing the unsupported/refused answer text.

### Logging Failure (safety)

1. A feature calls the audit service; the append fails (DB/serialization error).
2. The service catches it, records to application logs/metrics, and returns normally.
3. The feature's primary action (classify/reply/escalate) completes successfully — the user sees no failure.

### Staff Message-Scoped View (optional)

1. A staff user opens a message they handle.
2. They request `GET /api/messages/{id}/audit-logs`.
3. The system returns that message's tenant-scoped, staff-visible entries (security entries excluded by default).

### Manager Filtered Review

1. A manager filters by `severity=security` + a date range to review blocked cross-tenant attempts and guardrail refusals.
2. They open an entry to see the redacted metadata and references; nothing is editable.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Pipeline actions append entries (message_created_by_simulator, intent_classified, risk_detected) with required fields, tenant-scoped | Integration: drive pipeline → assert entries + fields |
| AC-02 | `intent_classified` is `ai_service` with metadata `predicted_label` + `confidence` and no prompt/model internals | Integration: assert actor_type + metadata keys |
| AC-03 | `rag_no_source_found` is `warning`, references the query/message, stores no unsupported answer | Integration: no-source query → assert entry + absence of answer text |
| AC-04 | Reply/task/escalation lifecycle events are appended with correct actor/entity (suggested_reply_*, task_*, escalation_*) | Integration: drive each action → assert entries |
| AC-05 | Entries are append-only: no update/delete path exists; attempts rejected | Integration/code: assert no mutate endpoint; 405/404 on attempt |
| AC-06 | Manager list returns only the tenant's entries, newest-first, paginated, with the expected columns | Integration: entries in A + B → list in A returns only A |
| AC-07 | List filters by event_type, actor, date range, entity, severity work within the tenant | Integration: assert filtered subsets |
| AC-08 | `GET /api/audit-logs/{id}` returns full redacted entry; cross-tenant → 404/403 | Integration |
| AC-09 | `GET /api/messages/{id}/audit-logs` returns the message's tenant-scoped entries; cross-tenant → 404/403 | Integration |
| AC-10 | Cross-tenant access attempt appends `cross_tenant_access_blocked` (security, actor set) in the attempting tenant with no target-tenant data | Integration: A→B access → assert entry in A, no B data |
| AC-11 | Guardrail refusal / unsupported answer appends a security/warning entry without storing refused text | Integration |
| AC-12 | metadata/summary never contain secrets, prompts, JWTs, API keys, or cross-tenant data | Integration/code: redaction tests over representative events |
| AC-13 | Oversized metadata is truncated (flag set), not rejected | Unit/integration: large payload → truncated + flagged |
| AC-14 | A logging failure does not fail the primary action | Integration: inject append failure → primary action still succeeds |
| AC-15 | Tenant isolation: Tenant 1 cannot list/read Tenant 2 audit logs | Integration: list/get as 1 → no 2 entries / 404-403 |
| AC-16 | Role enforcement: managers read tenant-wide; staff read message-scoped (when enabled); Platform Admin → 403; unauthenticated → 401; security entries manager-only | Integration: per-role calls |
| AC-17 | Audit Logs dashboard renders entries with filters; entry detail shows redacted metadata | Frontend test: assert rendering + filters |
| AC-18 | `created_at` server-assigned; ordering deterministic; invalid event_type/severity/filter → 422 | Integration |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenants, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT; `actor_user_id`; manager (read all) + staff (message-scoped); Platform Admin blocked; `user_login`/`user_logout` events |
| Spec 003 — Message Simulator | Required | `message_received` / `message_created_by_simulator`; `message_id`/`conversation_id` |
| Spec 004 — Message Inbox | Optional | May surface an audit indicator/link |
| Spec 005 — Message Detail Page | Required (light) | Entry point for message-scoped staff audit view |
| Spec 006 — Intent Classifier | Required | `intent_classified` + `classification_id`/label/confidence |
| Spec 007 — Risk Detection | Required | `risk_detected` + risk level/reason summary |
| Spec 008 — Document Upload | Required | `document_uploaded` / `document_processed` + `document_id` |
| Spec 009 — RAG Over Tenant Documents | Required | `rag_retrieved` / `rag_no_source_found` / `unsupported_answer_refused` |
| Spec 010 — Suggested Replies | Required | `suggested_reply_*` + `guardrail_refusal` |
| Spec 011 — Follow-Up Tasks | Required | `task_*` + `task_id` |
| Spec 012 — Escalation to Manager | Required | `escalation_*` + `escalation_id` |

This feature is the **consumer** of the actor/action/timestamp signals that 002–012 already expose; it adds the logging service + call sites + read surface. It is the final MVP feature.

---

## AI Behavior

- **AI is an actor, not a reader**: AI/ML components (classifier, risk engine, RAG, reply generator, guardrails) write entries with `actor_type` `ai_service`. They never read the audit log and never decide what a human may see.
- **No model internals in logs**: AI events store outcome facts only (e.g., `predicted_label`, `confidence`, `risk_level`) — never prompts, embeddings, raw model output, or chain-of-thought.
- **Guardrail transparency**: refusals (`guardrail_refusal`, `unsupported_answer_refused`, `rag_no_source_found`) are logged so managers can see when the system declined to answer — without persisting the refused/unsupported text.
- **No autonomous side effects**: writing an audit entry triggers nothing — no reply, no task, no escalation, no message. Logging is observation only.
- **Best-effort**: AI/system writers treat logging as non-fatal; a failed append never blocks the AI action.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session/service only** | `tenant_id` (and `actor_user_id` for humans) is always derived from the JWT or the calling service context. No client-supplied tenant/actor is accepted. |
| **SR-02: Audit tenancy** | An entry belongs to exactly one tenant. Tenant A can never list/read Tenant B entries. A `cross_tenant_access_blocked` entry is written in the **attempting** tenant only. |
| **SR-03: Append-only / immutable** | No update or delete path exists in the MVP. Entries are never modified after write; DB-level revocation of UPDATE/DELETE is recommended. |
| **SR-04: Role split** | Managers read tenant-wide logs; staff read message-scoped logs only when enabled; security-severity entries are manager-only by default. Platform Admin → 403. Unauthenticated → 401. |
| **SR-05: Redaction / minimization** | `metadata`/`redacted_summary` never contain secrets, system prompts, JWTs, API keys, passwords, full message/reply/document bodies, or any other tenant's data. Store ids + minimal facts + a short redacted summary. |
| **SR-06: Not Found vs Forbidden** | An entry/message/entity not in the caller's tenant → 404; one in another tenant → 403 (consistent with Specs 005–012). |
| **SR-07: No cross-tenant leakage in security events** | A `cross_tenant_access_blocked` entry contains no field from the target tenant — only the attempting user, the attempted action/entity-type, and the attempting tenant. |
| **SR-08: Best-effort safety** | Logging failures are caught and never break, roll back, or expose internals to the primary workflow; they are observable via app logs/metrics only. |

---

## Privacy / Redaction Rules

| Rule | Description |
|------|-------------|
| **PR-01: Minimize, don't copy** | Store entity **ids** and short factual fields, not verbatim message/reply/document text. The `redacted_summary` is a short human sentence with no sensitive payload. |
| **PR-02: Forbidden content** | Never store: system prompts, model prompts/instructions, JWTs/tokens, API keys/secrets, passwords/credentials, raw embeddings, full client message bodies, full reply drafts, full document text, or another tenant's data. |
| **PR-03: Allowed metadata** | Allowed examples: `predicted_label`, `confidence`, `risk_level`, `risk_reason` (short), `document_id`, `task_id`, `escalation_id`, `suggested_reply_id`, `classification_id`, `source_document_ids` (ids only), `status_from`/`status_to`, `attempted_route`, `metadata_truncated`. |
| **PR-04: Size bounds** | `metadata` is size-capped; over-cap payloads are truncated and flagged (`metadata_truncated=true`), never silently storing unbounded text. |
| **PR-05: PII restraint** | Client names/contact details are not duplicated into metadata beyond what an id reference provides; the `redacted_summary` avoids quoting message content. |
| **PR-06: Security-event redaction** | For `cross_tenant_access_blocked` / `guardrail_refusal` / `unsupported_answer_refused`, store the fact and the attempting context only — never the protected/target data or the refused answer text. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Audit append fails (DB/serialization) | Caught + logged to app logs/metrics; **primary action still succeeds** (best-effort); no user-facing error |
| Oversized metadata | Truncated + `metadata_truncated=true`; entry still written |
| Invalid `event_type`/`actor_type`/`severity` at write | Rejected at the service boundary (validation); caller's primary action unaffected; misconfiguration surfaced in app logs |
| Invalid filter / pagination on read | 422 validation; nothing returned |
| Entry/message/entity not in tenant | 404 / 403 per SR-06; no data exposed |
| Staff requests tenant-wide list | 403 (managers only) |
| Staff requests message-scoped audit when disabled | 403 per config |
| Platform Admin calls any read endpoint | 403 `INSUFFICIENT_ROLE` |
| Attempt to update/delete an entry | 405/404 — no such path exists (append-only) |
| Cross-tenant read attempt | 404/403 + (separately) a `cross_tenant_access_blocked` entry recorded in the attempting tenant |

---

## Edge Cases (summary)

- Logging failure → primary action unaffected (best-effort, swallowed safely).
- Oversized metadata → truncated + flagged, not rejected.
- AI/system events → `actor_user_id` null; human events → `actor_user_id` required.
- Cross-tenant attempt → entry in attempting tenant only, no target data.
- No single entity (login) → `entity_type` `user`/`session`, entity refs may be null.
- Duplicate retried events → optional `request_id` for de-dup; no hard uniqueness in MVP.
- Append-only → no edit/delete path; ordering by `created_at` then `id`.
- Large date range → bounded by pagination + max range; no bulk export in MVP.

---

## Out of Scope

- **Editing or deleting audit logs** — append-only/immutable in the MVP; no update/delete API.
- **Retention / purge / archival policies** — no TTL, rotation, or automated deletion in MVP (entries persist).
- **Log export / SIEM streaming / external forwarding** — no CSV/JSON bulk export, no syslog/SIEM/webhook shipping.
- **Real-time alerting / notifications on events** — the dashboard is the surface; no paging/email/push on audit events.
- **Cross-tenant or platform-wide audit views** — explicitly forbidden; no Platform Admin tenant-spanning log.
- **Tamper-proof cryptographic chaining / signed logs** — append-only at the app/DB level is sufficient for MVP; no hash chains/WORM storage.
- **Analytics / dashboards beyond filtered listing** — no charts, aggregations, or metrics dashboards in MVP.
- **Storing full message/reply/document content** — minimization only (ids + redacted summary).
- **Real WhatsApp API, calendar syncing, full CRM** — out of scope entirely.

---

## Assumptions

- An `AuditLog` belongs to exactly one tenant and is never modified after creation.
- The primary write mechanism is an **in-process logging service function** called by features 002–012; an internal HTTP endpoint is optional and, if present, is service-authenticated (not a tenant user).
- `actor_user_id` is set for human (`user`) events and null for `system`/`ai_service` events; `actor_type` is always set.
- `metadata` is a small JSON object of ids + minimal facts; it is size-bounded and redacted; it never holds secrets/prompts/keys/cross-tenant data.
- Reads are tenant-scoped and role-gated: managers read tenant-wide; staff read message-scoped (when enabled); security entries are manager-only by default.
- Logging is best-effort: a failed append never breaks, blocks, or rolls back the calling feature's action.
- Ordering is `created_at` desc with `id` tiebreak; reads are paginated and bounded.
- Retention/export/alerting/tamper-proofing are explicitly deferred (out of scope) — this MVP delivers append-only recording + a tenant-scoped, filterable read surface.
