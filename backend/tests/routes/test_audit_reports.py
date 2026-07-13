import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
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


async def _count_audit(migrated_db) -> int:
    async with migrated_db() as s:
        return (await s.execute(select(func.count()).select_from(AuditLog))).scalar_one()


async def test_report_flow_is_audited(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk(c, ah)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert {"report.create", "report_section.update", "report.submit"} <= actions


async def test_failed_reads_and_stale_saves_emit_no_audit(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk(c, ah)
        before = await _count_audit(migrated_db)

        missing = await c.get(f"/api/v1/exercises/{ex}/reports/{uuid.uuid4()}", headers=ah)
        assert missing.status_code == 404

        stale = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 999, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
            headers=ah,
        )
        assert stale.status_code == 409

        after = await _count_audit(migrated_db)
    assert after == before
