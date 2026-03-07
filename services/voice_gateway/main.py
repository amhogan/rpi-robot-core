import os
import json
import asyncio
import logging
import sys
import threading
from typing import Optional

import paho.mqtt.client as mqtt

from wyoming.event import Event, async_read_event, async_write_event
from wyoming.audio import AudioStart, AudioChunk, AudioStop

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

MQTT_TOPIC_TTS = os.environ.get("MQTT_TOPIC_TTS", "robot/tts/say")
MQTT_TOPIC_STT_REQ = os.environ.get("MQTT_TOPIC_STT_REQ", "robot/stt/request")
MQTT_TOPIC_STT_TEXT = os.environ.get("MQTT_TOPIC_STT_TEXT", "robot/stt/text")
MQTT_TOPIC_VOICE_CMD = os.environ.get(
    "MQTT_TOPIC_VOICE_CMD", "robot/voice/command"
)

PIPER_HOST = os.environ.get("PIPER_HOST", "wyoming-piper")
PIPER_PORT = int(os.environ.get("PIPER_PORT", "10200"))

WHISPER_HOST = os.environ.get("WHISPER_HOST", "wyoming-whisper")
WHISPER_PORT = int(os.environ.get("WHISPER_PORT", "10300"))

APLAY_DEVICE = os.environ.get("APLAY_DEVICE", "plughw:USB,0")
ARECORD_DEVICE = os.environ.get("ARECORD_DEVICE", "plughw:USB,0")

STT_DEFAULT_SECONDS = int(os.environ.get("STT_DEFAULT_SECONDS", "5"))

LOG_PREFIX = "[voice_gateway] "

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)

# -----------------------------------------------------------------------------
# Helper: ALSA format mapping
# -----------------------------------------------------------------------------

def width_to_alsa_format(width: int) -> str:
    """Map 'width' (bytes per sample) to ALSA aplay format."""
    if width == 1:
        return "U8"
    if width == 2:
        return "S16_LE"
    if width == 3:
        return "S24_LE"
    if width == 4:
        return "S32_LE"
    return "S16_LE"

# -----------------------------------------------------------------------------
# TTS (Piper)
# -----------------------------------------------------------------------------

async def _play_tts(text: str) -> None:
    """Connect to Wyoming Piper, send TTS request, stream audio to aplay."""
    logging.info(
        f"{LOG_PREFIX}Connecting to Wyoming TTS at tcp://{PIPER_HOST}:{PIPER_PORT}"
    )

    reader, writer = await asyncio.open_connection(PIPER_HOST, PIPER_PORT)

    try:
        # Send a 'synthesize' event with the requested text.
        synth_event = Event(
            type="synthesize",
            data={"text": text},
        )
        await async_write_event(synth_event, writer)

        aplay_proc: Optional[asyncio.subprocess.Process] = None
        rate = 22050
        width = 2
        channels = 1

        # Read events: audio-start, audio-chunk, audio-stop, error
        while True:
            event = await async_read_event(reader)
            if event is None:
                logging.info(f"{LOG_PREFIX}TTS connection closed by server")
                break

            etype = event.type
            data = event.data or {}

            if etype == "audio-start":
                rate = int(data.get("rate", rate))
                width = int(data.get("width", width))
                channels = int(data.get("channels", channels))
                alsa_format = width_to_alsa_format(width)

                logging.info(
                    f"{LOG_PREFIX}TTS audio-start: rate={rate}, width={width}, "
                    f"channels={channels}, alsa_format={alsa_format}"
                )

                cmd = [
                    "aplay",
                    "-q",
                    "-D",
                    APLAY_DEVICE,
                    "-r",
                    str(rate),
                    "-c",
                    str(channels),
                    "-f",
                    alsa_format,
                ]
                aplay_proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                )

            elif etype == "audio-chunk":
                if not aplay_proc or not aplay_proc.stdin:
                    logging.warning(
                        f"{LOG_PREFIX}Got audio-chunk but aplay is not running"
                    )
                    continue

                if event.payload:
                    aplay_proc.stdin.write(event.payload)
                    await aplay_proc.stdin.drain()
                else:
                    logging.warning(f"{LOG_PREFIX}audio-chunk has no payload")

            elif etype == "audio-stop":
                logging.info(f"{LOG_PREFIX}TTS audio-stop received")
                break

            elif etype == "error":
                logging.error(f"{LOG_PREFIX}TTS error from server: {data}")
                break

            else:
                logging.debug(
                    f"{LOG_PREFIX}TTS ignoring event type: {etype} ({data})"
                )

        if aplay_proc:
            if aplay_proc.stdin:
                aplay_proc.stdin.close()
            await aplay_proc.wait()

    finally:
        writer.close()
        await writer.wait_closed()


MQTT_TOPIC_TTS_DONE = "robot/tts/done"

