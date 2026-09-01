import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._evaluations import assign, evaluator, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _url(ex, rid, evid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}"


async def _assigned(migrated_db, c, ah, jti="ev1"):
    """submitted report + one assigned evaluator. Returns (ex, rid, sid, headers, evid)."""
    ex, rid, sid = await submitted_report(c, ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, jti)
    return ex, rid, sid, h, await assign(c, ah, ex, rid, uid)


async def _report_column(migrated_db, rid, column):
    """Read one report column directly. ``column`` is a test-local literal, never user input."""
    async with migrated_db() as s:
        return (
            await s.execute(text(f"SELECT {column} FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})  # noqa: S608
        ).scalar_one()


async def _report_status(migrated_db, rid):
    return await _report_column(migrated_db, rid, "status")


async def test_evaluator_updates_own_overall_feedback(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        r = await c.patch(_url(ex, rid, evid), json={"overall_feedback": "solid work"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["overall_feedback"] == "solid work"


async def test_first_feedback_write_moves_evaluation_to_in_progress(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        d = (await c.patch(_url(ex, rid, evid), json={"overall_feedback": "x"}, headers=h)).json()["data"]
        assert d["status"] == "in_progress"


async def test_first_feedback_write_moves_report_to_under_evaluation(migrated_db: async_sessionmaker) -> None:
    # L5 — the transition fires on evaluator *work*, never on assignment.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        assert await _report_status(migrated_db, rid) == "submitted"
        await c.patch(_url(ex, rid, evid), json={"overall_feedback": "x"}, headers=h)
        assert await _report_status(migrated_db, rid) == "under_evaluation"


async def test_second_feedback_write_does_not_re_emit_the_transition_audit_row(
    migrated_db: async_sessionmaker,
) -> None:
    # _begin_evaluation is idempotent: exactly one report.under_evaluation row, ever.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        await c.patch(_url(ex, rid, evid), json={"overall_feedback": "one"}, headers=h)
        await c.patch(_url(ex, rid, evid), json={"overall_feedback": "two"}, headers=h)
    async with migrated_db() as s:
        n = (
            await s.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "report.under_evaluation", AuditLog.resource_id == uuid.UUID(rid))
            )
        ).scalar_one()
        assert n == 1


async def test_feedback_write_on_already_under_evaluation_report_leaves_status_unchanged(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h1, evid1 = await _assigned(migrated_db, c, ah, jti="ev1")
        await c.patch(_url(ex, rid, evid1), json={"overall_feedback": "first"}, headers=h1)
        h2, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        await c.patch(_url(ex, rid, evid2), json={"overall_feedback": "second"}, headers=h2)
        assert await _report_status(migrated_db, rid) == "under_evaluation"


async def test_feedback_write_does_not_touch_grade_version(migrated_db: async_sessionmaker) -> None:
    # D3 sole-writer guard: only rollup.py (W5-2) increments grade_version.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        await c.patch(_url(ex, rid, evid), json={"overall_feedback": "x"}, headers=h)
    assert await _report_column(migrated_db, rid, "grade_version") == 0


async def test_feedback_write_does_not_set_report_overall_grade(migrated_db: async_sessionmaker) -> None:
    # A7 sole-writer guard. NOTE: this assertion FLIPS in W5-2 Task 8, which wires the rollup in.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        await c.patch(_url(ex, rid, evid), json={"overall_feedback": "x"}, headers=h)
    assert await _report_column(migrated_db, rid, "overall_grade") is None


async def test_evaluator_patching_a_peer_evaluation_returns_403(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h1, _ = await _assigned(migrated_db, c, ah, jti="ev1")
        _, uid2 = await evaluator(migrated_db, c, ah, ex, "ev2")
        evid2 = await assign(c, ah, ex, rid, uid2)
        r = await c.patch(_url(ex, rid, evid2), json={"overall_feedback": "peek"}, headers=h1)
        assert r.status_code == 403
        assert r.json()["error"]["message"] == "not_your_evaluation"


async def test_global_admin_patching_an_evaluation_feedback_succeeds(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, _, evid = await _assigned(migrated_db, c, ah)
        r = await c.patch(_url(ex, rid, evid), json={"overall_feedback": "admin note"}, headers=ah)
        assert r.status_code == 200, r.text


async def test_patch_explicit_null_feedback_returns_422(migrated_db: async_sessionmaker) -> None:
    # Repo convention (WP2 Phase D FIX PASS): explicit null on a PATCH field is 422, not "clear it".
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _, h, evid = await _assigned(migrated_db, c, ah)
        r = await c.patch(_url(ex, rid, evid), json={"overall_feedback": None}, headers=h)
        assert r.status_code == 422
