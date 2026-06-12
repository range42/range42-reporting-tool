"""Read-only permission catalogue for the frontend role editor. The catalogue is the
single source of truth in app/core/permissions.py; this endpoint just publishes it."""

from fastapi import APIRouter, Depends

from app.core.permissions import PERMISSION_CATALOGUE
from app.core.rbac import require_global_admin
from app.models.user import User
from app.schemas.common import DataEnvelope

router = APIRouter()


@router.get("/permissions")
async def list_permissions(
    _: User = Depends(require_global_admin),
) -> DataEnvelope[list[str]]:
    """The assignable permission keys, sorted (admin-only; drives the role editor)."""
    return DataEnvelope(data=sorted(PERMISSION_CATALOGUE))
