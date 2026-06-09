from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_jwt
from app.models.tenant import Tenant
from app.models.user import User


pytestmark = pytest.mark.asyncio


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(
    client: AsyncClient,
    email: str = "admin@elegant-weddings.demo",
    password: str = "demo-password-1",
    tenant_slug: str = "elegant-weddings",
    extra: dict[str, str] | None = None,
):
    payload = {"email": email, "password": password, "tenant_slug": tenant_slug}
    if extra:
        payload.update(extra)
    return await client.post("/auth/token", json=payload)


async def test_login_success_for_elegant_manager(client: AsyncClient):
    response = await login(client)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    token_data = decode_jwt(data["access_token"])
    assert token_data.role.value == "manager"


async def test_login_success_for_royal_manager(client: AsyncClient):
    response = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )

    assert response.status_code == 200
    assert decode_jwt(response.json()["access_token"]).role.value == "manager"


async def test_login_success_for_platform_admin(client: AsyncClient):
    response = await login(
        client,
        email="platform-admin@eventsense.demo",
        password="platform-password",
        tenant_slug="platform",
    )

    assert response.status_code == 200
    assert decode_jwt(response.json()["access_token"]).role.value == "platform_admin"


async def test_login_failure_wrong_password_returns_401(client: AsyncClient):
    response = await login(client, password="wrong")

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"
    assert "access_token" not in response.json()


async def test_login_failure_unknown_email_returns_401(client: AsyncClient):
    response = await login(client, email="nobody@elegant-weddings.demo")

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_login_failure_inactive_user_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "admin@elegant-weddings.demo")
        )
    ).scalar_one()
    user.is_active = False
    await db_session.commit()

    response = await login(client)

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_login_failure_inactive_tenant_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
):
    tenant = (
        await db_session.execute(select(Tenant).where(Tenant.slug == "elegant-weddings"))
    ).scalar_one()
    tenant.is_active = False
    await db_session.commit()

    response = await login(client)

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_token_contains_correct_tenant_user_role_claims(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "admin@elegant-weddings.demo")
        )
    ).scalar_one()

    response = await login(client)
    token_data = decode_jwt(response.json()["access_token"])

    assert token_data.sub == user.id
    assert token_data.tenant_id == user.tenant_id
    assert token_data.role == user.role


async def test_get_me_returns_current_user_safely(client: AsyncClient):
    token = (await login(client)).json()["access_token"]

    response = await client.get("/auth/me", headers=auth_headers(token))

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@elegant-weddings.demo"
    assert data["role"] == "manager"
    assert "hashed_password" not in data


async def test_missing_token_returns_401_missing_token_code(client: AsyncClient):
    response = await client.get("/api/v1/conversations")

    assert response.status_code == 401
    assert response.json()["error_code"] == "MISSING_TOKEN"


async def test_tampered_token_returns_401_invalid_token_code(client: AsyncClient):
    token = (await login(client)).json()["access_token"]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    response = await client.get("/auth/me", headers=auth_headers(tampered))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_expired_token_on_protected_route_returns_401_token_expired_code(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "admin@elegant-weddings.demo")
        )
    ).scalar_one()
    token = create_access_token(
        sub=user.id,
        tenant_id=user.tenant_id,
        role=user.role.value,
        expires_delta=timedelta(seconds=-1),
    )

    response = await client.get("/auth/me", headers=auth_headers(token))

    assert response.status_code == 401
    assert response.json()["error_code"] == "TOKEN_EXPIRED"


async def test_token_refresh_returns_new_token_with_same_claims_and_later_expiry(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "admin@elegant-weddings.demo")
        )
    ).scalar_one()
    token = create_access_token(
        sub=user.id,
        tenant_id=user.tenant_id,
        role=user.role.value,
        expires_delta=timedelta(minutes=1),
    )

    response = await client.post("/auth/refresh", headers=auth_headers(token))

    assert response.status_code == 200
    old_data = decode_jwt(token)
    new_data = decode_jwt(response.json()["access_token"])
    assert new_data.sub == old_data.sub
    assert new_data.tenant_id == old_data.tenant_id
    assert new_data.role == old_data.role
    assert new_data.exp > old_data.exp


async def test_token_refresh_with_expired_token_returns_401(client: AsyncClient):
    response = await client.post("/auth/refresh", headers=auth_headers("not-a-token"))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_token_refresh_rejects_inactive_user(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = (await login(client)).json()["access_token"]
    user = (
        await db_session.execute(
            select(User).where(User.email == "admin@elegant-weddings.demo")
        )
    ).scalar_one()
    user.is_active = False
    await db_session.commit()

    response = await client.post("/auth/refresh", headers=auth_headers(token))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_token_refresh_rejects_inactive_tenant(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = (await login(client)).json()["access_token"]
    tenant = (
        await db_session.execute(select(Tenant).where(Tenant.slug == "elegant-weddings"))
    ).scalar_one()
    tenant.is_active = False
    await db_session.commit()

    response = await client.post("/auth/refresh", headers=auth_headers(token))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_logout_returns_200(client: AsyncClient):
    token = (await login(client)).json()["access_token"]

    response = await client.post("/auth/logout", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {"message": "Logged out"}


async def test_body_tenant_id_field_is_ignored_at_login(
    client: AsyncClient,
    db_session: AsyncSession,
):
    royal = (
        await db_session.execute(select(Tenant).where(Tenant.slug == "royal-events-agency"))
    ).scalar_one()

    response = await login(client, extra={"tenant_id": str(royal.id)})

    assert response.status_code == 200
    token_data = decode_jwt(response.json()["access_token"])
    assert token_data.tenant_id != royal.id
