#!/usr/bin/env bash
# Start the Next.js frontend dev server
# Run from ~/prediction-tracker/frontend/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SCRIPT_DIR/node_modules" ]; then
  echo "Installing npm dependencies..."
  cd "$SCRIPT_DIR" && npm install
fi

echo "Starting frontend on http://localhost:3000"
cd "$SCRIPT_DIR"
npm run dev
