import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Exercise, ScoringConfig, TeamTypeConfig, User
from app.seed import DEFAULT_TEAM_TYPES, seed_exercise_defaults


async def _make_exercise(s: AsyncSession) -> Exercise:
    u = User(external_id="oidc:owner", email="o@x", display_name="O", is_global_admin=True)
    s.add(u)
    await s.flush()
    ex = Exercise(name="Ex", created_by=u.id)
    s.add(ex)
    await s.flush()
    return ex


@pytest.mark.integration
async def test_seeds_team_types_and_scoring(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ex = await _make_exercise(s)
        await seed_exercise_defaults(s, ex.id)
        await s.commit()
        types = (await s.execute(select(TeamTypeConfig).where(TeamTypeConfig.exercise_id == ex.id))).scalars().all()
        sc = (await s.execute(select(ScoringConfig).where(ScoringConfig.exercise_id == ex.id))).scalar_one()
    assert {t.type_key for t in types} == {d.type_key for d in DEFAULT_TEAM_TYPES}
    assert sc.teams_see_own_scores is True
    assert sc.show_leaderboard is False


@pytest.mark.integration
async def test_seed_is_idempotent(migrated_db: async_sessionmaker[AsyncSession]) -> None:
    async with migrated_db() as s:
        ex = await _make_exercise(s)
        await seed_exercise_defaults(s, ex.id)
        await seed_exercise_defaults(s, ex.id)  # second call must not duplicate
        await s.commit()
        n = len((await s.execute(select(TeamTypeConfig).where(TeamTypeConfig.exercise_id == ex.id))).scalars().all())
    assert n == len(DEFAULT_TEAM_TYPES)
