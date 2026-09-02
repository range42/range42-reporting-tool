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

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.services.evaluation.finalize_gate import ANY_CAN_FINALIZE
from tests.routes._evaluations import assign, evaluator, ga_headers, submitted_report
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
