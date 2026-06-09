# API Contracts: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT. **Processing** (`POST .../process`) requires `manager`. **Query + reads** allow `manager` or `staff`. Platform Admin → 403. `tenant_id` is always derived from the JWT; any client-supplied tenant is ignored. Single-resource endpoints resolve the document/message tenant first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–008 SR-05). **Every retrieval is tenant-filtered — there is no cross-tenant search path (SR-02).**

---

## 1. POST /api/documents/{document_id}/process

Chunk + embed + store a document's content, then set its status to `processed` (or `failed`). `manager` only. Idempotent: re-processing replaces existing chunks.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | The Spec 008 document to process. 422 if not a UUID. |

**Request body** (optional):
```json
{ "force": false }
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `force` | boolean | `false` | Reserved; re-processing already replaces chunks. `true` re-processes even if already `processed`. |

**Validation rules**:
- `document_id` valid UUID; document resolves in tenant → 404/403.
- Document must be `enabled` → else 422 `DOCUMENT_DISABLED`.
- Document must have non-empty content (guaranteed by Spec 008).
- Embedding model must be available → else 503 `MODEL_UNAVAILABLE` (document set `failed`).

**Response 200**:
```json
{
  "document_id": "d1000000-0000-0000-0000-000000000001",
  "status": "processed",
  "chunk_count": 3,
  "embedding_model": "local-minilm-v1"
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Document in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Document does not exist | `DOCUMENT_NOT_FOUND` |
| 422 | Document is disabled | `DOCUMENT_DISABLED` |
| 503 | Embedding model unavailable (doc set `failed`) | `MODEL_UNAVAILABLE` |

---

## 2. GET /api/documents/{document_id}/chunks

List the stored chunks for a document in the caller's tenant. `manager` and `staff`. Embedding vectors are **not** returned.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | The document whose chunks to list. |

**Response 200**:
```json
{
  "document_id": "d1000000-0000-0000-0000-000000000001",
  "chunks": [
    {
      "id": "e1000000-0000-0000-0000-000000000001",
      "document_id": "d1000000-0000-0000-0000-000000000001",
      "chunk_index": 0,
      "chunk_text": "A 30% deposit confirms the booking. Deposits are non-refundable within 45 days...",
      "metadata": { "embedding_model": "local-minilm-v1", "char_start": 0, "char_end": 780 },
      "created_at": "2026-06-06T10:05:00Z"
    }
  ],
  "total": 1
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Document in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Document does not exist | `DOCUMENT_NOT_FOUND` |
| 422 | `document_id` not a UUID | validation detail |

---

## 3. POST /api/rag/query

Retrieve the most relevant tenant-scoped sources for a query. `manager` and `staff`. Optionally links the query to a message for detail-page display. **Always filtered by the session tenant.**

**Request body**:
```json
{
  "query": "Is the deposit refundable if I cancel?",
  "message_id": "b1000000-0000-0000-0000-000000000003",
  "top_k": 4,
  "threshold": 0.25
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Non-empty, ≤ 2000 chars (client message or free text) |
| `message_id` | UUID | no | Message to link results to (must be in tenant if provided) |
| `top_k` | integer | no | 1–20; default `4` |
| `threshold` | number | no | 0.0–1.0; default from config (`0.25`) |

**Validation rules**:
- `query` non-empty after strip → 422 otherwise.
- `top_k` in 1–20; `threshold` in 0.0–1.0 → 422 otherwise.
- `message_id` if present must resolve in the caller's tenant → 404/403.

**Response 200 — grounded**:
```json
{
  "status": "grounded",
  "query_id": "f1000000-0000-0000-0000-000000000001",
  "embedding_model": "local-minilm-v1",
  "sources": [
    {
      "document_id": "d1000000-0000-0000-0000-000000000001",
      "document_title": "Deposit Policy",
      "document_type": "deposit_policy",
      "chunk_id": "e1000000-0000-0000-0000-000000000001",
      "snippet": "Deposits are non-refundable within 45 days of the event...",
      "score": 0.81,
      "rank": 1
    },
    {
      "document_id": "d1000000-0000-0000-0000-000000000003",
      "document_title": "Cancellation Policy",
      "document_type": "cancellation_policy",
      "chunk_id": "e1000000-0000-0000-0000-000000000020",
      "snippet": "Cancellations 90+ days before the event receive a 50% refund...",
      "score": 0.67,
      "rank": 2
    }
  ]
}
```

**Response 200 — no relevant source (refuse path)**:
```json
{
  "status": "no_source",
  "query_id": "f1000000-0000-0000-0000-000000000002",
  "embedding_model": "local-minilm-v1",
  "sources": []
}
```

**Response 200 — tenant has no documents**:
```json
{
  "status": "no_documents",
  "query_id": "f1000000-0000-0000-0000-000000000003",
  "embedding_model": "local-minilm-v1",
  "sources": []
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | `message_id` in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | `message_id` does not exist | `MESSAGE_NOT_FOUND` |
| 422 | Empty query / bad top_k / bad threshold | validation detail |
| 503 | Embedding model unavailable | `MODEL_UNAVAILABLE` (or 200 `status:failed` if persisted) |

> Note: `no_source` and `no_documents` are **200 OK** outcomes (the refuse path is a normal result, not an error). The downstream reply feature must treat them as "do not answer from documents".

---

## 4. GET /api/messages/{message_id}/rag-results

Fetch the stored RAG results for a message in the caller's tenant. `manager` and `staff`. Powers the detail-page Knowledge Sources panel.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `message_id` | UUID | The message whose RAG results to fetch. |

**Response 200 — results exist**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000003",
  "status": "grounded",
  "query_id": "f1000000-0000-0000-0000-000000000001",
  "created_at": "2026-06-06T10:06:00Z",
  "sources": [
    {
      "document_id": "d1000000-0000-0000-0000-000000000001",
      "document_title": "Deposit Policy",
      "document_type": "deposit_policy",
      "chunk_id": "e1000000-0000-0000-0000-000000000001",
      "snippet": "Deposits are non-refundable within 45 days of the event...",
      "score": 0.81,
      "rank": 1
    }
  ]
}
```

**Response 200 — never retrieved**:
```json
{
  "message_id": "b1000000-0000-0000-0000-000000000003",
  "status": "no_source",
  "query_id": null,
  "created_at": null,
  "sources": []
}
```
(The frontend renders `query_id: null` as a "not retrieved yet" state.)

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
| Manager processes a document | 200 | Chunks replaced; doc status `processed` |
| Staff processes a document | 403 | none |
| Process disabled document | 422 | none |
| Process, model unavailable | 503 | doc status `failed`; no chunks |
| Query with matches | 200 `grounded` | RagQuery + results persisted |
| Query, no match | 200 `no_source` | RagQuery persisted, no results |
| Query, empty corpus | 200 `no_documents` | RagQuery persisted |
| Query with `message_id` | 200 | results linked to message |
| Query cross-tenant message_id | 403/404 | none |
| Get chunks / rag-results cross-tenant | 403/404 | none |
| Any endpoint, Platform Admin | 403 | none |

---

## Role Matrix

| Endpoint | manager | staff | platform_admin |
|----------|---------|-------|----------------|
| POST /api/documents/{id}/process | ✅ | ❌ 403 | ❌ 403 |
| GET /api/documents/{id}/chunks | ✅ | ✅ | ❌ 403 |
| POST /api/rag/query | ✅ | ✅ | ❌ 403 |
| GET /api/messages/{id}/rag-results | ✅ | ✅ | ❌ 403 |

---

## Tenant Isolation Guarantees (contract-level)

- Every chunk search applies `WHERE tenant_id = :jwt_tenant AND documents.enabled AND documents.status='processed'`. There is no endpoint or parameter that searches across tenants (SR-02, SR-08).
- A supplied `message_id`/`document_id` from another tenant yields 404/403 and never contributes candidates.
- Chunks and results carry `tenant_id`; results for a message are filtered by the message's tenant.

---

## Non-Goals (contract-level)

These endpoints never: generate a suggested reply, synthesise/summarise sources into an answer, send anything, or retrieve across tenants. The output is ranked evidence + a status. `no_source`/`no_documents` are the mandated refuse outcomes the future suggested-reply feature must honour. Advancing/owning suggested replies is a later feature.
