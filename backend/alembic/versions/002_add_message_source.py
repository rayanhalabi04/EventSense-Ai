"""add message source

Revision ID: 002_add_message_source
Revises: 001_initial_tenant_auth
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "002_add_message_source"
down_revision = "001_initial_tenant_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("source", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "source")
