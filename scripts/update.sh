#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --rebase || true
docker compose -f compose/docker-compose.core.yml build
docker compose -f compose/docker-compose.core.yml up -d
