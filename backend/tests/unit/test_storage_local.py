from pathlib import Path

import pytest

from app.storage.local import LocalStorage


@pytest.mark.asyncio
async def test_write_read_roundtrip(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    await store.put("a/b.txt", b"hello")
    assert await store.get("a/b.txt") == b"hello"


@pytest.mark.asyncio
async def test_healthcheck_writable(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    assert await store.healthcheck() is True
