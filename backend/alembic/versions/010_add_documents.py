"""add documents

Revision ID: 010_add_documents
Revises: 009_add_escalations
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "010_add_documents"
down_revision = "009_add_escalations"
branch_labels = None
depends_on = None


document_type = sa.Enum(
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
)
document_status = sa.Enum("active", "archived", name="document_status")


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_documents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"], unique=False)
    op.create_index(
        "ix_documents_tenant_id_document_type",
        "documents",
        ["tenant_id", "document_type"],
        unique=False,
    )
    op.create_index(
        "ix_documents_tenant_id_status",
        "documents",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_id_status", table_name="documents")
    op.drop_index("ix_documents_tenant_id_document_type", table_name="documents")
    op.drop_index("ix_documents_tenant_id", table_name="documents")
    op.drop_table("documents")
    document_status.drop(op.get_bind(), checkfirst=True)
    document_type.drop(op.get_bind(), checkfirst=True)
