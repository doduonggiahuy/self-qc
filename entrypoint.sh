#!/bin/sh
set -eu

if [ "${SKIP_BOOTSTRAP:-false}" != "true" ]; then
  python manage.py migrate --noinput
  python manage.py bootstrap_roles
fi
exec "$@"
