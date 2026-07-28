"""WP3 S9 (#80) — section attachments + inline images.

Uploads are draft-only and writer-gated; the stored content type comes from
magic-byte sniffing (spoofed client MIME rejected, 415); size is capped (413);
downloads reuse the report read-scoping rules (default-deny). The storage
backend stays behind the StorageBackend Protocol — proven here by swapping in
an in-memory backend via DI override.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AuditLog
from app.seed import seed_system_roles
from tests.routes._helpers import client, make_user_token

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n%%EOF" + b"\x00" * 64
ZIP = b"PK\x03\x04" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "attachments"))


async def _ga(migrated_db):
    async with migrated_db() as s:
        await seed_system_roles(s)
        await s.commit()
    tok, _ = await make_user_token(migrated_db, jti="ga", admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _mk_report(c, ah):
    tid = (await c.post("/api/v1/templates", json={"name": "T", "report_type": "spot"}, headers=ah)).json()["data"][
        "id"
    ]
    await c.post(f"/api/v1/templates/{tid}/sections", json={"name": "S", "field_type": "rich_text"}, headers=ah)
    await c.post(f"/api/v1/templates/{tid}/publish", headers=ah)
    ex = (await c.post("/api/v1/exercises", json={"name": "E"}, headers=ah)).json()["data"]["id"]
    team = (await c.post(f"/api/v1/exercises/{ex}/teams", json={"name": "A", "team_type": "blue"}, headers=ah)).json()[
        "data"
    ]["id"]
    detail = (
        await c.post(
            f"/api/v1/exercises/{ex}/reports", json={"template_id": tid, "team_id": team, "name": "R"}, headers=ah
        )
    ).json()["data"]
    return ex, detail["id"], detail["sections"][0]["id"]


def _url(ex, rid, sid=None, aid=None):
    base = f"/api/v1/exercises/{ex}/reports/{rid}"
    if sid is not None:
        return f"{base}/sections/{sid}/attachments"
    if aid is not None:
        return f"{base}/attachments/{aid}"
    return f"{base}/attachments"


async def _upload(c, ah, ex, rid, sid, *, data=PNG, filename="pic.png", mime="image/png"):
    return await c.post(_url(ex, rid, sid=sid), files={"file": (filename, data, mime)}, headers=ah)


async def test_upload_download_roundtrip(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        r = await _upload(c, ah, ex, rid, sid)
        assert r.status_code == 201, r.text
        a = r.json()["data"]
        assert a["filename"] == "pic.png"
        assert a["content_type"] == "image/png"
        assert a["size_bytes"] == len(PNG)

        dl = await c.get(_url(ex, rid, aid=a["id"]) + "/download", headers=ah)
        assert dl.status_code == 200
        assert dl.content == PNG
        assert dl.headers["content-type"].startswith("image/png")
        assert dl.headers["x-content-type-options"] == "nosniff"
        assert "inline" in dl.headers["content-disposition"]  # images render inline (TipTap <img>)


async def test_pdf_downloads_as_attachment_disposition(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        r = await _upload(c, ah, ex, rid, sid, data=PDF, filename="doc.pdf", mime="application/pdf")
        assert r.status_code == 201, r.text
        dl = await c.get(_url(ex, rid, aid=r.json()["data"]["id"]) + "/download", headers=ah)
        assert dl.status_code == 200
        assert dl.headers["content-disposition"].startswith("attachment")


async def test_spoofed_mime_rejected_415(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        # zip bytes claiming to be a png: the claim must not be trusted
        r = await _upload(c, ah, ex, rid, sid, data=ZIP, filename="fake.png", mime="image/png")
        assert r.status_code == 415


async def test_disallowed_type_rejected_415(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        r = await _upload(c, ah, ex, rid, sid, data=b"plain text", filename="notes.txt", mime="text/plain")
        assert r.status_code == 415


async def test_oversize_rejected_413(migrated_db: async_sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTACHMENT_MAX_BYTES", "16")
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        r = await _upload(c, ah, ex, rid, sid, data=PNG)  # 72 bytes > 16
        assert r.status_code == 413


async def test_upload_blocked_when_not_draft_409(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        await c.patch(
            f"/api/v1/exercises/{ex}/reports/{rid}/sections/{sid}",
            json={"version": 1, "body": {"kind": "rich_text", "content": "<p>done</p>"}},
            headers=ah,
        )
        assert (await c.post(f"/api/v1/exercises/{ex}/reports/{rid}/submit", headers=ah)).status_code == 200
        r = await _upload(c, ah, ex, rid, sid)
        assert r.status_code == 409


async def test_outsider_cannot_upload_or_download(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        aid = (await _upload(c, ah, ex, rid, sid)).json()["data"]["id"]

        tok, _ = await make_user_token(migrated_db, jti="outsider")
        oh = {"Authorization": f"Bearer {tok}"}
        assert (await _upload(c, oh, ex, rid, sid)).status_code == 403
        assert (await c.get(_url(ex, rid, aid=aid) + "/download", headers=oh)).status_code == 403
        assert (await c.get(_url(ex, rid), headers=oh)).status_code == 403


async def test_list_returns_section_attachments(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        await _upload(c, ah, ex, rid, sid)
        await _upload(c, ah, ex, rid, sid, data=PDF, filename="doc.pdf", mime="application/pdf")
        r = await c.get(_url(ex, rid), headers=ah)
        assert r.status_code == 200
        items = r.json()["data"]
        assert {i["filename"] for i in items} == {"pic.png", "doc.pdf"}
        assert all(i["section_id"] == sid for i in items)


async def test_delete_removes_attachment_and_blob(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        aid = (await _upload(c, ah, ex, rid, sid)).json()["data"]["id"]
        assert (await c.delete(_url(ex, rid, aid=aid), headers=ah)).status_code == 204
        assert (await c.get(_url(ex, rid, aid=aid) + "/download", headers=ah)).status_code == 404
        assert (await c.delete(_url(ex, rid, aid=aid), headers=ah)).status_code == 404


async def test_upload_and_delete_write_audit_rows(migrated_db: async_sessionmaker) -> None:
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        ex, rid, sid = await _mk_report(c, ah)
        aid = (await _upload(c, ah, ex, rid, sid)).json()["data"]["id"]
        await c.delete(_url(ex, rid, aid=aid), headers=ah)
    async with migrated_db() as s:
        actions = (
            (await s.execute(select(AuditLog.action).where(AuditLog.resource_type == "attachment"))).scalars().all()
        )
    assert "attachment.create" in actions
    assert "attachment.delete" in actions


async def test_storage_protocol_swap(migrated_db: async_sessionmaker) -> None:
    """The routes must work against any StorageBackend impl (guardrail #2)."""
    from app.storage import get_storage

    class MemoryStorage:
        def __init__(self) -> None:
            self.blobs: dict[str, bytes] = {}

        async def put(self, key: str, data: bytes) -> None:
            self.blobs[key] = data

        async def get(self, key: str) -> bytes:
            return self.blobs[key]

        async def delete(self, key: str) -> None:
            self.blobs.pop(key, None)

        async def healthcheck(self) -> bool:
            return True

    mem = MemoryStorage()
    ah = await _ga(migrated_db)
    async with client(migrated_db) as c:
        c._transport.app.dependency_overrides[get_storage] = lambda: mem  # type: ignore[attr-defined]
        ex, rid, sid = await _mk_report(c, ah)
        r = await _upload(c, ah, ex, rid, sid)
        assert r.status_code == 201, r.text
        assert list(mem.blobs.values()) == [PNG]
        dl = await c.get(_url(ex, rid, aid=r.json()["data"]["id"]) + "/download", headers=ah)
        assert dl.content == PNG
