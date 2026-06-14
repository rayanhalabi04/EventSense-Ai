"""upgrade document_chunks embedding dimension for semantic embeddings

Moves the pgvector column from the original keyword/hash size (vector(64)) to the
configured EMBEDDING_DIM (default 768, the native size of Gemini
text-embedding-004). Existing chunk rows are derived data and cannot be reused
at a new dimension, so they are removed; re-embed them afterwards with:

    python -m app.reembed_chunks

Revision ID: 014_upgrade_embedding_dimension
Revises: 013_add_agent_source_tracking
Create Date: 2026-06-14
"""
from alembic import op

from app.core.config import settings


revision = "014_upgrade_embedding_dimension"
down_revision = "013_add_agent_source_tracking"
branch_labels = None
depends_on = None


_OLD_DIM = 64


def _set_dimension(dim: int) -> None:
    # Only PostgreSQL/pgvector stores a fixed-dimension vector column. On other
    # backends (e.g. SQLite used in tests) the embedding is free-form text and
    # the schema is built from the ORM models, so there is nothing to alter.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    # Old vectors do not fit the new dimension; chunks are fully rebuildable.
    op.execute("DELETE FROM document_chunks")
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({dim})")
    op.execute(
        f"""
        CREATE INDEX ix_document_chunks_embedding
        ON document_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def upgrade() -> None:
    _set_dimension(settings.embedding_dim)


def downgrade() -> None:
    _set_dimension(_OLD_DIM)
