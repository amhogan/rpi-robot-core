#!/usr/bin/env python3
import http.server
import json
import os
import socket
import time
from pathlib import Path
import shutil

HOST = os.getenv("NETSTATUS_HOST", "0.0.0.0")
PORT = int(os.getenv("NETSTATUS_PORT", "8081"))
ROBOT_NAME = os.getenv("ROBOT_NAME", None)


def get_cpu_temp_c():
    paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
    ]
    for p in paths:
        try:
            text = Path(p).read_text().strip()
            value = float(text) / 1000.0  # millidegrees C -> C
            return round(value, 1)
        except Exception:
            continue
    return None


def get_uptime_seconds():
    try:
        with open("/proc/uptime", "r") as f:
            first = f.read().split()[0]
            return float(first)
    except Exception:
        return None


def get_load_averages():
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
            one = float(parts[0])
            five = float(parts[1])
            fifteen = float(parts[2])
            return one, five, fifteen
    except Exception:
        return None, None, None


def get_disk_usage(path="/"):
    try:
        usage = shutil.disk_usage(path)
        total = usage.total
        used = usage.used
        free = usage.free
        used_percent = round((used / total) * 100, 1) if total > 0 else None
        return {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "used_percent": used_percent,
        }
    except Exception:
        return None


def check_tcp(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_mqtt() -> bool:
    """
    Try a few reasonable ways to reach the MQTT broker:
    - By container name on the robot-core network
    - Via the Docker host alias
    - Via a typical Docker bridge gateway IP
    """
    for host in ("mosquitto", "host.docker.internal", "172.17.0.1"):
        if check_tcp(host, 1883, timeout=0.7):
            return True
    return False


def get_voice_status():
    return {
        "mqtt_ok": check_mqtt(),
        "tts_ok": check_tcp("wyoming-piper", 10200),
        "stt_ok": check_tcp("wyoming-whisper", 10300),
    }


def build_status():
    load1, load5, load15 = get_load_averages()
    return {
        "hostname": ROBOT_NAME or socket.gethostname(),
        "time": int(time.time()),
        "cpu_temp_c": get_cpu_temp_c(),
        "uptime_seconds": get_uptime_seconds(),
        "loadavg_1m": load1,
        "loadavg_5m": load5,
        "loadavg_15m": load15,
        "disk_root": get_disk_usage("/"),
        "voice": get_voice_status(),
    }


class NetstatusHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/status"):
            self._send_json(build_status())
        else:
            self._send_json({"error": "not_found", "path": self.path}, status=404)

    # Keep logs quiet
    def log_message(self, format, *args):
        return


def main():
    server = http.server.ThreadingHTTPServer((HOST, PORT), NetstatusHandler)
    print(f"[netstatus] Listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
