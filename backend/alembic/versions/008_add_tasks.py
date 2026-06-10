"""add tasks

Revision ID: 008_add_tasks
Revises: 007_add_message_risk_fields
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "008_add_tasks"
down_revision = "007_add_message_risk_fields"
branch_labels = None
depends_on = None


task_status = sa.Enum("open", "in_progress", "completed", "cancelled", name="task_status")


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", task_status, nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"],
            ["users.id"],
            name=op.f("fk_tasks_assigned_to_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_tasks_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_tasks_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_tasks_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tasks_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"], unique=False)
    op.create_index("ix_tasks_tenant_id_status", "tasks", ["tenant_id", "status"], unique=False)
    op.create_index(
        "ix_tasks_tenant_id_conversation_id",
        "tasks",
        ["tenant_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_tenant_id_assigned_to_user_id",
        "tasks",
        ["tenant_id", "assigned_to_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_tenant_id_assigned_to_user_id", table_name="tasks")
    op.drop_index("ix_tasks_tenant_id_conversation_id", table_name="tasks")
    op.drop_index("ix_tasks_tenant_id_status", table_name="tasks")
    op.drop_index("ix_tasks_tenant_id", table_name="tasks")
    op.drop_table("tasks")
    task_status.drop(op.get_bind(), checkfirst=True)
