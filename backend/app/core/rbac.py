"""Permission-based RBAC dependency factories (shape reservation — no impl yet).

These are the final FastAPI-dependency signatures for v1 authorization. They are
unimplemented (raise ``NotImplementedError``); the resolver lands in WP2.

Resolver chain (how a permission string is checked):

    JWT  ->  user  ->  exercise_role  ->  role_definition.permissions  ->  string

i.e. the request's app-JWT identifies the *user*; the user's *exercise_role* for
the target exercise points at a *role_definition*; that definition carries a set
of permission *strings*; ``require_permission`` asserts ``perm`` is in that set.

NOTE: the architecture doc §5.3 ``require_role(role_names)`` example is
**SUPERSEDED** by this permission-based model. Gating on hard-coded role *names*
breaks custom/operator-defined roles (a role the operator invents would never
match a name allowlist). Authorize on *permissions*, never on role names.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import InvalidToken, verify_app_jwt
from app.models.user import User
from app.models.user_session import UserSession


@dataclass
class AuthContext:
    """The validated caller: the user plus the active session row backing the JWT."""

    user: User
    session: UserSession


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Resolve + validate the caller from the app-JWT and the server-side session row.

    Bearer present -> JWT signature/expiry -> session row exists, not revoked, not
    expired -> user exists. 401 on any failure. Refreshes ``last_seen_at`` (persisted
    by ``get_db``'s unit-of-work on a clean response).
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = verify_app_jwt(auth.removeprefix("Bearer "), settings.jwt_secret)
    except InvalidToken:
        raise HTTPException(status_code=401, detail="invalid token") from None

    session_row = (await db.execute(select(UserSession).where(UserSession.jti == claims.jti))).scalar_one_or_none()
    now = datetime.now(UTC)
    if session_row is None or session_row.revoked_at is not None or session_row.expires_at <= now:
        raise HTTPException(status_code=401, detail="session invalid")

    user = (await db.execute(select(User).where(User.id == session_row.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")

    session_row.last_seen_at = now
    await db.flush()
    return AuthContext(user=user, session=session_row)


async def get_current_user(ctx: AuthContext = Depends(get_auth_context)) -> User:
    """Resolve the caller's ``User`` (delegates to ``get_auth_context``)."""
    return ctx.user


def require_permission(perm: str) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that asserts the caller holds ``perm``.

    Resolves JWT -> user -> exercise_role -> role_definition.permissions and
    raises 403 if ``perm`` is absent. Unimplemented until WP2.
    """

    async def _dependency() -> None:
        raise NotImplementedError("require_permission resolver lands in WP2")

    return _dependency


def require_team_membership(tid: str) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that asserts the caller belongs to team ``tid``.

    Resolves JWT -> user -> team membership for ``tid`` and raises 403 otherwise.
    Unimplemented until WP2.
    """

    async def _dependency() -> None:
        raise NotImplementedError("require_team_membership resolver lands in WP2")

    return _dependency
