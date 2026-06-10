"""add escalations

Revision ID: 009_add_escalations
Revises: 008_add_tasks
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "009_add_escalations"
down_revision = "008_add_tasks"
branch_labels = None
depends_on = None


escalation_status = sa.Enum("open", "in_review", "resolved", "cancelled", name="escalation_status")


def upgrade() -> None:
    op.create_table(
        "escalations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_manager_user_id", sa.Uuid(), nullable=True),
        sa.Column("intent_label", sa.String(length=40), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=True),
        sa.Column("risk_reason", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("suggested_next_step", sa.Text(), nullable=True),
        sa.Column("status", escalation_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_manager_user_id"],
            ["users.id"],
            name=op.f("fk_escalations_assigned_manager_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_escalations_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_escalations_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_escalations_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_escalations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalations")),
    )
    op.create_index("ix_escalations_tenant_id", "escalations", ["tenant_id"], unique=False)
    op.create_index(
        "ix_escalations_tenant_id_status",
        "escalations",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_escalations_tenant_id_conversation_id",
        "escalations",
        ["tenant_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_escalations_tenant_id_assigned_manager_user_id",
        "escalations",
        ["tenant_id", "assigned_manager_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_escalations_tenant_id_assigned_manager_user_id", table_name="escalations")
    op.drop_index("ix_escalations_tenant_id_conversation_id", table_name="escalations")
    op.drop_index("ix_escalations_tenant_id_status", table_name="escalations")
    op.drop_index("ix_escalations_tenant_id", table_name="escalations")
    op.drop_table("escalations")
    escalation_status.drop(op.get_bind(), checkfirst=True)
