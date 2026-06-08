from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
        return TenantContext(
            user_id=UUID(payload["user_id"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=UserRole(payload["role"]),
        )
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def require_role(*roles: UserRole):
    async def dependency(
        ctx: TenantContext = Depends(get_current_tenant_context),
    ) -> TenantContext:
        if ctx.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return ctx

    return dependency
