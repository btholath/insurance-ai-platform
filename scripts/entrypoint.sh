#!/usr/bin/env bash
set -euo pipefail

host="${POSTGRES_HOST:-db}"
port="${POSTGRES_PORT:-5432}"

echo "Waiting for Postgres at ${host}:${port}..."
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('${host}', ${port}))
except OSError:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "Postgres is accepting connections."

python manage.py migrate --noinput

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
