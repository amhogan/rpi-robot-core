#!/usr/bin/env python3
import os
import json
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS
import paho.mqtt.client as mqtt

# MQTT config
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_STATUS = os.getenv("MQTT_TOPIC_STATUS", "robot/motion/status")
MQTT_TOPIC_CMD    = os.getenv("MQTT_TOPIC_CMD", "robot/voice/command")

app = Flask(__name__)
CORS(app)

_latest_status = None
_lock = threading.Lock()
_mqtt_client = None


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        app.logger.info(f"motion_status: Connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_STATUS)
        app.logger.info(f"motion_status: Subscribed to {MQTT_TOPIC_STATUS}")
    else:
        app.logger.error(f"motion_status: MQTT connect failed with code {rc}")


def on_message(client, userdata, msg):
    global _latest_status
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
    except Exception as e:
        app.logger.warning(f"motion_status: Bad payload on {msg.topic}: {e}")
        return

    with _lock:
        _latest_status = data


def mqtt_loop():
    global _mqtt_client
    client = mqtt.Client(
        client_id="motion_status",
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            app.logger.info(f"motion_status: Connecting to MQTT at {MQTT_HOST}:{MQTT_PORT} ...")
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            app.logger.info("motion_status: MQTT connection established.")
            break
        except Exception as e:
            app.logger.error(f"motion_status: MQTT connect failed: {e!r} — retrying in 5 seconds")
            time.sleep(5)

    _mqtt_client = client
    client.loop_forever()


@app.route("/status_motion")
def status_motion():
    with _lock:
        if _latest_status is None:
            # No data yet from MQTT
            return jsonify({"available": False, "reason": "no telemetry yet"}), 503

        data = dict(_latest_status)

    # Try to compute age_sec from timestamp if present
    age_sec = None
    ts_str = data.get("timestamp")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str)
            now = datetime.now(timezone.utc)
            age_sec = (now - ts).total_seconds()
        except Exception:
            pass

    data["age_sec"] = age_sec
    data["available"] = True
    return jsonify(data), 200


@app.route("/command", methods=["POST"])
def command():
    data = request.get_json(force=True, silent=True) or {}
    direction = str(data.get("direction", "stop")).lower()
    intent    = str(data.get("intent",    "stop")).lower()
    speed     = max(0.0, min(1.0, float(data.get("speed",    0.0))))
    duration  = max(0.0, min(10.0, float(data.get("duration", 0.4))))

    with _lock:
        client = _mqtt_client

    if client is None:
        return jsonify({"ok": False, "error": "mqtt not connected"}), 503

    payload = json.dumps({
        "intent": intent, "direction": direction,
        "speed": speed, "duration": duration,
    })
    client.publish(MQTT_TOPIC_CMD, payload, qos=0)
    return jsonify({"ok": True, "command": json.loads(payload)}), 200


def main():
    # Start MQTT thread
    t = threading.Thread(target=mqtt_loop, daemon=True)
    t.start()

    # Start Flask HTTP server
    app.logger.info("motion_status: Starting HTTP server on 0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
