#!/usr/bin/env bash
# Start the PoC: API and dashboard on http://localhost:8000 (override with PORT=...).
set -euo pipefail
cd "$(dirname "$0")"
[ -d app/frontend/dist ] || { echo "Dashboard not built yet. Run ./setup.sh first."; exit 1; }
cd app/backend
# A default spend cap, so a mistake cannot drain the API balance. Override by exporting FOD_MAX_SPEND_USD.
export FOD_MAX_SPEND_USD="${FOD_MAX_SPEND_USD:-1.00}"
echo "Open http://localhost:${PORT:-8000} and press Play."
exec uv run uvicorn fodgate.api:app --port "${PORT:-8000}"
