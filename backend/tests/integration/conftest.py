from collections.abc import Iterator

import pytest
from alembic.config import Config
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture()
def alembic_cfg() -> Config:
    return Config("alembic.ini")
