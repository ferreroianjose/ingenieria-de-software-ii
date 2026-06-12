#!/bin/bash
set -e

if [ "$RUN_MIGRATIONS" = "True" ]; then
    echo "Running migrations..."
    uv run python manage.py migrate --noinput

    if { [ "$DJANGO_DEBUG" = "True" ] || [ "$DJANGO_DEBUG" = "true" ]; } \
        && [ "$SKIP_INITIAL_DATA" != "True" ] && [ "$SKIP_INITIAL_DATA" != "true" ]; then
        echo "Development mode detected (DJANGO_DEBUG=True). Loading initial data..."
        
        echo "Seeding development data..."
        uv run python manage.py seed
    else
        echo "Skipping initial data load."
    fi
fi

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

echo "Starting command: $@"
exec "$@"
