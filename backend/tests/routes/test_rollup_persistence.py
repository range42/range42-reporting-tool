"""Task 7 — the sole-writer persistence path (M2, M9, M10, M14).

State is built through the real W5-1 API so these exercise the actual rows and transaction,
then ``recompute_report_grade`` is called directly — Task 8 is what wires it into the
grade-save handler, so nothing calls it implicitly yet.

Two sole-writer contracts must not collide: ``state_machine`` owns ``report.status``,
``rollup`` owns ``report.overall_grade`` / ``evaluation.overall_grade`` / ``grade_version``.

W5-3 L7: only a COMPLETED evaluation feeds ``report.overall_grade``, so grading alone no longer
publishes anything. These tests drive ``rollup`` directly rather than through a request, so they
complete their evaluations with :func:`mark_completed` — the route-level equivalent is the
finalize endpoint, covered in ``test_evaluations_finalize.py``.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog, Report
from app.services.scoring.rollup import recompute_report_grade, set_manual_grade
from tests.routes._evaluations import assign, evaluator, ga_headers, mark_completed
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

NUMERIC = {"grade_mode": "numeric", "grade_min": 0, "grade_max": 10}


async def _template_with_sections(c, ah, count: int, **section):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "sitrep"}, headers=ah)).json()["data"][
        "id"
    ]
    for i in range(count):
        r = await c.post(
            f"/api/v1/templates/{tid}/sections",
            json={"name": f"S{i}", "field_type": "rich_text", "is_required": False, **section},
            headers=ah,
        )
        assert r.status_code == 201, r.text
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    return tid


async def _world(migrated_db, c, ah, *, sections: int = 1, evaluators: int = 1, prefix: str = "ev"):
    """A submitted report with `sections` numeric sections and `evaluators` assigned graders."""
    tid = await _template_with_sections(c, ah, sections, **NUMERIC)
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
    rid = detail["id"]
    sids = [s["id"] for s in detail["sections"]]
    await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)
    graders = []
    for n in range(evaluators):
        h, uid = await evaluator(migrated_db, c, ah, ex, f"{prefix}{n}")
        graders.append((h, await assign(c, ah, ex, rid, uid)))
    return ex, rid, sids, graders


async def _grade(c, ex, rid, evid, sid, value, headers):
    r = await c.put(
        f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}",
        json={"grade": value},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def _complete(migrated_db, *evids):
    """Complete these evaluations so their grades count toward the report (L7)."""
    await mark_completed(migrated_db, *evids)


async def _recompute(migrated_db, rid, **kw):
    """Load the report in a fresh session, recompute, commit. Returns the GradeTimeline."""
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        timeline = await recompute_report_grade(s, report, **kw)
        await s.commit()
        return timeline


async def _report_row(migrated_db, rid, columns="overall_grade, grade_version"):
    async with migrated_db() as s:
        return (
            await s.execute(
                text(f"SELECT {columns} FROM report WHERE id = CAST(:i AS uuid)"),  # noqa: S608
                {"i": rid},
            )
        ).one()


# --- persistence --------------------------------------------------------------


async def test_recompute_persists_report_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah, sections=2)
        h, evid = graders[0]
        await _grade(c, ex, rid, evid, sids[0], "8", h)
        await _grade(c, ex, rid, evid, sids[1], "6", h)
    # The saves published nothing: the evaluation is still in progress (L7).
    assert await _report_row(migrated_db, rid) == (None, 0)
    await _complete(migrated_db, evid)
    await _recompute(migrated_db, rid)
    # (8 + 6) / 2 = 7, published once.
    assert await _report_row(migrated_db, rid) == (Decimal("7.00"), 1)
    await _recompute(migrated_db, rid)
    assert await _report_row(migrated_db, rid) == (Decimal("7.00"), 1)


async def test_recompute_persists_each_evaluation_overall_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah, evaluators=2)
        await _grade(c, ex, rid, graders[0][1], sids[0], "9", graders[0][0])
        await _grade(c, ex, rid, graders[1][1], sids[0], "5", graders[1][0])
    await _recompute(migrated_db, rid)
    async with migrated_db() as s:
        rows = (
            (
                await s.execute(
                    text(
                        "SELECT overall_grade FROM evaluation WHERE report_id = CAST(:i AS uuid) ORDER BY overall_grade"
                    ),
                    {"i": rid},
                )
            )
            .scalars()
            .all()
        )
    assert rows == [Decimal("5.00"), Decimal("9.00")]


async def test_recompute_sets_overall_grade_to_null_when_all_grades_are_removed(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _recompute(migrated_db, rid)
    async with migrated_db() as s:
        await s.execute(text("DELETE FROM section_grade"))
        await s.commit()
    await _recompute(migrated_db, rid)
    grade, _ = await _report_row(migrated_db, rid)
    assert grade is None  # NULL, never 0


async def test_recompute_on_report_with_no_evaluations_leaves_overall_grade_null(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        _, rid, _, _ = await _world(migrated_db, c, ah, evaluators=0)
    await _recompute(migrated_db, rid)
    grade, version = await _report_row(migrated_db, rid)
    assert grade is None
    assert version == 0  # nothing published, so nothing to version


# --- idempotence + D3 versioning ----------------------------------------------


async def test_recompute_is_idempotent_when_called_twice_with_no_change(migrated_db: async_sessionmaker) -> None:
    # Decimal("8.00") from the DB must compare equal to a freshly computed Decimal("8"),
    # or grade_version would climb on every save.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    await _recompute(migrated_db, rid)
    await _recompute(migrated_db, rid)
    grade, version = await _report_row(migrated_db, rid)
    assert grade == Decimal("8.00")
    assert version == 1


async def test_recompute_bumps_grade_version_only_when_the_grade_changes(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah, evaluators=2)
        (h1, evid1), (h2, evid2) = graders
        await _grade(c, ex, rid, evid1, sids[0], "8", h1)
        await _grade(c, ex, rid, evid2, sids[0], "9", h2)
        # Only the first evaluation counts yet, so the recompute publishes 8.00.
        await _complete(migrated_db, evid1)
        await _recompute(migrated_db, rid)
        assert await _report_row(migrated_db, rid) == (Decimal("8.00"), 1)
        # A recompute that changes nothing costs no version.
        await _recompute(migrated_db, rid)
        assert await _report_row(migrated_db, rid) == (Decimal("8.00"), 1)
    # The second evaluation joins the numerator: (8 + 9) / 2 = 8.50, one more version.
    await _complete(migrated_db, evid2)
    await _recompute(migrated_db, rid)
    grade, version = await _report_row(migrated_db, rid)
    assert grade == Decimal("8.50")
    assert version == 2


# --- audit (M14) ---------------------------------------------------------------


async def test_recompute_emits_report_grade_recomputed_audit_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    await _recompute(migrated_db, rid)
    async with migrated_db() as s:
        row = (await s.execute(select(AuditLog).where(AuditLog.action == "report.grade_recomputed"))).scalars().one()
    assert row.resource_type == "report"
    assert row.details["overall_grade"] == "8.00"
    assert row.details["previous"] is None
    assert row.details["grade_version"] == 1


async def test_recompute_emits_no_audit_row_when_the_grade_is_unchanged(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    await _recompute(migrated_db, rid)
    await _recompute(migrated_db, rid)
    async with migrated_db() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "report.grade_recomputed")
            )
        ).scalar_one()
    assert n == 1


# --- transaction + sole-writer discipline --------------------------------------


async def test_recompute_does_not_commit_the_session(migrated_db: async_sessionmaker) -> None:
    # get_db's unit of work owns the boundary, as with record_audit and state_machine.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    await _recompute(migrated_db, rid)
    # 8.00 / version 1 is now published. Change the underlying grade inside an uncommitted
    # session, recompute, then roll back: nothing may survive.
    assert await _report_row(migrated_db, rid) == (Decimal("8.00"), 1)
    async with migrated_db() as s:
        await s.execute(text("UPDATE section_grade SET grade = 2"))
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        await recompute_report_grade(s, report)
        await s.rollback()
    assert await _report_row(migrated_db, rid) == (Decimal("8.00"), 1)


async def test_recompute_never_writes_report_status(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    before = (await _report_row(migrated_db, rid, columns="status"))[0]
    await _recompute(migrated_db, rid)
    assert (await _report_row(migrated_db, rid, columns="status"))[0] == before


async def test_recompute_report_grade_issues_a_bounded_number_of_queries(migrated_db: async_sessionmaker) -> None:
    """No N+1: the query count must not grow with sections or evaluators."""

    async def _count_for(sections: int, evaluators: int) -> int:
        ah, _ = await ga_headers(migrated_db, jti=f"ga{sections}{evaluators}")
        async with client(migrated_db) as c:
            ex, rid, sids, graders = await _world(
                migrated_db, c, ah, sections=sections, evaluators=evaluators, prefix=f"q{sections}{evaluators}-"
            )
            for h, evid in graders:
                for sid in sids:
                    await _grade(c, ex, rid, evid, sid, "8", h)
        async with migrated_db() as s:
            report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
            statements: list[str] = []

            def _record(conn, cursor, statement, *a):  # noqa: ANN001
                statements.append(statement)

            bind = s.get_bind()
            engine = getattr(bind, "sync_engine", bind)
            event.listen(engine, "before_cursor_execute", _record)
            try:
                await recompute_report_grade(s, report)
                await s.flush()
            finally:
                event.remove(engine, "before_cursor_execute", _record)
            await s.rollback()
            return len(statements)

    small = await _count_for(sections=1, evaluators=1)
    large = await _count_for(sections=4, evaluators=3)
    assert large == small, f"query count grew from {small} to {large} — N+1"


# --- M9 manual override ---------------------------------------------------------


async def test_manual_override_suppresses_report_grade_recomputation(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        await set_manual_grade(s, report, Decimal("3.00"), actor_id=None, reason="moderated")
        await s.commit()
    await _recompute(migrated_db, rid)
    grade, _ = await _report_row(migrated_db, rid)
    assert grade == Decimal("3.00")  # the computed 8.00 must not overwrite it


async def test_manual_override_still_recomputes_per_evaluator_grades(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        await set_manual_grade(s, report, Decimal("3.00"), actor_id=None, reason="moderated")
        await s.commit()
    await _recompute(migrated_db, rid)
    async with migrated_db() as s:
        ev_grade = (
            await s.execute(text("SELECT overall_grade FROM evaluation WHERE report_id = CAST(:i AS uuid)"), {"i": rid})
        ).scalar_one()
    assert ev_grade == Decimal("8.00")


async def test_clearing_a_manual_override_restores_the_computed_grade(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        await set_manual_grade(s, report, Decimal("3.00"), actor_id=None, reason="moderated")
        await s.commit()
    async with migrated_db() as s:
        report = (await s.execute(select(Report).where(Report.id == uuid.UUID(rid)))).scalar_one()
        await set_manual_grade(s, report, None, actor_id=None, reason="reverted")
        await s.commit()
    grade, _ = await _report_row(migrated_db, rid)
    assert grade == Decimal("8.00")


# --- timeline -------------------------------------------------------------------


async def test_recompute_returns_the_timeline_entry_for_the_report(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sids, graders = await _world(migrated_db, c, ah)
        await _grade(c, ex, rid, graders[0][1], sids[0], "8", graders[0][0])
    await _complete(migrated_db, graders[0][1])
    timeline = await _recompute(migrated_db, rid)
    assert timeline.report_id == rid
    assert timeline.overall_grade == Decimal("8.00")
    assert timeline.grade_version == 1
    assert timeline.entry is not None
    assert timeline.entry.report_type == "sitrep"
    assert timeline.entry.section_grades[0].grade == Decimal("8.00")
