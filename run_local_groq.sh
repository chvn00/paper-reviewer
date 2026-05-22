#!/usr/bin/env bash
# Corre CHVN Paper Reviewer localmente con Groq API
set -euo pipefail

cd "$(dirname "$0")"

# Carga variables de .env si existe
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "${GROQ_API_KEY:-}" ]; then
  echo "❌  Falta GROQ_API_KEY. Crea un archivo .env con:"
  echo "    GROQ_API_KEY=gsk_xxxx"
  exit 1
fi

# Instala dependencias si falta alguna
.venv/bin/python -m pip install -q -r requirements.txt

echo "✅  Iniciando CHVN Paper Reviewer en http://localhost:8000"
exec .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
