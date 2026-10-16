#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
local_python="${HOME}/.local/share/agent-shared-system/venv/bin/python"
if [[ -x "$local_python" ]]; then
  exec "$local_python" -B "$project_dir/scripts/setup.py" --interactive
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python 3.12+ in this system, then run this launcher again." >&2
  exit 1
fi
exec python3 -B "$project_dir/scripts/setup.py" --interactive
