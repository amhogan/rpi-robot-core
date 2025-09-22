#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, signal, time
from datetime import datetime
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST","127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT","1883"))
MQTT_BASE = os.environ.get("MQTT_BASE","robot").rstrip("/")
MQTT_CID  = os.environ.get("MQTT_CLIENT_ID","dialogue-router")

TOPIC_STT = f"{MQTT_BASE}/stt/text"
TOPIC_TTS = f"{MQTT_BASE}/tts/say"

def intent_reply(text):
    t = (text or "").strip()
    if not t:
        return "I didn't catch that."
    low = t.lower()
    if low.startswith("say "):
        return t[4:].strip() or "Okay."
    if ("what time" in low) or ("time is it" in low):
        return datetime.now().strftime("It is %I:%M %p.").lstrip("0")
    if ("your name" in low) or ("who are you" in low):
        return "I am Oscar's voice assistant."
    return "You said: " + t

def on_connect(c, u, f, rc):
    print("[dialogue] MQTT connected rc=%s; subscribing to %s" % (rc, TOPIC_STT), flush=True)
    c.subscribe(TOPIC_STT)

def on_message(c, u, msg):
    try:
        payload = msg.payload.decode("utf-8","ignore").strip()
        if payload.startswith("{"):
            try:
                text = (json.loads(payload).get("text") or "").strip()
            except Exception:
                text = ""
        else:
            text = payload
        reply = intent_reply(text)
        print("[dialogue] heard=%r -> reply=%r" % (text, reply), flush=True)
        if reply:
            c.publish(TOPIC_TTS, reply, qos=0, retain=False)
    except Exception as e:
        print("[dialogue] error: %r" % e, flush=True)

def main():
    print("[dialogue] starting.", flush=True)
    c = mqtt.Client(client_id=MQTT_CID, clean_session=True, userdata=None,
                    protocol=mqtt.MQTTv311, transport="tcp")
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(MQTT_HOST, MQTT_PORT, 60)
    c.loop_start()

    stop = False
    def _sig(*_):
        nonlocal stop; stop = True
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT,  _sig)

    while not stop:
        time.sleep(0.5)

    c.loop_stop()

if __name__ == "__main__":
    main()
