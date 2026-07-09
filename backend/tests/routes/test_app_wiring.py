import pytest
from starlette.middleware.sessions import SessionMiddleware

from app.core.rbac import get_oidc_provider
from app.main import create_app


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)


def test_session_middleware_installed(env: None) -> None:
    app = create_app()
    assert any(m.cls is SessionMiddleware for m in app.user_middleware)


def test_get_oidc_provider_503_when_unconfigured(env: None) -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    scope = {"type": "http", "app": create_app(), "headers": []}
    req = Request(scope)
    req.app.state.oidc_provider = None
    with pytest.raises(HTTPException) as ei:
        get_oidc_provider(req)
    assert ei.value.status_code == 503
