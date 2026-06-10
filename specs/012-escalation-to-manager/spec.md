# Feature Specification: Escalation to Manager

**Feature Branch**: `012-escalation-to-manager`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 006 — Intent Classifier](../006-intent-classifier/spec.md)
- [Spec 007 — Risk Detection](../007-risk-detection/spec.md)
- [Spec 009 — RAG Over Tenant Documents](../009-rag-over-tenant-documents/spec.md)
- [Spec 010 — Suggested Replies](../010-suggested-replies/spec.md)

**Input**: User description: "The system should allow staff users to escalate risky or complex client messages to a manager for review. Escalations should be linked to the original message, tenant, intent classification, risk assessment, RAG sources if available, suggested reply if available, and escalation status."

---

## Goal

Let staff hand off risky or complex client messages to a manager for review, capturing the full AI context so the manager can decide quickly. An escalation is created from the message detail page and snapshots the message's intent (006), risk (007), RAG sources (009), and suggested reply (010), plus a short AI summary. High-risk messages show an escalation recommendation, but staff confirm the escalation — it is not auto-created (unless explicitly configured as a reviewed system action). Managers work an escalation queue: open a case, add review notes, change status, and resolve it. Creating an escalation sends no message to the client and never approves/sends the suggested reply. Every escalation is tenant-scoped; Tenant A can never access Tenant B escalations. This closes the MVP triage loop: risky cases reach a human decision-maker with all the evidence attached.

---

## Escalation Statuses

| Status | Meaning |
|--------|---------|
| `open` | Created by staff; awaiting manager pickup |
| `in_review` | A manager is actively reviewing it |
| `resolved` | Manager finished the case (records `resolved_at`) |
| `cancelled` | Escalation withdrawn / not needed |

## Escalation Priority

| Priority | Meaning |
|----------|---------|
| `medium` | Needs manager attention |
| `high` | Needs prompt manager attention |
| `urgent` | Needs immediate manager attention |

---

## Escalation Triggers (typical)

Escalation is appropriate for (staff-confirmed) messages such as: `complaint`, `cancellation_request`, `payment_issue`, `urgent_change`, `human_escalation`, high-risk `guest_count_change`, and `unsupported_or_unclear_request` that needs a human decision. These map from the Spec 006 intent + Spec 007 risk; the risk engine's `escalation_recommended` flag drives the UI recommendation.

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | Creates an escalation from the message detail page when a case needs manager judgment; provides a reason/priority; cannot resolve escalations. |
| **Manager** | Works the escalation queue: opens a case, moves it to `in_review`, adds review notes, sets/changes priority and assignee, and resolves (or cancels) it. |
| **System / AI service** | May *recommend* escalation (from risk) and pre-fill the AI summary/context, but does not create an escalation without staff confirmation. Not a human actor. |

Platform Admin has no access to tenant escalations.

---

## User Stories

### User Story 1 — Staff Escalates a Message to a Manager (Priority: P1)

A staff planner, viewing a risky/complex client message, creates an escalation. The system snapshots the message's intent, risk (level + reason), RAG source ids, and suggested reply id (when present), plus an AI summary, and stores the escalation linked to the message, scoped to the tenant, with status `open` and `created_by` = the staff user.

**Why this priority**: Routing risky cases to a manager is the feature's core purpose — without creation there is no queue to review. Every manager action operates on escalations created here.

**Independent Test**: From an Elegant Weddings high-risk complaint, create an escalation. Verify an `Escalation` is stored in the Elegant Weddings tenant, linked to the message, status `open`, capturing `intent_label`, `risk_level`, `risk_reason`, `source_document_ids`/`source_chunk_ids` (if RAG ran), `suggested_reply_id` (if a reply exists), priority, and `created_by`. Verify it is not visible to Royal Events Agency.

**Acceptance Scenarios**:

