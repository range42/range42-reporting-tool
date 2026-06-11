import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _exercise(c, token: str) -> str:
    r = await c.post("/api/v1/exercises", json={"name": "E"}, headers={"Authorization": f"Bearer {token}"})
    return r.json()["data"]["id"]


async def test_team_create_validates_type_and_uniqueness(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = await _exercise(c, token)
        ok = await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=h)
        bad_type = await c.post(
            f"/api/v1/exercises/{ex}/teams", json={"name": "Beta", "team_type": "chartreuse"}, headers=h
        )
        dup = await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "red"}, headers=h)
    assert ok.status_code == 201
    assert bad_type.status_code == 400
    assert dup.status_code == 409


async def test_team_get_list_patch_delete(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = await _exercise(c, token)
        create_r = await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Alpha", "team_type": "blue"}, headers=h)
        tid = create_r.json()["data"]["id"]
        got = await c.get(f"/api/v1/exercises/{ex}/teams/{tid}", headers=h)
        listed = await c.get(f"/api/v1/exercises/{ex}/teams", headers=h)
        patched = await c.patch(f"/api/v1/exercises/{ex}/teams/{tid}", json={"name": "Alpha2"}, headers=h)
        deleted = await c.delete(f"/api/v1/exercises/{ex}/teams/{tid}", headers=h)
    assert got.status_code == 200
    assert got.json()["data"]["members"] == []
    assert listed.status_code == 200 and len(listed.json()["data"]) == 1
    assert patched.status_code == 200 and patched.json()["data"]["name"] == "Alpha2"
    assert deleted.status_code == 204
