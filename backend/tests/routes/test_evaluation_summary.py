"""``GET .../reports/{rid}/evaluation-summary`` — the own-team, per-section grade+feedback view.

Visibility rides on the SAME rule as ``report.overall_grade`` elsewhere (``_GradeGate`` in
``routes/v1/reports.py``): a Global Admin or ``scoring:read:all`` holder always sees it; a team
member sees it only once the report is ``evaluated`` AND ``scoring_config.teams_see_own_scores``
is true. "Not yet evaluated" and "hidden by config" are both typed 409s, never a generic error —
this endpoint exists specifically so a writer can use a prior report's feedback as guidance, and
the absence of scores is an expected, common state, not a failure.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


def _summary_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluation-summary"


def _report_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}"


async def _world(migrated_db, c, ah):
    """Submitted report, one numeric 0-10 section, one assigned evaluator.

    Returns (ex, rid, sid, evaluator_headers, evaluation_id).
    """
    ex, rid, sid = await submitted_report(c, ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, "ev-a")
    evid = await assign(c, ah, ex, rid, uid)
    return ex, rid, sid, h, evid


async def _grade_and_finalize(c, ex, rid, evid, sid, value, feedback, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value, "feedback": feedback},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await c.patch(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}",
        json={"overall_feedback": "Solid overall."},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    await finalize(c, headers, ex, rid, evid)


async def _team_member(migrated_db, c, ah, ex, rid, jti, role_key="team_writer"):
    """A holder of ``role_key`` who is also a member of the report's own team."""
    h, uid = await role_holder(migrated_db, c, ah, ex, jti, role_key)
    team_id = (await c.get(_report_url(ex, rid), headers=ah)).json()["data"]["team_id"]
    r = await c.post(f"/api/v1/exercises/{ex}/teams/{team_id}/members", json={"user_id": uid}, headers=ah)
    assert r.status_code == 201, r.text
    return h


async def _other_team_member(migrated_db, c, ah, ex, jti, role_key="team_writer"):
    """A holder of ``role_key`` on a DIFFERENT team from the report under test."""
    team_id = (
        await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "Bravo", "team_type": "blue"}, headers=ah)
    ).json()["data"]["id"]
    h, uid = await role_holder(migrated_db, c, ah, ex, jti, role_key)
    r = await c.post(f"/api/v1/exercises/{ex}/teams/{team_id}/members", json={"user_id": uid}, headers=ah)
    assert r.status_code == 201, r.text
    return h


async def _hide_scores_from_teams(migrated_db, ex):
    async with migrated_db() as s:
        await s.execute(
            text("UPDATE scoring_config SET teams_see_own_scores = false WHERE exercise_id = CAST(:e AS uuid)"),
            {"e": ex},
        )
        await s.commit()


async def test_evaluation_summary_visible_to_own_team_once_evaluated(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        r = await c.get(_summary_url(ex, rid), headers=hw)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["report_id"] == rid
    assert body["overall_grade"] == "8.00"
    assert body["overall_feedback"] == "Solid overall."
    assert body["evaluated_at"] is not None
    assert len(body["section_grades"]) == 1
    sg = body["section_grades"][0]
    assert sg["name"] == "S"
    assert sg["grade"] == "8.00"
    assert sg["feedback"] == "Good structure."


async def test_evaluation_summary_hides_no_evaluator_identity_or_count(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        r = await c.get(_summary_url(ex, rid), headers=hw)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "evaluator_id" not in body
    assert "evaluator_count" not in body
    assert "evaluator_id" not in body["section_grades"][0]


async def test_evaluation_summary_rejects_a_member_of_a_different_team(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        other = await _other_team_member(migrated_db, c, ah, ex, "bravo-writer")
        r = await c.get(_summary_url(ex, rid), headers=other)
    assert r.status_code == 403, r.text


async def test_evaluation_summary_rejects_an_outsider_with_no_role(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        tok, _ = await make_user_token(migrated_db, jti="outsider")
        r = await c.get(_summary_url(ex, rid), headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, r.text


async def test_evaluation_summary_is_a_typed_409_before_the_report_is_evaluated(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)  # not graded/finalized yet
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        r = await c.get(_summary_url(ex, rid), headers=hw)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "not_yet_evaluated"


async def test_evaluation_summary_is_a_typed_409_when_teams_see_own_scores_is_false(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        await _hide_scores_from_teams(migrated_db, ex)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        r = await c.get(_summary_url(ex, rid), headers=hw)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "scores_not_visible"


async def test_evaluation_summary_visible_to_global_admin_regardless_of_config(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _grade_and_finalize(c, ex, rid, evid, sid, "8", "Good structure.", h)
        await _hide_scores_from_teams(migrated_db, ex)
        r = await c.get(_summary_url(ex, rid), headers=ah)
    assert r.status_code == 200, r.text
