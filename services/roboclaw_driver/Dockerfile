FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Copy repo-level pinned requirements so a repo-root compose build works
COPY ../requirements-pinned.txt /requirements-pinned.txt

# Install pinned requirements if present; then install service requirements
# If no service requirements are present, fall back to ensuring `pyserial`.
RUN if [ -f /requirements-pinned.txt ] && [ -s /requirements-pinned.txt ]; then \
      pip install --no-cache-dir -r /requirements-pinned.txt ; \
    fi && \
    if [ -f requirements.txt ] && [ -s requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      pip install --no-cache-dir pyserial ; \
    fi

# Simple flexible entrypoint:
#  - run run.sh if present
#  - else run main.py if present
#  - else sleep with a helpful message
COPY --link services/roboclaw_driver/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
