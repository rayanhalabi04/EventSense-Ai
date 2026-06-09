# Requirements Checklist: Audit Logs

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-08
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (traceability, transparency, safety) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI behavior, Security, Privacy/redaction, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Internal audit logging service appends a tenant-scoped entry, callable by 002–012, non-blocking (FR-001, AC-14)
- [ ] Each entry records all required fields: id, tenant_id, actor_user_id, actor_type, event_type, severity, entity_type, entity_id, message_id, conversation_id, metadata, redacted_summary, created_at, optional request_id (FR-002)
- [ ] Entries written for every defined event type when the action occurs (FR-003, AC-01, AC-04)
- [ ] Entries are append-only — no update/delete path; attempts rejected (FR-004, AC-05)
- [ ] Human actions: actor_type `user` + actor_user_id set; system/AI: `system`/`ai_service` + actor_user_id null (FR-005)
- [ ] Related entity references captured when available (entity_type/entity_id, message_id/conversation_id, document_id/task_id/escalation_id/suggested_reply_id/classification_id in metadata) (FR-006)
- [ ] Manager list filters by event_type, actor, date range, entity, severity; newest-first; paginated (FR-007, AC-06, AC-07)
- [ ] Manager can fetch a single entry with full redacted metadata + refs (FR-008, AC-08)
- [ ] Message-scoped retrieval + entity-scoped (escalation) retrieval supported (FR-009, AC-09)
- [ ] Every read tenant-scoped; cross-tenant blocked; client-supplied tenant ignored (FR-010, AC-15)
- [ ] metadata/redacted_summary never contain secrets/prompts/JWTs/keys/full bodies/cross-tenant data (FR-011, AC-12)
- [ ] metadata size-bounded; oversized truncated + flagged, not rejected (FR-012, AC-13)
- [ ] cross_tenant_access_blocked written in attempting tenant, actor set, no target data (FR-013, AC-10)
- [ ] Logging best-effort: failure never fails/rolls back the primary action (FR-014, AC-14)
- [ ] Role enforcement: managers tenant-wide; staff message-scoped (when enabled); Platform Admin/unauth blocked; security manager-only (FR-015, AC-16)
- [ ] created_at server-assigned; deterministic ordering; invalid enum/filter → 422 (FR-016, AC-18)
- [ ] Optional internal write endpoint is service-authenticated + same redaction/validation (FR-017)

---

## Audit Event Requirements

- [ ] `message_received` / `message_created_by_simulator` (message, info) (AC-01)
- [ ] `intent_classified` (ai_service, info; metadata predicted_label + confidence, no prompt) (AC-02)
- [ ] `risk_detected` (ai_service, info/warning; risk_level + short reason)
- [ ] `document_uploaded` (user, info; document_id) / `document_processed` (system, info)
- [ ] `rag_retrieved` (ai_service, info) / `rag_no_source_found` (ai_service, warning; no answer text) (AC-03)
- [ ] `suggested_reply_generated/_edited/_approved/_rejected` with correct actor (ai_service vs user) (AC-04)
- [ ] `task_created/_updated/_completed` (user, info; task_id) (AC-04)
- [ ] `escalation_created/_updated/_resolved` (user, info; escalation_id) (AC-04)
- [ ] `guardrail_refusal` (security; no refused text) / `unsupported_answer_refused` (warning; no answer text) (AC-11)
- [ ] `cross_tenant_access_blocked` (security; attempting tenant; no target data) (AC-10)
- [ ] `user_login` (and optional `user_logout`)
- [ ] Each action emits exactly one entry at completion (no duplicate/partial rows)

---

## Security Requirements

- [ ] `tenant_id` / `actor_user_id` always derived from JWT/service context — never client-supplied (SR-01)
- [ ] An entry belongs to exactly one tenant (SR-02)
- [ ] Append-only / immutable: no update/delete path; DB UPDATE/DELETE revocation recommended (SR-03, AC-05)
- [ ] Role split: managers tenant-wide; staff message-scoped (when enabled); security manager-only; Platform Admin 403; unauth 401 (SR-04, AC-16)
- [ ] Not-found vs forbidden: not-in-tenant → 404; other tenant → 403 (SR-06, AC-08, AC-09)
- [ ] cross_tenant_access_blocked has no target-tenant field (SR-07, FR-013, AC-10)
- [ ] Logging failures caught; never break/roll back/expose internals to the workflow (SR-08, AC-14)
- [ ] No secrets/prompts/JWTs/keys in any stored field (SR-05, AC-12)

---

## Privacy / Redaction Requirements

- [ ] Minimize, don't copy: store ids + minimal facts, not verbatim bodies (PR-01, AC-12)
- [ ] Forbidden content never stored: system/model prompts, JWTs/tokens, API keys/secrets, passwords, raw embeddings, full message/reply/document text, cross-tenant data (PR-02, AC-12)
- [ ] Allowed metadata limited to ids + short facts (predicted_label, confidence, risk_level, *_id, status_from/to, attempted_route, metadata_truncated) (PR-03)
- [ ] metadata size-capped; over-cap truncated + `metadata_truncated=true` (PR-04, AC-13)
- [ ] PII restraint: client names/contact not duplicated beyond an id reference; summary avoids quoting content (PR-05)
- [ ] Security events store only the fact + attempting context, never protected/target data or refused answer text (PR-06, AC-11)
- [ ] Redaction enforced at the single write boundary (denylist + size cap + summary sanitizer)

---

## Tenant Isolation Requirements

