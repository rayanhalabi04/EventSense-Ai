---

description: "Task list for Document Upload feature implementation"
---

# Tasks: Document Upload

**Branch**: `008-document-upload` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/008-document-upload/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `TenantScopedRepository`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; `get_current_tenant_context`; Platform Admin block; `users` table; consistent `error_code` payload shape

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: one table `documents` + one Alembic migration. Enums persisted as constrained strings (VARCHAR + app-boundary validation), not native PG enums.

**Config defaults** (research.md Decision 6): `DOC_MAX_TITLE_LEN=200`, `DOC_MAX_CONTENT_BYTES=1_048_576` (1 MB), `DOC_MAX_FILE_BYTES=5_242_880` (5 MB), `DOC_ALLOWED_MIME=text/plain,text/markdown` (+ `application/pdf` when enabled), `DOC_PDF_ENABLED=false`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–002 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant` model + `tenants` table (Spec 001), `User` model + role enum (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `NotFoundError`/`ForbiddenError` (Spec 001) and their error→HTTP mapping, and the shared `error_code` response envelope. Do NOT redefine any of these.
- [ ] T002 Add `DOC_MAX_TITLE_LEN` (200), `DOC_MAX_CONTENT_BYTES` (1_048_576), `DOC_MAX_FILE_BYTES` (5_242_880), `DOC_ALLOWED_MIME` (`text/plain`, `text/markdown`), and `DOC_PDF_ENABLED` (false) to `backend/app/core/config.py` with documented defaults; `application/pdf` is appended to the allowlist only when `DOC_PDF_ENABLED` is true (research.md Decision 6)
- [ ] T003 Verify `backend/tests/integration/` and `backend/tests/unit/` exist with `__init__.py`; create if absent (required before test files in later phases)

**Checkpoint**: Dependencies confirmed reused; config in place.

---

## Phase 2: Database & Models (Foundational — Blocking)

**Purpose**: The `documents` table and ORM model underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 5–7 cannot run without this phase.

- [ ] T004 [P] Create `DocumentType` (ten values: `pricing_packages`, `wedding_packages`, `faq`, `contract_terms`, `deposit_policy`, `cancellation_policy`, `service_description`, `decoration_rules`, `catering_rules`, `other`) and `DocumentStatus` (`uploaded`, `processing_pending`, `processed`, `failed`) string enums in `backend/app/schemas/document.py` (shared by the service and API layers) — per data-model.md
- [ ] T005 Create `Document` SQLAlchemy model in `backend/app/models/document.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `title` VARCHAR(200) NOT NULL; `document_type` VARCHAR(40) NOT NULL; `content` TEXT NOT NULL; `status` VARCHAR(20) NOT NULL default `uploaded`; `enabled` Boolean NOT NULL default true; `source_filename` VARCHAR(255) nullable; `source_mime` VARCHAR(100) nullable; `content_bytes` Integer nullable; `created_by` UUID FK→`users.id` NOT NULL; `created_at`/`updated_at` TIMESTAMPTZ (server_default now, updated_at onupdate now); `tenant` + `creator` relationships; `Index("ix_documents_tenant_type", "tenant_id", "document_type")`, `Index("ix_documents_tenant_status", "tenant_id", "status")`, `Index("ix_documents_tenant_enabled", "tenant_id", "enabled")` — per data-model.md
- [ ] T006 Create Alembic migration `backend/alembic/versions/00xx_create_documents.py` creating `documents` with all columns, the two FKs (`tenant_id`→`tenants.id`, `created_by`→`users.id`), defaults (`status='uploaded'`, `enabled=true`), and all three composite indexes; provide a correct `downgrade()` dropping the table and indexes (depends on T005)

**Checkpoint**: `alembic upgrade head` creates the table; ORM model importable.

---

## Phase 3: File / Content Storage & Validation (Foundational — Blocking)

