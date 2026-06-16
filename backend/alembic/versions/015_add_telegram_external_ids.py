"""add telegram external ids

Revision ID: 015_add_telegram_external_ids
Revises: 014_upgrade_embedding_dimension
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa


revision = "015_add_telegram_external_ids"
down_revision = "014_upgrade_embedding_dimension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("source", sa.String(length=100), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("external_conversation_id", sa.String(length=255), nullable=True),
    )
    op.add_column("messages", sa.Column("external_message_id", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_conversations_tenant_source_external_id",
        "conversations",
        ["tenant_id", "source", "external_conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_tenant_source_external_id", table_name="conversations")
    op.drop_column("messages", "external_message_id")
    op.drop_column("conversations", "external_conversation_id")
    op.drop_column("conversations", "source")
