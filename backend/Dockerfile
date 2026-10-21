# backend/Dockerfile - Production Container for Flask REST API & Ingestion Jobs
#
# Supports:
# 1. API Service (default): gunicorn -c backend/gunicorn.conf.py "backend.app:create_app()"
# 2. Weekly Cron Worker: python -m backend.jobs.sync_weekly
# 3. One-Time Historical Backfill: python -m backend.jobs.backfill_history

FROM python:3.12-slim

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthchecks, ca-certificates for ESPN HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend and database definition source code
COPY backend /app/backend
COPY db /app/db

# Expose default HTTP port
EXPOSE 5000

# Default command: Gunicorn REST API WSGI server
# Override with 'python -m backend.jobs.sync_weekly' for Railway weekly cron
# Override with 'python -m backend.jobs.backfill_history' for one-time historical crawl
CMD ["gunicorn", "-c", "backend/gunicorn.conf.py", "backend.app:create_app()"]
