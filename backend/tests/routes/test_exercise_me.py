import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ExerciseRole
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> dict[str, str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _grant_role(migrated_db: async_sessionmaker, *, user_id: str, exercise_id: str, role_key: str) -> None:
    async with migrated_db() as s:
        s.add(ExerciseRole(user_id=uuid.UUID(user_id), exercise_id=uuid.UUID(exercise_id), role_key=role_key))
        await s.commit()


async def _mk_exercise(c, ah) -> str:
    return (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]


async def test_me_approver_has_approve_capability(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = await _mk_exercise(c, ah)
        tok, uid = await make_user_token(migrated_db, jti="appr", admin=False)
        await _grant_role(migrated_db, user_id=uid, exercise_id=ex, role_key="team_approver")
        r = await c.get(f"/api/v1/exercises/{ex}/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["is_global_admin"] is False
        assert "reports:approve" in d["capabilities"]


async def test_me_plain_member_lacks_approve(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = await _mk_exercise(c, ah)
        tok, uid = await make_user_token(migrated_db, jti="writer", admin=False)
        await _grant_role(migrated_db, user_id=uid, exercise_id=ex, role_key="team_writer")
        r = await c.get(f"/api/v1/exercises/{ex}/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "reports:approve" not in d["capabilities"]
        assert "reports:write" in d["capabilities"]  # sanity: it does resolve the writer's perms


async def test_me_global_admin(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = await _mk_exercise(c, ah)
        r = await c.get(f"/api/v1/exercises/{ex}/me", headers=ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["is_global_admin"] is True


async def test_me_non_member_forbidden(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = await _mk_exercise(c, ah)
        tok, _uid = await make_user_token(migrated_db, jti="outsider", admin=False)
        r = await c.get(f"/api/v1/exercises/{ex}/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
