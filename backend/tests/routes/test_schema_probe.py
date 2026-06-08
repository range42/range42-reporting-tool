import pytest

from app.main import create_app


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)


def _find_discriminator(obj: object) -> bool:
    """Recursively search an OpenAPI fragment for a `discriminator` key."""
    if isinstance(obj, dict):
        if "discriminator" in obj:
            return True
        return any(_find_discriminator(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_find_discriminator(v) for v in obj)
    return False


def test_schema_probe_emits_discriminator(env: None) -> None:
    app = create_app()
    schema = app.openapi()
    path = schema["paths"]["/api/v1/_schema_probe"]["post"]
    request_schema = path["requestBody"]["content"]["application/json"]["schema"]
    # The request body resolves (possibly via $ref) to the SectionBody union;
    # assert the discriminator landed somewhere reachable in the document.
    assert _find_discriminator(request_schema) or _find_discriminator(schema["components"])
