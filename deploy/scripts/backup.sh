#!/usr/bin/env bash
set -euo pipefail
ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p backups
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U reporting reporting > "backups/db-${ts}.sql"
echo "wrote backups/db-${ts}.sql"
