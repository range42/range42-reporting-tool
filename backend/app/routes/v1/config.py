from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.common import DataEnvelope

router = APIRouter()


@router.get("/config")
async def config(s: Settings = Depends(get_settings)) -> DataEnvelope[dict[str, str]]:
    return DataEnvelope(
        data={
            "app_name": s.branding_app_name,
            "logo_url": s.branding_logo_url,
            "primary_color": s.branding_primary_color,
        }
    )
