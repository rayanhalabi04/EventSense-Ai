"""initial tenant auth foundation

Revision ID: 001_initial_tenant_auth
Revises: 0003_seed_demo_tenants
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa


revision = "001_initial_tenant_auth"
down_revision = "0003_seed_demo_tenants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("client_contact", sa.String(length=320), nullable=True),
        sa.Column("status", sa.Enum("open", "closed", "escalated", name="conversationstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_conversations_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"], unique=False)
    op.create_index("ix_conversations_tenant_id_status", "conversations", ["tenant_id", "status"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.Enum("inbound", "outbound", name="messagedirection"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], name=op.f("fk_messages_conversation_id_conversations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], name=op.f("fk_messages_sender_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_messages_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"], unique=False)
    op.create_index("ix_messages_tenant_id_conversation_id", "messages", ["tenant_id", "conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_tenant_id_conversation_id", table_name="messages")
    op.drop_index("ix_messages_tenant_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_tenant_id_status", table_name="conversations")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_table("conversations")
    sa.Enum(name="messagedirection").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conversationstatus").drop(op.get_bind(), checkfirst=True)