1. **Given** an authenticated staff user viewing a message in their tenant, **When** they submit an escalation (priority + optional reason), **Then** an `Escalation` is created linked to the message, scoped to the tenant, with status `open`, `created_by` = the user, and the captured context snapshot, and timestamps set.
2. **Given** the message has intent (006), risk (007), RAG sources (009), and/or a suggested reply (010), **When** the escalation is created, **Then** those are captured as `intent_label`, `risk_level`, `risk_reason`, `source_document_ids`/`source_chunk_ids`, `suggested_reply_id`, and an `ai_summary`.
3. **Given** a message with no RAG/reply yet, **When** the escalation is created, **Then** the escalation is still created with the available context (source/reply fields empty/null) — escalation does not require a reply to exist.
4. **Given** a staff user in Tenant A, **When** they create an escalation, **Then** it is scoped to Tenant A and never visible to Tenant B.
5. **Given** an escalation is created, **When** creation succeeds, **Then** the related message status may become `escalated` and the escalation appears in the manager queue.

---

### User Story 2 — Manager Works the Escalation Queue (Priority: P1)

A manager opens an escalation queue listing the tenant's escalations with priority, status, intent, risk, assignee, and the related message. They filter (status/priority/assignee), open a case to see the full captured context, move it to `in_review`, and assign it (to themselves or another manager).

**Why this priority**: Escalations are only useful if a manager can find and work them. The queue + detail view is the operational backbone of the feature. Equal P1 because creating escalations with no review surface delivers little.

**Independent Test**: With several escalations in a tenant, list them as a manager — verify only that tenant's escalations appear with full metadata, ordered sensibly (e.g., urgent/open first). Filter by `priority=urgent`. Open one — verify the captured message, intent, risk, sources, and suggested reply context. Move it to `in_review` and assign it — verify changes persist.

**Acceptance Scenarios**:

1. **Given** escalations exist in a tenant, **When** a manager lists them, **Then** only that tenant's escalations are returned with priority, status, `intent_label`, `risk_level`, `assigned_manager_id`, `message_id`, timestamps.
2. **Given** filters (status, priority, assignee), **When** the list is requested with them, **Then** only matching tenant escalations are returned.
3. **Given** an escalation in the caller's tenant, **When** a manager opens it, **Then** the full captured context (message, intent, risk + reason, AI summary, RAG sources, suggested reply) is returned.
4. **Given** an `open` escalation, **When** a manager sets it `in_review` and/or assigns a manager, **Then** the changes persist and `updated_at` refreshes.
5. **Given** an escalation from another tenant, **When** referenced, **Then** it is blocked (404/403) and no change occurs.

---

### User Story 3 — Manager Adds Notes and Resolves (Priority: P1)

A manager records review notes and resolves the escalation (status `resolved`, recording when), or cancels it if it was unnecessary. Resolved/cancelled escalations remain in the queue (filterable) for record-keeping.

**Why this priority**: Closing the loop with a human decision is the point of escalation. Equal P1 because an escalation that can never be resolved is just an alert with no outcome.

**Independent Test**: Take an `open`/`in_review` escalation, add `manager_notes`, and resolve it — verify status `resolved`, `resolved_at` set, notes stored. Cancel another — verify status `cancelled`. Verify both remain listed under the appropriate status filter and that resolving an already-resolved escalation is rejected.

**Acceptance Scenarios**:

1. **Given** an `open`/`in_review` escalation, **When** a manager adds `manager_notes`, **Then** the notes are stored and `updated_at` refreshes.
2. **Given** an `open`/`in_review` escalation, **When** a manager resolves it, **Then** status becomes `resolved` and `resolved_at` is recorded.
3. **Given** an escalation, **When** a manager cancels it, **Then** status becomes `cancelled`.
4. **Given** a `resolved`/`cancelled` escalation, **When** anyone attempts to resolve/cancel/edit it again, **Then** the request is rejected (invalid state transition) — terminal states are immutable.
5. **Given** a staff (non-manager) user, **When** they attempt to resolve an escalation, **Then** the request is rejected (403) — only managers resolve.

---

### User Story 4 — Escalation Recommendation for High-Risk Messages (Optional) (Priority: P2)

On the message detail page, high-risk messages (Spec 007 `escalation_recommended = true`) show an escalation recommendation prompting staff to escalate. The recommendation is informational; staff still confirm. The system may pre-fill the escalation's priority/summary from the risk context.

**Why this priority**: The recommendation improves triage speed and consistency, but escalation works fully via manual creation (US1). Lower priority and explicitly does not auto-create.

