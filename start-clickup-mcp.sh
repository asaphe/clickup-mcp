#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CLICKUP_API_TOKEN:-}" ]]; then
    echo "CLICKUP_API_TOKEN is not set." >&2
    echo "Get a personal token at: https://app.clickup.com/settings/apps" >&2
    echo "Then run: python3 $(dirname "$0")/setup_mcp.py" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec uv run --directory "$SCRIPT_DIR" python -m clickup_mcp_server
