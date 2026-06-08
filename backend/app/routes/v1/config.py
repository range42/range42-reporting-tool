from fastapi import APIRouter

from app.core.config import Settings
from app.schemas.common import DataEnvelope

router = APIRouter()


@router.get("/config")
async def config() -> DataEnvelope[dict[str, str]]:
    s = Settings()
    return DataEnvelope(
        data={
            "app_name": s.branding_app_name,
            "logo_url": s.branding_logo_url,
            "primary_color": s.branding_primary_color,
        }
    )