**Independent Test**: For a high-risk complaint, open the detail page — verify an "escalation recommended" indicator appears. Click escalate — verify the form is pre-filled (e.g., priority `high`) and the escalation is created only on confirmation.

**Acceptance Scenarios**:

1. **Given** a message with risk `high` / `escalation_recommended = true`, **When** the detail page renders, **Then** an escalation recommendation is shown.
2. **Given** the recommendation, **When** staff initiate escalation, **Then** the form may be pre-filled (priority/summary) from the risk context, and the escalation is created only on explicit confirmation.
3. **Given** a low-risk message, **When** the detail page renders, **Then** no escalation recommendation is forced (staff may still escalate manually).

---

### Edge Cases

- **Message already escalated**: a message may have an existing open escalation; creating another is allowed but the UI warns/links to the existing one (no hard block; duplicates allowed but discouraged).
- **No suggested reply / no RAG yet**: escalation is still created with whatever context exists; `suggested_reply_id` and source ids may be null/empty.
- **Assignee not a manager / not in tenant**: rejected (assignee must be an in-tenant manager).
- **Empty reason**: allowed (reason optional); priority required or defaulted.
- **Resolve without notes**: allowed (notes optional, but recommended).
- **Escalation does not send anything**: creating/resolving never messages the client and never approves/sends the suggested reply.
- **Concurrent manager actions**: last write wins for fields; terminal transitions guarded.
- **Cross-tenant id guessing**: requesting/modifying another tenant's escalation, or referencing another tenant's message/reply/manager → 404/403.
- **Captured snapshot vs live data**: captured `intent_label`/`risk_level`/`risk_reason`/`ai_summary` reflect the time of escalation; later re-classification does not silently mutate the escalation record (snapshot semantics).
- **Suggested reply later edited/approved**: the escalation keeps the `suggested_reply_id` link; the reply's own lifecycle (Spec 010) is independent.

---

## Requirements

### Functional Requirements

- **FR-001**: Staff MUST be able to create an escalation from a message, scoped to their tenant, linked via `message_id`, with status `open` and `created_by` = the staff user.
- **FR-002**: On creation, the system MUST capture a context snapshot: `intent_label` (006), `risk_level` + `risk_reason` (007), `source_document_ids`/`source_chunk_ids` (009 if available), `suggested_reply_id` (010 if available), and an `ai_summary`.
- **FR-003**: The system MUST store escalation fields: `id`, `tenant_id`, `message_id`, `created_by`, `assigned_manager_id`, `intent_label`, `risk_level`, `risk_reason`, `ai_summary`, `suggested_reply_id`, `source_document_ids`, `source_chunk_ids`, `status`, `priority`, `manager_notes`, `created_at`, `updated_at`, `resolved_at`.
- **FR-004**: The system MUST validate priority (valid enum), status transitions, and that `assigned_manager_id` (if set) is a **manager** in the caller's tenant.
- **FR-005**: Managers MUST be able to list escalations (queue) in their tenant, filtered by status, priority, and assignee, and fetch a single escalation with full context.
- **FR-006**: Managers MUST be able to update an escalation (status, priority, assignee, notes) and assign/reassign to an in-tenant manager.
- **FR-007**: Managers MUST be able to resolve an escalation (status `resolved`, set `resolved_at`) and cancel it (status `cancelled`).
- **FR-008**: The system MUST reject invalid state transitions (editing/resolving/cancelling a terminal escalation; resolving a cancelled one).
- **FR-009**: The system MAY recommend escalation for high-risk messages (from Spec 007 `escalation_recommended`), but MUST NOT auto-create an escalation without staff confirmation (unless a reviewed system action is explicitly configured).
- **FR-010**: Escalation creation/updates MUST NOT send any message to the client.
- **FR-011**: Escalation creation/updates MUST NOT approve or send the AI suggested reply (Spec 010 lifecycle is independent).
- **FR-012**: Escalation creation/updates MUST NOT create a follow-up task (Spec 011 is a separate feature).
- **FR-013**: The system MUST scope every escalation operation to the caller's tenant; cross-tenant access MUST be blocked.
- **FR-014**: On creation, the related message's status MAY become `escalated` (non-destructive; see Assumptions).
- **FR-015**: Only `manager` may resolve/cancel and add manager notes; `staff` may create and view; the system MUST enforce this role split.
- **FR-016**: The system MUST record `created_by` and maintain `created_at`/`updated_at` (and `resolved_at` on resolution); captured context is a snapshot at creation time.

