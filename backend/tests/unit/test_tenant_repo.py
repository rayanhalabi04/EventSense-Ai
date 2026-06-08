from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.core.tenant_repo import TenantScopedRepository, validate_same_tenant
from app.models.user import User, UserRole


pytestmark = pytest.mark.asyncio


async def test_repo_list_filters_by_tenant(db_session: AsyncSession, demo_tenants):
    repo = TenantScopedRepository(User, db_session)

    users = await repo.list(demo_tenants["elegant-weddings"].id)

    assert [user.email for user in users] == ["admin@elegant-weddings.demo"]


async def test_repo_get_or_403_blocks_cross_tenant(db_session: AsyncSession, demo_tenants):
    repo = TenantScopedRepository(User, db_session)
    result = await db_session.execute(
        select(User).where(User.email == "admin@royal-events.demo")
    )
    royal_user = result.scalar_one()

    with pytest.raises(ForbiddenError):
        await repo.get_or_403(royal_user.id, demo_tenants["elegant-weddings"].id)


async def test_create_injects_authenticated_tenant(db_session: AsyncSession, demo_tenants):
    repo = TenantScopedRepository(User, db_session)

    user = await repo.create(
        demo_tenants["elegant-weddings"].id,
        {
            "id": uuid4(),
            "tenant_id": demo_tenants["elegant-weddings"].id,
            "email": "staff@elegant-weddings.demo",
            "hashed_password": "not-used",
            "role": UserRole.staff,
            "full_name": "Elegant Staff",
        },
    )

    assert user.tenant_id == demo_tenants["elegant-weddings"].id


async def test_create_rejects_conflicting_client_tenant_id(
    db_session: AsyncSession,
    demo_tenants,
):
    repo = TenantScopedRepository(User, db_session)

    with pytest.raises(ForbiddenError):
        await repo.create(
            demo_tenants["elegant-weddings"].id,
            {
                "id": uuid4(),
                "tenant_id": demo_tenants["royal-events-agency"].id,
                "email": "bad@elegant-weddings.demo",
                "hashed_password": "not-used",
                "role": UserRole.staff,
                "full_name": "Bad Tenant",
            },
        )


async def test_validate_same_tenant_rejects_mismatch(db_session: AsyncSession, demo_tenants):
    repo = TenantScopedRepository(User, db_session)
    elegant_user = (
        await repo.list(demo_tenants["elegant-weddings"].id, email="admin@elegant-weddings.demo")
    )[0]
    royal_user = (
        await repo.list(demo_tenants["royal-events-agency"].id, email="admin@royal-events.demo")
    )[0]

    validate_same_tenant(elegant_user)
    with pytest.raises(ForbiddenError):
        validate_same_tenant(elegant_user, royal_user)
