#!/usr/bin/env bash
# Container entrypoint: apply migrations, then serve HTTP + WebSockets on $PORT.
set -euo pipefail
cd /app/backend
python manage.py migrate --noinput
export BIND="0.0.0.0:${PORT:-8000}"
exec gunicorn -c /app/deploy/gunicorn.conf.py config.asgi:application
