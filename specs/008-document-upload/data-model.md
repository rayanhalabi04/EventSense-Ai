# Data Model: Document Upload

**Branch**: `008-document-upload` | **Phase**: 1 — Design

---

## Schema Changes

**One new table**: `documents`. One new Alembic migration. No changes to existing `tenants` or `users` tables — the new table references them via FKs.

---

## Enums

### `DocumentType`

```python
class DocumentType(str, Enum):
    pricing_packages    = "pricing_packages"
    wedding_packages    = "wedding_packages"
    faq                 = "faq"
    contract_terms      = "contract_terms"
    deposit_policy      = "deposit_policy"
    cancellation_policy = "cancellation_policy"
    service_description = "service_description"
    decoration_rules    = "decoration_rules"
    catering_rules      = "catering_rules"
    other               = "other"
```

### `DocumentStatus`

```python
class DocumentStatus(str, Enum):
    uploaded           = "uploaded"            # content stored; not queued
    processing_pending = "processing_pending"  # manager handed off to future RAG pipeline
    processed          = "processed"           # set by future RAG feature
    failed             = "failed"              # set by future RAG feature
```

**State transitions**:

```
            create / content edit
(none) ─────────────────────────▶ uploaded
                                     │  manager marks handoff
                                     ▼
                              processing_pending
                                     │  (FUTURE RAG feature)
                          ┌──────────┴──────────┐
                          ▼                     ▼
                      processed              failed
                          │  content edit (this feature)
                          └──────────────▶ uploaded   (resets; stale embeddings invalidated)
```

- This feature writes `uploaded` (create + content edit) and `processing_pending` (manager handoff).
- `processed`/`failed` are written only by the future RAG feature.
- Any content edit (this feature) resets status to `uploaded` regardless of prior state.

---

## Existing Entities Used

### `tenants` (Spec 001)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | `documents.tenant_id` FK; scopes every operation |

### `users` (Spec 002)

| Column | Type | Used for |
|--------|------|----------|
| `id` | UUID | `documents.created_by` FK (attribution) |
| `role` | ENUM | `manager` (write) vs `staff` (read-only) gating |
| `tenant_id` | UUID | Must match the document's tenant |

---

## New Entity: `Document`

### Table `documents`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes all access |
| `title` | VARCHAR(200) | NOT NULL | not unique within a tenant |
| `document_type` | VARCHAR(40) | NOT NULL | one of `DocumentType` |
| `content` | TEXT | NOT NULL | stored text (pasted or extracted) |
| `status` | VARCHAR(20) | NOT NULL, default `uploaded` | one of `DocumentStatus` |
| `enabled` | BOOLEAN | NOT NULL, default true | false = excluded from future RAG processing |
| `source_filename` | VARCHAR(255) | NULL | original filename for file uploads |
| `source_mime` | VARCHAR(100) | NULL | original MIME for file uploads |
| `content_bytes` | INTEGER | NULL | byte size of stored content |
| `created_by` | UUID | NOT NULL, FK → `users.id` | authenticated manager |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now, on update now | |

### Indexes

- `INDEX (tenant_id, document_type)` — filtered listing by type.
- `INDEX (tenant_id, status)` — filtered listing by status + future "find processing_pending".
- `INDEX (tenant_id, enabled)` — future RAG "find enabled, pending" query.

### SQLAlchemy model (`backend/app/models/document.py`)

```python
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship()
    creator: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_documents_tenant_type", "tenant_id", "document_type"),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_tenant_enabled", "tenant_id", "enabled"),
    )
```

---

## Pydantic Schemas (`backend/app/schemas/document.py`)

```python
class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    document_type: DocumentType
    content: str | None = Field(default=None)   # required for JSON path; file path supplies content
    # (multipart file is handled separately by the route via UploadFile)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be blank")
        return v.strip()


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    document_type: DocumentType | None = None
    content: str | None = None
    enabled: bool | None = None
    status: DocumentStatus | None = None        # manager may set processing_pending only

    @field_validator("status")
    @classmethod
    def status_manager_settable(cls, v):
        # service enforces: only `processing_pending` (or back to uploaded) is settable here;
        # processed/failed are owned by the RAG feature -> 422 if a client sets them.
        return v


class DocumentListItem(BaseModel):
    id: UUID
    title: str
    document_type: DocumentType
    status: DocumentStatus
    enabled: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(DocumentListItem):
    content: str
    source_filename: str | None
    source_mime: str | None
    content_bytes: int | None
```

