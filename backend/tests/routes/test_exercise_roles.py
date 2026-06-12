import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_assign_list_delete_role(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    _, member_id = await make_user_token(migrated_db, jti="u", admin=False)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        role_payload = {"user_id": member_id, "role_key": "team_writer"}
        ok = await c.post(f"/api/v1/exercises/{ex}/roles", json=role_payload, headers=h)
        dup = await c.post(f"/api/v1/exercises/{ex}/roles", json=role_payload, headers=h)
        bad_payload = {"user_id": member_id, "role_key": "no_such_role"}
        bad = await c.post(f"/api/v1/exercises/{ex}/roles", json=bad_payload, headers=h)
        listed = await c.get(f"/api/v1/exercises/{ex}/roles", headers=h)
        rid = ok.json()["data"]["id"]
        deleted = await c.delete(f"/api/v1/exercises/{ex}/roles/{rid}", headers=h)
    assert ok.status_code == 201
    assert dup.status_code == 409
    assert bad.status_code == 400
    assert len(listed.json()["data"]) == 1
    assert deleted.status_code == 204


async def test_assign_role_unknown_user_404(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    token, _ = await make_user_token(migrated_db, jti="ga2", admin=True)
    h = {"Authorization": f"Bearer {token}"}
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
        r = await c.post(
            f"/api/v1/exercises/{ex}/roles",
            json={"user_id": "00000000-0000-0000-0000-000000000000", "role_key": "team_writer"},
            headers=h,
        )
    assert r.status_code == 404
