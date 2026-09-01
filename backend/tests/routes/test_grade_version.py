"""Task 9 — D3: ``report.grade_version`` monotonicity (M10).

WHAT THE COUNTER IS FOR. Anything that publishes a grade outward — a ``report.evaluated``
webhook (§11.3), an export, a leaderboard row — carries the version it was computed at. A
consumer compares the version it holds against the current one to tell whether its number has
been superseded. That only works if the counter rises on every published change and never,
ever goes backwards, which is what this module pins.

Tests only: a failure here is a bug in Task 7's rollup, never a reason to soften an assertion.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Report
from app.services.scoring import rollup
from tests.routes._evaluations import assign, evaluator, ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

NUMERIC = {"grade_mode": "numeric", "grade_min": 0, "grade_max": 10}


async def _arrange(migrated_db, c, ah, *, jti="ev1"):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "sitrep"}, headers=ah)).json()["data"][
        "id"
    ]
    r = await c.post(
        f"/api/v1/templates/{tid}/sections",
        json={"name": "S", "field_type": "rich_text", "is_required": False, **NUMERIC},
        headers=ah,
    )
    assert r.status_code == 201, r.text
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports",
            json={"template_id": tid, "team_id": team, "name": "R"},
            headers=ah,
        )
    ).json()["data"]
    rid, sid = detail["id"], detail["sections"][0]["id"]
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    h, uid = await evaluator(migrated_db, c, ah, ex, jti)
    return ex, rid, sid, h, await assign(c, ah, ex, rid, uid)


def _grade_url(ex, rid, evid, sid):
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}"


async def _load_report(session, rid) -> Report:
    return (await session.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()


async def _version(migrated_db, rid) -> int:
    async with migrated_db() as s:
        return (
            await s.execute(text("SELECT grade_version FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()


async def _exec(migrated_db, sql, **params):
    async with migrated_db() as s:
        await s.execute(text(sql), params)
        await s.commit()


# --- the basic ladder ----------------------------------------------------------


async def test_grade_version_starts_at_zero_on_a_new_report(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        _, rid, _, _, _ = await _arrange(migrated_db, c, ah)
    assert await _version(migrated_db, rid) == 0


async def test_grade_version_increments_by_one_on_the_first_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
    assert await _version(migrated_db, rid) == 1


async def test_grade_version_increments_on_each_grade_change(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        for value in ("8", "7", "6"):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
    assert await _version(migrated_db, rid) == 3


async def test_grade_version_not_incremented_when_recomputed_grade_is_unchanged(
    migrated_db: async_sessionmaker,
) -> None:
    # Re-saving the same value publishes nothing, so consumers must not see a new version.
    # "8" and "8.00" are the same grade; only a string comparison would disagree.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8.00"}, headers=h)
    assert await _version(migrated_db, rid) == 1


# --- transitions through NULL ---------------------------------------------------


async def test_grade_version_increments_when_grade_transitions_from_null(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        assert await _version(migrated_db, rid) == 0
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
    assert await _version(migrated_db, rid) == 1


async def test_grade_version_increments_when_grade_transitions_to_null(migrated_db: async_sessionmaker) -> None:
    # Retracting the last grade is itself a published change: consumers holding 8.00 must be
    # able to tell it no longer stands.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await c.delete(_grade_url(ex, rid, evid, sid), headers=h)
    assert await _version(migrated_db, rid) == 2


# --- manual override (M9) --------------------------------------------------------


async def test_grade_version_increments_when_a_manual_grade_is_set(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
    async with migrated_db() as s:
        report = await _load_report(s, rid)
        await rollup.set_manual_grade(s, report, Decimal("3"), actor_id=None, reason="moderated")
        await s.commit()
    assert await _version(migrated_db, rid) == 2


async def test_grade_version_not_incremented_while_overall_grade_is_manual(migrated_db: async_sessionmaker) -> None:
    # M9 — the computed number is suppressed, so nothing new is published and the counter
    # must hold still no matter how much the evaluators change underneath.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        async with migrated_db() as s:
            report = await _load_report(s, rid)
            await rollup.set_manual_grade(s, report, Decimal("3"), actor_id=None, reason="moderated")
            await s.commit()
        pinned = await _version(migrated_db, rid)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "1"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "9"}, headers=h)
    assert await _version(migrated_db, rid) == pinned


# --- the point of the whole thing -------------------------------------------------


async def test_grade_version_never_decreases_across_a_reopen_cycle(migrated_db: async_sessionmaker) -> None:
    """Simulates W5-4's reopen: a regraded report must never reuse an old version number.

    Without this, a consumer holding version 2 could receive a corrected grade also stamped 2
    and silently keep the stale one.
    """
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        seen = [await _version(migrated_db, rid)]
        # W5-4 has no reopen route yet; drive the state directly.
        await _exec(migrated_db, "UPDATE report SET status = 'evaluated' WHERE id = CAST(:i AS uuid)", i=rid)
        await _exec(migrated_db, "UPDATE report SET status = 'under_evaluation' WHERE id = CAST(:i AS uuid)", i=rid)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "4"}, headers=h)
        seen.append(await _version(migrated_db, rid))
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "6"}, headers=h)
        seen.append(await _version(migrated_db, rid))
    assert seen == sorted(seen), seen
    assert len(set(seen)) == len(seen), f"a version was reused: {seen}"


async def test_grade_version_is_visible_on_the_evaluation_detail_response(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        d = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=h)).json()["data"]
    assert d["grade_version"] == 1


async def test_grade_version_bump_shares_the_grade_write_transaction(
    migrated_db: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        before = await _version(migrated_db, rid)

        def _boom(*a, **kw):
            raise RuntimeError("rollup exploded")

        monkeypatch.setattr(rollup, "compute_report_grade", _boom)
        with pytest.raises(RuntimeError):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "2"}, headers=h)
    assert await _version(migrated_db, rid) == before


async def test_grade_version_recorded_in_the_grade_recomputed_audit_details(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "6"}, headers=h)
    async with migrated_db() as s:
        versions = (
            (
                await s.execute(
                    text(
                        "SELECT details->>'grade_version' FROM audit_log "
                        "WHERE action = 'report.grade_recomputed' ORDER BY created_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert versions == ["1", "2"]