def speak_text(text: str, mqtt_client=None) -> None:
    """Run async TTS from a synchronous MQTT callback."""
    logging.info(f"{LOG_PREFIX}TTS request: '{text}'")
    try:
        asyncio.run(_play_tts(text))
    except Exception as e:
        logging.exception(f"{LOG_PREFIX}Error in speak_text: {e}")
    finally:
        if mqtt_client:
            mqtt_client.publish(MQTT_TOPIC_TTS_DONE, "1")

# -----------------------------------------------------------------------------
# STT (Whisper)
# -----------------------------------------------------------------------------

async def _capture_audio_raw(seconds: int) -> bytes:
    """Capture raw S16_LE PCM 16kHz mono audio from arecord."""
    logging.info(
        f"{LOG_PREFIX}Starting arecord capture: device={ARECORD_DEVICE}, seconds={seconds}"
    )

    cmd = [
        "arecord",
        "-q",
        "-D",
        ARECORD_DEVICE,
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-d",
        str(seconds),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    audio_data, stderr_data = await proc.communicate()

    if stderr_data:
        logging.info(
            f"{LOG_PREFIX}arecord stderr: "
            f"{stderr_data.decode('utf-8', 'ignore')}"
        )

    logging.info(
        f"{LOG_PREFIX}arecord finished with code={proc.returncode}, "
        f"bytes={len(audio_data)}"
    )

    if proc.returncode != 0:
        logging.error(f"{LOG_PREFIX}arecord failed")
        return b""

    return audio_data


async def _run_stt_capture(seconds: int) -> Optional[str]:
    """Capture audio, send to Whisper, return recognized text."""
    audio_data = await _capture_audio_raw(seconds)
    if not audio_data:
        logging.error(f"{LOG_PREFIX}No audio captured for STT")
        return None

    logging.info(
        f"{LOG_PREFIX}Connecting to Wyoming STT at tcp://{WHISPER_HOST}:{WHISPER_PORT}"
    )

    reader, writer = await asyncio.open_connection(WHISPER_HOST, WHISPER_PORT)

    try:
        # 1) Send audio-start
        start = AudioStart(rate=16000, width=2, channels=1)
        await async_write_event(start.event(), writer)

        # 2) Send chunk
        chunk = AudioChunk(
            rate=16000,
            width=2,
            channels=1,
            audio=audio_data,
        )
        await async_write_event(chunk.event(), writer)

        # 3) Send stop
        stop = AudioStop()
        await async_write_event(stop.event(), writer)

        # 4) Collect transcript
        recognized_text: Optional[str] = None

        while True:
            event = await async_read_event(reader)
            if event is None:
                logging.info(f"{LOG_PREFIX}STT connection closed by server")
                break

            etype = event.type
            data = event.data or {}

            logging.info(
                f"{LOG_PREFIX}STT event from Whisper: "
                f"type={etype!r}, payload={event.payload is not None}, data={data}"
            )

            # Whisper sends "transcript" events
            if etype == "transcript":
                recognized_text = data.get("text", "")
                logging.info(
                    f"{LOG_PREFIX}STT transcript: {recognized_text!r}"
                )
                break

            elif etype == "error":
                logging.error(f"{LOG_PREFIX}STT error: {data}")
                break

        return recognized_text

    finally:
        writer.close()
        await writer.wait_closed()

# -----------------------------------------------------------------------------
# Voice command parsing (Option 1)
# -----------------------------------------------------------------------------

def interpret_voice_command(text: str) -> Optional[dict]:
    """
    Turn a natural-language STT transcript into a structured robot command.

    Returns a dict like:
      {"intent": "move", "direction": "forward"}
    or None if no command is recognized.
    """
    clean = (text or "").strip().lower()
    if not clean:
        return None

    # Hard stop / cancel
    if any(word in clean for word in ["stop", "halt", "freeze", "cancel that"]):
        return {"intent": "stop"}

    # Forward
    if any(phrase in clean for phrase in ["go forward", "move forward", "move ahead", "forward"]):
        return {"intent": "move", "direction": "forward"}

    # Backward / reverse
    if any(phrase in clean for phrase in ["go back", "back up", "move back", "reverse", "backward"]):
        return {"intent": "move", "direction": "backward"}

    # Turn left
    if any(phrase in clean for phrase in ["turn left", "go left", "rotate left", "spin left"]):
        return {"intent": "turn", "direction": "left"}

    # Turn right
    if any(phrase in clean for phrase in ["turn right", "go right", "rotate right", "spin right"]):
        return {"intent": "turn", "direction": "right"}

    # Status queries
    if "status" in clean or "how are you" in clean or "how are you doing" in clean:
        return {"intent": "query_status"}

    # Simple "say" commands: "say hello world"
    if clean.startswith("say "):
        phrase = text.strip()[4:]  # keep original casing after "say "
        phrase = phrase.strip()
        if phrase:
            return {"intent": "say", "text": phrase}

    # No known command
    return None


def handle_stt_text_message(client: mqtt.Client, payload: bytes) -> None:
    """Handle robot/stt/text messages: parse into robot/voice/command."""
    try:
        body = payload.decode("utf-8", "ignore").strip()
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logging.error(f"{LOG_PREFIX}Invalid JSON in STT text payload: {payload!r}")
        return

    text = (data.get("text") or "").strip()
    if not text:
        logging.warning(f"{LOG_PREFIX}STT text payload missing 'text' field: {data}")
        return

    logging.info(f"{LOG_PREFIX}Interpreting STT text for command: {text!r}")
    cmd = interpret_voice_command(text)
    if cmd is None:
        logging.info(f"{LOG_PREFIX}No command recognized from STT text")
        return

    try:
        client.publish(MQTT_TOPIC_VOICE_CMD, json.dumps(cmd))
        logging.info(
            f"{LOG_PREFIX}Published voice command to {MQTT_TOPIC_VOICE_CMD}: {cmd}"
        )
    except Exception as e:
        logging.exception(f"{LOG_PREFIX}Error publishing voice command: {e}")

# -----------------------------------------------------------------------------
# STT request handler
# -----------------------------------------------------------------------------

def handle_stt_request(client: mqtt.Client, payload: bytes) -> None:
    """Handle robot/stt/request messages."""
    try:
        body = payload.decode("utf-8", "ignore").strip()
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logging.error(f"{LOG_PREFIX}Invalid JSON in STT request")
        data = {}

    seconds = int(data.get("seconds", STT_DEFAULT_SECONDS))
    if seconds <= 0:
        seconds = STT_DEFAULT_SECONDS

    logging.info(f"{LOG_PREFIX}STT request received, seconds={seconds}")

    try:
        text = asyncio.run(_run_stt_capture(seconds))
        if text:
            out = {"text": text, "seconds": seconds}
            client.publish(MQTT_TOPIC_STT_TEXT, json.dumps(out))
            logging.info(f"{LOG_PREFIX}Published STT text: {text!r}")
        else:
            logging.warning(f"{LOG_PREFIX}No STT result recognized")
    except Exception as e:
        logging.exception(f"{LOG_PREFIX}Error during STT capture: {e}")

# -----------------------------------------------------------------------------
# MQTT callbacks
# -----------------------------------------------------------------------------

STARTUP_MESSAGE = os.environ.get("STARTUP_MESSAGE", "OSCAR is online")
STARTUP_DELAY = float(os.environ.get("STARTUP_DELAY_SECS", "5"))

def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"{LOG_PREFIX}Connected to MQTT at {MQTT_HOST}:{MQTT_PORT}")
    client.subscribe(MQTT_TOPIC_TTS)
    client.subscribe(MQTT_TOPIC_STT_REQ)
    client.subscribe(MQTT_TOPIC_STT_TEXT)
    logging.info(
        f"{LOG_PREFIX}Subscribed to "
        f"{MQTT_TOPIC_TTS}, {MQTT_TOPIC_STT_REQ}, {MQTT_TOPIC_STT_TEXT}"
    )
    if STARTUP_MESSAGE:
        threading.Timer(
            STARTUP_DELAY,
            speak_text,
            args=[STARTUP_MESSAGE],
            kwargs={"mqtt_client": client},
        ).start()


