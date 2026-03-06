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

# Install dependencies
RUN if [ -f requirements.txt ] && [ -s requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      echo "No requirements.txt or empty; skipping pip install"; \
    fi

RUN chmod +x /app/entrypoint.sh /app/run.sh

CMD ["/app/entrypoint.sh"]
