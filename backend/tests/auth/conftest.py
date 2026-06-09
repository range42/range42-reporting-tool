from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.test/realms/range42"
AUDIENCE = "range42-client"
KID = "test-key-1"


@pytest.fixture(scope="session")
def idp_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def idp_jwks_resolver(idp_private_key: rsa.RSAPrivateKey) -> Any:
    """A static stand-in for ``jwt.PyJWKClient`` exposing ``get_signing_key_from_jwt``."""
    public_key = idp_private_key.public_key()

    class _Resolver:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            return SimpleNamespace(key=public_key)

    return _Resolver()


@pytest.fixture()
def mint_id_token(idp_private_key: rsa.RSAPrivateKey) -> Callable[..., str]:
    """Mint an RS256 id_token. Override any claim via kwargs; pass ``exp``/``iat`` to test expiry."""

    def _mint(**overrides: Any) -> str:
        import time

        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "idp-subject-123",
            "email": "alice@idp.test",
            "name": "Alice Example",
            "picture": "https://idp.test/alice.png",
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(claims, idp_private_key, algorithm="RS256", headers={"kid": KID})

    return _mint
