#!/usr/bin/env bash
set -euo pipefail
PORTS=("127.0.0.1:1883" "127.0.0.1:10400")
TRIES=60
SLEEP=1
for ((i=1; i<=TRIES; i++)); do
  all_up=1
  for hp in "${PORTS[@]}"; do
    host="${hp%:*}"; port="${hp#*:}"
    if ! (echo >/dev/tcp/"$host"/"$port") 2>/dev/null; then
      all_up=0
      break
    fi
  done
  if [[ $all_up -eq 1 ]]; then
    exit 0
  fi
  sleep "$SLEEP"
done
echo "wait_wake_ports: timed out waiting for ${PORTS[*]}" >&2
exit 1
