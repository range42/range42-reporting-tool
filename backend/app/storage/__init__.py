"""Storage package — pluggable blob backends behind the StorageBackend Protocol."""

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage


def get_storage(s: Settings = Depends(get_settings)) -> StorageBackend:
    """DI factory for the configured storage backend (guardrail #2: Protocol-pluggable).

    Only the local-FS backend ships in v1; ``s3`` is reserved in the Settings
    Literal and lands with WP6 export work.
    """
    if s.storage_backend != "local":
        raise NotImplementedError(f"storage backend {s.storage_backend!r} not available in v1")
    return LocalStorage(s.storage_local_path)


__all__ = ["StorageBackend", "LocalStorage", "get_storage"]
