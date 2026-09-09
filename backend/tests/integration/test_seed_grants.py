"""Grants seeding: match logged-in users by email, then assign roles.

A Dex subject is not knowable before a persona's first login, so the seeder
cannot pre-assign roles the way a pinned-id realm import could. Seeding is
therefore split: ``seed_demo`` builds the world, ``seed_grants`` attaches roles
to users that already exist because they logged in.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.exercise_role import ExerciseRole
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.user import User
from app.seed_demo import ADMIN_EXTERNAL_ID, seed_demo
from app.seed_grants import GRANTS, seed_grants

REPO_ROOT = Path(__file__).resolve().parents[3]
DEX_CONFIG = REPO_ROOT / "deploy" / "dex" / "config.yaml"


def _printed_summary_keys(module: str) -> set[str]:
    """The ``summary['...']`` keys a seeding module's CLI prints."""
    return set(re.findall(r"summary\['([a-z_]+)'\]", Path(module).read_text()))


async def _login(session: AsyncSession, email: str, *, subject: str | None = None) -> User:
    """Stand in for a first OIDC login: the row upsert_user() would create."""
    user = User(
        external_id=f"oidc:{subject or email.split('@')[0]}",
        email=email,
        display_name=email.split("@")[0],
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.integration
async def test_seed_demo_creates_no_persona_users(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    """Only the emergency admin. A leftover seed:* persona is unmatchable by any
    login and shows up later as an inexplicable 403, not as a seeding error."""
    async with migrated_db() as s:
        await seed_demo(s)
        await s.commit()
        users = (await s.execute(select(User))).scalars().all()
    assert [u.external_id for u in users] == [ADMIN_EXTERNAL_ID]


@pytest.mark.integration
async def test_seed_grants_matches_users_by_email(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        await seed_demo(s)
        for g in GRANTS:
            await _login(s, g.email)
        await s.commit()

        summary = await seed_grants(s)
        await s.commit()

        roles = {
            (u.email, r.role_key)
            for r, u in (await s.execute(select(ExerciseRole, User).join(User, ExerciseRole.user_id == User.id))).all()
        }
        members = {
            (u.email, t.name)
            for m, u, t in (
                await s.execute(
                    select(TeamMember, User, Team)
                    .join(User, TeamMember.user_id == User.id)
                    .join(Team, TeamMember.team_id == Team.id)
                )
            ).all()
        }

    assert summary["granted"] == len(GRANTS)
    assert summary["skipped"] == 0
    for g in GRANTS:
        assert (g.email, g.role_key) in roles
        if g.team_name is not None:
            assert (g.email, g.team_name) in members


@pytest.mark.integration
async def test_seed_grants_skips_absent_personas(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    """Expected state, not an error: the step runs before everyone has logged in."""
    present = GRANTS[0]
    async with migrated_db() as s:
        await seed_demo(s)
        await _login(s, present.email)
        await s.commit()

        summary = await seed_grants(s)
        await s.commit()

    assert summary["granted"] == 1
    assert summary["skipped"] == len(GRANTS) - 1
    assert present.email not in summary["skipped_emails"]


@pytest.mark.integration
async def test_seed_grants_is_idempotent(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        await seed_demo(s)
        for g in GRANTS:
            await _login(s, g.email)
        await s.commit()

        await seed_grants(s)
        await s.commit()
        roles_after_first = len((await s.execute(select(ExerciseRole))).scalars().all())
        members_after_first = len((await s.execute(select(TeamMember))).scalars().all())

        await seed_grants(s)
        await s.commit()
        roles_after_second = len((await s.execute(select(ExerciseRole))).scalars().all())
        members_after_second = len((await s.execute(select(TeamMember))).scalars().all())

    assert roles_after_first == roles_after_second
    assert members_after_first == members_after_second


@pytest.mark.integration
async def test_grants_promote_an_oidc_global_admin(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    """The row always exists before this runs, and neither upsert_user() (which
    ignores provider claims for this flag) nor _get_or_create_user() (insert
    branch only) will ever set it. Reconciling on update is the point."""
    admin_grant = next(g for g in GRANTS if g.is_global_admin)
    async with migrated_db() as s:
        await seed_demo(s)
        await _login(s, admin_grant.email)
        await s.commit()

        await seed_grants(s)
        await s.commit()

        user = (await s.execute(select(User).where(User.email == admin_grant.email))).scalar_one()
        assert user.is_global_admin is True


@pytest.mark.integration
async def test_grants_do_not_demote_an_existing_admin(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    non_admin = next(g for g in GRANTS if not g.is_global_admin)
    async with migrated_db() as s:
        await seed_demo(s)
        user = await _login(s, non_admin.email)
        user.is_global_admin = True  # promoted out of band
        await s.commit()

        await seed_grants(s)
        await s.commit()

        refreshed = (await s.execute(select(User).where(User.email == non_admin.email))).scalar_one()
        assert refreshed.is_global_admin is True


def test_persona_emails_match_the_dex_config() -> None:
    """Two hand-maintained lists in two files will drift; this is the guard.

    Parsed with a regex rather than a YAML loader: pyyaml is not a declared
    backend dependency, only a transitive one.
    """
    text = DEX_CONFIG.read_text()
    static_block = text.split("staticPasswords:", 1)[1]
    dex_emails = set(re.findall(r"^\s*-\s*email:\s*(\S+)\s*$", static_block, re.MULTILINE))
    assert dex_emails == {g.email for g in GRANTS}


@pytest.mark.integration
async def test_seed_summaries_carry_every_key_their_cli_prints(
    migrated_db: async_sessionmaker[AsyncSession],
) -> None:
    """The ``_main()`` print blocks are a contract on the summary dicts.

    They are only executed by the module-as-script path, so a key renamed in the
    seeding function and left stale in its printout fails at runtime, in the
    container, after the data has already been committed — never under test.
    This scrapes the keys each CLI prints and asserts the summary provides them.
    """
    async with migrated_db() as s:
        demo_summary = await seed_demo(s)
        for g in GRANTS:
            await _login(s, g.email)
        grants_summary = await seed_grants(s)
        await s.commit()

    for module, summary in (
        ("app/seed_demo.py", demo_summary),
        ("app/seed_grants.py", grants_summary),
    ):
        printed = _printed_summary_keys(module)
        assert printed, f"no summary keys found in {module} — has the CLI changed shape?"
        assert printed <= set(summary), f"{module} prints keys its summary lacks: {printed - set(summary)}"
