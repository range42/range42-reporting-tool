import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/app",
        "JWT_SECRET": "x" * 32,
    }


def test_settings_load_with_required() -> None:
    s = Settings(_env_file=None, **_base_env())
    assert s.storage_backend == "local"
    assert s.tls_mode == "acme"
    assert s.run_migrations_on_start is False


def test_settings_missing_jwt_secret_fails() -> None:
    env = _base_env()
    del env["JWT_SECRET"]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **env)


def test_settings_weak_jwt_secret_fails() -> None:
    env = _base_env()
    env["JWT_SECRET"] = "short"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **env)
