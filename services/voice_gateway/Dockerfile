FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ALSA tools (playback/capture), useful for Jabra tests
RUN apt-get update && apt-get install -y --no-install-recommends \
      alsa-utils \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN if [ -f requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      pip install --no-cache-dir ; \
    fi

COPY --link entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
