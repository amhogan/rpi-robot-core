#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, asyncio, time, shlex, threading, signal, io, wave, subprocess, audioop
import paho.mqtt.client as mqtt

from wyoming.client import AsyncClient, AsyncTcpClient
from wyoming.event import Event
from wyoming.audio import AudioStart, AudioChunk, AudioStop

# -------- env helpers (allow inline comments like FOO=123 # note) --------
def _clean_env(name, default):
    val = os.environ.get(name, str(default))
    return val.split('#', 1)[0].strip()

def env_int(name, default):   return int(float(_clean_env(name, default)))
def env_float(name, default): return float(_clean_env(name, default))
def env_str(name, default):   return _clean_env(name, default)

# -------- config --------
BASE             = env_str("MQTT_BASE", "robot")
MQTT_HOST        = env_str("MQTT_HOST", "127.0.0.1")
MQTT_PORT        = env_int("MQTT_PORT", 1883)
MQTT_CID         = env_str("MQTT_CLIENT_ID", "voice-gateway")

TOPIC_TTS_SAY    = f"{BASE}/tts/say"
TOPIC_STT_CAP    = f"{BASE}/stt/capture"
TOPIC_STT_TEXT   = f"{BASE}/stt/text"
TOPIC_WAKE       = f"{BASE}/wake/detected"

# audio defaults for STT capture
RATE             = env_int("AUDIO_RATE", 16000)
CH               = env_int("AUDIO_CH", 1)
SW               = env_int("AUDIO_WIDTH_BYTES", 2)  # S16_LE -> 2 bytes
STT_SECS_DEFAULT = env_int("STT_SECONDS_DEFAULT", 3)

AREC_DEV         = env_str("ARECORD_DEVICE", "")
APLAY_DEV        = env_str("APLAY_DEVICE", "plughw:0,0")  # default to Jabra

WY_TTS_URI       = env_str("WY_TTS_URI", "tcp://127.0.0.1:10200")
WY_STT_URI       = env_str("WY_STT_URI", "tcp://127.0.0.1:10300")

# Direct TCP host/port for Piper (Wyoming)
WY_TTS_HOST      = env_str("WY_TTS_HOST", "127.0.0.1")
WY_TTS_PORT      = env_int("WY_TTS_PORT", 10200)

# chunking for arecord->STT
CHUNK = 3200  # ~100ms @ 16k mono s16le

# -------- logging --------
def log(*a, **k):
    print(time.strftime("[%H:%M:%S]"), *a, **k, flush=True)

# -------- background asyncio loop --------
loop = asyncio.new_event_loop()
def _runner():
    asyncio.set_event_loop(loop)
    loop.run_forever()
threading.Thread(target=_runner, daemon=True).start()

