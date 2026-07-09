from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.base import NormalizedClaims
from app.auth.session import RefreshDenied, refresh_session, start_session
from app.core.config import Settings
from app.core.security import verify_app_jwt

SECRET = "x" * 32


def _settings() -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql+asyncpg://u:p@db:5432/app", JWT_SECRET=SECRET)


async def _issue(s: AsyncSession, settings: Settings, *, auth_time: datetime):
    issued = await start_session(
        s,
        NormalizedClaims(subject="rf", email="rf@x", display_name="RF", provider="oidc"),
        settings,
        now=auth_time,
    )
    await s.flush()
    return issued


@pytest.mark.integration
async def test_refresh_within_window_reissues(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()
    async with migrated_db() as s:
        auth_time = datetime.now(UTC)
        issued = await _issue(s, settings, auth_time=auth_time)
        expires_before = issued.session.expires_at
        later = auth_time + timedelta(hours=1)
        new_token = await refresh_session(s, issued.session, settings, now=later)
        claims = verify_app_jwt(new_token, SECRET)
        assert claims.jti == issued.session.jti
        assert claims.auth_time == int(auth_time.timestamp())  # auth_time preserved
        assert issued.session.expires_at > expires_before  # refresh extended the expiry


@pytest.mark.integration
async def test_refresh_past_window_denied(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()  # default 24h window
    async with migrated_db() as s:
        auth_time = datetime.now(UTC)
        issued = await _issue(s, settings, auth_time=auth_time)
        too_late = auth_time + timedelta(hours=25)
        with pytest.raises(RefreshDenied):
            await refresh_session(s, issued.session, settings, now=too_late)


@pytest.mark.integration
async def test_refresh_revoked_denied(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    settings = _settings()
    async with migrated_db() as s:
        issued = await _issue(s, settings, auth_time=datetime.now(UTC))
        issued.session.revoked_at = datetime.now(UTC)
        await s.flush()
        with pytest.raises(RefreshDenied):
            await refresh_session(s, issued.session, settings)
