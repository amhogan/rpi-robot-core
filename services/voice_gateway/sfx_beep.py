#!/usr/bin/env python3
import os, math, struct, sys, subprocess

APLAY_DEVICE = os.environ.get("APLAY_DEVICE", "plughw:0,0")

def make_beep(rate=48000, hz=880, ms=150, amp=0.3):
    n = int(rate * ms / 1000.0)
    frames = bytearray()
    for i in range(n):
        s = int(amp * 32767 * math.sin(2*math.pi*hz*(i/rate)))
        frames += struct.pack("<h", s)
    return frames, rate

def play_pcm(pcm, rate):
    cmd = ["aplay", "-q", "-D", APLAY_DEVICE, "-f", "S16_LE", "-r", str(rate), "-c", "1"]
    try:
        subprocess.run(cmd, input=pcm, check=True)
    except Exception as e:
        print("[sfx] aplay failed:", e, file=sys.stderr)

if __name__ == "__main__":
    pcm, rate = make_beep()
    play_pcm(pcm, rate)
