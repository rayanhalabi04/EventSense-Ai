# Feature Specification: Document Upload

**Feature Branch**: `008-document-upload`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)

**Input**: User description: "Managers should be able to upload or add tenant-specific business documents that will later be used by the RAG system. Each document must belong to exactly one tenant and must never be visible or retrievable by another tenant."

---

## Goal

Let managers add and manage their agency's business documents (pricing, packages, policies, FAQs, rules) so that a later RAG feature can retrieve them to ground AI suggested replies. Every document belongs to exactly one tenant and is never visible or retrievable across tenants. This feature owns document **content + metadata + lifecycle status** — it stores text-based documents (plain text / markdown, optionally simple PDF), validates them, and tracks a processing status (`uploaded → processing_pending → processed → failed`) that the future RAG pipeline will advance. It explicitly does **not** chunk, embed, or retrieve — it only prepares and curates the document corpus that RAG will later consume.

---

## Document Types

A document is one of these types:

| Type | Meaning |
|------|---------|
| `pricing_packages` | Price lists / package pricing |
| `wedding_packages` | Wedding package descriptions |
| `faq` | Frequently asked questions |
| `contract_terms` | Contract terms and conditions |
| `deposit_policy` | Deposit rules |
| `cancellation_policy` | Cancellation rules |
| `service_description` | Description of services offered |
| `decoration_rules` | Decoration rules / constraints |
| `catering_rules` | Catering rules / constraints |
| `other` | Anything not covered above |

---

## Processing Status

| Status | Meaning |
|--------|---------|
| `uploaded` | Content stored; not yet queued for processing |
| `processing_pending` | Queued/marked for the future RAG pipeline to chunk + embed |
| `processed` | RAG pipeline finished chunking + embedding (set by the later feature) |
| `failed` | Processing failed (set by the later feature) |

This feature creates documents as `uploaded` and lets a manager mark them `processing_pending`. The `processed`/`failed` transitions are written by the future RAG feature — this feature only stores and reads the status field.

---

## Main Users

| Role | Description |
|------|-------------|
| **Manager** | Uploads/adds, views, updates, disables, and deletes documents for **their own tenant only**. The primary actor for this feature. |
| **Staff** | May **view/list** documents in their tenant (read-only). Cannot create, update, disable, or delete documents. |
| **System / RAG pipeline** | A later, separate feature that reads `processing_pending` documents and advances them to `processed`/`failed`. Not built here; this feature only prepares the data and status field. |

Platform Admin has no access to tenant documents.

---

## User Stories

### User Story 1 — Manager Uploads a Tenant Document (Priority: P1)

A manager adds a business document for their agency by providing a title, a document type, and the content (pasted text/markdown, or a simple text/PDF file). The system validates the input, stores the document scoped to the manager's tenant with status `uploaded`, and records who created it and when.

**Why this priority**: Without the ability to add documents there is no corpus for RAG to use later — this is the foundational capability. Everything else (listing, editing, status) operates on documents created here.

**Independent Test**: As an Elegant Weddings manager, upload a "Deposit Policy" (`deposit_policy`) with text content. Verify the document is stored in the Elegant Weddings tenant with status `uploaded`, `created_by` = the manager, and timestamps set. Verify it does not appear for the Royal Events Agency tenant.

**Acceptance Scenarios**:

1. **Given** an authenticated manager, **When** they submit a valid title, document type, and content, **Then** a document is created in their tenant with status `uploaded`, `created_by` set to the manager, and `created_at`/`updated_at` set.
2. **Given** a submission with an invalid document type, missing title, empty content, an unsupported file type, or oversized content, **When** it is submitted, **Then** it is rejected with a validation error and nothing is stored.
3. **Given** a manager in Tenant A, **When** they upload a document, **Then** it is scoped to Tenant A and never visible to Tenant B.
4. **Given** a staff user, **When** they attempt to upload a document, **Then** the request is rejected (403) — staff cannot create documents.

---

### User Story 2 — View and List Tenant Documents (Priority: P1)

