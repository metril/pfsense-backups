# Multi-stage build for the web service.
# Stage 1 builds the React SPA; stage 2 is the Python runtime.
# The frontend/ directory is optional — if absent the image still builds and
# `static_spa.py` returns a placeholder for non-API routes.

# ------------------------------------------------------------------ #
# Stage 1: frontend builder (only runs when frontend/ is present)
# ------------------------------------------------------------------ #
FROM node:20-alpine AS frontend
WORKDIR /fe
# COPY with a trailing dot fails if the source doesn't exist; work around by
# copying the whole repo and filtering.
COPY frontend/ ./frontend/
# Fallback if no frontend yet: produce an empty dist/ so stage 2 COPY succeeds.
RUN if [ -f frontend/package.json ]; then \
      cd frontend && npm ci && npm run build; \
    else \
      mkdir -p frontend/dist && echo "<!doctype html><title>pfSense Backup</title><p>SPA not built in this image.</p>" > frontend/dist/index.html; \
    fi

# ------------------------------------------------------------------ #
# Stage 2: Python runtime
# ------------------------------------------------------------------ #
FROM python:3.13-slim

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
