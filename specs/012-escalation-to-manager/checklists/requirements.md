# Requirements Checklist: Escalation to Manager

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (routing risky cases to managers) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI behavior, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Staff can create an escalation from a message, scoped to tenant, status `open`, created_by set (FR-001, AC-01)
- [ ] On create, context snapshot captured: intent_label, risk_level, risk_reason, source ids, suggested_reply_id, ai_summary (FR-002, AC-02)
- [ ] Stored fields match the spec list (id, tenant_id, message_id, created_by, assigned_manager_id, intent_label, risk_level, risk_reason, ai_summary, suggested_reply_id, source_document_ids, source_chunk_ids, status, priority, manager_notes, created_at, updated_at, resolved_at) (FR-003)
- [ ] Priority/status/assignee validated (FR-004)
- [ ] Manager can list (queue) + fetch single with full context (FR-005, AC-05, AC-07)
- [ ] Manager can update status/priority/assignee/notes + assign/reassign (FR-006, AC-08)
- [ ] Manager can resolve (resolved_at) and cancel (FR-007, AC-09)
- [ ] Invalid state transitions rejected (FR-008, AC-10)
- [ ] High-risk messages get an escalation recommendation; no auto-create (FR-009, AC-14)
- [ ] Creation/updates send no client message (FR-010, AC-13)
- [ ] Creation/updates do not approve/send the suggested reply (FR-011, AC-13)
- [ ] Creation/updates create no task (FR-012, AC-13)
- [ ] Operations tenant-scoped (FR-013, AC-04)
- [ ] On create, related message may become `escalated` (FR-014, AC-16)
- [ ] Only manager resolves/cancels/adds notes; staff create + view (FR-015, AC-11)
- [ ] created_by + timestamps recorded; resolved_at on resolve; context is a snapshot (FR-016, AC-18)

---

## Escalation Workflow Requirements

- [ ] Status lifecycle: open → in_review → resolved | cancelled
- [ ] `open → resolved|cancelled` directly allowed
- [ ] `resolved`/`cancelled` terminal; edits/transitions rejected (AC-10)
- [ ] `resolved` sets `resolved_at`; no auto-resolve
- [ ] Resolved/cancelled escalations remain in the queue (filterable)
- [ ] Priority defaults from risk when omitted; staff-overridable
- [ ] Queue ordered urgent/open first
- [ ] Duplicate escalations allowed but UI warns/links existing

---

## Optional AI Recommendation Requirements

- [ ] Escalation recommendation surfaced for high-risk messages from Spec 007 `escalation_recommended` (read-only) (AC-14)
- [ ] Recommendation never auto-creates an escalation (SR-07)
- [ ] Optional `ai_summary` generated from captured context (snapshot)
- [ ] Suggested priority derived from risk; staff-overridable
- [ ] Summary-service failure does not block creation (created without summary)
- [ ] Summary feature flag can disable cleanly

---

## Manager Review Requirements

- [ ] Manager queue lists tenant escalations with priority/status/intent/risk/assignee/message (AC-05)
- [ ] Manager can open full captured context (AC-07)
- [ ] Manager can move open → in_review and assign to an in-tenant manager (AC-08)
- [ ] Manager can add manager_notes (AC-08)
- [ ] Manager can resolve (resolved_at) and cancel (AC-09)
- [ ] Staff cannot resolve/cancel/assign/add notes (403) (AC-11)
- [ ] Terminal escalations are read-only (AC-10)

---

## Security Requirements

- [ ] `tenant_id` always derived from JWT — never from the client (SR-01)
- [ ] An escalation belongs to exactly one tenant (SR-02)
- [ ] `message_id`, `suggested_reply_id`, `assigned_manager_id` resolve in-tenant; assignee is a manager (SR-03, AC-08, AC-18)
- [ ] staff create+view; manager resolve/assign/notes; Platform Admin → 403 (SR-04, AC-11, AC-15)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent escalation/message → 404; cross-tenant → 403 (SR-05)
- [ ] No client message; no reply approval/send; no task (SR-06)
- [ ] AI cannot auto-create or auto-resolve (SR-07)
- [ ] Captured snapshot not silently mutated; created_by/assignee not spoofable cross-tenant (SR-08, AC-18)

---

## Tenant Isolation Requirements