A manager (and, read-only, a staff user) lists all documents in their tenant — with title, type, status, creator, and timestamps — and opens a single document to view its metadata and content. The list shows only the current tenant's documents.

**Why this priority**: Curation requires seeing what exists. Listing/viewing is the read side that makes the corpus manageable and is required before update/delete are useful. Equal priority to US1 because uploading without being able to see results is not usable.

**Independent Test**: With three documents in Elegant Weddings and three in Royal Events, list documents as an Elegant Weddings user — verify exactly the three Elegant Weddings documents appear and none from Royal Events. Open one — verify its metadata and content. Attempt to open a Royal Events document by id as an Elegant Weddings user — verify it is blocked.

**Acceptance Scenarios**:

1. **Given** documents exist in a tenant, **When** a manager or staff user lists documents, **Then** only that tenant's documents are returned, with title, type, status, `created_by`, `created_at`, `updated_at`.
2. **Given** a document id in the caller's tenant, **When** they request it, **Then** the document metadata and content are returned.
3. **Given** a document id belonging to another tenant, **When** a user requests it, **Then** it is blocked (404 if not in tenant / 403 if cross-tenant) and no content is exposed.
4. **Given** filters (by type and/or status), **When** the list is requested with them, **Then** only matching documents in the tenant are returned.

---

### User Story 3 — Update, Disable, and Delete Documents (Priority: P2)

A manager edits a document's title, type, or content; disables a document so it is excluded from future RAG processing without deleting it; or deletes a document entirely. Edits and disabling change status appropriately and update `updated_at`. Staff cannot perform any of these.

**Why this priority**: Documents change (prices update, policies revise). Managing them keeps the corpus accurate. Lower than P1 because an initial corpus (upload + view) already delivers value; management is the next increment.

**Independent Test**: As a manager, edit a document's content — verify `updated_at` changes and the new content is stored. Disable a document — verify it is marked disabled/excluded from processing but still listed (filtered). Delete a document — verify it no longer appears and a subsequent fetch returns 404. As a staff user, attempt each — verify all are rejected (403).

**Acceptance Scenarios**:

1. **Given** a manager and a document in their tenant, **When** they update its title/type/content with valid values, **Then** the changes are stored and `updated_at` is refreshed.
2. **Given** a manager updates content of a document that was `processing_pending` or `processed`, **When** the update is saved, **Then** the status is reset to `uploaded` (content changed → must be re-processed by RAG later).
3. **Given** a manager disables a document, **When** the change is saved, **Then** the document is marked disabled (excluded from future RAG processing) but remains retrievable in the management UI.
4. **Given** a manager deletes a document, **When** the deletion completes, **Then** the document (and its stored content) is removed and a subsequent fetch returns 404.
5. **Given** a staff user, **When** they attempt to update, disable, or delete any document, **Then** the request is rejected (403).
6. **Given** a manager attempts to update/disable/delete a document in another tenant, **When** the request is made, **Then** it is blocked (404/403) and no change occurs.

---

### Edge Cases

- **Duplicate title**: two documents may share a title (e.g., two "FAQ" revisions) — titles are not unique; both are stored separately.
- **Very large content / oversized file**: rejected with a clear validation error (size limit) before storage.
- **Unsupported file type** (e.g., `.docx`, image): rejected with a validation error; only text/markdown (and optionally simple PDF) are accepted.
- **Empty or whitespace-only content**: rejected with a validation error.
- **Title too long / too short**: rejected by length validation.
- **PDF with no extractable text** (if PDF supported): rejected or stored with empty extracted text flagged for review — never silently stored as empty.
- **Editing content of an already-processed document**: allowed, but status resets to `uploaded` so RAG re-processes it later (stale embeddings must not persist).
- **Deleting a `processing_pending` document**: allowed; it is simply removed (the future pipeline must tolerate a missing document).
- **Concurrent edits to the same document**: last write wins; `updated_at` reflects the final write.
- **Disabling vs deleting**: disabling is reversible and keeps content; deleting is permanent.

---

## Requirements

### Functional Requirements

