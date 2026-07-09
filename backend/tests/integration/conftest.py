from collections.abc import AsyncIterator, Iterator

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture()
def alembic_cfg() -> Config:
    return Config("alembic.ini")


@pytest.fixture()
async def migrated_db(pg_url: str, alembic_cfg: Config) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A migrated DB (alembic head, incl. triggers) + a sessionmaker; torn down to base."""
    alembic_cfg.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(alembic_cfg, "head")
    engine = create_async_engine(pg_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sm
    finally:
        await engine.dispose()
        command.downgrade(alembic_cfg, "base")
