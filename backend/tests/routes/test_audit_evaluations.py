"""Audit coverage for the W5-1 evaluation surface.

Two halves. The happy-path half proves every mutation writes its row; the negative half proves
a request ending in a 4xx writes NONE. If a ``..._writes_no_audit_row`` test fails, the fix is
to move ``record_audit`` after the last ``raise`` in the offending handler — never to relax the
assertion.

Actions introduced by this slice: ``evaluation.assigned`` (Task 5),
``evaluation.feedback_updated`` (Task 7), ``section_grade.saved`` (Task 8), and
``report.under_evaluation`` (Task 7/8, via ``state_machine.transition``).
"""

import asyncio
import inspect
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.routes.v1.evaluation_finalize import reopen_evaluation
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


# ======================================================================================
# W5-3 — the multi-evaluator surface's audit coverage.
#
# Actions this slice adds: ``evaluation.completed`` (Task 7), ``report.evaluated`` (Task 7, via
# ``state_machine.transition``), ``evaluation.unassigned`` (Task 9), ``evaluation.reassigned``
# (Task 9), ``event.report_evaluated`` (Task 11, the L11 emit seam), plus
# ``report.grade_recomputed`` written by ``rollup`` whenever the published grade actually moves.
#
# THE NEGATIVE HALF IS THE LOAD-BEARING ONE. A rejected finalize must write nothing at all:
# ``state_machine.transition`` raises BEFORE it mutates, and every ``record_audit`` in these
# handlers sits after the last ``raise``. If one of these tests fails, move the audit call —
# never relax the assertion.
# ======================================================================================


async def _all_actions(migrated_db):
    async with migrated_db() as s:
        return sorted(set((await s.execute(select(AuditLog.action))).scalars().all()))


async def _world(migrated_db, c, ah, *, evaluators=2):
    ex, rid, sid = await submitted_report(c, ah)
    graders = []
    for i in range(evaluators):
        h, uid = await evaluator(migrated_db, c, ah, ex, f"aud-{i}")
        graders.append((h, await assign(c, ah, ex, rid, uid), uid))
    return ex, rid, sid, graders


async def _report_and_evaluators(migrated_db, c, ah, *, evaluators=2):
    """Like ``_world``, but with the action snapshot taken BEFORE anyone is assigned.

    The set assertion below is a DELTA against this snapshot rather than a whole-table read:
    building a submitted report writes a dozen WP2-WP4 rows (exercise, team, template, report,
    submit), and pinning those here would make an unrelated slice's audit change fail this
    slice's test for no reason.
    """
    ex, rid, sid = await submitted_report(c, ah)
    # Role grants are setup too (``exercise_role.assign``), so they happen before the snapshot;
    # only the assignment itself is part of the flow under test.
    people = [await evaluator(migrated_db, c, ah, ex, f"aud-{i}") for i in range(evaluators)]
    before = set(await _all_actions(migrated_db))
    graders = [(h, await assign(c, ah, ex, rid, uid), uid) for h, uid in people]
    return ex, rid, sid, graders, before


async def _grade(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def test_full_multi_evaluator_flow_writes_the_expected_audit_action_set(
    migrated_db: async_sessionmaker,
) -> None:
    """assign x2 -> grade x2 -> finalize x2 -> unassign, as one exact set.

    An EXACT set, not a subset: a superset is how a duplicate transition or a stray second
    event slips in unnoticed, and that is precisely the failure Task 12 exists to prevent.
    """
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, before = await _report_and_evaluators(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "6", h_b)

        # Act
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_a}/finalize", headers=h_a)
        ).status_code == 200
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/finalize", headers=h_b)
        ).status_code == 200
        assert (
            await c.post(
                f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/unassign",
                json={"reason": "left the exercise"},
                headers=ah,
            )
        ).status_code == 200

    # Assert
    added = sorted(set(await _all_actions(migrated_db)) - before)
    assert added == [
        "evaluation.assigned",
        "evaluation.completed",
        "evaluation.unassigned",
        "event.report_evaluated",
        "report.evaluated",
        "report.grade_recomputed",
        "report.under_evaluation",
        "section_grade.saved",
    ]