---

## Service Logic (`backend/app/services/document_service.py`)

```python
async def create_document(session, tenant_id, user, *, title, document_type, content,
                          source_filename=None, source_mime=None) -> Document:
    _validate_content(content)                         # non-empty, <= DOC_MAX_CONTENT_BYTES -> 422
    doc = Document(
        tenant_id=tenant_id,                           # from JWT (SR-01)
        title=title, document_type=document_type.value,
        content=content, status=DocumentStatus.uploaded.value, enabled=True,
        source_filename=source_filename, source_mime=source_mime,
        content_bytes=len(content.encode("utf-8")),
        created_by=user.id,                            # from JWT (SR-07)
    )
    session.add(doc)
    await session.commit()
    return doc


async def list_documents(session, tenant_id, *, document_type=None, status=None, enabled=None) -> list[Document]:
    stmt = select(Document).where(Document.tenant_id == tenant_id)        # SR-02
    if document_type: stmt = stmt.where(Document.document_type == document_type.value)
    if status:        stmt = stmt.where(Document.status == status.value)
    if enabled is not None: stmt = stmt.where(Document.enabled == enabled)
    stmt = stmt.order_by(Document.updated_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def get_document(session, tenant_id, document_id) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError()                          # 404 DOCUMENT_NOT_FOUND
    if doc.tenant_id != tenant_id:
        raise ForbiddenError()                         # 403 CROSS_TENANT_FORBIDDEN
    return doc


async def update_document(session, tenant_id, document_id, data) -> Document:
    doc = await get_document(session, tenant_id, document_id)             # 404/403
    if data.title is not None:        doc.title = data.title.strip()
    if data.document_type is not None: doc.document_type = data.document_type.value
    if data.enabled is not None:      doc.enabled = data.enabled
    if data.status is not None:
        _assert_manager_settable_status(data.status)   # processed/failed -> 422
        doc.status = data.status.value
    if data.content is not None:
        _validate_content(data.content)
        doc.content = data.content
        doc.content_bytes = len(data.content.encode("utf-8"))
        doc.status = DocumentStatus.uploaded.value      # content change resets status (AC-10)
    await session.commit()
    return doc


async def delete_document(session, tenant_id, document_id) -> None:
    doc = await get_document(session, tenant_id, document_id)             # 404/403
    await session.delete(doc)
    await session.commit()
```

### File validation + extraction (`backend/app/files/extract.py`)

```python
def extract_text(upload) -> tuple[str, str, str]:
    """Returns (content, filename, mime). Raises typed 422 errors."""
    if upload.content_type not in settings.DOC_ALLOWED_MIME:
        raise UnsupportedFileType()                     # 422 UNSUPPORTED_FILE_TYPE
    raw = upload.file.read()
    if len(raw) > settings.DOC_MAX_FILE_BYTES:
        raise FileTooLarge()                            # 422 FILE_TOO_LARGE
    if upload.content_type == "application/pdf":
        if not settings.DOC_PDF_ENABLED:
            raise UnsupportedFileType()
        text = pdf_to_text(raw)                          # lightweight extractor
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise UnsupportedFileType()
    if not text.strip():
        raise EmptyDocumentContent()                    # 422 EMPTY_DOCUMENT_CONTENT
    return text, upload.filename, upload.content_type
```

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` | 404 | `DOCUMENT_NOT_FOUND` |
| `ForbiddenError` | 403 | `CROSS_TENANT_FORBIDDEN` |
| `UnsupportedFileType` | 422 | `UNSUPPORTED_FILE_TYPE` |
| `FileTooLarge` | 422 | `FILE_TOO_LARGE` |
| `EmptyDocumentContent` | 422 | `EMPTY_DOCUMENT_CONTENT` |
| invalid type/title/content/status | 422 | validation detail |
| (role guard, staff write or admin) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/document.ts`)

```typescript
type DocumentType =
  | "pricing_packages" | "wedding_packages" | "faq" | "contract_terms"
  | "deposit_policy" | "cancellation_policy" | "service_description"
  | "decoration_rules" | "catering_rules" | "other";

type DocumentStatus = "uploaded" | "processing_pending" | "processed" | "failed";

interface DocumentListItem {
  id: string;
  title: string;
  document_type: DocumentType;
  status: DocumentStatus;
  enabled: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface Document extends DocumentListItem {
  content: string;
  source_filename: string | null;
  source_mime: string | null;
  content_bytes: number | null;
}
```
