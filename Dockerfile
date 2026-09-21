# SENTINEL-AI | AERION Autonomous Border Surveillance System
# Production Container Image for Hugging Face Spaces & Cloud Deployment

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=7860 \
    SYSTEM_MODE=SIMULATED \
    HOME=/home/user

# Install system dependencies required for OpenCV, FFmpeg, and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    net-tools \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user for Hugging Face Spaces (UID 1000)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install lightweight CPU-only PyTorch first for fast build, followed by requirements
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application directories and model weights
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY models/ ./models/
COPY yolov8n.pt .
COPY .env.example .env

# Create persistent storage mountpoints and assign permissions
RUN mkdir -p storage/snapshots storage/recordings storage/evidence models \
    && chown -R user:user /app

# Switch to non-root user
USER user

# Expose default port for Hugging Face Spaces
EXPOSE 7860

# Health inspection check
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/system/health || exit 1

# Launch High-Performance Uvicorn Server with dynamic cloud port
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
