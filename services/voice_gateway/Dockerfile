FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ALSA tools (playback/capture) for Jabra tests
RUN apt-get update && apt-get install -y --no-install-recommends \
      alsa-utils \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Only install when requirements.txt exists AND is non-empty
RUN if [ -f requirements.txt ] && [ -s requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      echo "No requirements or empty requirements.txt; skipping pip install"; \
    fi

COPY --link entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
