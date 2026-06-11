from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus, DocumentType


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_for_document(self, tenant_id: UUID, document_id: UUID) -> None:
        await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id == document_id,
            )
        )

    def add_all(self, chunks: list[DocumentChunk]) -> None:
        self.session.add_all(chunks)

    async def list_active_chunks(
        self,
        tenant_id: UUID,
        *,
        document_types: list[DocumentType] | None = None,
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.tenant_id == tenant_id, Document.status == DocumentStatus.active)
        )
        if document_types:
            stmt = stmt.where(DocumentChunk.document_type.in_(document_types))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
