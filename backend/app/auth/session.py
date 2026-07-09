"""Session lifecycle: mint app-JWT + server-side ``user_session`` row (design L1).

Every login path (OIDC, emergency, later SAML) funnels through ``start_session``;
``revoke_session`` powers logout; ``refresh_session`` (B11) re-issues within the
max-session window. Audit emission for ``user.login`` lands in Phase E.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import NormalizedClaims
from app.auth.users import upsert_user
from app.core.config import Settings
from app.core.security import mint_app_jwt
from app.models.user import User
from app.models.user_session import UserSession


@dataclass(frozen=True)
class IssuedSession:
    """The product of a login: the bearer token plus the rows it is bound to."""

    token: str
    user: User
    session: UserSession


async def start_session(
    db: AsyncSession,
    claims: NormalizedClaims,
    settings: Settings,
    *,
    force_global_admin: bool = False,
    now: datetime | None = None,
) -> IssuedSession:
    """Upsert the user, create a session row, and mint a bound app-JWT.

    ``force_global_admin`` is set only by the emergency-admin path. The caller owns
    the transaction commit (``get_db`` does it on a clean response).
    """
    stamp = now or datetime.now(UTC)
    user = await upsert_user(db, claims, now=stamp)
    if force_global_admin and not user.is_global_admin:
        user.is_global_admin = True
        await db.flush()

    jti = secrets.token_urlsafe(32)
    expires_at = stamp + timedelta(minutes=settings.jwt_access_ttl_minutes)
    session = UserSession(jti=jti, user_id=user.id, auth_time=stamp, expires_at=expires_at, last_seen_at=stamp)
    db.add(session)
    await db.flush()

    token = mint_app_jwt(
        user_id=str(user.id),
        is_global_admin=user.is_global_admin,
        jti=jti,
        auth_time=stamp,
        secret=settings.jwt_secret,
        ttl_minutes=settings.jwt_access_ttl_minutes,
        now=stamp,
    )
    return IssuedSession(token=token, user=user, session=session)


async def revoke_session(db: AsyncSession, jti: str, *, now: datetime | None = None) -> bool:
    """Mark a session revoked (idempotent). Returns ``False`` if unknown/already revoked."""
    stamp = now or datetime.now(UTC)
    row = (await db.execute(select(UserSession).where(UserSession.jti == jti))).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = stamp
    await db.flush()
    return True


class RefreshDenied(Exception):
    """Raised when a session may not be refreshed (revoked/expired/window exceeded)."""


async def any_exercise_active(db: AsyncSession) -> bool:
    """Whether some exercise is currently ``active`` (ARCH §5.1.1 refresh gate).

    Phase D backport: query ``exercise.status == 'active'`` once the table exists.
    Until then there is no exercise table, so this returns ``True`` and refresh is
    governed purely by the auth-time max-session window (issue #1 acceptance).
    """
    return True


async def refresh_session(
    db: AsyncSession,
    session: UserSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str:
    """Re-issue an app-JWT for an active session within the max-session window.

    Keeps the same ``jti`` and original ``auth_time``; extends ``expires_at``.

    The ``expires_at <= stamp`` guard is intentionally absent: refresh exists
    precisely to renew a token whose per-token TTL has lapsed or is about to.
    Time-based denial is instead governed exclusively by the max-session window
    (``jwt_exercise_max_session_hours``), which bounds the total lifetime of an
    authentication event regardless of how many times the token is refreshed.

    Raises ``RefreshDenied`` if the session is revoked, the max-session window is
    exceeded, or no exercise is active.
    """
    stamp = now or datetime.now(UTC)
    if session.revoked_at is not None:
        raise RefreshDenied("session revoked")
    window = timedelta(hours=settings.jwt_exercise_max_session_hours)
    if stamp - session.auth_time >= window:
        raise RefreshDenied("max session window exceeded")
    if not await any_exercise_active(db):
        raise RefreshDenied("no active exercise")

    user = (await db.execute(select(User).where(User.id == session.user_id))).scalar_one()
    session.expires_at = stamp + timedelta(minutes=settings.jwt_access_ttl_minutes)
    session.last_seen_at = stamp
    await db.flush()
    return mint_app_jwt(
        user_id=str(user.id),
        is_global_admin=user.is_global_admin,
        jti=session.jti,
        auth_time=session.auth_time,
        secret=settings.jwt_secret,
        ttl_minutes=settings.jwt_access_ttl_minutes,
        now=stamp,
    )
