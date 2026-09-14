#!/usr/bin/env bash
set -e

# Change to the directory of this script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================="
echo "      Starting Job Search Automation Web App"
echo "======================================================="

# Activate virtual environment (tfenv prioritized per user configuration)
if [ -f "/mnt/extra/morningstar/tfenv/bin/activate" ]; then
    echo "[*] Activating tfenv environment (/mnt/extra/morningstar/tfenv)..."
    source /mnt/extra/morningstar/tfenv/bin/activate
    PYTHON="/mnt/extra/morningstar/tfenv/bin/python"
elif [ -f ".venv/bin/activate" ]; then
    echo "[*] Activating virtual environment (.venv)..."
    source .venv/bin/activate
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

# Auto-open browser in background if a desktop display exists
(sleep 2 && (xdg-open "http://127.0.0.1:8000" 2>/dev/null || open "http://127.0.0.1:8000" 2>/dev/null || true)) &

echo ""
echo "======================================================="
echo " App URL: http://127.0.0.1:8000"
echo " Press Ctrl+C in this terminal to stop the server."
echo "======================================================="
echo ""

exec "$PYTHON" -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000