async def test_rejected_finalize_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    """A 403 and a 409 each leave the finalize actions untouched."""
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)

        # Act: A finalizing B's evaluation is a 403 (D1); A finalizing twice is a 409.
        forbidden = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/finalize", headers=h_a)
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_a}/finalize", headers=h_a)
        ).status_code == 200
        conflict = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_a}/finalize", headers=h_a)

    # Assert
    assert forbidden.status_code == 403, forbidden.text
    assert conflict.status_code == 409, conflict.text
    # Exactly one completion — the 403 and the 409 added nothing.
    assert await _count(migrated_db, "evaluation.completed") == 1
    # …and the gate never opened, so neither did the transition or the event.
    assert await _count(migrated_db, "report.evaluated") == 0
    assert await _count(migrated_db, "event.report_evaluated") == 0


async def test_rejected_unassign_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    """A blank reason (422) and a non-admin caller (403) must both write nothing."""
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=1)
        (h, evid, _uid) = graders[0]
        await _grade(c, ex, rid, evid, sid, "8", h)
        url = f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/unassign"

        # Act
        blank = await c.post(url, json={"reason": "   "}, headers=ah)
        not_admin = await c.post(url, json={"reason": "valid reason"}, headers=h)

    # Assert
    assert blank.status_code == 422, blank.text
    assert not_admin.status_code == 403, not_admin.text
    assert await _count(migrated_db, "evaluation.unassigned") == 0


async def test_unassign_audit_details_record_the_reason_and_the_renormalized_grade(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, evid_b, uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)
        for h, evid in ((h_a, evid_a), (h_b, evid_b)):
            assert (
                await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize", headers=h)
            ).status_code == 200

        # Act: dropping the 4 renormalizes 6.00 up to 8.00.
        assert (
            await c.post(
                f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/unassign",
                json={"reason": "grader recused"},
                headers=ah,
            )
        ).status_code == 200

    # Assert
    [row] = await _rows(migrated_db, "evaluation.unassigned")
    assert row.details["reason"] == "grader recused"
    assert row.details["evaluator_id"] == uid_b
    assert row.details["is_admin_override"] is True
    assert row.details["overall_grade"] == "8.00"


async def test_admin_override_finalize_audit_details_record_is_admin_override_true(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    ah, ga_id = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=1)
        (h, evid, uid) = graders[0]
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        assert (
            await c.post(
                f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize",
                json={"on_behalf_of": uid, "comment": "evaluator unreachable"},
                headers=ah,
            )
        ).status_code == 200

    # Assert: the override is recorded, and credit stays with the evaluator.
    [row] = await _rows(migrated_db, "evaluation.completed")
    assert row.details["is_admin_override"] is True
    assert row.details["comment"] == "evaluator unreachable"
    assert row.details["credited_evaluator_id"] == uid
    assert str(row.user_id) == ga_id


async def test_report_evaluated_and_its_event_are_written_once_each_per_crossing(
    migrated_db: async_sessionmaker,
) -> None:
    """The transition audit row and the L11 event are a pair; neither may double up."""
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "6", h_b)

        # Act: the second finalize crosses the gate; a third press is a 409 and must not re-emit.
        for h, evid in ((h_a, evid_a), (h_b, evid_b)):
            assert (
                await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize", headers=h)
            ).status_code == 200
        assert (
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/finalize", headers=h_b)
        ).status_code == 409

    # Assert
    assert await _count(migrated_db, "report.evaluated") == 1
    assert await _count(migrated_db, "event.report_evaluated") == 1


# ======================================================================================
# W5-4 Task 8 — the reopen path's audit coverage and its concurrency.
#
# The reopen writes THREE rows where a finalize writes two: one on the evaluation
# (``evaluation.reopened``, carrying the reason), one on the report if it actually left
# ``evaluated`` (``report.reopened``), and the supersession event. The reason lives only on the
# first — it is deliberately kept out of the event payload, which leaves the deployment.
# ======================================================================================

