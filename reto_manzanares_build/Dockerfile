FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/manzanares.db \
    API_HOST=0.0.0.0 \
    API_PORT=8080

WORKDIR /app

RUN addgroup --system manzanares \
    && adduser --system --ingroup manzanares --home /app manzanares \
    && mkdir -p /app/data /app/backups \
    && chown -R manzanares:manzanares /app

COPY --chown=manzanares:manzanares app.py pyproject.toml README.md /app/
COPY --chown=manzanares:manzanares manzanares_agent /app/manzanares_agent

USER manzanares

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["python", "app.py", "servir"]
