"""The evaluator's own assignment listing, and the report context on one evaluation.

Both exist for the evaluator queue and the single-evaluation header: before this, the queue
had no cross-report source at all, and the header could only learn the team and submission
time by reading the report row — which a non-member evaluator is refused.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _list_url(ex: str) -> str:
    return f"/api/v1/exercises/{ex}/evaluations"


def _detail_url(ex: str, rid: str, evid: str) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}"


async def test_detail_carries_team_name_and_submitted_time(migrated_db: async_sessionmaker) -> None:
    """The header needs both, and cannot get them from the report row it may not read."""
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        evid = await assign(c, ah, ex, rid, uid1)

        data = (await c.get(_detail_url(ex, rid, evid), headers=h1)).json()["data"]

        assert data["team_name"] == "A"
        assert data["submitted_at"] is not None


async def test_listing_returns_the_callers_own_assignment_with_report_context(
    migrated_db: async_sessionmaker,
) -> None:
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        evid = await assign(c, ah, ex, rid, uid1)

        r = await c.get(_list_url(ex), headers=h1)
        assert r.status_code == 200, r.text
        rows = r.json()["data"]

        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == evid
        assert row["report_id"] == rid
        assert row["report_name"] == "R"
        assert row["team_name"] == "A"
        assert row["template_name"] == "T"
        assert row["submitted_at"] is not None
        assert row["status"] == "assigned"
        assert row["gradable_section_count"] == 1
        assert row["graded_section_count"] == 0


async def test_listing_omits_a_peer_evaluation(migrated_db: async_sessionmaker) -> None:
    """Evaluator isolation: the queue is the caller's own work and nobody else's."""
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "e2")
        mine = await assign(c, ah, ex, rid, uid1)
        await assign(c, ah, ex, rid, uid2)

        rows = (await c.get(_list_url(ex), headers=h1)).json()["data"]

        assert [row["id"] for row in rows] == [mine]


async def test_listing_includes_an_assignment_whose_report_is_not_submitted(
    migrated_db: async_sessionmaker,
) -> None:
    """The queue's "upcoming" band: assigned, but there is nothing to grade yet."""
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        await assign(c, ah, ex, rid, uid1)
        # Pull the report back out of submission; the assignment survives.
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/recall", headers=ah)
        assert r.status_code == 200, r.text

        rows = (await c.get(_list_url(ex), headers=h1)).json()["data"]

        assert len(rows) == 1
        assert rows[0]["submitted_at"] is None


async def test_listing_is_scoped_to_the_exercise_in_the_path(migrated_db: async_sessionmaker) -> None:
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex_a, rid_a, _ = await submitted_report(c, ah)
        ex_b, rid_b, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex_a, "e1")
        # The SAME person, granted the evaluator role in the second exercise too.
        r = await c.post(
            f"/api/v1/exercises/{ex_b}/roles",
            json={"user_id": uid1, "role_key": "evaluator"},
            headers=ah,
        )
        assert r.status_code == 201, r.text
        in_a = await assign(c, ah, ex_a, rid_a, uid1)
        await assign(c, ah, ex_b, rid_b, uid1)

        rows = (await c.get(_list_url(ex_a), headers=h1)).json()["data"]

        assert [row["id"] for row in rows] == [in_a]


async def test_listing_reports_grading_progress(migrated_db: async_sessionmaker) -> None:
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        evid = await assign(c, ah, ex, rid, uid1)
        r = await c.put(
            f"{_detail_url(ex, rid, evid)}/grades/{sid}",
            json={"grade": "7.50"},
            headers=h1,
        )
        assert r.status_code == 200, r.text

        rows = (await c.get(_list_url(ex), headers=h1)).json()["data"]

        assert rows[0]["graded_section_count"] == 1
        assert rows[0]["gradable_section_count"] == 1


async def test_listing_orders_by_deadline_with_undated_last(migrated_db: async_sessionmaker) -> None:
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, undated, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "e1")
        # A second report in the same exercise, this one with a deadline.
        tid = (await c.get(f"/api/v1/exercises/{ex}/reports/{undated}", headers=ah)).json()["data"]["template_id"]
        team = (await c.get(f"/api/v1/exercises/{ex}/teams", headers=ah)).json()["data"][0]["id"]
        dated = (
            await c.post(
                f"/api/v1/exercises/{ex}/reports",
                json={
                    "template_id": tid,
                    "team_id": team,
                    "name": "Dated",
                    "due_at": "2026-09-20T18:00:00Z",
                },
                headers=ah,
            )
        ).json()["data"]["id"]

        dsid = (await c.get(f"/api/v1/exercises/{ex}/reports/{dated}", headers=ah)).json()["data"]["sections"][0]["id"]
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{dated}/sections/{dsid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{dated}/submit", headers=ah)
        assert r.status_code == 200, r.text

        first = await assign(c, ah, ex, dated, uid1)
        second = await assign(c, ah, ex, undated, uid1)

        rows = (await c.get(_list_url(ex), headers=h1)).json()["data"]

        assert [row["id"] for row in rows] == [first, second]
        assert rows[0]["due_at"] is not None
        assert rows[1]["due_at"] is None


@pytest.mark.parametrize("role_key", ["team_writer", "team_approver", "observer"])
async def test_listing_is_denied_to_a_non_evaluator_role(migrated_db: async_sessionmaker, role_key: str) -> None:
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _ = await submitted_report(c, ah)
        h, _uid = await role_holder(migrated_db, c, ah, ex, "other", role_key)

        assert (await c.get(_list_url(ex), headers=h)).status_code == 403
