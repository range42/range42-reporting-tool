import os
import tempfile
from collections.abc import Iterator

import pytest

# app/main.py instantiates `app = create_app()` at import time, which calls
# Settings() and requires these vars. Test modules import app.main at collection,
# before per-test fixtures run, so provide them here at conftest load time so the
# import succeeds. The autouse fixture below then removes them per-test so unit
# tests that assert on a clean environment (e.g. missing-secret validation) are
# not affected by these collection-time defaults.
_IMPORT_TIME_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/app",
    "JWT_SECRET": "x" * 32,
    # Default storage path (/data/attachments) is not writable in local/CI test
    # sandboxes; point it at a writable temp dir for the storage health probe.
    "STORAGE_LOCAL_PATH": os.path.join(tempfile.gettempdir(), "rt-test-storage"),
}
for _k, _v in _IMPORT_TIME_ENV.items():
    os.environ.setdefault(_k, _v)


# Only the required secrets must be removed per-test (unit tests assert on their
# absence). STORAGE_LOCAL_PATH stays set: no test asserts a clean storage path,
# and the health endpoint needs a writable location.
_CLEAN_PER_TEST = ("DATABASE_URL", "JWT_SECRET")


@pytest.fixture(autouse=True)
def _clean_collection_env() -> Iterator[None]:
    from app.core.config import get_settings

    saved = {k: os.environ.pop(k, None) for k in _CLEAN_PER_TEST}
    get_settings.cache_clear()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
        get_settings.cache_clear()
