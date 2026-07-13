set dotenv-load := false

up:
    docker compose -f deploy/docker-compose.yml up --build

down:
    docker compose -f deploy/docker-compose.yml down -v

prod:
    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

migrate:
    docker compose -f deploy/docker-compose.yml run --rm migrate

logs:
    docker compose -f deploy/docker-compose.yml logs -f

# Seed the running dev stack. Runs inside the backend container (env_file + the
# `postgres` hostname only exist there). Launches both scripts, in order:
#   1. app.seed      - the 5 built-in system roles (baseline).
#   2. app.seed_demo - the emergency admin, persona users, an exercise, teams,
#                      and a published template (for manual exploration).
# Both are idempotent, so re-running never duplicates rows. Requires `just up`.
seed:
    docker compose -f deploy/docker-compose.yml exec -T backend uv run --no-sync python -m app.seed
    docker compose -f deploy/docker-compose.yml exec -T backend uv run --no-sync python -m app.seed_demo

lint:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
    cd frontend && pnpm exec eslint . && pnpm exec prettier --check .

test:
    cd backend && uv run pytest
    cd frontend && pnpm exec vitest run

build:
    docker compose -f deploy/docker-compose.yml build
