set dotenv-load := false

# The dev stack is the base compose plus the dev overlay (local OIDC provider).
# `prod` deliberately does NOT include the overlay.
dev := "-f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml"

up:
    docker compose {{dev}} up --build

down:
    docker compose {{dev}} down -v

prod:
    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

migrate:
    docker compose {{dev}} run --rm migrate

logs:
    docker compose {{dev}} logs -f

# Seed the running dev stack. Runs inside the backend container (env_file + the
# `postgres` hostname only exist there). Launches both scripts, in order:
#   1. app.seed      - the 5 built-in system roles (baseline).
#   2. app.seed_demo - the emergency admin, an exercise, teams, and a published
#                      template (for manual exploration). No persona users:
#                      those arrive by SSO login, then `just seed-grants`.
# Both are idempotent, so re-running never duplicates rows. Requires `just up`.
seed:
    docker compose {{dev}} exec -T backend uv run --no-sync python -m app.seed
    docker compose {{dev}} exec -T backend uv run --no-sync python -m app.seed_demo

# Assign persona roles + team membership. Matches users by EMAIL, so it must run
# *after* each persona has logged in once through the IdP — a login is what
# creates their row. Idempotent: re-run it as more personas log in, and anyone
# who has not yet is reported as skipped.
seed-grants:
    docker compose {{dev}} exec -T backend uv run --no-sync python -m app.seed_grants

lint:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
    cd frontend && pnpm exec eslint . && pnpm exec prettier --check .

test:
    cd backend && uv run pytest
    cd frontend && pnpm exec vitest run

build:
    docker compose {{dev}} build
