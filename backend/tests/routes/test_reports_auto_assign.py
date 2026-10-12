import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import evaluator, ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


async def _template(c, ah):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": True},
        headers=ah,
    )
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid


async def _team(c, ah, ex, name):
    return (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": name, "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]


async def _submitted_report(c, ah, ex, tid, team_id, name):
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": team_id, "name": name},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    assert r.status_code == 200, r.text
    return rid


async def test_evaluator_on_team_and_campaign_gets_auto_assigned_before_submission(
    migrated_db: async_sessionmaker,
) -> None:
    """Campaign membership added BEFORE submission — the _apply_transition hook path."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah)

        detail = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={"template_id": tid, "team_id": team, "name": "R1"},
                headers=ah,
            )
        ).json()["data"]
        rid, sid = detail["id"], detail["sections"][0]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
        assert r.status_code == 200, r.text

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert {e["report_id"] for e in mine} == {rid}


async def test_evaluator_on_team_and_campaign_gets_auto_assigned_after_submission(
    migrated_db: async_sessionmaker,
) -> None:
    """Campaign membership added AFTER submission — the add_campaign_report hook path."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah)

        rid = await _submitted_report(c, ah, ex, tid, team, "R1")
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert {e["report_id"] for e in mine} == {rid}


async def test_evaluator_on_team_only_is_not_assigned(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        # No campaign_evaluator row for carol -> the intersection is empty.

        rid = await _submitted_report(c, ah, ex, tid, team, "R1")
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert mine == []


async def test_evaluator_on_campaign_only_is_not_assigned(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah)
        # No team_evaluator row for carol on this team -> the intersection is empty.

        rid = await _submitted_report(c, ah, ex, tid, team, "R1")
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert mine == []


async def test_evaluator_on_two_teams_gets_both_campaigns_reports(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        bt1 = await _team(c, ah, ex, "BT1")
        bt2 = await _team(c, ah, ex, "BT2")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        for team in (bt1, bt2):
            await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah)

        rid1 = await _submitted_report(c, ah, ex, tid, bt1, "R1")
        rid2 = await _submitted_report(c, ah, ex, tid, bt2, "R2")
        for rid in (rid1, rid2):
            await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert {e["report_id"] for e in mine} == {rid1, rid2}


async def test_two_evaluators_with_identical_assignments_both_get_the_report(
    migrated_db: async_sessionmaker,
) -> None:
    """Redundant/collaborative grading: same team+campaign rows for two different evaluators."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "carol")
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "dave")
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        for uid in (uid1, uid2):
            await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
            await c.post(
                f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah
            )

        rid = await _submitted_report(c, ah, ex, tid, team, "R1")
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah)

        for h in (h1, h2):
            mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
            assert {e["report_id"] for e in mine} == {rid}


async def test_report_not_in_any_campaign_is_unaffected(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)

        await _submitted_report(c, ah, ex, tid, team, "R1")  # never added to a campaign

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert mine == []


async def test_auto_assign_does_not_duplicate_an_existing_manual_assignment(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
        tid = await _template(c, ah)
        team = await _team(c, ah, ex, "BT1")
        h, uid = await evaluator(migrated_db, c, ah, ex, "carol")
        await c.post(f"/api/v1/exercises/{ex}/teams/{team}/evaluators", json={"evaluator_id": uid}, headers=ah)
        campaign = (await c.post(f"/api/v1/exercises/{ex}/campaigns", json={"name": "SITREP"}, headers=ah)).json()[
            "data"
        ]["id"]
        await c.post(f"/api/v1/exercises/{ex}/campaigns/{campaign}/evaluators", json={"evaluator_id": uid}, headers=ah)

        rid = await _submitted_report(c, ah, ex, tid, team, "R1")
        # Manually assigned first, then the report joins the campaign -> must not double-assign.
        manual = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations", json={"evaluator_id": uid}, headers=ah
        )
        assert manual.status_code == 201, manual.text
        joined = await c.post(
            f"/api/v1/exercises/{ex}/campaigns/{campaign}/reports", json={"report_id": rid}, headers=ah
        )
        assert joined.status_code == 201, joined.text

        mine = (await c.get(f"/api/v1/exercises/{ex}/evaluations", headers=h)).json()["data"]
        assert len(mine) == 1
