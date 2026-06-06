# API Contracts: Escalation to Manager

**Branch**: `012-escalation-to-manager` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT. **Create + view** allow `staff` or `manager`. **Resolve / update / assign / notes** require `manager`. Platform Admin → 403. `tenant_id` and `created_by` are always derived from the JWT; any client-supplied tenant is ignored. Every endpoint resolves the escalation/message tenant first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–011). Referenced `message_id`, `suggested_reply_id`, and `assigned_manager_id` must resolve within the caller's tenant (assignee must be a `manager`). **No endpoint sends a client message, approves/sends the suggested reply, or creates a task.**

---

## 1. POST /api/escalations

Create an escalation from a message. `staff`/`manager` (staff-confirmed; never auto-created). Captures the context snapshot.

**Request body**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "priority": "high",
  "reason": "Client is upset and the event is next week; needs manager judgment.",
  "assigned_manager_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message_id` | UUID | yes | The escalated message (must be in tenant) |
| `priority` | string (EscalationPriority) | no | `medium`/`high`/`urgent`; defaulted from risk if omitted |
| `reason` | string | no | Optional staff context note |
| `assigned_manager_id` | UUID | no | An in-tenant **manager**; omit for unassigned |

**Validation rules**:
- `message_id` resolves in tenant → 404/403.
- `priority` ∈ `EscalationPriority` (if provided) → 422.
- `assigned_manager_id` (if set) is an in-tenant **manager** → 422 `INVALID_ASSIGNEE`.

**Response 201**:
```json
{
  "id": "e5000000-0000-0000-0000-000000000001",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "created_by": "c2000000-0000-0000-0000-000000000045",
  "assigned_manager_id": null,
  "intent_label": "complaint",
  "risk_level": "high",
  "risk_reason": "Complaint with urgency: event is next week.",
  "ai_summary": "Client unhappy with decoration sample; wedding next week. Grounded in no specific policy; needs manager outreach.",
  "suggested_reply_id": "a9000000-0000-0000-0000-000000000005",
  "source_document_ids": [],
  "source_chunk_ids": [],
  "status": "open",
  "priority": "high",
  "manager_notes": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z",
  "resolved_at": null
}
```
Side effect: the related message's status may become `escalated`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 422 | Invalid priority | validation detail |
| 422 | Assignee not an in-tenant manager | `INVALID_ASSIGNEE` |

---

## 2. GET /api/escalations

Queue: list escalations in the caller's tenant. `staff`/`manager` (managers are the primary users; staff may view). Ordered urgent/open first.

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string (EscalationStatus) | — | Filter by status |
| `priority` | string (EscalationPriority) | — | Filter by priority |
| `assigned_manager_id` | UUID | — | Filter by assigned manager |

**Response 200**:
```json
{
  "items": [
    {
      "id": "e5000000-0000-0000-0000-000000000001",
      "message_id": "b1000000-0000-0000-0000-000000000020",
      "status": "open",
      "priority": "high",
      "intent_label": "complaint",
      "risk_level": "high",
      "assigned_manager_id": null,
      "created_by": "c2000000-0000-0000-0000-000000000045",
      "created_at": "2026-06-06T10:00:00Z",
      "updated_at": "2026-06-06T10:00:00Z",
      "resolved_at": null
    }
  ],
  "total": 1
}
```
Note: queue items are a metadata summary; fetch a single escalation for the full captured context.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 422 | Invalid filter value | validation detail |

---

## 3. GET /api/escalations/{escalation_id}

Fetch a single escalation with full captured context. `staff`/`manager`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `escalation_id` | UUID | The escalation to fetch. |

**Response 200**: full `EscalationResponse` (all fields incl. `risk_reason`, `ai_summary`, `suggested_reply_id`, source ids, `manager_notes`).

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Escalation in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Escalation does not exist | `ESCALATION_NOT_FOUND` |
| 422 | `escalation_id` not a UUID | validation detail |

---

## 4. PATCH /api/escalations/{escalation_id}

Update an escalation (status transition, priority, assignee, manager notes). **`manager` only.** Allowed only on non-terminal escalations.

