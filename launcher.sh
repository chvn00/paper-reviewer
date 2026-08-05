#!/bin/bash
# Paper Reviewer Launcher
# Inicia el servidor FastAPI y abre el navegador

cd /Users/cesarvalencia/Downloads/Paper_Reviewer_mac

# Matar proceso existente en puerto 8000
lsof -ti :8000 | xargs kill -9 2>/dev/null
sleep 1

# Usar python3 del sistema directamente
/usr/bin/python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# Esperar a que el servidor esté listo (máximo 30 segundos)
for i in {1..30}; do
    if /usr/bin/curl -s http://localhost:8000 > /dev/null 2>&1; then
        echo "✓ Server ready"
        break
    fi
    sleep 1
done

# Abrir navegador
/usr/bin/open http://localhost:8000

# Mantener el script corriendo
wait $SERVER_PID
