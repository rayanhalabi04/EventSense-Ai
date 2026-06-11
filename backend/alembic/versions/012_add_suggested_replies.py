"""add suggested replies

Revision ID: 012_add_suggested_replies
Revises: 011_add_document_chunks
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "012_add_suggested_replies"
down_revision = "011_add_document_chunks"
branch_labels = None
depends_on = None


suggested_reply_status = sa.Enum(
    "draft", "approved", "edited", "rejected", name="suggested_reply_status"
)


def upgrade() -> None:
    op.create_table(
        "suggested_replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("suggested_text", sa.Text(), nullable=False),
        sa.Column("status", suggested_reply_status, nullable=False),
        sa.Column("source_document_ids", sa.JSON(), nullable=False),
        sa.Column("rag_sources", sa.JSON(), nullable=False),
        sa.Column("answer_supported", sa.Boolean(), nullable=False),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("generation_method", sa.String(length=40), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_suggested_replies_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_suggested_replies_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_suggested_replies_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_suggested_replies_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name=op.f("fk_suggested_replies_approved_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggested_replies")),
    )
    op.create_index(
        "ix_suggested_replies_tenant_id", "suggested_replies", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_suggested_replies_tenant_id_conversation_id",
        "suggested_replies",
        ["tenant_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_suggested_replies_tenant_id_message_id",
        "suggested_replies",
        ["tenant_id", "message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_suggested_replies_tenant_id_message_id", table_name="suggested_replies")
    op.drop_index(
        "ix_suggested_replies_tenant_id_conversation_id", table_name="suggested_replies"
    )
    op.drop_index("ix_suggested_replies_tenant_id", table_name="suggested_replies")
    op.drop_table("suggested_replies")
    suggested_reply_status.drop(op.get_bind(), checkfirst=True)
