import os
import json
import time
import signal
import logging
from threading import Event, Lock, Thread
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import serial
from roboclaw_3 import Roboclaw


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# MQTT config
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_CMD = os.getenv("MQTT_TOPIC_CMD", "robot/motion/command")
MQTT_TOPIC_STATUS = os.getenv("MQTT_TOPIC_STATUS", "robot/motion/status")

# Telemetry config
TELEMETRY_INTERVAL_SEC = float(os.getenv("TELEMETRY_INTERVAL_SEC", "0.5"))

# RoboClaw config
ROBOCLAW_PORT = os.getenv(
    "ROBOCLAW_PORT",
    "/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x30A-if00",
)
ROBOCLAW_BAUD = int(os.getenv("ROBOCLAW_BAUD", "38400"))
ROBOCLAW_ADDRESS = int(os.getenv("ROBOCLAW_ADDRESS", "128"))  # 0x80

stop_event = Event()


class RoboClawDriver:
    def __init__(self):
        self.address = ROBOCLAW_ADDRESS

        # Create the Roboclaw object
        self.rc = Roboclaw(ROBOCLAW_PORT, ROBOCLAW_BAUD)

        # Ensure the underlying serial port exists as self._port
        # Some versions of roboclaw_3.py don't set this up correctly.
        if not hasattr(self.rc, "_port"):
            try:
                logging.info(
                    f"Creating serial port for RoboClaw at "
                    f"{ROBOCLAW_PORT} {ROBOCLAW_BAUD} via pyserial"
                )
                self.rc._port = serial.Serial(
                    ROBOCLAW_PORT,
                    ROBOCLAW_BAUD,
                    timeout=0.01,
                )
            except Exception as e:
                logging.error(f"Failed to create serial port for RoboClaw: {e}")

        # Duty state shared between command() and heartbeat loop.
        # Heartbeat sends DutyM1M2(m1, m2) every 400ms to satisfy the
        # 500ms hardware watchdog even during long motion commands.
        self._duty_lock = Lock()
        self._current_duty = (0, 0)

        self._connect()

    def _connect(self):
        logging.info(f"Opening RoboClaw at {ROBOCLAW_PORT} {ROBOCLAW_BAUD}...")
        # Try the library's Open() if it exists, but don't die if it doesn't work
        try:
            if hasattr(self.rc, "Open"):
                self.rc.Open()
        except Exception as e:
            logging.warning(f"RoboClaw Open() failed (continuing anyway): {e}")

        # Optional: try a simple ping/version read
        try:
            result = self.rc.ReadVersion(self.address)
            # Some libs return (ok, version), some may return just version
            ok = None
            version_raw = None

            if isinstance(result, tuple) and len(result) >= 2:
                ok, version_raw = result[0], result[1]
            else:
                # Assume success and that result is the version
                ok, version_raw = True, result

            if ok:
                if isinstance(version_raw, bytes):
                    version = version_raw.decode("ascii", errors="ignore")
                else:
                    version = str(version_raw)
                logging.info(f"RoboClaw version: {version}")
            else:
                logging.warning("Could not read version from RoboClaw")
        except Exception as e:
            logging.warning(f"Could not read version from RoboClaw: {e}")

        # Configure hardware serial watchdog: cmd 14, value in units of 100ms.
        # Value 5 = 500ms — motors cut if no valid serial command arrives.
        try:
            self.rc._write1(self.address, 14, 5)
            logging.info("RoboClaw serial watchdog set to 500ms")
        except Exception as e:
            logging.warning(f"Could not set RoboClaw watchdog timeout: {e}")

    def stop(self):
        logging.info("Stopping motors (DutyM1M2 0,0)")
        with self._duty_lock:
            self._current_duty = (0, 0)
        try:
            self.rc.DutyM1M2(self.address, 0, 0)
        except Exception as e:
            logging.error(f"Error stopping motors: {e}")

    def command(self, direction: str, speed: float, duration: float):
        """
        direction: 'forward', 'backward', 'left', 'right'
        speed: 0.0–1.0
        duration: seconds
        """
        speed = max(0.0, min(1.0, float(speed)))
        duration = max(0.0, float(duration))

        max_duty = 32767
        duty = int(max_duty * speed)

        m1 = 0
        m2 = 0

        if direction == "stop":
            self.stop()
            return
        elif direction == "forward":
            m1 = duty
            m2 = duty
        elif direction == "backward":
            m1 = -duty
            m2 = -duty
        elif direction == "left":
            m1 = -duty
            m2 = duty
        elif direction == "right":
            m1 = duty
            m2 = -duty
        else:
            logging.warning(f"Unknown direction '{direction}', ignoring")
            return

        logging.info(
            f"Driving RoboClaw: dir={direction} speed={speed} duration={duration}s "
            f"duty(m1,m2)=({m1},{m2})"
        )

        with self._duty_lock:
            self._current_duty = (m1, m2)
        try:
            self.rc.DutyM1M2(self.address, m1, m2)
            if duration > 0:
                time.sleep(duration)
            self.stop()
        except Exception as e:
            logging.error(f"Error while driving RoboClaw: {e}")
            self.stop()

    def read_status(self) -> dict:
        """
        Read key telemetry values from the RoboClaw and return as a dict.
        """
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "main_battery_v": None,
            "logic_battery_v": None,
            "m1_current_a": None,
            "m2_current_a": None,
            "m1_temp_c": None,
            "m2_temp_c": None,
            "error_bits": None,
        }

        # Main battery voltage (V * 10)
        try:
            ok, main_mv = self.rc.ReadMainBatteryVoltage(self.address)
            if ok:
                status["main_battery_v"] = main_mv / 10.0
        except Exception as e:
            logging.warning(f"Error reading main battery voltage: {e}")

        # Logic battery voltage (V * 10)
        try:
            ok, logic_mv = self.rc.ReadLogicBatteryVoltage(self.address)
            if ok:
                status["logic_battery_v"] = logic_mv / 10.0
        except Exception as e:
            logging.warning(f"Error reading logic battery voltage: {e}")

        # Currents (commonly reported as 100 * amps)
        try:
            ok, m1_cur, m2_cur = self.rc.ReadCurrents(self.address)
            if ok:
                status["m1_current_a"] = m1_cur / 100.0
                status["m2_current_a"] = m2_cur / 100.0
        except Exception as e:
            logging.warning(f"Error reading motor currents: {e}")

        # Temps (°C * 10)
        try:
            ok, temp1_tenths = self.rc.ReadTemp(self.address)
            if ok:
                status["m1_temp_c"] = temp1_tenths / 10.0
        except Exception as e:
            logging.warning(f"Error reading temp 1: {e}")

        try:
            # Some RoboClaw libs support ReadTemp2, others don't
            ok, temp2_tenths = self.rc.ReadTemp2(self.address)
            if ok:
                status["m2_temp_c"] = temp2_tenths / 10.0
        except Exception as e:
            # Not fatal; just log at debug level to avoid spam
            logging.debug(f"Error reading temp 2 (may be unsupported): {e}")

        # Error bits
        try:
            ok, error_bits = self.rc.ReadError(self.address)
            if ok:
                status["error_bits"] = error_bits
        except Exception as e:
            logging.warning(f"Error reading error bits: {e}")

        return status


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info(f"Connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_CMD)
        logging.info(f"Subscribed to {MQTT_TOPIC_CMD}")
    else:
        logging.error(f"MQTT connection failed with code {rc}")


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    logging.info(f"MQTT message on {msg.topic}: {payload}")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logging.error("Payload is not valid JSON")
        return

    direction = data.get("direction")
    duration = data.get("duration", 0.0)
    speed = data.get("speed", 0.0)

    if not direction:
        logging.error("Command missing 'direction'")
        return

    driver: RoboClawDriver = userdata["driver"]
    driver.command(direction, speed, duration)


def mqtt_loop(client):
    while not stop_event.is_set():
        client.loop(timeout=1.0)


def heartbeat_loop(driver: RoboClawDriver):
    """
    Send DutyM1M2 every 400ms to satisfy the 500ms hardware watchdog.
    When idle the duty is (0,0); during motion it reflects the active command.
    """
    logging.info("Starting RoboClaw heartbeat loop (400ms interval)")
    while not stop_event.is_set():
        with driver._duty_lock:
            m1, m2 = driver._current_duty
        try:
            driver.rc.DutyM1M2(driver.address, m1, m2)
        except Exception as e:
            logging.warning(f"Heartbeat error: {e}")
        time.sleep(0.4)


def telemetry_loop(driver: RoboClawDriver, client: mqtt.Client):
    """
    Background loop to read RoboClaw telemetry and publish to MQTT.
    """
    logging.info(
        f"Starting telemetry loop to {MQTT_TOPIC_STATUS} every {TELEMETRY_INTERVAL_SEC}s"
    )
    while not stop_event.is_set():
        try:
            status = driver.read_status()
            payload = json.dumps(status)
            client.publish(MQTT_TOPIC_STATUS, payload)
        except Exception as e:
            logging.warning(f"Telemetry loop error: {e}")
        time.sleep(TELEMETRY_INTERVAL_SEC)


def main():
    driver = RoboClawDriver()

    client = mqtt.Client(
        client_id="roboclaw_driver",
        userdata={"driver": driver},
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    # Robust connect loop so a DNS/connection blip doesn't crash the container
    while not stop_event.is_set():
        try:
            logging.info(f"Connecting to MQTT at {MQTT_HOST}:{MQTT_PORT} ...")
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            logging.info("MQTT connection established.")
            break
        except Exception as e:
            logging.error(f"MQTT connect failed: {e!r} — retrying in 5 seconds")
            time.sleep(5)

    # Start MQTT loop thread
    t_mqtt = Thread(target=mqtt_loop, args=(client,))
    t_mqtt.start()

    # Start watchdog heartbeat thread
    t_heartbeat = Thread(target=heartbeat_loop, args=(driver,))
    t_heartbeat.start()

    # Start telemetry loop thread
    t_telemetry = Thread(target=telemetry_loop, args=(driver, client))
    t_telemetry.start()

    def handle_signal(sig, frame):
        logging.info(f"Signal {sig} received, shutting down...")
        stop_event.set()
        driver.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not stop_event.is_set():
        time.sleep(0.2)

    logging.info("Exiting roboclaw_mqtt_driver")


if __name__ == "__main__":
    main()
