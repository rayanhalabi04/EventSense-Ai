import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole


DEMO_TENANTS = [
    {
        "name": "Elegant Weddings",
        "slug": "elegant-weddings",
        "email": "admin@elegant-weddings.demo",
        "password": "demo-password-1",
        "full_name": "Elegant Weddings Admin",
        "role": UserRole.manager,
    },
    {
        "name": "Royal Events Agency",
        "slug": "royal-events-agency",
        "email": "admin@royal-events.demo",
        "password": "demo-password-2",
        "full_name": "Royal Events Agency Admin",
        "role": UserRole.manager,
    },
]


async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as session:
        for item in DEMO_TENANTS:
            result = await session.execute(select(Tenant).where(Tenant.slug == item["slug"]))
            tenant = result.scalar_one_or_none()
            if tenant is None:
                tenant = Tenant(name=item["name"], slug=item["slug"])
                session.add(tenant)
                await session.flush()

            result = await session.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == item["email"])
            )
            user = result.scalar_one_or_none()
            if user is None:
                session.add(
                    User(
                        tenant_id=tenant.id,
                        email=item["email"],
                        hashed_password=hash_password(item["password"]),
                        role=item["role"],
                        full_name=item["full_name"],
                    )
                )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
