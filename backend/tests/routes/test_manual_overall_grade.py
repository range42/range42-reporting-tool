"""Task 11 — manual overall-grade override endpoint (M9) + gated grade visibility (M17).

``PUT /exercises/{ex}/reports/{rid}/overall-grade`` is the ONE write to ``report.overall_grade``
from outside the computed path, and it still goes through ``rollup.set_manual_grade`` so the
sole-writer contract (M2) holds literally.

M17: ``ReportOut`` / ``ReportDetailOut`` carry ``overall_grade`` / ``overall_grade_is_manual`` /
``grade_version`` only for Global Admin, ``scoring:read:all`` holders, and team members once the
report is ``evaluated`` AND ``scoring_config.teams_see_own_scores`` is true. Otherwise ``None``.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


# --- arrange helpers ------------------------------------------------------------


def _grade_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/overall-grade"


def _report_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}"


async def _world(migrated_db, c, ah):
    """Submitted report with one numeric 0-10 section and one assigned evaluator.

    Returns (ex, rid, sid, evaluator_headers, evaluation_id).
    """
    ex, rid, sid = await submitted_report(c, ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, "ev-a")
    evid = await assign(c, ah, ex, rid, uid)
    return ex, rid, sid, h, evid


async def _grade_section(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _publish_grade(c, ex, rid, evid, sid, value, headers):
    """Grade a section AND finalize, which is what publishes report.overall_grade under W5-3."""
    await _grade_section(c, ex, rid, evid, sid, value, headers)
    await finalize(c, headers, ex, rid, evid)


async def _report_row(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT overall_grade, overall_grade_is_manual, grade_version "
                    "FROM report WHERE id = CAST(:i AS uuid)"
                ),
                {"i": rid},
            )
        ).one()


async def _sql(migrated_db, stmt, **params):
    async with migrated_db() as s:
        await s.execute(text(stmt), params)
        await s.commit()


async def _team_member(migrated_db, c, ah, ex, rid, jti):
    """A team_writer who is also a member of the report's team — the M17 'team' persona."""
    h, uid = await role_holder(migrated_db, c, ah, ex, jti, "team_writer")
    team_id = (await c.get(_report_url(ex, rid), headers=ah)).json()["data"]["team_id"]
    r = await c.post(f"/api/v1/exercises/{ex}/teams/{team_id}/members", json={"user_id": uid}, headers=ah)
    assert r.status_code == 201, r.text
    return h


# --- the endpoint -----------------------------------------------------------------


async def test_global_admin_sets_a_manual_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "3.5", "reason": "moderated"}, headers=ah)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["report_id"] == rid
    assert body["overall_grade"] == "3.50"
    grade, _is_manual, _version = await _report_row(migrated_db, rid)
    assert str(grade) == "3.50"


async def test_manual_grade_sets_overall_grade_is_manual_true(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["overall_grade_is_manual"] is True
    _grade, is_manual, _version = await _report_row(migrated_db, rid)
    assert is_manual is True


async def test_manual_grade_increments_grade_version(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _publish_grade(c, ex, rid, evid, sid, "9", h)  # computed grade -> version 1
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["grade_version"] == 2
    _grade, _is_manual, version = await _report_row(migrated_db, rid)
    assert version == 2


async def test_manual_grade_survives_a_subsequent_section_grade_save(migrated_db: async_sessionmaker) -> None:
    """M9's whole point: a later section grade must neither overwrite the hand-set number nor
    bump grade_version, because nothing new was published."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)
        assert r.status_code == 200, r.text
        before = await _report_row(migrated_db, rid)
        await _grade_section(c, ex, rid, evid, sid, "9", h)
    after = await _report_row(migrated_db, rid)
    assert str(after.overall_grade) == "3.00"
    assert after.overall_grade_is_manual is True
    assert after.grade_version == before.grade_version


async def test_assigned_evaluator_can_set_a_manual_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, h, _evid = await _world(migrated_db, c, ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "7", "reason": "holistic"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["overall_grade"] == "7.00"


async def test_peer_evaluator_setting_a_manual_grade_returns_403(migrated_db: async_sessionmaker) -> None:
    """D1 (E1) applies: holding evaluations:write is not enough — the caller must be assigned
    to THIS report. A refused write leaves no row behind."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        hpeer, _ = await evaluator(migrated_db, c, ah, ex, "ev-peer")
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "1", "reason": "x"}, headers=hpeer)
    assert r.status_code == 403, r.text
    grade, is_manual, version = await _report_row(migrated_db, rid)
    assert (grade, is_manual, version) == (None, False, 0)


async def test_team_writer_setting_a_manual_grade_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "10", "reason": "we rock"}, headers=hw)
    assert r.status_code == 403, r.text


