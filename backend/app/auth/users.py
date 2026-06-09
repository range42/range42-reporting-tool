from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import NormalizedClaims
from app.models.user import User


async def upsert_user(session: AsyncSession, claims: NormalizedClaims, *, now: datetime | None = None) -> User:
    """Map normalized claims to a User row (insert on miss, update on hit).

    ``external_id`` is namespaced ``{provider}:{subject}`` so OIDC/SAML/emergency
    subjects cannot collide on the UNIQUE column (design §2.1). ``is_global_admin``
    is intentionally not touched here — it is managed by us, not provider claims.
    """
    external_id = f"{claims.provider}:{claims.subject}"
    stamp = now or datetime.now(UTC)
    existing = (await session.execute(select(User).where(User.external_id == external_id))).scalar_one_or_none()
    if existing is None:
        user = User(
            external_id=external_id,
            email=claims.email,
            display_name=claims.display_name,
            last_login_at=stamp,
        )
        session.add(user)
        await session.flush()
        return user
    existing.email = claims.email
    existing.display_name = claims.display_name
    existing.last_login_at = stamp
    await session.flush()
    return existing
