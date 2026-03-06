import os
import logging
import time

from flask import Flask, Response, render_template_string
import cv2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = Flask(__name__)

CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
FRAME_FPS = int(os.getenv("FRAME_FPS", "15"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "70"))

camera = None


def open_camera():
    global camera
    logging.info(f"Opening camera device {CAMERA_DEVICE} ...")
    cam = cv2.VideoCapture(CAMERA_DEVICE)
    if not cam.isOpened():
        logging.error(f"Failed to open camera device {CAMERA_DEVICE}")
        return None

    # Try to set capture properties
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cam.set(cv2.CAP_PROP_FPS, FRAME_FPS)

    # Read one test frame
    ret, frame = cam.read()
    if not ret or frame is None:
        logging.error(f"Opened {CAMERA_DEVICE} but could not read a frame")
        cam.release()
        return None

    h, w = frame.shape[:2]
    logging.info(
        f"Camera {CAMERA_DEVICE} opened successfully: {w}x{h} at ~{FRAME_FPS} fps"
    )
    camera = cam
    return cam


def get_camera():
    """Ensure we have an open camera; reopen if needed."""
    global camera
    if camera is None:
        camera = open_camera()
    else:
        # Check that it's still alive by grabbing a frame
        ret, frame = camera.read()
        if not ret or frame is None:
            logging.warning("Lost camera, attempting to reopen...")
            camera.release()
            camera = open_camera()
    return camera


def generate_frames():
    global camera
    while True:
        cam = get_camera()
        if cam is None:
            # No camera available, wait a bit and try again
            time.sleep(1.0)
            continue

        ret, frame = cam.read()
        if not ret or frame is None:
            logging.warning("Failed to read frame from camera")
            time.sleep(0.1)
            continue

        # Encode frame as JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        success, buffer = cv2.imencode(".jpg", frame, encode_param)
        if not success:
            logging.warning("Failed to encode frame as JPEG")
            continue

        jpg_bytes = buffer.tobytes()

        # MJPEG multipart response
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpg_bytes + b"\r\n"
        )


INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <title>Robot Camera Stream</title>
    <style>
      body { background: #111; color: #eee; font-family: sans-serif; text-align: center; }
      img { max-width: 100%; height: auto; border: 2px solid #444; margin-top: 20px; }
    </style>
  </head>
  <body>
    <h1>Robot Camera Stream</h1>
    <p>Device: {{ device }}</p>
    <img src="/video.mjpg" />
  </body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, device=CAMERA_DEVICE)


@app.route("/video.mjpg")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    # When running directly (dev), listen on 0.0.0.0:8080
    logging.info(f"Starting camera server on 0.0.0.0:8080 using {CAMERA_DEVICE}")
    open_camera()
    app.run(host="0.0.0.0", port=8080, debug=False)
