"""W5-3 Task 8 — finalize-on-behalf-of (D2, half one).

THE DEADLOCK THIS EXISTS FOR: under ``all_must_finalize`` one absent evaluator holds a report
hostage forever. §4.2's exit is an audited Global Admin override — the admin presses Finalize
in the evaluator's name.

CREDIT AND ACTOR ARE DIFFERENT FIELDS, and getting them backwards makes the dispute trail lie:

* ``evaluation.evaluator_id`` — unchanged. The work is still the absent evaluator's.
* ``evaluation.finalized_by`` — the ADMIN who pressed the button.
* ``evaluation.finalize_is_admin_override`` — True, so the override is visible forever.

Each is asserted separately below for exactly that reason.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.services.evaluation.finalize_gate import ANY_CAN_FINALIZE
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _finalize_url(ex, rid, evid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize"


async def _sql(migrated_db, stmt, **params):
    async with migrated_db() as s:
        await s.execute(text(stmt), params)
        await s.commit()


async def _world(migrated_db, c, ah, *, evaluators=1):
    """Submitted report, one numeric section, `evaluators` assigned graders.

    Returns (ex, rid, sid, [(headers, evaluation_id, user_id), ...]).
    """
    ex, rid, sid = await submitted_report(c, ah)
    graders = []
    for i in range(evaluators):
        h, uid = await evaluator(migrated_db, c, ah, ex, f"ev-{i}")
        graders.append((h, await assign(c, ah, ex, rid, uid), uid))
    return ex, rid, sid, graders


async def _grade(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _evaluation_row(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT status, evaluator_id, finalized_by, finalize_is_admin_override, finalize_comment "
                    "FROM evaluation WHERE id = CAST(:i AS uuid)"
                ),
                {"i": evid},
            )
        ).one()


async def _report_row(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, overall_grade FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def _audit_rows(migrated_db, resource_id):
    async with migrated_db() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog).where(AuditLog.resource_id == uuid.UUID(resource_id)).order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )


COMMENT = "evaluator unreachable for two weeks; exercise closing"


# --- the happy path -------------------------------------------------------------------


async def test_global_admin_can_finalize_on_behalf_of_an_absent_evaluator(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ga_id = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act: the evaluator never presses Finalize; the admin does it for them.
        r = await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid, "comment": COMMENT}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["report_status"] == "evaluated"
    assert await _report_row(migrated_db, rid) == ("evaluated", pytest.approx(8.00))


async def test_finalize_on_behalf_of_sets_is_admin_override_and_records_the_admin_as_finalized_by(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, ga_id = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid, "comment": COMMENT}, headers=ah)

    # Assert: credit stays with the evaluator, the button-press is attributed to the admin.
    assert r.status_code == 200, r.text
    status, evaluator_id, finalized_by, is_override, comment = await _evaluation_row(migrated_db, evid)
    assert status == "completed"
    assert str(evaluator_id) == uid
    assert str(finalized_by) == ga_id
    assert is_override is True
    assert comment == COMMENT


async def test_finalizing_your_own_evaluation_is_not_an_override(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act: no on_behalf_of, the evaluator presses their own button.
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 200, r.text
    _status, evaluator_id, finalized_by, is_override, comment = await _evaluation_row(migrated_db, evid)
    assert str(finalized_by) == str(evaluator_id) == uid
    assert is_override is False
    assert comment is None


# --- the guards -----------------------------------------------------------------------


async def test_finalize_on_behalf_of_requires_a_comment(migrated_db: async_sessionmaker) -> None:
    """A mandatory reason is §4.2's deadlock-resolution contract, not a nicety."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid}, headers=ah)
        blank = await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid, "comment": "   "}, headers=ah)

    # Assert
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == "comment_required"
    assert blank.status_code == 422, blank.text


async def test_finalize_on_behalf_of_rejects_a_non_admin_caller(migrated_db: async_sessionmaker) -> None:
    # Arrange: the evaluator's OWN evaluation, so D1 access passes and only the admin rule bites.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid, "comment": COMMENT}, headers=h)

    # Assert
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == "not_global_admin"


