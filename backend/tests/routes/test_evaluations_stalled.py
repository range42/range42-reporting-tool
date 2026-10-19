"""The Global-Admin list of reports stuck in ``under_evaluation``, oldest pending activity first."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.evaluation.finalize_gate import ANY_CAN_FINALIZE
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, submitted_report
from tests.routes._helpers import client
from tests.routes.test_evaluations_breakdown import _grade, _set_policy

pytestmark = pytest.mark.integration


def _url(ex: str) -> str:
    return f"/api/v1/exercises/{ex}/stalled-reports"


async def _sibling_report(c, ah, ex: str, rid: str, name: str) -> tuple[str, str]:
    """Submit another report in ``rid``'s exercise, same template and team. Returns (rid, sid)."""
    src = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": src["template_id"], "team_id": src["team_id"], "name": name},
            headers=ah,
        )
    ).json()["data"]
    new_rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.patch(
        f"/api/v1/exercises/{ex}/reports/{new_rid}/sections/{sid}",
        json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
        headers=ah,
    )
    r = await c.post(f"/api/v1/exercises/{ex}/reports/{new_rid}/submit", headers=ah)
    assert r.json()["data"]["status"] == "submitted", r.text
    return new_rid, sid


async def _start_grading(migrated_db, c, ah, ex, rid, sid, jti):
    """Assign a fresh evaluator and grade, which moves the report to under_evaluation."""
    h, uid = await evaluator(migrated_db, c, ah, ex, jti)
    evid = await assign(c, ah, ex, rid, uid)
    await _grade(c, ex, rid, evid, sid, "5", h)
    return h, evid


async def _backdate(migrated_db, evid: str, days: int) -> None:
    async with migrated_db() as s:
        for table, column in (("evaluation", "id"), ("section_grade", "evaluation_id")):
            await s.execute(
                text(
                    f"UPDATE {table} SET updated_at = now() - make_interval(days => :d) "
                    f"WHERE {column} = CAST(:e AS uuid)"
                ),
                {"d": days, "e": evid},
            )
        await s.commit()


async def test_stalled_lists_only_under_evaluation_reports(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, graded_rid, sid = await submitted_report(c, ah)
        await _start_grading(migrated_db, c, ah, ex, graded_rid, sid, "st-a")
        untouched_rid, _ = await _sibling_report(c, ah, ex, graded_rid, "untouched")
        done_rid, done_sid = await _sibling_report(c, ah, ex, graded_rid, "done")
        h, evid = await _start_grading(migrated_db, c, ah, ex, done_rid, done_sid, "st-b")
        await finalize(c, h, ex, done_rid, evid)

        # Act
        r = await c.get(_url(ex), headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["reports"]
    assert [row["report_id"] for row in rows] == [graded_rid]
    assert untouched_rid not in {row["report_id"] for row in rows}
    row = rows[0]
    assert row["report_name"] == "R"
    assert row["team_name"] == "A"
    assert row["under_evaluation_since"] is not None


async def test_stalled_counts_counted_and_completed_evaluators(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        h_a, evid_a = await _start_grading(migrated_db, c, ah, ex, rid, sid, "st-a")
        await _start_grading(migrated_db, c, ah, ex, rid, sid, "st-b")
        await finalize(c, h_a, ex, rid, evid_a)

        # Act
        r = await c.get(_url(ex), headers=ah)

    # Assert
    row = r.json()["data"]["reports"][0]
    assert row["counted_evaluator_count"] == 2
    assert row["completed_evaluator_count"] == 1
    assert row["oldest_pending_activity_at"] is not None


async def test_stalled_orders_oldest_pending_activity_first(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, fresh_rid, sid = await submitted_report(c, ah)
        await _start_grading(migrated_db, c, ah, ex, fresh_rid, sid, "st-a")
        old_rid, old_sid = await _sibling_report(c, ah, ex, fresh_rid, "old")
        _, old_evid = await _start_grading(migrated_db, c, ah, ex, old_rid, old_sid, "st-b")
        await _backdate(migrated_db, old_evid, days=9)

        # Act
        r = await c.get(_url(ex), headers=ah)

    # Assert
    assert [row["report_id"] for row in r.json()["data"]["reports"]] == [old_rid, fresh_rid]


async def test_stalled_puts_reports_with_no_pending_evaluator_first(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, active_rid, sid = await submitted_report(c, ah)
        _, active_evid = await _start_grading(migrated_db, c, ah, ex, active_rid, sid, "st-a")
        await _backdate(migrated_db, active_evid, days=30)
        orphan_rid, orphan_sid = await _sibling_report(c, ah, ex, active_rid, "orphan")
        _, orphan_evid = await _start_grading(migrated_db, c, ah, ex, orphan_rid, orphan_sid, "st-b")
        unassigned = await c.post(
            f"/api/v1/exercises/{ex}/reports/{orphan_rid}/evaluations/{orphan_evid}/unassign",
            json={"reason": "left the org"},
            headers=ah,
        )
        assert unassigned.status_code == 200, unassigned.text

        # Act
        r = await c.get(_url(ex), headers=ah)

    # Assert
    rows = r.json()["data"]["reports"]
    assert [row["report_id"] for row in rows] == [orphan_rid, active_rid]
    assert rows[0]["oldest_pending_activity_at"] is None
    assert rows[0]["counted_evaluator_count"] == 0


async def test_stalled_reports_the_exercise_finalize_policy(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, _rid, _sid = await submitted_report(c, ah)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)

        # Act
        r = await c.get(_url(ex), headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"finalize_policy": ANY_CAN_FINALIZE, "reports": []}


async def test_stalled_refuses_a_non_admin(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        h, _evid = await _start_grading(migrated_db, c, ah, ex, rid, sid, "st-a")

        # Act
        r = await c.get(_url(ex), headers=h)

    # Assert
    assert r.status_code == 403


async def test_stalled_returns_404_for_an_unknown_exercise(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)

        # Act
        r = await c.get(_url("00000000-0000-0000-0000-000000000000"), headers=ah)

    # Assert
    assert r.status_code == 404
