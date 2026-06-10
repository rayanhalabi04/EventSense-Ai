"""create tenants

Revision ID: 0001_create_tenants
Revises:
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_tenants"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Let create_table below create the enum exactly once. Previously this
    # migration ALSO called tenant_kind.create() explicitly, so create_table's
    # _on_table_create hook re-emitted CREATE TYPE and Postgres errored with
    # DuplicateObject ("type tenant_kind already exists") on a fresh database.
    tenant_kind = sa.Enum("customer", "platform", name="tenant_kind")

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("kind", tenant_kind, nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("name", name=op.f("uq_tenants_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=False)
    op.create_index("ix_tenants_kind", "tenants", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tenants_kind", table_name="tenants")
    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")
    sa.Enum(name="tenant_kind").drop(op.get_bind(), checkfirst=True)