async def test_finalize_on_behalf_of_rejects_an_unknown_user(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(
            _finalize_url(ex, rid, evid),
            json={"on_behalf_of": str(uuid.uuid4()), "comment": COMMENT},
            headers=ah,
        )

    # Assert
    assert r.status_code == 404, r.text
    assert r.json()["error"]["message"] == "user_not_found"


async def test_finalize_on_behalf_of_rejects_a_malformed_user_id(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(
            _finalize_url(ex, rid, evid), json={"on_behalf_of": "not-a-uuid", "comment": COMMENT}, headers=ah
        )

    # Assert
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == "invalid_on_behalf_of"


async def test_finalize_on_behalf_of_rejects_a_user_who_is_not_this_evaluations_evaluator(
    migrated_db: async_sessionmaker,
) -> None:
    """An evaluation names exactly ONE evaluator, so the stricter check is available.

    ``reports.py``'s approval override cannot make it — a chain step names a *role*, which many
    users may satisfy. Here, naming anyone else is a mistake worth refusing.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a, _uid_a), (_h_b, _evid_b, uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)

        # Act: finalize A's evaluation in B's name.
        r = await c.post(_finalize_url(ex, rid, evid_a), json={"on_behalf_of": uid_b, "comment": COMMENT}, headers=ah)

    # Assert
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == "on_behalf_of_mismatch"


# --- audit ----------------------------------------------------------------------------


async def test_finalize_on_behalf_of_writes_an_audit_row_with_the_override_flag_and_reason(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, ga_id = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        assert (
            await c.post(_finalize_url(ex, rid, evid), json={"on_behalf_of": uid, "comment": COMMENT}, headers=ah)
        ).status_code == 200

    # Assert
    rows = [r for r in await _audit_rows(migrated_db, evid) if r.action == "evaluation.completed"]
    assert len(rows) == 1
    details = rows[0].details
    assert details["is_admin_override"] is True
    assert details["comment"] == COMMENT
    assert details["credited_evaluator_id"] == uid
    assert str(rows[0].user_id) == ga_id


# --- the mandated edge case -----------------------------------------------------------


async def test_any_can_finalize_combined_with_admin_override_transitions_and_records_the_override(
    migrated_db: async_sessionmaker,
) -> None:
    """Mode ``any_can_finalize``, three assigned evaluators, none completed.

    The admin finalizes on behalf of one. The gate opens on that single completed evaluation,
    so the report becomes ``evaluated`` with an aggregate over that evaluator ALONE — the other
    two contribute neither a value nor their weight.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=3)
        for h, evid, _uid in graders:
            await _grade(c, ex, rid, evid, sid, "6", h)
        # The one the admin acts for grades differently, so an aggregate over all three
        # (6.00) is distinguishable from an aggregate over them alone (9.00).
        target_h, target_evid, target_uid = graders[0]
        await _grade(c, ex, rid, target_evid, sid, "9", target_h)
        await _sql(
            migrated_db,
            "UPDATE scoring_config SET finalize_policy = :m WHERE exercise_id = CAST(:e AS uuid)",
            m=ANY_CAN_FINALIZE,
            e=ex,
        )

        # Act
        r = await c.post(
            _finalize_url(ex, rid, target_evid), json={"on_behalf_of": target_uid, "comment": COMMENT}, headers=ah
        )

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finalize_gate_satisfied"] is True
    assert await _report_row(migrated_db, rid) == ("evaluated", pytest.approx(9.00))
    _status, _evaluator_id, _by, is_override, _comment = await _evaluation_row(migrated_db, target_evid)
    assert is_override is True
    report_actions = [r.action for r in await _audit_rows(migrated_db, rid)]
    assert report_actions.count("report.evaluated") == 1


# ======================================================================================
# W5-3 Task 9 — POST .../unassign (D2, half two).
#
# THE OTHER HALF OF THE SAME DEADLOCK: half one finalizes IN the absent evaluator's name.
# Half two removes them from the reckoning entirely — used when the admin has no grade to
# publish on their behalf, only an empty seat to clear.
#
# L8 — UNASSIGN IS SOFT. The row and its section_grade rows survive; ``unassigned_at IS NULL``
# is the whole L7 "counted" predicate. Nothing is deleted, ``status`` is not rewritten, and the
# dispute trail stays readable. Several tests below exist only to hold that line.
#
# L5 — RENORMALIZATION, not rescaling: the dropped evaluator leaves the denominator, and the
# survivors' weights are re-divided among themselves.
# ======================================================================================


REASON = "evaluator left the organisation mid-exercise"


def _unassign_url(ex, rid, evid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/unassign"


async def _unassign_row(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT unassigned_at, unassigned_by, unassign_reason, status, completed_at, finalized_by "
                    "FROM evaluation WHERE id = CAST(:i AS uuid)"
                ),
                {"i": evid},
            )
        ).one()


async def _grade_state(migrated_db, rid):
    """(status, overall_grade, grade_version) — the three fields L5/L9 move together."""
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, overall_grade, grade_version FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def _section_grade_count(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM section_grade WHERE evaluation_id = CAST(:i AS uuid)"),
                {"i": evid},
            )
        ).scalar_one()


# --- the happy path -------------------------------------------------------------------


async def test_global_admin_can_unassign_an_evaluator_with_a_reason(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, ga_id = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    unassigned_at, unassigned_by, reason, _status, _completed_at, _finalized_by = await _unassign_row(migrated_db, evid)
    assert unassigned_at is not None
    assert str(unassigned_by) == ga_id
    assert reason == REASON


# --- the guards -----------------------------------------------------------------------


async def test_unassign_requires_a_non_blank_reason(migrated_db: async_sessionmaker) -> None:
    """A dropped evaluator is a dispute waiting to happen; the reason is the defence."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        missing = await c.post(_unassign_url(ex, rid, evid), json={}, headers=ah)
        blank = await c.post(_unassign_url(ex, rid, evid), json={"reason": "   "}, headers=ah)

    # Assert
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["message"] == "reason_required"
    assert blank.status_code == 422, blank.text
    assert blank.json()["error"]["message"] == "reason_required"


async def test_unassign_is_rejected_for_non_admin_callers(migrated_db: async_sessionmaker) -> None:
    """Including the evaluation's OWN evaluator — self-removal is not a thing (§4.2)."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=h)

    # Assert
    assert r.status_code == 403, r.text
    assert (await _unassign_row(migrated_db, evid))[0] is None


async def test_unassign_of_an_already_unassigned_evaluation_is_rejected(migrated_db: async_sessionmaker) -> None:
    """A double-clicked button must not re-bump grade_version (L9)."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        assert (await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=ah)).status_code == 200
        _s, _g, version_after_first = await _grade_state(migrated_db, rid)

        # Act
        r = await c.post(_unassign_url(ex, rid, evid), json={"reason": "again"}, headers=ah)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "already_unassigned"
    assert (await _grade_state(migrated_db, rid))[2] == version_after_first


# --- L5: renormalization --------------------------------------------------------------


async def test_unassign_evaluator_renormalizes_aggregated_weight(migrated_db: async_sessionmaker) -> None:
    """THE canonical D2 assertion.

    Weights 1.0/1.5 over grades 8.0/6.0 average (8.0 + 9.0) / 2.5 == 6.80. Dropping the 1.5
    leaves 8.00 — the survivor's own grade, NOT 6.80 rescaled by 1.0/2.5 (which would be 2.72).
    The value is asserted, not merely that it moved.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        h_a, uid_a = await evaluator(migrated_db, c, ah, ex, "ev-a")
        h_b, uid_b = await evaluator(migrated_db, c, ah, ex, "ev-b")
        evid_a = await assign(c, ah, ex, rid, uid_a, aggregated_weight="1.0")
        evid_b = await assign(c, ah, ex, rid, uid_b, aggregated_weight="1.5")
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "6", h_b)
        await finalize(c, h_a, ex, rid, evid_a)
        await finalize(c, h_b, ex, rid, evid_b)
        _status, before, version_before = await _grade_state(migrated_db, rid)
        assert before == Decimal("6.80")

        # Act: drop the heavier, lower-scoring evaluator.
        r = await c.post(_unassign_url(ex, rid, evid_b), json={"reason": REASON}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    _status, after, version_after = await _grade_state(migrated_db, rid)
    assert after == Decimal("8.00")
    assert version_after > version_before


async def test_unassign_does_not_delete_the_evaluation_or_its_section_grades(
    migrated_db: async_sessionmaker,
) -> None:
    """L8: soft. The row, its grades and its status all survive the removal."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        assert await _section_grade_count(migrated_db, evid) == 1

        # Act
        assert (await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=ah)).status_code == 200

    # Assert
    row = await _unassign_row(migrated_db, evid)
    assert row is not None
    assert row.status == "in_progress"  # NOT rewritten to some 'unassigned' pseudo-status
    assert await _section_grade_count(migrated_db, evid) == 1


async def test_unassigning_an_evaluator_who_had_already_finalized_removes_their_grade_from_the_aggregate(
    migrated_db: async_sessionmaker,
) -> None:
    """EDGE CASE: they were completed and contributing.

    Afterwards they contribute neither numerator nor denominator, yet ``completed_at`` and
    ``finalized_by`` stay readable — that pair IS the dispute trail.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)
        await finalize(c, h_a, ex, rid, evid_a)
        await finalize(c, h_b, ex, rid, evid_b)
        assert (await _grade_state(migrated_db, rid))[1] == Decimal("6.00")

        # Act
        r = await c.post(_unassign_url(ex, rid, evid_b), json={"reason": REASON}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert (await _grade_state(migrated_db, rid))[1] == Decimal("8.00")
    row = await _unassign_row(migrated_db, evid_b)
    assert row.status == "completed"
    assert row.completed_at is not None
    assert row.finalized_by is not None


# --- L6: the gate settles on unassign too ---------------------------------------------


async def test_unassigning_the_last_unfinalized_evaluator_auto_transitions_the_report_to_evaluated(
    migrated_db: async_sessionmaker,
) -> None:
    """EDGE CASE, L6 — the whole point of D2 half two.

    ``all_must_finalize`` with one absent evaluator is the deadlock. Removing them leaves a
    fully-finalized counted set, so the gate opens and the report crosses on the way out.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)  # graded but never finalized
        await finalize(c, h_a, ex, rid, evid_a)
        status_before, _g, version_before = await _grade_state(migrated_db, rid)
        assert status_before == "under_evaluation"  # blocked by the absent evaluator

        # Act
        r = await c.post(_unassign_url(ex, rid, evid_b), json={"reason": REASON}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finalize_gate_satisfied"] is True
    status_after, grade_after, version_after = await _grade_state(migrated_db, rid)
    assert status_after == "evaluated"
    assert grade_after == Decimal("8.00")
    # D3: the version identifies the PUBLISHED grade, and the removed evaluator never
    # contributed a value — the gate opened without the number moving, so nothing was
    # republished. Bumping here would invalidate a consumer's cache over a non-event.
    assert version_after == version_before
    evaluated = [row for row in await _audit_rows(migrated_db, rid) if row.action == "report.evaluated"]
    assert len(evaluated) == 1
    assert evaluated[0].details["trigger"] == "evaluator_unassigned"


async def test_unassigning_the_only_evaluator_does_not_transition_the_report(
    migrated_db: async_sessionmaker,
) -> None:
    """THE COUNTERPART that stops L6 over-firing.

    Zero counted evaluations is a CLOSED gate, not a vacuously open one — a report with nobody
    left to grade it wants a human, so it stays ``under_evaluation`` with a NULL grade and the
    response says so.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, _uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finalize_gate_satisfied"] is False
    status_after, grade_after, _v = await _grade_state(migrated_db, rid)
    assert status_after == "under_evaluation"
    assert grade_after is None
    assert [row for row in await _audit_rows(migrated_db, rid) if row.action == "report.evaluated"] == []


# --- audit ----------------------------------------------------------------------------


async def test_unassign_writes_an_audit_row_with_the_reason_and_the_new_aggregate(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, ga_id = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a, _uid_a), (h_b, evid_b, uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)
        await finalize(c, h_a, ex, rid, evid_a)
        await finalize(c, h_b, ex, rid, evid_b)

        # Act
        assert (await c.post(_unassign_url(ex, rid, evid_b), json={"reason": REASON}, headers=ah)).status_code == 200

    # Assert
    rows = [row for row in await _audit_rows(migrated_db, evid_b) if row.action == "evaluation.unassigned"]
    assert len(rows) == 1
    details = rows[0].details
    assert details["reason"] == REASON
    assert details["evaluator_id"] == uid_b
    assert details["is_admin_override"] is True
    assert details["overall_grade"] == "8.00"
    assert str(rows[0].user_id) == ga_id


# --- L8: the row survives to be reused ------------------------------------------------


async def test_reassigning_a_previously_unassigned_evaluator_reactivates_the_existing_row(
    migrated_db: async_sessionmaker,
) -> None:
    """L8 exists so ``UNIQUE(report_id, evaluator_id)`` survives a change of mind.

    Re-assigning the same evaluator must revive their row — with their old section grades still
    attached — not collide with it and not create a second one.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid, uid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        assert (await c.post(_unassign_url(ex, rid, evid), json={"reason": REASON}, headers=ah)).status_code == 200

        # Act
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations", json={"evaluator_id": uid}, headers=ah)

    # Assert
    assert r.status_code == 201, r.text
    assert r.json()["data"]["id"] == evid
    async with migrated_db() as s:
        count = (
            await s.execute(text("SELECT count(*) FROM evaluation WHERE report_id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert count == 1
    assert (await _unassign_row(migrated_db, evid))[0] is None
    assert await _section_grade_count(migrated_db, evid) == 1
    actions = [row.action for row in await _audit_rows(migrated_db, evid)]
    assert actions.count("evaluation.reassigned") == 1
