"""W5-4 Task 2 — ``POST .../evaluations/{evid}/reopen``: guards and authz.

Guards land before behaviour so Task 3's mutation cannot quietly pass through a check that
was never written. Every case here asserts the rejection AND that nothing moved: a guard
placed after the mutation still returns the right status code, and only
``test_rejected_reopen_never_mutates_or_audits`` notices.

Path shape follows this surface's documented nesting — under the report, not a flat
``/evaluations/{id}`` — so the exercise-scoped permission dependency has an ``exercise_id``
to resolve against.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import (
    assign,
    evaluator,
    finalize,
    ga_headers,
    role_holder,
    submitted_report,
)
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

_REOPEN_ACTION = "evaluation.reopened"


def _reopen_url(ex: str, rid: str, evid: str) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen"


async def _grade(c, ex, rid, evid, sid, value, headers) -> None:
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _completed_world(migrated_db, c, ah):
    """Submitted report -> one assigned evaluator -> graded -> finalized.

    Returns (ex, rid, sid, evaluator_headers, evid) with the evaluation ``completed`` and the
    report ``evaluated`` — the only state a reopen is ever allowed to act on.
    """
    ex, rid, sid = await submitted_report(c, ah)
    eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
    evid = await assign(c, ah, ex, rid, uid)
    await _grade(c, ex, rid, evid, sid, 7, eh)
    await finalize(c, eh, ex, rid, evid)
    return ex, rid, sid, eh, evid


async def _evaluation_reopen_columns(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT status, reopen_count, reopened_at, reopened_by FROM evaluation WHERE id = CAST(:i AS uuid)"
                ),
                {"i": evid},
            )
        ).one()


async def _reopen_audit_count(migrated_db, evid) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM audit_log WHERE action = :a AND resource_id = CAST(:i AS uuid)"),
                {"a": _REOPEN_ACTION, "i": evid},
            )
        ).scalar_one()


# --- the no-migration claim, asserted rather than assumed -----------------------------


async def test_reopen_columns_exist_from_the_w5_1_migration(migrated_db: async_sessionmaker) -> None:
    """W5-4 adds no migration: the three columns come from W5-1's ``0011``.

    Asserted instead of trusted — if a later edit to ``0011`` drops them, the failure should
    name the missing column here rather than surface as an opaque 500 from the Task 3 mutation.
    """
    # Arrange / Act
    async with migrated_db() as s:
        cols = await s.run_sync(lambda sync_s: {c["name"] for c in inspect(sync_s.bind).get_columns("evaluation")})

    # Assert
    assert {"reopen_count", "reopened_at", "reopened_by"} <= cols


# --- authz ----------------------------------------------------------------------------


async def test_reopen_requires_authentication(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"})

    # Assert
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("role_key", ["team_admin", "team_writer", "team_approver", "observer"])
async def test_reopen_is_forbidden_for_every_exercise_role(migrated_db: async_sessionmaker, role_key: str) -> None:
    """Reopen is Global-Admin only. No exercise-scoped role reaches it, however privileged."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        rh, _ = await role_holder(migrated_db, c, ah, ex, f"rh-{role_key}", role_key)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=rh)

    # Assert
    assert r.status_code == 403, r.text


async def test_reopen_is_forbidden_for_the_owning_evaluator(migrated_db: async_sessionmaker) -> None:
    """The strongest form of the rule: not even the evaluator may un-finalize their own work.

    There is no self-revert path. Evaluator isolation removes the reconciliation window that
    would justify one, so the only way back into grading is an admin reopen.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=eh)

    # Assert
    assert r.status_code == 403, r.text


async def test_reopen_returns_404_for_an_unknown_evaluation(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, _evid = await _completed_world(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, str(uuid.uuid4())), json={"reason": "recount"}, headers=ah)

    # Assert
    assert r.status_code == 404, r.text
    assert r.json()["error"]["message"] == "evaluation_not_found"


# --- the mandatory reason -------------------------------------------------------------


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
async def test_reopen_requires_a_non_blank_reason(migrated_db: async_sessionmaker, body: dict[str, str]) -> None:
    """All three shapes are one error, not two.

    A whitespace-only reason is the case a schema constraint cannot catch, so the check lives
    in the handler and the omitted key is routed through it too — otherwise a missing key and
    a blank one answer with different payloads for the same mistake.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json=body, headers=ah)

    # Assert
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == "reason_required"


