"""Who can be assigned to evaluate in an exercise (the assignment screen's picker).

The list must agree with what ``POST …/evaluations`` accepts: a name that appears here and is
then rejected as ``user_is_not_an_evaluator`` would be a picker that lies.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import evaluator, ga_headers, role_holder
from tests.routes._helpers import client

pytestmark = pytest.mark.integration


def _url(ex: str) -> str:
    return f"/api/v1/exercises/{ex}/evaluator-candidates"


async def _exercise(c, ah) -> str:
    return (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]


async def test_lists_the_exercise_evaluators_with_their_names(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = await _exercise(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.get(_url(ex), headers=ah)
        assert r.status_code == 200, r.text
        assert r.json()["data"] == [{"user_id": uid, "display_name": "U", "email": "ev1@x"}]


async def test_excludes_roles_that_do_not_grant_evaluations_write(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = await _exercise(c, ah)
        await role_holder(migrated_db, c, ah, ex, "w1", "team_writer")
        await role_holder(migrated_db, c, ah, ex, "a1", "team_approver")
        assert (await c.get(_url(ex), headers=ah)).json()["data"] == []


async def test_excludes_evaluators_of_a_different_exercise(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        mine, theirs = await _exercise(c, ah), await _exercise(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, mine, "ev1")
        await evaluator(migrated_db, c, ah, theirs, "ev2")
        assert [row["user_id"] for row in (await c.get(_url(mine), headers=ah)).json()["data"]] == [uid]


async def test_lists_each_evaluator_once_even_with_several_roles(migrated_db: async_sessionmaker) -> None:
    """A user holding evaluator AND another role is one candidate, not two rows."""
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = await _exercise(c, ah)
        _, uid = await evaluator(migrated_db, c, ah, ex, "ev1")
        r = await c.post(
            f"/api/v1/exercises/{ex}/roles",
            json={"user_id": uid, "role_key": "observer"},
            headers=ah,
        )
        assert r.status_code == 201, r.text
        assert [row["user_id"] for row in (await c.get(_url(ex), headers=ah)).json()["data"]] == [uid]


async def test_is_rejected_for_non_admin_callers(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        ex = await _exercise(c, ah)
        eh, _ = await evaluator(migrated_db, c, ah, ex, "ev1")
        assert (await c.get(_url(ex), headers=eh)).status_code == 403
