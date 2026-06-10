from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.audit_log_service import (
    AUDIT_EVENT_DOCUMENT_CHUNKED_INDEXED,
    AuditLogService,
)
from app.services.embedding_service import embedding_service


PARENT_CHUNK_SIZE = 1800
CHILD_CHUNK_SIZE = 550
CHUNK_OVERLAP = 120


def split_text(text: str, *, size: int, overlap: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


async def rebuild_document_chunks(
    session: AsyncSession,
    document: Document,
    *,
    actor_user_id: UUID | None = None,
) -> int:
    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.tenant_id == document.tenant_id,
            DocumentChunk.document_id == document.id,
        )
    )
    if document.status == DocumentStatus.archived:
        chunk_count = 0
    else:
        chunk_count = _add_chunks(session, document)

    AuditLogService.record(
        session,
        tenant_id=document.tenant_id,
        actor_user_id=actor_user_id,
        event_type=AUDIT_EVENT_DOCUMENT_CHUNKED_INDEXED,
        resource_type="document",
        resource_id=document.id,
        details={
            "document_id": document.id,
            "document_type": document.document_type,
            "title": document.title,
            "chunk_count": chunk_count,
        },
    )
    return chunk_count


def _add_chunks(session: AsyncSession, document: Document) -> int:
    rows: list[DocumentChunk] = []
    global_child_index = 0
    for parent_index, parent_text in enumerate(
        split_text(document.content_text, size=PARENT_CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    ):
        parent_chunk_id = uuid4()
        child_texts = split_text(parent_text, size=CHILD_CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        embeddings = embedding_service.embed_batch(child_texts)
        for child_text, embedding in zip(child_texts, embeddings, strict=True):
            rows.append(
                DocumentChunk(
                    tenant_id=document.tenant_id,
                    document_id=document.id,
                    parent_chunk_id=parent_chunk_id,
                    chunk_text=child_text,
                    parent_text=parent_text,
                    chunk_index=global_child_index,
                    parent_chunk_index=parent_index,
                    document_title=document.title,
                    document_type=document.document_type,
                    chunk_metadata={
                        "parent_chunk_index": parent_index,
                        "child_chunk_size": len(child_text),
                        "parent_chunk_size": len(parent_text),
                    },
                    embedding=embedding,
                )
            )
            global_child_index += 1
    session.add_all(rows)
    return len(rows)
