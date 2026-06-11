from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import UserRole
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate, DocumentUpload
from app.services.document_service import DocumentService, MAX_UPLOAD_BYTES


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


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    title: str | None = Form(None),
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> Document:
    filename = file.filename or ""
    if not filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid file type: only .txt files are supported",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"file too large: maximum size is {MAX_UPLOAD_BYTES} bytes",
        )
    try:
        content_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploaded .txt file must be UTF-8 text",
        ) from exc

    return await DocumentService(session).upload_txt_document(
        DocumentUpload(
            filename=filename,
            document_type=document_type,
            title=title,
            content_text=content_text,
        ),
        ctx,
    )


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
