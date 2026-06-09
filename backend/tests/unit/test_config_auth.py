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


def test_oidc_and_emergency_settings_defaults() -> None:
    s = Settings(_env_file=None, **_base_env())
    assert s.oidc_client_id == ""
    assert s.oidc_scopes == "openid profile email"
    assert s.emergency_admin_enabled is False
    assert s.emergency_admin_password_hash == ""


def test_oidc_and_emergency_settings_override() -> None:
    s = Settings(
        _env_file=None,
        OIDC_CLIENT_ID="rt",
        OIDC_CLIENT_SECRET="shh",
        OIDC_REDIRECT_URI="https://app/api/v1/auth/callback",
        EMERGENCY_ADMIN_ENABLED="true",
        EMERGENCY_ADMIN_PASSWORD_HASH="$2b$12$abc",
        **_base_env(),
    )
    assert s.oidc_client_id == "rt"
    assert s.oidc_client_secret == "shh"
    assert s.oidc_redirect_uri.endswith("/auth/callback")
    assert s.emergency_admin_enabled is True
    assert s.emergency_admin_password_hash == "$2b$12$abc"


def test_session_https_only_default_and_override() -> None:
    assert Settings(_env_file=None, **_base_env()).session_https_only is False
    assert Settings(_env_file=None, SESSION_HTTPS_ONLY="true", **_base_env()).session_https_only is True
