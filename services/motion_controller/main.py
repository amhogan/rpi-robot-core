import os
import json
import logging
import sys
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

MQTT_TOPIC_VOICE_CMD   = os.environ.get("MQTT_TOPIC_VOICE_CMD",   "robot/voice/command")
MQTT_TOPIC_MOTION_CMD  = os.environ.get("MQTT_TOPIC_MOTION_CMD",  "robot/motion/command")
MQTT_TOPIC_SAFETY_STOP = os.environ.get("MQTT_TOPIC_SAFETY_STOP", "robot/safety/stop")

LOG_LEVEL  = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_PREFIX = "[motion_controller] "

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

VALID_DIRECTIONS = {"forward", "backward", "left", "right", "stop"}

# -----------------------------------------------------------------------------
# Safety clamping
# -----------------------------------------------------------------------------

def normalize_command(cmd: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Validate and clamp a voice command. Returns None if the command is invalid
    and a stop should be issued instead.
    """
    direction = str(cmd.get("direction", "")).lower()
    if direction not in VALID_DIRECTIONS:
        logger.error(f"{LOG_PREFIX}Invalid direction '{direction}' — issuing stop")
        return None

    duration = float(cmd.get("duration", 0.0) or 0.0)
    speed    = float(cmd.get("speed",    0.0) or 0.0)

    duration = max(0.0, min(10.0, duration))
    speed    = max(0.0, min(1.0,  speed))

    return {"direction": direction, "duration": duration, "speed": speed}


def stop_payload() -> str:
    return json.dumps({"direction": "stop", "speed": 0.0, "duration": 0.0})

# -----------------------------------------------------------------------------
# MQTT callbacks
# -----------------------------------------------------------------------------

_mqtt_client = None


def on_connect(client, userdata, flags, reason_code, properties=None):
    logger.info(
        f"{LOG_PREFIX}Connected to MQTT at {MQTT_HOST}:{MQTT_PORT} "
        f"(reason_code={reason_code})"
    )
    client.subscribe(MQTT_TOPIC_VOICE_CMD)
    client.subscribe(MQTT_TOPIC_SAFETY_STOP)
    logger.info(
        f"{LOG_PREFIX}Subscribed to {MQTT_TOPIC_VOICE_CMD} and {MQTT_TOPIC_SAFETY_STOP}"
    )


def on_message(client, userdata, msg):
    payload_str = msg.payload.decode("utf-8", "ignore")
    logger.info(f"{LOG_PREFIX}Received on {msg.topic}: {payload_str}")

    if msg.topic == MQTT_TOPIC_SAFETY_STOP:
        try:
            data = json.loads(payload_str)
            reason = data.get("reason", "unknown")
        except Exception:
            reason = payload_str or "unknown"
        logger.warning(f"{LOG_PREFIX}SAFETY STOP received — reason: {reason}")
        client.publish(MQTT_TOPIC_MOTION_CMD, stop_payload(), qos=1)
        return

    if msg.topic != MQTT_TOPIC_VOICE_CMD:
        return

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as e:
        logger.error(f"{LOG_PREFIX}Invalid JSON in voice command: {e} — issuing stop")
        client.publish(MQTT_TOPIC_MOTION_CMD, stop_payload(), qos=1)
        return

    normalized = normalize_command(payload)
    if normalized is None:
        client.publish(MQTT_TOPIC_MOTION_CMD, stop_payload(), qos=1)
        return

    out = json.dumps(normalized)
    logger.info(f"{LOG_PREFIX}Forwarding to {MQTT_TOPIC_MOTION_CMD}: {out}")
    client.publish(MQTT_TOPIC_MOTION_CMD, out, qos=1)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    logger.info(
        f"{LOG_PREFIX}Starting motion_controller; "
        f"MQTT={MQTT_HOST}:{MQTT_PORT}, "
        f"voice_cmd={MQTT_TOPIC_VOICE_CMD}, "
        f"motion_cmd={MQTT_TOPIC_MOTION_CMD}, "
        f"safety_stop={MQTT_TOPIC_SAFETY_STOP}"
    )

    client = mqtt.Client(
        client_id="rpi-robot-motion-controller",
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
