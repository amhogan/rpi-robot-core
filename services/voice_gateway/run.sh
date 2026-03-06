#!/usr/bin/env bash
set -e
cd /app

cleanup() {
    kill "$MAIN_PID" "$WAKE_PID" 2>/dev/null || true
    wait "$MAIN_PID" "$WAKE_PID" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT EXIT

# TTS/STT gateway
python main.py &
MAIN_PID=$!

# Wake word listener (has its own retry loop)
python wake_listener.py &
WAKE_PID=$!

wait
