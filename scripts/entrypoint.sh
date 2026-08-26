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

# Optional bootstrap superuser. Runs on every boot, so it must be opt-in and
# idempotent: without DJANGO_SUPERUSER_PASSWORD set there is no account at all
# (never a default/guessable one), and if the email already exists we skip
# rather than let createsuperuser --noinput exit 1 and kill the boot.
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    su_email="${DJANGO_SUPERUSER_EMAIL:-}"
    if [ -z "${su_email}" ]; then
        echo "DJANGO_SUPERUSER_PASSWORD is set but DJANGO_SUPERUSER_EMAIL is not; skipping superuser bootstrap." >&2
    else
        export DJANGO_SUPERUSER_ROLE="${DJANGO_SUPERUSER_ROLE:-system_administrator}"
        if python manage.py shell -c "
import sys
from django.contrib.auth import get_user_model
sys.exit(0 if get_user_model().objects.filter(email='''${su_email}'''.lower()).exists() else 1)
"; then
            echo "Superuser ${su_email} already exists; skipping bootstrap."
        else
            echo "Creating bootstrap superuser ${su_email} (role: ${DJANGO_SUPERUSER_ROLE})..."
            python manage.py createsuperuser --noinput
        fi
    fi
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
