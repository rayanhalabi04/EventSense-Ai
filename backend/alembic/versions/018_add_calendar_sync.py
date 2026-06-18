"""Add calendar sync tables

Revision ID: 018_add_calendar_sync
Revises: 017_escalation_system_created_by
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "018_add_calendar_sync"
down_revision: Union[str, None] = "017_escalation_system_created_by"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


calendar_provider = postgresql.ENUM("google", name="calendar_provider", create_type=False)
calendar_connection_type = postgresql.ENUM(
    "tenant_shared",
    name="calendar_connection_type",
    create_type=False,
)
calendar_event_sync_status = postgresql.ENUM(
    "created",
    "failed",
    "deleted",
    name="calendar_event_sync_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    calendar_provider.create(bind, checkfirst=True)
    calendar_connection_type.create(bind, checkfirst=True)
    calendar_event_sync_status.create(bind, checkfirst=True)

    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("provider", calendar_provider, nullable=False, server_default="google"),
        sa.Column("provider_account_email", sa.String(length=320), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False, server_default="primary"),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column(
            "connection_type",
            calendar_connection_type,
            nullable=False,
            server_default="tenant_shared",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_connections_tenant_id", "calendar_connections", ["tenant_id"])
    op.create_index(
        "uq_calendar_connections_active_google_tenant_shared",
        "calendar_connections",
        ["tenant_id", "provider", "connection_type"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("calendar_connection_id", sa.Uuid(), nullable=True),
        sa.Column("provider", calendar_provider, nullable=False, server_default="google"),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("provider_event_link", sa.Text(), nullable=True),
        sa.Column("calendar_id", sa.String(length=255), nullable=False, server_default="primary"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("related_conversation_id", sa.Uuid(), nullable=True),
        sa.Column("related_message_id", sa.Uuid(), nullable=True),
        sa.Column("related_task_id", sa.Uuid(), nullable=True),
        sa.Column("related_escalation_id", sa.Uuid(), nullable=True),
        sa.Column("sync_status", calendar_event_sync_status, nullable=False, server_default="created"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["calendar_connection_id"], ["calendar_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_escalation_id"], ["escalations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_events_tenant_id", "calendar_events", ["tenant_id"])
    op.create_index(
        "ix_calendar_events_tenant_id_start_time",
        "calendar_events",
        ["tenant_id", "start_time"],
    )
    op.create_index(
        "ix_calendar_events_tenant_id_related_task_id",
        "calendar_events",
        ["tenant_id", "related_task_id"],
    )
    op.create_index(
        "ix_calendar_events_tenant_id_related_conversation_id",
        "calendar_events",
        ["tenant_id", "related_conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_tenant_id_related_conversation_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_tenant_id_related_task_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_tenant_id_start_time", table_name="calendar_events")
    op.drop_index("ix_calendar_events_tenant_id", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_index("uq_calendar_connections_active_google_tenant_shared", table_name="calendar_connections")
    op.drop_index("ix_calendar_connections_tenant_id", table_name="calendar_connections")
    op.drop_table("calendar_connections")

    bind = op.get_bind()
    calendar_event_sync_status.drop(bind, checkfirst=True)
    calendar_connection_type.drop(bind, checkfirst=True)
    calendar_provider.drop(bind, checkfirst=True)
