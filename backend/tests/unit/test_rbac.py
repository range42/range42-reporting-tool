import pytest

from app.core.rbac import require_permission, require_team_membership


def test_require_permission_constructs() -> None:
    dep = require_permission("report.read")
    assert callable(dep)


def test_require_team_membership_constructs() -> None:
    dep = require_team_membership("team-1")
    assert callable(dep)


@pytest.mark.asyncio
async def test_require_permission_inner_raises_not_implemented() -> None:
    dep = require_permission("report.read")
    with pytest.raises(NotImplementedError):
        await dep()


@pytest.mark.asyncio
async def test_require_team_membership_inner_raises_not_implemented() -> None:
    dep = require_team_membership("team-1")
    with pytest.raises(NotImplementedError):
        await dep()
