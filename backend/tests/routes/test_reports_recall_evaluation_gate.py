"""The L14 recall gate: recall is blocked once evaluation has begun (§7.2).

Every test here keeps ``report.status`` at ``submitted`` on purpose. Once ``_begin_evaluation``
has fired the report is ``under_evaluation`` and ``_require_status`` rejects the recall first,
so the gate would never be reached — the tests would pass for the wrong reason.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _recall_url(ex, rid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/recall"


async def _set_evaluation_status(migrated_db, evid, status):
    """Drive evaluation.status directly: the report must stay 'submitted' for this gate to be
    the thing under test (see the module docstring)."""
    async with migrated_db() as s:
        await s.execute(
            text("UPDATE evaluation SET status = :st WHERE id = CAST(:i AS uuid)"), {"st": status, "i": evid}
        )
        await s.commit()


async def _report_status(migrated_db, rid):
    async with migrated_db() as s:
        return (await s.execute(text("SELECT status FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})).scalar_one()


async def test_recall_succeeds_when_no_evaluator_is_assigned(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        r = await c.post(_recall_url(ex, rid), headers=ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "draft"


async def test_recall_succeeds_when_evaluation_is_only_assigned(migrated_db: async_sessionmaker) -> None:
    # Pins §7.2's wording: 'assigned' alone does NOT block recall.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        await assign(c, ah, ex, rid, uid)
        r = await c.post(_recall_url(ex, rid), headers=ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "draft"


@pytest.mark.parametrize("status", ["in_progress", "completed"])
async def test_recall_returns_409_once_evaluation_has_begun(migrated_db: async_sessionmaker, status: str) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        await _set_evaluation_status(migrated_db, evid, status)
        r = await c.post(_recall_url(ex, rid), headers=ah)
        assert r.status_code == 409, r.text


async def test_recall_409_detail_carries_evaluation_in_progress_error_key(migrated_db: async_sessionmaker) -> None:
    # Also proves the ordering: the report is still 'submitted', so _require_status passes and
    # this gate is what produced the 409.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        await _set_evaluation_status(migrated_db, evid, "in_progress")
        assert await _report_status(migrated_db, rid) == "submitted"
        r = await c.post(_recall_url(ex, rid), headers=ah)
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "evaluation_in_progress"


async def test_recall_409_leaves_report_status_unchanged(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        evid = await assign(c, ah, ex, rid, uid)
        await _set_evaluation_status(migrated_db, evid, "completed")
        await c.post(_recall_url(ex, rid), headers=ah)
        assert await _report_status(migrated_db, rid) == "submitted"


async def test_recall_blocked_by_one_evaluator_even_when_a_peer_has_not_started(
    migrated_db: async_sessionmaker,
) -> None:
    # The gate is an ANY, not an ALL.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await submitted_report(c, ah)
        _, uid1 = await evaluator(migrated_db, c, ah, ex, "ev1")
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid1 = await assign(c, ah, ex, rid, uid1)
        await assign(c, ah, ex, rid, uid2)  # stays 'assigned'
        await _set_evaluation_status(migrated_db, evid1, "in_progress")
        assert (await c.post(_recall_url(ex, rid), headers=ah)).status_code == 409
