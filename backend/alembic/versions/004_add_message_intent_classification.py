"""add message intent classification

Revision ID: 004_add_message_intent_classification
Revises: 003_add_message_status
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


# Revision id kept <= 32 chars: alembic_version.version_num is varchar(32),
# and the previous id "004_add_message_intent_classification" (37) overflowed it.
revision = "004_add_message_intent"
down_revision = "003_add_message_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("intent_label", sa.String(length=40), nullable=True))
    op.add_column("messages", sa.Column("intent_confidence", sa.Float(), nullable=True))
    op.add_column("messages", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "classified_at")
    op.drop_column("messages", "intent_confidence")
    op.drop_column("messages", "intent_label")
