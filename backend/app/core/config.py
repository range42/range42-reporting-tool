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
    run_migrations_on_start: bool = Field(False, alias="RUN_MIGRATIONS_ON_START")
    cors_origins: str = Field("", alias="CORS_ORIGINS")
    app_version: str = Field("0.1.0", alias="APP_VERSION")
    oidc_issuer_url: str = Field("", alias="OIDC_ISSUER_URL")
    branding_app_name: str = Field("Reporting Tool", alias="BRANDING_APP_NAME")
    branding_logo_url: str = Field("", alias="BRANDING_LOGO_URL")
    branding_primary_color: str = Field("#2563eb", alias="BRANDING_PRIMARY_COLOR")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
