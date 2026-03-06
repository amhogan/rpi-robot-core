#!/usr/bin/env python3
import json
import sys
import termios
import tty
import time
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC = "robot/motion/command"

SPEED = 0.4
DURATION = 0.5

HELP = """
Robot MQTT Teleop (W/A/S/D keys)

 w = forward
 s = backward
 a = left pivot
 d = right pivot
 q = small forward nudge
 e = small backward nudge
 x = stop
 c = quit
"""

def send(client, direction, duration=DURATION, speed=SPEED):
    payload = json.dumps({
        "direction": direction,
        "duration": duration,
        "speed": speed
    })
    print("->", payload)
    client.publish(TOPIC, payload)

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch

def main():
    print(HELP)

    client = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            ch = getch()
            if ch == "w":
                send(client, "forward")
            elif ch == "s":
                send(client, "backward")
            elif ch == "a":
                send(client, "left")
            elif ch == "d":
                send(client, "right")
            elif ch == "q":
                send(client, "forward", 0.2, 0.2)
            elif ch == "e":
                send(client, "backward", 0.2, 0.2)
            elif ch == "x":
                send(client, "forward", 0.0, 0.0)
            elif ch == "c":
                print("Exiting.")
                break
            else:
                pass
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
