#!/usr/bin/env bash
set -euo pipefail
test -f "${1:?usage: restore.sh <dump.sql>}"
docker compose -f deploy/docker-compose.yml exec -T postgres \
  psql -U reporting -d reporting < "$1"
echo "restored from $1"
