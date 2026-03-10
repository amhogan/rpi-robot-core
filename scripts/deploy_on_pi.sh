#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="${1:-$HOME/rpi-robot-core}"
BRANCH="${2:-rpi-build-adjustments}"
COMPOSE_FILE="compose/docker-compose.core.yml"

echo "Deploy: repo=${REPO_DIR} branch=${BRANCH}"

cd "$REPO_DIR"

# Ensure we have the branch
git fetch origin
git checkout "$BRANCH"
git pull --rebase origin "$BRANCH"

# Optional: record previous docker state for quick rollback
date > /tmp/deploy-$(date +%s).stamp
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' > /tmp/docker-images-before.txt || true

# Build and bring up
docker compose -f "$COMPOSE_FILE" build --pull
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Give services a bit to start
sleep 2

# Show status for quick verification
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# Show a few lines of logs for key services
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=20 voice_gateway || true
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=20 roboclaw_driver || true

# Verify devices
echo "Host devices:"
ls -l /dev/video* /dev/ttyUSB* /dev/ttyACM* /dev/rplidar /dev/snd || true

echo "Deploy finished."
