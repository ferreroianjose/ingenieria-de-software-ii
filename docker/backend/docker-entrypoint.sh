#!/bin/bash
set -e

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Starting server..."
exec "$@"
