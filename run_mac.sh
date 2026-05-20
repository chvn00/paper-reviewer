#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt

if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew services start ollama >/dev/null
  else
    echo "Ollama is not running. Start Ollama, then re-run this script."
    exit 1
  fi
fi

if ! ollama list | grep -q "llama3.2"; then
  ollama pull llama3.2
fi

exec .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
