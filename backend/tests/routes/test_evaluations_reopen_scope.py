"""The negative surface: no edit-after-finalize, and no un-finalize beside the reopen.

Most of what follows asserts that something does NOT exist or is NOT permitted. It is the file
a reviewer opens to check that a reconciliation surface has not crept back in.

The rule it guards: a finalized evaluation is frozen. Grades and overall feedback are refused
while it is completed, and the ONE way back into grading is the reopen — audited, with a
mandatory reason, publishing a new grade version. An evaluator may drive that reopen on their
OWN evaluation so they can revise and finalize again; they still cannot edit in place, and they
still cannot touch a peer's evaluation.
"""

import re

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import create_app
from tests.routes._evaluations import assign, evaluator, finalize, ga_headers, submitted_report
from tests.routes._helpers import client

pytestmark = pytest.mark.integration

#: Any un-finalize path other than the one audited reopen. Deliberately broad.
_SELF_REVERT_PATH = re.compile(r"/evaluations/\{[^}]+\}/(un-?finalize|revert|withdraw|reopen-own)")


def _grade_url(ex, rid, evid, sid) -> str:
    return f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/grades/{sid}"


async def _grade(c, ex, rid, evid, sid, value, headers):
    return await c.put(_grade_url(ex, rid, evid, sid), json={"grade": value}, headers=headers)


async def _completed(migrated_db, c, ah, *, jti: str = "ev-0"):
    """Submitted report -> assigned evaluator -> graded -> finalized."""
    ex, rid, sid = await submitted_report(c, ah)
    eh, uid = await evaluator(migrated_db, c, ah, ex, jti)
    evid = await assign(c, ah, ex, rid, uid)
    r = await _grade(c, ex, rid, evid, sid, 7, eh)
    assert r.status_code == 200, r.text
    await finalize(c, eh, ex, rid, evid)
    return ex, rid, sid, eh, uid, evid


# --- the reopen is the only un-finalize ----------------------------------------------


async def test_an_evaluator_reopening_their_own_evaluation_must_still_give_a_reason(
    migrated_db: async_sessionmaker,
) -> None:
    """Duplicated from the reopen guard tests on purpose — this is the file a reviewer reads to
    confirm the rule, and a rule proven only somewhere else is a rule waiting to be lost.

    Self-revision is not silent revision: the reason is what a later dispute reads.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, _uid, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen",
            json={"reason": "   "},
            headers=eh,
        )

    # Assert
    assert r.status_code == 422, r.text
    assert r.json()["error"]["message"] == "reason_required"


async def test_an_evaluator_cannot_reopen_a_peers_evaluation(migrated_db: async_sessionmaker) -> None:
    """Revising your own work is not the same as reaching into someone else's."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, _uid, evid = await _completed(migrated_db, c, ah)
        peer, _peer_uid = await evaluator(migrated_db, c, ah, ex, "ev-peer")

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen",
            json={"reason": "i disagree with them"},
            headers=peer,
        )

    # Assert
    assert r.status_code == 403, r.text


def test_no_un_finalize_route_exists_beside_the_reopen() -> None:
    """Reads as paranoid. It is the cheapest available guard against the surface returning.

    Asserted against the live OpenAPI schema rather than by grepping source, so a route
    registered from anywhere — a new module, a stub router — is still caught.
    """
    # Arrange / Act
    paths = list(create_app().openapi()["paths"])

    # Assert
    offenders = [p for p in paths if _SELF_REVERT_PATH.search(p)]
    assert offenders == [], f"a second un-finalize surface reappeared beside the reopen: {offenders}"


# --- no edit after finalize ----------------------------------------------------------


async def test_a_grade_write_is_rejected_while_the_evaluation_is_finalized(
    migrated_db: async_sessionmaker,
) -> None:
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, eh, _uid, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await _grade(c, ex, rid, evid, sid, 9, eh)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_finalized"


