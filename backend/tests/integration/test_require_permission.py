import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rbac import require_permission
from app.core.security import mint_app_jwt
from app.models.exercise_role import ExerciseRole
from app.models.user import User
from app.models.user_session import UserSession
from app.seed import seed_system_roles

SECRET = "x" * 32
EX = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)


def _app(sm: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.db_sessionmaker = sm

    @app.get("/exercises/{exercise_id}/write")
    async def write(exercise_id: uuid.UUID, _: None = Depends(require_permission("reports:write"))) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/exercises/{exercise_id}/approve")
    async def approve(
        exercise_id: uuid.UUID, _: None = Depends(require_permission("reports:approve"))
    ) -> dict[str, bool]:
        return {"ok": True}

    return app


async def _setup(sm: async_sessionmaker[AsyncSession], *, jti: str, role_keys: list[str], admin: bool = False) -> str:
    async with sm() as s:
        await seed_system_roles(s)
        u = User(external_id=f"oidc:{jti}", email=f"{jti}@x", display_name="U", is_global_admin=admin)
        s.add(u)
        await s.flush()
        s.add(
            UserSession(
                jti=jti, user_id=u.id, auth_time=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(hours=1)
            )
        )
        for rk in role_keys:
            s.add(ExerciseRole(exercise_id=EX, user_id=u.id, role_key=rk))
        await s.commit()
    return mint_app_jwt(
        user_id="0", is_global_admin=admin, jti=jti, auth_time=datetime.now(UTC), secret=SECRET, ttl_minutes=60
    )


def _url(path: str) -> str:
    return f"/exercises/{EX}/{path}"


@pytest.mark.integration
async def test_role_with_permission_allowed(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _setup(migrated_db, jti="rp-w", role_keys=["team_writer"])
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get(_url("write"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.integration
async def test_role_without_permission_forbidden(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _setup(migrated_db, jti="rp-noapprove", role_keys=["team_writer"])
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get(_url("approve"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.integration
async def test_no_role_in_exercise_forbidden(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _setup(migrated_db, jti="rp-none", role_keys=[])
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get(_url("write"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.integration
async def test_global_admin_bypass(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _setup(migrated_db, jti="rp-admin", role_keys=[], admin=True)
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get(_url("approve"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.integration
async def test_or_across_multiple_roles(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    token = await _setup(migrated_db, jti="rp-both", role_keys=["team_writer", "team_approver"])
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        w = await c.get(_url("write"), headers={"Authorization": f"Bearer {token}"})
        a = await c.get(_url("approve"), headers={"Authorization": f"Bearer {token}"})
    assert w.status_code == 200
    assert a.status_code == 200


@pytest.mark.integration
async def test_role_in_other_exercise_does_not_grant_here(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    # User has team_writer in EX, but requests a write in a DIFFERENT exercise → 403.
    token = await _setup(migrated_db, jti="rp-xexercise", role_keys=["team_writer"])
    other = uuid.UUID("33333333-3333-3333-3333-333333333333")
    async with AsyncClient(transport=ASGITransport(app=_app(migrated_db)), base_url="http://t") as c:
        r = await c.get(f"/exercises/{other}/write", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
