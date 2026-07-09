import inspect

from app.core.rbac import require_permission, require_team_membership


def test_require_permission_constructs() -> None:
    dep = require_permission("report.read")
    assert callable(dep)


def test_require_permission_inner_is_coroutine() -> None:
    """The resolver's inner dependency must be an async function (FastAPI DI contract)."""
    dep = require_permission("report.read")
    assert inspect.iscoroutinefunction(dep)


def test_require_team_membership_is_coroutine_function() -> None:
    """require_team_membership is now a plain async dependency (not a factory). FastAPI reads
    the ``team_id`` path parameter directly — no wrapping factory needed."""
    assert inspect.iscoroutinefunction(require_team_membership)
