import os
from collections.abc import AsyncGenerator

os.environ["LLM_ENABLED"] = "false"
os.environ["MEMORY_ENABLED"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_async_session
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.tenant import Tenant, TenantKind
from app.models.user import User, UserRole


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        elegant = Tenant(name="Elegant Weddings", slug="elegant-weddings", kind=TenantKind.customer)
        royal = Tenant(name="Royal Events Agency", slug="royal-events-agency", kind=TenantKind.customer)
        platform = Tenant(name="EventSense Platform", slug="platform", kind=TenantKind.platform)
        session.add_all([elegant, royal, platform])
        await session.flush()
        session.add_all(
            [
                User(
                    tenant_id=elegant.id,
                    email="admin@elegant-weddings.demo",
                    hashed_password=hash_password("demo-password-1"),
                    role=UserRole.manager,
                    full_name="Elegant Weddings Admin",
                ),
                User(
                    tenant_id=royal.id,
                    email="admin@royal-events.demo",
                    hashed_password=hash_password("demo-password-2"),
                    role=UserRole.manager,
                    full_name="Royal Events Agency Admin",
                ),
                User(
                    tenant_id=platform.id,
                    email="platform-admin@eventsense.demo",
                    hashed_password=hash_password("platform-password"),
                    role=UserRole.platform_admin,
                    full_name="EventSense Platform Admin",
                ),
            ]
        )
        await session.commit()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_get_async_session

    async with SessionLocal() as session:
        yield session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def make_test_token():
    return create_access_token


@pytest_asyncio.fixture
async def demo_tenants(db_session: AsyncSession) -> dict[str, Tenant]:
    from sqlalchemy import select

    result = await db_session.execute(select(Tenant))
    return {tenant.slug: tenant for tenant in result.scalars().all()}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
