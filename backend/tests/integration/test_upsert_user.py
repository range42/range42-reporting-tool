import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.base import NormalizedClaims
from app.auth.users import upsert_user
from app.models.user import User


@pytest.mark.integration
async def test_upsert_inserts_with_namespaced_external_id(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    claims = NormalizedClaims(subject="abc-123", email="a@x.test", display_name="Ann", provider="oidc")
    async with migrated_db() as s:
        user = await upsert_user(s, claims)
        await s.commit()
        assert user.external_id == "oidc:abc-123"
        assert user.email == "a@x.test"
        assert user.is_global_admin is False


@pytest.mark.integration
async def test_upsert_updates_existing_and_is_idempotent(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    first = NormalizedClaims(subject="abc-123", email="a@x.test", display_name="Ann", provider="oidc")
    async with migrated_db() as s:
        u1 = await upsert_user(s, first)
        await s.commit()
        uid = u1.id

    second = NormalizedClaims(subject="abc-123", email="ann@x.test", display_name="Ann B", provider="oidc")
    async with migrated_db() as s:
        u2 = await upsert_user(s, second)
        await s.commit()
        assert u2.id == uid
        assert u2.email == "ann@x.test"
        assert u2.display_name == "Ann B"
        count = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        assert count == 1


@pytest.mark.integration
async def test_same_subject_different_provider_are_distinct(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    oidc = NormalizedClaims(subject="abc-123", email="a@x.test", display_name="Ann", provider="oidc")
    saml = NormalizedClaims(subject="abc-123", email="a@x.test", display_name="Ann", provider="saml")
    async with migrated_db() as s:
        u_oidc = await upsert_user(s, oidc)
        u_saml = await upsert_user(s, saml)
        await s.commit()
        assert u_oidc.id != u_saml.id
        assert u_oidc.external_id == "oidc:abc-123"
        assert u_saml.external_id == "saml:abc-123"
        count = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        assert count == 2


@pytest.mark.integration
async def test_upsert_sets_and_updates_avatar(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        u1 = await upsert_user(
            s,
            NormalizedClaims(
                subject="av", email="a@x", display_name="A", provider="oidc", avatar_url="https://img/1.png"
            ),
        )
        assert u1.avatar_url == "https://img/1.png"
        u2 = await upsert_user(
            s,
            NormalizedClaims(
                subject="av", email="a@x", display_name="A", provider="oidc", avatar_url="https://img/2.png"
            ),
        )
        assert u2.id == u1.id
        assert u2.avatar_url == "https://img/2.png"  # updated on hit