def on_message(client, userdata, msg):
    payload_str = msg.payload.decode("utf-8", "ignore")
    logging.info(f"{LOG_PREFIX}Received on {msg.topic}: {payload_str}")

    if msg.topic == MQTT_TOPIC_TTS:
        try:
            payload = json.loads(payload_str)
            text = payload.get("text", "").strip()
            if text:
                speak_text(text, mqtt_client=client)
            else:
                logging.warning(
                    f"{LOG_PREFIX}Empty text in TTS payload"
                )
        except Exception:
            logging.error(f"{LOG_PREFIX}Invalid JSON in TTS payload")

    elif msg.topic == MQTT_TOPIC_STT_REQ:
        handle_stt_request(client, msg.payload)

    elif msg.topic == MQTT_TOPIC_STT_TEXT:
        handle_stt_text_message(client, msg.payload)

# -----------------------------------------------------------------------------
# Main entrypoint
# -----------------------------------------------------------------------------

def main() -> None:
    logging.info(
        f"{LOG_PREFIX}Starting voice_gateway; "
        f"MQTT={MQTT_HOST}:{MQTT_PORT}, "
        f"Piper={PIPER_HOST}:{PIPER_PORT}, "
        f"Whisper={WHISPER_HOST}:{WHISPER_PORT}, "
        f"APLAY_DEVICE='{APLAY_DEVICE}', "
        f"ARECORD_DEVICE='{ARECORD_DEVICE}'"
    )

    client = mqtt.Client(
        client_id="rpi-robot-voice-gateway",
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
