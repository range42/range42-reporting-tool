import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _mk_report(c, ah, *, char_limit=None, field_type="rich_text", choice_config=None):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    sec = {"name": "S", "field_type": field_type, "is_required": True}
    if char_limit is not None:
        sec["char_limit"] = char_limit
    if choice_config is not None:
        sec["choice_config"] = choice_config
    await c.post(f"/api/v1/templates/{tid}/sections", json=sec, headers=ah)
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


async def _ga(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def test_save_rich_text_sanitizes_and_counts(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={
                "version": 1,
                "body": {"kind": "rich_text", "content": "<p>hi <strong>there</strong></p><script>x()</script>"},
            },
            headers=ah,
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "<script>" not in d["content"]
        assert d["content_plain"] == "hi there"
        assert d["char_count"] == len("hi there")
        assert d["version"] == 2


async def test_save_char_limit_exceeded_422(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah, char_limit=3)
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>toolong</p>"}},
            headers=ah,
        )
        assert r.status_code == 422


async def test_save_stale_version_409(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>a</p>"}},
            headers=ah,
        )
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>b</p>"}},
            headers=ah,
        )
        assert r.status_code == 409


async def test_save_field_type_mismatch_422(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)  # rich_text section
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "choice", "choice_values": ["a"]}},
            headers=ah,
        )
        assert r.status_code == 422


async def test_save_choice_validates_codes_and_cardinality(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    cfg = {
        "selection": "single",
        "values": [
            {"code": "a", "label": "A", "position": 0, "deprecated_at": None},
            {"code": "b", "label": "B", "position": 1, "deprecated_at": None},
        ],
    }
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah, field_type="choice", choice_config=cfg)
        ok = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "choice", "choice_values": ["a"]}},
            headers=ah,
        )
        assert ok.status_code == 200
        assert ok.json()["data"]["choice_values"] == ["a"]
        bad_code = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 2, "body": {"kind": "choice", "choice_values": ["zzz"]}},
            headers=ah,
        )
        assert bad_code.status_code == 422
        too_many = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 2, "body": {"kind": "choice", "choice_values": ["a", "b"]}},
            headers=ah,
        )
        assert too_many.status_code == 422
