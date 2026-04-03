#!/usr/bin/env bash
# Start the FastAPI backend
# Run from ~/prediction-tracker/backend/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create .env if it doesn't exist
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo "Created .env from .env.example — please set ANTHROPIC_API_KEY"
fi

# Set up venv if needed
if [ ! -d "$SCRIPT_DIR/venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$SCRIPT_DIR/venv"
fi

source "$SCRIPT_DIR/venv/bin/activate"

echo "Installing/updating dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" -q

echo "Starting backend on http://localhost:8000"
cd "$SCRIPT_DIR"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
