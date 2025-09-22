FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# If there is a requirements.txt, install it; otherwise ensure pyserial is present.
RUN if [ -f requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt ; \
    else \
      pip install --no-cache-dir pyserial ; \
    fi

# Simple flexible entrypoint:
#  - run run.sh if present
#  - else run main.py if present
#  - else sleep with a helpful message
COPY --link entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