**Purpose**: The pure file-validation + text-extraction helper is the upload security boundary (SR-05). Build and fully unit-test it in isolation before any service/API wiring. **BLOCKS the multipart create path in US1.**

- [ ] T007 Define typed errors `UnsupportedFileType`, `FileTooLarge`, `EmptyDocumentContent` in `backend/app/files/extract.py` (or a shared errors module if one exists from 001) for the upload validation path
- [ ] T008 Implement `extract_text(upload) -> tuple[content, filename, mime]` in `backend/app/files/extract.py`: reject MIME/extension not in `DOC_ALLOWED_MIME` → `UnsupportedFileType`; read bytes and reject size > `DOC_MAX_FILE_BYTES` → `FileTooLarge`; for `text/plain`/`text/markdown` decode UTF-8 (undecodable bytes → `UnsupportedFileType`); for `application/pdf` extract text only when `DOC_PDF_ENABLED` (else `UnsupportedFileType`); empty/whitespace extracted text → `EmptyDocumentContent`. Pure, no DB/I/O beyond reading the upload. Per data-model.md + research.md Decisions 2 & 8 (depends on T002, T007)
- [ ] T009 Implement `_validate_content(content)` helper (non-empty/non-whitespace, byte length ≤ `DOC_MAX_CONTENT_BYTES` → else raise validation error) in `backend/app/files/extract.py` or `backend/app/services/document_service.py`, shared by both create paths and update (depends on T002)

### Unit Tests for the File Helper

- [ ] T010 [P] Write `backend/tests/unit/test_file_extract.py`: MIME/extension allowlist accept (`.txt`/`.md`) and reject (e.g. `application/json`, `.docx`) → `UnsupportedFileType`; oversize file → `FileTooLarge`; non-UTF-8 bytes → `UnsupportedFileType`; empty/whitespace-only file → `EmptyDocumentContent`; PDF rejected when `DOC_PDF_ENABLED=false` and (if enabled) empty-extracted-text PDF → `EmptyDocumentContent`; content > `DOC_MAX_CONTENT_BYTES` → validation error (AC-17 basis) (depends on T008, T009)

**Checkpoint**: File validation/extraction is correct and deterministic; unit tests pass without any DB.

---

## Phase 4: Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service and endpoints.

- [ ] T011 Add Pydantic models to `backend/app/schemas/document.py` (alongside the enums from T004) per data-model.md: `DocumentCreateRequest` (`title` 1–200 non-blank, `document_type: DocumentType`, `content: str | None`), `DocumentUpdateRequest` (all optional: `title`, `document_type`, `content`, `enabled`, `status`), `DocumentListItem` (metadata only: `id`, `title`, `document_type`, `status`, `enabled`, `created_by`, `created_at`, `updated_at`; `from_attributes=True`), `DocumentResponse(DocumentListItem)` (adds `content`, `source_filename`, `source_mime`, `content_bytes`), and a `DocumentListResponse` (`items: list[DocumentListItem]`, `total: int`) matching the contract's `{items, total}` shape; title `field_validator` strips and rejects blank (depends on T004)

**Checkpoint**: Schemas importable — service and API phases can begin.

---

## Phase 5: User Story 1 — Manager Uploads a Tenant Document (Priority: P1) 🎯 MVP

**Goal**: A manager creates a document (pasted JSON `content` **or** multipart file upload) scoped to their JWT tenant, stored with status `uploaded`, `enabled=true`, `created_by`=the manager, and timestamps set. Validation (title/type/content/file MIME+size) rejects bad input with 422 before storage and stores nothing. `tenant_id`/`created_by` come from the JWT only; a client-supplied `tenant_id` is ignored. Staff create → 403; platform admin → 403.

**Independent Test**: As an Elegant Weddings manager, create a "Deposit Policy" (`deposit_policy`) with text content → stored in the Elegant Weddings tenant, status `uploaded`, `created_by`=manager, timestamps set; not visible to Royal Events.

