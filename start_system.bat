@echo off
title SENTINEL-AI Border Surveillance System - Smart India Hackathon 2026
echo =========================================================================
echo       SENTINEL-AI: Multi-Sensor Border Surveillance Command Center
echo                 Smart India Hackathon 2026 Prototype
echo =========================================================================
echo.
echo [1/3] Checking environment dependencies...
python --version
echo [2/3] Launching FastAPI Surveillance Backend + WebSocket Server...
echo [3/3] Opening Command Dashboard at: http://localhost:8000
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
