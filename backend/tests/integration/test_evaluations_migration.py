import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _check_constraint_count(s: AsyncSession, name: str) -> int:
    return (
        await s.execute(
            text("select count(*) from information_schema.check_constraints where constraint_name = :n"),
            {"n": name},
        )
    ).scalar_one()


async def _seed_report(s: AsyncSession, *, status: str = "submitted") -> dict[str, str]:
    """Minimal user → exercise → team → template → report chain."""
    uid = (
        await s.execute(
            text(
                'INSERT INTO "user" (id, external_id, email, display_name) '
                "VALUES (gen_random_uuid(), 'oidc:ev', 'ev@x', 'Ev') RETURNING id"
            )
        )
    ).scalar_one()
    xid = (
        await s.execute(
            text(
                "INSERT INTO exercise (id, name, status, created_by) "
                "VALUES (gen_random_uuid(), 'X', 'active', :u) RETURNING id"
            ),
            {"u": uid},
        )
    ).scalar_one()
    tid = (
        await s.execute(
            text(
                "INSERT INTO team (id, exercise_id, name, team_type) "
                "VALUES (gen_random_uuid(), :x, 'T', 'blue') RETURNING id"
            ),
            {"x": xid},
        )
    ).scalar_one()
    tpl = (
        await s.execute(
            text(
                "INSERT INTO report_template (id, lineage_id, version, name, report_type, status, created_by) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 1, 'Tpl', 'sitrep', 'published', :u) RETURNING id"
            ),
            {"u": uid},
        )
    ).scalar_one()
    rid = (
        await s.execute(
            text(
                "INSERT INTO report (id, exercise_id, team_id, template_id, template_version_at_creation, "
                "name, status, created_by) "
                "VALUES (gen_random_uuid(), :x, :t, :p, 1, 'R', :s, :u) RETURNING id"
            ),
            {"x": xid, "t": tid, "p": tpl, "s": status, "u": uid},
        )
    ).scalar_one()
    return {"user": uid, "exercise": xid, "team": tid, "template": tpl, "report": rid}


async def _seed_evaluation(s: AsyncSession, ids: dict[str, str]) -> str:
    return (
        await s.execute(
            text(
                "INSERT INTO evaluation (id, report_id, evaluator_id, assigned_by) "
                "VALUES (gen_random_uuid(), :r, :u, :u) RETURNING id"
            ),
            {"r": ids["report"], "u": ids["user"]},
        )
    ).scalar_one()


async def test_evaluation_tables_exist(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert {"evaluation", "section_grade"} <= tables


async def test_evaluation_report_evaluator_pair_is_unique(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        await _seed_evaluation(s, ids)
        await s.commit()
    async with migrated_db() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO evaluation (id, report_id, evaluator_id, assigned_by) "
                    "VALUES (gen_random_uuid(), (SELECT id FROM report LIMIT 1), "
                    '(SELECT id FROM "user" LIMIT 1), (SELECT id FROM "user" LIMIT 1))'
                )
            )
            await s.commit()


async def test_section_grade_shape_check_constraint_exists(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        assert await _check_constraint_count(s, "ck_section_grade_shape") == 1


async def test_section_grade_eval_section_pair_is_unique(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        evid = await _seed_evaluation(s, ids)
        sdef = (
            await s.execute(
                text(
                    "INSERT INTO template_section_def (id, template_id, position, name, field_type) "
                    "VALUES (gen_random_uuid(), :p, 1, 'S', 'text') RETURNING id"
                ),
                {"p": ids["template"]},
            )
        ).scalar_one()
        rsid = (
            await s.execute(
                text(
                    "INSERT INTO report_section (id, report_id, section_def_id, position) "
                    "VALUES (gen_random_uuid(), :r, :d, 1) RETURNING id"
                ),
                {"r": ids["report"], "d": sdef},
            )
        ).scalar_one()
        params = {"e": evid, "s": rsid, "u": ids["user"]}
        stmt = text(
            "INSERT INTO section_grade (id, evaluation_id, report_section_id, grade, graded_by) "
            "VALUES (gen_random_uuid(), :e, :s, 5, :u)"
        )
        await s.execute(stmt, params)
        await s.commit()
        with pytest.raises(IntegrityError):
            await s.execute(stmt, params)
            await s.commit()


async def test_report_gains_grade_rollup_columns(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        conn = await s.connection()
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("report")})
        assert {"overall_feedback", "overall_grade", "overall_grade_is_manual", "grade_version"} <= cols
        assert await _check_constraint_count(s, "ck_report_grade_version") == 1


async def test_report_grade_version_defaults_to_zero_on_insert(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        row = (
            await s.execute(
                text("SELECT grade_version, overall_grade, overall_grade_is_manual FROM report WHERE id = :r"),
                {"r": ids["report"]},
            )
        ).one()
        assert row.grade_version == 0
        assert row.overall_grade is None
        assert row.overall_grade_is_manual is False


async def test_report_status_check_accepts_under_evaluation(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    # Rolled back, never committed: downgrade() restores the 3-value ck_report_status and would
    # fail on a surviving under_evaluation row (documented limitation in 0011's downgrade note).
    async with migrated_db() as s:
        ids = await _seed_report(s, status="under_evaluation")
        assert ids["report"] is not None
        await s.rollback()


async def test_report_status_check_accepts_evaluated(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s, status="evaluated")
        assert ids["report"] is not None
        await s.rollback()


async def test_report_status_check_still_rejects_unknown_status(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    async with migrated_db() as s:
        with pytest.raises(IntegrityError):
            await _seed_report(s, status="archived")
            await s.commit()


async def test_scoring_config_finalize_policy_defaults_to_all_must_finalize(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        policy = (
            await s.execute(
                text(
                    "INSERT INTO scoring_config (id, exercise_id) VALUES (gen_random_uuid(), :x) "
                    "RETURNING finalize_policy"
                ),
                {"x": ids["exercise"]},
            )
        ).scalar_one()
        assert policy == "all_must_finalize"
        assert await _check_constraint_count(s, "ck_scoring_config_finalize_policy") == 1


async def test_scoring_config_finalize_policy_rejects_unknown_value(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO scoring_config (id, exercise_id, finalize_policy) VALUES (gen_random_uuid(), :x, :p)"
                ),
                {"x": ids["exercise"], "p": "majority_wins"},
            )
            await s.commit()


async def test_evaluation_aggregated_weight_check_rejects_zero(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO evaluation (id, report_id, evaluator_id, assigned_by, aggregated_weight) "
                    "VALUES (gen_random_uuid(), :r, :u, :u, 0)"
                ),
                {"r": ids["report"], "u": ids["user"]},
            )
            await s.commit()


async def test_evaluation_status_check_rejects_unknown_value(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ids = await _seed_report(s)
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO evaluation (id, report_id, evaluator_id, assigned_by, status) "
                    "VALUES (gen_random_uuid(), :r, :u, :u, 'finalized')"
                ),
                {"r": ids["report"], "u": ids["user"]},
            )
            await s.commit()
