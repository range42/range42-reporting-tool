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
    """FastAPI dependency: a per-request unit of work.

    Yields a session from the lifespan-managed sessionmaker; **commits on a clean
    response and rolls back on any exception**. This is the documented persistence
    policy for request-scoped writes — including the ``get_current_user``
    ``last_seen_at`` heartbeat (read-only routes still persist it on clean exit).
    Handlers may ``flush()`` to obtain server-generated values mid-request; the
    final commit/rollback is owned here, so handlers must not commit themselves.
    """
    sm: async_sessionmaker[AsyncSession] = request.app.state.db_sessionmaker
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
