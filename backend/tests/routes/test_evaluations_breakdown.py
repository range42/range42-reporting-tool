"""W5-3 Task 10 — the per-evaluator breakdown, D1-scoped, with D4a ``completed_at``.

ONE ROUTE, TWO AUDIENCES. ``GET …/evaluations`` answers two different questions depending on
who asks, and the difference is the whole security surface of this slice:

* Global Admin — every evaluator row, including soft-unassigned ones, with names and weights.
  This is the dispute-resolution view.
* Evaluator — **exactly one row, their own**, plus the report's shared aggregate. Never a peer
  row, never a peer id, never a peer name (D1/E1, locked).

WHY THIS ROUTE STOPPED BEING A FILTER AND BECAME A GATE. W5-1 (#95) shipped this as a list
that merely filtered to the caller's rows, so an evaluator with no evaluation on the report got
``200 []`` — harmless, because an empty list disclosed nothing. Task 10 adds the report-level
``aggregate`` to the SAME response, and an empty ``evaluations[]`` no longer means an empty
body: it would hand a non-participant the report's grade, its grade_version and its evaluator
headcount. The premise of #95's asymmetry expired, so the route now gates. See #122.

THE ONE THING THAT MUST NOT REGRESS: gating on row EXISTENCE, not on the L7 counted predicate.
An unassigned evaluator keeps their row (L8, soft unassign) precisely so the dispute trail
survives — gating on ``counts()`` would blind them to the report they graded, destroying the
guarantee W5-3 Task 9 exists to provide.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.evaluation.finalize_gate import ALL_MUST_FINALIZE, ANY_CAN_FINALIZE
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations"


async def _world(migrated_db, c, ah, *, evaluators=2):
    """Submitted report with `evaluators` graders. Returns (ex, rid, sid, [(h, evid, uid), ...])."""
    ex, rid, sid = await submitted_report(c, ah)
    graders = []
    for i in range(evaluators):
        h, uid = await evaluator(migrated_db, c, ah, ex, f"bd-ev-{i}")
        graders.append((h, await assign(c, ah, ex, rid, uid), uid))
    return ex, rid, sid, graders


async def _grade(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _set_policy(migrated_db, ex, mode):
    async with migrated_db() as s:
        await s.execute(
            text("UPDATE scoring_config SET finalize_policy = :m WHERE exercise_id = CAST(:e AS uuid)"),
            {"m": mode, "e": ex},
        )
        await s.commit()


# --- the Global-Admin view ------------------------------------------------------------


async def test_global_admin_breakdown_lists_every_evaluator_row(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, graders = await _world(migrated_db, c, ah)

        # Act
        r = await c.get(_url(ex, rid), headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["report_id"] == rid
    assert {row["evaluator_id"] for row in data["evaluations"]} == {uid for _h, _e, uid in graders}
    assert all(row["evaluator_display_name"] for row in data["evaluations"])


async def test_global_admin_breakdown_exposes_completed_at_per_evaluator(
    migrated_db: async_sessionmaker,
) -> None:
    """D4a — a response-shape change only, for dispute auditability of who finalized when."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, uid_a), (h_b, _evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await finalize(c, h_a, ex, rid, evid_a)

        # Act
        r = await c.get(_url(ex, rid), headers=ah)

    # Assert: the finalized row carries a timestamp, the unfinished one carries null.
    rows = {row["evaluator_id"]: row for row in r.json()["data"]["evaluations"]}
    assert rows[uid_a]["completed_at"] is not None
    assert rows[uid_a]["finalized_by"] == uid_a
    assert all(row["completed_at"] is None for uid, row in rows.items() if uid != uid_a)


