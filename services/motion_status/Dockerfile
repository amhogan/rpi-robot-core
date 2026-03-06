FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask paho-mqtt flask-cors

COPY motion_status.py .

ENV FLASK_ENV=production

CMD ["python", "motion_status.py"]