### Tests for User Story 1

> Write tests first; confirm they fail before implementing the Phase 5 backend tasks.

- [ ] T012 [US1] Write `test_manager_creates_document_json` (AC-01) in `backend/tests/integration/test_documents.py` — manager POST JSON `{title, document_type, content}` → 201, stored with status `uploaded`, `enabled=true`, `created_by`=manager, `tenant_id`=manager's tenant, `created_at`/`updated_at` set, `content_bytes` correct
- [ ] T013 [P] [US1] Write `test_manager_creates_document_file_upload` (AC-01, AC-17) in `backend/tests/integration/test_documents.py` — manager POST multipart `.md` file → 201, status `uploaded`, `source_filename`/`source_mime` recorded, content = extracted text
- [ ] T014 [P] [US1] Write `test_create_rejects_invalid_input` (AC-02) in `backend/tests/integration/test_documents.py` — invalid `document_type`, blank/missing title, empty/whitespace content, and missing-both/both-supplied content source each → 422 and no row stored
- [ ] T015 [P] [US1] Write `test_create_rejects_bad_file` (AC-17) in `backend/tests/integration/test_documents.py` — unsupported MIME → 422 `UNSUPPORTED_FILE_TYPE`; oversize file → 422 `FILE_TOO_LARGE`; empty-extracted-text → 422 `EMPTY_DOCUMENT_CONTENT`; nothing stored
- [ ] T016 [P] [US1] Write `test_staff_cannot_create` (AC-04) in `backend/tests/integration/test_documents.py` — staff POST → 403 `INSUFFICIENT_ROLE`, no row
- [ ] T017 [P] [US1] Write `test_client_tenant_id_ignored_on_create` (AC-15, SR-01) in `backend/tests/integration/test_documents.py` — manager POST with a foreign `tenant_id` in the body → ignored; document is created in the JWT tenant only
- [ ] T018 [P] [US1] Write `test_created_by_not_spoofable` (SR-07) in `backend/tests/integration/test_documents.py` — a `created_by` supplied in the body is ignored; `created_by` is always the authenticated manager

### Backend Implementation for User Story 1

- [ ] T019 [US1] Implement `create_document(session, tenant_id, user, *, title, document_type, content, source_filename=None, source_mime=None) -> Document` in `backend/app/services/document_service.py`: call `_validate_content`; construct `Document` with `tenant_id` (JWT, SR-01), `status=uploaded`, `enabled=true`, `created_by=user.id` (SR-07), `content_bytes=len(content.encode("utf-8"))`; add + commit; return (depends on T005, T009)
- [ ] T020 [US1] Implement `POST /api/documents` route in `backend/app/api/v1/documents.py` with `require_role(manager)`, `tenant_id`/`user` from `get_current_tenant_context`, supporting **both** content paths: `application/json` → `DocumentCreateRequest`; `multipart/form-data` → form fields `title`/`document_type` + `UploadFile` `file` routed through `extract_text`; enforce exactly-one content source (missing/both → 422); error→HTTP mapping: `UnsupportedFileType`/`FileTooLarge`/`EmptyDocumentContent` → 422 with the contract `error_code`; return 201 `DocumentResponse` (depends on T019, T008, T011)
- [ ] T021 [US1] Mount the documents router at `/api` in `backend/app/main.py` so endpoints resolve at `/api/documents` (depends on T020)

**Checkpoint**: US1 functional — managers create documents via JSON and file upload (tenant-scoped, validated, status `uploaded`); staff/admin blocked; client tenant override ignored; tests pass.

---

## Phase 6: User Story 2 — View and List Tenant Documents (Priority: P1)

