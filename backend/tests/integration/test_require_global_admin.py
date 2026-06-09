from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rbac import require_global_admin
from app.core.security import mint_app_jwt
from app.models.user import User
from app.models.user_session import UserSession

SECRET = "x" * 32


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)


def _app(sm: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.db_sessionmaker = sm

    @app.get("/admin")
    async def admin(_: User = Depends(require_global_admin)) -> dict[str, bool]:
        return {"ok": True}

    return app


async def _token(sm: async_sessionmaker[AsyncSession], *, jti: str, admin: bool) -> str:
    async with sm() as s:
        u = User(external_id=f"oidc:{jti}", email=f"{jti}@x", display_name="U", is_global_admin=admin)
        s.add(u)
        await s.flush()
        s.add(
            UserSession(
                jti=jti, user_id=u.id, auth_time=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(hours=1)
            )
        )
        await s.commit()
    return mint_app_jwt(
        user_id="0", is_global_admin=admin, jti=jti, auth_time=datetime.now(UTC), secret=SECRET, ttl_minutes=60
    )


@pytest.mark.integration
async def test_global_admin_allowed(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _token(migrated_db, jti="ga-yes", admin=True)
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.integration
async def test_non_admin_forbidden(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _token(migrated_db, jti="ga-no", admin=False)
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