async def test_global_admin_breakdown_includes_unassigned_rows_with_their_reason(
    migrated_db: async_sessionmaker,
) -> None:
    """L8: the removed evaluator stays visible to the admin — that IS the dispute trail."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, evid_b, uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)
        assert (
            await c.post(
                f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_b}/unassign",
                json={"reason": "left the org"},
                headers=ah,
            )
        ).status_code == 200

        # Act
        r = await c.get(_url(ex, rid), headers=ah)

    # Assert
    rows = {row["evaluator_id"]: row for row in r.json()["data"]["evaluations"]}
    assert len(rows) == 2  # the unassigned row is still listed
    assert rows[uid_b]["unassigned_at"] is not None
    assert rows[uid_b]["unassign_reason"] == "left the org"


# --- D1: the evaluator view -----------------------------------------------------------


async def test_evaluator_breakdown_returns_only_their_own_row(migrated_db: async_sessionmaker) -> None:
    """D1 negative case 2."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, uid_a), _b = graders

        # Act
        r = await c.get(_url(ex, rid), headers=h_a)

    # Assert
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["evaluations"]
    assert len(rows) == 1
    assert rows[0]["evaluator_id"] == uid_a
    assert rows[0]["id"] == evid_a


async def test_evaluator_breakdown_response_contains_no_peer_identifiers(
    migrated_db: async_sessionmaker,
) -> None:
    """D1 negative case 3 — whole-body string scan.

    A field-level assertion misses a nested-relationship leak; serializing the entire body and
    searching it does not. The peer's display name is asserted too, because a name is an
    identity even when the id is absent.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, _evid_a, _uid_a), (h_b, evid_b, uid_b) = graders
        await _grade(c, ex, rid, evid_b, sid, "4", h_b)
        await finalize(c, h_b, ex, rid, evid_b)

        # Act
        r = await c.get(_url(ex, rid), headers=h_a)

    # Assert
    body = r.text
    assert uid_b not in body
    assert evid_b not in body
    assert "bd-ev-1" not in body  # the peer's display name / jti


async def test_evaluator_breakdown_includes_the_shared_aggregate_and_counted_count(
    migrated_db: async_sessionmaker,
) -> None:
    """A cardinality is not an identity (plan §5).

    The evaluator is told their judgment is one of N, because otherwise they cannot read the
    aggregate honestly. They are NOT told who the other N-1 are.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah, evaluators=3)
        (h_a, evid_a, _uid_a), (h_b, evid_b, _uid_b), (h_c, evid_c, _uid_c) = graders
        for h, evid in ((h_a, evid_a), (h_b, evid_b), (h_c, evid_c)):
            await _grade(c, ex, rid, evid, sid, "6", h)
        await finalize(c, h_a, ex, rid, evid_a)
        await finalize(c, h_b, ex, rid, evid_b)

        # Act
        r = await c.get(_url(ex, rid), headers=h_a)

    # Assert
    agg = r.json()["data"]["aggregate"]
    assert agg["counted_evaluator_count"] == 3
    assert agg["completed_evaluator_count"] == 2
    assert len(r.json()["data"]["evaluations"]) == 1


# --- the gate state -------------------------------------------------------------------


async def test_breakdown_reports_the_current_finalize_policy_and_gate_state(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), (h_b, _evid_b, _uid_b) = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        await finalize(c, h_a, ex, rid, evid_a)

        # Act: one of two finalized. Strict mode is still closed; permissive mode is open.
        strict = await c.get(_url(ex, rid), headers=ah)
        await _set_policy(migrated_db, ex, ANY_CAN_FINALIZE)
        permissive = await c.get(_url(ex, rid), headers=ah)

    # Assert
    assert strict.json()["data"]["finalize_policy"] == ALL_MUST_FINALIZE
    assert strict.json()["data"]["finalize_gate_satisfied"] is False
    assert permissive.json()["data"]["finalize_policy"] == ANY_CAN_FINALIZE
    assert permissive.json()["data"]["finalize_gate_satisfied"] is True


