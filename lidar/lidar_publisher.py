"""
lidar_publisher.py
RPLIDAR A1M8 -> MQTT publisher service for OSCAR robot.
Publishes scan data to robot/lidar/scan and health to robot/lidar/health.
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Optional

import paho.mqtt.client as mqtt
from rplidar import RPLidar, RPLidarException

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------
LIDAR_PORT      = os.getenv("LIDAR_PORT", "/dev/rplidar")
LIDAR_BAUDRATE  = int(os.getenv("LIDAR_BAUDRATE", "115200"))
MQTT_HOST       = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT       = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_SCAN = os.getenv("MQTT_TOPIC_SCAN", "robot/lidar/scan")
MQTT_TOPIC_HEALTH = os.getenv("MQTT_TOPIC_HEALTH", "robot/lidar/health")
SCAN_MODE       = os.getenv("LIDAR_SCAN_MODE", "normal")
PUBLISH_HZ      = float(os.getenv("LIDAR_PUBLISH_HZ", "5"))
MIN_QUALITY     = int(os.getenv("LIDAR_MIN_QUALITY", "10"))
HEALTH_INTERVAL = int(os.getenv("LIDAR_HEALTH_INTERVAL", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lidar_publisher")

# ---------------------------------------------------------------------------
# MQTT helpers
# ---------------------------------------------------------------------------
def build_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(client_id="oscar_lidar", clean_session=True)
    client.will_set(MQTT_TOPIC_HEALTH, json.dumps({"status": "offline"}), retain=True)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            log.info("MQTT connected to %s:%d", MQTT_HOST, MQTT_PORT)
            client.publish(MQTT_TOPIC_HEALTH, json.dumps({"status": "online"}), retain=True)
        else:
            log.warning("MQTT connect failed, rc=%d", rc)

    def on_disconnect(client, userdata, rc):
        log.warning("MQTT disconnected, rc=%d", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


def mqtt_connect_with_retry(client: mqtt.Client, retries: int = 10, delay: float = 3.0):
    for attempt in range(1, retries + 1):
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            time.sleep(0.5)
            return
        except Exception as exc:
            log.warning("MQTT connect attempt %d/%d failed: %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")


# ---------------------------------------------------------------------------
# LIDAR helpers
# ---------------------------------------------------------------------------
def lidar_connect_with_retry(retries: int = 10, delay: float = 3.0) -> RPLidar:
    for attempt in range(1, retries + 1):
        try:
            lidar = RPLidar(LIDAR_PORT, baudrate=LIDAR_BAUDRATE)
            info = lidar.get_info()
            log.info("LIDAR connected: %s", info)
            health = lidar.get_health()
            log.info("LIDAR health: %s", health)
            return lidar
        except Exception as exc:
            log.warning("LIDAR connect attempt %d/%d failed: %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to RPLIDAR on {LIDAR_PORT}")


def publish_health(client: mqtt.Client, lidar: RPLidar):
    try:
        status, error_code = lidar.get_health()
        payload = {
            "timestamp": time.time(),
            "status": status,
            "error_code": error_code,
        }
        client.publish(MQTT_TOPIC_HEALTH, json.dumps(payload), retain=True)
    except Exception as exc:
        log.warning("Health check failed: %s", exc)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run():
    log.info("Starting LIDAR publisher — port=%s mode=%s", LIDAR_PORT, SCAN_MODE)

    running = True
    def _shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received.")
        running = False
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    mqtt_client = build_mqtt_client()
    mqtt_connect_with_retry(mqtt_client)

    lidar: Optional[RPLidar] = None
    min_interval = 1.0 / PUBLISH_HZ
    last_publish  = 0.0
    last_health   = time.time()  # defer first health check by HEALTH_INTERVAL

    while running:
        try:
            if lidar is None:
                lidar = lidar_connect_with_retry()

            if SCAN_MODE == "express":
                scan_iter = lidar.iter_scans(scan_type="express")
            else:
                scan_iter = lidar.iter_scans()

            for scan in scan_iter:
                if not running:
                    break

                now = time.time()

                # Health check: stop scanning, query, then fully reconnect
                if now - last_health >= HEALTH_INTERVAL:
                    try:
                        lidar.stop()
                        publish_health(mqtt_client, lidar)
                    finally:
                        try:
                            lidar.disconnect()
                        except Exception:
                            pass
                        lidar = None
                    last_health = now
                    break  # outer while loop will do a fresh lidar_connect_with_retry()

                if now - last_publish < min_interval:
                    continue

                points = [
                    {"a": round(m[1], 2), "d": round(m[2], 1), "q": m[0]}
                    for m in scan
                    if (m[0] is None or m[0] >= MIN_QUALITY) and m[2] > 0
                ]

                if points:
                    payload = json.dumps({
                        "ts": round(now, 3),
                        "n": len(points),
                        "pts": points,
                    })
                    mqtt_client.publish(MQTT_TOPIC_SCAN, payload)
                    last_publish = now

        except RPLidarException as exc:
            log.error("LIDAR error: %s — reconnecting in 5s", exc)
            if lidar:
                try:
                    lidar.stop()
                    lidar.disconnect()
                except Exception:
                    pass
            lidar = None
            time.sleep(5)

        except Exception as exc:
            log.exception("Unexpected error: %s", exc)
            time.sleep(5)

    log.info("Shutting down...")
    if lidar:
        try:
            lidar.stop()
            lidar.disconnect()
        except Exception:
            pass
    mqtt_client.publish(MQTT_TOPIC_HEALTH, json.dumps({"status": "offline"}), retain=True)
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    log.info("LIDAR publisher stopped.")


if __name__ == "__main__":
    run()
