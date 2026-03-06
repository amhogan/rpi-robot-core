FROM python:3.11-slim

WORKDIR /app

# Install system libs needed for OpenCV + V4L2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libv4l-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir flask opencv-python-headless

COPY camera_server.py .

ENV CAMERA_DEVICE=/dev/video0
ENV FRAME_WIDTH=640
ENV FRAME_HEIGHT=480
ENV FRAME_FPS=15
ENV JPEG_QUALITY=70

CMD ["python", "camera_server.py"]
