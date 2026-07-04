# =============================================================================
# Enterprise ETL Platform — Production Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): Install dependencies in an isolated environment
#   Stage 2 (runtime): Minimal production image — only what's needed to run
#
# Security:
#   - Runs as non-root user (appuser)
#   - No build tools in final image
#   - Minimal base image
# =============================================================================

# ---- Stage 1: Dependency Builder ----------------------------------------
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files to disk and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install system dependencies required for psycopg2 and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


# ---- Stage 2: Production Runtime Image ----------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime system dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Create non-root user for security
# Running as root inside a container is a security risk
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Create required runtime directories with proper ownership
RUN mkdir -p /app/data/raw /app/data/reports /app/data/archive /app/logs && \
    chown -R appuser:appgroup /app

# Copy application code
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup config/ ./config/
COPY --chown=appuser:appgroup migrations/ ./migrations/
COPY --chown=appuser:appgroup main.py alembic.ini ./

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Health check for Docker/orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health/ping').raise_for_status()"

# Production startup command
# Using uvicorn with multiple workers for production
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
