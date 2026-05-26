#!/bin/bash
# srchigh — One-command install script
# Usage: bash install.sh

set -e

echo "==> srchigh — eCourts Judgments Scraper Install"
echo ""

# Check Python
PY=$(command -v python3 || echo "")
if [ -z "$PY" ]; then
    echo "ERROR: Python 3.9+ required. Install it first."
    exit 1
fi

echo "[1] Checking Tesseract OCR..."
if command -v tesseract &>/dev/null; then
    echo "    Found: $(tesseract --version 2>&1 | head -1)"
else
    echo "    WARNING: tesseract not found."
    echo "    Install with:"
    echo "      macOS: brew install tesseract"
    echo "      Ubuntu: sudo apt install tesseract-ocr"
    echo "      Fedora: sudo dnf install tesseract"
fi

echo ""
echo "[2] Installing Python dependencies..."
pip3 install --user -r "$(dirname "$0")/requirements.txt" 2>&1 | tail -3

echo ""
echo "[3] Installing srchigh package..."
cd "$(dirname "$0")"
pip3 install --user -e . 2>&1 | tail -5 || {
    echo ""
    echo "    NOTE: system Python permissions may block install."
    echo "    You can still run directly:"
    echo "      python3 src/srchigh/main.py \"divorce\" 5 --court bombay"
    echo ""
    echo "    Or install with: pip3 install --user -e ."
    exit 0
}

echo ""
echo "==> Done! Run: srchigh \"divorce\" 5 --court bombay"
