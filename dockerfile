# Stage 1: Builder
FROM python:3.14-slim AS builder
WORKDIR /app

# Install build-essential untuk compile library jika diperlukan
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install library ke folder .local agar mudah di-copy ke stage final
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Final
FROM python:3.14-slim
WORKDIR /app

COPY --from=builder /root/.local /root/.local
COPY . .

# Konfigurasi Environment
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Command uvicorn sudah di-handle di docker-compose untuk fleksibilitas reload