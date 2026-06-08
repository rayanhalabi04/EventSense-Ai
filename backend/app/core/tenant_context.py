from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import (
    AUTH_EVENT_INSUFFICIENT_ROLE,
    decode_access_token,
    emit_auth_event,
    insufficient_role_error,
    invalid_token_error,
    missing_token_error,
)
from app.models.user import UserRole


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    tenant_id: UUID
    role: UserRole


async def get_current_tenant_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TenantContext:
    if credentials is None:
        raise missing_token_error()

    try:
        data = decode_access_token(credentials.credentials)
        return TenantContext(
            user_id=data.sub,
            tenant_id=data.tenant_id,
            role=data.role,
        )
    except HTTPException:
        raise
    except (TypeError, ValueError):
        raise invalid_token_error()


def require_role(*roles: UserRole):
    async def dependency(
        ctx: TenantContext = Depends(get_current_tenant_context),
    ) -> TenantContext:
        if ctx.role not in roles:
            emit_auth_event(
                AUTH_EVENT_INSUFFICIENT_ROLE,
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                required_roles=[role.value for role in roles],
                actual_role=ctx.role.value,
            )
            raise insufficient_role_error()
        return ctx

    return dependency
