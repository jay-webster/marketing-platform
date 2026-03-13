# -----------------------------------------------------------------
# Stage 1: dependency builder
# -----------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build tools needed for some Python packages (e.g. asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------
# Stage 2: runtime image
# -----------------------------------------------------------------
FROM python:3.13-slim

WORKDIR /app

# Runtime libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ ./src/
COPY utils/ ./utils/
COPY migrations/ ./migrations/

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
