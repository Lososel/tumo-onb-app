#!/bin/bash
# Installs backend (Python venv) and frontend (npm) dependencies for Claude Code cloud sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Backend: virtualenv at backend/.venv (pytest, httpx, ruff + app deps)
cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements-dev.txt

# Frontend: npm install (not ci) so the cached container state is reused
cd "$ROOT/frontend"
npm install --no-audit --no-fund --loglevel=error

# Make backend tools available on PATH for the session
echo "export PATH=\"$ROOT/backend/.venv/bin:\$PATH\"" >> "${CLAUDE_ENV_FILE:-/dev/null}"