- [ ] List/get returns only the caller's tenant entries (AC-06, AC-15)
- [ ] Tenant A cannot read a Tenant B entry (404/403) (AC-08)
- [ ] Tenant A cannot query Tenant B's message-scoped or escalation-scoped audit (AC-09, AC-15)
- [ ] cross_tenant_access_blocked recorded in the attempting tenant only, no target data (AC-10)
- [ ] A client-supplied `tenant_id` is ignored (tenant from JWT/service)
- [ ] No shared/cross-tenant/platform-wide audit view exists
- [ ] The audit log itself never becomes a cross-tenant leak vector (security-event redaction)

---

## API Requirements

- [ ] `GET /api/audit-logs` manager-only; filters + pagination; newest-first (AC-06, AC-07, AC-16)
- [ ] `GET /api/audit-logs/{id}` manager-only; full redacted entry; cross-tenant → 404/403 (AC-08)
- [ ] `GET /api/messages/{id}/audit-logs` manager + staff (when enabled, security excluded); cross-tenant → 404/403 (AC-09, AC-16)
- [ ] `GET /api/escalations/{id}/audit-logs` manager-only; entity-scoped; cross-tenant → 404/403
- [ ] Optional `POST /api/internal/audit-logs` service-authenticated; same redaction/validation; tenant users 403 (FR-017)
- [ ] No tenant create/update/delete routes; mutate attempts → 405 (AC-05)
- [ ] Role matrix enforced; Platform Admin 403; unauthenticated 401 (AC-16)
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] List bounded by `AUDIT_LIST_MAX_LIMIT`; invalid filter/pagination → 422 (AC-18)

---

## Data Requirements

- [ ] `audit_logs` table created via Alembic migration (no `updated_at`)
- [ ] `tenant_id` FK + index; `actor_user_id` nullable FK → users
- [ ] `message_id` nullable FK (`ON DELETE SET NULL`); `entity_id` plain UUID (no cascade onto audit rows)
- [ ] `metadata` JSONB default `{}`; `redacted_summary` TEXT; `request_id` nullable
- [ ] `AuditActorType` enum: user, system, ai_service
- [ ] `AuditSeverity` enum: info, warning, error, security
- [ ] `AuditEntityType` enum (message, conversation, classification_result, risk_assessment, document, rag_retrieval, suggested_reply, task, escalation, user, session)
- [ ] `AuditEventType` enum (the defined event set; closed-but-extensible string-backed)
- [ ] Indexes on `(tenant_id, created_at desc)`, `(tenant_id, event_type)`, `(tenant_id, severity)`, `(tenant_id, actor_user_id)`, `(tenant_id, message_id)`, `(tenant_id, entity_type, entity_id)`
- [ ] `created_at` server-assigned; ordering deterministic (created_at desc, id tiebreak)
- [ ] Append-only enforced at the data/service layer (no mutation path; DB revocation recommended)

---

## Testing Requirements

- [ ] Unit: redaction — forbidden-key stripping, size cap + `metadata_truncated`, summary sanitize, no cross-tenant field (AC-12, AC-13)
- [ ] Unit: service — enum validation, actor/actor_user_id rule, best-effort (injected failure → no raise), deterministic ordering
- [ ] Integration: pipeline writes — message/intent/risk with required fields (AC-01, AC-02)
- [ ] Integration: rag_no_source_found warning w/o answer text (AC-03); reply/task/escalation events (AC-04)
- [ ] Integration: append-only — no mutate route; 405/404 on attempt (AC-05)
- [ ] Integration: manager list newest-first + pagination + tenant scope (AC-06); filters (AC-07)
- [ ] Integration: get one + cross-tenant 404/403 (AC-08); message-scoped list + cross-tenant (AC-09)
- [ ] Integration: cross_tenant_access_blocked in attempting tenant, no target data (AC-10); guardrail/unsupported (AC-11)
- [ ] Integration: redaction over representative events — no secrets/prompts/JWT/keys/cross-tenant (AC-12); oversized truncation (AC-13)
- [ ] Integration: best-effort — injected append failure → primary action still succeeds (AC-14)
- [ ] Integration: tenant isolation list/get (AC-15); role enforcement incl. security-manager-only + Platform Admin 403 + 401 (AC-16); ordering + invalid filter 422 (AC-18)
- [ ] Frontend: dashboard renders entries + filters; severity/actor badges; entry detail shows redacted metadata; no edit/delete controls; staff message-scoped excludes security (AC-17)
- [ ] Quickstart: all 8 steps (message, intent, risk, RAG+reply, task, escalation, cross-tenant, isolation)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No editing or deleting of audit logs (append-only/immutable in MVP)
- [ ] No retention / purge / TTL / archival policy
- [ ] No log export / SIEM streaming / external forwarding (CSV/syslog/webhook)
- [ ] No real-time alerting / notifications on events
- [ ] No cross-tenant or platform-wide audit view
- [ ] No cryptographic tamper-proof chaining / signed / WORM logs
- [ ] No analytics / charts / aggregations beyond filtered listing
- [ ] No storing of full message/reply/document content (minimization only)
- [ ] No storing of system prompts, secrets, JWTs, API keys
- [ ] No real WhatsApp API, no calendar syncing, no full CRM

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build the redaction + service (single best-effort write path) before wiring call sites, and before the read API.
- Hard guarantees to verify: (1) **append-only** — no edit/delete path anywhere; (2) **best-effort** — a logging failure never breaks the primary workflow; (3) **redaction** — no secrets/prompts/JWTs/keys/full-bodies/cross-tenant data in any stored field; (4) **tenant isolation** — Tenant A never sees Tenant B logs, and `cross_tenant_access_blocked` is written in the attacker's tenant only.
- **This is the final MVP feature** — it consumes the actor/action/timestamp signals that features 002–012 already expose and adds the logging service + call sites + read surface.
