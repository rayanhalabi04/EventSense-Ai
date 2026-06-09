# Research: Document Upload

**Branch**: `008-document-upload` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Store Content in the Database (TEXT column) for MVP

**Decision**: Store document content directly in a `TEXT` column on the `documents` table. File uploads are read/extracted at request time and the resulting text is stored in the same column. The API contract is kept storage-agnostic.

**Rationale**:
- MVP documents are small text/markdown business docs (policies, FAQs, packages) — well within comfortable row sizes.
- One store (Postgres) means transactional create/update/delete with the metadata, no second system to keep consistent, and trivial tenant scoping (the `tenant_id` filter already protects content).
- The future RAG pipeline reads `content` directly to chunk + embed — no file fetch indirection.

**Alternatives considered**:
- Object storage (S3/MinIO) + pointer column: better for large binaries, but adds infra, a consistency seam, and signed-URL handling not justified at demo scale. The service keeps a thin storage seam so this can be swapped later without API changes.
- Filesystem storage: not multi-tenant-safe or portable across deployments; rejected.

---

## Decision 2: Text/Markdown First; PDF Optional via Text Extraction

**Decision**: Support `text/plain` and `text/markdown` as the MVP baseline (paste or file). Allow `application/pdf` behind a `DOC_PDF_ENABLED` flag; when enabled, extract text at upload and store the extracted text as `content`. PDFs with no extractable text are rejected (422), never stored empty.

**Rationale**:
- The corpus is plain business text; markdown preserves light structure RAG can use later.
- PDF is common for policies, so optional support is valuable — but only as extracted text, since RAG consumes text, not binaries.
- Rejecting empty-extraction PDFs prevents silently storing useless documents (a real failure mode for scanned/image PDFs).

**Alternatives considered**:
- `.docx`/images/spreadsheets: heavier parsing, OCR, format variance — out of scope. Text/markdown (+ simple PDF) covers MVP.
- Storing the raw PDF binary: useless to RAG without extraction and bloats the row; rejected (store extracted text).

---

## Decision 3: Status Lifecycle Split Between This Feature and RAG

**Decision**: `DocumentStatus` = `uploaded → processing_pending → processed → failed`. This feature writes `uploaded` (on create and on any content edit) and lets a manager set `processing_pending` (handoff). The future RAG feature owns `processed`/`failed`.

**Rationale**:
- Clean ownership boundary: this feature prepares + curates; RAG processes. Storing the full enum now means RAG slots in without a schema change.
- Resetting to `uploaded` on content edit guarantees stale embeddings can't persist — RAG must re-process changed content.

**Alternatives considered**:
- Only `uploaded`/`pending` here: would force a migration when RAG arrives; storing the full lifecycle now is cheaper and forward-compatible.
- Auto-advancing to `processing_pending` on create: premature — managers should curate first and decide what to send to RAG.

---

## Decision 4: Role Split — Manager Writes, Staff Read-Only

**Decision**: `manager` may create/update/disable/delete and set status; `staff` may list/view only; Platform Admin is blocked. Enforced via `require_role` per HTTP method.

**Rationale**:
- The feature goal designates managers as the document owners; staff benefit from reading the corpus but should not mutate the agency's source-of-truth documents.
- Per-method role guards keep reads broad and writes narrow without a separate permission system.

**Alternatives considered**:
- Staff can also write: contradicts the stated ownership model; rejected (can be relaxed later if needed).
- Manager-only (no staff read): unnecessarily restrictive; staff reading documents is useful and harmless within the tenant.

---

## Decision 5: Tenant Scoping + 404-vs-403 Consistency

**Decision**: `tenant_id` and `created_by` always come from the JWT. Every single-document operation resolves the document by id and applies the Specs 005–007 pattern: not found → 404; exists in another tenant → 403. List queries are unconditionally `WHERE tenant_id = :jwt_tenant`.

**Rationale**:
- Reuses the established, audited cross-tenant contract — no new security model.
- Deriving `created_by`/`tenant_id` from the session makes spoofing impossible (SR-01, SR-07).

---

## Decision 6: Validation Limits (server-side, configurable)

**Decision**: Enforce server-side: title length ≤ 200; content ≤ ~1 MB; file ≤ ~5 MB; MIME allowlist (`text/plain`, `text/markdown`, optional `application/pdf`); non-empty title + content. Limits are configurable via settings.

**Rationale**:
- Bounds protect storage and the future RAG pipeline from pathological inputs.
- Server-side enforcement (not just client) is the security boundary (SR-05); the frontend mirrors limits as hints only.

**Resolved defaults**:

| Setting | Default | Purpose |
|---------|---------|---------|
| `DOC_MAX_TITLE_LEN` | `200` | Title length cap |
| `DOC_MAX_CONTENT_BYTES` | `1_048_576` (1 MB) | Stored content cap |
| `DOC_MAX_FILE_BYTES` | `5_242_880` (5 MB) | Upload size cap |
| `DOC_ALLOWED_MIME` | `text/plain, text/markdown` (+ `application/pdf` if enabled) | Upload allowlist |
| `DOC_PDF_ENABLED` | `false` | Toggle PDF extraction |

---

## Decision 7: Disable (soft) vs Delete (hard)

**Decision**: `enabled` boolean controls inclusion in future RAG processing; disabling keeps the document and content and remains visible in management. Delete is a hard removal of the row + content.

**Rationale**:
- Managers often want to temporarily exclude a doc (e.g., outdated promo) without losing it — disable is reversible.
- Hard delete is needed for genuinely obsolete documents and keeps the corpus clean. No version history is kept for MVP (last-write-wins).

**Alternatives considered**:
- Soft-delete only (no hard delete): leaves clutter and complicates "remove permanently"; both are offered.
- Versioned documents: useful but out of scope; `updated_at` + last-write-wins suffices for MVP.

---

## Decision 8: Two Create Paths, One Service

**Decision**: Accept both a JSON body (pasted `content`) and a multipart file upload on `POST /api/documents`; both converge on `DocumentService.create_document` after the file path runs through the extraction/validation helper.

**Rationale**:
- Managers will both paste short text and upload existing files; supporting both with one storage path avoids divergent logic and keeps validation centralised.

---

## Decision 9: No Chunking, Embeddings, or Retrieval Here

**Decision**: This feature produces only plain text + metadata + status. It performs no chunking, no embedding, no pgvector writes, and exposes no retrieval/search endpoint.

**Rationale**:
- Explicit scope boundary. Keeping document curation separate from RAG processing means the corpus can be managed independently of model/embedding concerns, and the RAG feature can evolve (re-chunk, re-embed, change models) without touching document CRUD.
- The `processing_pending` status + `enabled` flag are the only seams RAG needs; AC-16 asserts the absence of RAG work here.

---

## Decision 10: Demo Seed Strategy for the Two Tenants

**Decision**: The quickstart seeds Elegant Weddings and Royal Events Agency with distinct example documents (Premium/Luxury packages, deposit/refund, cancellation/catering, decoration/bridal-entrance rules) to demonstrate tenant isolation concretely.

**Rationale**:
- Two tenants with parallel-but-distinct documents make cross-tenant leakage immediately testable (listing in one must never show the other's docs) and mirror the project's established demo tenants.
