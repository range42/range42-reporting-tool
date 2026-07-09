from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rbac import AuthContext, get_auth_context
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

    @app.get("/ctx")
    async def ctx(c: AuthContext = Depends(get_auth_context)) -> dict[str, str]:
        return {"email": c.user.email, "jti": c.session.jti}

    return app


@pytest.mark.integration
async def test_auth_context_exposes_user_and_session(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    jti = "ctx-jti"
    async with migrated_db() as s:
        u = User(external_id="oidc:ctx", email="ctx@x.test", display_name="Ctx")
        s.add(u)
        await s.flush()
        s.add(
            UserSession(
                jti=jti, user_id=u.id, auth_time=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(hours=1)
            )
        )
        await s.commit()
    token = mint_app_jwt(
        user_id="00000000-0000-0000-0000-000000000000",
        is_global_admin=False,
        jti=jti,
        auth_time=datetime.now(UTC),
        secret=SECRET,
        ttl_minutes=60,
    )
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        r = await cl.get("/ctx", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"email": "ctx@x.test", "jti": jti}
