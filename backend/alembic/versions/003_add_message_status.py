"""add message status

Revision ID: 003_add_message_status
Revises: 002_add_message_source
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa


revision = "003_add_message_status"
down_revision = "002_add_message_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    message_status = sa.Enum("unread", "read", name="message_status")
    message_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "messages",
        sa.Column("status", message_status, nullable=False, server_default="unread"),
    )


def downgrade() -> None:
    op.drop_column("messages", "status")
    sa.Enum(name="message_status").drop(op.get_bind(), checkfirst=True)
