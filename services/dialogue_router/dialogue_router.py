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

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MODEL     = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

TOPIC_STT = "robot/stt/text"
TOPIC_TTS = "robot/tts/say"
TOPIC_CMD = "robot/motion/command"

SYSTEM = """\
You are O.S.C.A.R. (Operational Support and Communication Autonomous Robot), \
a friendly and helpful mobile robot that responds to spoken voice commands.

You can:
- Speak responses aloud via text-to-speech
- Move: forward, backward, left, or right

Reply ONLY with a single JSON object — no markdown, no extra text:
{
  "say": "your spoken response (1–2 sentences, conversational and friendly)",
  "motion": {"direction": "forward|backward|left|right", "speed": 0.0–1.0, "duration": 0.5–5.0}
}

Set "motion" to null if no movement is needed.
Speed: 0.5 is comfortable, 1.0 is full speed. Duration is seconds (0.5–5.0 typical).
Keep "say" short — it will be spoken aloud via text-to-speech.
"""

_stop = threading.Event()
_mqtt_client = None
_anthropic = anthropic.Anthropic()


def route(text: str) -> None:
    logging.info(f"Routing: {text!r}")
    try:
        msg = _anthropic.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.warning(f"Non-JSON from Claude: {raw!r}")
        data = {"say": raw, "motion": None}
    except Exception as e:
        logging.error(f"Claude API error: {e}")
        if _mqtt_client:
            _mqtt_client.publish(TOPIC_TTS, "Sorry, I had a problem processing that.")
        return

    say    = (data.get("say") or "").strip()
    motion = data.get("motion")

    if say:
        logging.info(f"TTS → {say!r}")
        _mqtt_client.publish(TOPIC_TTS, say)

    if isinstance(motion, dict):
        direction = motion.get("direction", "")
        if direction in ("forward", "backward", "left", "right"):
            cmd = json.dumps({
                "direction": direction,
                "speed":     float(motion.get("speed", 0.5)),
                "duration":  float(motion.get("duration", 1.0)),
            })
            logging.info(f"Motion → {cmd}")
            _mqtt_client.publish(TOPIC_CMD, cmd)


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
