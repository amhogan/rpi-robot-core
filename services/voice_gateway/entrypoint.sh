#!/usr/bin/env bash
set -e
cd /app
if [[ -x "./run.sh" ]]; then
  exec ./run.sh
elif [[ -f "./main.py" ]]; then
  exec python ./main.py
else
  echo "voice_gateway: No run.sh or main.py found in /app. Container will stay up."
  tail -f /dev/null
fi
