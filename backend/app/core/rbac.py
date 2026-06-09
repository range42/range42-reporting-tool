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

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import OIDCProvider
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import InvalidToken, verify_app_jwt
from app.models.exercise_role import ExerciseRole
from app.models.role_definition import RoleDefinition
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


async def require_global_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency for global-scoped routes: 403 unless the caller is a global admin."""
    if not user.is_global_admin:
        raise HTTPException(status_code=403, detail="global admin required")
    return user


def require_permission(perm: str) -> Callable[..., Awaitable[None]]:
    """Build a dependency asserting the caller holds ``perm`` in the path's exercise.

    Global admins bypass. Otherwise resolves the caller's ``exercise_role`` rows for
    the path ``exercise_id``, ORs their ``role_definition`` permission sets, and 403s
    if ``perm`` is absent. Exercise-scoped only — global strings are guarded by
    ``require_global_admin`` (design §4.3).
    """

    async def _dependency(
        exercise_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if user.is_global_admin:
            return
        role_keys = (
            (
                await db.execute(
                    select(ExerciseRole.role_key).where(
                        ExerciseRole.exercise_id == exercise_id,
                        ExerciseRole.user_id == user.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not role_keys:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        granted = (
            (await db.execute(select(RoleDefinition.permissions).where(RoleDefinition.role_key.in_(role_keys))))
            .scalars()
            .all()
        )
        allowed: set[str] = set()
        for perms in granted:
            allowed.update(perms)
        if perm not in allowed:
            raise HTTPException(status_code=403, detail="insufficient permissions")

    return _dependency


def require_team_membership(tid: str) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that asserts the caller belongs to team ``tid``.

    Resolves JWT -> user -> team membership for ``tid`` and raises 403 otherwise.
    Lands in **Phase D** (needs the ``team_member`` table).
    """

    async def _dependency() -> None:
        raise NotImplementedError("require_team_membership lands in Phase D (needs team_member)")

    return _dependency


def get_oidc_provider(request: Request) -> OIDCProvider:
    """Return the configured OIDC provider or raise 503 if OIDC is not set up."""
    provider: OIDCProvider | None = getattr(request.app.state, "oidc_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="OIDC not configured")
    return provider
