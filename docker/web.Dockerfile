# Multi-stage build for the web service.
# Stage 1 builds the React SPA; stage 2 is the Python runtime.
# The frontend/ directory is optional — if absent the image still builds and
# `static_spa.py` returns a placeholder for non-API routes.

# ------------------------------------------------------------------ #
# Stage 1: frontend builder
# ------------------------------------------------------------------ #
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/ ./frontend/
# L3/L6: install ALL deps (including dev — build tools need them), then
# produce dist. Only the built dist is copied into the runtime stage, so
# the dev deps never reach the final image.
RUN cd frontend && npm ci && npm run build

# ------------------------------------------------------------------ #
# Stage 2: Python runtime
# ------------------------------------------------------------------ #
FROM python:3.13-slim

# L10: OCI image labels so GHCR + anything consuming the registry can show
# where this image came from. Values are populated at build time by the
# GitHub Actions release workflow via docker/metadata-action.
LABEL org.opencontainers.image.title="pfsense-backup-web" \
      org.opencontainers.image.description="pfSense backup — web/API service (FastAPI + React)" \
      org.opencontainers.image.source="https://github.com/metril/pfsense-backup" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --extra web --no-dev

COPY pfsense_shared/ ./pfsense_shared/
COPY web/ ./web/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY --from=frontend /fe/frontend/dist/ ./web/static/

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8080/api/health >/dev/null || exit 1

CMD ["python", "-m", "web"]
