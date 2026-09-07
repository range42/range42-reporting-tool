"""Task 8 — the grade write and its rollup are ONE transaction, plus the B6 delete route.

M13's whole point: a saved grade whose rollup failed would leave the report advertising a
stale overall_grade with no way to notice. Either both land or neither does.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.scoring import rollup
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

NUMERIC = {"grade_mode": "numeric", "grade_min": 0, "grade_max": 10}


async def _arrange(migrated_db, c, ah, *, jti="ev1"):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "sitrep"}, headers=ah)).json()["data"][
        "id"
    ]
    r = await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": False, **NUMERIC},
        headers=ah,
    )
    assert r.status_code == 201, r.text
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
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, jti)
    return ex, rid, sid, h, await assign(c, ah, ex, rid, uid)


def _grade_url(ex, rid, evid, sid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}"


async def _scalar(migrated_db, sql, **params):
    async with migrated_db() as s:
        return (await s.execute(text(sql), params)).scalar_one()


async def _overall(migrated_db, rid):
    return await _scalar(migrated_db, "SELECT overall_grade FROM report WHERE id = CAST(:i AS uuid)", i=rid)


# --- atomicity ----------------------------------------------------------------


async def test_grade_save_and_rollup_commit_atomically(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        assert (await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)).status_code == 200
        # W5-3 L7: the grade is published by the finalize, in that request's transaction.
        await finalize(c, h, ex, rid, evid)
    assert await _scalar(migrated_db, "SELECT count(*) FROM section_grade") == 1
    assert await _overall(migrated_db, rid) == Decimal("8.00")


async def test_rollup_failure_rolls_back_the_section_grade_write(
    migrated_db: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the rollup raises, the grade must not survive — proving one transaction, not two."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)

        def _boom(*a, **kw):
            raise RuntimeError("rollup exploded")

        monkeypatch.setattr(rollup, "aggregate_overall_grade", _boom)
        with pytest.raises(RuntimeError):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
    assert await _scalar(migrated_db, "SELECT count(*) FROM section_grade") == 0
    assert await _overall(migrated_db, rid) is None


async def test_evaluation_out_exposes_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        before = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=h)).json()["data"]
        assert before["overall_grade"] is None
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        after = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=h)).json()["data"]
    assert after["overall_grade"] == "8.00"


# --- B6 delete route ------------------------------------------------------------


async def test_delete_grade_recomputes_the_report_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1")
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.put(_grade_url(ex, rid, evid1, sid), json={"grade": "9"}, headers=h1)
        await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "5"}, headers=h2)
        await finalize(c, h1, ex, rid, evid1)
        await finalize(c, h2, ex, rid, evid2)
        assert await _overall(migrated_db, rid) == Decimal("7.00")
        # A finalized evaluation refuses grade edits, so ev2 is reopened by hand (W5-4 owns
        # the real route) to prove the delete still drives a recompute.
        async with migrated_db() as s2:
            await s2.execute(
                text("UPDATE evaluation SET status = 'in_progress' WHERE id = CAST(:i AS uuid)"), {"i": evid2}
            )
            await s2.execute(
                text("UPDATE report SET status = 'under_evaluation' WHERE id = CAST(:i AS uuid)"), {"i": rid}
            )
            await s2.commit()
        assert (await c.delete(_grade_url(ex, rid, evid2, sid), headers=h2)).status_code == 204
    assert await _overall(migrated_db, rid) == Decimal("9.00")


async def test_removing_the_only_grade_sets_report_overall_grade_to_null(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        assert (await c.delete(_grade_url(ex, rid, evid, sid), headers=h)).status_code == 204
    # NULL, never 0 — "ungraded" and "scored zero" must stay distinguishable.
    assert await _overall(migrated_db, rid) is None
    assert await _scalar(migrated_db, "SELECT count(*) FROM section_grade") == 0


async def test_delete_grade_by_a_peer_evaluator_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h1, evid1 = await _arrange(migrated_db, c, ah, jti="ev1")
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.put(_grade_url(ex, rid, evid2, sid), json={"grade": "5"}, headers=h2)
        # D1 still holds on the new verb.
        assert (await c.delete(_grade_url(ex, rid, evid2, sid), headers=h1)).status_code == 403
    assert await _scalar(migrated_db, "SELECT count(*) FROM section_grade") == 1


async def test_delete_of_a_grade_that_does_not_exist_returns_404(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        assert (await c.delete(_grade_url(ex, rid, evid, sid), headers=h)).status_code == 404


async def test_delete_grade_emits_an_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await c.delete(_grade_url(ex, rid, evid, sid), headers=h)
    assert await _scalar(migrated_db, "SELECT count(*) FROM audit_log WHERE action = 'section_grade.deleted'") == 1


async def test_delete_grade_on_a_completed_evaluation_returns_409(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        async with migrated_db() as s:
            await s.execute(text("UPDATE evaluation SET status = 'completed' WHERE id = CAST(:i AS uuid)"), {"i": evid})
            await s.commit()
        assert (await c.delete(_grade_url(ex, rid, evid, sid), headers=h)).status_code == 409
    assert await _scalar(migrated_db, "SELECT count(*) FROM section_grade") == 1