# --- state guards ---------------------------------------------------------------------


async def test_reopen_is_rejected_when_the_evaluation_was_never_finalized(
    migrated_db: async_sessionmaker,
) -> None:
    """``assigned`` and ``in_progress`` both fail: there is no finalized state to undo."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
        evid = await assign(c, ah, ex, rid, uid)

        # Act / Assert — still 'assigned'
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=ah)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["message"] == "not_finalized"

        # Arrange — the first grade moves it to 'in_progress'
        await _grade(c, ex, rid, evid, sid, 7, eh)

        # Act / Assert
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=ah)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["message"] == "not_finalized"


async def test_reopen_is_rejected_when_the_evaluator_was_unassigned(
    migrated_db: async_sessionmaker,
) -> None:
    """An unassigned seat stays out of the counted set. Reopening it would re-enter a weight
    the rollup has already renormalized away, so the unassigned check precedes the status one.
    """
    # Arrange: a second evaluator keeps the report gradeable after the first is dropped.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh0, uid0 = await evaluator(migrated_db, c, ah, ex, "ev-0")
        _eh1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev-1")
        evid0 = await assign(c, ah, ex, rid, uid0)
        await assign(c, ah, ex, rid, uid1)
        await _grade(c, ex, rid, evid0, sid, 7, eh0)
        await finalize(c, eh0, ex, rid, evid0)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid0}/unassign",
            json={"reason": "left the exercise"},
            headers=ah,
        )
        assert r.status_code == 200, r.text

        # Act
        r = await c.post(_reopen_url(ex, rid, evid0), json={"reason": "recount"}, headers=ah)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_unassigned"


# --- the guard-ordering test ----------------------------------------------------------


async def test_rejected_reopen_never_mutates_or_audits(migrated_db: async_sessionmaker) -> None:
    """Every rejection above must leave the evaluation untouched.

    This is the test that catches a guard written AFTER the mutation: such a handler still
    answers 403/404/409/422, and every other test here would pass.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        anon_token, _ = await make_user_token(migrated_db, jti="nobody")
        rejections = (
            (None, {"reason": "recount"}),
            ({"Authorization": f"Bearer {anon_token}"}, {"reason": "recount"}),
            (eh, {"reason": "recount"}),
            (ah, {}),
            (ah, {"reason": "   "}),
        )

        # Act
        for headers, body in rejections:
            r = await c.post(_reopen_url(ex, rid, evid), json=body, headers=headers)
            assert r.status_code in (401, 403, 422), r.text

    # Assert — the completed evaluation is exactly as finalize left it.
    status, reopen_count, reopened_at, reopened_by = await _evaluation_reopen_columns(migrated_db, evid)
    assert status == "completed"
    assert reopen_count == 0
    assert reopened_at is None
    assert reopened_by is None
    assert await _reopen_audit_count(migrated_db, evid) == 0


# --- W5-4 Task 3: the mutation -------------------------------------------------------


async def _evaluation_finalize_columns(migrated_db, evid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(
                    "SELECT status, completed_at, finalized_by, finalize_is_admin_override, "
                    "finalize_comment, reopen_count, reopened_at, reopened_by, overall_feedback "
                    "FROM evaluation WHERE id = CAST(:i AS uuid)"
                ),
                {"i": evid},
            )
        ).one()


