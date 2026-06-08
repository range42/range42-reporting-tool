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
