FROM python:3.11-slim

# pigpio needs access to /dev/mem or /dev/gpiomem — runs privileged or with
# the gpiomem device passed through in docker-compose.

WORKDIR /app

# pigpio C library required before the Python binding installs
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        make \
        wget \
        unzip \
    && wget -q https://github.com/joan2937/pigpio/archive/master.zip -O pigpio.zip \
    && unzip pigpio.zip \
    && cd pigpio-master && make -j$(nproc) && make install \
    && cd .. && rm -rf pigpio-master pigpio.zip \
    && apt-get purge -y gcc make wget unzip \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rc_input.py .

# pigpiod runs on the HOST — this container connects to it over TCP.
# PIGPIO_ADDR env var lets pigpio.pi() find the host daemon.
ENV PIGPIO_ADDR=host.docker.internal

CMD ["python", "-u", "rc_input.py"]
