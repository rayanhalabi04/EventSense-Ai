# Implementation Plan: Document Upload

**Branch**: `008-document-upload` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-document-upload/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenants, `tenant_id` isolation, cross-tenant blocking, `TenantScopedRepository`
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth; `manager` (write) + `staff` (read) roles; `require_role`; `get_current_tenant_context`

**Downstream consumer**: the future RAG feature reads `processing_pending` documents to chunk + embed and advances status to `processed`/`failed`. Not built here.

---

## Summary

Build tenant-scoped CRUD for business documents that a later RAG pipeline will consume. A new `documents` table stores `title`, `document_type`, `content`, `status`, `enabled`, `created_by`, source-file metadata, and timestamps, all scoped by `tenant_id`. A `DocumentService` enforces tenant ownership (404/403 like Specs 005–007) and the role split (manager writes, staff read-only). Five REST endpoints provide create/list/get/update/delete plus a multipart file-upload path that validates MIME/extension/size and extracts text (plain text/markdown now, simple PDF optional). New documents are `uploaded`; managers can mark them `processing_pending` for RAG; editing content resets status to `uploaded`. The feature performs **no** chunking, embedding, or retrieval — it only prepares and curates the corpus and exposes the status field.

---

## Technical Approach

- **DB-stored content for MVP**: content lives in a `TEXT` column; the API contract is storage-agnostic so a later move to object storage needs no client changes. File uploads are read/extracted at request time and stored as text.
- **Validation-first**: a Pydantic layer validates type/title/content; a file-validation helper enforces an allowlist of MIME types + a size cap and (optionally) extracts PDF text before anything is persisted.
- **Tenant + role enforcement**: every operation resolves the document within the JWT tenant (404/403); writes require `manager`, reads allow `manager`+`staff`; Platform Admin → 403. `tenant_id` and `created_by` come from the session, never the client.
- **Status lifecycle owned partly here**: this feature sets `uploaded` (on create / content edit) and `processing_pending` (manager handoff); `processed`/`failed` are reserved for the future RAG feature.
- **Two create paths, one model**: JSON body (pasted content) and multipart (file upload) both converge on the same `DocumentService.create_document`.

---

## Backend Tasks

1. **`schemas/document.py`** — Pydantic models: `DocumentCreateRequest`, `DocumentUpdateRequest`, `DocumentResponse` (with content), `DocumentListItem` (metadata only), plus `DocumentType` and `DocumentStatus` string enums.
2. **`services/document_service.py`**:
   - `create_document(session, tenant_id, user, data)` — validate, store status `uploaded`, set `created_by` + timestamps.
   - `list_documents(session, tenant_id, filters)` — tenant-scoped list with optional `document_type`/`status`/`enabled` filters.
   - `get_document(session, tenant_id, document_id)` — tenant-resolve (404/403); return with content.
   - `update_document(session, tenant_id, document_id, data)` — update title/type/content/enabled/status; reset status to `uploaded` on content change.
   - `delete_document(session, tenant_id, document_id)` — remove document + content.
3. **`files/extract.py`** — file-validation + text-extraction helper: MIME/extension allowlist, size check, plain-text/markdown passthrough, optional PDF text extraction; raises typed errors (`UnsupportedFileType`, `FileTooLarge`, `EmptyDocumentContent`).
4. **`api/v1/documents.py`** — five endpoints (+ multipart support on create) with `require_role` per method and error→HTTP mapping.
5. **Config** — `DOC_MAX_TITLE_LEN`, `DOC_MAX_CONTENT_BYTES`, `DOC_MAX_FILE_BYTES`, `DOC_ALLOWED_MIME`, `DOC_PDF_ENABLED` in settings.
6. **Router mount** — register the documents router at `/api` in `main.py`.

---

## Database Tasks

1. **Alembic migration** — create `documents`:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL, FK → `tenants.id`, indexed
   - `title` VARCHAR(200) NOT NULL
   - `document_type` VARCHAR(40) NOT NULL (one of `DocumentType`)
   - `content` TEXT NOT NULL
   - `status` VARCHAR(20) NOT NULL default `uploaded`
   - `enabled` BOOLEAN NOT NULL default true
   - `source_filename` VARCHAR(255) NULL
   - `source_mime` VARCHAR(100) NULL
   - `content_bytes` INTEGER NULL (size of stored content)
   - `created_by` UUID NOT NULL FK → users
   - `created_at`, `updated_at` TIMESTAMPTZ
2. **Indexes**: `(tenant_id, document_type)` and `(tenant_id, status)` for filtered listing; `(tenant_id, enabled)` for the future processing query.
3. **SQLAlchemy model** `Document` in `models/document.py` with relationships to `Tenant` and `User` (creator).
4. **Enums** persisted as constrained strings (portable + evolvable), validated at the app boundary.

---

## File / Content Storage Tasks

1. **Allowlist + limits** — accept `text/plain`, `text/markdown` (and `application/pdf` when `DOC_PDF_ENABLED`); enforce `DOC_MAX_FILE_BYTES` and `DOC_MAX_CONTENT_BYTES`.
2. **Text passthrough** — for text/markdown, decode (UTF-8) and store directly; reject undecodable bytes.
3. **PDF extraction (optional)** — if enabled, extract text with a lightweight library; if extraction yields empty/whitespace text → `EmptyDocumentContent` (422). Store extracted text as `content`.
4. **Source metadata** — record `source_filename`, `source_mime`, `content_bytes` for file uploads (null for pasted content).
5. **Storage abstraction** — content saved to the `content` column for MVP; keep a thin seam so a later object-store backend can replace the column without API changes.
6. **No chunk/embed** — explicitly out of scope; the helper produces only plain text + metadata.

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/documents` | POST | manager | Create (JSON content or multipart file) |
| `/api/documents` | GET | manager, staff | List tenant documents (filters) |
| `/api/documents/{document_id}` | GET | manager, staff | Get one document + content |
| `/api/documents/{document_id}` | PATCH | manager | Update title/type/content/enabled/status |
| `/api/documents/{document_id}` | DELETE | manager | Delete document + content |

- All resolve tenant first (404/403) per SR-04; `tenant_id`/`created_by` from JWT only.
- Pydantic validation (type/title/content); file validation for multipart.
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/documents.ts`** — typed client: `createDocument`, `uploadDocumentFile`, `listDocuments(filters)`, `getDocument(id)`, `updateDocument(id, payload)`, `deleteDocument(id)`.
2. **`types/document.ts`** — `DocumentType`, `DocumentStatus`, `Document`, `DocumentListItem` TS types.
3. **`pages/DocumentsPage.tsx`** — `/documents` route; `ProtectedRoute` + role-aware UI (manager sees write controls; staff read-only); lists documents with type/status filters.
4. **`components/documents/DocumentList.tsx`** + `DocumentRow.tsx` — table/cards with title, type badge, status badge, enabled state, creator, timestamps.
5. **`components/documents/DocumentForm.tsx`** — create/edit form: title, type `Select`, content textarea, and a file picker (`.txt`/`.md`/optional `.pdf`); client-side type/size hints; calls create/update.
6. **`components/documents/DocumentDetail.tsx`** — view metadata + content; manager actions: edit, disable/enable, delete, mark `processing_pending`.
7. **States** — loading, empty (no documents yet), validation errors (422 surfaced inline), forbidden (staff write attempt hidden/blocked), not-found.

---

## Testing Tasks

**Backend integration** — `tests/integration/test_documents.py`:
- Manager create + stored fields (AC-01); validation rejections (AC-02, AC-17)
- Tenant isolation list/get (AC-03, AC-05, AC-08)
- Staff read-only + staff write 403 (AC-04)
- List filters (AC-06); get with content (AC-07)
- Update + updated_at (AC-09); content edit resets status (AC-10)
- Disable/enable (AC-11); delete → 404 (AC-12); mark processing_pending (AC-13)
- Platform Admin 403 (AC-14); tenant override ignored (AC-15)
- No chunk/embed/retrieve side effects (AC-16)

**Unit** — `tests/unit/test_file_extract.py`: MIME/extension allowlist, size cap, UTF-8 decode failure, PDF empty-text rejection, content-size bound.

**Frontend** — render/interaction tests: list shows tenant docs; manager sees write controls, staff does not; form validation surfaces 422; delete confirms and removes.

---

## Build Order

1. **DB + models** — Alembic migration + `Document` model + enums.
2. **Schemas** — Pydantic models + enums.
3. **File helper** — `files/extract.py` (validation + text/PDF extraction) with unit tests.
4. **Service** — `document_service` (create/list/get/update/delete) with tenant + role + status-reset logic.
5. **API** — five endpoints + multipart create + router mount + error mapping; integration tests.
6. **Frontend** — types + API client → Documents page → list → form (create/upload) → detail (edit/disable/delete/handoff) → states.
7. **Validation** — run quickstart with the two demo tenants and their example documents; confirm all 17 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/008-document-upload/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── documents.py                 # 5 endpoints (+ multipart create)
│   ├── services/
│   │   └── document_service.py          # create / list / get / update / delete
│   ├── files/
│   │   └── extract.py                   # file validation + text/PDF extraction
│   ├── models/
│   │   └── document.py                  # Document ORM model
│   └── schemas/
│       └── document.py                  # Pydantic + DocumentType/DocumentStatus enums
├── alembic/versions/
│   └── 00xx_create_documents.py
└── tests/
    ├── integration/
    │   └── test_documents.py
    └── unit/
        └── test_file_extract.py

frontend/
└── src/
    ├── api/
    │   └── documents.ts
    ├── types/
    │   └── document.ts
    ├── pages/
    │   └── DocumentsPage.tsx
    └── components/documents/
        ├── DocumentList.tsx
        ├── DocumentRow.tsx
        ├── DocumentForm.tsx
        └── DocumentDetail.tsx
```

Modified files:

```
backend/app/main.py            # mount documents router
backend/app/core/config.py     # DOC_* settings (limits, allowlist, PDF flag)
frontend/src/App.tsx           # add /documents route
frontend/src/components/NavBar (or Sidebar)  # add Documents nav item (manager + staff)
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–007. A dedicated `backend/app/files/` package isolates upload validation + text extraction from the service/API layers, keeping the storage seam clean for the future object-store/RAG work.
