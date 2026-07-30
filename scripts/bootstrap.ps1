[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker with Compose v2 is required."
}

if (-not (Test-Path -LiteralPath ".env.development")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env.development"
    Write-Host "Created .env.development from .env.example."
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed to start." }

docker compose run --rm backend alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }

docker compose --profile tools run --rm verify
if ($LASTEXITCODE -ne 0) { throw "Environment verification failed." }

Write-Host "Fashion Network is ready at http://localhost"