async def test_breakdown_aggregate_is_null_before_any_evaluation_is_completed(
    migrated_db: async_sessionmaker,
) -> None:
    """Null because nothing CONTRIBUTES — distinct from a caller who may not see it, who is
    refused outright rather than handed a nulled aggregate."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, _uid_a), _b = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)  # graded, not finalized

        # Act
        r = await c.get(_url(ex, rid), headers=ah)

    # Assert
    agg = r.json()["data"]["aggregate"]
    assert agg["overall_grade"] is None
    assert agg["counted_evaluator_count"] == 2
    assert agg["completed_evaluator_count"] == 0


# --- the gate: who may call this at all -----------------------------------------------


async def test_evaluator_cannot_read_breakdown_for_unassigned_report(
    migrated_db: async_sessionmaker,
) -> None:
    """D1 negative case 7 — 403, NOT an empty list.

    This reverses W5-1/#95's ``200 []``. The response now carries the report's aggregate, so
    letting a non-participant through would disclose the grade, the grade_version and the
    evaluator headcount for a report they have nothing to do with.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _graders = await _world(migrated_db, c, ah)
        outsider_h, _uid = await evaluator(migrated_db, c, ah, ex, "bd-outsider")

        # Act: holds the evaluator role in the exercise, but has no evaluation on this report.
        r = await c.get(_url(ex, rid), headers=outsider_h)

    # Assert
    assert r.status_code == 403, r.text


async def test_unassigned_evaluator_can_still_read_the_breakdown_for_their_dispute_trail(
    migrated_db: async_sessionmaker,
) -> None:
    """THE REGRESSION THIS FILE EXISTS TO PREVENT.

    The gate is row EXISTENCE, not the L7 counted predicate. A soft-unassigned evaluator keeps
    their row (L8) so the dispute trail survives; gating on ``counts()`` would lock them out of
    the very record W5-3 Task 9 preserved for them, and the lockout would be invisible until a
    dispute arrived.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, graders = await _world(migrated_db, c, ah)
        (h_a, evid_a, uid_a), _b = graders
        await _grade(c, ex, rid, evid_a, sid, "8", h_a)
        assert (
            await c.post(
                f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid_a}/unassign",
                json={"reason": "reassigned to another exercise"},
                headers=ah,
            )
        ).status_code == 200

        # Act
        r = await c.get(_url(ex, rid), headers=h_a)

    # Assert
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["evaluations"]
    assert len(rows) == 1
    assert rows[0]["evaluator_id"] == uid_a
    assert rows[0]["unassigned_at"] is not None


@pytest.mark.parametrize("role_key", ["team_admin", "team_writer", "team_approver"])
async def test_team_roles_cannot_read_evaluation_breakdown_before_evaluated(
    migrated_db: async_sessionmaker, role_key: str
) -> None:
    """D1 negative case 6 — §5.2 grants team roles the evaluated RESULT, never the breakdown."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _graders = await _world(migrated_db, c, ah)
        h, _uid = await role_holder(migrated_db, c, ah, ex, f"bd-{role_key}", role_key)

        # Act
        r = await c.get(_url(ex, rid), headers=h)

    # Assert
    assert r.status_code == 403, r.text


async def test_unauthenticated_breakdown_is_401(migrated_db: async_sessionmaker) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _graders = await _world(migrated_db, c, ah)

        # Act
        r = await c.get(_url(ex, rid))

    # Assert
    assert r.status_code == 401, r.text


async def test_global_admin_breakdown_of_a_report_with_no_evaluators(
    migrated_db: async_sessionmaker,
) -> None:
    """A submitted report nobody has been assigned to yet.

    The gate is CLOSED on an empty counted set rather than vacuously open, and the admin gets a
    readable empty state instead of an error — this is the screen someone lands on right after
    submission, before any evaluator exists.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid = await submitted_report(c, ah)

        # Act
        r = await c.get(_url(ex, rid), headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["evaluations"] == []
    assert data["report_status"] == "submitted"
    assert data["finalize_gate_satisfied"] is False
    assert data["aggregate"]["overall_grade"] is None
    assert data["aggregate"]["counted_evaluator_count"] == 0
