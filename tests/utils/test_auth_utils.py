"""Unit tests for utils/auth.py — no DB, no HTTP."""
import pytest
from fastapi import HTTPException

from utils.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_complexity,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_and_verify_password():
    hashed = hash_password("Str0ng!Pass1")
    assert hashed != "Str0ng!Pass1"
    assert verify_password("Str0ng!Pass1", hashed)


def test_verify_wrong_password_returns_false():
    hashed = hash_password("Str0ng!Pass1")
    assert not verify_password("Wrong!Pass1", hashed)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def test_create_and_decode_access_token():
    token = create_access_token({"sub": "user-1", "role": "admin", "session_id": "sess-1"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"
    assert payload["session_id"] == "sess-1"


def test_decode_expired_token_raises_401():
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from src.config import settings

    payload = {
        "sub": "user-1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_decode_tampered_token_raises_401():
    token = create_access_token({"sub": "user-1"})
    tampered = token[:-4] + "XXXX"
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(tampered)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Password complexity
# ---------------------------------------------------------------------------

def test_validate_password_complexity_passes():
    # Should not raise
    validate_password_complexity("Str0ng!Pass1")


def test_validate_password_complexity_fails_too_short():
    with pytest.raises(HTTPException) as exc_info:
        validate_password_complexity("Sh0rt!")
    assert exc_info.value.status_code == 422


def test_validate_password_complexity_fails_no_uppercase():
    with pytest.raises(HTTPException) as exc_info:
        validate_password_complexity("str0ng!pass1")
    assert exc_info.value.status_code == 422


def test_validate_password_complexity_fails_no_digit():
    with pytest.raises(HTTPException) as exc_info:
        validate_password_complexity("Str!ngPass!")
    assert exc_info.value.status_code == 422


def test_validate_password_complexity_fails_no_special():
    with pytest.raises(HTTPException) as exc_info:
        validate_password_complexity("Str0ngPass1")
    assert exc_info.value.status_code == 422
