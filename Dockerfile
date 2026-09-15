# SENTINEL-AI | Smart India Hackathon 2026
# Autonomous Multi-Sensor Border Surveillance & Intrusion Detection System
# Production Offline-First Container Image

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for OpenCV, Video transcoding (FFmpeg), and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    net-tools \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application directories and model weights
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY models/ ./models/
COPY yolov8n.pt .
COPY .env.example .env

# Create persistent storage mountpoints
RUN mkdir -p storage/snapshots storage/recordings storage/evidence models

# Expose FastAPI Command Center HTTP/WebSocket port
EXPOSE 8000

# Container health inspection
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

# Launch High-Performance Uvicorn Server
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
