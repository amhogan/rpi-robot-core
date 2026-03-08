#!/usr/bin/env python3
import os, math, struct, sys, subprocess

APLAY_DEVICE = os.environ.get("APLAY_DEVICE", "plughw:0,0")

def make_beep(rate=48000, hz=880, ms=400, amp=0.3):
    # Prepend silence to wake the BT sink, then play the beep tone.
    silence_frames = int(rate * 0.6)
    silence = b"\x00" * silence_frames * 2  # s16le mono
    n = int(rate * ms / 1000.0)
    frames = bytearray()
    for i in range(n):
        s = int(amp * 32767 * math.sin(2*math.pi*hz*(i/rate)))
        frames += struct.pack("<h", s)
    return silence + bytes(frames), rate

def play_pcm(pcm, rate):
    cmd = ["aplay", "-q", "-D", APLAY_DEVICE, "-f", "S16_LE", "-r", str(rate), "-c", "1"]
    try:
        subprocess.run(cmd, input=pcm, check=True)
    except Exception as e:
        print("[sfx] aplay failed:", e, file=sys.stderr)

if __name__ == "__main__":
    pcm, rate = make_beep()
    play_pcm(pcm, rate)
