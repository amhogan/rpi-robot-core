#!/usr/bin/env python3
"""
lidar_test.py — quick smoke test for RPLIDAR A1M8 on RPi 5.
"""

import sys
import time
from rplidar import RPLidar

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/rplidar"
SCAN_COUNT = 5

print(f"Connecting to RPLIDAR on {PORT}...")
lidar = RPLidar(PORT)

try:
    print("\n--- Device Info ---")
    print(lidar.get_info())

    print("\n--- Device Health ---")
    status, error_code = lidar.get_health()
    print(f"  Status: {status}  Error code: {error_code}")

    if status == "Error":
        print("LIDAR reports error — check power and USB connection.")
        sys.exit(1)

    print(f"\n--- Capturing {SCAN_COUNT} scans (express mode) ---")
    for i, scan in enumerate(lidar.iter_scans(scan_type="express")):
        valid = [m for m in scan if m[0] is None or m[0] >= 10 and m[2] > 0]
        print(f"  Scan {i+1}: {len(scan)} raw pts, {len(valid)} quality-filtered pts")
        if i + 1 >= SCAN_COUNT:
            break

    print("\n✓ RPLIDAR A1M8 is working correctly.")

except Exception as exc:
    print(f"\n✗ Error: {exc}")
    sys.exit(1)

finally:
    lidar.stop()
    lidar.disconnect()
    print("Disconnected.")
