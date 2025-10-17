#!/usr/bin/env bash
set -Eeuo pipefail

ok(){ printf "\033[1;32m[ OK ]\033[0m %s\n" "$*"; }
warn(){ printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err(){ printf "\033[1;31m[FAIL]\033[0m %s\n" "$*"; }

# 1) Docker
if docker ps >/dev/null 2>&1; then ok "Docker daemon reachable"; else err "Docker not reachable"; exit 1; fi

# 2) Containers
need=(mosquitto wyoming-piper wyoming-whisper video-dashboard ros-core usb-cam web-video-server)
missing=()
for n in "${need[@]}"; do
  if ! docker ps --format '{{.Names}}' | grep -qx "$n"; then missing+=("$n"); fi
done
if [ "${#missing[@]}" -gt 0 ]; then err "Missing containers: ${missing[*]}"; docker ps; fi

# 3) Ports
ports=(1883 10200 10300 8080 8081)
for p in "${ports[@]}"; do
  if ss -ltn "( sport = :$p )" | grep -q ":$p"; then ok "Port $p is listening"; else err "Port $p is NOT listening"; fi
done

# 4) HTTP checks
curl -fsS "http://127.0.0.1:8081/" >/dev/null && ok "Dashboard on 8081" || err "Dashboard 8081 not responding"
curl -fsS "http://127.0.0.1:8080/" >/dev/null && ok "web_video_server on 8080" || warn "web_video_server 8080 not yet responding"

# 5) MQTT probe
if command -v nc >/dev/null && nc -z 127.0.0.1 1883; then ok "Mosquitto reachable on 1883"; else warn "MQTT probe inconclusive"; fi

# 6) ROS topic
if docker ps --format '{{.Names}}' | grep -qx usb-cam; then
  if docker exec usb-cam bash -lc "source /opt/ros/iron/setup.bash && ros2 topic list" | grep -q "/image_raw"; then
    ok "ROS camera topic /image_raw present"
  else
    warn "No /image_raw yet; topics:"; docker exec usb-cam bash -lc "source /opt/ros/iron/setup.bash && ros2 topic list || true"
  fi
fi

# 7) Piper/Whisper ports
for p in 10200 10300; do
  if command -v nc >/dev/null && nc -z 127.0.0.1 "$p"; then ok "Service on $p listening"; else warn "Service on $p not detected yet"; fi
done

echo; ok "Sanity checks complete."