### Key Entities

- **Tenant** (001): scopes all escalations.
- **User** (002): `created_by` (staff), `assigned_manager_id` (a manager); role gates actions.
- **Message** (003): the escalated message (`message_id`).
- **ClassificationResult** (006): source of `intent_label`.
- **RiskAssessment** (007): source of `risk_level` + `risk_reason` + escalation recommendation.
- **SuggestedReply** (010): linked via `suggested_reply_id` (independent lifecycle).
- **RAG sources** (009): captured as `source_document_ids`/`source_chunk_ids`.
- **Escalation** (new): the manager-review case with its lifecycle.
- **EscalationStatus** (enum): `open`, `in_review`, `resolved`, `cancelled`.
- **EscalationPriority** (enum): `medium`, `high`, `urgent`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Message | `POST /api/escalations` | The escalated message (`message_id`, in-tenant) |
| Priority | Create/update request | `medium`/`high`/`urgent` (defaulted from risk if omitted) |
| Reason / notes | Create request / manager update | Optional staff reason; manager review notes |
| Assignee | Create/update request | An in-tenant **manager** (optional) |
| Status change | Update / resolve | Lifecycle transition |
| Captured context | Specs 006/007/009/010 | Snapshotted at creation |
| Filters | Queue request | status / priority / assignee |

---

## Outputs

| Output | Description |
|--------|-------------|
| Created escalation | Stored, linked to the message, status `open`, with context snapshot |
| Escalation queue | Tenant-scoped list with priority/status/intent/risk/assignee/message |
| Single escalation | Full captured context for one in-tenant escalation |
| Updated escalation | Reflecting status/priority/assignee/notes changes |
| Resolved/cancelled escalation | Terminal status (+ `resolved_at` on resolution) |
| Escalation recommendation | Detail-page indicator for high-risk messages |
| Message status change | Related message may become `escalated` |
| 403 / 404 | Cross-tenant / platform-admin / staff-resolve / missing message/escalation/manager |
| 422 | Invalid priority / invalid transition / invalid assignee |

---

## Main Workflow

1. **Staff views a risky message** on the detail page; a high-risk message shows an **escalation recommendation** (Spec 007).
2. **Staff escalates** — `POST /api/escalations` with `message_id` + priority (+ optional reason). The system captures the context snapshot (intent, risk + reason, RAG source ids, suggested reply id, AI summary).
3. **Escalation created** — status `open`, `created_by` set, tenant-scoped; the related message may become `escalated`.
4. **Manager queue** — the escalation appears in the manager's queue (filter/sort by priority/status).
5. **Manager reviews** — opens the case, sees full context, moves it to `in_review`, assigns it.
6. **Manager decides** — adds `manager_notes`, then resolves (`resolved`, `resolved_at`) or cancels (`cancelled`).

No client message is sent, the suggested reply is not approved/sent, and no task is created at any step.

---

## Alternative Workflows

### Recommended Escalation (high-risk)

1. A high-risk complaint shows the escalation recommendation on the detail page.
2. Staff clicks escalate; the form is pre-filled (e.g., priority `high`) from risk context.
3. Staff confirms → escalation created (never auto-created).

### Escalate Before Replying (cancellation)

1. A cancellation request (high risk) has a grounded suggested reply (Spec 010).
2. Staff escalates for manager review **before** the reply is approved/sent.
3. The escalation captures `suggested_reply_id`; the reply remains in its own (un-approved) state — escalation does not approve/send it.

### Manager Review Flow

1. Manager opens the queue, picks an `open` escalation, sets it `in_review`, assigns to self.
2. Reviews context, adds notes, and resolves (or cancels).
3. The resolved escalation stays in the queue under the `resolved` filter.

### Payment Issue — Escalate or Task

1. A payment issue (medium/high) — staff may create a task (Spec 011) **or** escalate.
2. If escalated, the manager reviews; this feature does not create the task (separate feature).

### Cross-Tenant Attempt

