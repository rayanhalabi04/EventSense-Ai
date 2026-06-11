from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def list(
        self,
        tenant_id: UUID,
        *,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        search: str | None = None,
    ) -> list[Document]:
        stmt = select(Document).where(Document.tenant_id == tenant_id)
        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if search is not None and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Document.title.ilike(term), Document.content_text.ilike(term)))

        result = await self.session.execute(
            stmt.order_by(Document.created_at.desc(), Document.id.desc())
        )
        return list(result.scalars().all())

    async def add(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document
