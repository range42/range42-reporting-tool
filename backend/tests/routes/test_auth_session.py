from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.base import NormalizedClaims
from app.auth.session import start_session
from app.core.config import Settings
from app.main import create_app

SECRET = "x" * 32


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)


def _settings() -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app", JWT_SECRET=SECRET)


async def _seed_token(sm: async_sessionmaker[AsyncSession], **kw: Any) -> str:
    async with sm() as s:
        issued = await start_session(
            s,
            NormalizedClaims(subject="me", email="me@x.test", display_name="Me", provider="oidc"),
            _settings(),
            **kw,
        )
        await s.commit()
        return issued.token


def _client(migrated_db: async_sessionmaker[AsyncSession]) -> AsyncClient:
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.integration
async def test_me_returns_user(env: None, migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _seed_token(migrated_db)
    async with _client(migrated_db) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["email"] == "me@x.test"


@pytest.mark.integration
async def test_logout_invalidates_token(env: None, migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _seed_token(migrated_db)
    async with _client(migrated_db) as c:
        out = await c.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert out.status_code == 200
        after = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401  # session revoked, token now invalid


@pytest.mark.integration
async def test_refresh_reissues(env: None, migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _seed_token(migrated_db, now=datetime.now(UTC) - timedelta(minutes=5))
    async with _client(migrated_db) as c:
        r = await c.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]
