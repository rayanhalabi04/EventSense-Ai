from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_async_session
from app.core.security import hash_password
from app.main import app
from app.models.tenant import Tenant
from app.models.user import User, UserRole


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        elegant = Tenant(name="Elegant Weddings", slug="elegant-weddings")
        royal = Tenant(name="Royal Events Agency", slug="royal-events-agency")
        session.add_all([elegant, royal])
        await session.flush()
        session.add_all(
            [
                User(
                    tenant_id=elegant.id,
                    email="admin@elegant-weddings.demo",
                    hashed_password=hash_password("demo-password-1"),
                    role=UserRole.tenant_admin,
                    full_name="Elegant Weddings Admin",
                ),
                User(
                    tenant_id=royal.id,
                    email="admin@royal-events.demo",
                    hashed_password=hash_password("demo-password-2"),
                    role=UserRole.tenant_admin,
                    full_name="Royal Events Agency Admin",
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


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
