FROM python:3.13-slim

# L10: OCI image labels — populated/overridden by the release workflow.
LABEL org.opencontainers.image.title="pfsense-backups-worker" \
      org.opencontainers.image.description="pfSense backups — scheduler + worker" \
      org.opencontainers.image.source="https://github.com/metril/pfsense-backups" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency resolution inside the image.
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app

# Copy lockfile + manifest first for build-cache friendliness.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --extra worker --no-dev

# Application code.
COPY pfsense_shared/ ./pfsense_shared/
COPY worker/ ./worker/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data /backups \
    && chown -R appuser:appuser /app /backups

USER appuser

ENV PATH="/app/.venv/bin:${PATH}"

# Ports: 8000 Prometheus; 5555 ZMQ PULL; 5556 ZMQ PUB.
EXPOSE 8000 5555 5556

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8000/metrics >/dev/null || exit 1

CMD ["python", "-m", "worker"]
