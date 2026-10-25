# ==============================================================================
# AIOS Command Center - Production Dockerfile
# ==============================================================================
FROM python:3.12-slim-bookworm

# Environment variables for Python runtime optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HUD_HOST=0.0.0.0 \
    HUD_PORT=5050 \
    HUD_DATA_DIR=/app/data \
    HUD_SCRATCH_DIR=/app/scratch \
    HUD_CALENDAR_DIR=/app/calendar \
    SECOND_BRAIN_DIR=/app/vault

# Create non-root user and group (UID/GID 10001) for defense-in-depth security
RUN groupadd -g 10001 aios && \
    useradd -u 10001 -g aios -s /bin/bash -m aios

# Set working directory
WORKDIR /app

# Copy dependency requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create application state and data directories with correct permissions
RUN mkdir -p /app/data /app/scratch /app/state /app/calendar /app/vault /app/inbox && \
    chown -R aios:aios /app

# Copy application source code with non-root ownership
COPY --chown=aios:aios hud_server.py app.py index.html package.json inference_adapter.py data_contracts.py ./
COPY --chown=aios:aios hud/ ./hud/
COPY --chown=aios:aios static/ ./static/
COPY --chown=aios:aios config/ ./config/
COPY --chown=aios:aios inbox/ ./inbox/
COPY --chown=aios:aios plugins/ ./plugins/

# Switch to non-root user
USER aios

# Expose HTTP port for the AIOS Command Center
EXPOSE 5050

# Native Python healthcheck (no external curl/wget dependencies required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/api/os/telemetry', timeout=3)" || exit 1

# Start the unified AI OS Command Center server
CMD ["python", "hud_server.py"]
