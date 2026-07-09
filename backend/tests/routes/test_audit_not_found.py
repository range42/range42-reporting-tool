"""Regression: 404-producing mutations must not write any audit_log rows."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration


async def test_patch_missing_exercise_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="anf-admin1", admin=True)
    h = {"Authorization": f"Bearer {token}"}

    rand = str(uuid.uuid4())
    async with client(migrated_db) as c:
        r = await c.patch(f"/api/v1/exercises/{rand}", json={"name": "ghost"}, headers=h)

    assert r.status_code == 404

    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "exercise.update"))
        ).scalar_one()
    assert n == 0, f"Expected 0 audit rows for exercise.update on a 404, got {n}"


async def test_delete_missing_role_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="anf-admin2", admin=True)
    h = {"Authorization": f"Bearer {token}"}

    rand = str(uuid.uuid4())
    async with client(migrated_db) as c:
        r = await c.delete(f"/api/v1/roles/{rand}", headers=h)

    assert r.status_code == 404

    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "role.delete"))
        ).scalar_one()
    assert n == 0, f"Expected 0 audit rows for role.delete on a 404, got {n}"


async def test_delete_missing_exercise_role_emits_no_audit(migrated_db: async_sessionmaker) -> None:
    token, _ = await make_user_token(migrated_db, jti="anf-admin3", admin=True)
    h = {"Authorization": f"Bearer {token}"}

    async with client(migrated_db) as c:
        ex = (await c.post("/api/v1/exercises", json={"name": "AuditNF"}, headers=h)).json()["data"]["id"]
        rand = str(uuid.uuid4())
        r = await c.delete(f"/api/v1/exercises/{ex}/roles/{rand}", headers=h)

    assert r.status_code == 404

    async with migrated_db() as s:
        n = (
            await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "exercise_role.revoke"))
        ).scalar_one()
    assert n == 0, f"Expected 0 audit rows for exercise_role.revoke on a 404, got {n}"
