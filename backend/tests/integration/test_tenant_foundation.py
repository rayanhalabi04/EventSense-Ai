from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token
from app.core.tenant_context import TenantContext, get_current_tenant_context
from app.models.tenant import TenantKind
from app.models.user import User, UserRole


pytestmark = pytest.mark.asyncio


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_demo_tenants_seeded(db_session: AsyncSession):
    result = await db_session.execute(
        select(User).options(selectinload(User.tenant)).order_by(User.email)
    )
    users = {user.email: user for user in result.scalars().all()}

    assert users["admin@elegant-weddings.demo"].role is UserRole.manager
    assert users["admin@elegant-weddings.demo"].tenant.slug == "elegant-weddings"
    assert users["admin@elegant-weddings.demo"].tenant.kind is TenantKind.customer
    assert users["admin@royal-events.demo"].role is UserRole.manager
    assert users["admin@royal-events.demo"].tenant.slug == "royal-events-agency"
    assert users["admin@royal-events.demo"].tenant.kind is TenantKind.customer


async def test_platform_tenant_seeded(db_session: AsyncSession):
    result = await db_session.execute(
        select(User)
        .options(selectinload(User.tenant))
        .where(User.email == "platform-admin@eventsense.demo")
    )
    platform_admin = result.scalar_one()

    assert platform_admin.role is UserRole.platform_admin
    assert platform_admin.tenant.slug == "platform"
    assert platform_admin.tenant.kind is TenantKind.platform


async def test_tenant_context_from_jwt(make_test_token, demo_tenants):
    token = make_test_token(
        user_id=uuid4(),
        tenant_id=demo_tenants["elegant-weddings"].id,
        role=UserRole.manager.value,
    )

    ctx = await get_current_tenant_context(type("Creds", (), {"credentials": token})())

    assert isinstance(ctx, TenantContext)
    assert ctx.tenant_id == demo_tenants["elegant-weddings"].id
    assert ctx.role is UserRole.manager


async def test_client_tenant_id_cannot_override_context(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants,
):
    result = await db_session.execute(
        select(User).where(User.email == "admin@elegant-weddings.demo")
    )
    elegant_user = result.scalar_one()
    token = create_access_token(
        user_id=elegant_user.id,
        tenant_id=elegant_user.tenant_id,
        role=elegant_user.role.value,
    )

    response = await client.get(
        f"/api/v1/tenants/me?tenant_id={demo_tenants['royal-events-agency'].id}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(demo_tenants["elegant-weddings"].id)


async def test_platform_admin_boundary_is_respected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    result = await db_session.execute(
        select(User).where(User.email == "platform-admin@eventsense.demo")
    )
    platform_admin = result.scalar_one()
    token = create_access_token(
        user_id=platform_admin.id,
        tenant_id=platform_admin.tenant_id,
        role=platform_admin.role.value,
    )

    tenant_me_response = await client.get("/api/v1/tenants/me", headers=auth_headers(token))
    admin_response = await client.get("/api/v1/admin/tenants", headers=auth_headers(token))

    assert tenant_me_response.status_code == 403
    assert admin_response.status_code == 200
    assert {tenant["slug"] for tenant in admin_response.json()} == {
        "elegant-weddings",
        "platform",
        "royal-events-agency",
    }