**Goal**: A manager (and, read-only, staff) lists the tenant's documents (metadata only, `{items, total}`), optionally filtered by `document_type`/`status`/`enabled`, and fetches a single document with content. Lists are unconditionally `WHERE tenant_id = :jwt_tenant`. Single GET resolves the document first: not found → 404 `DOCUMENT_NOT_FOUND`; in another tenant → 403 `CROSS_TENANT_FORBIDDEN`. Platform admin → 403.

**Independent Test**: With three documents in Elegant Weddings and three in Royal Events, list as an Elegant Weddings user → exactly the three EW docs; open one → metadata + content; attempt to open a Royal Events doc by id → 403.

### Tests for User Story 2

> Write tests first; confirm they fail before implementing the Phase 6 backend tasks.

- [ ] T022 [P] [US2] Write `test_list_returns_only_tenant_documents` (AC-03, AC-05) in `backend/tests/integration/test_documents.py` — 3 in Tenant A + 3 in Tenant B → list as A returns exactly the 3 A docs (metadata-only, no `content`), `total=3`
- [ ] T023 [P] [US2] Write `test_list_filters_by_type_and_status` (AC-06) in `backend/tests/integration/test_documents.py` — `?document_type=` and `?status=` (and `?enabled=`) return only matching in-tenant subsets
- [ ] T024 [P] [US2] Write `test_get_single_returns_content` (AC-07) in `backend/tests/integration/test_documents.py` — in-tenant doc id → 200 full `DocumentResponse` with `content` and source fields
- [ ] T025 [P] [US2] Write `test_get_cross_tenant_and_missing` (AC-08, SR-04) in `backend/tests/integration/test_documents.py` — random UUID → 404 `DOCUMENT_NOT_FOUND`; another tenant's doc id → 403 `CROSS_TENANT_FORBIDDEN`, no content exposed; non-UUID path → 422
- [ ] T026 [P] [US2] Write `test_staff_can_list_and_view` (AC-04) in `backend/tests/integration/test_documents.py` — staff GET list and GET single → 200 (read-only access allowed)

### Backend Implementation for User Story 2

- [ ] T027 [US2] Implement `list_documents(session, tenant_id, *, document_type=None, status=None, enabled=None) -> list[Document]` in `backend/app/services/document_service.py`: `select(Document).where(Document.tenant_id == tenant_id)` (SR-02/SR-06) + optional filters; `order_by(Document.updated_at.desc())` (matches quickstart expected order) (depends on T005)
- [ ] T028 [US2] Implement `get_document(session, tenant_id, document_id) -> Document` in `backend/app/services/document_service.py`: `session.get`; `None` → `NotFoundError` (404 `DOCUMENT_NOT_FOUND`); `doc.tenant_id != tenant_id` → `ForbiddenError` (403 `CROSS_TENANT_FORBIDDEN`) — mirrors Specs 005–007 SR-04 (depends on T005)
- [ ] T029 [US2] Implement `GET /api/documents` (list, `{items, total}`) and `GET /api/documents/{document_id}` (single, full `DocumentResponse`) routes in `backend/app/api/v1/documents.py` with `require_role(manager, staff)`, `tenant_id` from JWT, optional filter query params (invalid enum value → 422), UUID path param (malformed → 422), and `NotFoundError`→404 / `ForbiddenError`→403 mapping (depends on T027, T028, T011)

**Checkpoint**: US1 + US2 functional — tenant-scoped list (with filters) and single-document read with content; cross-tenant/missing handled; staff read-only works.

---

## Phase 7: User Story 3 — Update, Disable, and Delete Documents (Priority: P2)

**Goal**: A manager edits a document's title/type/content, disables/re-enables it (`enabled`), marks it `processing_pending` (RAG handoff), or deletes it. Editing content resets `status` to `uploaded` (AC-10) and overrides any conflicting `status` field. Setting `processed`/`failed` → 422 `STATUS_NOT_SETTABLE` (RAG-owned). `updated_at` refreshes on change. Delete removes the row + content (subsequent GET → 404). Staff write → 403; cross-tenant → 404/403; platform admin → 403.

