import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rbac import require_global_admin
from app.models import Exercise, User
from app.schemas.common import DataEnvelope
from app.schemas.evaluation import StalledReportsOut
from app.services.evaluation.stalled import stalled_reports

router = APIRouter(tags=["evaluations"])


@router.get("/exercises/{exercise_id}/stalled-reports")
async def list_stalled_reports(
    exercise_id: uuid.UUID,
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[StalledReportsOut]:
    """Reports under evaluation, most stalled first (Global Admin only). Read-only."""
    exists = (await db.execute(select(Exercise.id).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return DataEnvelope(data=await stalled_reports(db, exercise_id))
