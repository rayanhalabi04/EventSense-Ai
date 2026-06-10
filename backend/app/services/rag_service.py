import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus, DocumentType
from app.services.audit_log_service import (
    AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL,
    AUDIT_EVENT_RAG_QUERY_EXECUTED,
    AUDIT_EVENT_RAG_RETRIEVAL_RETURNED_SOURCES,
    AuditLogService,
)
from app.services.embedding_service import embedding_service, tokenize_for_retrieval


NO_SOURCE_MESSAGE = "I could not find supporting information in the uploaded tenant documents."
MIN_RELEVANCE_SCORE = 0.08


@dataclass(frozen=True)
class RagSource:
    document_id: UUID
    document_title: str
    document_type: str
    content: str
    score: float
    chunk_index: int
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": str(self.document_id),
            "document_title": self.document_title,
            "document_type": self.document_type,
            "content": self.content,
            "score": self.score,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RagResult:
    query: str
    answer_supported: bool
    sources: list[RagSource]
    refusal_reason: str | None = None
    document_type_filter: list[str] | None = None


def route_document_types(query: str) -> list[DocumentType] | None:
    text = query.lower()
    if any(word in text for word in ("price", "pricing", "package", "cost", "rate", "inclusion")):
        return [DocumentType.pricing, DocumentType.package]
    if any(word in text for word in ("deposit", "payment", "paid", "pay", "installment")):
        return [DocumentType.deposit_policy, DocumentType.contract_terms]
    if any(word in text for word in ("cancel", "cancellation", "refund", "refundable")):
        return [DocumentType.cancellation_policy, DocumentType.contract_terms]
    if any(word in text for word in ("service", "include", "offer", "provide", "faq")):
        return [DocumentType.service_description, DocumentType.faq]
    return None


async def retrieve(
    session: AsyncSession,
    *,
    query: str,
    tenant_id: UUID,
    top_k: int = 5,
    document_type_filter: DocumentType | None = None,
    actor_user_id: UUID | None = None,
    audit: bool = True,
) -> RagResult:
    top_k = max(1, min(top_k, 20))
    routed_types = [document_type_filter] if document_type_filter is not None else route_document_types(query)
    if audit:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_RAG_QUERY_EXECUTED,
            resource_type="rag_query",
            details={
                "query": query,
                "top_k": top_k,
                "document_type_filter": [item.value for item in routed_types] if routed_types else None,
            },
        )

    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.tenant_id == tenant_id, Document.status == DocumentStatus.active)
    )
    if routed_types:
        stmt = stmt.where(DocumentChunk.document_type.in_(routed_types))

    chunks = list((await session.execute(stmt)).scalars().all())
    query_embedding = embedding_service.embed_text(query)
    query_tokens = tokenize_for_retrieval(query)
    ranked = sorted(
        (
            (_cosine_similarity(query_embedding, chunk.embedding), chunk)
            for chunk in chunks
            if chunk.embedding is not None
            and query_tokens.intersection(tokenize_for_retrieval(chunk.chunk_text))
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    sources = [
        RagSource(
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            document_type=chunk.document_type.value,
            content=chunk.parent_text,
            score=round(score, 6),
            chunk_index=chunk.chunk_index,
            metadata=chunk.chunk_metadata,
        )
        for score, chunk in ranked[:top_k]
        if score >= MIN_RELEVANCE_SCORE
    ]

    if not sources:
        if audit:
            AuditLogService.record(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type=AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL,
                resource_type="rag_query",
                details={"query": query, "reason": NO_SOURCE_MESSAGE},
            )
        return RagResult(
            query=query,
            answer_supported=False,
            sources=[],
            refusal_reason=NO_SOURCE_MESSAGE,
            document_type_filter=[item.value for item in routed_types] if routed_types else None,
        )

    if audit:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_RAG_RETRIEVAL_RETURNED_SOURCES,
            resource_type="rag_query",
            details={
                "query": query,
                "source_count": len(sources),
                "document_ids": [source.document_id for source in sources],
            },
        )
    return RagResult(
        query=query,
        answer_supported=True,
        sources=sources,
        document_type_filter=[item.value for item in routed_types] if routed_types else None,
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
