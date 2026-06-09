from app.core.config import Settings, get_settings


def test_get_settings_is_cached(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert isinstance(a, Settings)
    assert a is b  # same cached instance, env not re-read per call
