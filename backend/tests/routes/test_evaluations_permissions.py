"""The D1 permission matrix — the slice's security boundary.

THIS MODULE IS A VERIFIER, NOT A DRIVER. A failing cell is a bug in the handler that owns the
route (Tasks 5-9), never a wrong assertion here. Any relaxation of a 403 cell is a D1
violation and must be rejected in review.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._evaluations import assign, evaluator, ga_headers, role_holder, submitted_report
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

# Non-evaluator exercise roles: 403 on every W5-1 evaluation route (L13). Their read of a
# finalized evaluation is W5-4, not this slice.
DENIED_ROLES = ["team_admin", "team_writer", "team_approver", "observer"]


class Fixture:
    """One exercise, one submitted report, and the personas the matrix needs."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


async def _fixture(migrated_db, c, ah):
    ex, rid, sid = await submitted_report(c, ah)
    ha, uid_a = await evaluator(migrated_db, c, ah, ex, "ev-a")
    hb, uid_b = await evaluator(migrated_db, c, ah, ex, "ev-b")
    hc, uid_c = await evaluator(migrated_db, c, ah, ex, "ev-c")  # holds the permission, NOT assigned
    evid_a = await assign(c, ah, ex, rid, uid_a)
    evid_b = await assign(c, ah, ex, rid, uid_b)
    denied = {}
    for rk in DENIED_ROLES:
        denied[rk], _ = await role_holder(migrated_db, c, ah, ex, f"p-{rk}", rk)
    tok, uid_out = await make_user_token(migrated_db, jti="out")  # authenticated, no role here
    return Fixture(
        ex=ex,
        rid=rid,
        sid=sid,
        ha=ha,
        hb=hb,
        hc=hc,
        uid_a=uid_a,
        uid_b=uid_b,
        uid_c=uid_c,
        uid_out=uid_out,
        evid_a=evid_a,
        evid_b=evid_b,
        denied=denied,
        hout={"Authorization": f"Bearer {tok}"},
    )


def _base(f):
    return f"/api/v1/exercises/{f.ex}/reports/{f.rid}/evaluations"


async def _assert_denied_everywhere(c, f, h):
    """Every W5-1 evaluation route 403s for this caller."""
    b = _base(f)
    assert (await c.post(b, json={"evaluator_id": f.uid_c}, headers=h)).status_code == 403
    assert (await c.get(b, headers=h)).status_code == 403
    assert (await c.get(f"{b}/{f.evid_a}", headers=h)).status_code == 403
    assert (await c.patch(f"{b}/{f.evid_a}", json={"overall_feedback": "x"}, headers=h)).status_code == 403
    assert (await c.put(f"{b}/{f.evid_a}/grades/{f.sid}", json={"grade": "5"}, headers=h)).status_code == 403
    assert (await c.get(f"{b}/{f.evid_a}/grades", headers=h)).status_code == 403


# --- the parametrized sweep ---------------------------------------------------


