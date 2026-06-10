"""add document chunks

Revision ID: 011_add_document_chunks
Revises: 010_add_documents
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "011_add_document_chunks"
down_revision = "010_add_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE TABLE document_chunks (
                id uuid PRIMARY KEY,
                tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                parent_chunk_id uuid NOT NULL,
                chunk_text text NOT NULL,
                parent_text text NOT NULL,
                chunk_index integer NOT NULL,
                parent_chunk_index integer NOT NULL,
                document_title varchar(255) NOT NULL,
                document_type document_type NOT NULL,
                metadata jsonb NOT NULL,
                embedding vector(64) NOT NULL,
                created_at timestamp with time zone DEFAULT now() NOT NULL
            )
            """
        )
    else:
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("document_id", sa.Uuid(), nullable=False),
            sa.Column("parent_chunk_id", sa.Uuid(), nullable=False),
            sa.Column("chunk_text", sa.Text(), nullable=False),
            sa.Column("parent_text", sa.Text(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("parent_chunk_index", sa.Integer(), nullable=False),
            sa.Column("document_title", sa.String(length=255), nullable=False),
            sa.Column(
                "document_type",
                sa.Enum(
                    "pricing",
                    "package",
                    "faq",
                    "deposit_policy",
                    "cancellation_policy",
                    "contract_terms",
                    "service_description",
                    "decoration_rules",
                    "catering_rules",
                    "other",
                    name="document_type",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("embedding", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenants.id"],
                name=op.f("fk_document_chunks_tenant_id_tenants"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["documents.id"],
                name=op.f("fk_document_chunks_document_id_documents"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        )

    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index(
        "ix_document_chunks_tenant_id_document_type",
        "document_chunks",
        ["tenant_id", "document_type"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE INDEX ix_document_chunks_embedding
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.drop_index("ix_document_chunks_tenant_id_document_type", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_tenant_id", table_name="document_chunks")
    op.drop_table("document_chunks")
