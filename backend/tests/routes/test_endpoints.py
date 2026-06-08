import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)


@pytest.mark.asyncio
async def test_ping(env: None) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/ping")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_config_branding(env: None) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/config")
    body = r.json()["data"]
    assert body["app_name"] == "Reporting Tool"
    assert body["primary_color"].startswith("#")


@pytest.mark.asyncio
async def test_health_oidc_disabled(env: None) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/v1/health")
    checks = r.json()["data"]["checks"]
    assert checks["oidc_provider"] == "disabled"
    assert "version" in r.json()["data"]
