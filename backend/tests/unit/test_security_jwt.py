from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import AppClaims, InvalidToken, mint_app_jwt, verify_app_jwt

SECRET = "x" * 32


def test_mint_then_verify_roundtrip() -> None:
    auth_time = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    token = mint_app_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        is_global_admin=True,
        jti="sess-abc",
        auth_time=auth_time,
        secret=SECRET,
        ttl_minutes=60,
    )
    claims = verify_app_jwt(token, SECRET)
    assert isinstance(claims, AppClaims)
    assert claims.sub == "11111111-1111-1111-1111-111111111111"
    assert claims.is_global_admin is True
    assert claims.jti == "sess-abc"
    assert claims.auth_time == int(auth_time.timestamp())


def test_tampered_token_rejected() -> None:
    token = mint_app_jwt(
        user_id="u",
        is_global_admin=False,
        jti="j",
        auth_time=datetime.now(UTC),
        secret=SECRET,
        ttl_minutes=60,
    )
    with pytest.raises(InvalidToken):
        verify_app_jwt(token + "x", SECRET)


def test_wrong_secret_rejected() -> None:
    token = mint_app_jwt(
        user_id="u",
        is_global_admin=False,
        jti="j",
        auth_time=datetime.now(UTC),
        secret=SECRET,
        ttl_minutes=60,
    )
    with pytest.raises(InvalidToken):
        verify_app_jwt(token, "y" * 32)


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    token = mint_app_jwt(
        user_id="u",
        is_global_admin=False,
        jti="j",
        auth_time=past,
        secret=SECRET,
        ttl_minutes=1,
        now=past,
    )
    with pytest.raises(InvalidToken):
        verify_app_jwt(token, SECRET)


def test_alg_none_token_rejected() -> None:
    """An unsigned (alg=none) token must never be accepted (algorithm confusion)."""
    import base64
    import json

    def _b64(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64(
        {
            "sub": "u",
            "is_global_admin": False,
            "jti": "j",
            "iat": 0,
            "auth_time": 0,
            "exp": 9_999_999_999,
        }
    )
    with pytest.raises(InvalidToken):
        verify_app_jwt(f"{header}.{payload}.", SECRET)


def test_non_bool_is_global_admin_rejected() -> None:
    """A token whose is_global_admin is a string must be rejected, not coerced."""
    import jwt

    forged = jwt.encode(
        {"sub": "u", "is_global_admin": "false", "jti": "j", "iat": 0, "auth_time": 0, "exp": 9_999_999_999},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidToken):
        verify_app_jwt(forged, SECRET)
