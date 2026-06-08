import uuid
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if not str(p).startswith(str(self._root.resolve())):
            raise ValueError("path traversal blocked")
        return p

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def healthcheck(self) -> bool:
        probe = self._root / f".health-{uuid.uuid4().hex}"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False
