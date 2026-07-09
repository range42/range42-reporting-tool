import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ScoringConfig, TeamTypeConfig
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_create_exercise_seeds_defaults(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga1", admin=True)
    async with client(migrated_db) as c:
        r = await c.post(
            "/api/v1/exercises", json={"name": "Cyber Storm"}, headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 201
    ex_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "draft"
    async with migrated_db() as s:
        types = (await s.execute(select(TeamTypeConfig).where(TeamTypeConfig.exercise_id == ex_id))).scalars().all()
        sc = (await s.execute(select(ScoringConfig).where(ScoringConfig.exercise_id == ex_id))).scalar_one_or_none()
    assert len(types) == 6
    assert sc is not None


async def test_create_exercise_forbidden_for_non_admin(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="u1", admin=False)
    async with client(migrated_db) as c:
        r = await c.post("/api/v1/exercises", json={"name": "X"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_get_and_list_and_archive(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex_id = (await c.post("/api/v1/exercises", json={"name": "Y"}, headers=h)).json()["data"]["id"]
        got = await c.get(f"/api/v1/exercises/{ex_id}", headers=h)
        listed = await c.get("/api/v1/exercises", headers=h)
        patched = await c.patch(f"/api/v1/exercises/{ex_id}", json={"name": "Y2"}, headers=h)
        deleted = await c.delete(f"/api/v1/exercises/{ex_id}", headers=h)
        after = await c.get(f"/api/v1/exercises/{ex_id}", headers=h)
    assert got.status_code == 200
    assert listed.status_code == 200 and listed.json()["meta"]["total"] >= 1
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "Y2"
    assert deleted.status_code == 200
    assert after.json()["data"]["status"] == "archived"
