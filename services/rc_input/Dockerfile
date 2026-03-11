FROM python:3.11-slim

WORKDIR /app

# lgpio needs access to /dev/gpiochip0
# The container must be run with --device=/dev/gpiochip0
# (handled in docker-compose via devices:)

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        swig \
    && pip install --no-cache-dir lgpio paho-mqtt \
    && apt-get purge -y gcc swig \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY rc_input.py .

CMD ["python", "-u", "rc_input.py"]
