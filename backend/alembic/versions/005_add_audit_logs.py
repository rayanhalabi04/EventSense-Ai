"""add audit logs

Revision ID: 005_add_audit_logs
Revises: 004_add_message_intent_classification
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "005_add_audit_logs"
down_revision = "004_add_message_intent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_logs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_tenant_id_created_at",
        "audit_logs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_tenant_id_event_type",
        "audit_logs",
        ["tenant_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_id_event_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
