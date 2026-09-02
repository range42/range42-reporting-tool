"""W5-3 Task 1 — migration 0012 (D2 unassign/override columns) + the W5-1 prerequisite guards.

The two guards are verification tests, not creation tests: G-6's ``scoring_config.finalize_policy``
and D3's ``report.grade_version`` come from W5-1's ``0011``. If either goes missing, W5-1 is what
needs fixing — 0012 must never add them (duplicate-migration failure, conflicting CHECK names).
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.integration


async def _columns(migrated_db: async_sessionmaker, table: str) -> dict[str, dict]:
    async with migrated_db() as s:
        conn = await s.connection()
        return await conn.run_sync(lambda c: {col["name"]: col for col in inspect(c).get_columns(table)})


async def test_scoring_config_finalize_policy_is_available_from_w5_1(migrated_db: async_sessionmaker) -> None:
    """G-6 guard: this slice's gate is unimplementable without W5-1's column (L2)."""
    cols = await _columns(migrated_db, "scoring_config")
    assert "finalize_policy" in cols
    assert cols["finalize_policy"]["nullable"] is False


async def test_report_grade_version_is_available_from_w5_1(migrated_db: async_sessionmaker) -> None:
    """D3 / L9 guard: the monotonic publish counter must already exist."""
    cols = await _columns(migrated_db, "report")
    assert "grade_version" in cols
    assert cols["grade_version"]["nullable"] is False


async def test_evaluation_has_unassign_and_override_columns(migrated_db: async_sessionmaker) -> None:
    """The six §4.2 D2 columns, with the right nullability. Only finalize_is_admin_override is
    NOT NULL (server default false); the rest are NULL until an override/unassign happens."""
    cols = await _columns(migrated_db, "evaluation")
    expected_nullable = {
        "finalized_by": True,
        "finalize_is_admin_override": False,
        "finalize_comment": True,
        "unassigned_at": True,
        "unassigned_by": True,
        "unassign_reason": True,
    }
    missing = set(expected_nullable) - set(cols)
    assert not missing, f"missing columns: {sorted(missing)}"
    assert {name: cols[name]["nullable"] for name in expected_nullable} == expected_nullable
    assert cols["finalize_is_admin_override"]["default"] == "false"


async def test_evaluation_override_fks_restrict_user_deletion(migrated_db: async_sessionmaker) -> None:
    """finalized_by / unassigned_by reference user.id ON DELETE RESTRICT — an admin who acted on
    an evaluation cannot be deleted out from under the audit trail."""
    async with migrated_db() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT kcu.column_name, rc.delete_rule, ccu.table_name AS ref_table "
                    "FROM information_schema.referential_constraints rc "
                    "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = rc.constraint_name "
                    "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = rc.constraint_name "
                    "WHERE kcu.table_name = 'evaluation' AND kcu.column_name IN ('finalized_by', 'unassigned_by')"
                )
            )
        ).all()
    assert {(r.column_name, r.delete_rule, r.ref_table) for r in rows} == {
        ("finalized_by", "RESTRICT", "user"),
        ("unassigned_by", "RESTRICT", "user"),
    }


async def test_evaluation_active_partial_index_exists(migrated_db: async_sessionmaker) -> None:
    """A non-partial index would pass a plain name check while degrading every gate query, so
    assert the WHERE predicate in indexdef, not just the name."""
    async with migrated_db() as s:
        indexdef = (
            await s.execute(
                text("SELECT indexdef FROM pg_indexes WHERE tablename = 'evaluation' AND indexname = :n"),
                {"n": "ix_evaluation_report_active"},
            )
        ).scalar_one_or_none()
    assert indexdef is not None, "ix_evaluation_report_active is missing"
    assert "(report_id)" in indexdef
    assert "WHERE (unassigned_at IS NULL)" in indexdef


async def test_evaluation_status_enum_is_unchanged(migrated_db: async_sessionmaker) -> None:
    """§9-A3: no 'unassigned' status. Unassignment is orthogonal to progress; an unassigned but
    completed evaluation keeps 'completed' for the audit trail."""
    async with migrated_db() as s:
        clause = (
            await s.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'evaluation'::regclass AND conname = 'ck_evaluation_status'"
                )
            )
        ).scalar_one()
    assert "unassigned" not in clause
    for status in ("assigned", "in_progress", "completed"):
        assert status in clause
