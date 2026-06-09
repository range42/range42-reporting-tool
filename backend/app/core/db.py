from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_dependency(
    sm: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sm() as session:
        yield session


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session from the lifespan-managed sessionmaker."""
    sm: async_sessionmaker[AsyncSession] = request.app.state.db_sessionmaker
    async with sm() as session:
        yield session
