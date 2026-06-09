from app.core.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/app",
        "JWT_SECRET": "x" * 32,
    }


def test_auth_settings_defaults() -> None:
    s = Settings(_env_file=None, **_base_env())
    assert s.jwt_access_ttl_minutes == 60
    assert s.jwt_exercise_max_session_hours == 24


def test_auth_settings_override() -> None:
    s = Settings(
        _env_file=None,
        JWT_ACCESS_TTL_MINUTES="15",
        JWT_EXERCISE_MAX_SESSION_HOURS="8",
        **_base_env(),
    )
    assert s.jwt_access_ttl_minutes == 15
    assert s.jwt_exercise_max_session_hours == 8
