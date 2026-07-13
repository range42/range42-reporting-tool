import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


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
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": team, "name": "R"},
            headers=ah,
        )
    ).json()["data"]
    return ex, detail["id"], detail["sections"][0]["id"]


async def test_submit_blocked_when_required_empty(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk(c, ah)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert r.status_code == 409


async def test_submit_succeeds_when_filled(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk(c, ah)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "submitted"
        assert d["submitted_at"] is not None
        # second submit blocked (not draft)
        again = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert again.status_code == 409
