import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.db import build_engine
from app.schemas.common import DataEnvelope
from app.storage.local import LocalStorage

router = APIRouter()


async def _db_ping(engine: AsyncEngine) -> bool:
    # Fail fast: a down/unreachable DB must report "fail" rather than hang.
    async with asyncio.timeout(2):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    return True


@router.get("/health")
async def health(request: Request, s: Settings = Depends(get_settings)) -> DataEnvelope[dict[str, object]]:
    storage_ok = await LocalStorage(s.storage_local_path).healthcheck()

    # Prefer the lifespan-managed engine; under unit tests (httpx ASGITransport
    # does not run the lifespan) fall back to a short-lived engine we dispose.
    engine: AsyncEngine | None = getattr(request.app.state, "db_engine", None)
    own_engine = engine is None
    if engine is None:
        engine = build_engine(s.database_url)
    try:
        db_ok = await _db_ping(engine)
    except Exception:
        db_ok = False
    finally:
        if own_engine:
            await engine.dispose()

    checks = {
        "storage": "ok" if storage_ok else "fail",
        "db": "ok" if db_ok else "fail",
        "oidc_provider": "disabled" if not s.oidc_issuer_url else "configured",
    }
    return DataEnvelope(data={"version": s.app_version, "checks": checks})
