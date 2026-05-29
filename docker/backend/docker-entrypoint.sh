#!/bin/bash
set -e

if [ "$RUN_MIGRATIONS" = "True" ]; then
    echo "Running migrations..."
    uv run python manage.py migrate --noinput

    # Carga de datos iniciales para cada módulo solo en desarrollo
    if [ "$DJANGO_DEBUG" = "True" ] || [ "$DJANGO_DEBUG" = "true" ]; then
        echo "Development mode detected (DJANGO_DEBUG=True). Loading initial data..."
        
        echo "Loading initial data for users module..."
        uv run python manage.py load_initial_users

        echo "Loading initial data for classes module..."
        uv run python manage.py load_initial_classes

        echo "Loading initial data for payments module..."
        uv run python manage.py load_initial_payments
    else
        echo "Skipping initial data load."
    fi
fi

echo "Starting command: $@"
exec "$@"