async def test_manual_grade_without_a_reason_returns_422(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        missing = await c.put(_grade_url(ex, rid), json={"overall_grade": "3"}, headers=ah)
        empty = await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": ""}, headers=ah)
    assert missing.status_code == 422, missing.text
    assert empty.status_code == 422, empty.text
    grade, is_manual, _version = await _report_row(migrated_db, rid)
    assert (grade, is_manual) == (None, False)


async def test_clearing_the_manual_flag_restores_the_computed_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _publish_grade(c, ex, rid, evid, sid, "9", h)
        await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": None, "reason": "reverted"}, headers=ah)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["overall_grade"] == "9.00"
    assert body["overall_grade_is_manual"] is False
    grade, is_manual, _version = await _report_row(migrated_db, rid)
    assert (str(grade), is_manual) == ("9.00", False)


async def test_clearing_the_manual_flag_increments_grade_version(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
        await _publish_grade(c, ex, rid, evid, sid, "9", h)  # v1
        await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)  # v2
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": None, "reason": "reverted"}, headers=ah)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["grade_version"] == 3  # 3.00 -> 9.00 is a new published number


async def test_manual_grade_out_of_numeric_5_2_range_returns_422(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        too_big = await c.put(_grade_url(ex, rid), json={"overall_grade": "1000", "reason": "x"}, headers=ah)
        negative = await c.put(_grade_url(ex, rid), json={"overall_grade": "-1", "reason": "x"}, headers=ah)
        too_fine = await c.put(_grade_url(ex, rid), json={"overall_grade": "8.125", "reason": "x"}, headers=ah)
        ceiling = await c.put(_grade_url(ex, rid), json={"overall_grade": "999.99", "reason": "x"}, headers=ah)
    assert too_big.status_code == 422, too_big.text
    assert negative.status_code == 422, negative.text
    assert too_fine.status_code == 422, too_fine.text
    assert ceiling.status_code == 200, ceiling.text


async def test_manual_grade_writes_grade_set_manually_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, ga_uid = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        r = await c.put(_grade_url(ex, rid), json={"overall_grade": "3", "reason": "moderated"}, headers=ah)
        assert r.status_code == 200, r.text
    async with migrated_db() as s:
        row = (await s.execute(select(AuditLog).where(AuditLog.action == "report.grade_set_manually"))).scalars().one()
    assert row.resource_type == "report"
    assert str(row.resource_id) == rid
    assert str(row.user_id) == ga_uid
    assert row.details["reason"] == "moderated"
    assert row.details["overall_grade"] == "3.00"
    assert row.details["grade_version"] == 1


async def test_manual_grade_route_rejects_an_outsider(migrated_db: async_sessionmaker) -> None:
    """Authenticated, no role in the exercise: the permission dependency 403s before any lookup."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _sid, _h, _evid = await _world(migrated_db, c, ah)
        tok, _ = await make_user_token(migrated_db, jti="outsider")
        r = await c.put(
            _grade_url(ex, rid), json={"overall_grade": "1", "reason": "x"}, headers={"Authorization": f"Bearer {tok}"}
        )
    assert r.status_code == 403, r.text


# --- M17: gated visibility on report reads ---------------------------------------------


async def _graded_world(migrated_db, c, ah):
    """A report with a computed 9.00 grade, still under_evaluation.

    Two evaluators, one finalized: that publishes 9.00 while leaving the finalize gate closed,
    so the report stays ``under_evaluation`` and the M17 status branches below stay meaningful.
    """
    ex, rid, sid, h, evid = await _world(migrated_db, c, ah)
    _h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev-b")
    await assign(c, ah, ex, rid, uid2)
    await _publish_grade(c, ex, rid, evid, sid, "9", h)
    return ex, rid


async def _hide_scores_from_teams(migrated_db, ex):
    await _sql(
        migrated_db,
        "UPDATE scoring_config SET teams_see_own_scores = false WHERE exercise_id = CAST(:e AS uuid)",
        e=ex,
    )


async def _mark_evaluated(migrated_db, rid):
    """W5-3 owns the real transition; until it lands the status is set directly."""
    await _sql(migrated_db, "UPDATE report SET status = 'evaluated' WHERE id = CAST(:i AS uuid)", i=rid)


def _grade_fields(report_json):
    return (report_json["overall_grade"], report_json["overall_grade_is_manual"], report_json["grade_version"])


async def _read_both(c, ex, rid, headers):
    """(detail fields, list-row fields) for the same caller — both surfaces must agree."""
    detail = await c.get(_report_url(ex, rid), headers=headers)
    listing = await c.get(f"/api/v1/exercises/{ex}/reports", headers=headers)
    assert detail.status_code == 200, detail.text
    assert listing.status_code == 200, listing.text
    return _grade_fields(detail.json()["data"]), _grade_fields(listing.json()["data"][0])


HIDDEN = (None, None, None)
SHOWN = ("9.00", False, 1)


async def test_report_out_hides_overall_grade_from_team_when_teams_see_own_scores_is_false(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _graded_world(migrated_db, c, ah)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        await _mark_evaluated(migrated_db, rid)
        await _hide_scores_from_teams(migrated_db, ex)
        assert await _read_both(c, ex, rid, hw) == (HIDDEN, HIDDEN)


async def test_report_out_shows_overall_grade_to_team_once_evaluated_and_allowed(
    migrated_db: async_sessionmaker,
) -> None:
    """The positive branch of M17: evaluated + teams_see_own_scores (default true) -> visible."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _graded_world(migrated_db, c, ah)
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        await _mark_evaluated(migrated_db, rid)
        assert await _read_both(c, ex, rid, hw) == (SHOWN, SHOWN)


async def test_report_out_hides_overall_grade_before_report_is_evaluated(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _graded_world(migrated_db, c, ah)  # under_evaluation, teams_see_own_scores=true
        hw = await _team_member(migrated_db, c, ah, ex, rid, "writer")
        assert await _read_both(c, ex, rid, hw) == (HIDDEN, HIDDEN)


async def test_report_out_shows_overall_grade_to_global_admin_at_any_status(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _graded_world(migrated_db, c, ah)  # under_evaluation
        await _hide_scores_from_teams(migrated_db, ex)
        assert await _read_both(c, ex, rid, ah) == (SHOWN, SHOWN)


async def test_report_out_shows_overall_grade_to_scoring_read_all_holder(migrated_db: async_sessionmaker) -> None:
    """An observer holds scoring:read:all (and reports:read:all) but sits on no team."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid = await _graded_world(migrated_db, c, ah)  # under_evaluation
        hobs, _ = await role_holder(migrated_db, c, ah, ex, "obs", "observer")
        await _hide_scores_from_teams(migrated_db, ex)
        assert await _read_both(c, ex, rid, hobs) == (SHOWN, SHOWN)
