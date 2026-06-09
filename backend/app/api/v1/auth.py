from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import authenticate_and_create_token
from app.core.database import get_async_session
from app.core.security import invalid_credentials_error
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse


router = APIRouter()


class LegacyLoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None


@router.post("/login", response_model=TokenResponse)
async def legacy_login(
    credentials: LegacyLoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    tenant_slug = credentials.tenant_slug
    if tenant_slug is None:
        result = await session.execute(
            select(User, Tenant)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(User.email == str(credentials.email), Tenant.is_active.is_(True))
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise invalid_credentials_error()
        tenant_slug = row.Tenant.slug

    return await authenticate_and_create_token(
        LoginRequest(
            email=credentials.email,
            password=credentials.password,
            tenant_slug=tenant_slug,
        ),
        session,
    )
