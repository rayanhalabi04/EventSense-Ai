from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.core.tenant_context import TenantContext, require_role
from app.models.tenant import Tenant
from app.models.user import User, UserRole


pytestmark = pytest.mark.asyncio


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def user_by_email(db_session: AsyncSession, email: str) -> User:
    return (await db_session.execute(select(User).where(User.email == email))).scalar_one()


def token_for(user: User) -> str:
    return create_access_token(sub=user.id, tenant_id=user.tenant_id, role=user.role.value)


async def create_staff_user(db_session: AsyncSession) -> User:
    tenant = (
        await db_session.execute(select(Tenant).where(Tenant.slug == "elegant-weddings"))
    ).scalar_one()
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="staff@elegant-weddings.demo",
        hashed_password=hash_password("staff-password-1"),
        role=UserRole.staff,
        full_name="Elegant Weddings Staff",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_staff_can_access_tenant_content_route(
    client: AsyncClient,
    db_session: AsyncSession,
):
    staff = await create_staff_user(db_session)

    response = await client.get("/api/v1/conversations", headers=auth_headers(token_for(staff)))

    assert response.status_code == 200


async def test_manager_can_access_tenant_content_route(
    client: AsyncClient,
    db_session: AsyncSession,
):
    manager = await user_by_email(db_session, "admin@elegant-weddings.demo")

    response = await client.get("/api/v1/conversations", headers=auth_headers(token_for(manager)))

    assert response.status_code == 200


async def test_platform_admin_cannot_access_tenant_content_route(
    client: AsyncClient,
    db_session: AsyncSession,
):
    platform_admin = await user_by_email(db_session, "platform-admin@eventsense.demo")

    response = await client.get(
        "/api/v1/conversations",
        headers=auth_headers(token_for(platform_admin)),
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_platform_admin_can_list_tenants_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
):
    platform_admin = await user_by_email(db_session, "platform-admin@eventsense.demo")

    response = await client.get(
        "/api/v1/admin/tenants",
        headers=auth_headers(token_for(platform_admin)),
    )

    assert response.status_code == 200
    assert {tenant["slug"] for tenant in response.json()} == {
        "elegant-weddings",
        "royal-events-agency",
        "platform",
    }


async def test_staff_cannot_access_admin_tenants_route_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
):
    staff = await create_staff_user(db_session)

    response = await client.get("/api/v1/admin/tenants", headers=auth_headers(token_for(staff)))

    assert response.status_code == 403
    assert response.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_manager_cannot_access_admin_tenants_route_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
):
    manager = await user_by_email(db_session, "admin@elegant-weddings.demo")

    response = await client.get("/api/v1/admin/tenants", headers=auth_headers(token_for(manager)))

    assert response.status_code == 403
    assert response.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_manager_only_policy_allows_manager_and_blocks_staff(
    db_session: AsyncSession,
):
    staff = await create_staff_user(db_session)
    manager = await user_by_email(db_session, "admin@elegant-weddings.demo")
    dependency = require_role(UserRole.manager)

    assert (
        await dependency(
            TenantContext(user_id=manager.id, tenant_id=manager.tenant_id, role=manager.role)
        )
    ).role is UserRole.manager

    with pytest.raises(HTTPException) as exc:
        await dependency(TenantContext(user_id=staff.id, tenant_id=staff.tenant_id, role=staff.role))

    assert exc.value.status_code == 403
    assert exc.value.detail["error_code"] == "INSUFFICIENT_ROLE"


async def test_modified_role_claim_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    staff = await create_staff_user(db_session)
    token = token_for(staff)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    response = await client.get("/api/v1/admin/tenants", headers=auth_headers(tampered))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"
