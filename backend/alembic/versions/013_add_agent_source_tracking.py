"""add agent source tracking to tasks and escalations

Adds nullable provenance columns so the focused agent's ``apply=true`` is
idempotent: at most one agent-created task and one agent-created escalation per
(tenant, message). ``source_type`` is "agent" for agent-created rows (NULL for
human/UI-created); ``source_message_id`` is a plain dedup marker (no FK).

Revision ID: 013_add_agent_source_tracking
Revises: 012_add_suggested_replies
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa


revision = "013_add_agent_source_tracking"
down_revision = "012_add_suggested_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("source_type", sa.String(length=20), nullable=True))
    op.add_column("tasks", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.add_column("escalations", sa.Column("source_type", sa.String(length=20), nullable=True))
    op.add_column("escalations", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_tasks_tenant_id_source_message_id",
        "tasks",
        ["tenant_id", "source_message_id"],
    )
    op.create_index(
        "ix_escalations_tenant_id_source_message_id",
        "escalations",
        ["tenant_id", "source_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_escalations_tenant_id_source_message_id", table_name="escalations")
    op.drop_index("ix_tasks_tenant_id_source_message_id", table_name="tasks")
    op.drop_column("escalations", "source_message_id")
    op.drop_column("escalations", "source_type")
    op.drop_column("tasks", "source_message_id")
    op.drop_column("tasks", "source_type")
