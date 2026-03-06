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

MQTT_TOPIC_VOICE_CMD = os.environ.get(
    "MQTT_TOPIC_VOICE_CMD", "robot/voice/command"
)
MQTT_TOPIC_MOTION_STATUS = os.environ.get(
    "MQTT_TOPIC_MOTION_STATUS", "robot/motion/status"
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_PREFIX = "[motion_controller] "

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Core helpers
# -----------------------------------------------------------------------------

def normalize_command(cmd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a voice command payload into a motion-friendly structure.

    Expected input example:
      {
        "intent": "move",
        "direction": "forward",
        "duration": 2.0,
        "speed": 0.5,
        ...
      }

    For now, we just sanitize/normalize and pass it through. Later we can map
    to RoboClaw/ROS2 actions here.
    """
    intent = str(cmd.get("intent", "")).lower()
    direction = str(cmd.get("direction", "")).lower()

    # Default safe values
    duration = float(cmd.get("duration", 0.0) or 0.0)
    speed = float(cmd.get("speed", 0.0) or 0.0)

    # Clamp a bit so we don't accidentally do something wild
    if duration < 0.0:
        duration = 0.0
    if duration > 10.0:
        duration = 10.0

    if speed < 0.0:
        speed = 0.0
    if speed > 1.0:
        speed = 1.0

    normalized = {
        "intent": intent,
        "direction": direction,
        "duration": duration,
        "speed": speed,
        # room for future fields
        "raw": cmd,
    }
    return normalized


def simulate_motion_action(command: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder for real motor control / ROS2 integration.

    For now, we just log and return a status dict that we publish on
    MQTT_TOPIC_MOTION_STATUS. Later, this is where we'll:
      - call a RoboClaw driver
      - publish ROS2 Twist messages
      - etc.
    """
    intent = command.get("intent")
    direction = command.get("direction")
    duration = command.get("duration")
    speed = command.get("speed")

    logger.info(
        f"{LOG_PREFIX}Simulating motion: intent={intent}, "
        f"direction={direction}, duration={duration}, speed={speed}"
    )

    # Fake "execution time" bookkeeping for downstream components
    status = {
        "status": "accepted",
        "intent": intent,
        "direction": direction,
        "duration": duration,
        "speed": speed,
        "timestamp": int(time.time()),
        "note": "Simulated motion only (no real motors yet)",
    }
    return status

# -----------------------------------------------------------------------------
# MQTT callbacks
# -----------------------------------------------------------------------------

def on_connect(client, userdata, flags, reason_code, properties=None):
    logger.info(
        f"{LOG_PREFIX}Connected to MQTT at {MQTT_HOST}:{MQTT_PORT} "
        f"(reason_code={reason_code})"
    )
    client.subscribe(MQTT_TOPIC_VOICE_CMD)
    logger.info(
        f"{LOG_PREFIX}Subscribed to {MQTT_TOPIC_VOICE_CMD} for voice commands"
    )


def on_message(client, userdata, msg):
    payload_str = msg.payload.decode("utf-8", "ignore")
    logger.info(f"{LOG_PREFIX}Received on {msg.topic}: {payload_str}")

    if msg.topic != MQTT_TOPIC_VOICE_CMD:
        logger.debug(f"{LOG_PREFIX}Ignoring message on {msg.topic}")
        return

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as e:
        logger.error(f"{LOG_PREFIX}Invalid JSON in voice command: {e}")
        return

    normalized = normalize_command(payload)
    status = simulate_motion_action(normalized)

    # Publish status/ack so other components (dashboard, logs, etc.)
    # can see what happened.
    try:
        client.publish(
            MQTT_TOPIC_MOTION_STATUS,
            json.dumps(status),
            qos=0,
            retain=False,
        )
        logger.info(
            f"{LOG_PREFIX}Published motion status on "
            f"{MQTT_TOPIC_MOTION_STATUS}: {status}"
        )
    except Exception as e:
        logger.exception(
            f"{LOG_PREFIX}Failed to publish motion status: {e}"
        )

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    logger.info(
        f"{LOG_PREFIX}Starting motion_controller; "
        f"MQTT={MQTT_HOST}:{MQTT_PORT}, "
        f"VOICE_CMD_TOPIC={MQTT_TOPIC_VOICE_CMD}, "
        f"MOTION_STATUS_TOPIC={MQTT_TOPIC_MOTION_STATUS}"
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
