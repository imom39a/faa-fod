#!/usr/bin/env bash
# Start the always-on agent: API, dashboard, dispatcher and a display-only console in this terminal.
# People sign in on the chat page in the browser. Options are passed through (see --help):
#   ./run-agent.sh --play --speed 2     start the scripted schedule at once
#   FOD_AGENT=code ./run-agent.sh       never call the model (code-only routing)
set -euo pipefail
cd "$(dirname "$0")"
[ -d app/frontend/dist ] || echo "Dashboard not built (run ./setup.sh). The agent and its API still start."
cd app/backend
# A default spend cap, so a mistake cannot drain the API balance. Override by exporting FOD_MAX_SPEND_USD.
export FOD_MAX_SPEND_USD="${FOD_MAX_SPEND_USD:-1.00}"
export FOD_AGENT="${FOD_AGENT:-on}"
export FOD_TIMELINE="${FOD_TIMELINE:-timeline-agent.json}"
exec uv run python -m fodgate.agent --port "${PORT:-8000}" "$@"
