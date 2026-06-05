# Levanta Docker Compose (si hace falta) y Tailwind en modo watch.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Error "Falta .env. Copiá el ejemplo: Copy-Item .env.example .env"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker no está instalado o no está en el PATH."
}

$null = docker compose version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose no está disponible."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm no está instalado (necesario para compilar Tailwind)."
}

$tailwindBin = Join-Path "node_modules" ".bin/tailwindcss.cmd"
if (-not (Test-Path $tailwindBin)) {
    $tailwindBin = Join-Path "node_modules" ".bin/tailwindcss"
}
if (-not (Test-Path $tailwindBin)) {
    Write-Host "Instalando dependencias npm..."
    npm install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$running = docker compose ps web --status running -q 2>$null
if (-not $running) {
    Write-Host "Iniciando Docker Compose (db, web, qcluster)..."
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Docker Compose ya está en ejecución."
}

Write-Host ""
Write-Host "App: http://localhost:8000"
Write-Host "Tailwind watch activo. Ctrl+C detiene el watch y baja los contenedores."
Write-Host ""

try {
    npm run tw:watch
} finally {
    Write-Host ""
    Write-Host "Deteniendo Tailwind y Docker Compose..."
    docker compose down
}
