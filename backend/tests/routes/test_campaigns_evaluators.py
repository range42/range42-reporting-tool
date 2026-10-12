import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import evaluator, ga_headers
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _exercise_and_campaign(c, h, name: str = "C") -> tuple[str, str]:
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=h)).json()["data"]["id"]
    resp = await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": name}, headers=h)
    cid = resp.json()["data"]["id"]
    return ex, cid


async def test_add_list_remove_campaign_evaluator(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, cid = await _exercise_and_campaign(c, ah)
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        added = await c.post(
            f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", json={"evaluator_id": uid}, headers=ah
        )
        assert added.status_code == 201, added.text
        listed = await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", headers=ah)
        assert [e["evaluator_id"] for e in listed.json()["data"]] == [uid]
        removed = await c.delete(f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators/{uid}", headers=ah)
        assert removed.status_code == 204
        listed_after = await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", headers=ah)
        assert listed_after.json()["data"] == []


async def test_add_campaign_evaluator_rejects_duplicate(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db, jti="ga2")
    async with client(migrated_db) as c:
        ex, cid = await _exercise_and_campaign(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "carol2")
        first = await c.post(
            f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", json={"evaluator_id": uid}, headers=ah
        )
        assert first.status_code == 201
        dup = await c.post(f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", json={"evaluator_id": uid}, headers=ah)
        assert dup.status_code == 409


async def test_add_campaign_evaluator_rejects_non_evaluator_user(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="ga3", admin=True)
    ah = {"Authorization": f"Bearer {token}"}
    _, rando_id = await make_user_token(migrated_db, jti="rando", admin=False)
    async with client(migrated_db) as c:
        ex, cid = await _exercise_and_campaign(c, ah)
        r = await c.post(
            f"/api/v1/exercises/{ex}/campaigns/{cid}/evaluators", json={"evaluator_id": rando_id}, headers=ah
        )
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "user_is_not_an_evaluator"