1. A Tenant B user requests/edits a Tenant A escalation, or assigns a Tenant A manager.
2. Tenant resolution returns 404/403; no data exposed; no change made.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Staff can create an escalation linked to a message; stored in tenant, status `open`, created_by, timestamps, with context snapshot | Integration test: POST → assert fields + snapshot |
| AC-02 | Context capture: intent_label, risk_level, risk_reason, source ids, suggested_reply_id, ai_summary populated from upstream when available | Integration test: assert captured values |
| AC-03 | Escalation is created even when RAG/reply absent (fields null/empty) | Integration test: message w/o reply → escalation created |
| AC-04 | Escalations are tenant-scoped; Tenant B cannot list/read Tenant A escalations | Integration test: create in A; list/get as B → not present / 404-403 |
| AC-05 | Manager queue returns only the tenant's escalations with metadata | Integration test: escalations in A + B → list in A returns only A |
| AC-06 | Queue filters by status, priority, assignee work within the tenant | Integration test: assert filtered subsets |
| AC-07 | `GET /api/escalations/{id}` returns full captured context; cross-tenant → 404/403 | Integration test |
| AC-08 | Manager can update status/priority/assignee/notes; out-of-tenant or non-manager assignee rejected | Integration test: update ok; bad assignee → 422/403 |
| AC-09 | Manager can resolve (status `resolved` + resolved_at) and cancel (status `cancelled`) | Integration test |
| AC-10 | Invalid transitions rejected (edit/resolve/cancel a terminal escalation) | Integration test → 422 INVALID_STATE_TRANSITION |
| AC-11 | Only managers resolve/cancel/add notes; staff create + view only | Integration test: staff resolve → 403 |
| AC-12 | `GET /api/messages/{id}/escalations` returns the message's tenant-scoped escalations | Integration test; cross-tenant → 404/403 |
| AC-13 | Escalation creation sends no client message, does not approve/send the reply, and creates no task | Code/integration test: assert no such side effects |
| AC-14 | High-risk messages show an escalation recommendation; escalation is never auto-created | Frontend/integration test: recommendation present; no escalation without POST |
| AC-15 | Platform Admin blocked from all escalation endpoints (403) | Integration test: admin → 403 INSUFFICIENT_ROLE |
| AC-16 | On creation, related message status may become `escalated` | Integration test: create → assert message status |
| AC-17 | Manager queue + escalation detail display escalations with context | Frontend test: assert rendering |
| AC-18 | Non-existent/cross-tenant message rejected on create; captured context is a snapshot (later re-classification doesn't mutate it) | Integration test: bad message → 404/403; re-classify → escalation unchanged |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenants, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT; `staff` (create/view) + `manager` (review/resolve); assignee must be in-tenant manager; Platform Admin blocked |
| Spec 003 — Message Simulator | Required | The escalated message (`message_id`) |
| Spec 004 — Message Inbox | Required (light) | May show an "escalated" indicator |
| Spec 005 — Message Detail Page | Required | Entry point; replaces the "Escalate" placeholder; shows the recommendation |
| Spec 006 — Intent Classifier | Required | `intent_label` snapshot |
| Spec 007 — Risk Detection | Required | `risk_level` + `risk_reason` + `escalation_recommended` |
| Spec 009 — RAG Over Tenant Documents | Optional | `source_document_ids`/`source_chunk_ids` when available |
| Spec 010 — Suggested Replies | Optional | `suggested_reply_id` when available (independent lifecycle) |
| Audit Log (future feature) | Future integration | Escalation actions (create/update/resolve/cancel/assign/notes) will be logged by the later audit-log feature; **not implemented here** |

---

## AI Behavior

- **Recommendation, not creation**: the system surfaces an escalation recommendation for high-risk messages using Spec 007's `escalation_recommended` flag. It never creates an escalation without staff confirmation (FR-009), unless a reviewed system action is explicitly configured (out of scope for MVP default).
- **Context summary**: the AI may generate a short `ai_summary` of the case (message + intent + risk + sources) to help the manager triage quickly. The summary is captured at creation as a snapshot.
- **Priority hint from risk**: suggested priority may be derived from the risk level (high/urgent for high risk), staff-overridable.
- **No autonomous side effects**: recommending or summarising creates nothing, sends nothing, approves nothing, and resolves nothing.
- **Graceful fallback**: if the summary service is unavailable, escalation creation still works (summary optional).

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the JWT. No client-supplied tenant accepted. Escalations are created/queried only within the session tenant. |
| **SR-02: Escalation tenancy** | An escalation belongs to exactly one tenant. Tenant A can never list/read/update/resolve Tenant B escalations. |
| **SR-03: In-tenant references** | `message_id`, `suggested_reply_id`, and `assigned_manager_id` must resolve within the caller's tenant; cross-tenant references are rejected (404/403/422). |
| **SR-04: Role split** | `staff` may create + view; only `manager` may resolve/cancel, add manager notes, and assign. Platform Admin → 403. Unauthenticated → 401. |
| **SR-05: Not Found vs Forbidden** | An escalation/message not in the caller's tenant → 404; one in another tenant → 403 (consistent with Specs 005–011). |
| **SR-06: No autonomous actions** | Escalation creation/updates send no client message (FR-010), do not approve/send the suggested reply (FR-011), and create no task (FR-012). |
| **SR-07: No AI auto-create / auto-resolve** | The AI may only recommend/summarise; creation requires staff confirmation and resolution requires a manager. No auto-resolve. |
| **SR-08: Snapshot integrity** | Captured context (intent/risk/summary/source ids/reply id) is recorded at creation and not silently mutated by later upstream changes; `created_by`/`assigned_manager_id` cannot be spoofed cross-tenant. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Invalid priority value | 422 validation; nothing stored |
| Invalid status transition (edit/resolve/cancel terminal) | 422 `INVALID_STATE_TRANSITION`; no change |
| `assigned_manager_id` not an in-tenant manager | 422 `INVALID_ASSIGNEE`; no change |
| `message_id` non-existent / cross-tenant | 404 / 403; nothing stored |
| `suggested_reply_id` cross-tenant / mismatched message | 422 / 403; nothing stored |
| Staff attempts to resolve/cancel/add manager notes | 403 `INSUFFICIENT_ROLE`; no change |
| Cross-tenant escalation access | 404/403 per SR-05; no data exposed |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE` |
| AI summary service unavailable | Escalation created without `ai_summary` (or with a placeholder); creation not blocked |
| Storage write fails | 5xx; no partial escalation persisted (transactional create) |

---

## Edge Cases (summary)

- Message already escalated → new escalation allowed; UI warns/links existing.
- No reply/RAG → escalation still created; those fields null/empty.
- Assignee must be an in-tenant manager.
- Reason/notes optional; priority defaulted from risk if omitted.
- Terminal-state edits/resolves → 422.
- Cross-tenant id/assignee/reply → 404/403/422.
- Snapshot semantics: later re-classification doesn't mutate the escalation.
- Concurrent manager actions → last write wins; terminal guarded.

---

## Out of Scope

- **Sending any message to the client** — no WhatsApp/email/SMS; nothing transmitted.
- **Approving/sending the AI suggested reply** — Spec 010's lifecycle is independent; escalation only links it.
- **Creating follow-up tasks** — Spec 011 is a separate feature; escalation creates no task.
- **Auto-creating escalations** — staff confirmation required (no auto-create in MVP default).
- **Auto-resolving escalations** — resolution is a manager action only.
- **Audit logging** — escalation actions will be logged by the later audit-log feature; **not implemented here** (named as a future integration/dependency).
- **Notifications / paging / email alerts to managers** — out of scope (the queue is the surface); a future enhancement.
- **SLA timers / auto-escalation on timeout** — out of scope for MVP.
- **Cross-tenant or shared escalations** — explicitly forbidden.
- **Full CRM / case management** — out of scope.
- **Real WhatsApp API, calendar syncing** — out of scope entirely.

---

## Assumptions

- An escalation links to exactly one message (`message_id`) and belongs to one tenant.
- Captured context (`intent_label`, `risk_level`, `risk_reason`, `ai_summary`, `source_document_ids`, `source_chunk_ids`, `suggested_reply_id`) is a **snapshot** at creation; later upstream changes do not mutate the escalation record.
- `assigned_manager_id` must be a user with the `manager` role in the same tenant; escalations may be created unassigned and assigned later by a manager.
- Priority defaults from the risk level when omitted (high/urgent for high risk; medium otherwise), staff-overridable.
- The related message's status may be set to `escalated` on creation (non-destructive, isolated; does not block other features).
- Terminal statuses (`resolved`, `cancelled`) are immutable for fields; reopening is out of scope for MVP.
- The detail page's "Escalate" placeholder from Spec 005 is replaced by the real escalation control + recommendation; if a "Create Task" control (Spec 011) exists, both are independent.
- Audit logging is a future integration; this feature records actor + action + timestamps for that feature to consume but does not implement logging.
- The AI summary is optional convenience; escalation creation never depends on it.

---

## Advanced Requirements Update (Updated Brief — 2026-06): Risky-Case Agent

The updated brief introduces a **focused, bounded risky-case agent** that assists staff on high-risk messages by orchestrating existing tenant-scoped tools. The agent lives at the convergence of risk (007) → RAG (009) → reply (010) → task (011) → escalation (012), which is why it is specified here. It is **assistive, bounded, and non-autonomous**: it proposes actions and a human confirms. It is explicitly **not** a general or large multi-agent system.

### Scope

- The agent runs **only on risky cases** (Spec 007 `risk_level = high` or `escalation_recommended = true`), never on routine low-risk messages.
- The agent has **exactly four tools**, all tenant-scoped and reusing existing services:
  - `rag_search` — tenant-scoped retrieval (Spec 009).
  - `suggest_reply` — draft a grounded reply (Spec 010); never auto-sent.
  - `create_follow_up_task` — propose a follow-up task (Spec 011).
  - `escalate_to_manager` — create an escalation (this spec, staff-confirmed).
- **Bounded tool calls**: a hard maximum number of tool invocations per run (`AGENT_MAX_TOOL_CALLS`, small default e.g. 5); exceeding it stops the agent and falls back to human review.

### Functional Requirements (additional)

- **FR-017**: The agent MUST operate only on risky cases and MUST be invoked explicitly (a staff action or the risky-case path), never as a blocking step in message creation.
- **FR-018**: The agent MUST be limited to the four tools above; it MUST NOT call any other service, send a client message, or act outside the tenant boundary.
- **FR-019**: Tool calls MUST be **bounded** by `AGENT_MAX_TOOL_CALLS`; on reaching the bound, on tool error, or on low confidence, the agent MUST **fall back to human review** — surface its partial findings and create nothing without confirmation.
- **FR-020**: `suggest_reply` output MUST pass Spec 014 guardrails (grounding/safety) before display and MUST remain human-approved (never auto-sent); `create_follow_up_task` and `escalate_to_manager` MUST require human confirmation in the MVP default (no autonomous create).
- **FR-021**: **Every agent action** (each tool call — inputs summary, tool, outcome — plus the final recommendation) MUST be **logged** (Spec 013 audit log + an agent-run record), tenant-scoped and redacted (no secrets/PII/cross-tenant data).
- **FR-022**: The agent's guardrails MUST be **inescapable**: it cannot bypass the tenant filter, cannot exceed the call bound, and cannot perform an action a human role could not perform directly.

### Acceptance Criteria (additional)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-19 | Agent runs only on high-risk / escalation-recommended cases; skipped for low-risk | Integration test |
| AC-20 | Agent is limited to the four tools; no other side effects occur | Code/integration test |
| AC-21 | Tool calls are bounded; exceeding the bound triggers human-review fallback (no autonomous create) | Integration test: force > max calls → fallback |
| AC-22 | Every tool call + final recommendation is logged (audit + agent-run), tenant-scoped and redacted | Integration test: assert log entries |
| AC-23 | Agent-suggested reply is guardrail-checked and human-approved; task/escalation require confirmation | Integration test |
| AC-24 | Agent cannot cross the tenant boundary via any tool (`rag_search`/`escalate`/`task`) | Integration test (cross-tenant attempt) |

> The agent is the "agent/tool workflow" subject already evaluated by Spec 015 (`agent_workflow` area) and gated by Spec 014 guardrails + logged via Spec 013 audit. It could graduate to its own spec later; for the MVP it is a bounded assist layer over Specs 009–012. **Config**: `AGENT_ENABLED`, `AGENT_MAX_TOOL_CALLS`, `AGENT_REQUIRE_HUMAN_CONFIRM` (default true).
