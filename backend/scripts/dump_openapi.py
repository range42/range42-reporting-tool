"""Write the OpenAPI spec to backend/openapi.json without booting a server.
Usage: cd backend && DATABASE_URL=postgresql+asyncpg://u:p@db:5432/app JWT_SECRET=<32+chars> PYTHONPATH=. uv run python scripts/dump_openapi.py"""

import json
from pathlib import Path

from app.main import app

out = Path(__file__).resolve().parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"wrote {out}")
