# API Contracts: Intent Classifier

**Branch**: `006-intent-classifier` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT; requires `staff` or `manager` role. Platform Admin → 403. `tenant_id` is always derived from the JWT; any client-supplied tenant is ignored. Every endpoint resolves the message's tenant first (404 if the message does not exist in the system; 403 if it exists in another tenant — consistent with Spec 005 SR-04).

---

## 1. POST /api/messages/{message_id}/classify

Re-run classification for one message and return the result. Used for retries (e.g., after `MODEL_UNAVAILABLE`) and manual re-classification. The automatic path runs on message creation; this endpoint is the explicit trigger.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message to classify. 422 if not a valid UUID. |

**Request body** (optional):
```json
{
  "force": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | boolean | `false` | When `true`, overwrite even a `reviewed` classification. When `false`, a `reviewed` result is preserved and returned unchanged. |

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- Message must resolve in the caller's tenant → 404 / 403.
- Message must be `inbound`; classifying an `outbound` message → 409 `NOT_CLASSIFIABLE`.
- The model must be available → 503 `MODEL_UNAVAILABLE` otherwise.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000001",
  "label": "pricing_request",
  "confidence": 0.82,
  "model_version": "tfidf-logreg-v1",
  "status": "classified",
  "reviewed_by": null,
  "reviewed_at": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Low-confidence response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000002",
  "label": "other",
  "confidence": 0.31,
  "model_version": "tfidf-logreg-v1",
  "status": "needs_review",
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
| 422 | `message_id` not a UUID / malformed body | validation detail |
| 503 | Model artifact unavailable | `MODEL_UNAVAILABLE` |

---

## 2. GET /api/messages/{message_id}/classification

Read the stored classification for a message.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message whose classification is requested. |

**Request body**: none.

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- Message must resolve in the caller's tenant → 404 / 403.
- Classification must exist → 404 `NO_CLASSIFICATION` otherwise.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000001",
  "label": "complaint",
  "confidence": 0.74,
  "model_version": "tfidf-logreg-v1",
  "status": "classified",
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
| 404 | Message has no classification yet | `NO_CLASSIFICATION` |
| 422 | `message_id` not a UUID | validation detail |

---

## 3. PATCH /api/messages/{message_id}/classification/review

Human review: correct or confirm the label. Marks the classification `reviewed`, records the reviewer and time, and clears the needs-review state.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message whose classification is being reviewed. |

**Request body** (required):
```json
{
  "label": "pricing_request"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | string (IntentLabel) | yes | The corrected/confirmed label. Must be one of the eleven valid labels. |

**Validation rules**:
- `message_id` must be a valid UUID → 422.
- `label` must be one of the eleven `IntentLabel` values → 422 otherwise (stored classification unchanged).
- Message must resolve in the caller's tenant → 404 / 403.
- Classification must exist → 404 `NO_CLASSIFICATION` otherwise.
- Reviewer is the authenticated `staff`/`manager` user.

**Response 200**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000002",
  "label": "pricing_request",
  "confidence": 0.31,
  "model_version": "tfidf-logreg-v1",
  "status": "reviewed",
  "reviewed_by": "c2000000-0000-0000-0000-000000000045",
  "reviewed_at": "2026-06-06T10:15:00Z",
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:15:00Z"
}
```
Note: `confidence` and `model_version` retain the original model's values; `status` is now `reviewed` and the label is the human-chosen one.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Message in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Message does not exist | `MESSAGE_NOT_FOUND` |
| 404 | Message has no classification | `NO_CLASSIFICATION` |
| 422 | `label` missing or not a valid IntentLabel | validation detail |

---

## Embedded Classification in Existing Endpoints

To avoid N+1 fetches, the intent is embedded in the inbox and detail responses (read-only summary; the three endpoints above remain authoritative for writes/targeted reads).

### Spec 004 — `GET /api/v1/inbox` (extended)

Each inbox item gains:
```json
"classification": { "label": "pricing_request", "confidence": 0.82, "status": "classified" }
```
`null` when the message is unclassified.

### Spec 005 — `GET /api/v1/conversations/{id}` (extended)

Each message in `messages[]` gains the same `classification` summary object (or `null`). The detail page renders it in the `IntentPanel` (replacing the Spec 005 "AI Intent" placeholder).

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Auto-classify on inbound creation | (internal) | Creates/updates a ClassificationResult; never fails message creation |
| `POST /classify`, confident | 200 | Upsert label/confidence, status=classified |
| `POST /classify`, low confidence | 200 | label=other, status=needs_review |
| `POST /classify` on reviewed (force=false) | 200 | Reviewed result preserved, returned unchanged |
| `POST /classify` on reviewed (force=true) | 200 | Overwrites with new model result |
| `POST /classify` on outbound | 409 | No result created |
| `POST /classify`, model down | 503 | No result; retry later |
| `GET` existing | 200 | none |
| `GET` none | 404 | none |
| `PATCH review` valid | 200 | label updated, status=reviewed, reviewer recorded |
| `PATCH review` invalid label | 422 | none |
| Any endpoint, cross-tenant | 403 | none |
| Any endpoint, non-existent message | 404 | none |
| Any endpoint, Platform Admin | 403 | none |

---

## Non-Goals (contract-level)

These endpoints never: create tasks, create escalations, generate or send replies, or perform document retrieval. `human_escalation` is only a returnable **label** — selecting/predicting it triggers no escalation in this feature.