**Independent Test**: As a manager, edit a doc's content → `updated_at` changes, status returns to `uploaded`; disable → `enabled=false` but still listed; delete → subsequent GET 404. As staff, attempt each → 403.

### Tests for User Story 3

> Write tests first; confirm they fail before implementing the Phase 7 backend tasks.

- [ ] T030 [P] [US3] Write `test_update_fields_refreshes_updated_at` (AC-09) in `backend/tests/integration/test_documents.py` — PATCH title/type → changes stored, `updated_at` refreshed
- [ ] T031 [P] [US3] Write `test_content_edit_resets_status_to_uploaded` (AC-10) in `backend/tests/integration/test_documents.py` — doc marked `processing_pending` → PATCH `content` → status reset to `uploaded`, `content_bytes` updated (even if a conflicting `status` is sent)
- [ ] T032 [P] [US3] Write `test_disable_and_reenable` (AC-11) in `backend/tests/integration/test_documents.py` — PATCH `enabled=false` → still gettable and listed; PATCH `enabled=true` → re-enabled
- [ ] T033 [P] [US3] Write `test_mark_processing_pending` (AC-13) in `backend/tests/integration/test_documents.py` — PATCH `status=processing_pending` → 200, status updated
- [ ] T034 [P] [US3] Write `test_status_processed_failed_rejected` (contract) in `backend/tests/integration/test_documents.py` — PATCH `status=processed` and `status=failed` → 422 `STATUS_NOT_SETTABLE`, unchanged
- [ ] T035 [P] [US3] Write `test_delete_then_get_404` (AC-12) in `backend/tests/integration/test_documents.py` — DELETE → 204; subsequent GET → 404 `DOCUMENT_NOT_FOUND`
- [ ] T036 [P] [US3] Write `test_staff_cannot_update_disable_delete` (AC-04) in `backend/tests/integration/test_documents.py` — staff PATCH and DELETE → 403 `INSUFFICIENT_ROLE`, no change
- [ ] T037 [P] [US3] Write `test_update_delete_cross_tenant_blocked` (AC-15, SR-04) in `backend/tests/integration/test_documents.py` — PATCH/DELETE a Tenant B doc as Tenant A → 404/403, no change

### Backend Implementation for User Story 3

- [ ] T038 [US3] Implement `update_document(session, tenant_id, document_id, data) -> Document` in `backend/app/services/document_service.py`: `get_document` (404/403); apply provided `title` (stripped) / `document_type` / `enabled`; if `status` provided assert it is only `uploaded`/`processing_pending` else raise `StatusNotSettable` (422 `STATUS_NOT_SETTABLE`); if `content` provided `_validate_content`, set content + `content_bytes` and force `status=uploaded` (overrides any conflicting status, AC-10); commit; return (depends on T028, T009)
- [ ] T039 [US3] Implement `delete_document(session, tenant_id, document_id) -> None` in `backend/app/services/document_service.py`: `get_document` (404/403) → `session.delete` + commit (removes row + content) (depends on T028)
- [ ] T040 [US3] Implement `PATCH /api/documents/{document_id}` (`require_role(manager)`, `DocumentUpdateRequest`, returns 200 `DocumentResponse`) and `DELETE /api/documents/{document_id}` (`require_role(manager)`, returns 204) routes in `backend/app/api/v1/documents.py` with `tenant_id` from JWT, UUID path param, and `NotFoundError`→404 / `ForbiddenError`→403 / `StatusNotSettable`→422 mapping (depends on T038, T039, T011)

**Checkpoint**: US1 + US2 + US3 functional — full create → view → update/disable/delete loop; content edit resets status; RAG-owned statuses rejected; staff/cross-tenant/admin blocked.

---

## Phase 8: Frontend Implementation

**Purpose**: Documents page with list, create/upload form, detail/edit, and role-aware controls, plus loading/empty/error/forbidden states.

