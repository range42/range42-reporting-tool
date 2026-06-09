import inspect

import pytest

from app.core.rbac import require_permission, require_team_membership


def test_require_permission_constructs() -> None:
    dep = require_permission("report.read")
    assert callable(dep)


def test_require_team_membership_constructs() -> None:
    dep = require_team_membership("team-1")
    assert callable(dep)


def test_require_permission_inner_is_coroutine() -> None:
    """The resolver's inner dependency must be an async function (FastAPI DI contract)."""
    dep = require_permission("report.read")
    assert inspect.iscoroutinefunction(dep)


@pytest.mark.asyncio
async def test_require_team_membership_inner_raises_not_implemented() -> None:
    dep = require_team_membership("team-1")
    with pytest.raises(NotImplementedError):
        await dep()
