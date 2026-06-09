import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole


STAFF_USERS = [
    {
        "tenant_slug": "elegant-weddings",
        "email": "staff@elegant-weddings.demo",
        "password": "staff-password-1",
        "full_name": "Elegant Weddings Staff",
    },
    {
        "tenant_slug": "royal-events-agency",
        "email": "staff@royal-events.demo",
        "password": "staff-password-2",
        "full_name": "Royal Events Agency Staff",
    },
]


async def seed_staff_users() -> None:
    async with AsyncSessionLocal() as session:
        for item in STAFF_USERS:
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.slug == item["tenant_slug"])
            )
            tenant = tenant_result.scalar_one()

            user_result = await session.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == item["email"])
            )
            if user_result.scalar_one_or_none() is None:
                session.add(
                    User(
                        tenant_id=tenant.id,
                        email=item["email"],
                        hashed_password=hash_password(item["password"]),
                        role=UserRole.staff,
                        full_name=item["full_name"],
                    )
                )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_staff_users())
