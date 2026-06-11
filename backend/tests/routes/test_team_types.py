import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _new_exercise(c, token: str) -> str:
    r = await c.post("/api/v1/exercises", json={"name": "E"}, headers={"Authorization": f"Bearer {token}"})
    return r.json()["data"]["id"]


async def test_list_defaults_then_add_and_dup(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = await _new_exercise(c, token)
        listed = await c.get(f"/api/v1/exercises/{ex}/team-types", headers=h)
        added = await c.post(
            f"/api/v1/exercises/{ex}/team-types",
            json={"type_key": "yellow", "display_label": "Yellow Cell"},
            headers=h,
        )
        dup = await c.post(
            f"/api/v1/exercises/{ex}/team-types",
            json={"type_key": "blue", "display_label": "dup"},
            headers=h,
        )
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 6
    assert added.status_code == 201
    assert dup.status_code == 409


async def test_update_and_delete_team_type(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = await _new_exercise(c, token)
        created = await c.post(
            f"/api/v1/exercises/{ex}/team-types", json={"type_key": "gold", "display_label": "Gold"}, headers=h
        )
        tid = created.json()["data"]["id"]
        patched = await c.patch(
            f"/api/v1/exercises/{ex}/team-types/{tid}", json={"display_label": "Gold Cell"}, headers=h
        )
        deleted = await c.delete(f"/api/v1/exercises/{ex}/team-types/{tid}", headers=h)
    assert patched.status_code == 200
    assert patched.json()["data"]["display_label"] == "Gold Cell"
    assert deleted.status_code == 204
