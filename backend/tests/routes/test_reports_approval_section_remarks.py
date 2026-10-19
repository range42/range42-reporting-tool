import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.routes._helpers import client
from tests.routes.test_reports_approve import _ga, _mk_pending

pytestmark = pytest.mark.integration


async def _first_section_id(c, ah, ex: str, rid: str) -> str:
    detail = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]
    return detail["sections"][0]["id"]


async def test_approve_with_section_remarks_persists_them(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        sid = await _first_section_id(c, ah, ex, rid)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"comment": "lgtm overall", "section_remarks": [{"report_section_id": sid, "remark": "typo"}]},
            headers=ah,
        )

    # Assert
    assert r.status_code == 200, r.text
    rec = r.json()["data"]["approval_records"][0]
    assert rec["comment"] == "lgtm overall"
    assert [(m["report_section_id"], m["remark"]) for m in rec["section_remarks"]] == [(sid, "typo")]


async def test_reject_with_section_remarks_persists_them(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        sid = await _first_section_id(c, ah, ex, rid)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/reject",
            json={"comment": "needs work", "section_remarks": [{"report_section_id": sid, "remark": "no evidence"}]},
            headers=ah,
        )

    # Assert
    assert r.status_code == 200, r.text
    rec = r.json()["data"]["approval_records"][0]
    assert rec["section_remarks"][0]["remark"] == "no evidence"


async def test_report_detail_returns_the_section_remarks_of_a_rejection(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        sid = await _first_section_id(c, ah, ex, rid)
        await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/reject",
            json={"comment": "needs work", "section_remarks": [{"report_section_id": sid, "remark": "no evidence"}]},
            headers=ah,
        )

        # Act
        r = await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    rec = r.json()["data"]["approval_records"][0]
    assert rec["section_remarks"][0]["report_section_id"] == sid


async def test_approve_rejects_remark_on_foreign_section(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        other_ex, other_rid, _ = await _mk_pending(c, ah)
        foreign_sid = await _first_section_id(c, ah, other_ex, other_rid)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"section_remarks": [{"report_section_id": foreign_sid, "remark": "x"}]},
            headers=ah,
        )
        after = (await c.get(f"/api/v1/exercises/{ex}/reports/{rid}", headers=ah)).json()["data"]

    # Assert
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "section_not_found"
    assert after["status"] == "pending_approval"
    assert after["approval_records"] == []


async def test_approve_rejects_malformed_section_id(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"section_remarks": [{"report_section_id": "not-a-uuid", "remark": "x"}]},
            headers=ah,
        )

    # Assert
    assert r.status_code == 422


async def test_approve_rejects_duplicate_section_remark(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        sid = await _first_section_id(c, ah, ex, rid)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={
                "section_remarks": [
                    {"report_section_id": sid, "remark": "one"},
                    {"report_section_id": sid, "remark": "two"},
                ]
            },
            headers=ah,
        )

    # Assert
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "duplicate_section_remark"


async def test_approve_rejects_blank_remark(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)
        sid = await _first_section_id(c, ah, ex, rid)

        # Act
        r = await c.post(
            f"/api/v1/exercises/{ex}/reports/{rid}/approve",
            json={"section_remarks": [{"report_section_id": sid, "remark": "   "}]},
            headers=ah,
        )

    # Assert
    assert r.status_code == 422


async def test_approve_without_section_remarks_returns_an_empty_list(migrated_db: async_sessionmaker) -> None:
    # Arrange
    ah, _ = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, _ = await _mk_pending(c, ah)

        # Act
        r = await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/approve", json={"comment": "ok"}, headers=ah)

    # Assert
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approval_records"][0]["section_remarks"] == []
