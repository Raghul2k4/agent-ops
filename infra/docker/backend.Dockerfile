# syntax=docker/dockerfile:1.7
# Backend image. Schema migrations are applied by the Compose command with psql;
# the image itself never creates schema at startup.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq5 postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip && pip install -e .

RUN useradd --create-home --uid 10001 agentops && chown -R agentops:agentops /app
USER agentops

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# `python -m app` selects the selector event loop, which psycopg's async mode
# needs on Windows and accepts on Linux.
CMD ["python", "-m", "app"]
