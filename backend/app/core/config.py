from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret: str = Field(alias="JWT_SECRET")

    storage_backend: Literal["local", "s3"] = Field("local", alias="STORAGE_BACKEND")
    storage_local_path: str = Field("/data/attachments", alias="STORAGE_LOCAL_PATH")
    tls_mode: Literal["acme", "internal", "custom"] = Field("acme", alias="TLS_MODE")
    # Reserved: the one-shot `migrate` compose service is the canonical
    # migration path. This flag is honored by the app lifespan only if you
    # choose to wire alembic there (not wired today).
    run_migrations_on_start: bool = Field(False, alias="RUN_MIGRATIONS_ON_START")
    cors_origins: str = Field("", alias="CORS_ORIGINS")
    app_version: str = Field("0.1.0", alias="APP_VERSION")
    oidc_issuer_url: str = Field("", alias="OIDC_ISSUER_URL")
    oidc_client_id: str = Field("", alias="OIDC_CLIENT_ID")
    oidc_client_secret: str = Field("", alias="OIDC_CLIENT_SECRET")
    oidc_scopes: str = Field("openid profile email", alias="OIDC_SCOPES")
    oidc_redirect_uri: str = Field("", alias="OIDC_REDIRECT_URI")
    emergency_admin_enabled: bool = Field(False, alias="EMERGENCY_ADMIN_ENABLED")
    emergency_admin_password_hash: str = Field("", alias="EMERGENCY_ADMIN_PASSWORD_HASH")
    jwt_access_ttl_minutes: int = Field(60, alias="JWT_ACCESS_TTL_MINUTES")
    jwt_exercise_max_session_hours: int = Field(24, alias="JWT_EXERCISE_MAX_SESSION_HOURS")
    branding_app_name: str = Field("Reporting Tool", alias="BRANDING_APP_NAME")
    branding_logo_url: str = Field("", alias="BRANDING_LOGO_URL")
    branding_primary_color: str = Field("#2563eb", alias="BRANDING_PRIMARY_COLOR")
    session_https_only: bool = Field(False, alias="SESSION_HTTPS_ONLY")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached Settings. FastAPI dependency; tests call ``cache_clear()``."""
    return Settings()
