from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import UserRole
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_DOCUMENT_ARCHIVED,
    AUDIT_EVENT_DOCUMENT_CREATED,
    AUDIT_EVENT_DOCUMENT_UPDATED,
    AuditLogService,
)
from app.services.document_chunking_service import rebuild_document_chunks


router = APIRouter()


async def get_tenant_document_or_403(
    document_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    if document.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return document


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    document = Document(
        tenant_id=ctx.tenant_id,
        title=payload.title,
        document_type=payload.document_type,
        original_filename=payload.original_filename,
        content_text=payload.content_text,
        status=payload.status,
        uploaded_by_user_id=ctx.user_id,
    )
    session.add(document)
    await session.flush()
    await rebuild_document_chunks(session, document, actor_user_id=ctx.user_id)

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_DOCUMENT_CREATED,
        resource_type="document",
        resource_id=document.id,
        details=_audit_details(document, ctx.user_id),
    )
    await session.commit()
    await session.refresh(document)
    return document


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    document_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    search: str | None = None,
    ctx: TenantContext = Depends(
        require_role(UserRole.staff, UserRole.manager, UserRole.platform_admin)
    ),
    session: AsyncSession = Depends(get_async_session),
) -> list[Document]:
    stmt = select(Document).where(Document.tenant_id == ctx.tenant_id)
    if document_type is not None:
        stmt = stmt.where(Document.document_type == document_type)
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if search is not None and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Document.title.ilike(term), Document.content_text.ilike(term)))

    result = await session.execute(stmt.order_by(Document.created_at.desc(), Document.id.desc()))
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    ctx: TenantContext = Depends(
        require_role(UserRole.staff, UserRole.manager, UserRole.platform_admin)
    ),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    return await get_tenant_document_or_403(document_id, ctx, session)


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    document = await get_tenant_document_or_403(document_id, ctx, session)

    for field in ("title", "document_type", "content_text", "status"):
        if field in payload.model_fields_set:
            setattr(document, field, getattr(payload, field))
    await session.flush()
    await rebuild_document_chunks(session, document, actor_user_id=ctx.user_id)

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_DOCUMENT_UPDATED,
        resource_type="document",
        resource_id=document.id,
        details=_audit_details(document, ctx.user_id),
    )
    await session.commit()
    await session.refresh(document)
    return document


@router.delete("/{document_id}", response_model=DocumentRead)
async def archive_document(
    document_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    document = await get_tenant_document_or_403(document_id, ctx, session)
    old_status = document.status
    document.status = DocumentStatus.archived
    await session.flush()
    await rebuild_document_chunks(session, document, actor_user_id=ctx.user_id)

    AuditLogService.record(
        session,
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
    await session.commit()
    await session.refresh(document)
    return document


def _audit_details(document: Document, actor_user_id: UUID) -> dict[str, object]:
    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "title": document.title,
        "actor_user_id": actor_user_id,
    }
