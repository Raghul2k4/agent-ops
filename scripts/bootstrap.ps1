<#
.SYNOPSIS
    One-shot local bootstrap for AgentOps.

.DESCRIPTION
    Creates the Python virtualenv, installs backend + frontend dependencies,
    copies .env.example to backend/.env if missing, and applies database
    migrations when the database is reachable.

    Idempotent: safe to re-run.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipMigrations
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'apps\web'

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message" -ForegroundColor Cyan
}

Write-Step 'Environment check'
& (Join-Path $PSScriptRoot 'verify_env.ps1') | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host 'verify_env.ps1 reported failures; continuing with setup anyway.' -ForegroundColor Yellow
}

Write-Step 'Backend virtualenv (Python 3.12)'
if (-not (Test-Path (Join-Path $backend '.venv'))) {
    & py -3.12 -m venv (Join-Path $backend '.venv')
}
$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "virtualenv creation failed: $py" }
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -e "$backend[dev]" --quiet
Write-Host "Backend dependencies installed." -ForegroundColor Green

Write-Step 'Backend environment file'
$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Write-Host "Created $envFile from .env.example - review the DATABASE_URL before running migrations." -ForegroundColor Yellow
} else {
    Write-Host "$envFile already exists - left untouched." -ForegroundColor DarkGray
}

if (-not $SkipFrontend) {
    Write-Step 'Frontend dependencies'
    if (Test-Path (Join-Path $frontend 'package.json')) {
        Push-Location $frontend
        try { npm install --silent; Write-Host 'Frontend dependencies installed.' -ForegroundColor Green }
        finally { Pop-Location }
    } else {
        Write-Host 'apps/web/package.json not found - skipping.' -ForegroundColor Yellow
    }
}

if (-not $SkipMigrations) {
    Write-Step 'Database migrations'
    Push-Location $backend
    try {
        & $py -m alembic upgrade head
        if ($LASTEXITCODE -eq 0) { Write-Host 'Migrations applied.' -ForegroundColor Green }
        else { Write-Host 'Migrations did not run - check DATABASE_URL (see docs/deployment.md section 2).' -ForegroundColor Yellow }
    } finally { Pop-Location }
}

Write-Step 'Done'
Write-Host 'Next steps:' -ForegroundColor White
Write-Host '  1. Review backend/.env (DATABASE_URL, SESSION_SECRET)'
Write-Host '  2. cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload'
Write-Host '  3. cd apps/web; npm run dev'
Write-Host '  4. cd backend; python -m pytest -q'
