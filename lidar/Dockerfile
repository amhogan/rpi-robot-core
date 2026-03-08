FROM python:3.11-slim-bookworm

LABEL maintainer="amhogan"
LABEL description="OSCAR RPLIDAR A1M8 publisher service"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lidar_publisher.py .

ENV LIDAR_PORT=/dev/rplidar \
    LIDAR_BAUDRATE=115200 \
    MQTT_HOST=mqtt \
    MQTT_PORT=1883 \
    MQTT_TOPIC_SCAN=robot/lidar/scan \
    MQTT_TOPIC_HEALTH=robot/lidar/health \
    LIDAR_SCAN_MODE=normal \
    LIDAR_PUBLISH_HZ=5 \
    LIDAR_MIN_QUALITY=10 \
    LIDAR_HEALTH_INTERVAL=30

CMD ["python", "-u", "lidar_publisher.py"]
