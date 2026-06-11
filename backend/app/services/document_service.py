from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.document import Document, DocumentStatus, DocumentType
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_DOCUMENT_ARCHIVED,
    AUDIT_EVENT_DOCUMENT_CREATED,
    AUDIT_EVENT_DOCUMENT_UPDATED,
    AuditLogService,
)
from app.services.document_chunking_service import rebuild_document_chunks


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.documents = DocumentRepository(session)

    async def get_tenant_document_or_403(
        self,
        document_id: UUID,
        ctx: TenantContext,
    ) -> Document:
        document = await self.documents.get(document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
        if document.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return document

    async def create_document(self, payload: DocumentCreate, ctx: TenantContext) -> Document:
        document = Document(
            tenant_id=ctx.tenant_id,
            title=payload.title,
            document_type=payload.document_type,
            original_filename=payload.original_filename,
            content_text=payload.content_text,
            status=payload.status,
            uploaded_by_user_id=ctx.user_id,
        )
        await self.documents.add(document)
        await rebuild_document_chunks(self.session, document, actor_user_id=ctx.user_id)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_DOCUMENT_CREATED,
            resource_type="document",
            resource_id=document.id,
            details=_audit_details(document, ctx.user_id),
        )
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def list_documents(
        self,
        ctx: TenantContext,
        *,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        search: str | None = None,
    ) -> list[Document]:
        return await self.documents.list(
            ctx.tenant_id,
            document_type=document_type,
            status=status,
            search=search,
        )

    async def update_document(
        self,
        document_id: UUID,
        payload: DocumentUpdate,
        ctx: TenantContext,
    ) -> Document:
        document = await self.get_tenant_document_or_403(document_id, ctx)

        for field in ("title", "document_type", "content_text", "status"):
            if field in payload.model_fields_set:
                setattr(document, field, getattr(payload, field))
        await self.session.flush()
        await rebuild_document_chunks(self.session, document, actor_user_id=ctx.user_id)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_DOCUMENT_UPDATED,
            resource_type="document",
            resource_id=document.id,
            details=_audit_details(document, ctx.user_id),
        )
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def archive_document(self, document_id: UUID, ctx: TenantContext) -> Document:
        document = await self.get_tenant_document_or_403(document_id, ctx)
        old_status = document.status
        document.status = DocumentStatus.archived
        await self.session.flush()
        await rebuild_document_chunks(self.session, document, actor_user_id=ctx.user_id)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_DOCUMENT_ARCHIVED,
            resource_type="document",
            resource_id=document.id,
            details={
                **_audit_details(document, ctx.user_id),
                "old_status": old_status,
                "new_status": document.status,
            },
        )
        await self.session.commit()
        await self.session.refresh(document)
        return document


def _audit_details(document: Document, actor_user_id: UUID) -> dict[str, object]:
    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "title": document.title,
        "actor_user_id": actor_user_id,
    }
