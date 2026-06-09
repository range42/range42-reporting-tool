from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.oidc import OIDCMetadata, OIDCProvider
from app.core.security import verify_app_jwt
from app.main import create_app
from tests.auth.conftest import AUDIENCE, AUTHORIZATION_ENDPOINT, ISSUER, JWKS_URI, TOKEN_ENDPOINT

SECRET = "x" * 32


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)


def _wire_provider(app: Any, transport: httpx.ASGITransport, resolver: Any) -> None:
    app.state.oidc_provider = OIDCProvider(
        metadata=OIDCMetadata(
            issuer=ISSUER,
            authorization_endpoint=AUTHORIZATION_ENDPOINT,
            token_endpoint=TOKEN_ENDPOINT,
            jwks_uri=JWKS_URI,
        ),
        client_id=AUDIENCE,
        client_secret="shh",
        redirect_uri="https://app.test/api/v1/auth/callback",
        scopes="openid profile email",
        jwks_resolver=resolver,
        transport=transport,
    )


@pytest.mark.integration
async def test_login_then_callback_issues_jwt(
    env: None,
    migrated_db: Any,
    fake_idp_transport: httpx.ASGITransport,
    idp_jwks_resolver: Any,
) -> None:
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    _wire_provider(app, fake_idp_transport, idp_jwks_resolver)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        login = await c.get("/api/v1/auth/login")  # AsyncClient keeps the txn cookie
        assert login.status_code == 302
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        cb = await c.get("/api/v1/auth/callback", params={"code": "auth-code", "state": state})
    assert cb.status_code == 200
    data = cb.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@idp.test"
    assert data["user"]["avatar_url"] == "https://idp.test/alice.png"
    assert verify_app_jwt(data["access_token"], SECRET).sub == data["user"]["id"]


@pytest.mark.integration
async def test_callback_bad_state_is_400(
    env: None, migrated_db: Any, fake_idp_transport: httpx.ASGITransport, idp_jwks_resolver: Any
) -> None:
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    _wire_provider(app, fake_idp_transport, idp_jwks_resolver)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        await c.get("/api/v1/auth/login")
        cb = await c.get("/api/v1/auth/callback", params={"code": "x", "state": "forged"})
    assert cb.status_code == 400


def test_login_503_when_oidc_unconfigured(env: None) -> None:
    import asyncio

    app = create_app()  # no provider wired (lifespan skipped under ASGITransport)
    transport = ASGITransport(app=app)

    async def _go() -> int:
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            return (await c.get("/api/v1/auth/login")).status_code

    assert asyncio.run(_go()) == 503
