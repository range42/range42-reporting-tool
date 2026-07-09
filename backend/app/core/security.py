"""Token verification boundaries (shape reservation — no impl yet).

Two distinct token families exist, with different trust models:

1. **App JWT (outbound, ours).** Signed HS256 with ``JWT_SECRET``. We mint these
   for our own sessions and we are the *sole* verifier — the same symmetric
   secret signs and verifies, so it must never leave the backend. No key
   rotation/JWKS infrastructure is needed for these in v1.

2. **OIDC provider tokens (inbound, theirs).** Issued by the external identity
   provider during login. These are validated against the **provider's** JWKS
   (asymmetric: the provider holds the private key, we fetch its public keys
   from the JWKS endpoint advertised at ``OIDC_ISSUER_URL``). We never hold an
   asymmetric private key — there is no asymmetric key management on our side
   for v1.

Implementations (mint/verify app JWTs, JWKS fetch + cache + verify) land in WP2.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import jwt
from jwt import PyJWK

# HS256: the only algorithm we use to sign/verify our own app JWTs.
APP_JWT_ALGORITHM = "HS256"


class InvalidToken(Exception):
    """Raised when an app-JWT fails signature, expiry, or structural validation."""


@dataclass(frozen=True)
class AppClaims:
    """Decoded app-JWT payload (minimal-claims model, see design L1)."""

    sub: str
    is_global_admin: bool
    jti: str
    iat: int
    auth_time: int
    exp: int


def mint_app_jwt(
    *,
    user_id: str,
    is_global_admin: bool,
    jti: str,
    auth_time: datetime,
    secret: str,
    ttl_minutes: int,
    now: datetime | None = None,
) -> str:
    """Sign a minimal-claims app-JWT (HS256). ``now`` is injectable for testing."""
    issued = now or datetime.now(UTC)
    if issued.tzinfo is None or auth_time.tzinfo is None:
        raise ValueError("mint_app_jwt requires timezone-aware datetimes")
    payload = {
        "sub": user_id,
        "is_global_admin": is_global_admin,
        "jti": jti,
        "iat": int(issued.timestamp()),
        "auth_time": int(auth_time.timestamp()),
        "exp": int((issued + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=APP_JWT_ALGORITHM)


def verify_app_jwt(token: str, secret: str) -> AppClaims:
    """Verify signature + expiry and return typed claims. Raises ``InvalidToken``.

    ``iat`` is treated as informational only; PyJWT's default strict ``iat <= now``
    check is disabled so that tokens minted with an injected future ``now`` (used in
    tests and in refresh flows) are not spuriously rejected.  The meaningful
    time-bound is ``exp``, which is always verified.
    """
    try:
        data = jwt.decode(token, secret, algorithms=[APP_JWT_ALGORITHM], options={"verify_iat": False})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    try:
        is_admin = data["is_global_admin"]
        if not isinstance(is_admin, bool):
            raise InvalidToken("is_global_admin must be a boolean")
        return AppClaims(
            sub=str(data["sub"]),
            is_global_admin=is_admin,
            jti=str(data["jti"]),
            iat=int(data["iat"]),
            auth_time=int(data["auth_time"]),
            exp=int(data["exp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken(f"malformed claims: {exc}") from exc


class InvalidProviderToken(Exception):
    """Raised when an inbound OIDC id_token fails JWKS signature/claim validation."""


class SigningKeyResolver(Protocol):
    """Structural seam over ``jwt.PyJWKClient`` so tests can inject a static key."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


def verify_provider_id_token(
    token: str,
    *,
    jwks_resolver: SigningKeyResolver,
    issuer: str,
    audience: str,
) -> dict[str, object]:
    """Verify an inbound OIDC id_token against the provider's JWKS (RS256).

    ``jwks_resolver`` is a ``jwt.PyJWKClient`` in production (fetches + caches the
    provider's public keys) and a static test double under the fake-IdP harness.
    Validates signature, ``iss``, ``aud``, ``exp`` and returns the claims dict.
    Raises ``InvalidProviderToken`` on any failure.
    """
    try:
        signing_key = jwks_resolver.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidProviderToken(str(exc)) from exc
    return dict(claims)
