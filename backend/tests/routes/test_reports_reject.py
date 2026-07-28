import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _ga(migrated_db: async_sessionmaker) -> dict[str, str]:
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _mk_pending(c, ah) -> tuple[str, str]:
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
            json={"template_id": tid, "team_id": team, "name": "R", "approval_required": True},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    return ex, rid


async def _audit_count(migrated_db: async_sessionmaker, action: str) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


async def test_reject_returns_to_draft_with_comment(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending(c, ah)
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/reject", json={"comment": "needs work"}, headers=ah)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "draft"
        assert d["submitted_at"] is None
        assert len(d["approval_records"]) == 1
        assert d["approval_records"][0]["action"] == "rejected"
        assert d["approval_records"][0]["comment"] == "needs work"
    assert await _audit_count(migrated_db, "report.reject") == 1


async def test_reject_requires_comment(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _mk_pending(c, ah)
        empty = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/reject", json={}, headers=ah)
        assert empty.status_code == 422
        blank = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/reject", json={"comment": ""}, headers=ah)
        assert blank.status_code == 422


async def test_reject_requires_pending(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        # draft (never submitted) cannot be rejected
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
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R"},
                headers=ah,
            )
        ).json()["data"]["id"]
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/reject", json={"comment": "x"}, headers=ah)
        assert r.status_code == 409
