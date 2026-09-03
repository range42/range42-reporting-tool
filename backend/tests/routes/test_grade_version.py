"""Task 9 — D3: ``report.grade_version`` monotonicity (M10).

WHAT THE COUNTER IS FOR. Anything that publishes a grade outward — a ``report.evaluated``
webhook (§11.3), an export, a leaderboard row — carries the version it was computed at. A
consumer compares the version it holds against the current one to tell whether its number has
been superseded. That only works if the counter rises on every published change and never,
ever goes backwards, which is what this module pins.

Tests only: a failure here is a bug in the rollup, never a reason to soften an assertion.

W5-3 MOVED WHEN THE COUNTER TICKS. Under W5-2 every changed grade save published immediately,
so the ladder was driven by re-saving one grade. L7 now excludes an in-progress evaluation from
the report aggregate, so publication happens on FINALIZE. The ladder below is therefore driven
by successive evaluators finalizing under ``all_must_finalize``: each one joins the numerator
and changes the published number, and only the last closes the gate.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Report
from app.services.scoring import rollup
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers
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


async def _arrange_many(migrated_db, c, ah, count):
    """Same world, `count` assigned evaluators. Returns (ex, rid, sid, [(headers, evid), ...])."""
    ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah, jti="ev0")
    graders = [(h, evid)]
    for i in range(1, count):
        hi, uid = await evaluator(migrated_db, c, ah, ex, f"ev{i}")
        graders.append((hi, await assign(c, ah, ex, rid, uid)))
    return ex, rid, sid, graders


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


async def _reopen(migrated_db, rid, evid):
    """W5-4's reopen, by hand: the report is gradeable again and the evaluation is not done."""
    await _exec(migrated_db, "UPDATE report SET status = 'under_evaluation' WHERE id = CAST(:i AS uuid)", i=rid)
    await _exec(
        migrated_db,
        "UPDATE evaluation SET status = 'in_progress', completed_at = NULL WHERE id = CAST(:i AS uuid)",
        i=evid,
    )


# --- the basic ladder ----------------------------------------------------------


async def test_grade_version_starts_at_zero_on_a_new_report(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        _, rid, _, _, _ = await _arrange(migrated_db, c, ah)
    assert await _version(migrated_db, rid) == 0


async def test_grade_version_increments_by_one_on_the_first_published_grade(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        assert await _version(migrated_db, rid) == 0, "an in-progress grade publishes nothing"
        await finalize(c, h, ex, rid, evid)
    assert await _version(migrated_db, rid) == 1


async def test_grade_version_increments_on_each_published_change(migrated_db: async_sessionmaker) -> None:
    """Three evaluators, three finalizes, three different aggregates: 8.00, 7.00, 6.00."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _arrange_many(migrated_db, c, ah, 3)
        for (h, evid), value in zip(graders, ("8", "6", "4"), strict=True):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
        seen = []
        for h, evid in graders:
            await finalize(c, h, ex, rid, evid)
            seen.append(await _version(migrated_db, rid))
    assert seen == [1, 2, 3]


async def test_grade_version_not_incremented_when_recomputed_grade_is_unchanged(
    migrated_db: async_sessionmaker,
) -> None:
    # A second evaluator agreeing exactly does not change the published mean, so consumers
    # must not see a new version. "8" and "8.00" are the same grade; only a string comparison
    # would disagree, and that would bump on every finalize.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _arrange_many(migrated_db, c, ah, 3)
        for (h, evid), value in zip(graders, ("8", "8", "8.00"), strict=True):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
        for h, evid in graders:
            await finalize(c, h, ex, rid, evid)
    assert await _version(migrated_db, rid) == 1


# --- transitions through NULL ---------------------------------------------------


async def test_grade_version_increments_when_grade_transitions_from_null(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        assert await _version(migrated_db, rid) == 0
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await finalize(c, h, ex, rid, evid)
    assert await _version(migrated_db, rid) == 1


async def test_grade_version_increments_when_grade_transitions_to_null(migrated_db: async_sessionmaker) -> None:
    # Losing the last contributor is itself a published change: consumers holding 8.00 must be
    # able to tell it no longer stands. Retracting the grade is impossible once finalized (409),
    # so the route in is unassignment — W5-3 Task 9's endpoint, driven here by hand.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await finalize(c, h, ex, rid, evid)
        assert await _version(migrated_db, rid) == 1
    await _exec(migrated_db, "UPDATE evaluation SET unassigned_at = now() WHERE id = CAST(:i AS uuid)", i=evid)
    async with migrated_db() as s:
        report = await _load_report(s, rid)
        await rollup.recompute_report_grade(s, report, trigger="evaluation.unassigned")
        await s.commit()
    async with migrated_db() as s:
        grade = (
            await s.execute(text("SELECT overall_grade FROM report WHERE id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert grade is None
    assert await _version(migrated_db, rid) == 2


# --- manual override (M9) --------------------------------------------------------


async def test_grade_version_increments_when_a_manual_grade_is_set(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await finalize(c, h, ex, rid, evid)
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
        ex, rid, sid, graders = await _arrange_many(migrated_db, c, ah, 3)
        for (h, evid), value in zip(graders, ("8", "1", "9"), strict=True):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
        first_h, first_evid = graders[0]
        await finalize(c, first_h, ex, rid, first_evid)
        async with migrated_db() as s:
            report = await _load_report(s, rid)
            await rollup.set_manual_grade(s, report, Decimal("3"), actor_id=None, reason="moderated")
            await s.commit()
        pinned = await _version(migrated_db, rid)
        # The remaining evaluators finalize, moving the computed mean underneath the override.
        for h, evid in graders[1:]:
            await finalize(c, h, ex, rid, evid)
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
        await finalize(c, h, ex, rid, evid)
        seen = [await _version(migrated_db, rid)]
        for value in ("4", "6"):
            # W5-4 has no reopen route yet; drive both rows back to a gradeable state.
            await _reopen(migrated_db, rid, evid)
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
            await finalize(c, h, ex, rid, evid)
            seen.append(await _version(migrated_db, rid))
    assert seen == sorted(seen), seen
    assert len(set(seen)) == len(seen), f"a version was reused: {seen}"


async def test_grade_version_is_visible_on_the_evaluation_detail_response(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, h, evid = await _arrange(migrated_db, c, ah)
        await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        await finalize(c, h, ex, rid, evid)
        d = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}", headers=h)).json()["data"]
    assert d["grade_version"] == 1


async def test_grade_version_bump_shares_the_grade_write_transaction(
    migrated_db: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _arrange_many(migrated_db, c, ah, 2)
        for h, evid in graders:
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": "8"}, headers=h)
        first_h, first_evid = graders[0]
        await finalize(c, first_h, ex, rid, first_evid)
        before = await _version(migrated_db, rid)

        def _boom(*a, **kw):
            raise RuntimeError("rollup exploded")

        monkeypatch.setattr(rollup, "aggregate_overall_grade", _boom)
        second_h, second_evid = graders[1]
        with pytest.raises(RuntimeError):
            await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{second_evid}/finalize", headers=second_h)
    assert await _version(migrated_db, rid) == before


async def test_grade_version_recorded_in_the_grade_recomputed_audit_details(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid, graders = await _arrange_many(migrated_db, c, ah, 2)
        for (h, evid), value in zip(graders, ("8", "6"), strict=True):
            await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=h)
        for h, evid in graders:
            await finalize(c, h, ex, rid, evid)
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
