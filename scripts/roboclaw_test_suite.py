#!/usr/bin/env python3
"""
roboclaw_test_suite.py

Interactive test script for RoboClaw after rewiring.

Tests:
  1. Connect and read firmware version
  2. Read main battery voltage
  3. Read currents (if supported)
  4. M1 forward/backward
  5. M2 forward/backward
  6. Both motors forward/backward together (straight line)

Press Enter between tests so you can observe behavior and logs.
"""

import time
import sys

try:
    from roboclaw_3 import Roboclaw  # Ion Motion RoboClaw Python library
except ImportError:
    print("ERROR: Could not import roboclaw_3. Make sure the RoboClaw Python library is installed.")
    print("Typically: place roboclaw_3.py in the same directory or install it into your environment.")
    sys.exit(1)

# --- CONFIG --- #
PORT = "/dev/ttyACM0"
BAUDRATE = 38400
ADDRESS = 0x80   # Default RoboClaw address
SPEED = 64       # 0-127 for simple Forward/Backward commands (approx 50% power)
RUN_TIME = 2.0   # seconds each direction
# ---------------#


def wait_for_enter(msg="Press Enter to continue..."):
    input(msg)


def stop_all(rc):
    """Stop both motors."""
    rc.ForwardM1(ADDRESS, 0)
    rc.ForwardM2(ADDRESS, 0)


def read_battery_voltage(rc):
    try:
        status, value = rc.ReadMainBatteryVoltage(ADDRESS)
        if status:
            # Value is in 0.1V units
            volts = value / 10.0
            print(f"Main battery voltage: {volts:.1f} V (raw={value})")
        else:
            print("Failed to read main battery voltage (status=False).")
    except Exception as e:
        print(f"Exception while reading main battery voltage: {e}")


def read_currents(rc):
    """Try reading motor currents if supported by your board/firmware."""
    try:
        status, m1_current, m2_current = rc.ReadCurrents(ADDRESS)
        if status:
            # Units are 10 mA: 100 = 1A
            m1_a = m1_current / 100.0
            m2_a = m2_current / 100.0
            print(f"Motor currents: M1={m1_a:.2f} A, M2={m2_a:.2f} A (raw: {m1_current}, {m2_current})")
        else:
            print("Failed to read motor currents (status=False).")
    except Exception as e:
        print(f"Exception while reading currents: {e}")


def test_connection_and_version(rc):
    print("\n=== TEST 1: Connection and Firmware Version ===")
    try:
        result = rc.ReadVersion(ADDRESS)
        if result[0]:
            print(f"RoboClaw version: {result[1].decode('ascii', errors='ignore')}")
        else:
            print("Failed to read version (status=False). Check wiring, address, and baud.")
    except Exception as e:
        print(f"Exception while reading firmware version: {e}")

    read_battery_voltage(rc)
    read_currents(rc)
    print("=== END TEST 1 ===\n")


def test_m1_forward_backward(rc):
    print("\n=== TEST 2: M1 Forward / Backward ===")
    print(f"Commanding M1 forward at speed {SPEED} for {RUN_TIME} seconds...")
    try:
        rc.ForwardM1(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)

        print(f"Commanding M1 backward at speed {SPEED} for {RUN_TIME} seconds...")
        rc.BackwardM1(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)
        print("M1 test complete.")
    except Exception as e:
        print(f"Exception during M1 test: {e}")
    finally:
        stop_all(rc)
    print("=== END TEST 2 ===\n")


def test_m2_forward_backward(rc):
    print("\n=== TEST 3: M2 Forward / Backward ===")
    print(f"Commanding M2 forward at speed {SPEED} for {RUN_TIME} seconds...")
    try:
        rc.ForwardM2(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)

        print(f"Commanding M2 backward at speed {SPEED} for {RUN_TIME} seconds...")
        rc.BackwardM2(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)
        print("M2 test complete.")
    except Exception as e:
        print(f"Exception during M2 test: {e}")
    finally:
        stop_all(rc)
    print("=== END TEST 3 ===\n")


def test_both_motors_forward_backward(rc):
    print("\n=== TEST 4: Both Motors Forward / Backward (Straight) ===")
    print("This should drive the base straight forward, then straight backward (if wiring and polarity match).")
    print(f"Commanding BOTH motors forward at speed {SPEED} for {RUN_TIME} seconds...")
    try:
        rc.ForwardM1(ADDRESS, SPEED)
        rc.ForwardM2(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)

        print(f"Commanding BOTH motors backward at speed {SPEED} for {RUN_TIME} seconds...")
        rc.BackwardM1(ADDRESS, SPEED)
        rc.BackwardM2(ADDRESS, SPEED)
        time.sleep(RUN_TIME)
        stop_all(rc)
        time.sleep(0.5)
        print("Both-motors test complete.")
    except Exception as e:
        print(f"Exception during both-motors test: {e}")
    finally:
        stop_all(rc)
    print("=== END TEST 4 ===\n")


def main():
    print("=== RoboClaw Test Suite ===")
    print(f"Port: {PORT}, Baudrate: {BAUDRATE}, Address: 0x{ADDRESS:02X}")
    print("Make sure the wheels are off the ground or the base is safely restrained.")
    print("Press Ctrl+C at any time to stop and exit.\n")

    rc = Roboclaw(PORT, BAUDRATE)

    try:
        print(f"Opening RoboClaw on {PORT} at {BAUDRATE}...")
        rc.Open()
        print("RoboClaw port opened.\n")
    except Exception as e:
        print(f"ERROR: Failed to open RoboClaw serial port: {e}")
        sys.exit(1)

    try:
        wait_for_enter("Ready to begin TEST 1 (connection & version). Press Enter... ")
        test_connection_and_version(rc)

        wait_for_enter("Ready to begin TEST 2 (M1 forward/backward). Press Enter... ")
        test_m1_forward_backward(rc)

        wait_for_enter("Ready to begin TEST 3 (M2 forward/backward). Press Enter... ")
        test_m2_forward_backward(rc)

        wait_for_enter("Ready to begin TEST 4 (both motors forward/backward). Press Enter... ")
        test_both_motors_forward_backward(rc)

        print("All tests complete.")
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received. Stopping motors and exiting...")
    finally:
        stop_all(rc)
        print("Motors stopped. Closing connection.")
        # roboclaw_3.Roboclaw doesn't strictly need a close, but we can let GC handle it.
        print("Done.")


if __name__ == "__main__":
    main()
