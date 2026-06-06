# Requirements Checklist: Document Upload

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (curating the RAG corpus) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Manager can create a document with title, type, and text content scoped to their tenant (FR-001)
- [ ] Stored metadata includes title, document_type, tenant_id, status, enabled, created_by, created_at, updated_at, content, source file fields (FR-002)
- [ ] New documents are created with status `uploaded` (FR-003)
- [ ] Text/markdown content supported; simple PDF text extraction optional (FR-004)
- [ ] Type, title, content, and file type/size are validated (FR-005)
- [ ] Manager can list (with type/status filters) and fetch a single document with content (FR-006)
- [ ] Staff can list/view but cannot create/update/disable/delete (FR-007, AC-04)
- [ ] Manager can update title/type/content; content change resets status to `uploaded` (FR-008, AC-10)
- [ ] Manager can disable (exclude from RAG) without deleting, and re-enable (FR-009, AC-11)
- [ ] Manager can delete a document and its content (FR-010, AC-12)
- [ ] Manager can mark a document `processing_pending` (FR-011, AC-13)
- [ ] All operations are tenant-scoped; cross-tenant access blocked (FR-012)
- [ ] Manager can only manage their own tenant's documents (tenant from JWT) (FR-013, AC-15)
- [ ] Feature performs no chunking, embedding, or retrieval (FR-014, AC-16)
- [ ] `created_by` + timestamps recorded and maintained (FR-015)

---

## Security Requirements

- [ ] `tenant_id` is always derived from the JWT — never from the client (SR-01)
- [ ] A document belongs to exactly one tenant (SR-02)
- [ ] Only `manager` may write; `staff` read-only; Platform Admin → 403 (SR-03, AC-04, AC-14)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent document → 404; cross-tenant document → 403 (SR-04, AC-08)
- [ ] File type/size, title length, content size/non-emptiness validated server-side before storage (SR-05, AC-02, AC-17)
- [ ] Stored content is partitioned by tenant; retrieval always carries the tenant filter (SR-06)
- [ ] `created_by` is the authenticated manager; cannot be spoofed (SR-07)

---

## Tenant Isolation Requirements

- [ ] Listing returns only the caller's tenant documents (AC-03, AC-05)
- [ ] Tenant A cannot read a Tenant B document by id (403) (AC-08)
- [ ] Tenant A cannot update/disable/delete a Tenant B document (404/403)
- [ ] A client-supplied `tenant_id` in body/query is ignored (AC-15)
- [ ] Demo: Elegant Weddings and Royal Events Agency each see only their own four documents
- [ ] No shared/cross-tenant document concept exists

---

## API Requirements

- [ ] `POST /api/documents` creates via JSON content or multipart file (201) (AC-01)
- [ ] `POST` rejects invalid title/type/content (422) and bad file type/size (422) (AC-02, AC-17)
- [ ] `GET /api/documents` lists tenant documents with type/status/enabled filters (AC-05, AC-06)
- [ ] `GET /api/documents/{id}` returns metadata + content (AC-07); 404/403 for missing/cross-tenant (AC-08)
- [ ] `PATCH /api/documents/{id}` updates fields; content change resets status (AC-09, AC-10)
- [ ] `PATCH` rejects setting `processed`/`failed` (422 STATUS_NOT_SETTABLE)
- [ ] `DELETE /api/documents/{id}` removes document; subsequent GET 404 (AC-12)
- [ ] Writes require `manager`; reads allow `manager`+`staff`; Platform Admin → 403 (role matrix)
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] List items are metadata-only (no content); single GET returns content

---

## Data Requirements

- [ ] `documents` table created via Alembic migration
- [ ] `tenant_id` FK + index; `created_by` FK → users
- [ ] `DocumentType` enum has exactly the ten specified types
- [ ] `DocumentStatus` enum: `uploaded`, `processing_pending`, `processed`, `failed`
- [ ] `status` defaults to `uploaded`; `enabled` defaults to true
- [ ] `content` NOT NULL; `source_filename`/`source_mime`/`content_bytes` populated for file uploads
- [ ] Titles not unique within a tenant
- [ ] Indexes on `(tenant_id, document_type)`, `(tenant_id, status)`, `(tenant_id, enabled)`
- [ ] `created_at`/`updated_at` maintained; `updated_at` refreshes on change
- [ ] State transitions: this feature writes `uploaded`/`processing_pending`; RAG owns `processed`/`failed`

---

## Testing Requirements

- [ ] Unit: MIME/extension allowlist, size cap, UTF-8 decode failure, PDF empty-text rejection, content-size bound
- [ ] Integration: manager create + stored fields (AC-01); validation rejections (AC-02, AC-17)
- [ ] Integration: tenant isolation list/get/cross-tenant (AC-03, AC-05, AC-08)
- [ ] Integration: staff read-only + staff write 403 (AC-04)
- [ ] Integration: list filters (AC-06); get with content (AC-07)
- [ ] Integration: update + updated_at (AC-09); content edit resets status (AC-10)
- [ ] Integration: disable/enable (AC-11); delete → 404 (AC-12); mark processing_pending (AC-13)
- [ ] Integration: Platform Admin 403 (AC-14); tenant override ignored (AC-15)
- [ ] Integration: no chunk/embed/retrieve side effects (AC-16)
- [ ] Frontend: list shows tenant docs; manager sees write controls, staff does not; 422 surfaced; delete confirms
- [ ] Quickstart: two demo tenants with their example documents, isolation verified

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No RAG retrieval / semantic search
- [ ] No chunking
- [ ] No embeddings / pgvector indexing
- [ ] No suggested reply generation
- [ ] No advancing status to `processed`/`failed` (RAG-owned)
- [ ] No audit-log system (logging added by the later audit feature)
- [ ] No document versioning / revision history
- [ ] No rich file types (`.docx`, images, spreadsheets); no OCR
- [ ] No cross-tenant document sharing
- [ ] No real WhatsApp API, no calendar syncing, no full CRM

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build the file-extraction helper and service before wiring the API.
