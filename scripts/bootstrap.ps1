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
    # The SQL files in supabase/migrations are the single schema authority (no Alembic).
    # Hosted Supabase: prefer `supabase db push` (see docs/deployment.md 2.3).
    # Here we apply them with psql so a local PostgreSQL test database stays in sync.
    $migrations = Get-ChildItem (Join-Path $root 'supabase\migrations') -Filter '*.sql' |
        Sort-Object Name
    $envFile = Join-Path $backend '.env'
    $dbUrl = if (Test-Path $envFile) {
        (Select-String -Path $envFile -Pattern '^\s*DATABASE_URL\s*=' |
            Select-Object -First 1).Line -replace '^\s*DATABASE_URL\s*=\s*', ''
    } else { '' }

    if ([string]::IsNullOrWhiteSpace($dbUrl) -or $dbUrl -match '<[^>]+>') {
        Write-Host 'DATABASE_URL is not configured - skipping migrations.' -ForegroundColor Yellow
        Write-Host 'Set it in backend/.env, or run: supabase db push --db-url ...' -ForegroundColor Yellow
    } elseif ($migrations.Count -eq 0) {
        Write-Host 'No migration files found - skipping.' -ForegroundColor Yellow
    } else {
        $psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
        if (-not $psql) {
            $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($candidate) { $psql = $candidate.FullName }
        }
        if (-not $psql) {
            Write-Host 'psql not found - skipping migrations. Install the PostgreSQL client or set PSQL_BIN.' -ForegroundColor Yellow
        } else {
            $dsn = $dbUrl.Trim().Trim('"').Trim("'") -replace '^postgresql\+[a-z0-9]+://', 'postgresql://'
            foreach ($migration in $migrations) {
                & $psql $dsn '-v' 'ON_ERROR_STOP=1' '-f' $migration.FullName | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "Migration failed: $($migration.Name)" -ForegroundColor Red
                    break
                }
            }
            if ($LASTEXITCODE -eq 0) { Write-Host 'Migrations applied.' -ForegroundColor Green }
        }
    }
}

Write-Step 'Done'
Write-Host 'Next steps:' -ForegroundColor White
Write-Host '  1. Review backend/.env (DATABASE_URL, AUTH_MODE, SUPABASE_URL)'
Write-Host '  2. cd backend; .\.venv\Scripts\Activate.ps1; python -m app'
Write-Host '  3. cd apps/web; npm run dev'
Write-Host '  4. cd backend; python -m pytest -q'
