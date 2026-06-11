from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import mint_app_jwt
from app.main import create_app
from app.models import User, UserSession

SECRET = "x" * 32  # must equal tests/routes/conftest.py::SECRET (the app's verify secret)


def client(sm: async_sessionmaker) -> AsyncClient:
    app = create_app()
    app.state.db_sessionmaker = sm
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def make_user_token(sm: async_sessionmaker, *, jti: str, admin: bool = False, **kw: Any) -> tuple[str, str]:
    """Create a user + session; return (token, user_id)."""
    async with sm() as s:
        u = User(external_id=f"oidc:{jti}", email=f"{jti}@x", display_name="U", is_global_admin=admin, **kw)
        s.add(u)
        await s.flush()
        s.add(
            UserSession(
                jti=jti, user_id=u.id, auth_time=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(hours=1)
            )
        )
        uid = str(u.id)
        await s.commit()
    token = mint_app_jwt(
        user_id=uid, is_global_admin=admin, jti=jti, auth_time=datetime.now(UTC), secret=SECRET, ttl_minutes=60
    )
    return token, uid
