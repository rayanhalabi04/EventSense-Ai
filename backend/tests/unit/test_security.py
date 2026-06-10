from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, decode_jwt, hash_password, verify_password
from app.models.user import UserRole


def tamper_jwt_signature(token: str) -> str:
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    return ".".join((header, payload, replacement + signature[1:]))


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("right-password")

    assert hashed != "right-password"
    assert verify_password("right-password", hashed) is True


def test_wrong_password_fails_verify():
    hashed = hash_password("right-password")

    assert verify_password("wrong-password", hashed) is False


def test_create_access_token_contains_all_required_claims():
    user_id = uuid4()
    tenant_id = uuid4()

    token = create_access_token(sub=user_id, tenant_id=tenant_id, role=UserRole.staff.value)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == UserRole.staff.value
    assert {"exp", "iat", "jti"}.issubset(payload)


def test_create_access_token_exp_is_60_minutes_from_now():
    token = create_access_token(sub=uuid4(), tenant_id=uuid4(), role=UserRole.staff.value)
    data = decode_jwt(token)
    now = int(datetime.now(timezone.utc).timestamp())

    assert 59 * 60 <= data.exp - now <= 60 * 60


def test_decode_jwt_returns_correct_token_data():
    user_id = uuid4()
    tenant_id = uuid4()

    token = create_access_token(sub=user_id, tenant_id=tenant_id, role=UserRole.manager.value)
    data = decode_jwt(token)

    assert data.sub == user_id
    assert data.tenant_id == tenant_id
    assert data.role is UserRole.manager


def test_decode_jwt_rejects_expired_token():
    token = create_access_token(
        sub=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.staff.value,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)

    assert exc.value.status_code == 401
    assert exc.value.detail["error_code"] == "TOKEN_EXPIRED"


def test_decode_jwt_rejects_tampered_signature():
    token = create_access_token(sub=uuid4(), tenant_id=uuid4(), role=UserRole.staff.value)
    tampered = tamper_jwt_signature(token)

    with pytest.raises(HTTPException) as exc:
        decode_jwt(tampered)

    assert exc.value.status_code == 401
    assert exc.value.detail["error_code"] == "INVALID_TOKEN"
