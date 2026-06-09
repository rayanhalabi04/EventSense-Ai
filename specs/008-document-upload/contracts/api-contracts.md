# API Contracts: Document Upload

**Branch**: `008-document-upload` | **Phase**: 1 — Design

**Auth (all endpoints)**: Bearer JWT. **Writes** (`POST`/`PATCH`/`DELETE`) require `manager`. **Reads** (`GET`) allow `manager` or `staff`. Platform Admin → 403. `tenant_id` and `created_by` are always derived from the JWT; any client-supplied tenant is ignored. Single-document endpoints resolve the document first (404 if it does not exist; 403 if it exists in another tenant — consistent with Specs 005–007 SR-04).

---

## 1. POST /api/documents

Create a document for the caller's tenant. Two content paths:
- **JSON** (`application/json`): pasted text content.
- **Multipart** (`multipart/form-data`): file upload (`.txt`/`.md`, optionally `.pdf`) — text extracted server-side.

**JSON request body**:
```json
{
  "title": "Deposit Policy",
  "document_type": "deposit_policy",
  "content": "A 25% deposit is required to confirm a booking. Deposits are non-refundable within 30 days of the event."
}
```

**Multipart fields**:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title (1–200 chars) |
| `document_type` | string (DocumentType) | One of the ten types |
| `file` | file | `.txt`/`.md` (and `.pdf` if enabled); validated for MIME + size |

**Validation rules**:
- `title` non-empty, ≤ 200 chars → 422 otherwise.
- `document_type` ∈ `DocumentType` → 422 otherwise.
- Exactly one content source: `content` (JSON) **or** `file` (multipart). Missing/both-empty → 422.
- `content` non-empty, ≤ `DOC_MAX_CONTENT_BYTES` → 422 otherwise.
- File: MIME/extension in allowlist (→ 422 `UNSUPPORTED_FILE_TYPE`), size ≤ `DOC_MAX_FILE_BYTES` (→ 422 `FILE_TOO_LARGE`), non-empty extracted text (→ 422 `EMPTY_DOCUMENT_CONTENT`).

**Response 201**:
```json
{
  "id": "d1000000-0000-0000-0000-000000000001",
  "title": "Deposit Policy",
  "document_type": "deposit_policy",
  "status": "uploaded",
  "enabled": true,
  "content": "A 25% deposit is required to confirm a booking...",
  "source_filename": null,
  "source_mime": null,
  "content_bytes": 102,
  "created_by": "c2000000-0000-0000-0000-000000000045",
  "created_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T10:00:00Z"
}
```

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 422 | Invalid title/type/content | validation detail |
| 422 | Unsupported file type | `UNSUPPORTED_FILE_TYPE` |
| 422 | File too large | `FILE_TOO_LARGE` |
| 422 | Empty/extracted-empty content | `EMPTY_DOCUMENT_CONTENT` |

---

## 2. GET /api/documents

List documents in the caller's tenant. Read-only; `manager` and `staff`.

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `document_type` | string (DocumentType) | — | Filter by type |
| `status` | string (DocumentStatus) | — | Filter by status |
| `enabled` | boolean | — | Filter by enabled flag |

**Response 200**:
```json
{
  "items": [
    {
      "id": "d1000000-0000-0000-0000-000000000001",
      "title": "Deposit Policy",
      "document_type": "deposit_policy",
      "status": "uploaded",
      "enabled": true,
      "created_by": "c2000000-0000-0000-0000-000000000045",
      "created_at": "2026-06-06T10:00:00Z",
      "updated_at": "2026-06-06T10:00:00Z"
    }
  ],
  "total": 1
}
```
Note: list items are **metadata only** (no `content`) to keep the payload light; fetch a single document for content.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 422 | Invalid filter value | validation detail |

---

## 3. GET /api/documents/{document_id}

Fetch a single document (metadata + content) in the caller's tenant. `manager` and `staff`.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | The document to fetch. 422 if not a UUID. |

