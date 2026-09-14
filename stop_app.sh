#!/usr/bin/env bash
echo "======================================================="
echo "      Stopping Job Search Automation Web App"
echo "======================================================="

echo "[*] Killing process on port 8000..."
fuser -k 8000/tcp 2>/dev/null || true

echo "[*] Stopping uvicorn background processes..."
pkill -f "uvicorn web.backend.app:app" 2>/dev/null || true

echo "[OK] App server stopped."
