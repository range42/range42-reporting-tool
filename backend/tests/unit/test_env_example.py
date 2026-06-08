from pathlib import Path

from app.core.config import Settings


def test_every_setting_documented() -> None:
    env_example = Path(__file__).resolve().parents[3] / "deploy" / ".env.example"
    text = env_example.read_text()
    documented = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }
    required = {f.alias for f in Settings.model_fields.values() if f.alias}
    missing = required - documented
    assert not missing, f"undocumented env vars: {sorted(missing)}"