async def _reopen(c, ah, ex, rid, evid, *, reason: str = "recount after dispute"):
    r = await c.post(_reopen_url(ex, rid, evid), json={"reason": reason}, headers=ah)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_reopen_sets_the_evaluation_back_to_in_progress(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.status == "in_progress"


async def test_reopen_increments_reopen_count(migrated_db: async_sessionmaker) -> None:
    """0 -> 1. The counter is how a later dispute knows a grade was revisited at all."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        before = (await _evaluation_finalize_columns(migrated_db, evid)).reopen_count

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    after = (await _evaluation_finalize_columns(migrated_db, evid)).reopen_count
    assert (before, after) == (0, 1)


async def test_reopen_stamps_reopened_at_and_reopened_by(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, ga_uid = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.reopened_at is not None
    assert str(row.reopened_by) == ga_uid


async def test_reopen_clears_completed_at(migrated_db: async_sessionmaker) -> None:
    """A reopened evaluation is not complete, so it must not carry a completion time.

    The previous value is deliberately not preserved on the row — ``audit_log`` is the
    dispute trail, and a column that means two different things depending on ``status`` is
    worse than one that is simply absent.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        assert (await _evaluation_finalize_columns(migrated_db, evid)).completed_at is not None

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    assert (await _evaluation_finalize_columns(migrated_db, evid)).completed_at is None


async def test_reopen_clears_the_finalize_and_admin_override_fields(
    migrated_db: async_sessionmaker,
) -> None:
    """A stale override flag would misattribute the NEXT finalize.

    Set up the worst case on purpose: an admin finalize-on-behalf-of, which is the only path
    that writes all three fields. If reopen leaves them behind, the evaluator's own later
    finalize inherits someone else's comment and an override flag it never earned.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
        evid = await assign(c, ah, ex, rid, uid)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize",
            json={"on_behalf_of": uid, "comment": "evaluator unreachable"},
            headers=ah,
        )
        assert r.status_code == 200, r.text
        before = await _evaluation_finalize_columns(migrated_db, evid)
        assert before.finalize_is_admin_override is True
        assert before.finalize_comment == "evaluator unreachable"

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.finalized_by is None
    assert row.finalize_is_admin_override is False
    assert row.finalize_comment is None


async def test_reopen_preserves_the_evaluators_section_grades(migrated_db: async_sessionmaker) -> None:
    """Reopen un-finalizes; it does NOT erase work.

    This is the whole difference between a reopen and an unassign-then-reassign. The evaluator
    resumes from the grades they already entered.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid)
        r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades", headers=eh)

    # Assert
    assert r.status_code == 200, r.text
    grades = r.json()["data"]
    assert len(grades) == 1
    assert grades[0]["grade"] == "7.00"


async def test_reopen_preserves_the_evaluators_overall_feedback(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
        evid = await assign(c, ah, ex, rid, uid)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}",
            json={"overall_feedback": "solid analysis, thin on attribution"},
            headers=eh,
        )
        assert r.status_code == 200, r.text
        await finalize(c, eh, ex, rid, evid)

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.overall_feedback == "solid analysis, thin on attribution"


async def test_reopen_response_shows_the_updated_row_in_the_breakdown(
    migrated_db: async_sessionmaker,
) -> None:
    """The caller must not have to re-fetch to see what their own call did."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        data = await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = next(e for e in data["evaluations"] if e["id"] == evid)
    assert row["status"] == "in_progress"
    assert row["reopen_count"] == 1
    assert row["completed_at"] is None
    assert row["finalized_by"] is None
    assert row["finalize_is_admin_override"] is False


# --- W5-4 Task 4: grade version, report status, supersession --------------------------

_REOPENED_EVENT = "event.report_evaluation_reopened"
_EVALUATED_EVENT = "event.report_evaluated"


async def _report_row(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, overall_grade, grade_version FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def _audit_details(migrated_db, action: str, resource_id: str) -> list[dict]:
    """Every audit row for one action on one resource, oldest first."""
    async with migrated_db() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT details FROM audit_log WHERE action = :a AND resource_id = CAST(:i AS uuid) "
                    "ORDER BY created_at, id"
                ),
                {"a": action, "i": resource_id},
            )
        ).scalars()
        return list(rows)


async def _multi_evaluator_world(migrated_db, c, ah, grades: tuple[int, ...]):
    """Submitted report, one grader per entry in ``grades``, each finalized at that grade.

    Returns (ex, rid, [(headers, evaluation_id), ...]) with the report ``evaluated``.
    """
    ex, rid, sid = await submitted_report(c, ah)
    graders = []
    for i, value in enumerate(grades):
        eh, uid = await evaluator(migrated_db, c, ah, ex, f"ev-{i}")
        evid = await assign(c, ah, ex, rid, uid)
        await _grade(c, ex, rid, evid, sid, value, eh)
        graders.append((eh, evid))
    for eh, evid in graders:
        await finalize(c, eh, ex, rid, evid)
    return ex, rid, graders


async def test_reopen_after_evaluated_returns_the_report_to_under_evaluation(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        assert (await _report_row(migrated_db, rid)).status == "evaluated"

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    assert (await _report_row(migrated_db, rid)).status == "under_evaluation"


async def test_reopen_bumps_the_grade_version(migrated_db: async_sessionmaker) -> None:
    """1 -> 2. The version is a consumer's only way to tell a regrade from a redelivery."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        before = (await _report_row(migrated_db, rid)).grade_version

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    assert (before, (await _report_row(migrated_db, rid)).grade_version) == (1, 2)


