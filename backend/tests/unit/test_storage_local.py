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


@pytest.mark.asyncio
async def test_delete_removes_object(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    await store.put("a/b.bin", b"payload")
    await store.delete("a/b.bin")
    with pytest.raises(FileNotFoundError):
        await store.get("a/b.bin")


@pytest.mark.asyncio
async def test_delete_missing_key_is_idempotent(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    await store.delete("never/was.bin")  # must not raise


def test_path_traversal_blocked(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError):
        store._path("../evil.txt")


def test_path_traversal_sibling_prefix_blocked(tmp_path: Path) -> None:
    # A sibling dir sharing the root's name prefix must not bypass the guard.
    store = LocalStorage(str(tmp_path / "attachments"))
    with pytest.raises(ValueError):
        store._path("../attachments-evil/x")
