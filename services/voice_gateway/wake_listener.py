#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Wake listener: streams mic ? Wyoming OpenWakeWord, and on detection:
  1) publishes the wake info to MQTT (robot/wake/detected)
  2) plays a short 'listening' beep
  3) publishes robot/stt/capture <seconds> to kick off STT
  4) temporarily releases the mic for STT, then resumes streaming

This avoids mic contention (arecord in wake listener vs arecord in STT).
"""

import os
import time
import json
import shlex
import signal
import asyncio
import threading
import subprocess
from contextlib import suppress

import paho.mqtt.client as mqtt
from wyoming.client import AsyncClient
from wyoming.audio import AudioStart, AudioChunk, AudioStop

# ---------- env helpers (inline comments allowed like FOO=123 # note) ----------
def _clean_env(name, default):
    val = os.environ.get(name, str(default))
    return val.split("#", 1)[0].strip()

def env_int(name, default):   return int(float(_clean_env(name, default)))
def env_str(name, default):   return _clean_env(name, default)

# ---------- config ----------
BASE              = env_str("MQTT_BASE", "robot")
MQTT_HOST         = env_str("MQTT_HOST", "127.0.0.1")
MQTT_PORT         = env_int("MQTT_PORT", 1883)
MQTT_CID          = env_str("MQTT_CLIENT_ID", "robot-wake-listener")

TOPIC_WAKE        = f"{BASE}/wake/detected"
TOPIC_STT_CAPTURE = f"{BASE}/stt/capture"

# Mic capture format (keep in sync with OpenWakeWord model expectations)
RATE              = env_int("AUDIO_RATE", 16000)
CH                = env_int("AUDIO_CH", 1)
SW                = env_int("AUDIO_WIDTH_BYTES", 2)  # 2 bytes = S16_LE

AREC_DEV          = env_str("ARECORD_DEVICE", "")     # e.g. "plughw:0,0" or empty for default
AREC_EXTRA        = env_str("ARECORD_EXTRA", "")      # optional flags

# Where the Wyoming OpenWakeWord server is
WY_WAKE_URI       = env_str("WY_WAKE_URI", "tcp://127.0.0.1:10400")

# How long to record after wake (seconds)
CAPTURE_SECS      = env_int("STT_SECONDS_DEFAULT", 3)

# Beep script (created earlier)
BEEP_PATH         = env_str("WAKE_BEEP_PATH", "/home/pi/robot-project/services/voice_gateway/sfx_beep.py")
APLAY_DEVICE      = env_str("APLAY_DEVICE", "plughw:0,0")  # used by beep

# Chunk ~100 ms @ 16 kHz mono s16le
CHUNK_BYTES       = 3200

# Cooldown to avoid rapid-fire re-triggers (seconds)
WAKE_COOLDOWN     = env_int("WAKE_COOLDOWN_SECS", 1)

# ---------- tiny logger ----------
def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)

# ---------- MQTT ----------
_mqtt = None
def mqtt_connect():
    global _mqtt
    c = mqtt.Client(client_id=MQTT_CID, clean_session=True, protocol=mqtt.MQTTv311, transport="tcp")
    c.connect(MQTT_HOST, MQTT_PORT, 60)
    c.loop_start()
    _mqtt = c
    log(f"[wake] MQTT connected rc=0; publishing to {TOPIC_WAKE} and {TOPIC_STT_CAPTURE}")

def mqtt_publish(topic, payload, qos=0, retain=False):
    if _mqtt is None:
        return
    _mqtt.publish(topic, payload, qos=qos, retain=retain)

# ---------- beep ----------
def play_beep_async():
    try:
        subprocess.Popen(
            [BEEP_PATH],
            env=dict(os.environ, APLAY_DEVICE=APLAY_DEVICE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log("[wake] beep failed:", repr(e))

# ---------- arecord helpers ----------
async def spawn_arecord():
    cmd = f"arecord -q -f S16_LE -r {RATE} -c {CH} -t raw -"
    if AREC_DEV:
        cmd = f"arecord -q -D {shlex.quote(AREC_DEV)} -f S16_LE -r {RATE} -c {CH} -t raw -"
    if AREC_EXTRA:
        cmd = cmd.replace("arecord ", f"arecord {AREC_EXTRA} ")
    log("[wake] starting capture:", cmd)
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc

async def stop_arecord(proc):
    if proc and proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                proc.kill()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=1.0)

# ---------- main wake loop ----------
async def stream_and_listen():
    client = AsyncClient.from_uri(WY_WAKE_URI)
    await client.connect()
    await client.write_event(AudioStart(rate=RATE, width=SW, channels=CH).event())

    proc = await spawn_arecord()
    last_wake_ts = 0.0

    async def pump_current_proc(p):
        """Read from the given arecord proc and forward to OWW until EOF."""
        while True:
            chunk = await p.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            await client.write_event(AudioChunk(rate=RATE, width=SW, channels=CH, audio=chunk).event())

    # Start initial pump
    pump_task = asyncio.create_task(pump_current_proc(proc))

    try:
        while True:
            evt = await client.read_event()
            if evt is None:
                break

            et = getattr(evt, "type", None)
            data = getattr(evt, "data", {}) or {}

            if et == "wake":
                now = time.time()
                if now - last_wake_ts < WAKE_COOLDOWN:
                    continue
                last_wake_ts = now

                payload = json.dumps({
                    "name": data.get("name"),
                    "probability": data.get("probability"),
                    "timestamp": data.get("timestamp"),
                })
                log("[wake] detected:", payload)
                mqtt_publish(TOPIC_WAKE, payload, qos=0, retain=False)

                # Beep right away
                play_beep_async()

                # IMPORTANT: release the mic so STT can open it
                log(f"[wake] pausing mic for {CAPTURE_SECS}s for STT")
                pump_task.cancel()
                with suppress(asyncio.CancelledError):
                    await pump_task
                await stop_arecord(proc)

                # Trigger STT (voice gateway will start its own arecord)
                mqtt_publish(TOPIC_STT_CAPTURE, str(CAPTURE_SECS), qos=0, retain=False)

                # Wait for STT window to finish, then resume streaming to OWW
                await asyncio.sleep(CAPTURE_SECS + 0.2)

                # Respawn arecord and restart pump
                proc = await spawn_arecord()
                pump_task = asyncio.create_task(pump_current_proc(proc))

    finally:
        # Clean up
        if pump_task:
            pump_task.cancel()
            with suppress(asyncio.CancelledError):
                await pump_task
        await stop_arecord(proc)

        # Drain arecord stderr for hints
        if proc:
            try:
                _, err = await asyncio.wait_for(proc.communicate(), timeout=0.5)
                err = (err or b"").decode(errors="ignore").strip()
                if err:
                    log("[wake] arecord stderr:", err)
            except Exception:
                pass

        await client.disconnect()

async def main_async():
    mqtt_connect()
    # simple restart loop
    while True:
        try:
            await stream_and_listen()
        except Exception as e:
            log("[wake] error:", repr(e))
        await asyncio.sleep(0.5)

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop_evt = threading.Event()
    def _sig(*_): stop_evt.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    t = threading.Thread(target=lambda: loop.run_until_complete(main_async()), daemon=True)
    t.start()

    while not stop_evt.is_set():
        time.sleep(0.25)

    log("[wake] exiting.")

if __name__ == "__main__":
    main()
