"""Finalizing an evaluation a second time, after reopening it.

The round trip an evaluator walks when they revise work they already gave: finalize, find the
second finalize refused, reopen with a reason, edit, finalize again. Each step is asserted at
the API, and the published aggregate is read back from the database — a reopen that answered
200 while leaving ``report.overall_grade`` on the superseded number would otherwise pass every
step individually.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _finalize_url(ex, rid, evid) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/finalize"


def _reopen_url(ex, rid, evid) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen"


async def _grade(c, ex, rid, evid, sid, value, headers):
    return await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )


async def _report_row(migrated_db, rid):
    async with migrated_db() as s:
        return (
            await s.execute(
                text("SELECT status, overall_grade, grade_version FROM report WHERE id = CAST(:i AS uuid)"),
                {"i": rid},
            )
        ).one()


async def _reopen_audit_details(migrated_db, evid) -> list[dict]:
    async with migrated_db() as s:
        rows = await s.execute(
            text(
                "SELECT details FROM audit_log WHERE action = 'evaluation.reopened' "
                "AND resource_id = CAST(:i AS uuid) ORDER BY created_at"
            ),
            {"i": evid},
        )
    return list(rows.scalars().all())


async def _completed(migrated_db, c, ah, *, grade: str = "7"):
    """Submitted report -> one assigned evaluator -> graded -> finalized."""
    ex, rid, sid = await submitted_report(c, ah)
    eh, uid = await evaluator(migrated_db, c, ah, ex, "ev-0")
    evid = await assign(c, ah, ex, rid, uid)
    assert (await _grade(c, ex, rid, evid, sid, grade, eh)).status_code == 200
    await finalize(c, eh, ex, rid, evid)
    return ex, rid, sid, eh, evid


async def test_an_evaluator_can_reopen_regrade_and_finalize_again(migrated_db: async_sessionmaker) -> None:
    """The whole point: work already given is not stranded."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, eh, evid = await _completed(migrated_db, c, ah)
        assert (await c.post(_finalize_url(ex, rid, evid), headers=eh)).status_code == 409

        # Act
        reopened = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=eh)
        regraded = await _grade(c, ex, rid, evid, sid, "9", eh)
        refinalized = await c.post(_finalize_url(ex, rid, evid), headers=eh)

    # Assert
    assert reopened.status_code == 200, reopened.text
    assert regraded.status_code == 200, regraded.text
    assert refinalized.status_code == 200, refinalized.text
    assert refinalized.json()["data"]["finalize_gate_satisfied"] is True


async def test_the_second_finalize_publishes_the_revised_grade(migrated_db: async_sessionmaker) -> None:
    """The report ends on the NEW number, at a NEW version, back in ``evaluated``."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, eh, evid = await _completed(migrated_db, c, ah, grade="7")
        _status, published, version_before = await _report_row(migrated_db, rid)
        assert published == Decimal("7.00")

        # Act
        await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=eh)
        await _grade(c, ex, rid, evid, sid, "9", eh)
        r = await c.post(_finalize_url(ex, rid, evid), headers=eh)
        assert r.status_code == 200, r.text

    # Assert
    status, grade, version_after = await _report_row(migrated_db, rid)
    assert (status, grade) == ("evaluated", Decimal("9.00"))
    assert version_after > version_before


async def test_a_second_finalize_without_a_reopen_is_still_refused(migrated_db: async_sessionmaker) -> None:
    """The reopen is the toll, not a formality to route around.

    A finalize that quietly accepted a completed evaluation would republish a grade version
    behind which nothing had changed, and leave no reason for a dispute to read.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await c.post(_finalize_url(ex, rid, evid), headers=eh)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "already_finalized"


async def test_the_reopen_audit_row_says_the_evaluator_reopened_their_own_work(
    migrated_db: async_sessionmaker,
) -> None:
    """A dispute must be able to tell a self-revision from an admin intervention."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=eh)
        assert r.status_code == 200, r.text

    # Assert
    rows = await _reopen_audit_details(migrated_db, evid)
    assert len(rows) == 1
    assert rows[0]["is_self_reopen"] is True
    assert rows[0]["reason"] == "recount"


async def test_an_admin_reopen_is_not_recorded_as_a_self_reopen(migrated_db: async_sessionmaker) -> None:
    """The mirror of the test above — the flag must distinguish, not always answer True."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await c.post(_reopen_url(ex, rid, evid), json={"reason": "recount"}, headers=ah)
        assert r.status_code == 200, r.text

    # Assert
    rows = await _reopen_audit_details(migrated_db, evid)
    assert rows[0]["is_self_reopen"] is False
