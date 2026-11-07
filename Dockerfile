FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries=5 -r requirements.txt

COPY src/ ./src/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY dashboards/ ./dashboards/
ENV PYTHONPATH=/app/src

# Raw data, clean output, rejects and logs are mounted as volumes (see docker-compose.yml)
ENTRYPOINT ["python", "-m", "pulseiq_etl"]
