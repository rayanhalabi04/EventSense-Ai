from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.core.security import (
    AUTH_EVENT_LOGIN_FAILURE,
    AUTH_EVENT_LOGIN_FAILURE_INACTIVE,
    AUTH_EVENT_LOGIN_SUCCESS,
    AUTH_EVENT_LOGOUT,
    AUTH_EVENT_TOKEN_REFRESH,
    create_access_token,
    emit_auth_event,
    invalid_credentials_error,
    invalid_token_error,
    verify_password,
)
from app.core.tenant_context import TenantContext, get_current_tenant_context
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse


router = APIRouter()


def _expires_in_seconds() -> int:
    return settings.access_token_expire_minutes * 60


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(
        sub=user.id,
        tenant_id=user.tenant_id,
        role=user.role.value,
    )
    return TokenResponse(access_token=token, expires_in=_expires_in_seconds())


async def authenticate_and_create_token(
    credentials: LoginRequest,
    session: AsyncSession,
) -> TokenResponse:
    tenant_result = await session.execute(
        select(Tenant)
        .where(Tenant.slug == credentials.tenant_slug, Tenant.is_active.is_(True))
        .limit(1)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        emit_auth_event(
            AUTH_EVENT_LOGIN_FAILURE,
            email=str(credentials.email),
            tenant_slug=credentials.tenant_slug,
            outcome="blocked",
        )
        raise invalid_credentials_error()

    user_result = await session.execute(
        select(User)
        .where(User.email == str(credentials.email), User.tenant_id == tenant.id)
        .limit(1)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        emit_auth_event(
            AUTH_EVENT_LOGIN_FAILURE,
            email=str(credentials.email),
            tenant_slug=credentials.tenant_slug,
            outcome="blocked",
        )
        raise invalid_credentials_error()

    if not user.is_active:
        emit_auth_event(
            AUTH_EVENT_LOGIN_FAILURE_INACTIVE,
            email=str(credentials.email),
            tenant_slug=credentials.tenant_slug,
            outcome="blocked",
        )
        raise invalid_credentials_error()

    if not verify_password(credentials.password, user.hashed_password):
        emit_auth_event(
            AUTH_EVENT_LOGIN_FAILURE,
            email=str(credentials.email),
            tenant_slug=credentials.tenant_slug,
            outcome="blocked",
        )
        raise invalid_credentials_error()

    emit_auth_event(
        AUTH_EVENT_LOGIN_SUCCESS,
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role.value,
        outcome="allowed",
    )
    return _token_response(user)


@router.post("/token", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    return await authenticate_and_create_token(credentials, session)


@router.get("/me", response_model=UserResponse)
async def get_me(
    ctx: TenantContext = Depends(get_current_tenant_context),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    user = await session.get(User, ctx.user_id)
    if user is None or user.tenant_id != ctx.tenant_id:
        raise invalid_token_error()
    return user


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    ctx: TenantContext = Depends(get_current_tenant_context),
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    user = await session.get(User, ctx.user_id)
    tenant = await session.get(Tenant, ctx.tenant_id)
    if (
        user is None
        or tenant is None
        or user.tenant_id != tenant.id
        or not user.is_active
        or not tenant.is_active
    ):
        raise invalid_token_error()

    emit_auth_event(
        AUTH_EVENT_TOKEN_REFRESH,
        user_id=user.id,
        tenant_id=tenant.id,
        outcome="allowed",
    )
    return _token_response(user)


@router.post("/logout")
async def logout(
    ctx: TenantContext = Depends(get_current_tenant_context),
) -> dict[str, str]:
    emit_auth_event(
        AUTH_EVENT_LOGOUT,
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        outcome="allowed",
    )
    return {"message": "Logged out"}
