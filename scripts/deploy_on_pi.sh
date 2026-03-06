#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="${1:-$HOME/rpi-robot-core}"
BRANCH="${2:-rpi-build-adjustments}"
COMPOSE_FILE="compose/docker-compose.yml"

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
docker ps --filter "name=robot" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# Show a few lines of logs for voice gateway and roboclaw
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=100 voice_gateway | sed -n '1,40p' || true
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=100 roboclaw-driver | sed -n '1,40p' || true

# Verify devices
echo "Host devices:"
ls -l /dev/video* /dev/tty* /dev/snd || true

echo "Deploy finished."
