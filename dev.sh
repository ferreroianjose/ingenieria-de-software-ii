#!/usr/bin/env bash
# Levanta Docker Compose (si hace falta) y Tailwind en modo watch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Falta .env. Copiá el ejemplo: cp .env.example .env"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker no está instalado o no está en el PATH."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose no está disponible."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm no está instalado (necesario para compilar Tailwind)."
  exit 1
fi

if [[ ! -x node_modules/.bin/tailwindcss ]]; then
  echo "Instalando dependencias npm..."
  npm install
fi

if [[ -z "$(docker compose ps web --status running -q 2>/dev/null || true)" ]]; then
  echo "Iniciando Docker Compose (db, web, qcluster)..."
  docker compose up -d
else
  echo "Docker Compose ya está en ejecución."
fi

cleanup() {
  local status=$?
  trap - INT TERM EXIT
  echo ""
  echo "Deteniendo Tailwind y Docker Compose..."
  docker compose down >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup INT TERM EXIT

echo ""
echo "App: http://localhost:8000"
echo "Tailwind watch activo. Ctrl+C detiene el watch y baja los contenedores."
echo ""

npm run tw:watch