async def test_reopen_recomputes_the_aggregate_over_the_remaining_completed_evaluations(
    migrated_db: async_sessionmaker,
) -> None:
    """A reopened evaluation still COUNTS but no longer CONTRIBUTES a grade.

    Three equal weights at 9 / 6 / 6 average 7.00. Reopening the 9 leaves the numerator to the
    two sixes — 6.00, not 7.00. A result of 7.00 here would mean the contributing predicate is
    filtering on unassignment alone and ignoring status.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, graders = await _multi_evaluator_world(migrated_db, c, ah, (9, 6, 6))
        assert str((await _report_row(migrated_db, rid)).overall_grade) == "7.00"

        # Act — reopen the outlier
        await _reopen(c, ah, ex, rid, graders[0][1])

    # Assert
    assert str((await _report_row(migrated_db, rid)).overall_grade) == "6.00"


async def test_reopen_of_the_only_evaluation_nulls_the_overall_grade(
    migrated_db: async_sessionmaker,
) -> None:
    """Nothing contributes, so the report publishes no grade at all.

    NULL rather than a stale number: the report is back under evaluation and there is currently
    no completed evaluation standing behind any figure.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    row = await _report_row(migrated_db, rid)
    assert row.overall_grade is None
    assert row.grade_version == 2


async def test_reopen_while_the_report_is_still_under_evaluation_does_not_transition(
    migrated_db: async_sessionmaker,
) -> None:
    """No transition to invent: the report never reached ``evaluated``.

    Under the default policy a second, unfinished evaluator holds the gate shut. The reopen
    still mutates and still bumps the version, but writes no report-level transition row —
    ``under_evaluation -> under_evaluation`` is not an edge.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh0, uid0 = await evaluator(migrated_db, c, ah, ex, "ev-0")
        eh1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev-1")
        evid0 = await assign(c, ah, ex, rid, uid0)
        evid1 = await assign(c, ah, ex, rid, uid1)
        await _grade(c, ex, rid, evid0, sid, 8, eh0)
        await _grade(c, ex, rid, evid1, sid, 4, eh1)
        await finalize(c, eh0, ex, rid, evid0)
        assert (await _report_row(migrated_db, rid)).status == "under_evaluation"

        # Act
        await _reopen(c, ah, ex, rid, evid0)

    # Assert
    assert (await _report_row(migrated_db, rid)).status == "under_evaluation"
    assert await _audit_details(migrated_db, "report.reopened", rid) == []


async def test_reopen_emits_the_supersession_event_with_the_superseded_version(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    events = await _audit_details(migrated_db, _REOPENED_EVENT, rid)
    assert len(events) == 1
    assert events[0]["superseded_grade_version"] == 1
    assert events[0]["grade_version"] == 2


async def test_reopen_does_not_re_emit_report_evaluated(migrated_db: async_sessionmaker) -> None:
    """The report is no longer evaluated. Emitting it here would state the opposite of fact."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        before = len(await _audit_details(migrated_db, _EVALUATED_EVENT, rid))

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    assert (before, len(await _audit_details(migrated_db, _EVALUATED_EVENT, rid))) == (1, 1)


