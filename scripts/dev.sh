#!/usr/bin/env bash
# AgentOS one-command dev launcher (macOS / Linux).
# Installs Python deps, builds the web UI, and starts the server.
#
# Usage:  ./scripts/dev.sh [PORT]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8000}"

echo "==> Installing Python dependencies..."
python -m pip install -e "$ROOT"

echo "==> Building web UI..."
( cd "$ROOT/web" && npm install && npm run build )

echo "==> Starting AgentOS on http://127.0.0.1:$PORT ..."
python -m uvicorn server.main:app --host 127.0.0.1 --port "$PORT"
