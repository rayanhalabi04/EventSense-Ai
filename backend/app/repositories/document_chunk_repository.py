from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import bindparam, delete, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus, DocumentType


@dataclass(frozen=True)
class ScoredDocumentChunk:
    chunk: DocumentChunk
    score: float
    retrieval_backend: str


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

    async def search_similar_chunks(
        self,
        tenant_id: UUID,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
    ) -> list[ScoredDocumentChunk]:
        if self.session.get_bind().dialect.name == "postgresql":
            return await self.search_similar_chunks_pgvector(
                tenant_id,
                query_embedding=query_embedding,
                top_k=top_k,
                document_types=document_types,
            )
        return await self.search_similar_chunks_fallback(
            tenant_id,
            query_embedding=query_embedding,
            top_k=top_k,
            document_types=document_types,
        )

    async def search_similar_chunks_pgvector(
        self,
        tenant_id: UUID,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
    ) -> list[ScoredDocumentChunk]:
        distance = DocumentChunk.embedding.op("<=>")(
            bindparam("query_embedding", query_embedding, type_=DocumentChunk.embedding.type)
        )
        stmt = (
            select(DocumentChunk, (literal(1.0) - distance).label("score"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                Document.status == DocumentStatus.active,
            )
            .order_by(distance)
            .limit(top_k)
        )
        if document_types:
            stmt = stmt.where(DocumentChunk.document_type.in_(document_types))

        result = await self.session.execute(stmt)
        return [
            ScoredDocumentChunk(chunk=chunk, score=float(score), retrieval_backend="pgvector_sql")
            for chunk, score in result.all()
        ]

    async def search_similar_chunks_fallback(
        self,
        tenant_id: UUID,
        *,
        query_embedding: list[float],
        top_k: int,
        document_types: list[DocumentType] | None = None,
    ) -> list[ScoredDocumentChunk]:
        chunks = await self.list_active_chunks(tenant_id, document_types=document_types)
        ranked = sorted(
            (
                ScoredDocumentChunk(
                    chunk=chunk,
                    score=_cosine_similarity(query_embedding, chunk.embedding),
                    retrieval_backend="python_cosine_fallback",
                )
                for chunk in chunks
                if chunk.embedding is not None
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:top_k]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
