#!/usr/bin/env bash
# Run a Django management command for cron/ops: deploy/manage.sh <command> [args...]
# settings.py loads the project .env (next to deploy/) by itself, so nothing is sourced
# here; real environment variables (e.g. from systemd) still take precedence.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec .venv/bin/python manage.py "$@"
