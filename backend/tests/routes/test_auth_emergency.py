import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import verify_app_jwt
from app.main import create_app

SECRET = "x" * 32
PASSWORD = "break-glass-please"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _client(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession], *, enabled: bool
) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("EMERGENCY_ADMIN_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("EMERGENCY_ADMIN_PASSWORD_HASH", _hash(PASSWORD))
    app = create_app()
    app.state.db_sessionmaker = migrated_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.integration
async def test_emergency_login_success(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(monkeypatch, migrated_db, enabled=True) as c:
        r = await c.post("/api/v1/auth/emergency-login", json={"password": PASSWORD})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["user"]["is_global_admin"] is True
    assert verify_app_jwt(data["access_token"], SECRET).is_global_admin is True


@pytest.mark.integration
async def test_emergency_login_wrong_password_401(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(monkeypatch, migrated_db, enabled=True) as c:
        r = await c.post("/api/v1/auth/emergency-login", json={"password": "nope"})
    assert r.status_code == 401


@pytest.mark.integration
async def test_emergency_login_disabled_404(
    monkeypatch: pytest.MonkeyPatch, migrated_db: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(monkeypatch, migrated_db, enabled=False) as c:
        r = await c.post("/api/v1/auth/emergency-login", json={"password": PASSWORD})
    assert r.status_code == 404  # gated: do not reveal the endpoint exists
