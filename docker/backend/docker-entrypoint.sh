#!/bin/bash
set -e

echo "Running migrations..."
uv run python manage.py migrate --noinput

# Carga de datos iniciales para cada módulo solo en desarrollo
if [ "$DJANGO_DEBUG" = "True" ] || [ "$DJANGO_DEBUG" = "true" ]; then
    echo "Development mode detected (DJANGO_DEBUG=True). Loading initial data..."
    
    echo "Loading initial data for users..."
    uv run python manage.py load_initial_users

    # Agregá más comandos de carga acá cuando sea necesario
else
    echo "Skipping initial data load."
fi

echo "Starting server..."
exec "$@"
