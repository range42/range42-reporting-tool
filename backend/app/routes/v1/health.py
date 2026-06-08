from fastapi import APIRouter

from app.core.config import Settings
from app.schemas.common import DataEnvelope
from app.storage.local import LocalStorage

router = APIRouter()


@router.get("/health")
async def health() -> DataEnvelope[dict[str, object]]:
    s = Settings()
    storage_ok = await LocalStorage(s.storage_local_path).healthcheck()
    checks = {
        "storage": "ok" if storage_ok else "fail",
        "oidc_provider": "disabled" if not s.oidc_issuer_url else "configured",
    }
    return DataEnvelope(data={"version": s.app_version, "checks": checks})
