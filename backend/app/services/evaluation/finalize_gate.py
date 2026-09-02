"""The finalize gate (G-6): when do an exercise's evaluations feed the report grade.

``scoring_config.finalize_policy`` is the single seam. Nothing else in the codebase should
spell the mode literals — import the constants from here.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScoringConfig

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
