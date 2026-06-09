# Research: Escalation to Manager

**Branch**: `012-escalation-to-manager` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Staff-Confirmed Creation; Recommendation Is Read-Only

**Decision**: Escalations are created only via an explicit authenticated `POST /api/escalations`. The high-risk "escalation recommended" indicator is a read-only UI signal sourced from Spec 007's `escalation_recommended` flag; it never creates an escalation.

**Rationale**:
- The constraint is "no auto-create without staff confirmation" (FR-009, SR-07). Keeping the recommendation a display signal and creation a separate write makes this structural.
- Spec 007 already computes `escalation_recommended`, so the recommendation reuses existing data — no new inference here.

**Alternatives considered**:
- Auto-create escalations for all high-risk messages: floods the queue and removes human judgment; rejected for MVP (a "reviewed system action" is mentioned in the spec but explicitly out of scope by default).
- A combined "recommend-and-create" call: easy to misuse; rejected.

---

## Decision 2: Context Snapshot at Creation (not live joins)

**Decision**: At creation, capture `intent_label` (006), `risk_level` + `risk_reason` (007), `source_document_ids`/`source_chunk_ids` (009), `suggested_reply_id` (010), and an `ai_summary` onto the escalation row as a point-in-time snapshot. Later upstream changes do not mutate the escalation.

**Rationale**:
- A manager reviewing an escalation needs to see what the case looked like **when it was escalated**. If a message is re-classified afterwards, the escalation record should not silently change (SR-08, AC-18) — that would rewrite history a manager is acting on.
- Snapshot fields also make the queue fast (no multi-join per row) and keep the record meaningful even if upstream rows change.

**Alternatives considered**:
- Store only foreign keys and join live: simpler schema but loses point-in-time fidelity and complicates the queue; the `suggested_reply_id` is kept as a live link (its lifecycle is independent), while intent/risk are snapshotted.
- Full document/chunk text snapshot: heavy and redundant; storing source **ids** + the snippet via the reply/RAG records is enough.

---

## Decision 3: Status State Machine with Terminal Immutability

**Decision**: `EscalationStatus` = `open → in_review → resolved | cancelled`, with `open → resolved|cancelled` allowed. `resolved`/`cancelled` are terminal; edits/transitions on terminal escalations are rejected (422). `resolved` sets `resolved_at`.

**Rationale**:
- A small explicit machine models the manager review lifecycle and prevents nonsensical transitions (e.g., editing a resolved case). Terminal immutability keeps closed cases trustworthy for the audit feature.
- No auto-resolve: resolution is always a manager action (SR-07).

**Alternatives considered**:
- Free-form status: error-prone; rejected.
- Reopen resolved escalations: useful but adds transition + audit nuance; deferred (out of scope MVP).

---

## Decision 4: Role Split — Staff Create/View, Manager Review/Resolve

**Decision**: `staff` may create and view escalations; only `manager` may set `in_review`, assign, add `manager_notes`, resolve, and cancel. Platform Admin blocked. Enforced via per-action `require_role`.

**Rationale**:
- Matches the feature intent: staff raise cases, managers decide. The queue + resolution is a manager responsibility (FR-015, SR-04).
- Staff still need visibility (to see status of what they raised), hence staff read access.

**Alternatives considered**:
- Staff can resolve their own escalations: undermines the manager-review purpose; rejected.
- Manager-only everything (no staff view): staff lose feedback on raised cases; rejected.

---

## Decision 5: In-Tenant Reference Validation (message, reply, manager assignee)

**Decision**: On create/update, resolve `message_id`, `suggested_reply_id`, and `assigned_manager_id` within the JWT tenant. The assignee must have role `manager`. Cross-tenant message → 404/403; cross-tenant/mismatched reply → 422/403; non-manager/cross-tenant assignee → 422 `INVALID_ASSIGNEE`.

**Rationale**:
- Tenancy must hold for every referenced entity (SR-03). Validating up front prevents an escalation pointing across tenants or to a non-manager.
- The reply must belong to the same message/tenant to be a valid captured link.

---

## Decision 6: Message Status → `escalated` (non-destructive side effect)

**Decision**: On creation, set the related message's status to `escalated` (reusing the Spec 003/005 message-status model). Isolated so a failure there never fails escalation creation; does not block other escalations/tasks.

**Rationale**:
- Gives inbox/detail a visible signal that a message has been escalated (FR-014, AC-16). Non-destructive + isolated keeps the primary action robust. Consistent with Spec 011's `task_created` approach.

**Alternatives considered**:
- A boolean flag instead of status value: viable; the spec calls for `escalated` status, so we reuse the status field (documented). Either acceptable.

---

## Decision 7: No Side Effects — No Send, No Reply-Approval, No Task

**Decision**: No escalation endpoint or method sends a client message, approves/sends the Spec 010 suggested reply, or creates a Spec 011 task. The escalation only links the reply (`suggested_reply_id`); the reply's lifecycle stays independent.

**Rationale**:
- Direct scope boundary (FR-010, FR-011, FR-012, SR-06). Escalation is a routing/review entity; entangling it with messaging/reply-approval/tasks would couple features and risk accidental client communication or premature approval. Example 2 explicitly escalates **before** the reply is approved.

---

## Decision 8: Enums as Constrained Strings

**Decision**: `EscalationStatus` and `EscalationPriority` persist as application-level string enums in VARCHAR columns, validated at the boundary.

**Rationale**:
- Portable + evolvable (e.g., a future `waiting_on_client` status) without enum-altering migrations; invalid values rejected at the API (422).

---

## Decision 9: Priority Default from Risk; Queue Ordering

**Decision**: `priority` defaults from the risk level when omitted (high risk → `high`/`urgent`; otherwise `medium`), staff-overridable. The queue orders by priority (urgent → high → medium) then status (open/in_review first) then age.

**Rationale**:
- Managers should see the most pressing cases first. Deriving the default from existing risk reuses upstream signal and matches the examples (high-risk complaint → high/urgent).

**Resolved defaults**:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ESCALATION_DEFAULT_PRIORITY` | `medium` | When no priority + no risk hint |
| `ESCALATION_SUMMARY_ENABLED` | `true` | Toggle the optional AI summary |
| Queue ordering | `priority desc, status (open/in_review first), created_at asc` | Manager triage |

---

## Decision 10: Optional AI Summary (non-fatal)

**Decision**: An `EscalationSummarizer` produces a short `ai_summary` from the captured context. It is optional: if the summary service fails, the escalation is still created (without a summary). Behind an interface with a deterministic stub for tests.

**Rationale**:
- The summary speeds manager triage but must never block raising an escalation (a safety/operational action). Decoupling keeps creation robust.

---

## Decision 11: Audit Logging Is a Future Integration, Not Built Here

**Decision**: This feature does not implement audit logging. Each escalation records actor (`created_by`, `assigned_manager_id`), action via status + notes, and timestamps — enough for the later audit-log feature to record create/update/resolve/cancel/assign/notes events.

**Rationale**:
- Explicitly requested. Keeping audit out avoids premature coupling; the audit feature will hook escalation service events when built. Named as a dependency/future integration in the spec.

---

## Decision 12: Duplicate Escalations Allowed but Discouraged

**Decision**: A message may have more than one escalation (e.g., re-raised after cancellation). Creation does not hard-block on an existing open escalation; the UI warns and links the existing one.

**Rationale**:
- Hard-blocking could trap staff if an escalation was wrongly cancelled; a soft warning preserves flexibility while discouraging accidental duplicates. `GET /messages/{id}/escalations` surfaces existing ones.
