"""add suggested reply auto-sent tracking

Revision ID: 016_add_suggested_reply_auto_sent
Revises: 015_add_telegram_external_ids
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa


revision = "016_auto_sent"
down_revision = "015_add_telegram_external_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suggested_replies",
        sa.Column("auto_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "suggested_replies",
        sa.Column("sent_channel", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suggested_replies", "sent_channel")
    op.drop_column("suggested_replies", "auto_sent_at")
