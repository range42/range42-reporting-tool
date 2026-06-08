from pathlib import Path

import pytest

from app.core.config import Settings

# deploy/.env.example is created in Task 18; until then this coverage test cannot
# run (FileNotFoundError). Keep it skipped so the suite stays green; remove the
# skip and run it as part of Task 18 (deploy phase).
pytestmark = pytest.mark.skip(reason="deploy/.env.example created in Task 18")


def test_every_setting_documented() -> None:
    env_example = Path(__file__).resolve().parents[3] / "deploy" / ".env.example"
    text = env_example.read_text()
    documented = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }
    required = {
        f.alias for f in Settings.model_fields.values() if f.alias
    }
    missing = required - documented
    assert not missing, f"undocumented env vars: {sorted(missing)}"