_REOPEN_ACTIONS = ("evaluation.reopened", "report.reopened", "event.report_evaluation_reopened")


def _reopen_url(ex, rid, evid) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen"


def _finalize_url(ex, rid, evid) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize"


async def _reopen_counts(migrated_db) -> dict[str, int]:
    return {a: await _count(migrated_db, a) for a in _REOPEN_ACTIONS}


async def _evaluation_row(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, reopen_count FROM evaluation WHERE id = CAST(:i AS uuid)"),
                {"i": evid},
            )
        ).one()


async def _report_status_and_version(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, grade_version FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def test_full_reopen_round_trip_writes_the_expected_audit_action_set(
    migrated_db: async_sessionmaker,
) -> None:
    """assign -> grade -> finalize -> reopen -> re-finalize, as one exact set.

    An EXACT set, not a subset: a superset is how a duplicate transition or a stray second
    event slips in unnoticed. ``event.report_evaluated`` is the one action that must appear
    TWICE — once per crossing — and the count is asserted separately because a set cannot say so.
    """
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, before = await _report_and_evaluators(migrated_db, c, ah, evaluators=1)
        [(h_a, evid_a, _uid_a)] = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

        # Act
        assert (await c.post(_reopen_url(ex, rid, evid_a), json={"reason": "recount"}, headers=ah)).status_code == 200
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

    # Assert
    added = sorted(set(await _all_actions(migrated_db)) - before)
    assert added == [
        "evaluation.assigned",
        "evaluation.completed",
        "evaluation.reopened",
        "event.report_evaluated",
        "event.report_evaluation_reopened",
        "report.evaluated",
        "report.grade_recomputed",
        "report.reopened",
        "report.under_evaluation",
        "section_grade.saved",
    ]
    assert await _count(migrated_db, "event.report_evaluated") == 2
    assert await _count(migrated_db, "event.report_evaluation_reopened") == 1
    assert await _count(migrated_db, "report.reopened") == 1


async def test_reopen_audit_details_record_the_reason_and_the_superseded_version(
    migrated_db: async_sessionmaker,
) -> None:
    """The reason is recoverable from the audit trail and from nowhere else.

    It is kept off the event payload on purpose, so if this row did not carry it the reason
    would be unrecoverable the moment the request ended.
    """
    # Arrange
    ah, ga_uid = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, _before = await _report_and_evaluators(migrated_db, c, ah, evaluators=1)
        [(h_a, evid_a, uid_a)] = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

        # Act
        r = await c.post(_reopen_url(ex, rid, evid_a), json={"reason": "grade disputed by the team"}, headers=ah)
        assert r.status_code == 200, r.text

    # Assert
    [row] = await _rows(migrated_db, "evaluation.reopened")
    assert row.resource_type == "evaluation"
    assert str(row.user_id) == ga_uid  # the admin who acted, not the evaluator
    assert row.details["reason"] == "grade disputed by the team"
    assert row.details["evaluator_id"] == uid_a
    assert row.details["reopen_count"] == 1
    assert row.details["report_status_before"] == "evaluated"
    assert row.details["superseded_grade_version"] == 1
    assert row.details["grade_version"] == 2
    assert row.details["overall_grade"] is None  # nothing contributes while it is reopened

    # ...and the report-level row carries the supersession pointer too.
    [report_row] = await _rows(migrated_db, "report.reopened")
    assert report_row.details["superseded_grade_version"] == 1
    assert report_row.details["evaluation_id"] == evid_a


async def test_rejected_reopen_writes_no_audit_row(migrated_db: async_sessionmaker) -> None:
    """403 / 404 / 409 / 422 each leave every reopen action untouched.

    The guards precede the mutation and ``record_audit`` sits after the last raise. If this
    fails, move the audit call — never relax the assertion.
    """
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, _before = await _report_and_evaluators(migrated_db, c, ah, evaluators=1)
        [(h_a, evid_a, _uid_a)] = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        # 409 first, while the evaluation is still in_progress and nothing is finalized.
        rejections = [await c.post(_reopen_url(ex, rid, evid_a), json={"reason": "early"}, headers=ah)]
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200
        before = await _reopen_counts(migrated_db)

        # Act
        rejections += [
            await c.post(_reopen_url(ex, rid, evid_a), json={"reason": "nope"}, headers=h_a),  # 403
            await c.post(_reopen_url(ex, rid, str(uuid.uuid4())), json={"reason": "nope"}, headers=ah),  # 404
            await c.post(_reopen_url(ex, rid, evid_a), json={"reason": "   "}, headers=ah),  # 422
        ]

    # Assert
    assert [r.status_code for r in rejections] == [409, 403, 404, 422], [r.text for r in rejections]
    assert await _reopen_counts(migrated_db) == before
    assert before == dict.fromkeys(_REOPEN_ACTIONS, 0)
    assert (await _evaluation_row(migrated_db, evid_a)).reopen_count == 0


async def test_back_to_back_double_reopen_increments_the_counter_exactly_once(
    migrated_db: async_sessionmaker,
) -> None:
    """A SEQUENTIAL DOUBLE-CALL PROVES NOTHING ABOUT LOCKING — read this before trusting it.

    ``httpx.ASGITransport`` does not overlap requests in this harness, so these two calls run
    back-to-back: the first has committed before the second is admitted, and the second would
    see ``in_progress`` and 409 whether or not any row lock existed. What this test pins is the
    IDEMPOTENCE of the outcome — one counter increment, one event, one report transition from a
    doubled admin action.

    The lock itself is exercised at the session level, in
    ``test_a_held_report_lock_blocks_the_reopen_before_it_mutates``.
    """
    # Arrange
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, _before = await _report_and_evaluators(migrated_db, c, ah, evaluators=1)
        [(h_a, evid_a, _uid_a)] = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

        # Act
        first, second = await asyncio.gather(
            c.post(_reopen_url(ex, rid, evid_a), json={"reason": "recount"}, headers=ah),
            c.post(_reopen_url(ex, rid, evid_a), json={"reason": "recount again"}, headers=ah),
        )

    # Assert
    assert {first.status_code, second.status_code} == {200, 409}, (first.text, second.text)
    assert (await _evaluation_row(migrated_db, evid_a)).reopen_count == 1
    assert await _count(migrated_db, "report.reopened") == 1
    assert await _count(migrated_db, "event.report_evaluation_reopened") == 1


async def test_a_reopen_and_a_peer_finalize_leave_a_coherent_end_state(
    migrated_db: async_sessionmaker,
) -> None:
    """Two admin/evaluator actions on one report, back-to-back (see the note above).

    Evaluator A is reopened while evaluator B finalizes. Whatever the order, the end state must
    be internally consistent: A is back in grading, B is complete, the gate is therefore not
    satisfied, and the report is under evaluation with exactly one reopen recorded.
    """
    # Arrange: both graded, only A finalized, so the report is still under evaluation.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, _before = await _report_and_evaluators(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "6", h_b)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

        # Act
        reopened, finalized = await asyncio.gather(
            c.post(_reopen_url(ex, rid, evid_a), json={"reason": "recount"}, headers=ah),
            c.post(_finalize_url(ex, rid, evid_b), headers=h_b),
        )

    # Assert — ORDER-AGNOSTIC, deliberately. Which request lands first is not deterministic
    # under load, and both orders are legitimate: if the finalize wins, the gate opens, the
    # report crosses to ``evaluated`` and the reopen then pulls it back; if the reopen wins,
    # the gate never opens and the report never leaves ``under_evaluation``. Asserting either
    # specific order made this test pass in isolation and fail in a full run.
    assert reopened.status_code == 200, reopened.text
    assert finalized.status_code == 200, finalized.text
    assert (await _evaluation_row(migrated_db, evid_a)).status == "in_progress"
    assert (await _evaluation_row(migrated_db, evid_b)).status == "completed"

    # Whatever the order: A is counted and unfinished, so the gate is shut at the end.
    status, _version = await _report_status_and_version(migrated_db, rid)
    assert status == "under_evaluation"

    # And the two counts move together. ``report.reopened`` is written only when the reopen
    # found the report already ``evaluated`` — which is exactly when the crossing fired its
    # event. One without the other means a crossing went unannounced, or a report was pulled
    # back from a state it never reached.
    crossings = await _count(migrated_db, "event.report_evaluated")
    reopen_transitions = await _count(migrated_db, "report.reopened")
    assert crossings == reopen_transitions
    assert crossings in (0, 1)


# --- the lock, where it can actually be driven: two transactions ---------------------


async def test_a_held_report_lock_stalls_the_reopen_until_it_is_released(
    migrated_db: async_sessionmaker,
) -> None:
    """The reopen participates in the report's serialization — asserted, not assumed.

    An outside session takes ``SELECT ... FOR UPDATE`` on the report and does not commit; the
    reopen is then launched as a task and given a full second to produce a committed change.
    It must not, and once the lock is released the very same in-flight request completes —
    which is what shows it was waiting on the lock rather than failing for some other reason.

    WHAT THIS DOES NOT PROVE, and do not let the name suggest otherwise: that the handler takes
    the lock BEFORE mutating. It cannot. ``rollup.recompute_report_grade`` takes the same row
    lock internally, so a handler that mutated first and locked later would stall here just the
    same, and its mutation would be flushed-but-uncommitted and therefore invisible to the
    observing session either way. Measured: with the handler's own
    ``_get_report_for_update`` swapped for an unlocked read, this test still passes.

    Lock ORDER — report before evaluation — is what prevents a production deadlock against
    finalize and unassign, and it is guarded structurally by the test below instead.
    """
    # Arrange: a finalized evaluation, so the reopen is otherwise permitted.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders, _before = await _report_and_evaluators(migrated_db, c, ah, evaluators=1)
        [(h_a, evid_a, _uid_a)] = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

        async with migrated_db() as holder:
            await holder.execute(
                text("SELECT id FROM report WHERE id = CAST(:i AS uuid) FOR UPDATE"),
                {"i": rid},
            )

            # Act: launch the reopen against the locked row.
            task = asyncio.create_task(c.post(_reopen_url(ex, rid, evid_a), json={"reason": "recount"}, headers=ah))
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

            # Assert: a full second in, nothing is committed.
            assert (await _evaluation_row(migrated_db, evid_a)).reopen_count == 0
            assert await _count(migrated_db, "evaluation.reopened") == 0

            # Act: release the lock; the SAME in-flight request finishes.
            await holder.commit()

        r = await task

    # Assert
    assert r.status_code == 200, r.text
    assert (await _evaluation_row(migrated_db, evid_a)).reopen_count == 1
    assert await _count(migrated_db, "evaluation.reopened") == 1


def test_reopen_takes_the_report_lock_before_touching_the_evaluation() -> None:
    """LOCK ORDER, guarded structurally because it cannot be observed behaviourally.

    Every handler on this surface must take the parent report's lock as its first act and only
    then load the evaluation. Two paths acquiring these two locks in opposite orders deadlock
    in production, and a deadlock surfaces as hung requests — never as a failing test.

    A source assertion is a blunt instrument, but it is the only one available here, and it
    fails loudly the moment someone reorders the handler or swaps the locking read for a plain
    one. Behavioural tests cannot see the difference: see the docstring above.
    """
    # Arrange
    src = inspect.getsource(reopen_evaluation)

    # Act / Assert — presence first, so a swapped-out lock fails as a message, not a ValueError.
    assert "_get_report_for_update" in src, "reopen no longer takes the report row lock"
    assert src.index("_get_report_for_update") < src.index("_get_evaluation("), (
        "reopen loads the evaluation before locking the report — the lock order is inverted"
    )
    assert src.index("_get_evaluation(") < src.index("ev.status ="), (
        "reopen mutates the evaluation before loading it under the report lock"
    )
