#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

ruff_bin="ruff"
mypy_bin="mypy"
pytest_bin="pytest"

if [[ -x ".venv/bin/ruff" ]]; then
  ruff_bin=".venv/bin/ruff"
fi

if [[ -x ".venv/bin/mypy" ]]; then
  mypy_bin=".venv/bin/mypy"
fi

if [[ -x ".venv/bin/pytest" ]]; then
  pytest_bin=".venv/bin/pytest"
fi

"$ruff_bin" check .
"$mypy_bin" app tests

GOOGLE_API_KEY=dummy \
ELASTIC_MCP_URL=dummy \
FIRESTORE_EMULATOR_HOST=dummy \
NASA_FIRMS_API_KEY=dummy \
ENVIRONMENT=test \
"$pytest_bin" -q

(
  cd frontend
  npm run lint
  npm run build
)
