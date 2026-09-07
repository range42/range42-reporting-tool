"""W5-3 Task 2 — ``finalize_policy`` resolution (G-6, missing-row default).

``scoring_config.finalize_policy`` decides whether every assigned evaluator must finalize
before a report's grade is aggregated. Exercises created before WP5 have no
``scoring_config`` row at all, so the resolver must answer with the documented default
rather than NULL — the aggregation branch reads a mode, never an absence.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.routes.v1.evaluation_finalize import _get_report_for_update
from app.routes.v1.reports import _get_report
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


# --- any_can_finalize: the gate opening must not lock out the remaining evaluators ----


async def test_remaining_evaluators_can_still_finalize_after_the_gate_opened(
    migrated_db: async_sessionmaker,
) -> None:
    """Under ``any_can_finalize`` the first finalize marks the report evaluated (§7.2).

    That must not strand the other evaluators: their own work is still in progress, and
    refusing it would leave an evaluation permanently un-finalizable through no fault of the
    person assigned to it.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for (h, evid), value in zip(graders, ("8", "6"), strict=True):
            await _grade(c, ex, rid, evid, sid, value, h)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)
        first_h, first_evid = graders[0]
        second_h, second_evid = graders[1]
        assert (await c.post(_finalize_url(ex, rid, first_evid), headers=first_h)).status_code == 200
        assert (await _report_row(migrated_db, rid))[0] == "evaluated"

        # Act
        r = await c.post(_finalize_url(ex, rid, second_evid), headers=second_h)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["report_status"] == "evaluated"
    status, _at, _g, _by, _ovr = await _evaluation_row(migrated_db, second_evid)
    assert status == "completed"


async def test_a_later_finalize_republishes_the_aggregate_with_a_new_version(
    migrated_db: async_sessionmaker,
) -> None:
    """The second evaluator joins the numerator, so the published number changes."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for (h, evid), value in zip(graders, ("8", "6"), strict=True):
            await _grade(c, ex, rid, evid, sid, value, h)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)
        first_h, first_evid = graders[0]
        second_h, second_evid = graders[1]
        await c.post(_finalize_url(ex, rid, first_evid), headers=first_h)
        assert await _report_row(migrated_db, rid) == ("evaluated", Decimal("8.00"), 1)

        # Act
        await c.post(_finalize_url(ex, rid, second_evid), headers=second_h)

    # Assert: (8 + 6) / 2 = 7.00, published as a new version so consumers see the supersession.
    assert await _report_row(migrated_db, rid) == ("evaluated", Decimal("7.00"), 2)


async def test_finalizing_an_evaluated_report_does_not_transition_it_again(
    migrated_db: async_sessionmaker,
) -> None:
    """``evaluated -> evaluated`` is not a legal transition; the settle step must not attempt it."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        for h, evid in graders:
            await _grade(c, ex, rid, evid, sid, "8", h)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)
        for h, evid in graders:
            assert (await c.post(_finalize_url(ex, rid, evid), headers=h)).status_code == 200

    # Assert: exactly one report.evaluated row, not one per finalize.
    assert (await _audit_actions(migrated_db, rid)).count("report.evaluated") == 1


# ======================================================================================
# W5-3 Task 11 — the ``report.evaluated`` emit seam (L11) + WP6 handoff.
#
# WP5 HAS NO WEBHOOKS. No `webhook_config`, no HMAC signer, no delivery engine — those are
# WP6 (#53/#54). What this task pins down is the CALL SITE: one function that builds the
# §11.3 payload and records that the event happened. WP6 replaces its body with an outbox
# insert and every caller keeps working.
#
# The seam is asserted through the audit row (`event.report_evaluated`) because that is the
# only observable WP5 has. When WP6 lands, these tests should keep passing unchanged — if
# they need editing, the seam was not a seam.
#
# D1 EXTENDS TO MACHINES. A webhook carrying the per-evaluator breakdown is a peer-visibility
# hole with extra steps, and a durable one: the payload outlives the request in an outbox, a
# delivery log and someone's HTTP endpoint.
# ======================================================================================


_EVALUATED_EVENT = "event.report_evaluated"


