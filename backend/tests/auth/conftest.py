from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

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


TOKEN_ENDPOINT = "https://idp.test/token"
AUTHORIZATION_ENDPOINT = "https://idp.test/authorize"
JWKS_URI = "https://idp.test/jwks"


@pytest.fixture()
def fake_idp_transport(mint_id_token: Callable[..., str]) -> httpx.ASGITransport:
    """An ASGI transport whose ``POST /token`` returns a freshly minted id_token."""

    async def token(request: Request) -> JSONResponse:
        form = await request.form()
        if not form.get("code") or not form.get("code_verifier"):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        return JSONResponse({"access_token": "fake-access", "token_type": "Bearer", "id_token": mint_id_token()})

    app = Starlette(routes=[Route("/token", token, methods=["POST"])])
    return httpx.ASGITransport(app=app)