- [ ] T041 [P] Create `frontend/src/types/document.ts` with `DocumentType`, `DocumentStatus`, `DocumentListItem`, and `Document` TS types mirroring the backend (per data-model.md)
- [ ] T042 [P] Create `frontend/src/api/documents.ts` typed client using the existing auth token interceptor: `createDocument(payload)`, `uploadDocumentFile(form)`, `listDocuments(filters)`, `getDocument(id)`, `updateDocument(id, payload)`, `deleteDocument(id)` (depends on T041)
- [ ] T043 [US2] Create `DocumentsPage` at `frontend/src/pages/DocumentsPage.tsx` (route `/documents` via `ProtectedRoute` for `manager`+`staff`): loads + lists tenant documents with `document_type`/`status` filters; role-aware (manager sees create/upload + write controls; staff read-only); loading / empty ("no documents yet") / error states (depends on T042)
- [ ] T044 [US2] Create `DocumentList`/`DocumentRow` in `frontend/src/components/documents/` rendering title, type badge, `DocumentStatus` badge, enabled state, creator, timestamps (depends on T042)
- [ ] T045 [P] [US2] Create a status-badge component (e.g. in `DocumentRow` or a small `DocumentStatusBadge.tsx`) mapping each `DocumentStatus` to a distinct shadcn `Badge` style (depends on T041)
- [ ] T046 [US1] Create `DocumentForm` in `frontend/src/components/documents/DocumentForm.tsx`: create/edit form with title input, `document_type` `Select` (ten types), content textarea, and a file picker (`.txt`/`.md`, `.pdf` only when enabled); client-side title/size hints mirroring server limits; surfaces 422 `error_code`/`detail` inline; calls create/update (depends on T042)
- [ ] T047 [US3] Create `DocumentDetail` in `frontend/src/components/documents/DocumentDetail.tsx`: view metadata + content; manager actions edit / disable-enable / delete (with confirm) / mark `processing_pending`; not-found state; actions hidden/disabled for staff (depends on T042, T046)
- [ ] T048 Add the `/documents` route in `frontend/src/App.tsx` and a "Documents" nav item (visible to `manager`+`staff`, hidden for `platform_admin`) in the NavBar/Sidebar (depends on T043)

**Checkpoint**: Documents page usable end-to-end — list, filter, create/upload, view, edit, disable, delete; states handled; staff read-only.

---

## Phase 9: Frontend Tests

**Purpose**: Cover the list, form validation, status badge, states, and manager-only controls.

- [ ] T049 [P] Write `DocumentList`/`DocumentRow` render test in `frontend/src/components/documents/DocumentList.test.tsx` — list renders tenant docs with type + status badges; empty state renders when no documents
- [ ] T050 [P] Write `DocumentForm` validation test in `frontend/src/components/documents/DocumentForm.test.tsx` — blank title / missing type / empty content blocked client-side; a server 422 surfaces inline without losing input
- [ ] T051 [P] Write status-badge test in `frontend/src/components/documents/DocumentStatusBadge.test.tsx` — each `DocumentStatus` renders its distinct badge
- [ ] T052 [P] Write role/error-state test in `frontend/src/pages/DocumentsPage.test.tsx` — manager sees create/upload + edit/delete controls; staff sees read-only (controls hidden/disabled); list error state renders an error message

**Checkpoint**: Frontend behavior verified for list, form validation, status badge, empty/error states, and manager-only access.

---

## Phase 10: Tenant Isolation & Role Security (cross-cutting)

**Purpose**: Explicitly assert the security contract across all five endpoints (some overlap with US1–US3 tenant tests; this phase guarantees full coverage).

