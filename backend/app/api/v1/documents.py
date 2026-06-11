from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import UserRole
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.services.document_service import DocumentService


router = APIRouter()


async def get_tenant_document_or_403(
    document_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Document:
    return await DocumentService(session).get_tenant_document_or_403(document_id, ctx)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    return await DocumentService(session).create_document(payload, ctx)


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
    return await DocumentService(session).list_documents(
        ctx,
        document_type=document_type,
        status=status,
        search=search,
    )


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
    return await DocumentService(session).update_document(document_id, payload, ctx)


@router.delete("/{document_id}", response_model=DocumentRead)
async def archive_document(
    document_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    return await DocumentService(session).archive_document(document_id, ctx)
