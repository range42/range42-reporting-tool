"""Integration tests: audit rows are recorded on successful login (WP2 E5)."""

from typing import Any
from urllib.parse import parse_qs, urlparse

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.oidc import OIDCMetadata, OIDCProvider
from app.main import create_app
from app.models import AuditLog
from tests.auth.conftest import AUDIENCE, AUTHORIZATION_ENDPOINT, ISSUER, JWKS_URI, TOKEN_ENDPOINT

SECRET = "x" * 32
PASSWORD = "break-glass-please"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _emergency_client(monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("EMERGENCY_ADMIN_ENABLED", "true")
    monkeypatch.setenv("EMERGENCY_ADMIN_PASSWORD_HASH", _hash(PASSWORD))
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _wire_provider(app: Any, transport: Any, resolver: Any) -> None:
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
async def test_emergency_login_records_audit_row(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]
) -> None:
    async with _emergency_client(monkeypatch, migrated_db) as c:
        r = await c.post("/api/v1/auth/emergency-login", json={"password": PASSWORD})
    assert r.status_code == 200

    async with migrated_db() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.action == "auth.emergency_login"))
        rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].user_id is not None
    assert rows[0].details == {"provider": "emergency"}


@pytest.mark.integration
async def test_failed_emergency_login_emits_no_audit(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]
) -> None:
    async with _emergency_client(monkeypatch, migrated_db) as c:
        r = await c.post("/api/v1/auth/emergency-login", json={"password": "wrong-password"})
    assert r.status_code == 401

    async with migrated_db() as session:
        n = (
            await session.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "auth.emergency_login")
            )
        ).scalar_one()
    assert n == 0


@pytest.mark.integration
async def test_oidc_callback_records_audit_row(
    monkeypatch: pytest.MonkeyPatch,
    migrated_db: async_sessionmaker[AsyncSession],
    fake_idp_transport: Any,
    idp_jwks_resolver: Any,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    _wire_provider(app, fake_idp_transport, idp_jwks_resolver)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        login = await c.get("/api/v1/auth/login")
        assert login.status_code == 302
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        cb = await c.get("/api/v1/auth/callback", params={"code": "auth-code", "state": state})
    assert cb.status_code == 200

    async with migrated_db() as session:
        rows = (await session.execute(select(AuditLog).where(AuditLog.action == "auth.login"))).scalars().all()

    assert len(rows) == 1
    assert rows[0].user_id is not None
    assert rows[0].details is not None
    assert isinstance(rows[0].details.get("provider"), str) and rows[0].details["provider"]