async def test_the_original_report_evaluated_event_is_not_retracted(
    migrated_db: async_sessionmaker,
) -> None:
    """The already-emitted event stands, unmodified. This is INTENDED, not an oversight.

    There is no retraction event in the contract and delivery is at-least-once, so a consumer
    that already received the original cannot be told to forget it. Supersession — a higher
    ``grade_version`` in a later event — is the only mechanism available.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)
        original = (await _audit_details(migrated_db, _EVALUATED_EVENT, rid))[0]

        # Act
        await _reopen(c, ah, ex, rid, evid)

    # Assert
    after = await _audit_details(migrated_db, _EVALUATED_EVENT, rid)
    assert len(after) == 1
    assert after[0] == original
    assert after[0]["grade_version"] == 1  # still describes the superseded grade


async def test_the_supersession_payload_excludes_the_reason_text(
    migrated_db: async_sessionmaker,
) -> None:
    """A reason may name someone's absence or performance. Event payloads leave the
    deployment; the reason is audit-only."""
    # Arrange
    secret = "evaluator was clearly asleep"
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed_world(migrated_db, c, ah)

        # Act
        await _reopen(c, ah, ex, rid, evid, reason=secret)

    # Assert
    payload = (await _audit_details(migrated_db, _REOPENED_EVENT, rid))[0]
    assert "reason" not in payload
    assert secret not in str(payload)
    # ...but it IS recoverable from the evaluation's own audit row.
    assert (await _audit_details(migrated_db, _REOPEN_ACTION, evid))[0]["reason"] == secret


async def test_the_supersession_payload_excludes_per_evaluator_rows(
    migrated_db: async_sessionmaker,
) -> None:
    """Evaluator isolation extends to machines. A payload outlives the request in an outbox,
    a delivery log and someone else's endpoint — a breakdown shipped there is a durable
    peer-visibility hole."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, graders = await _multi_evaluator_world(migrated_db, c, ah, (9, 6))

        # Act
        await _reopen(c, ah, ex, rid, graders[0][1])

    # Assert
    payload = (await _audit_details(migrated_db, _REOPENED_EVENT, rid))[0]
    assert "evaluations" not in payload
    assert "evaluator_id" not in payload
    flat = str(payload)
    for _eh, evid in graders:
        assert evid not in flat


# --- W5-4 Task 6: the round trip -----------------------------------------------------
#
# Characterization only. Reopen re-enters W5-3's ordinary finalize path — there is no
# reopen-specific finalize branch, and these tests exist to prove that staying true. A failure
# here means the finalize path took a shortcut that assumed a first finalize, not that reopen
# is broken.


