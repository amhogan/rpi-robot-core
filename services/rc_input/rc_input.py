#!/usr/bin/env python3
"""
OSCAR rc_input service — lgpio edition
Reads PWM signals from FS-iA6 receiver via lgpio (RPi 5 native, no daemon needed)
and publishes control commands to MQTT.

GPIO Mapping:
  GPIO17 (Pin 11) -> CH1 Steering  (right stick horizontal)
  GPIO27 (Pin 13) -> CH2 Throttle  (right stick vertical)
  GPIO22 (Pin 15) -> CH5 Override  (SwA switch)

MQTT Topics Published:
  oscar/control/rc    -> {steering, throttle, ch1_raw, ch2_raw, ch5_raw, timestamp}
  oscar/control/mode  -> "rc" | "auto"
"""

import lgpio
import paho.mqtt.client as mqtt
import json
import time
import logging
import os
import signal
import sys

# ── Configuration ─────────────────────────────────────────────────────────────
GPIO_CH1_STEER    = int(os.getenv("GPIO_CH1", "17"))
GPIO_CH2_THROTTLE = int(os.getenv("GPIO_CH2", "27"))
GPIO_CH5_OVERRIDE = int(os.getenv("GPIO_CH5", "22"))

MQTT_BROKER     = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT       = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_RC   = os.getenv("MQTT_TOPIC_RC",   "oscar/control/rc")
MQTT_TOPIC_MODE = os.getenv("MQTT_TOPIC_MODE", "oscar/control/mode")

PWM_MIN    = int(os.getenv("PWM_MIN",    "1000"))
PWM_CENTER = int(os.getenv("PWM_CENTER", "1500"))
PWM_MAX    = int(os.getenv("PWM_MAX",    "2000"))

SIGNAL_TIMEOUT     = float(os.getenv("SIGNAL_TIMEOUT",     "0.5"))
PUBLISH_INTERVAL   = float(os.getenv("PUBLISH_INTERVAL",   "0.05"))   # 20 Hz
OVERRIDE_THRESHOLD = int(os.getenv("OVERRIDE_THRESHOLD",   "1700"))
DEADBAND           = int(os.getenv("DEADBAND",             "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rc_input] %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)


# ── PWM Reader ────────────────────────────────────────────────────────────────
class PWMReader:
    """
    Measures PWM pulse width on a GPIO pin using lgpio edge alerts.
    lgpio reports timestamps in nanoseconds.
    """

    def __init__(self, handle, gpio):
        self.handle = handle
        self.gpio = gpio
        self._pulse_width = PWM_CENTER
        self._rise_ns = None
        self._last_seen = 0.0

        # Set as input, no pull (external signal drives it)
        lgpio.gpio_claim_alert(handle, gpio, lgpio.BOTH_EDGES)
        lgpio.callback(handle, gpio, lgpio.BOTH_EDGES, self._edge)

    def _edge(self, chip, gpio, level, timestamp_ns):
        if level == 1:
            self._rise_ns = timestamp_ns
        elif level == 0 and self._rise_ns is not None:
            pw_us = (timestamp_ns - self._rise_ns) / 1000  # ns → µs
            if PWM_MIN - 100 <= pw_us <= PWM_MAX + 100:
                self._pulse_width = int(pw_us)
                self._last_seen = time.monotonic()

    @property
    def pulse_width(self):
        return self._pulse_width

    @property
    def is_alive(self):
        return (time.monotonic() - self._last_seen) < SIGNAL_TIMEOUT


def normalize(pw):
    """Map pulse width to [-1.0, +1.0] with center deadband."""
    if abs(pw - PWM_CENTER) <= DEADBAND:
        return 0.0
    if pw < PWM_CENTER:
        return (pw - PWM_CENTER) / float(PWM_CENTER - PWM_MIN)
    else:
        return (pw - PWM_CENTER) / float(PWM_MAX - PWM_CENTER)


# ── MQTT ──────────────────────────────────────────────────────────────────────
def build_mqtt_client():
    client = mqtt.Client(client_id="rc_input", clean_session=True)
    client.on_connect = lambda c, u, f, rc: log.info(f"MQTT connected (rc={rc})")
    client.on_disconnect = lambda c, u, rc: log.warning(f"MQTT disconnected (rc={rc})")
    return client


def mqtt_connect(client):
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
            client.loop_start()
            return
        except Exception as e:
            log.warning(f"MQTT connect failed ({e}), retrying in 2s...")
            time.sleep(2)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("Starting rc_input service (lgpio)")
    log.info(f"  GPIO CH1={GPIO_CH1_STEER}, CH2={GPIO_CH2_THROTTLE}, CH5={GPIO_CH5_OVERRIDE}")
    log.info(f"  MQTT {MQTT_BROKER}:{MQTT_PORT}")

    # Open GPIO chip (chip 0 on RPi 5)
    handle = lgpio.gpiochip_open(0)

    ch1 = PWMReader(handle, GPIO_CH1_STEER)
    ch2 = PWMReader(handle, GPIO_CH2_THROTTLE)
    ch5 = PWMReader(handle, GPIO_CH5_OVERRIDE)

    mqtt_client = build_mqtt_client()
    mqtt_connect(mqtt_client)

    current_mode = None

    def publish_mode(mode):
        nonlocal current_mode
        if mode != current_mode:
            mqtt_client.publish(MQTT_TOPIC_MODE, mode, qos=1, retain=True)
            log.info(f"Mode -> {mode}")
            current_mode = mode

    def shutdown(sig, frame):
        log.info("Shutting down rc_input")
        lgpio.gpiochip_close(handle)
        publish_mode("auto")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    last_publish = 0.0
    log.info("rc_input running — waiting for RC signal...")

    while True:
        now = time.monotonic()
        signal_present = ch1.is_alive and ch2.is_alive
        override_active = signal_present and ch5.pulse_width > OVERRIDE_THRESHOLD

        if override_active:
            publish_mode("rc")
        else:
            publish_mode("auto")

        if signal_present and override_active and (now - last_publish) >= PUBLISH_INTERVAL:
            payload = json.dumps({
                "steering":  round(normalize(ch1.pulse_width), 3),
                "throttle":  round(normalize(ch2.pulse_width), 3),
                "ch1_raw":   ch1.pulse_width,
                "ch2_raw":   ch2.pulse_width,
                "ch5_raw":   ch5.pulse_width,
                "timestamp": time.time()
            })
            mqtt_client.publish(MQTT_TOPIC_RC, payload, qos=0)
            last_publish = now

        time.sleep(0.01)


if __name__ == "__main__":
    main()
