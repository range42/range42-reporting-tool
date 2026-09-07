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
