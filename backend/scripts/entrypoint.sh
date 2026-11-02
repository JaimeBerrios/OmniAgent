#!/bin/sh
set -eu

echo "===== ESPERANDO BASE DE DATOS ====="

python - <<'PY'
import os
import time
import psycopg

url = os.environ["DATABASE_URL"].replace(
    "postgresql+psycopg://",
    "postgresql://",
)

for attempt in range(30):
    try:
        with psycopg.connect(url, connect_timeout=3):
            print("PostgreSQL disponible.")
        break
    except psycopg.OperationalError:
        if attempt == 29:
            raise
        time.sleep(2)
PY

echo "===== EJECUTANDO MIGRACIONES ====="
python /app/scripts/migrate.py

echo "===== INICIANDO FASTAPI ====="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