async def _event_rows(migrated_db, rid):
    async with migrated_db() as s:
        return list(
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.resource_id == uuid.UUID(rid), AuditLog.action == _EVALUATED_EVENT)
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )


async def test_report_evaluated_event_is_emitted_once_when_the_gate_closes(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=h)

    # Assert
    assert r.status_code == 200, r.text
    assert len(await _event_rows(migrated_db, rid)) == 1


async def test_report_evaluated_event_is_not_emitted_when_the_gate_stays_open(
    migrated_db: async_sessionmaker,
) -> None:
    """One of two evaluators under ``all_must_finalize`` — nothing has been decided yet."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a), (h_b, evid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "6", h_b)

        # Act
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

    # Assert
    assert await _event_rows(migrated_db, rid) == []


async def test_report_evaluated_payload_matches_the_architecture_shape(
    migrated_db: async_sessionmaker,
) -> None:
    """§11.3: ``{exercise_id, report_id, team_id, overall_grade, section_grades[]}``."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        assert (await c.post(_finalize_url(ex, rid, evid), headers=h)).status_code == 200

    # Assert
    [row] = await _event_rows(migrated_db, rid)
    payload = row.details
    assert set(payload) == {
        "exercise_id",
        "report_id",
        "team_id",
        "overall_grade",
        "section_grades",
        "grade_version",
    }
    assert payload["exercise_id"] == ex
    assert payload["report_id"] == rid
    assert payload["overall_grade"] == "8.00"
    [section] = payload["section_grades"]
    assert set(section) == {"section_def_id", "name", "grade", "weight"}
    assert section["grade"] == "8.00"


async def test_report_evaluated_payload_carries_grade_version(migrated_db: async_sessionmaker) -> None:
    """ADDITIVE TO §11.3, deliberately (§9-A8).

    Delivery is at-least-once and §11.3 defines no retraction event, so a consumer's only
    defence against acting on a superseded grade is D3's monotonic version. Without it a
    reopen-and-regrade is indistinguishable from a duplicate delivery of the original.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        assert (await c.post(_finalize_url(ex, rid, evid), headers=h)).status_code == 200

    # Assert
    [row] = await _event_rows(migrated_db, rid)
    _status, _overall, version = await _report_row(migrated_db, rid)
    assert row.details["grade_version"] == version
    assert version > 0


async def test_report_evaluated_payload_does_not_include_per_evaluator_rows(
    migrated_db: async_sessionmaker,
) -> None:
    """D1 extends to machines — whole-payload scan, not a field check.

    Two evaluators with different grades, so a payload that leaked per-evaluator values would
    contain 9.00 and 5.00 as well as the 7.00 aggregate.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a), (h_b, evid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "9", h_a)
        await _grade(c, ex, rid, evid_b, sid, "5", h_b)
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200
        assert (await c.post(_finalize_url(ex, rid, evid_b), headers=h_b)).status_code == 200

    # Assert
    [row] = await _event_rows(migrated_db, rid)
    payload = row.details
    assert "evaluations" not in payload
    assert "evaluator_breakdown" not in payload
    blob = str(payload)
    assert evid_a not in blob
    assert evid_b not in blob
    assert "9.00" not in blob and "5.00" not in blob  # only the 7.00 aggregate survives
    assert payload["overall_grade"] == "7.00"


