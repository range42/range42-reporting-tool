"""W5-3 Task 2 — ``finalize_policy`` resolution (G-6, missing-row default).

``scoring_config.finalize_policy`` decides whether every assigned evaluator must finalize
before a report's grade is aggregated. Exercises created before WP5 have no
``scoring_config`` row at all, so the resolver must answer with the documented default
rather than NULL — the aggregation branch reads a mode, never an absence.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.services.evaluation.finalize_gate import (
    ALL_MUST_FINALIZE,
    ANY_CAN_FINALIZE,
    resolve_finalize_policy,
)
from tests.routes._evaluations import assign, evaluator, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


async def _exercise(c, ah) -> str:
    return (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]


async def _sql(migrated_db, stmt, **params):
    async with migrated_db() as s:
        await s.execute(text(stmt), params)
        await s.commit()


async def _resolve(migrated_db, exercise_id: str) -> str:
    async with migrated_db() as s:
        return await resolve_finalize_policy(s, uuid.UUID(exercise_id))


async def test_finalize_policy_defaults_to_all_must_finalize_when_no_scoring_config_row_exists(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange: an exercise predating WP5 — no scoring_config row of its own.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)
    await _sql(migrated_db, "DELETE FROM scoring_config WHERE exercise_id = CAST(:e AS uuid)", e=ex)

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ALL_MUST_FINALIZE


async def test_finalize_policy_reads_any_can_finalize_from_scoring_config(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)
    await _sql(
        migrated_db,
        "UPDATE scoring_config SET finalize_policy = :m WHERE exercise_id = CAST(:e AS uuid)",
        m=ANY_CAN_FINALIZE,
        e=ex,
    )

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ANY_CAN_FINALIZE


async def test_finalize_policy_reads_the_seeded_default_row(migrated_db: async_sessionmaker) -> None:
    # Arrange: a freshly created exercise gets a seeded scoring_config row.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ALL_MUST_FINALIZE


# --- Task 7: POST .../evaluations/{evid}/finalize -------------------------------------
#
# Path shape follows this module's documented L3 deviation — nested under the report, not
# §6.8's flat /evaluations/{id} — so the exercise-scoped permission dependency has an
# exercise_id to resolve against.


def _finalize_url(ex, rid, evid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize"


async def _set_policy(migrated_db, ex, mode):
    await _sql(
        migrated_db,
        "UPDATE scoring_config SET finalize_policy = :m WHERE exercise_id = CAST(:e AS uuid)",
        m=mode,
        e=ex,
    )


async def _world(migrated_db, c, ah, *, evaluators=1):
    """Submitted report, one numeric section, `evaluators` assigned graders.

    Returns (ex, rid, sid, [(headers, evaluation_id), ...]).
    """
    ex, rid, sid = await submitted_report(c, ah)
    graders = []
    for i in range(evaluators):
        h, uid = await evaluator(migrated_db, c, ah, ex, f"ev-{i}")
        graders.append((h, await assign(c, ah, ex, rid, uid)))
    return ex, rid, sid, graders


async def _grade(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _report_row(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, overall_grade, grade_version FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def _evaluation_row(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT status, completed_at, overall_grade, finalized_by, finalize_is_admin_override "
                    "FROM evaluation WHERE id = CAST(:i AS uuid)"
                ),
                {"i": evid},
            )
        ).one()


async def test_finalize_sets_evaluation_completed_and_completed_at(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 200, r.text
    status, completed_at, grade, _by, _ovr = await _evaluation_row(migrated_db, evid)
    assert status == "completed"
    assert completed_at is not None
    assert grade == Decimal("8.00")


async def test_finalize_by_last_evaluator_transitions_report_to_evaluated(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for h, evid in graders:
            await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        for h, evid in graders:
            r = await c.post(_finalize_url(ex, rid, evid), headers=h)
            assert r.status_code == 200, r.text
        body = r.json()["data"]

    # Assert
    assert body["finalize_gate_satisfied"] is True
    assert body["report_status"] == "evaluated"
    status, grade, version = await _report_row(migrated_db, rid)
    assert status == "evaluated"
    assert grade == Decimal("8.00")
    assert version >= 1


async def test_finalize_by_first_of_two_evaluators_leaves_report_under_evaluation(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for h, evid in graders:
            await _grade(c, ex, rid, evid, sid, "8", h)
        first_h, first_evid = graders[0]

        # Act
        r = await c.post(_finalize_url(ex, rid, first_evid), headers=first_h)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finalize_gate_satisfied"] is False
    assert r.json()["data"]["report_status"] == "under_evaluation"
    status, _g, _v = await _report_row(migrated_db, rid)
    assert status == "under_evaluation"


async def test_finalize_under_any_can_finalize_transitions_on_first_finalize(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for h, evid in graders:
            await _grade(c, ex, rid, evid, sid, "8", h)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)
        first_h, first_evid = graders[0]

        # Act
        r = await c.post(_finalize_url(ex, rid, first_evid), headers=first_h)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finalize_gate_satisfied"] is True
    status, _g, _v = await _report_row(migrated_db, rid)
    assert status == "evaluated"


async def test_finalize_is_rejected_when_evaluation_already_completed(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        assert (await c.post(_finalize_url(ex, rid, evid), headers=h)).status_code == 200

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "already_finalized"


async def test_finalize_is_rejected_when_evaluation_was_unassigned(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        await _sql(
            migrated_db,
            "UPDATE evaluation SET unassigned_at = now() WHERE id = CAST(:i AS uuid)",
            i=evid,
        )

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_unassigned"


async def test_finalize_is_rejected_when_report_is_not_under_evaluation(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange: grading moves the report to under_evaluation, so force it back to submitted.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        await _sql(migrated_db, "UPDATE report SET status = 'submitted' WHERE id = CAST(:i AS uuid)", i=rid)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "invalid_state"


async def test_finalize_is_rejected_when_a_gradeable_section_has_no_grade(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange: nothing graded at all, so the report is still submitted -> begin it by hand.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _sql(migrated_db, "UPDATE report SET status = 'under_evaluation' WHERE id = CAST(:i AS uuid)", i=rid)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "section_grade_missing"
    assert len(r.json()["error"]["details"][0]["section_def_ids"]) == 1


async def test_finalize_recomputes_the_aggregate_before_evaluating_the_gate(
    migrated_db: async_sessionmaker,
) -> None:
    """Ordering matters: a gate settled before the recompute would announce a stale grade."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        # No grade is published while the only evaluator is still in progress.
        assert (await _report_row(migrated_db, rid))[1] is None

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert: the transition and the grade land together, not one request apart.
    assert r.status_code == 200, r.text
    status, grade, version = await _report_row(migrated_db, rid)
    assert (status, grade) == ("evaluated", Decimal("8.00"))
    assert version == 1


async def test_finalize_is_rejected_for_a_foreign_evaluator(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)
        other, _uid = await evaluator(migrated_db, c, ah, ex, "ev-other")

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=other)

    # Assert
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == "not_your_evaluation"


async def test_finalize_emits_an_audit_row_on_each_gate_branch(migrated_db: async_sessionmaker) -> None:
    """A finalize that does not close the gate is still audited, on the evaluation.

    Only the finalize that closes it emits ``report.evaluated``, and that row belongs to the
    report — one transition, one row, from the state machine's sole-writer path.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for h, evid in graders:
            await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        for h, evid in graders:
            assert (await c.post(_finalize_url(ex, rid, evid), headers=h)).status_code == 200

    # Assert
    first_actions = await _audit_actions(migrated_db, graders[0][1])
    report_actions = await _audit_actions(migrated_db, rid)
    assert "evaluation.completed" in first_actions
    assert report_actions.count("report.evaluated") == 1


async def _audit_actions(migrated_db, resource_id):
    async with migrated_db() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog.action)
                    .where(AuditLog.resource_id == uuid.UUID(resource_id))
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )
