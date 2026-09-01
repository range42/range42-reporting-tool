"""Audit coverage for the W5-1 evaluation surface.

Two halves. The happy-path half proves every mutation writes its row; the negative half proves
a request ending in a 4xx writes NONE. If a ``..._writes_no_audit_row`` test fails, the fix is
to move ``record_audit`` after the last ``raise`` in the offending handler — never to relax the
assertion.

Actions introduced by this slice: ``evaluation.assigned`` (Task 5),
``evaluation.feedback_updated`` (Task 7), ``section_grade.saved`` (Task 8), and
``report.under_evaluation`` (Task 7/8, via ``state_machine.transition``).
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._evaluations import assign, evaluator, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


async def _rows(migrated_db, action):
    async with migrated_db() as s:
        return (
            (await s.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)))
            .scalars()
            .all()
        )


async def _count(migrated_db, action):
    async with migrated_db() as s:
        return (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        ).scalar_one()


# --- the happy-path rows ------------------------------------------------------


async def test_assign_evaluator_writes_evaluation_assigned_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        await assign(c, ah, ex, rid, uid)
    rows = await _rows(migrated_db, "evaluation.assigned")
    assert len(rows) == 1
    assert rows[0].resource_type == "evaluation"


async def test_assigned_audit_details_carry_report_and_evaluator_ids(migrated_db: async_sessionmaker) -> None:
    ah, ga_uid = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        await assign(c, ah, ex, rid, uid)
    row = (await _rows(migrated_db, "evaluation.assigned"))[0]
    assert row.details["report_id"] == rid
    assert row.details["evaluator_id"] == uid
    assert str(row.user_id) == ga_uid  # the acting admin, not the assignee


async def test_feedback_update_writes_evaluation_feedback_updated_audit_row(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}",
            json={"overall_feedback": "note"},
            headers=h,
        )
    assert await _count(migrated_db, "evaluation.feedback_updated") == 1


async def test_grade_upsert_writes_section_grade_saved_audit_row_with_the_grade_mode(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await submitted_report(c, ah)  # section is numeric-graded
        h, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        await c.put(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
            json={"grade": "7"},
            headers=h,
        )
    rows = await _rows(migrated_db, "section_grade.saved")
    assert len(rows) == 1
    assert rows[0].resource_type == "section_grade"
    assert rows[0].details["grade_mode"] == "numeric"
    assert rows[0].details["evaluation_id"] == evid


async def test_under_evaluation_transition_writes_exactly_one_report_audit_row(
    migrated_db: async_sessionmaker,
) -> None:
    # Two evaluator writes, one transition row: _begin_evaluation is idempotent.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await submitted_report(c, ah)
        h, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        base = f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}"
        await c.patch(base, json={"overall_feedback": "note"}, headers=h)
        await c.put(f"{base}/grades/{sid}", json={"grade": "7"}, headers=h)
    assert await _count(migrated_db, "report.under_evaluation") == 1


# --- the negative rows: a 4xx audits nothing ---------------------------------


async def test_failed_assignment_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        await assign(c, ah, ex, rid, uid)
        # Duplicate -> 409.
        dup = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations",
            json={"evaluator_id": uid},
            headers=ah,
        )
        assert dup.status_code == 409
    assert await _count(migrated_db, "evaluation.assigned") == 1


async def test_403_on_peer_evaluation_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        h1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        await assign(c, ah, ex, rid, uid1)
        evid2 = await assign(c, ah, ex, rid, uid2)
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid2}",
            json={"overall_feedback": "peek"},
            headers=h1,
        )
        assert r.status_code == 403
    assert await _count(migrated_db, "evaluation.feedback_updated") == 0


async def test_422_on_invalid_grade_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await submitted_report(c, ah)
        h, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        # Out of range for grade_min/grade_max -> 422.
        r = await c.put(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
            json={"grade": "99"},
            headers=h,
        )
        assert r.status_code == 422
    assert await _count(migrated_db, "section_grade.saved") == 0
    # A rejected grade write must not have begun the evaluation either: _begin_evaluation runs
    # AFTER validation in Task 8's handler precisely so the report stays 'submitted'.
    assert await _count(migrated_db, "report.under_evaluation") == 0