- **FR-001**: Managers MUST be able to create a document with a title, document type, and text content, scoped to their own tenant.
- **FR-002**: The system MUST store document metadata: `title`, `document_type`, `tenant_id`, `status`, `enabled` flag, `created_by`, `created_at`, `updated_at`, plus content (and source filename/MIME when uploaded as a file).
- **FR-003**: New documents MUST be created with status `uploaded`.
- **FR-004**: The system MUST support text-based content (plain text / markdown) as the MVP baseline; simple PDF text extraction MAY be supported if straightforward.
- **FR-005**: The system MUST validate document type (must be a valid `DocumentType`), title (non-empty, length-bounded), content (non-empty, size-bounded), and file type/size when a file is uploaded.
- **FR-006**: Managers MUST be able to list documents in their tenant, optionally filtered by type and/or status, and fetch a single document with content.
- **FR-007**: Staff users MUST be able to list and view documents in their tenant (read-only) and MUST NOT be able to create, update, disable, or delete them.
- **FR-008**: Managers MUST be able to update a document's title, type, and content; on a content change the status MUST reset to `uploaded`.
- **FR-009**: Managers MUST be able to disable a document (set `enabled = false`) to exclude it from future RAG processing without deleting it, and re-enable it.
- **FR-010**: Managers MUST be able to delete a document, removing its metadata and stored content.
- **FR-011**: Managers MUST be able to mark a document `processing_pending` to hand it to the future RAG pipeline.
- **FR-012**: The system MUST scope every document operation to the caller's tenant; cross-tenant access MUST be blocked.
- **FR-013**: A manager MUST only create/manage documents for their own tenant (tenant from JWT; client cannot specify another tenant).
- **FR-014**: This feature MUST NOT chunk, embed, or retrieve documents — it only stores content, metadata, and status.
- **FR-015**: The system MUST record `created_by` (the authenticated manager) and maintain `created_at` and `updated_at` timestamps.

### Key Entities

- **Tenant** (existing, Spec 001): owns documents; `tenant_id` scopes everything.
- **User** (existing, Spec 002): the manager who creates/manages a document (`created_by`); role gates write access.
- **Document** (new): a tenant-scoped business document — title, type, content, status, enabled flag, creator, timestamps, and source file metadata when uploaded.
- **DocumentType** (enum): the ten document types.
- **DocumentStatus** (enum): `uploaded`, `processing_pending`, `processed`, `failed`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Title | Create/update request | Non-empty, length-bounded document title |
| Document type | Create/update request | One of the ten `DocumentType` values |
| Content | Create/update request | Text/markdown body (or extracted from an uploaded file) |
| Uploaded file (optional) | Multipart upload | `.txt` / `.md` (and optionally simple `.pdf`); validated for type + size |
| Filters | List request | Optional `document_type` and/or `status` filters |
| Enabled flag | Update request | Enable/disable the document |
| Status change | Update request | Manager sets `processing_pending` (handoff to RAG) |

---

## Outputs

| Output | Description |
|--------|-------------|
| Created document | Stored document with metadata + status `uploaded` |
| Document list | Tenant-scoped list (title, type, status, enabled, creator, timestamps) |
| Single document | Metadata + content for one in-tenant document |
| Updated document | Reflecting edited fields, refreshed `updated_at`, reset status on content change |
| Deletion result | Confirmation; document and content removed |
| 403 / 404 | Cross-tenant / platform-admin / staff-write / missing document |
| 422 | Invalid type/title/content/file |

---

## Main Workflow

1. **Manager opens the Documents page** — sees the tenant's existing documents.
2. **Manager adds a document** — enters title + type, pastes content or uploads a `.txt`/`.md` (optionally `.pdf`) file.
3. **System validates** — type is valid, title within length, content non-empty and within size, file type/size acceptable.
4. **System stores** — document saved in the manager's tenant, status `uploaded`, `created_by` + timestamps set.
5. **Manager curates** — edits content (status resets to `uploaded`), disables stale documents, deletes obsolete ones.
6. **Manager hands off to RAG** — marks a document `processing_pending` for the future pipeline.
7. **Staff view** — staff can browse/read the tenant's documents but cannot modify them.

