from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.base import NormalizedClaims
from app.auth.session import revoke_session, start_session
from app.core.config import Settings
from app.core.security import verify_app_jwt
from app.models.user_session import UserSession

SECRET = "x" * 32


def _settings() -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app", JWT_SECRET=SECRET)


@pytest.mark.integration
async def test_start_session_creates_row_and_token(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()
    async with migrated_db() as s:
        issued = await start_session(
            s, NormalizedClaims(subject="o1", email="o@x", display_name="O", provider="oidc"), settings
        )
        await s.commit()
        claims = verify_app_jwt(issued.token, SECRET)
        assert claims.jti == issued.session.jti
        assert claims.sub == str(issued.user.id)
        assert claims.is_global_admin is False
        row = (await s.execute(select(UserSession).where(UserSession.jti == issued.session.jti))).scalar_one()
        assert row.revoked_at is None


@pytest.mark.integration
async def test_start_session_force_global_admin(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()
    async with migrated_db() as s:
        issued = await start_session(
            s,
            NormalizedClaims(subject="admin", email="a@x", display_name="A", provider="emergency"),
            settings,
            force_global_admin=True,
        )
        assert issued.user.is_global_admin is True
        assert verify_app_jwt(issued.token, SECRET).is_global_admin is True


@pytest.mark.integration
async def test_revoke_session(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()
    async with migrated_db() as s:
        issued = await start_session(
            s, NormalizedClaims(subject="r1", email="r@x", display_name="R", provider="oidc"), settings
        )
        await s.flush()
        assert await revoke_session(s, issued.session.jti, now=datetime.now(UTC)) is True
        assert await revoke_session(s, issued.session.jti) is False  # already revoked
        assert await revoke_session(s, "ghost") is False  # unknown
