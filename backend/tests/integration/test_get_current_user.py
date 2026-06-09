from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rbac import get_current_user
from app.core.security import mint_app_jwt
from app.models.user import User
from app.models.user_session import UserSession

SECRET = "x" * 32


def _app(sm: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.db_sessionmaker = sm

    @app.get("/whoami")
    async def whoami(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"email": user.email}

    return app


async def _seed_user_and_session(
    sm: async_sessionmaker[AsyncSession], *, jti: str, expires_at: datetime, revoked: bool = False
) -> None:
    async with sm() as s:
        user = User(external_id=f"oidc:{jti}", email="u@x.test", display_name="U")
        s.add(user)
        await s.flush()
        s.add(
            UserSession(
                jti=jti,
                user_id=user.id,
                auth_time=datetime.now(UTC),
                expires_at=expires_at,
                revoked_at=(datetime.now(UTC) if revoked else None),
            )
        )
        await s.commit()


def _token(jti: str) -> str:
    return mint_app_jwt(
        user_id="00000000-0000-0000-0000-000000000000",
        is_global_admin=False,
        jti=jti,
        auth_time=datetime.now(UTC),
        secret=SECRET,
        ttl_minutes=60,
    )


@pytest.fixture(autouse=True)
def _secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)


@pytest.mark.integration
async def test_valid_token_and_session_resolves_user(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    jti = "sess-ok"
    await _seed_user_and_session(migrated_db, jti=jti, expires_at=datetime.now(UTC) + timedelta(hours=1))
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/whoami", headers={"Authorization": f"Bearer {_token(jti)}"})
    assert r.status_code == 200
    assert r.json() == {"email": "u@x.test"}


@pytest.mark.integration
async def test_missing_bearer_is_401(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/whoami")
    assert r.status_code == 401


@pytest.mark.integration
async def test_unknown_session_is_401(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/whoami", headers={"Authorization": f"Bearer {_token('ghost')}"})
    assert r.status_code == 401


@pytest.mark.integration
async def test_revoked_session_is_401(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    jti = "sess-revoked"
    await _seed_user_and_session(migrated_db, jti=jti, expires_at=datetime.now(UTC) + timedelta(hours=1), revoked=True)
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/whoami", headers={"Authorization": f"Bearer {_token(jti)}"})
    assert r.status_code == 401


@pytest.mark.integration
async def test_expired_session_is_401(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    jti = "sess-expired"
    await _seed_user_and_session(
        migrated_db,
        jti=jti,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),  # already expired
    )
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/whoami", headers={"Authorization": f"Bearer {_token(jti)}"})
    assert r.status_code == 401
