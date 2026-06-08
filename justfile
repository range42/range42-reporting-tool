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

seed:
    @echo "seed is a no-op in the skeleton (domain seed lands in WP2)"

lint:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
    cd frontend && pnpm exec eslint . && pnpm exec prettier --check .

test:
    cd backend && uv run pytest
    cd frontend && pnpm exec vitest run

build:
    docker compose -f deploy/docker-compose.yml build
