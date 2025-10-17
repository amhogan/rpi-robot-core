RPi-Robot Core Docker Stack
===========================

Files:
- compose.core.yml: MQTT + Wyoming voice services on ${ROBOT_NETWORK}
- override.voice.yml: voice env overrides (kept minimal)
- override.site.yml: nginx video dashboard serving ~/src/robot-project/site on ${VIDEO_DASHBOARD_PORT}

Bring-up (from repo root ~/src/rpi-robot-core):
  docker compose -f docker/compose.core.yml -f docker/override.voice.yml -f docker/override.site.yml up -d

Check:
  docker ps
  curl -sSf http://127.0.0.1:${PIPER_PORT:-10200}/ || echo "Piper port ok (no HTTP)"
  nc -vz 127.0.0.1 ${WHISPER_PORT:-10300}
  open http://RPi-Robot:${VIDEO_DASHBOARD_PORT:-8081}/