async def test_report_evaluated_section_grades_exclude_an_unassigned_evaluator(
    migrated_db: async_sessionmaker,
) -> None:
    """THE PAYLOAD MUST RECONCILE WITH ITSELF.

    ``overall_grade`` counts only contributing evaluations (L7), so ``section_grades`` must be
    aggregated over the same set. Averaged over every row instead, a payload would publish
    section values that do not add up to the overall grade it ships alongside them — and the
    consumer has no way to tell which half to trust.

    Two evaluators grade 9 and 5; the 5 is unassigned before the gate closes. Both halves must
    then read 9.00.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h_a, evid_a), (h_b, evid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "9", h_a)
        await _grade(c, ex, rid, evid_b, sid, "5", h_b)
        await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/unassign",
            json={"reason": "unavailable"},
            headers=ah,
        )

        # Act
        assert (await c.post(_finalize_url(ex, rid, evid_a), headers=h_a)).status_code == 200

    # Assert
    [row] = await _event_rows(migrated_db, rid)
    assert row.details["overall_grade"] == "9.00"
    [section] = row.details["section_grades"]
    assert section["grade"] == "9.00"


# ======================================================================================
# W5-3 Task 12 — concurrent finalize by two evaluators.
#
# THE RACE: finalize reads every sibling evaluation, then writes the parent report. Two
# evaluators pressing the button at the same instant each read a pre-state in which the other
# has not finished, so without serialization you get one of two wrong outcomes:
#
#   * neither transitions — both see a gate that is still closed, and the report is stuck
#     ``under_evaluation`` with every evaluator finished; or
#   * a lost update — each aggregates over its own contribution alone and the last write wins
#     with half the data, publishing a grade that averages one evaluator.
#
# HOW MUCH OF THIS THE HTTP TESTS ACTUALLY COVER: less than it looks. ``asyncio.gather`` over
# ``httpx.ASGITransport`` does NOT overlap requests in this harness — measured at the handler
# boundary, request 2 does not enter until request 1 has returned, with one shared client or
# two. So the gathered tests below are BACK-TO-BACK calls: they pin the idempotence of the
# outcome (one transition, one event, one version bump, a clean 409) but they cannot fail on a
# lost update or a stale read.
#
# The race itself is therefore exercised at the session level, in the two tests at the end of
# this block, where two transactions can be driven against each other deterministically.
#
# LOCK ORDER IS ALWAYS report-then-evaluation. W5-4's reopen must take the same order or the
# two slices deadlock against each other in production.
# ======================================================================================


async def _two_graded_evaluators(migrated_db, c, ah, *, grades=("8", "6")):
    """A submitted report with two evaluators who have graded but not finalized."""
    ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=2)
    for (h, evid), value in zip(graders, grades, strict=True):
        await _grade(c, ex, rid, evid, sid, value, h)
    return ex, rid, sid, graders


async def test_back_to_back_finalize_by_two_evaluators_transitions_the_report_exactly_once(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, graders = await _two_graded_evaluators(migrated_db, c, ah)
        (h_a, evid_a), (h_b, evid_b) = graders

        # Act: gathered, though the harness runs them back-to-back (see the note above).
        first, second = await asyncio.gather(
            c.post(_finalize_url(ex, rid, evid_a), headers=h_a),
            c.post(_finalize_url(ex, rid, evid_b), headers=h_b),
        )

    # Assert
    assert {first.status_code, second.status_code} == {200}, (first.text, second.text)
    assert (await _report_row(migrated_db, rid))[0] == "evaluated"
    actions = await _audit_actions(migrated_db, rid)
    assert actions.count("report.evaluated") == 1
    assert len(await _event_rows(migrated_db, rid)) == 1


async def test_back_to_back_finalize_by_two_evaluators_produces_a_consistent_aggregate(
    migrated_db: async_sessionmaker,
) -> None:
    """THE LOST-UPDATE ASSERTION.

    Grades 8 and 6 at equal weight aggregate to 7.00. Either request aggregating over its own
    contribution alone would publish 8.00 or 6.00 — both plausible-looking numbers, which is
    what makes this failure mode survive review.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, graders = await _two_graded_evaluators(migrated_db, c, ah, grades=("8", "6"))
        (h_a, evid_a), (h_b, evid_b) = graders

        # Act
        await asyncio.gather(
            c.post(_finalize_url(ex, rid, evid_a), headers=h_a),
            c.post(_finalize_url(ex, rid, evid_b), headers=h_b),
        )

    # Assert
    status, overall, _version = await _report_row(migrated_db, rid)
    assert status == "evaluated"
    assert overall == Decimal("7.00")


