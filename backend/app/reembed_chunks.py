"""Re-embed every tenant document chunk with the active embedding backend.

Run this after changing EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_DIM (and
after the matching Alembic migration), because chunks embedded with a different
model or dimension cannot be compared against new query vectors.

Tenant isolation is preserved: chunks are rebuilt per-document from the owning
document's own content, so no data crosses tenants.

Usage:
    python -m app.reembed_chunks
"""

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.services.document_chunking_service import rebuild_document_chunks
from app.services.embedding_service import embedding_service


async def reembed_all_chunks() -> None:
    backend = embedding_service.backend_name
    kind = "semantic" if embedding_service.is_semantic else "deterministic (NON-semantic) fallback"
    print(f"Re-embedding with backend={backend} ({kind}), dim={embedding_service.dimensions}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Document).order_by(Document.tenant_id, Document.id))
        documents = list(result.scalars().all())

        total_chunks = 0
        for document in documents:
            count = await rebuild_document_chunks(session, document)
            total_chunks += count
            print(f"  {document.tenant_id} :: {document.title} -> {count} chunks")
        await session.commit()

    print(f"Done. Re-embedded {len(documents)} documents into {total_chunks} chunks.")


if __name__ == "__main__":
    asyncio.run(reembed_all_chunks())
