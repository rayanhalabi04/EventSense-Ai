# API Contracts: Risk Detection

**Branch**: `007-risk-detection` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT; requires `staff` or `manager` role. Platform Admin → 403. `tenant_id` is always derived from the JWT; any client-supplied tenant is ignored. Every endpoint resolves the message's tenant first (404 if the message does not exist in the system; 403 if it exists in another tenant — consistent with Specs 005/006 SR-04).

---

## 1. POST /api/messages/{message_id}/risk-assessment

Re-run the rule engine for one message and return the result. Used for retries and manual re-assessment after rule changes. The automatic path runs after intent classification; this endpoint is the explicit trigger. Requires an existing classification.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message to assess. 422 if not a valid UUID. |

**Request body** (optional):
```json
{
  "force": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | boolean | `false` | When `true`, overwrite even a `reviewed` assessment. When `false`, a `reviewed` result is preserved and returned unchanged. |

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- Message must resolve in the caller's tenant → 404 / 403.
- Message must be `inbound`; assessing an `outbound` message → 409 `NOT_CLASSIFIABLE`.
- Message must already have a classification → 409 `NOT_CLASSIFIED` otherwise.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000003",
  "level": "high",
  "flag": "cancellation_risk",
  "reason": "Cancellation intent with deposit/refund mention.",
  "escalation_recommended": true,
  "rules_version": "rules-v1",
  "status": "assessed",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Low-risk response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000001",
  "level": "low",
  "flag": null,
  "reason": "Routine pricing request.",
  "escalation_recommended": false,
  "rules_version": "rules-v1",
  "status": "assessed",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 409 | Message is outbound | `NOT_CLASSIFIABLE` |
| 409 | Message has no classification yet | `NOT_CLASSIFIED` |
| 422 | `message_id` not a UUID / malformed body | validation detail |

---

## 2. GET /api/messages/{message_id}/risk-assessment

Read the stored risk assessment for a message.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message whose assessment is requested. |

**Request body**: none.

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- Message must resolve in the caller's tenant → 404 / 403.
- Assessment must exist → 404 `NO_RISK_ASSESSMENT` otherwise.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000005",
  "level": "high",
  "flag": "complaint",
  "reason": "Complaint with urgency: event is next week.",
  "escalation_recommended": true,
  "rules_version": "rules-v1",
  "status": "assessed",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 404 | Message has no assessment yet | `NO_RISK_ASSESSMENT` |
| 422 | `message_id` not a UUID | validation detail |

---

## 3. PATCH /api/messages/{message_id}/risk-assessment/review

Human review: correct or confirm the risk. Sets `status` `reviewed`, recomputes `escalation_recommended` from the corrected level/flag, records reviewer + time.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message whose assessment is being reviewed. |

**Request body** (required):
```json
{
  "level": "high",
  "flag": "complaint",
  "reason": "Confirmed complaint; client is upset about decoration quality."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `level` | string (RiskLevel) | yes | Corrected/confirmed level. One of `low`/`medium`/`high`. |
| `flag` | string (RiskFlag) or null | no | Corrected primary flag, or null. Must be a valid flag if present. |
| `reason` | string | yes | Human-readable reason (1–500 chars). |

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- `level` must be a valid `RiskLevel` → 422 otherwise.
- `flag` if present must be a valid `RiskFlag` → 422 otherwise.
- `reason` length 1–500 → 422 otherwise.
- Message must resolve in the caller's tenant → 404 / 403.
- Assessment must exist → 404 `NO_RISK_ASSESSMENT` otherwise.
- Reviewer is the authenticated `staff`/`manager` user.
- On any validation failure, the stored assessment is unchanged.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000006",
  "level": "high",
  "flag": "complaint",
  "reason": "Confirmed complaint; client is upset about decoration quality.",
  "escalation_recommended": true,
  "rules_version": "rules-v1",
  "status": "reviewed",
  "reviewed_by": "c2000000-0000-0000-0000-000000000045",
  "reviewed_at": "2026-06-06T10:20:00Z",
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:20:00Z"
}
```
Note: `rules_version` retains the engine's original value; `status` is now `reviewed`; `escalation_recommended` is recomputed from the corrected level/flag.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 404 | Message has no assessment | `NO_RISK_ASSESSMENT` |
| 422 | invalid level/flag, or reason length out of range | validation detail |

---

## Embedded Risk in Existing Endpoints

To avoid N+1 fetches, risk is embedded in the inbox and detail responses (read-only summary; the three endpoints above remain authoritative for writes/targeted reads). This sits alongside the Spec 006 `classification` summary.

### Spec 004 — `GET /api/v1/inbox` (extended)

Each inbox item gains:
```json
"risk": {
  "level": "high",
  "flag": "cancellation_risk",
  "reason": "Cancellation intent with deposit/refund mention.",
  "escalation_recommended": true
}
```
`null` when the message is not assessed.

### Spec 005 — `GET /api/v1/conversations/{id}` (extended)

Each message in `messages[]` gains the same `risk` summary object (or `null`). The detail page renders it in the `RiskPanel` (replacing the Spec 005 "Risk / Sentiment" placeholder).

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Auto-assess after classification | (internal) | Creates/updates a RiskAssessment; never fails message/classification |
| `POST /risk-assessment`, classified | 200 | Upsert level/flag/reason/escalation; status=assessed |
| `POST` on reviewed (force=false) | 200 | Reviewed result preserved, returned unchanged |
| `POST` on reviewed (force=true) | 200 | Overwrites with new engine result |
| `POST` not yet classified | 409 | No result; classify first |
| `POST` on outbound | 409 | No result created |
| `GET` existing | 200 | none |
| `GET` none | 404 | none |
| `PATCH review` valid | 200 | level/flag/reason updated, status=reviewed, reviewer recorded |
| `PATCH review` invalid | 422 | none |
| Any endpoint, cross-tenant | 403 | none |
| Any endpoint, non-existent message | 404 | none |
| Any endpoint, Platform Admin | 403 | none |

---

## Non-Goals (contract-level)

These endpoints never: create tasks, create or perform escalations, generate or send replies, or perform document retrieval. `escalation_recommended` is informational metadata only — it triggers nothing in this feature. `human_escalation_needed` is only a returnable **flag**; producing it does not escalate anything. Acting on a recommendation is the separate, human-reviewed escalation feature.
