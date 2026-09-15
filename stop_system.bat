@echo off
title Stop SENTINEL-AI System
echo =========================================================================
echo               Stopping SENTINEL-AI Surveillance System...
echo =========================================================================
echo.
powershell -Command "Get-NetTCPConnection -LocalPort 8000, 8443 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo.
echo [OK] SENTINEL-AI services on ports 8000 and 8443 stopped.
pause