---

## Alternative Workflows

### Upload via File

1. Manager chooses a `.txt`/`.md` (or simple `.pdf`) file.
2. System validates MIME/extension and size; extracts text (for PDF) or reads the text directly.
3. If extraction yields empty text, the upload is rejected (not stored as empty).
4. Otherwise the document is stored with the extracted/loaded content and the source filename/MIME recorded.

### Edit Content of a Processed Document

1. A document is `processed` (by the future RAG feature).
2. Manager edits its content.
3. The system saves the new content and resets status to `uploaded` so RAG must re-process it (old embeddings are stale).

### Disable Instead of Delete

1. Manager wants to temporarily exclude a document from RAG.
2. Manager disables it (`enabled = false`).
3. It remains listed in management (and filterable) but is excluded from future processing; it can be re-enabled.

### Cross-Tenant Access Attempt

1. An Elegant Weddings user requests/edits a Royal Events document by id.
2. The backend resolves the tenant from the JWT, sees the document is not in that tenant, and returns 404 (not in tenant) / 403 (cross-tenant).
3. No document content is exposed and no change is made.

### Staff Write Attempt

1. A staff user attempts to create/update/disable/delete a document.
2. The role guard rejects the request with 403.
3. No change occurs; staff retain read-only access.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | A manager can create a document; it is stored in their tenant with status `uploaded`, `created_by`, and timestamps | Integration test: POST → assert stored fields |
| AC-02 | Invalid type / missing title / empty content / unsupported file / oversized content is rejected (422); nothing stored | Integration test: each bad input → 422, no row |
| AC-03 | Documents are tenant-scoped; Tenant B cannot list or read Tenant A documents | Integration test: create in A; list/get as B → not present / 404-403 |
| AC-04 | Staff cannot create, update, disable, or delete documents (403); staff can list/view | Integration test: staff write → 403; staff read → 200 |
| AC-05 | Listing returns only the caller's tenant documents with full metadata | Integration test: 3 in A + 3 in B → list in A returns exactly the 3 A docs |
| AC-06 | List filters by `document_type` and `status` work within the tenant | Integration test: assert filtered subsets |
| AC-07 | `GET /api/documents/{id}` returns metadata + content for an in-tenant document | Integration test: assert fields + content |
| AC-08 | `GET` a non-existent or cross-tenant document returns 404 / 403 | Integration test: random id → 404; other-tenant id → 403 |
| AC-09 | Updating title/type/content stores changes and refreshes `updated_at` | Integration test: PATCH → assert changes + new updated_at |
| AC-10 | Updating content resets status to `uploaded` | Integration test: processed doc → PATCH content → assert status uploaded |
| AC-11 | Disabling sets `enabled=false`; document remains retrievable; re-enable works | Integration test: disable → enabled false, still gettable; enable → true |
| AC-12 | Deleting removes the document; subsequent GET returns 404 | Integration test: DELETE → GET 404 |
| AC-13 | A manager can mark a document `processing_pending` | Integration test: PATCH status → assert processing_pending |
| AC-14 | Platform Admin is blocked from all document endpoints (403) | Integration test: admin token → 403 INSUFFICIENT_ROLE |
| AC-15 | A manager cannot create/manage documents for another tenant (tenant from JWT only) | Integration test: attempt tenant_id override → ignored; cross-tenant → 403/404 |
| AC-16 | The feature performs no chunking, embedding, or retrieval | Code/integration test: assert no such side effects/endpoints |
| AC-17 | File upload validates MIME/extension and size; empty extracted text rejected | Integration test: bad MIME → 422; oversize → 422; empty PDF text → 422 |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenants, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT auth; `manager` (write) and `staff` (read-only) roles; Platform Admin blocked |
| Later RAG feature | Downstream consumer | Will read `processing_pending` documents to chunk + embed and advance status to `processed`/`failed`. Not part of this feature. |

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the JWT. Any `tenant_id` in the request body/query is ignored. Documents are created and queried only within the session tenant. |
| **SR-02: Tenant ownership** | A document belongs to exactly one tenant. Tenant A can never list, read, update, disable, or delete Tenant B documents. |
| **SR-03: Role-based write** | Only `manager` may create/update/disable/delete documents. `staff` is read-only. Platform Admin → 403. Unauthenticated → 401. |
| **SR-04: Not Found vs Forbidden** | A document not in the caller's tenant → 404; one that exists in another tenant → 403 (consistent with Specs 005–007). Endpoints never confirm cross-tenant content. |
| **SR-05: Upload validation** | File type (MIME/extension allowlist), size limit, title length, and content size/non-emptiness are validated server-side before storage. Malformed input never reaches storage. |
| **SR-06: Content isolation** | Stored content is partitioned by tenant; retrieval always carries the tenant filter so document content cannot leak across tenants (including for the future RAG pipeline). |
| **SR-07: Creator attribution** | `created_by` is the authenticated manager; it cannot be spoofed by the client. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Invalid document type | 422 validation error; nothing stored |
| Missing/empty/whitespace title or content | 422 validation error; nothing stored |
| Title too long / content too large | 422 validation error; nothing stored |
| Unsupported file type | 422 `UNSUPPORTED_FILE_TYPE`; nothing stored |
| File exceeds size limit | 422 `FILE_TOO_LARGE`; nothing stored |
| PDF with no extractable text (if PDF supported) | 422 `EMPTY_DOCUMENT_CONTENT`; nothing stored |
| Staff attempts a write | 403 `INSUFFICIENT_ROLE`; no change |
| Cross-tenant document operation | 404/403 per SR-04; no data exposed, no change |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE` |
| `GET`/`PATCH`/`DELETE` non-existent document | 404 `DOCUMENT_NOT_FOUND` |
| Storage write fails | 5xx; no partial document persisted (transactional create) |

---

## Edge Cases (summary)

- Duplicate titles allowed (not unique).
- Oversized/unsupported file → 422 before storage.
- Empty/whitespace content → 422.
- PDF with no extractable text → 422 (never silently empty).
- Editing processed content → status resets to `uploaded`.
- Deleting `processing_pending` → allowed; pipeline tolerates absence.
- Concurrent edits → last write wins.
- Disable is reversible; delete is permanent.

---

## Out of Scope

- **RAG retrieval** — separate, later feature; this feature does not retrieve documents.
- **Chunking** — done by the future RAG pipeline, not here.
- **Embeddings / pgvector indexing** — done by the future RAG pipeline, not here.
- **Suggested reply generation** — separate, later feature.
- **Advancing status to `processed`/`failed`** — written by the future RAG pipeline; this feature only stores/reads the field and lets a manager set `processing_pending`.
- **Audit logging** — added by the later audit-log feature; not built here.
- **Document versioning / revision history** — out of scope (last-write-wins; no version table for MVP).
- **Rich file types** (`.docx`, images, spreadsheets) — out of scope; text/markdown (and optionally simple PDF) only.
- **OCR / scanned-image extraction** — out of scope.
- **Document sharing across tenants** — explicitly forbidden, not a feature.
- **Real WhatsApp API, calendar syncing, full CRM** — out of scope entirely.

---

## Assumptions

- Documents are stored with their content in the database (text column) for MVP; large-file/object-storage is a post-MVP optimisation (the API contract is unaffected). PDF support, if included, extracts text at upload time and stores the extracted text as content.
- A document belongs to exactly one tenant and one creator; there is no cross-tenant or shared document concept.
- Titles are not unique within a tenant.
- The `enabled` flag controls inclusion in future RAG processing; disabled documents are retained and visible in management.
- Content edits invalidate any future RAG processing, so status resets to `uploaded` on content change.
- The future RAG feature owns the `processed`/`failed` transitions and the actual chunk/embed work; this feature only prepares documents and exposes the status field.
- Reasonable default limits (documented in research): title ≤ 200 chars, content ≤ ~1 MB, file ≤ ~5 MB, allowed types `text/plain`, `text/markdown` (+ `application/pdf` if enabled).