async def _finalize(c, headers, ex, rid, evid, **body):
    r = await c.post(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize",
        json=body or None,
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _event_versions(migrated_db, rid) -> list[int]:
    return [e["grade_version"] for e in await _audit_details(migrated_db, _EVALUATED_EVENT, rid)]


async def test_a_reopened_evaluation_can_be_finalized_again(migrated_db: async_sessionmaker) -> None:
    """Back to ``completed`` with a fresh completion time — and the reopen counter stands.

    ``reopen_count`` records history, so re-finalizing must not reset it to zero.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        await _reopen(c, ah, ex, rid, evid)
        assert (await _evaluation_finalize_columns(migrated_db, evid)).completed_at is None

        # Act
        await _finalize(c, eh, ex, rid, evid)

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.status == "completed"
    assert row.completed_at is not None
    assert row.reopen_count == 1


async def test_re_finalize_after_reopen_returns_the_report_to_evaluated(
    migrated_db: async_sessionmaker,
) -> None:
    """Through the ordinary gate, with no reopen-aware special case."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        await _reopen(c, ah, ex, rid, evid)
        assert (await _report_row(migrated_db, rid)).status == "under_evaluation"

        # Act
        await _finalize(c, eh, ex, rid, evid)

    # Assert
    assert (await _report_row(migrated_db, rid)).status == "evaluated"


async def test_the_full_cycle_bumps_the_grade_version_three_times(
    migrated_db: async_sessionmaker,
) -> None:
    """1 on the first finalize, 2 on the reopen, 3 on the re-finalize.

    Asserted as a sequence rather than an endpoint: the version is monotonic, and a consumer
    orders supersessions by it. A cycle that landed back on 1 would make the second publication
    indistinguishable from a redelivery of the first.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        seen = [(await _report_row(migrated_db, rid)).grade_version]

        # Act
        await _reopen(c, ah, ex, rid, evid)
        seen.append((await _report_row(migrated_db, rid)).grade_version)
        await _finalize(c, eh, ex, rid, evid)
        seen.append((await _report_row(migrated_db, rid)).grade_version)

    # Assert
    assert seen == [1, 2, 3]


async def test_re_finalize_re_emits_report_evaluated_with_the_new_version(
    migrated_db: async_sessionmaker,
) -> None:
    """Two publications now stand, at versions 1 and 3.

    The first is not withdrawn — it cannot be — so the second must be distinguishable from it.
    The version is the only thing that does that.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        assert await _event_versions(migrated_db, rid) == [1]

        # Act
        await _reopen(c, ah, ex, rid, evid)
        await _finalize(c, eh, ex, rid, evid)

    # Assert
    assert await _event_versions(migrated_db, rid) == [1, 3]


async def test_a_grade_changed_during_the_reopen_reaches_the_re_emitted_event(
    migrated_db: async_sessionmaker,
) -> None:
    """Otherwise the whole reopen is theatre.

    The point of returning an evaluation to grading is that the grade can change; if the
    re-published aggregate still carried the old number, nothing would have been achieved.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, eh, evid = await _completed_world(migrated_db, c, ah)
        await _reopen(c, ah, ex, rid, evid)

        # Act — the evaluator revises 7 up to 9, then finalizes again
        await _grade(c, ex, rid, evid, sid, 9, eh)
        await _finalize(c, eh, ex, rid, evid)

    # Assert
    assert str((await _report_row(migrated_db, rid)).overall_grade) == "9.00"
    published = await _audit_details(migrated_db, _EVALUATED_EVENT, rid)
    assert published[-1]["overall_grade"] == "9.00"
    assert published[0]["overall_grade"] == "7.00"  # the superseded publication is untouched


async def test_a_second_cycle_increments_the_reopen_count_to_two(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed_world(migrated_db, c, ah)
        await _reopen(c, ah, ex, rid, evid)
        await _finalize(c, eh, ex, rid, evid)

        # Act
        await _reopen(c, ah, ex, rid, evid, reason="second dispute")

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.reopen_count == 2
    assert row.status == "in_progress"


async def test_an_admin_can_finalize_on_behalf_of_after_a_reopen(
    migrated_db: async_sessionmaker,
) -> None:
    """The override composes with reopen — and lands cleanly on a row whose first finalize
    was NOT an override.

    This is precisely why the reopen clears the override fields: the flag here must be True
    because of THIS finalize, not left over from an earlier one.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
        evid = await assign(c, ah, ex, rid, uid)
        await _grade(c, ex, rid, evid, sid, 7, eh)
        await _finalize(c, eh, ex, rid, evid)  # the evaluator's own, no override
        assert (await _evaluation_finalize_columns(migrated_db, evid)).finalize_is_admin_override is False
        await _reopen(c, ah, ex, rid, evid)

        # Act — the evaluator has since become unreachable
        await _finalize(c, ah, ex, rid, evid, on_behalf_of=uid, comment="evaluator on leave")

    # Assert
    row = await _evaluation_finalize_columns(migrated_db, evid)
    assert row.status == "completed"
    assert row.finalize_is_admin_override is True
    assert row.finalize_comment == "evaluator on leave"


# --- the unchanged-grade reopen ------------------------------------------------------


async def test_a_reopen_that_does_not_move_the_grade_still_bumps_the_version(
    migrated_db: async_sessionmaker,
) -> None:
    """A supersession event must never claim that version N supersedes version N.

    Two evaluators who agree exactly: both grade 8, the aggregate is 8.00. Reopening one
    leaves the other contributing the same 8.00, so the published NUMBER is unchanged — but a
    publication still happened, because the report left ``evaluated`` and its grade now rests
    on one evaluation instead of two.

    The recompute normally bumps only when the number moves, which is right for a grade save:
    bumping on every keystroke would tell consumers the grade changed when it did not. A
    reopen is the opposite case — the state changed even though the number did not — so the
    reopen asks for the bump explicitly.

    Identical grades are not an exotic case; two evaluators agreeing is the expected outcome.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, graders = await _multi_evaluator_world(migrated_db, c, ah, (8, 8))
        before = await _report_row(migrated_db, rid)
        assert str(before.overall_grade) == "8.00"
        assert before.grade_version == 1

        # Act — reopen one; the survivor still averages 8.00
        await _reopen(c, ah, ex, rid, graders[0][1])

    # Assert
    after = await _report_row(migrated_db, rid)
    assert str(after.overall_grade) == "8.00"  # the number genuinely did not move
    assert after.grade_version == 2  # ...but the publication is a new one
    event = (await _audit_details(migrated_db, _REOPENED_EVENT, rid))[0]
    assert (event["superseded_grade_version"], event["grade_version"]) == (1, 2)
