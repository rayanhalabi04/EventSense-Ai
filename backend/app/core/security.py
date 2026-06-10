import base64
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.auth import TokenData
from app.services.audit_log_service import (
    AUDIT_EVENT_AUTH_LOGIN_FAILED,
    AUDIT_EVENT_AUTH_LOGIN_SUCCESS,
    AUDIT_EVENT_AUTH_LOGOUT,
    AuditLogService,
)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_EVENT_LOGIN_SUCCESS = "login_success"
AUTH_EVENT_LOGIN_FAILURE = "login_failure"
AUTH_EVENT_LOGIN_FAILURE_INACTIVE = "login_failure_inactive"
AUTH_EVENT_INSUFFICIENT_ROLE = "insufficient_role"
AUTH_EVENT_PLATFORM_ADMIN_CONTENT_ATTEMPT = "platform_admin_content_attempt"
AUTH_EVENT_TOKEN_REFRESH = "token_refresh"
AUTH_EVENT_LOGOUT = "logout"

TOKEN_TYPE_BEARER = "bearer"


def _auth_error(status_code: int, detail: str, error_code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"detail": detail, "error_code": error_code},
    )


def invalid_credentials_error() -> HTTPException:
    return _auth_error(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid credentials",
        "INVALID_CREDENTIALS",
    )


def missing_token_error() -> HTTPException:
    return _auth_error(status.HTTP_401_UNAUTHORIZED, "Missing token", "MISSING_TOKEN")


def invalid_token_error() -> HTTPException:
    return _auth_error(status.HTTP_401_UNAUTHORIZED, "Invalid token", "INVALID_TOKEN")


def expired_token_error() -> HTTPException:
    return _auth_error(status.HTTP_401_UNAUTHORIZED, "Token expired", "TOKEN_EXPIRED")


def insufficient_role_error() -> HTTPException:
    return _auth_error(status.HTTP_403_FORBIDDEN, "forbidden", "INSUFFICIENT_ROLE")


AUTH_EVENT_TO_AUDIT_EVENT = {
    AUTH_EVENT_LOGIN_SUCCESS: AUDIT_EVENT_AUTH_LOGIN_SUCCESS,
    AUTH_EVENT_LOGIN_FAILURE: AUDIT_EVENT_AUTH_LOGIN_FAILED,
    AUTH_EVENT_LOGIN_FAILURE_INACTIVE: AUDIT_EVENT_AUTH_LOGIN_FAILED,
    AUTH_EVENT_LOGOUT: AUDIT_EVENT_AUTH_LOGOUT,
}


def emit_auth_event(
    action: str,
    *,
    session: AsyncSession | None = None,
    **details: object,
) -> None:
    event_type = AUTH_EVENT_TO_AUDIT_EVENT.get(action)
    tenant_id = details.get("tenant_id")
    if session is None or event_type is None or not isinstance(tenant_id, UUID):
        return None

    actor_user_id = details.get("user_id")
    AuditLogService.record(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id if isinstance(actor_user_id, UUID) else None,
        event_type=event_type,
        details={key: value for key, value in details.items() if key not in {"tenant_id"}},
    )
    return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *,
    sub: str | UUID | None = None,
    user_id: str | UUID | None = None,
    tenant_id: str | UUID,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    subject = sub if sub is not None else user_id
    if subject is None:
        raise ValueError("sub or user_id is required")

    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> TokenData:
    if not _has_canonical_base64url_segments(token):
        raise invalid_token_error()

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise expired_token_error() from exc
    except JWTError as exc:
        raise invalid_token_error() from exc

    try:
        return TokenData.model_validate(payload)
    except ValueError as exc:
        raise invalid_token_error() from exc


def decode_access_token(token: str) -> TokenData:
    return decode_jwt(token)


def _has_canonical_base64url_segments(token: str) -> bool:
    segments = token.split(".")
    if len(segments) != 3:
        return False

    for segment in segments:
        try:
            padding = "=" * (-len(segment) % 4)
            decoded = base64.urlsafe_b64decode(segment + padding)
            canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
        except Exception:
            return False
        if canonical != segment:
            return False
    return True