**Request body** (all optional):
```json
{
  "status": "in_review",
  "priority": "urgent",
  "assigned_manager_id": "c2000000-0000-0000-0000-000000000099",
  "manager_notes": "Reviewing now; will call the client."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string (EscalationStatus) | Transition (`open`/`in_review`/`resolved`/`cancelled`) |
| `priority` | string (EscalationPriority) | New priority |
| `assigned_manager_id` | UUID | Assign/reassign to an in-tenant manager |
| `manager_notes` | string | Review notes (≤ 4000) |

**Validation rules**:
- Caller must be `manager` → else 403 `INSUFFICIENT_ROLE`.
- `escalation_id` valid UUID; escalation resolves in tenant → 404/403.
- Non-terminal → else 422 `INVALID_STATE_TRANSITION`; `status` transition must be allowed.
- `assigned_manager_id` (if set) is an in-tenant manager → 422 `INVALID_ASSIGNEE`.
- Setting `status=resolved` sets `resolved_at`.

**Response 200**: updated `EscalationResponse` with refreshed `updated_at`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Caller is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Escalation in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Escalation does not exist | `ESCALATION_NOT_FOUND` |
| 422 | Invalid field / illegal transition / terminal | `INVALID_STATE_TRANSITION` / validation detail |
| 422 | Assignee not an in-tenant manager | `INVALID_ASSIGNEE` |

---

## 5. POST /api/escalations/{escalation_id}/resolve

Resolve an escalation. **`manager` only.** Allowed only on non-terminal escalations. Sets `resolved_at`. (Cancelling is done via `PATCH {"status":"cancelled"}`.)

**Request body** (optional):
```json
{ "manager_notes": "Called the client, arranged a redo of the decoration; closing." }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `manager_notes` | string | no | Final review notes (≤ 4000) |

**Validation rules**:
- Caller must be `manager` → else 403.
- `escalation_id` valid UUID; resolves in tenant → 404/403.
- Non-terminal → else 422 `INVALID_STATE_TRANSITION`.

**Response 200**: `EscalationResponse` with `status` `resolved`, `resolved_at` set, notes stored.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Caller is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Escalation in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Escalation does not exist | `ESCALATION_NOT_FOUND` |
| 422 | Already `resolved`/`cancelled` | `INVALID_STATE_TRANSITION` |

---

## 6. GET /api/messages/{message_id}/escalations

List the escalations raised for a specific message, tenant-scoped. `staff`/`manager`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The source message. |

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000020",
  "items": [ { "...": "EscalationListItem" } ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 422 | `message_id` not a UUID | validation detail |

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Staff creates escalation | 201 | Stored `open` + context snapshot; related message may become `escalated` |
| Create with cross-tenant message/assignee | 404/403/422 | none |
| List queue / get | 200 | none (tenant-scoped) |
| Manager update (status/priority/assignee/notes) | 200 | `updated_at` refreshed |
| Staff attempts update/resolve | 403 | none |
| Manager → in_review | 200 | status change |
| Manager resolve | 200 | status `resolved`, `resolved_at` set |
| Cancel (PATCH status) | 200 | status `cancelled` |
| Edit/resolve/cancel a terminal escalation | 422 | none |
| Message escalations list | 200 | none |
| Any endpoint, Platform Admin | 403 | none |
| Escalation creation | (always) | **no client message; no reply approval/send; no task created** |

---

## Role Matrix

| Endpoint | staff | manager | platform_admin |
|----------|-------|---------|----------------|
| POST /api/escalations | ✅ | ✅ | ❌ 403 |
| GET /api/escalations | ✅ | ✅ | ❌ 403 |
| GET /api/escalations/{id} | ✅ | ✅ | ❌ 403 |
| PATCH /api/escalations/{id} | ❌ 403 | ✅ | ❌ 403 |
| POST /api/escalations/{id}/resolve | ❌ 403 | ✅ | ❌ 403 |
| GET /api/messages/{id}/escalations | ✅ | ✅ | ❌ 403 |

---

## Non-Goals (contract-level)

These endpoints never: send a client message, approve or send the AI suggested reply (Spec 010 lifecycle is independent), create a follow-up task (Spec 011), auto-create an escalation (staff confirmation required), auto-resolve an escalation (manager action only), or write audit logs. Audit logging of escalation actions is a **future integration** (separate audit-log feature). `escalated` on the message is the only side effect, and it is non-destructive.
