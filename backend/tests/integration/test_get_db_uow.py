import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.user import User


def _app(sm: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.db_sessionmaker = sm

    @app.post("/make")
    async def make(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
        db.add(User(external_id="oidc:uow", email="uow@x.test", display_name="UoW"))
        await db.flush()
        return {"ok": "1"}

    @app.post("/boom")
    async def boom(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
        db.add(User(external_id="oidc:boom", email="boom@x.test", display_name="Boom"))
        await db.flush()
        raise HTTPException(status_code=400, detail="nope")

    return app


async def _count(sm: async_sessionmaker[AsyncSession], external_id: str) -> int:
    async with sm() as s:
        rows = (await s.execute(select(User).where(User.external_id == external_id))).scalars().all()
        return len(rows)


@pytest.mark.integration
async def test_clean_response_commits(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/make")
    assert r.status_code == 200
    assert await _count(migrated_db, "oidc:uow") == 1  # committed on clean exit


@pytest.mark.integration
async def test_exception_rolls_back(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    transport = ASGITransport(app=_app(migrated_db))
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/boom")
    assert r.status_code == 400
    assert await _count(migrated_db, "oidc:boom") == 0  # rolled back
