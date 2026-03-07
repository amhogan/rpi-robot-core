#!/usr/bin/env python3
import json
import logging
import os
import signal
import threading
import time

import anthropic
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_HOST      = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT      = int(os.getenv("MQTT_PORT", "1883"))
MODEL          = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MEMORY_PATH    = os.getenv("MEMORY_PATH", "/data/oscar_memory.json")
HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "20"))  # max turns kept

TOPIC_STT = "robot/stt/text"
TOPIC_TTS = "robot/tts/say"
TOPIC_CMD = "robot/voice/command"

SYSTEM = """\
You are O.S.C.A.R. (Operational Support and Communication Autonomous Robot), \
a friendly and helpful mobile robot. You operate on a Quantum J4 wheelchair base \
driven by a Raspberry Pi 5 on Drew's property (grass, driveway, ramps). \
You are large and heavy — safety is your top priority.

You can:
- Speak responses aloud via text-to-speech
- Move: forward, backward, left, or right
- Stop on request or when it is safe to do so

Reply ONLY with a single JSON object — no markdown, no extra text:
{
  "say": "your spoken response (1–2 sentences, conversational and friendly)",
  "motion": {"direction": "forward|backward|left|right|stop", "speed": 0.0–1.0, "duration": 0.5–5.0}
}

Set "motion" to null if no movement is needed.
Speed: 0.5 is comfortable, 1.0 is full speed. Duration is seconds (0.5–5.0 typical).
Keep "say" short — it will be spoken aloud via text-to-speech.
Never command motion that could endanger people or property.
"""

_stop        = threading.Event()
_mqtt_client = None
_anthropic   = anthropic.Anthropic()

# Conversation history: list of {"role": "user"|"assistant", "content": str}
# Protected by _history_lock so concurrent route() calls don't corrupt it.
_history      = []
_history_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Persistent memory helpers
# ---------------------------------------------------------------------------

def _load_history() -> None:
    """Load conversation history from disk on startup."""
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _history.extend(data)
            logging.info(f"Loaded {len(_history)} history entries from {MEMORY_PATH}")
    except FileNotFoundError:
        logging.info(f"No history file at {MEMORY_PATH} — starting fresh")
    except Exception as e:
        logging.warning(f"Could not load history: {e} — starting fresh")


def _save_history() -> None:
    """Persist current history window to disk."""
    try:
        os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"Could not save history: {e}")


def _append_and_prune(user_text: str, assistant_text: str) -> None:
    """Append a turn and prune to HISTORY_WINDOW turns (2 messages per turn)."""
    with _history_lock:
        _history.append({"role": "user",      "content": user_text})
        _history.append({"role": "assistant", "content": assistant_text})
        # Prune oldest turns first; each turn = 2 messages
        max_msgs = HISTORY_WINDOW * 2
        while len(_history) > max_msgs:
            _history.pop(0)
            _history.pop(0)
        snapshot = list(_history)
    _save_history()
    logging.info(f"History: {len(snapshot) // 2} turns stored")


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route(text: str) -> None:
    logging.info(f"Routing: {text!r}")

    with _history_lock:
        messages = list(_history) + [{"role": "user", "content": text}]

    try:
        msg = _anthropic.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM,
            messages=messages,
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.warning(f"Non-JSON from Claude: {raw!r}")
        data = {"say": raw, "motion": None}
        raw  = json.dumps(data)
    except Exception as e:
        logging.error(f"Claude API error: {e}")
        if _mqtt_client:
            _mqtt_client.publish(TOPIC_TTS, json.dumps({"text": "Sorry, I had a problem processing that."}))
        return

    # Persist this exchange to rolling history
    _append_and_prune(text, raw)

    say    = (data.get("say") or "").strip()
    motion = data.get("motion")

    if say:
        logging.info(f"TTS → {say!r}")
        _mqtt_client.publish(TOPIC_TTS, json.dumps({"text": say}))

    if isinstance(motion, dict):
        direction = motion.get("direction", "")
        if direction in ("forward", "backward", "left", "right", "stop"):
            cmd = json.dumps({
                "direction": direction,
                "speed":     float(motion.get("speed", 0.5)),
                "duration":  float(motion.get("duration", 1.0)),
            })
            logging.info(f"Motion → {cmd}")
            _mqtt_client.publish(TOPIC_CMD, cmd)


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info(f"MQTT connected to {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_STT)
        logging.info(f"Subscribed to {TOPIC_STT}")
    else:
        logging.error(f"MQTT connect failed rc={rc}")


def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="ignore")
    try:
        text = json.loads(raw).get("text", "").strip()
    except Exception:
        text = raw.strip()
    if text:
        threading.Thread(target=route, args=(text,), daemon=True).start()


def main():
    global _mqtt_client

    _load_history()

    _mqtt_client = mqtt.Client(client_id="dialogue_router", protocol=mqtt.MQTTv5)
    _mqtt_client.on_connect = on_connect
    _mqtt_client.on_message = on_message

    while not _stop.is_set():
        try:
            _mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            logging.error(f"MQTT connect failed: {e!r} — retrying in 5s")
            time.sleep(5)

    _mqtt_client.loop_start()

    def _sig(sig, frame):
        _stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    while not _stop.is_set():
        time.sleep(0.5)

    _mqtt_client.loop_stop()
    logging.info("dialogue_router exiting")


if __name__ == "__main__":
    main()