**Response 200**: same shape as the `POST` 201 response (full `DocumentResponse` with `content`).

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Platform Admin | `INSUFFICIENT_ROLE` |
| 403 | Document in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Document does not exist | `DOCUMENT_NOT_FOUND` |
| 422 | `document_id` not a UUID | validation detail |

---

## 4. PATCH /api/documents/{document_id}

Update a document. `manager` only. Any subset of fields may be provided.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | The document to update. |

**Request body** (all optional):
```json
{
  "title": "Deposit Policy (2026)",
  "document_type": "deposit_policy",
  "content": "Updated deposit terms...",
  "enabled": true,
  "status": "processing_pending"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | New title (1–200) |
| `document_type` | string (DocumentType) | New type |
| `content` | string | New content (non-empty, ≤ limit). **Changing content resets `status` to `uploaded`.** |
| `enabled` | boolean | Enable/disable (exclude from future RAG processing) |
| `status` | string | Manager may set `processing_pending` (or `uploaded`). Setting `processed`/`failed` → 422 (owned by RAG feature). |

**Validation rules**:
- `document_id` valid UUID; document resolves in tenant → 404/403.
- Provided fields validated (title length, type enum, content non-empty/size).
- `status` may only be set to `uploaded` or `processing_pending` here → else 422 `STATUS_NOT_SETTABLE`.
- If `content` is changed, `status` is forced to `uploaded` (overrides a conflicting `status` field).

**Response 200**: full `DocumentResponse` reflecting the changes and refreshed `updated_at`.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Document in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Document does not exist | `DOCUMENT_NOT_FOUND` |
| 422 | Invalid field value | validation detail |
| 422 | Attempt to set `processed`/`failed` | `STATUS_NOT_SETTABLE` |

---

## 5. DELETE /api/documents/{document_id}

Permanently delete a document and its content. `manager` only.

**Path parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `document_id` | UUID | The document to delete. |

**Response 204**: no body.

**Error cases**:

| Status | Condition | error_code |
|--------|-----------|-----------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | Role is `staff` or `platform_admin` | `INSUFFICIENT_ROLE` |
| 403 | Document in another tenant | `CROSS_TENANT_FORBIDDEN` |
| 404 | Document does not exist | `DOCUMENT_NOT_FOUND` |
| 422 | `document_id` not a UUID | validation detail |

---

## Cross-Cutting Behaviour

| Scenario | HTTP | Side effect |
|----------|------|-------------|
| Manager creates (JSON) | 201 | Document stored, status `uploaded` |
| Manager creates (file) | 201 | File validated + text extracted + stored |
| Staff creates / updates / deletes | 403 | none |
| Manager lists | 200 | none (tenant-scoped) |
| Staff lists / gets | 200 | none (read-only) |
| Get/Patch/Delete cross-tenant | 403 | none |
| Get/Patch/Delete non-existent | 404 | none |
| Patch content | 200 | content updated, status reset to `uploaded` |
| Patch enabled=false | 200 | excluded from future RAG; still listed |
| Patch status=processing_pending | 200 | handed to future RAG pipeline |
| Patch status=processed/failed | 422 | none (RAG-owned) |
| Delete | 204 | document + content removed |
| Any endpoint, Platform Admin | 403 | none |

---

## Role Matrix

| Endpoint | manager | staff | platform_admin |
|----------|---------|-------|----------------|
| POST /api/documents | ✅ | ❌ 403 | ❌ 403 |
| GET /api/documents | ✅ | ✅ | ❌ 403 |
| GET /api/documents/{id} | ✅ | ✅ | ❌ 403 |
| PATCH /api/documents/{id} | ✅ | ❌ 403 | ❌ 403 |
| DELETE /api/documents/{id} | ✅ | ❌ 403 | ❌ 403 |

---

## Non-Goals (contract-level)

These endpoints never: chunk content, generate embeddings, write to pgvector, perform retrieval/semantic search, or generate replies. The only RAG-facing seams are the `status` field (`processing_pending`) and the `enabled` flag. Advancing status to `processed`/`failed` is owned by the future RAG feature, not these endpoints.
