import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _mk(c, ah):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    rid = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": team, "name": "R"},
            headers=ah,
        )
    ).json()["data"]["id"]
    return ex, rid


async def test_patch_and_delete_draft(migrated_db: async_sessionmaker) -> None:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    ga, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    ah = {"Authorization": f"Bearer {ga}"}
    async with client(migrated_db) as c:
        ex, rid = await _mk(c, ah)
        patched = await c.patch(f"/api/v1/exercises/{ex}/reports/{rid}", json={"name": "R2"}, headers=ah)
        assert patched.status_code == 200
        assert patched.json()["data"]["name"] == "R2"
        deleted = await c.delete(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)
        assert deleted.status_code == 204
        assert (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).status_code == 404
