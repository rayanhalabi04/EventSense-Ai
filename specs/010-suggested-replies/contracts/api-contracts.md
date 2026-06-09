# API Contracts: Suggested Replies

**Branch**: `010-suggested-replies` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT; requires `staff` or `manager`. Platform Admin → 403. `tenant_id` and `approved_by` are always derived from the JWT; any client-supplied tenant is ignored. Every endpoint resolves the message/reply tenant first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–009). **No endpoint sends a reply, creates a task, or creates an escalation.**

---

## 1. POST /api/messages/{message_id}/suggested-replies

Generate a new draft reply for a message. Requires upstream intent (006), risk (007), and a RAG retrieval (009).

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | Message to draft a reply for. 422 if not a UUID. |

**Request body** (optional):
```json
{ "force": false }
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | boolean | `false` | Create a new draft even if drafts already exist (regeneration). Never overwrites an `approved` reply. |

**Validation / preconditions**:
- `message_id` valid UUID; message resolves in tenant → 404/403.
- Message body non-empty → else 422.
- Message has intent + risk + a RAG retrieval → else 409 `PRECONDITION_NOT_MET`.
- Generation model available → else 503 `MODEL_UNAVAILABLE` (no draft stored).

**Response 201 — grounded draft**:
```json
{
  "id": "a9000000-0000-0000-0000-000000000001",
  "message_id": "b1000000-0000-0000-0000-000000000010",
  "generated_text": "Thank you for your interest! Our Premium Wedding Package includes full-day coordination for up to 200 guests... (per our Premium Wedding Package document).",
  "edited_text": null,
  "effective_text": "Thank you for your interest! Our Premium Wedding Package includes...",
  "status": "draft_generated",
  "grounded": true,
  "sources": [
    {
      "document_id": "d1000000-0000-0000-0000-000000000001",
      "document_title": "Premium Wedding Package",
      "document_type": "wedding_packages",
      "chunk_id": "e1000000-0000-0000-0000-000000000001",
      "snippet": "Premium package: full-day coordination, 200 guests, premium florals..."
    }
  ],
  "model_name": "gpt-style-v1",
  "prompt_version": "reply-prompt-v1",
  "approved_by": null,
  "approved_at": null,
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Response 201 — refusal draft (no supporting source)**:
```json
{
  "id": "a9000000-0000-0000-0000-000000000002",
  "message_id": "b1000000-0000-0000-0000-000000000011",
  "generated_text": "Thank you for reaching out. That service isn't covered in our current documents, so I'd like to confirm the details with our team before giving you an exact answer. A member of our team will follow up shortly.",
  "edited_text": null,
  "effective_text": "Thank you for reaching out. That service isn't covered in our current documents...",
  "status": "draft_generated",
  "grounded": false,
  "sources": [],
  "model_name": "gpt-style-v1",
  "prompt_version": "reply-prompt-v1",
  "approved_by": null,
  "approved_at": null,
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
| 409 | Missing intent/risk/RAG | `PRECONDITION_NOT_MET` |
| 422 | Empty message body / bad UUID | validation detail |
| 503 | Generation model unavailable | `MODEL_UNAVAILABLE` |

---

## 2. GET /api/messages/{message_id}/suggested-replies

List the draft replies for a message (newest first). `staff`/`manager`.

**Response 200**:
```json
{
  "items": [ { "...": "SuggestedReplyResponse (see POST)" } ],
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

## 3. GET /api/suggested-replies/{reply_id}

Fetch a single suggested reply. `staff`/`manager`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `reply_id` | UUID | The reply to fetch. |

**Response 200**: a `SuggestedReplyResponse` (see POST).

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Reply in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Reply does not exist | `REPLY_NOT_FOUND` |
| 422 | `reply_id` not a UUID | validation detail |

---

## 4. PATCH /api/suggested-replies/{reply_id}

Edit a reply's text. `staff`/`manager`. Allowed only when status is `draft_generated` or `edited`.

**Request body**:
```json
{ "edited_text": "Thank you for your interest! Our Premium package starts at £4,500 and includes..." }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `edited_text` | string | yes | New reply text (1–4000 chars, non-blank) |

**Validation rules**:
- `reply_id` valid UUID; reply resolves in tenant → 404/403.
- `edited_text` non-empty after strip → 422 `EMPTY_REPLY_TEXT`.
- Status must be non-terminal → else 422 `INVALID_STATE_TRANSITION`.

**Response 200**: updated `SuggestedReplyResponse` with `edited_text` set, `generated_text` unchanged, `status` `edited`, `effective_text` = the edit.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Reply in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Reply does not exist | `REPLY_NOT_FOUND` |
| 422 | Empty text | `EMPTY_REPLY_TEXT` |
| 422 | Reply is `approved`/`rejected` | `INVALID_STATE_TRANSITION` |

---

## 5. POST /api/suggested-replies/{reply_id}/approve

Approve a reply (human-accept). `staff`/`manager`. **Does not send anything.** Allowed only when non-terminal.

**Request body**: none.

**Validation rules**:
- `reply_id` valid UUID; reply resolves in tenant → 404/403.
- Status must be `draft_generated` or `edited` → else 422 `INVALID_STATE_TRANSITION`.

**Response 200**: `SuggestedReplyResponse` with `status` `approved`, `approved_by` = caller, `approved_at` set.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Reply in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Reply does not exist | `REPLY_NOT_FOUND` |
| 422 | Already `approved`/`rejected` | `INVALID_STATE_TRANSITION` |

---

## 6. POST /api/suggested-replies/{reply_id}/reject

Reject a reply. `staff`/`manager`. Allowed only when non-terminal.

**Request body** (optional):
```json
{ "reason": "Tone too casual; will rewrite." }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reason` | string | no | Optional free-text note (not used for any action) |

**Validation rules**:
- `reply_id` valid UUID; reply resolves in tenant → 404/403.
- Status must be non-terminal → else 422 `INVALID_STATE_TRANSITION`.

**Response 200**: `SuggestedReplyResponse` with `status` `rejected`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Reply in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Reply does not exist | `REPLY_NOT_FOUND` |
| 422 | Already `approved`/`rejected` | `INVALID_STATE_TRANSITION` |

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Generate, grounded | 201 | New `draft_generated` reply with sources |
| Generate, no source (policy question) | 201 | Refusal draft, empty sources, `grounded=false` |
| Generate, missing upstream | 409 | none |
| Generate, model down | 503 | none (no malformed draft) |
| Generate again | 201 | New row; prior `approved` untouched |
| Edit non-terminal | 200 | `edited_text` set, status `edited` |
| Edit terminal | 422 | none |
| Approve non-terminal | 200 | status `approved`, reviewer recorded, **no send** |
| Approve/reject terminal | 422 | none |
| Reject non-terminal | 200 | status `rejected` |
| Any endpoint, cross-tenant | 403 | none |
| Any endpoint, non-existent | 404 | none |
| Any endpoint, Platform Admin | 403 | none |

---

## Role Matrix

| Endpoint | staff | manager | platform_admin |
|----------|-------|---------|----------------|
| POST /messages/{id}/suggested-replies | ✅ | ✅ | ❌ 403 |
| GET /messages/{id}/suggested-replies | ✅ | ✅ | ❌ 403 |
| GET /suggested-replies/{id} | ✅ | ✅ | ❌ 403 |
| PATCH /suggested-replies/{id} | ✅ | ✅ | ❌ 403 |
| POST /suggested-replies/{id}/approve | ✅ | ✅ | ❌ 403 |
| POST /suggested-replies/{id}/reject | ✅ | ✅ | ❌ 403 |

---

## Grounding & Isolation Guarantees (contract-level)

- A grounded draft's `source_document_ids`/`source_chunk_ids` are a subset of the message's tenant RAG retrieval (GR-05); cross-tenant sources never appear (GR-03, SR-03).
- A policy/package question with RAG `no_source`/`no_documents` yields a refusal draft (empty sources, `grounded=false`) — never an invented answer (GR-02, FR-004).
- All replies are tenant-scoped via the message; cross-tenant access → 404/403.

---

## Non-Goals (contract-level)

These endpoints never: send a reply (no transport of any kind), create a task, create or perform an escalation, run intent/risk/RAG themselves beyond consuming results (a RAG query may be triggered for grounding), or auto-approve/auto-regenerate. `approved` is human-acceptance only. Sending, tasks, and escalation are separate, later features.
