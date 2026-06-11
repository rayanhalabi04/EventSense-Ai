from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentType
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.audit_log_service import (
    AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL,
    AUDIT_EVENT_RAG_QUERY_EXECUTED,
    AUDIT_EVENT_RAG_RETRIEVAL_RETURNED_SOURCES,
    AuditLogService,
)
from app.services.embedding_service import embedding_service, tokenize_for_retrieval
from app.services.guardrail_service import (
    SAFE_REFUSAL,
    audit_guardrail_event,
    check_input_guardrails,
    check_retrieval_guardrails,
)


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
    enforce_guardrails: bool = True,
) -> RagResult:
    top_k = max(1, min(top_k, 20))
    tenant_slug = await _tenant_slug(session, tenant_id)
    if enforce_guardrails:
        input_result = check_input_guardrails(query, tenant_slug)
        if audit and input_result.flags:
            audit_guardrail_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                rail_type="input",
                result=input_result,
                resource_type="rag_query",
                original_text=query,
            )
        if not input_result.allowed:
            return RagResult(
                query=input_result.sanitized_text or query,
                answer_supported=False,
                sources=[],
                refusal_reason=input_result.reason or SAFE_REFUSAL,
                document_type_filter=None,
            )
        safe_query = input_result.sanitized_text or query
    else:
        safe_query = query

    routed_types = [document_type_filter] if document_type_filter is not None else route_document_types(safe_query)
    if audit:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_RAG_QUERY_EXECUTED,
            resource_type="rag_query",
            details={
                "query": safe_query,
                "top_k": top_k,
                "document_type_filter": [item.value for item in routed_types] if routed_types else None,
            },
        )

    query_embedding = embedding_service.embed_text(safe_query)
    query_tokens = tokenize_for_retrieval(safe_query)
    candidate_limit = min(max(top_k * 5, 20), 100)
    ranked = await DocumentChunkRepository(session).search_similar_chunks(
        tenant_id,
        query_embedding=query_embedding,
        top_k=candidate_limit,
        document_types=routed_types,
    )
    sources = [
        RagSource(
            document_id=scored.chunk.document_id,
            document_title=scored.chunk.document_title,
            document_type=scored.chunk.document_type.value,
            content=scored.chunk.parent_text,
            score=round(scored.score, 6),
            chunk_index=scored.chunk.chunk_index,
            metadata=scored.chunk.chunk_metadata,
        )
        for scored in ranked
        if scored.score >= MIN_RELEVANCE_SCORE
        and query_tokens.intersection(tokenize_for_retrieval(scored.chunk.chunk_text))
    ][:top_k]

    if not sources:
        if audit:
            AuditLogService.record(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type=AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL,
                resource_type="rag_query",
                details={"query": safe_query, "reason": NO_SOURCE_MESSAGE},
            )
        return RagResult(
            query=safe_query,
            answer_supported=False,
            sources=[],
            refusal_reason=NO_SOURCE_MESSAGE,
            document_type_filter=[item.value for item in routed_types] if routed_types else None,
        )

    if enforce_guardrails:
        retrieval_result = check_retrieval_guardrails([source.to_dict() for source in sources], tenant_slug)
        if audit and retrieval_result.result.flags:
            audit_guardrail_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                rail_type="retrieval",
                result=retrieval_result.result,
                resource_type="rag_query",
            )
        if not retrieval_result.result.allowed:
            if audit:
                AuditLogService.record(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    event_type=AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL,
                    resource_type="rag_query",
                    details={"query": safe_query, "reason": retrieval_result.result.reason},
                )
            return RagResult(
                query=safe_query,
                answer_supported=False,
                sources=[],
                refusal_reason=retrieval_result.result.reason or SAFE_REFUSAL,
                document_type_filter=[item.value for item in routed_types] if routed_types else None,
            )
        sources = [_rag_source_from_dict(source) for source in retrieval_result.sources]

    if audit:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_RAG_RETRIEVAL_RETURNED_SOURCES,
            resource_type="rag_query",
            details={
                "query": safe_query,
                "source_count": len(sources),
                "document_ids": [source.document_id for source in sources],
            },
        )
    return RagResult(
        query=safe_query,
        answer_supported=True,
        sources=sources,
        document_type_filter=[item.value for item in routed_types] if routed_types else None,
    )


async def _tenant_slug(session: AsyncSession, tenant_id: UUID) -> str | None:
    return await TenantRepository(session).get_slug(tenant_id)


def _rag_source_from_dict(source: dict[str, object]) -> RagSource:
    return RagSource(
        document_id=UUID(str(source["document_id"])),
        document_title=str(source["document_title"]),
        document_type=str(source["document_type"]),
        content=str(source["content"]),
        score=float(source["score"]),
        chunk_index=int(source["chunk_index"]),
        metadata=dict(source.get("metadata") or {}),
    )
