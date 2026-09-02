"""W5-3 Task 2 — ``finalize_policy`` resolution (G-6, missing-row default).

``scoring_config.finalize_policy`` decides whether every assigned evaluator must finalize
before a report's grade is aggregated. Exercises created before WP5 have no
``scoring_config`` row at all, so the resolver must answer with the documented default
rather than NULL — the aggregation branch reads a mode, never an absence.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.evaluation.finalize_gate import (
    ALL_MUST_FINALIZE,
    ANY_CAN_FINALIZE,
    resolve_finalize_policy,
)
from tests.routes._evaluations import ga_headers
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


async def _exercise(c, ah) -> str:
    return (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]


async def _sql(migrated_db, stmt, **params):
    async with migrated_db() as s:
        await s.execute(text(stmt), params)
        await s.commit()


async def _resolve(migrated_db, exercise_id: str) -> str:
    async with migrated_db() as s:
        return await resolve_finalize_policy(s, uuid.UUID(exercise_id))


async def test_finalize_policy_defaults_to_all_must_finalize_when_no_scoring_config_row_exists(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange: an exercise predating WP5 — no scoring_config row of its own.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)
    await _sql(migrated_db, "DELETE FROM scoring_config WHERE exercise_id = CAST(:e AS uuid)", e=ex)

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ALL_MUST_FINALIZE


async def test_finalize_policy_reads_any_can_finalize_from_scoring_config(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)
    await _sql(
        migrated_db,
        "UPDATE scoring_config SET finalize_policy = :m WHERE exercise_id = CAST(:e AS uuid)",
        m=ANY_CAN_FINALIZE,
        e=ex,
    )

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ANY_CAN_FINALIZE


async def test_finalize_policy_reads_the_seeded_default_row(migrated_db: async_sessionmaker) -> None:
    # Arrange: a freshly created exercise gets a seeded scoring_config row.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex = await _exercise(c, ah)

    # Act
    mode = await _resolve(migrated_db, ex)

    # Assert
    assert mode == ALL_MUST_FINALIZE