async def test_second_finalize_on_the_same_evaluation_returns_409_not_a_duplicate_transition(
    migrated_db: async_sessionmaker,
) -> None:
    """Two presses of ONE evaluator's button — the guard must reject, not re-transition."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, [(h, evid)] = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, evid, sid, "8", h)

        # Act
        first, second = await asyncio.gather(
            c.post(_finalize_url(ex, rid, evid), headers=h),
            c.post(_finalize_url(ex, rid, evid), headers=h),
        )

    # Assert: exactly one wins, the other is a clean 409 — never a 500 from a duplicate
    # transition escaping as InvalidTransition.
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["message"] == "already_finalized"
    assert (await _audit_actions(migrated_db, rid)).count("report.evaluated") == 1


async def test_losing_a_finalize_race_does_not_double_bump_grade_version(
    migrated_db: async_sessionmaker,
) -> None:
    """D3 — the version identifies the published grade, so one crossing is one version.

    Two concurrent finalizes publish one aggregate between them. A version bumped twice would
    tell every consumer the grade changed again when it did not.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, graders = await _two_graded_evaluators(migrated_db, c, ah, grades=("8", "8"))
        (h_a, evid_a), (h_b, evid_b) = graders

        # Act: identical grades, so the aggregate is 8.00 no matter who lands first and the
        # version can only move for a real publication.
        await asyncio.gather(
            c.post(_finalize_url(ex, rid, evid_a), headers=h_a),
            c.post(_finalize_url(ex, rid, evid_b), headers=h_b),
        )

    # Assert
    _status, overall, version = await _report_row(migrated_db, rid)
    assert overall == Decimal("8.00")
    assert version == 1


# --- the race, where it can actually be driven: two transactions ------------------------


async def _report_ids(migrated_db, c, ah):
    """A submitted, graded, single-evaluator report. Returns (exercise_id, report_id)."""
    ex, rid, sid = await submitted_report(c, ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, "lock-0")
    evid = await assign(c, ah, ex, rid, uid)
    await _grade(c, ex, rid, evid, sid, "8", h)
    return ex, rid


async def test_get_report_for_update_sees_state_committed_by_another_transaction(
    migrated_db: async_sessionmaker,
) -> None:
    """THE STALE-READ BUG THIS TASK EXISTS TO CLOSE.

    Locking the row is not enough on its own. A handler that loads the report, THEN blocks on
    the lock, still holds the attribute values it read before waiting — the sessionmaker uses
    ``expire_on_commit=False``, so nothing invalidates them. The loser of a finalize race would
    read ``status == 'under_evaluation'`` from that snapshot, decide the report had not crossed
    yet, and emit a second ``report.evaluated`` for one crossing.

    Acquiring the lock and re-reading the row must be the same operation.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid = await _report_ids(migrated_db, c, ah)

    async with migrated_db() as s1:
        await _get_report(s1, uuid.UUID(ex), uuid.UUID(rid))  # the pre-lock snapshot
        async with migrated_db() as s2:  # another request wins the race and commits
            await s2.execute(text("UPDATE report SET status = 'evaluated' WHERE id = CAST(:i AS uuid)"), {"i": rid})
            await s2.commit()

        # Act
        locked = await _get_report_for_update(s1, uuid.UUID(ex), uuid.UUID(rid))

    # Assert
    assert locked.status == "evaluated"


async def test_get_report_for_update_blocks_a_second_transaction_until_the_first_commits(
    migrated_db: async_sessionmaker,
) -> None:
    """Mutual exclusion, asserted rather than assumed.

    ``lock_timeout`` is what makes this deterministic: the second transaction is told to give
    up after 250ms instead of blocking the suite, so a lock that was never taken shows up as a
    PASSING acquisition where a failure is expected.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid = await _report_ids(migrated_db, c, ah)

    async with migrated_db() as holder:
        await _get_report_for_update(holder, uuid.UUID(ex), uuid.UUID(rid))

        # Act / Assert: a second transaction cannot take the same row.
        async with migrated_db() as contender:
            await contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
            with pytest.raises(DBAPIError):
                await _get_report_for_update(contender, uuid.UUID(ex), uuid.UUID(rid))

        await holder.commit()

    # …and once released, it is available again.
    async with migrated_db() as after:
        await after.execute(text("SET LOCAL lock_timeout = '250ms'"))
        assert (await _get_report_for_update(after, uuid.UUID(ex), uuid.UUID(rid))).id is not None