- [ ] T053 [P] Write `test_platform_admin_blocked_all_document_endpoints` (AC-14) in `backend/tests/integration/test_documents.py` — platform admin token on POST/GET list/GET single/PATCH/DELETE → 403 `INSUFFICIENT_ROLE`
- [ ] T054 [P] Write `test_tenant_a_cannot_access_tenant_b_documents` (AC-03, SR-02) in `backend/tests/integration/test_documents.py` — Tenant A cannot list, get, update, disable, or delete any Tenant B document (not present in list; 403/404 on single ops)
- [ ] T055 [P] Write `test_no_rag_side_effects` (AC-16) in `backend/tests/integration/test_documents.py` — assert no chunking/embedding/vector/retrieval records, calls, or endpoints result from any document operation (feature only stores content + metadata + status)

**Checkpoint**: Platform Admin blocked everywhere; full tenant isolation across all CRUD ops; no RAG work performed.

---

## Phase 11: Quickstart & Manual Validation

**Purpose**: End-to-end validation against the running stack using the two demo tenants.

- [ ] T056 Run `alembic upgrade head` (applies `create_documents`); confirm the documents router is mounted at `/api/documents` and `DOC_*` settings load with defaults
- [ ] T057 [P] Run `pytest backend/tests/unit/test_file_extract.py -v` and `pytest backend/tests/integration/test_documents.py -v`; confirm all pass (AC-01–AC-17)
- [ ] T058 [P] Run the frontend test suite; confirm the `DocumentList`/`DocumentForm`/status-badge/`DocumentsPage` tests pass
- [ ] T059 Execute the `quickstart.md` seed flows: as Elegant Weddings manager create Premium Wedding Package, Deposit Policy, Cancellation Policy, Decoration Rules; as Royal Events manager create Luxury Wedding Package, Refund Policy, Catering Policy, Bridal Entrance Setup Policy; confirm each tenant's list shows only its own four documents (updated_at desc order)
- [ ] T060 [P] Validate the supporting quickstart flows: cross-tenant GET → 403 `CROSS_TENANT_FORBIDDEN`; type/status filters; multipart `.md` upload → status `uploaded` + source fields; unsupported file → 422; content edit resets status to `uploaded`; `status=processed` → 422 `STATUS_NOT_SETTABLE`; disable then delete (204) then GET 404; staff list 200 + staff create 403; platform admin → 403 `INSUFFICIENT_ROLE`
- [ ] T061 Frontend manual check (quickstart "See It in the UI"): EW manager sees four seeded docs with type/status badges + create/upload controls; create (paste) and upload (`.md`) both appear as `uploaded`; edit content returns badge to `uploaded`; disable stays listed; delete disappears; EW staff sees read-only list; RE manager sees only Royal Events documents
- [ ] T062 Only if T059–T061 reveal a doc mismatch: update `quickstart.md` to match implemented behavior (do not modify other features' specs)

**Checkpoint**: Feature validated end-to-end against quickstart and the two demo tenants; tenant isolation proven.

---

## Phase 12: Acceptance Checklist

**Purpose**: Tick off the requirements checklist once the corresponding tasks are green.

- [ ] T063 Verify every Functional, Security, Tenant Isolation, API, Data, and Testing item in `specs/008-document-upload/checklists/requirements.md` is satisfied (AC-01–AC-17 covered by Phases 5–11); check the boxes for completed items
- [ ] T064 Confirm all Out-of-Scope items in the checklist remain unbuilt: no RAG retrieval, no chunking, no embeddings/pgvector, no suggested replies, no advancing to `processed`/`failed`, no audit-log system, no versioning, no rich file types/OCR, no cross-tenant sharing, no WhatsApp/calendar/CRM

**Checkpoint**: All 17 acceptance criteria verified; out-of-scope confirmed unbuilt; feature ready to mark complete.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Database & Models (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**
- **File Helper (Phase 3)**: Depends on config (T002) — pure, testable in isolation — **BLOCKS the multipart create path in US1**
- **Schemas (Phase 4)**: Depends on enums (T004)
- **US1 (Phase 5)**: Depends on Phases 2–4 (model, file helper, schemas) — create (JSON + file) + router mount
- **US2 (Phase 6)**: Depends on model + schemas (T005, T011) and `get_document`/`list_documents`; read endpoints
- **US3 (Phase 7)**: Depends on US2 `get_document` (T028) for resolve-then-mutate; update/delete endpoints
- **Frontend (Phase 8)**: Depends on the API contract being stable (Phases 5–7); types → client → page/components
- **Frontend Tests (Phase 9)**: Depend on the frontend components (T043–T047)
- **Security (Phase 10)**: Depends on all five endpoints (T020, T029, T040)
- **Quickstart & Validation (Phase 11)**: Depends on all prior phases
- **Acceptance Checklist (Phase 12)**: Depends on Phase 11

### Within Each Story

- Tests written (and confirmed failing) before the corresponding backend implementation
- Enums → model → migration; config → file helper → unit tests; enums → schemas
- Service (create/list/get/update/delete) → endpoint → router mount
- Frontend: types → API client → page → list → form → detail → route/nav

### Parallel Opportunities

- T004 (enums) unblocks T005 (model) and T011 (schemas)
- T012–T018 (US1 tests), T022–T026 (US2 tests), T030–T037 (US3 tests) can each run in parallel within their group (same file, distinct functions)
- T041 (types) → T042 (API client) feed parallel component work; T045/T049–T052 parallelizable
- T053–T055 (security tests) can run in parallel
- T057 and T058 (test-suite runs) can run in parallel

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Phase 1: Setup & spec alignment (config)
2. Phase 2: DB + model + migration (CRITICAL)
3. Phase 3: file validation/extraction helper + unit tests (the upload boundary — build/test in isolation first)
4. Phase 4: Schemas
5. Phase 5: US1 — create (JSON + multipart) + router mount
6. **STOP and VALIDATE**: run file-helper unit tests + US1 integration tests; confirm tenant scoping, validation, status `uploaded`, client-tenant override ignored
7. Phase 6: US2 — list (filters) + single-document read
8. **STOP and VALIDATE**: tenant-scoped list + read with content — usable corpus MVP

### Incremental Delivery

1. Setup + DB + File helper + Schemas → foundation ready
2. US1 → create via JSON + file (**MVP backend deliverable**)
3. US2 → list/filter + read single (corpus is browsable)
4. US3 → update/disable/delete + processing_pending handoff
5. Frontend → Documents page + components + tests
6. Security + quickstart + acceptance → all 17 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` and `created_by` are **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01, SR-07); any `tenant_id`/`created_by` in the request body/query is ignored
- 404 (document not in tenant) vs 403 (document exists in another tenant) mirrors Specs 005–007 SR-04 via `get_document`
- Enums persist as constrained strings (VARCHAR + app-boundary validation), not native PG enums, for evolvability (data-model.md)
- Content lives in a `TEXT` column for MVP behind a thin storage seam (research.md Decision 1); a later object-store backend can replace it without API changes
- This feature writes `uploaded` (on create + any content edit) and `processing_pending` (manager handoff) only; `processed`/`failed` are owned by the future RAG feature → setting them returns 422 `STATUS_NOT_SETTABLE`
- Any content edit resets status to `uploaded` (AC-10) so stale future-RAG embeddings cannot persist
- `enabled=false` (disable) is reversible and keeps content visible in management; delete is a permanent hard removal of row + content
- The feature performs **no** chunking, embedding, pgvector writes, retrieval, or reply generation (FR-014, AC-16); the only RAG-facing seams are the `status` field and the `enabled` flag
- **Audit logging is out of scope for 008** — it is deferred to the later audit-log feature (013). If a post-action event hook is added, it is a no-op/future-integration stub only; build no audit persistence, API, or UI here
- PDF support is gated behind `DOC_PDF_ENABLED` (default `false`); the MVP baseline is `text/plain` + `text/markdown`
