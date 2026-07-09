import pytest

from tests.auth.conftest import (  # noqa: F401  -- re-export fake-IdP fixtures for route tests
    fake_idp_transport,
    idp_jwks_resolver,
    idp_private_key,
    mint_id_token,
)
from tests.integration.conftest import (  # noqa: F401  -- re-export DB fixtures for route integration tests
    alembic_cfg,
    migrated_db,
    pg_url,
)

SECRET = "x" * 32


@pytest.fixture(autouse=True)
def _route_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the secrets create_app() needs (the root autouse fixture pops them per-test)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", SECRET)
