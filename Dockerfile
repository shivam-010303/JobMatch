FROM python:3.11-slim

WORKDIR /app

# Install only essential build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install PyTorch CPU-only (much smaller than GPU version)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install requirements (API only)
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt \
    && rm -rf ~/.cache/pip

# Copy app code
COPY src/ ./src/
COPY scripts/setup_data.py ./scripts/

RUN mkdir -p /app/data /app/data/qdrant

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATABASE_PATH=/app/data/jobs.db
ENV QDRANT_PATH=/app/data/qdrant

EXPOSE 8000

CMD python scripts/setup_data.py && uvicorn src.api.main:app --host 0.0.0.0 --port 8000
