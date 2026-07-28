"""WP3 S10 (#81) — campaigns CRUD + timeline/compare reads.

A campaign groups reports across teams/time within an exercise (M2M — a report
may appear in several campaigns). Writes are GA-only like the other authoring
surfaces; reads reuse the report visibility rules (own team, or
``reports:read:all``) — server-side, default-deny.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def _seed(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()


async def _ga(migrated_db):
    await _seed(migrated_db)
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _published_template(c, ah) -> str:
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S", "field_type": "rich_text"}, headers=ah)
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid


async def _exercise_with_two_team_reports(c, ah):
    """Exercise with teams Alpha/Beta, one report each; returns (ex, tid, (team_a, rid_a), (team_b, rid_b))."""
    tid = await _published_template(c, ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    out = []
    for name in ("Alpha", "Beta"):
        team = (
            await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": name, "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": f"R-{name}"},
                headers=ah,
            )
        ).json()["data"]["id"]
        out.append((team, rid))
    return ex, tid, out[0], out[1]


async def _campaign_with_reports(c, ah):
    """Campaign over both team reports; returns (ex, cid, (team_a, rid_a), (team_b, rid_b))."""
    ex, _, a, b = await _exercise_with_two_team_reports(c, ah)
    cid = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C1"}, headers=ah)).json()["data"]["id"]
    for _, rid in (a, b):
        r = await c.post(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports", json={"report_id": rid}, headers=ah)
        assert r.status_code == 201, r.text
    return ex, cid, a, b


# --- CRUD --------------------------------------------------------------------


async def test_campaign_crud_and_audit(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        r = await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C1", "description": "d"}, headers=ah)
        assert r.status_code == 201, r.text
        cid = r.json()["data"]["id"]
        assert r.json()["data"]["report_count"] == 0

        listed = (await c.get(f"/api/v1/exercises/{ex}/campaigns", headers=ah)).json()["data"]
        assert [row["name"] for row in listed] == ["C1"]

        r = await c.patch(f"/api/v1/exercises/{ex}/campaigns/{cid}", json={"name": "C2"}, headers=ah)
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "C2"

        r = await c.delete(f"/api/v1/exercises/{ex}/campaigns/{cid}", headers=ah)
        assert r.status_code == 204
        assert (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}", headers=ah)).status_code == 404
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert {"campaign.create", "campaign.update", "campaign.delete"} <= actions


async def test_campaign_duplicate_name_409(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C1"}, headers=ah)
        r = await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C1"}, headers=ah)
        assert r.status_code == 409


async def test_campaign_unknown_exercise_404(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        r = await c.post(
            "/api/v1/exercises/00000000-0000-0000-0000-000000000000/campaigns", json={"name": "C"}, headers=ah
        )
        assert r.status_code == 404


async def test_campaign_writes_require_global_admin(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    tok, _ = await make_user_token(migrated_db, jti="w", admin=False)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        r = await c.post(
            f"/api/v1/exercises/{ex}/campaigns", json={"name": "C"}, headers={"Authorization": f"Bearer {tok}"}
        )
        assert r.status_code == 403


# --- membership ---------------------------------------------------------------


async def test_add_and_remove_reports(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, cid, (_, rid_a), _ = await _campaign_with_reports(c, ah)
        detail = (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}", headers=ah)).json()["data"]
        assert detail["report_count"] == 2

        # duplicate add
        r = await c.post(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports", json={"report_id": rid_a}, headers=ah)
        assert r.status_code == 409

        r = await c.delete(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports/{rid_a}", headers=ah)
        assert r.status_code == 204
        # remove again -> 404
        r = await c.delete(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports/{rid_a}", headers=ah)
        assert r.status_code == 404
    async with migrated_db() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert {"campaign.report.add", "campaign.report.remove"} <= actions


async def test_add_report_from_other_exercise_422(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, tid, _, _ = await _exercise_with_two_team_reports(c, ah)
        cid = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C"}, headers=ah)).json()["data"]["id"]
        # a report in a different exercise
        ex2 = (await c.post("/api/v1/exercises", json={"name": "E2"}, headers=ah)).json()["data"]["id"]
        team2 = (
            await c.post(f"/api/v1/exercises/{ex2}/teams", json={"name": "X", "team_type": "blue"}, headers=ah)
        ).json()["data"]["id"]
        rid2 = (
            await c.post(
                f"/api/v1/exercises/{ex2}/reports",
                json={"template_id": tid, "team_id": team2, "name": "R2"},
                headers=ah,
            )
        ).json()["data"]["id"]
        r = await c.post(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports", json={"report_id": rid2}, headers=ah)
        assert r.status_code == 422


# --- timeline ------------------------------------------------------------------


async def test_timeline_ordered_and_carries_team(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, cid, (_, rid_a), (_, rid_b) = await _campaign_with_reports(c, ah)
        # submit Beta's report so it gets a submitted_at (submitted sorts before unsubmitted)
        sec = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid_b}", headers=ah)).json()["data"]["sections"][0]
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid_b}/sections/{sec['id']}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>x</p>"}},
            headers=ah,
        )
        await c.post(f"/api/v1/exercises/{ex}/reports/{rid_b}/submit", headers=ah)

        rows = (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/timeline", headers=ah)).json()["data"]
        assert [row["report_id"] for row in rows] == [rid_b, rid_a]
        assert rows[0]["team_name"] == "Beta"
        assert rows[0]["submitted_at"] is not None
        assert rows[1]["submitted_at"] is None


async def test_timeline_scoped_to_own_team(migrated_db: async_sessionmaker) -> None:
    """Cross-team leak test: a team member sees only their team's reports."""
    ah = await _ga(migrated_db)
    tok, uid = await make_user_token(migrated_db, jti="w", admin=False)
    async with client(migrated_db) as c:
        ex, cid, (team_a, rid_a), _ = await _campaign_with_reports(c, ah)
        await c.post(f"/api/v1/exercises/{ex}/teams/{team_a}/members", json={"user_id": uid}, headers=ah)
        await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": uid, "role_key": "team_writer"}, headers=ah)
        wh = {"Authorization": f"Bearer {tok}"}
        rows = (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/timeline", headers=wh)).json()["data"]
        assert [row["report_id"] for row in rows] == [rid_a]


async def test_timeline_observer_sees_all(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    tok, uid = await make_user_token(migrated_db, jti="o", admin=False)
    async with client(migrated_db) as c:
        ex, cid, (_, rid_a), (_, rid_b) = await _campaign_with_reports(c, ah)
        await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": uid, "role_key": "observer"}, headers=ah)
        oh = {"Authorization": f"Bearer {tok}"}
        rows = (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/timeline", headers=oh)).json()["data"]
        assert {row["report_id"] for row in rows} == {rid_a, rid_b}


async def test_reads_require_exercise_role(migrated_db: async_sessionmaker) -> None:
    """Default-deny: a user with no role in the exercise gets 403, not an empty list."""
    ah = await _ga(migrated_db)
    tok, _ = await make_user_token(migrated_db, jti="n", admin=False)
    async with client(migrated_db) as c:
        ex, cid, _, _ = await _campaign_with_reports(c, ah)
        nh = {"Authorization": f"Bearer {tok}"}
        assert (await c.get(f"/api/v1/exercises/{ex}/campaigns", headers=nh)).status_code == 403
        assert (await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/timeline", headers=nh)).status_code == 403


# --- compare -------------------------------------------------------------------


async def test_compare_returns_sections_for_requested_reports(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, cid, (_, rid_a), (_, rid_b) = await _campaign_with_reports(c, ah)
        r = await c.get(
            f"/api/v1/exercises/{ex}/campaigns/{cid}/compare",
            params={"report_ids": [rid_a, rid_b]},
            headers=ah,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert [d["id"] for d in data] == [rid_a, rid_b]
        assert all("sections" in d for d in data)


async def test_compare_report_not_in_campaign_404(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, tid, (_, rid_a), (_, rid_b) = await _exercise_with_two_team_reports(c, ah)
        cid = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "C"}, headers=ah)).json()["data"]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{cid}/reports", json={"report_id": rid_a}, headers=ah)
        r = await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/compare", params={"report_ids": [rid_b]}, headers=ah)
        assert r.status_code == 404


async def test_compare_cross_team_leak_403(migrated_db: async_sessionmaker) -> None:
    """Cross-team leak test: requesting another team's report by id is refused."""
    ah = await _ga(migrated_db)
    tok, uid = await make_user_token(migrated_db, jti="w", admin=False)
    async with client(migrated_db) as c:
        ex, cid, (team_a, _), (_, rid_b) = await _campaign_with_reports(c, ah)
        await c.post(f"/api/v1/exercises/{ex}/teams/{team_a}/members", json={"user_id": uid}, headers=ah)
        await c.post(f"/api/v1/exercises/{ex}/roles", json={"user_id": uid, "role_key": "team_writer"}, headers=ah)
        wh = {"Authorization": f"Bearer {tok}"}
        r = await c.get(f"/api/v1/exercises/{ex}/campaigns/{cid}/compare", params={"report_ids": [rid_b]}, headers=wh)
        assert r.status_code == 403
