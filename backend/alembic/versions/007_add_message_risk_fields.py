"""add message risk fields

Revision ID: 007_add_message_risk_fields
Revises: 006_enable_pgvector
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "007_add_message_risk_fields"
down_revision = "006_enable_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("risk_level", sa.String(length=20), nullable=True))
    op.add_column("messages", sa.Column("risk_flags", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("risk_reason", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("risk_detected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "risk_detected_at")
    op.drop_column("messages", "risk_reason")
    op.drop_column("messages", "risk_flags")
    op.drop_column("messages", "risk_level")
