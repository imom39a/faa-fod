#!/usr/bin/env bash
# One-time setup for the Gate FOD Inspection PoC. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2"; exit 1; }; }
need uv   "Install from https://docs.astral.sh/uv/ (it also installs Python 3.12 for you)."
need node "Install Node.js 20 or newer from https://nodejs.org/."
need npm  "It ships with Node.js."

node_major=$(node -p 'process.versions.node.split(".")[0]')
if [ "$node_major" -lt 20 ]; then echo "Node.js 20 or newer is required (found $(node -v))."; exit 1; fi

echo "==> Backend dependencies"
(cd app/backend && uv sync)

echo "==> Dashboard dependencies and build"
(cd app/frontend && npm ci && npm run build)

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example. Add ANTHROPIC_API_KEY there if you have one (optional for the scripted demo)."
fi

echo
echo "Setup complete. Start the demo with:  ./run.sh"