@pytest.mark.parametrize("role_key", DENIED_ROLES)
async def test_permission_matrix_denies_non_evaluator_roles_on_every_route(
    migrated_db: async_sessionmaker, role_key: str
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        await _assert_denied_everywhere(c, f, f.denied[role_key])


async def test_permission_matrix_denies_an_outsider_on_every_route(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        await _assert_denied_everywhere(c, f, f.hout)


async def test_permission_matrix_assign_is_global_admin_only(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        # An assigned evaluator may not assign anyone — not even themselves.
        assert (await c.post(_base(f), json={"evaluator_id": f.uid_c}, headers=f.ha)).status_code == 403


async def test_permission_matrix_global_admin_reads_every_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        assert len((await c.get(_base(f), headers=ah)).json()["data"]) == 2
        assert (await c.get(f"{_base(f)}/{f.evid_a}", headers=ah)).status_code == 200
        assert (await c.get(f"{_base(f)}/{f.evid_b}", headers=ah)).status_code == 200


async def test_permission_matrix_assigned_evaluator_owns_every_write_on_their_row(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        b = _base(f)
        assert (await c.get(f"{b}/{f.evid_a}", headers=f.ha)).status_code == 200
        assert (await c.patch(f"{b}/{f.evid_a}", json={"overall_feedback": "x"}, headers=f.ha)).status_code == 200
        assert (await c.put(f"{b}/{f.evid_a}/grades/{f.sid}", json={"grade": "5"}, headers=f.ha)).status_code == 200
        assert (await c.get(f"{b}/{f.evid_a}/grades", headers=f.ha)).status_code == 200


# --- D1: explicit cross-evaluator rejections (must never be relaxed) ---------


async def test_evaluator_a_cannot_touch_evaluator_b_evaluation(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        b = _base(f)
        assert (await c.get(f"{b}/{f.evid_b}", headers=f.ha)).status_code == 403
        assert (await c.patch(f"{b}/{f.evid_b}", json={"overall_feedback": "x"}, headers=f.ha)).status_code == 403
        assert (await c.put(f"{b}/{f.evid_b}/grades/{f.sid}", json={"grade": "5"}, headers=f.ha)).status_code == 403
        assert (await c.get(f"{b}/{f.evid_b}/grades", headers=f.ha)).status_code == 403


async def test_evaluator_c_unassigned_to_this_report_gets_403_on_every_detail_route(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        b = _base(f)
        # …but the LIST route is 200 + [] for them — filter, not gate.
        listed = await c.get(b, headers=f.hc)
        assert listed.status_code == 200
        assert listed.json()["data"] == []
        assert (await c.get(f"{b}/{f.evid_a}", headers=f.hc)).status_code == 403
        assert (await c.patch(f"{b}/{f.evid_a}", json={"overall_feedback": "x"}, headers=f.hc)).status_code == 403
        assert (await c.put(f"{b}/{f.evid_a}/grades/{f.sid}", json={"grade": "5"}, headers=f.hc)).status_code == 403
        assert (await c.get(f"{b}/{f.evid_a}/grades", headers=f.hc)).status_code == 403


async def test_evaluator_a_cannot_read_evaluator_b_evaluation_after_both_finalized(
    migrated_db: async_sessionmaker,
) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        async with migrated_db() as s:
            await s.execute(
                text("UPDATE evaluation SET status = 'completed' WHERE report_id = CAST(:i AS uuid)"), {"i": f.rid}
            )
            await s.execute(text("UPDATE report SET status = 'evaluated' WHERE id = CAST(:i AS uuid)"), {"i": f.rid})
            await s.commit()
        assert (await c.get(f"{_base(f)}/{f.evid_b}", headers=f.ha)).status_code == 403


async def test_evaluations_list_for_an_evaluator_never_exceeds_one_row(migrated_db: async_sessionmaker) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        assert len((await c.get(_base(f), headers=f.ha)).json()["data"]) == 1
        assert len((await c.get(_base(f), headers=f.hb)).json()["data"]) == 1


async def test_no_evaluation_route_exposes_a_peer_evaluator_id(migrated_db: async_sessionmaker) -> None:
    # Leak canary: the serialized body of every evaluator-facing route must not contain the peer's id.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        b = _base(f)
        await c.patch(f"{b}/{f.evid_a}", json={"overall_feedback": "x"}, headers=f.ha)
        await c.put(f"{b}/{f.evid_a}/grades/{f.sid}", json={"grade": "5"}, headers=f.ha)
        bodies = [
            (await c.get(b, headers=f.ha)).text,
            (await c.get(f"{b}/{f.evid_a}", headers=f.ha)).text,
            (await c.get(f"{b}/{f.evid_a}/grades", headers=f.ha)).text,
            (await c.patch(f"{b}/{f.evid_a}", json={"overall_feedback": "y"}, headers=f.ha)).text,
        ]
        for body in bodies:
            assert f.uid_b not in body
            assert f.evid_b not in body


async def test_evaluator_whose_exercise_role_was_revoked_gets_403(migrated_db: async_sessionmaker) -> None:
    # Edge case 6 — the evaluation row survives (evaluator_id is RESTRICT); the caller does not.
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        assignments = (await c.get(f"/api/v1/exercises/{f.ex}/roles", headers=ah)).json()["data"]
        aid = next(a["id"] for a in assignments if a["user_id"] == f.uid_a)
        assert (await c.delete(f"/api/v1/exercises/{f.ex}/roles/{aid}", headers=ah)).status_code == 204
        assert (await c.get(f"{_base(f)}/{f.evid_a}", headers=f.ha)).status_code == 403
        # TODO(W5-3/W5-4): reassignment of an orphaned evaluation is out of scope here.


# --- recall row of the matrix (Task 9's route) --------------------------------


@pytest.mark.parametrize("role_key", ["team_writer", "team_approver", "observer"])
async def test_recall_is_denied_to_roles_without_reports_recall(migrated_db: async_sessionmaker, role_key: str) -> None:
    ah, _ = await ga_headers(migrated_db)
    async with client(migrated_db) as c:
        f = await _fixture(migrated_db, c, ah)
        h = f.denied[role_key]
        r = await c.post(f"/api/v1/exercises/{f.ex}/reports/{f.rid}/recall", headers=h)
        assert r.status_code == 403
