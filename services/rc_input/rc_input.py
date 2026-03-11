#!/usr/bin/env python3
"""
OSCAR rc_input service
Reads PWM signals from FS-iA6 receiver via pigpio and publishes
control commands to MQTT topics.

GPIO Mapping:
  GPIO17 (Pin 11) -> CH1 Steering  (right stick horizontal)
  GPIO27 (Pin 13) -> CH2 Throttle  (right stick vertical)
  GPIO22 (Pin 15) -> CH5 Override  (SwA switch)

MQTT Topics Published:
  oscar/control/rc    -> {steering, throttle, timestamp}
  oscar/control/mode  -> "rc" | "auto"
"""

import pigpio
import paho.mqtt.client as mqtt
import json
import time
import logging
import os
import signal
import sys

# ── Configuration ────────────────────────────────────────────────────────────
GPIO_CH1_STEER    = int(os.getenv("GPIO_CH1", "17"))   # Steering
GPIO_CH2_THROTTLE = int(os.getenv("GPIO_CH2", "27"))   # Throttle
GPIO_CH5_OVERRIDE = int(os.getenv("GPIO_CH5", "22"))   # RC Override switch

MQTT_BROKER   = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_RC   = os.getenv("MQTT_TOPIC_RC",   "oscar/control/rc")
MQTT_TOPIC_MODE = os.getenv("MQTT_TOPIC_MODE", "oscar/control/mode")

# PWM pulse width bounds from FS-i6 transmitter (microseconds)
PWM_MIN    = int(os.getenv("PWM_MIN",    "1000"))
PWM_CENTER = int(os.getenv("PWM_CENTER", "1500"))
PWM_MAX    = int(os.getenv("PWM_MAX",    "2000"))

# How long with no valid pulse before we consider signal lost (seconds)
SIGNAL_TIMEOUT = float(os.getenv("SIGNAL_TIMEOUT", "0.5"))

# Publish rate cap (seconds) - don't flood MQTT
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "0.05"))  # 20 Hz

# Override active when CH5 pulse > this threshold
OVERRIDE_THRESHOLD = int(os.getenv("OVERRIDE_THRESHOLD", "1700"))

# Deadband around center to treat as zero (microseconds)
DEADBAND = int(os.getenv("DEADBAND", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rc_input] %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)


# ── PWM Reader ────────────────────────────────────────────────────────────────
class PWMReader:
    """Reads a single PWM channel using pigpio edge callbacks."""

    def __init__(self, pi, gpio):
        self.pi = pi
        self.gpio = gpio
        self._pulse_width = PWM_CENTER  # default to center
        self._last_tick = None
        self._last_seen = 0.0
        self._cb = pi.callback(gpio, pigpio.EITHER_EDGE, self._edge)

    def _edge(self, gpio, level, tick):
        if level == 1:
            # Rising edge — record start tick
            self._last_tick = tick
        elif level == 0 and self._last_tick is not None:
            # Falling edge — calculate pulse width
            pw = pigpio.tickDiff(self._last_tick, tick)
            if PWM_MIN - 100 <= pw <= PWM_MAX + 100:   # sanity check
                self._pulse_width = pw
                self._last_seen = time.monotonic()

    @property
    def pulse_width(self):
        return self._pulse_width

    @property
    def is_alive(self):
        return (time.monotonic() - self._last_seen) < SIGNAL_TIMEOUT

    def cancel(self):
        self._cb.cancel()


def normalize(pw, deadband=DEADBAND):
    """Map pulse width to [-1.0, +1.0], with center deadband."""
    center = PWM_CENTER
    if abs(pw - center) <= deadband:
        return 0.0
    if pw < center:
        return (pw - center) / float(center - PWM_MIN)
    else:
        return (pw - center) / float(PWM_MAX - center)


# ── MQTT ──────────────────────────────────────────────────────────────────────
def build_mqtt_client():
    client = mqtt.Client(client_id="rc_input", clean_session=True)
    client.on_connect = lambda c, u, f, rc: log.info(
        f"MQTT connected (rc={rc})"
    )
    client.on_disconnect = lambda c, u, rc: log.warning(
        f"MQTT disconnected (rc={rc}), will retry"
    )
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
    log.info("Starting rc_input service")
    log.info(f"  GPIO CH1={GPIO_CH1_STEER}, CH2={GPIO_CH2_THROTTLE}, CH5={GPIO_CH5_OVERRIDE}")
    log.info(f"  MQTT {MQTT_BROKER}:{MQTT_PORT}")

    # Connect to pigpiod daemon
    pi = pigpio.pi()
    if not pi.connected:
        log.error("Cannot connect to pigpiod — is the daemon running?")
        sys.exit(1)

    # Set GPIO as inputs
    for gpio in (GPIO_CH1_STEER, GPIO_CH2_THROTTLE, GPIO_CH5_OVERRIDE):
        pi.set_mode(gpio, pigpio.INPUT)
        pi.set_pull_up_down(gpio, pigpio.PUD_DOWN)

    # Set up PWM readers
    ch1 = PWMReader(pi, GPIO_CH1_STEER)
    ch2 = PWMReader(pi, GPIO_CH2_THROTTLE)
    ch5 = PWMReader(pi, GPIO_CH5_OVERRIDE)

    # Connect MQTT
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
        ch1.cancel()
        ch2.cancel()
        ch5.cancel()
        pi.stop()
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

        # Determine mode from CH5 override switch
        override_active = (
            signal_present and ch5.pulse_width > OVERRIDE_THRESHOLD
        )

        if override_active:
            publish_mode("rc")
        else:
            publish_mode("auto")

        # Publish RC commands at rate cap
        if signal_present and override_active and (now - last_publish) >= PUBLISH_INTERVAL:
            steering = normalize(ch1.pulse_width)
            throttle = normalize(ch2.pulse_width)

            payload = json.dumps({
                "steering":  round(steering, 3),
                "throttle":  round(throttle, 3),
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