async def test_a_feedback_patch_is_rejected_while_the_evaluation_is_finalized(
    migrated_db: async_sessionmaker,
) -> None:
    """Feedback is part of the finalized assessment, not a free-text margin note.

    Leaving this path open would make the scope reduction cosmetic: an evaluator who cannot
    change the number could still rewrite the words attached to it, after the fact and with
    nothing announcing the change.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, eh, _uid, evid = await _completed(migrated_db, c, ah)

        # Act
        r = await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}",
            json={"overall_feedback": "actually, on reflection, a nine"},
            headers=eh,
        )

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_finalized"


async def test_a_grade_write_is_permitted_again_after_a_reopen(migrated_db: async_sessionmaker) -> None:
    """The reopen is what unlocks editing, and it is the only thing that does."""
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid, eh, _uid, evid = await _completed(migrated_db, c, ah)
        assert (await _grade(c, ex, rid, evid, sid, 9, eh)).status_code == 409

        # Act
        rr = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen",
            json={"reason": "recount"},
            headers=ah,
        )
        assert rr.status_code == 200, rr.text
        r = await _grade(c, ex, rid, evid, sid, 9, eh)

    # Assert
    assert r.status_code == 200, r.text


async def test_a_grade_write_is_rejected_on_an_unassigned_evaluation(
    migrated_db: async_sessionmaker,
) -> None:
    """An unassigned evaluator must not keep writing grades that no longer count.

    Their row survives so the dispute trail does, but it is out of the reckoning — and a write
    that can never reach the aggregate should fail loudly rather than be silently discarded.
    """
    # Arrange: a second evaluator keeps the report gradable after the first is dropped.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh0, uid0 = await evaluator(migrated_db, c, ah, ex, "ev-0")
        _eh1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev-1")
        evid0 = await assign(c, ah, ex, rid, uid0)
        await assign(c, ah, ex, rid, uid1)
        assert (await _grade(c, ex, rid, evid0, sid, 7, eh0)).status_code == 200
        ur = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid0}/unassign",
            json={"reason": "left the exercise"},
            headers=ah,
        )
        assert ur.status_code == 200, ur.text

        # Act
        r = await _grade(c, ex, rid, evid0, sid, 9, eh0)

    # Assert
    assert r.status_code == 409, r.text
    assert r.json()["error"]["message"] == "evaluation_unassigned"


# --- the reopen stays invisible to peers ---------------------------------------------


async def test_no_evaluator_visible_field_reveals_that_a_peer_was_reopened(
    migrated_db: async_sessionmaker,
) -> None:
    """Evaluator isolation survives the reopen.

    A peer's reopen moves the shared aggregate — that is unavoidable and honest, an evaluator
    is entitled to know the report's published grade. What must not leak is WHOSE work moved
    it: no peer row, no peer id, no peer reopen counter.
    """
    # Arrange: two evaluators, both finalized, then the SECOND is reopened.
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, sid = await submitted_report(c, ah)
        eh0, uid0 = await evaluator(migrated_db, c, ah, ex, "ev-0")
        eh1, uid1 = await evaluator(migrated_db, c, ah, ex, "ev-1")
        evid0 = await assign(c, ah, ex, rid, uid0)
        evid1 = await assign(c, ah, ex, rid, uid1)
        assert (await _grade(c, ex, rid, evid0, sid, 8, eh0)).status_code == 200
        assert (await _grade(c, ex, rid, evid1, sid, 4, eh1)).status_code == 200
        await finalize(c, eh0, ex, rid, evid0)
        await finalize(c, eh1, ex, rid, evid1)
        rr = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid1}/reopen",
            json={"reason": "peer dispute"},
            headers=ah,
        )
        assert rr.status_code == 200, rr.text

        # Act — the FIRST evaluator reads their breakdown
        r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations", headers=eh0)

    # Assert
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["evaluations"]) == 1
    own = data["evaluations"][0]
    assert own["id"] == evid0
    assert own["status"] == "completed"  # their own work is untouched
    assert own["reopen_count"] == 0
    flat = str(data)
    assert evid1 not in flat
    assert uid1 not in flat


async def test_the_peers_reopen_metadata_is_visible_to_a_global_admin(
    migrated_db: async_sessionmaker,
) -> None:
    """The mirror of the test above — the isolation must be scoping, not deletion.

    If the reopen counters were simply never serialized, the test above would pass for the
    wrong reason and the admin dispute trail would be empty when it was needed.
    """
    # Arrange
    async with client(migrated_db) as c:
        ah, _ = await ga_headers(migrated_db)
        ex, rid, _sid, _eh, _uid, evid = await _completed(migrated_db, c, ah)
        rr = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/evaluations/{evid}/reopen",
            json={"reason": "recount"},
            headers=ah,
        )
        assert rr.status_code == 200, rr.text

        # Act
        r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}/evaluations", headers=ah)

    # Assert
    row = next(e for e in r.json()["data"]["evaluations"] if e["id"] == evid)
    assert row["reopen_count"] == 1
    assert row["status"] == "in_progress"