- [ ] Queue returns only the caller's tenant escalations (AC-04, AC-05)
- [ ] Tenant A cannot read/update/resolve a Tenant B escalation (AC-07)
- [ ] Cross-tenant related message rejected on create (AC-18)
- [ ] Cross-tenant / non-manager assignee rejected (AC-08, INVALID_ASSIGNEE)
- [ ] Cross-tenant suggested_reply_id rejected
- [ ] `GET /messages/{id}/escalations` is tenant-scoped (AC-12)
- [ ] A client-supplied `tenant_id` is ignored (tenant from JWT)
- [ ] No shared/cross-tenant escalations exist

---

## API Requirements

- [ ] `POST /api/escalations` creates with snapshot (201); validates refs (AC-01, AC-02, AC-18)
- [ ] `GET /api/escalations` queue with status/priority/assignee filters (AC-05, AC-06)
- [ ] `GET /api/escalations/{id}` full context; cross-tenant → 404/403 (AC-07)
- [ ] `PATCH /api/escalations/{id}` manager-only; status/priority/assignee/notes; terminal → 422 (AC-08, AC-10, AC-11)
- [ ] `POST /api/escalations/{id}/resolve` manager-only; sets resolved_at; terminal → 422 (AC-09, AC-11)
- [ ] `GET /api/messages/{id}/escalations` lists a message's escalations (AC-12)
- [ ] Role matrix enforced (create/view staff+manager; mutate manager); Platform Admin 403 (AC-15)
- [ ] Error responses use consistent `error_code` values per the contract

---

## Data Requirements

- [ ] `escalations` table created via Alembic migration
- [ ] `message_id` FK (`ON DELETE CASCADE`) + index; `tenant_id` FK + index
- [ ] `created_by` FK → users; `assigned_manager_id` nullable FK → users; `suggested_reply_id` nullable FK
- [ ] Snapshot fields: intent_label, risk_level, risk_reason, ai_summary, source_document_ids, source_chunk_ids
- [ ] `EscalationStatus` enum: open, in_review, resolved, cancelled
- [ ] `EscalationPriority` enum: medium, high, urgent
- [ ] `status` defaults `open`; `priority` defaults `medium`/from-risk; `resolved_at` set only when resolved
- [ ] Indexes on `(tenant_id, status)`, `(tenant_id, priority)`, `(tenant_id, assigned_manager_id)`, `(tenant_id, message_id)`
- [ ] `messages.status` supports `escalated` (migration or free-string), non-destructive
- [ ] State machine enforced at the data/service layer

---

## Testing Requirements

- [ ] Unit: state machine (valid/invalid transitions), assignee in-tenant-manager validation, snapshot capture, priority-from-risk
- [ ] Unit: escalation summarizer (deterministic stub, unavailable fallback)
- [ ] Integration: create + snapshot (AC-01, AC-02); created without reply/RAG (AC-03)
- [ ] Integration: tenant isolation list/get (AC-04, AC-05, AC-07)
- [ ] Integration: queue filters (AC-06); update + bad assignee (AC-08)
- [ ] Integration: resolve + resolved_at; cancel (AC-09); invalid transitions (AC-10)
- [ ] Integration: role split — staff resolve 403 (AC-11)
- [ ] Integration: message escalations list (AC-12); no message/reply-approve/task side effects (AC-13)
- [ ] Integration: recommendation present + no auto-create (AC-14); Platform Admin 403 (AC-15); message → escalated (AC-16)
- [ ] Integration: cross-tenant message rejected + snapshot immutable after re-classify (AC-18)
- [ ] Frontend: queue + detail render; manager resolve/assign/notes; staff cannot resolve; recommendation banner + confirm-to-create (AC-17)
- [ ] Quickstart: all 5 scenarios (complaint, cancellation, payment, manager review, isolation)

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No sending of any client message
- [ ] No approving/sending the AI suggested reply (Spec 010 lifecycle independent)
- [ ] No follow-up task creation (Spec 011 separate)
- [ ] No auto-creation of escalations (staff confirmation required)
- [ ] No auto-resolution of escalations (manager action only)
- [ ] No audit-log implementation (named as a future integration/dependency)
- [ ] No notifications / paging / email alerts
- [ ] No SLA timers / auto-escalation on timeout
- [ ] No cross-tenant or shared escalations
- [ ] No full CRM / case management
- [ ] No real WhatsApp API, no calendar syncing

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build the service (tenant + role + assignee-manager validation + state machine + snapshot) before the API; the AI recommendation/summary are read-only/non-fatal.
- Hard guarantees to verify: (1) no auto-create — recommendation is read-only, creation is a staff-confirmed POST; (2) no auto-resolve — resolution is manager-only; (3) no side effects — no client message, no reply approval/send, no task.
- **Audit logging is a future integration** — this feature records actor + action + timestamps for the later audit-log feature; it does not implement logging.