# -------- TTS: synth with Piper, convert to 48k WAV, play via aplay --------
def tts_play_48k(text: str) -> None:
    if not text:
        return
    log("TTS:", text)

    async def _synth() -> bytes | None:
        client = AsyncTcpClient(WY_TTS_HOST, WY_TTS_PORT)
        await client.connect()
        await client.write_event(Event(type="synthesize", data={"text": text}))

        fmt = None
        pcm = bytearray()
        while True:
            ev = await client.read_event()
            if ev is None:
                break
            if ev.type == "audio-start":
                fmt = AudioStart.from_event(ev)
            elif ev.type == "audio-chunk":
                chunk = AudioChunk.from_event(ev)
                if chunk is not None:
                    pcm += chunk.audio
            elif ev.type == "audio-stop":
                break

        await client.disconnect()
        if not fmt or not pcm:
            return None

        width    = fmt.width or 2
        channels = fmt.channels or 1
        rate     = fmt.rate or 16000
        data = bytes(pcm)

        if channels == 2:
            data = audioop.tomono(data, width, 0.5, 0.5)
            channels = 1

        if width != 2:
            data = audioop.lin2lin(data, width, 2)
            width = 2

        # resample to 48k to avoid "chipmunk" pitch on your speaker path
        resamp, _ = audioop.ratecv(data, 2, 1, rate, 48000, None)

        bio = io.BytesIO()
        with wave.open(bio, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(resamp)
        return bio.getvalue()

    wav_bytes = asyncio.run(_synth())
    if not wav_bytes:
        log("TTS: no audio returned from Piper.")
        return

    cmd = ["aplay", "-q", "-D", APLAY_DEV, "-t", "wav", "-"]
    log("TTS: playing with:", " ".join(shlex.quote(x) for x in cmd), f"({len(wav_bytes)} bytes)")
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.stdin.write(wav_bytes)
        p.stdin.close()
        p.wait(timeout=15)
    except Exception as e:
        log("TTS: aplay failed:", repr(e))

# -------- STT capture --------
async def stt_once(seconds: int) -> str | None:
    rec_cmd = f"arecord -q -f S16_LE -r {RATE} -c {CH} -d {seconds} -t raw -"
    if AREC_DEV:
        rec_cmd = f"arecord -q -D {shlex.quote(AREC_DEV)} -f S16_LE -r {RATE} -c {CH} -d {seconds} -t raw -"
    log("STT: starting capture:", rec_cmd)

    proc = await asyncio.create_subprocess_exec(
        *shlex.split(rec_cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    c = AsyncClient.from_uri(WY_STT_URI)
    await c.connect()
    await c.write_event(AudioStart(rate=RATE, width=SW, channels=CH).event())

    try:
        while True:
            buf = await asyncio.wait_for(proc.stdout.read(CHUNK), timeout=seconds + 2)
            if not buf:
                break
            await c.write_event(AudioChunk(rate=RATE, width=SW, channels=CH, audio=buf).event())
    except asyncio.TimeoutError:
        log("STT: read timeout from arecord; stopping early.")
    finally:
        await c.write_event(AudioStop().event())

    transcript = None
    deadline = time.time() + max(6, seconds + 3)
    try:
        while time.time() < deadline:
            evt = await asyncio.wait_for(c.read_event(), timeout=deadline - time.time())
            if evt is None:
                break
            et = getattr(evt, "type", None)
            data = getattr(evt, "data", {}) or {}
            if et in ("transcript", "text"):
                transcript = data.get("text") or transcript
                log("STT: got", et, "->", repr(transcript))
                break
    finally:
        await c.disconnect()

    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=2)
        err = (err or b"").decode(errors="ignore").strip()
        if err:
            log("arecord stderr:", err)
    except Exception:
        pass

    code = proc.returncode
    log("STT: arecord exit code", code, "transcript=", repr(transcript))
    return transcript

# -------- MQTT --------
stt_busy = threading.Event()

def on_connect(client, userdata, flags, rc):
    log(f"MQTT connected rc={rc}; subscribing to {TOPIC_TTS_SAY} and {TOPIC_STT_CAP}")
    client.subscribe([(TOPIC_TTS_SAY, 0), (TOPIC_STT_CAP, 0)])

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload  # bytes
    if topic == TOPIC_TTS_SAY:
        text = payload.decode("utf-8", "ignore").strip()
        log("MQTT:", topic, text)
        threading.Thread(target=tts_play_48k, args=(text,), daemon=True).start()
    elif topic == TOPIC_STT_CAP:
        raw = payload.decode("utf-8", "ignore").strip()
        log("MQTT:", topic, raw)
        try:
            secs = int(float(raw)) if raw else STT_SECS_DEFAULT
        except Exception:
            secs = STT_SECS_DEFAULT
        if stt_busy.is_set():
            log("STT: busy; ignoring request.")
            return
        stt_busy.set()
        fut = asyncio.run_coroutine_threadsafe(stt_once(secs), loop)
        def _done(_):
            try:
                txt = fut.result()
            except Exception as e:
                log("STT error:", repr(e))
                txt = None
            if txt:
                out = json.dumps({"text": txt, "secs": secs}, ensure_ascii=False)
                client.publish(TOPIC_STT_TEXT, out, qos=0, retain=False)
            stt_busy.clear()
        fut.add_done_callback(_done)

def main():
    log("Gateway starting.")
    client = mqtt.Client(client_id=MQTT_CID, clean_session=True, userdata=None, protocol=mqtt.MQTTv311, transport="tcp")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    stop = threading.Event()
    def _sig(*_): stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    while not stop.is_set():
        time.sleep(0.5)
    client.loop_stop()
    log("Gateway exiting.")

if __name__ == "__main__":
    main()
