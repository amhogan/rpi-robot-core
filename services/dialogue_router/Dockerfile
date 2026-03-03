FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ALSA tools for audio tests inside the container (Jabra via /dev/snd)
RUN apt-get update && apt-get install -y --no-install-recommends \
      alsa-utils \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Copy repo-level pinned requirements so a repo-root compose build works
COPY ../requirements-pinned.txt /requirements-pinned.txt

# Install pinned requirements if present, then service `requirements.txt` if present
RUN if [ -f /requirements-pinned.txt ] && [ -s /requirements-pinned.txt ]; then \
      pip install --no-cache-dir -r /requirements-pinned.txt ; \
    fi && \
    if [ -f requirements.txt ] && [ -s requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      echo "No requirements.txt or empty; skipping pip install"; \
    fi

COPY --link services/dialogue_router/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
