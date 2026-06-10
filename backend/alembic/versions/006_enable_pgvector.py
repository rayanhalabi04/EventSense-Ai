"""enable pgvector extension

Revision ID: 006_enable_pgvector
Revises: 005_add_audit_logs
Create Date: 2026-06-10

Creates the PostgreSQL ``vector`` extension so later RAG features (Spec 009) can
store embeddings. Idempotent and PostgreSQL-only; skipped on other dialects so
the suite can run migrations against sqlite in tests.
"""
from alembic import op


revision = "006_enable_pgvector"
down_revision = "005_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector")
