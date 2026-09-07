"""The finalize gate (G-6): when do an exercise's evaluations feed the report grade.

``scoring_config.finalize_policy`` is the single seam. Nothing else in the codebase should
spell the mode literals — import the constants from here.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScoringConfig
from app.services.scoring.aggregate import EvaluationFacts, contributes_grade, counts

#: Every assigned evaluator must finalize before their evaluation counts.
ALL_MUST_FINALIZE = "all_must_finalize"
#: Any evaluation with a grade counts, finalized or not.
ANY_CAN_FINALIZE = "any_can_finalize"


async def resolve_finalize_policy(db: AsyncSession, exercise_id: uuid.UUID) -> str:
    """The exercise's finalize mode.

    G-6: exercises predating WP5 have no ``scoring_config`` row, so the caller would otherwise
    get ``None`` where it needs a mode. The documented default stands in — never NULL.
    """
    mode = (
        await db.execute(select(ScoringConfig.finalize_policy).where(ScoringConfig.exercise_id == exercise_id))
    ).scalar_one_or_none()
    return mode or ALL_MUST_FINALIZE


def is_gate_open(evaluations: Sequence[EvaluationFacts], mode: str) -> bool:
    """Whether ``under_evaluation`` -> ``evaluated`` is permitted right now (§7.2).

    The empty counted set is CLOSED, not vacuously open: ``all()`` over nothing is True, and a
    report whose every evaluator was unassigned must not silently become ``evaluated`` with no
    grade behind it — that case wants a human, not a transition.

    Any mode other than ``any_can_finalize`` takes the strict branch, so a value that somehow
    escaped the column's CHECK constraint fails closed.
    """
    counted = [e for e in evaluations if counts(e)]
    if not counted:
        return False
    if mode == ANY_CAN_FINALIZE:
        return any(contributes_grade(e) for e in counted)
    return all(contributes_grade(e) for e in counted)
