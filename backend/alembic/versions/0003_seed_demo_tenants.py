"""seed demo tenants

Revision ID: 0003_seed_demo_tenants
Revises: 0002_create_users
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import UUID

from app.core.security import hash_password


revision = "0003_seed_demo_tenants"
down_revision = "0002_create_users"
branch_labels = None
depends_on = None


TENANT_IDS = {
    "elegant": "a1b2c3d4-0000-0000-0000-000000000001",
    "royal": "a1b2c3d4-0000-0000-0000-000000000002",
    "platform": "a1b2c3d4-0000-0000-0000-0000000000ff",
}

USER_IDS = {
    "elegant_manager": "b1b2c3d4-0000-0000-0000-000000000001",
    "royal_manager": "b1b2c3d4-0000-0000-0000-000000000002",
    "platform_admin": "b1b2c3d4-0000-0000-0000-0000000000ff",
}


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    tenants = sa.table(
        "tenants",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        # Match the real enum column type so Postgres accepts the value (a plain
        # String bind is rejected: "column kind is of type tenant_kind but
        # expression is of type character varying").
        sa.column("kind", sa.Enum("customer", "platform", name="tenant_kind", create_type=False)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("email", sa.String()),
        sa.column("hashed_password", sa.String()),
        sa.column(
            "role",
            sa.Enum("staff", "manager", "platform_admin", name="user_role", create_type=False),
        ),
        sa.column("full_name", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    op.bulk_insert(
        tenants,
        [
            {
                "id": UUID(TENANT_IDS["elegant"]),
                "name": "Elegant Weddings",
                "slug": "elegant-weddings",
                "kind": "customer",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID(TENANT_IDS["royal"]),
                "name": "Royal Events Agency",
                "slug": "royal-events-agency",
                "kind": "customer",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID(TENANT_IDS["platform"]),
                "name": "EventSense Platform",
                "slug": "platform",
                "kind": "platform",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    op.bulk_insert(
        users,
        [
            {
                "id": UUID(USER_IDS["elegant_manager"]),
                "tenant_id": UUID(TENANT_IDS["elegant"]),
                "email": "admin@elegant-weddings.demo",
                "hashed_password": hash_password("demo-password-1"),
                "role": "manager",
                "full_name": "Elegant Weddings Admin",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID(USER_IDS["royal_manager"]),
                "tenant_id": UUID(TENANT_IDS["royal"]),
                "email": "admin@royal-events.demo",
                "hashed_password": hash_password("demo-password-2"),
                "role": "manager",
                "full_name": "Royal Events Agency Admin",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID(USER_IDS["platform_admin"]),
                "tenant_id": UUID(TENANT_IDS["platform"]),
                "email": "platform-admin@eventsense.demo",
                "hashed_password": hash_password("platform-password"),
                "role": "platform_admin",
                "full_name": "EventSense Platform Admin",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM users WHERE email IN ("
        "'admin@elegant-weddings.demo', "
        "'admin@royal-events.demo', "
        "'platform-admin@eventsense.demo'"
        ")"
    )
    op.execute(
        "DELETE FROM tenants WHERE slug IN ("
        "'elegant-weddings', 'royal-events-agency', 'platform'"
        ")"
    )
