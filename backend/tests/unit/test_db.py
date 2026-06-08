from app.core.db import build_engine, get_sessionmaker


def test_build_engine_uses_asyncpg() -> None:
    engine = build_engine("postgresql+asyncpg://u:p@db:5432/app")
    assert engine.dialect.driver == "asyncpg"


def test_sessionmaker_returns_factory() -> None:
    engine = build_engine("postgresql+asyncpg://u:p@db:5432/app")
    sm = get_sessionmaker(engine)
    assert sm.kw["expire_on_commit"] is False
