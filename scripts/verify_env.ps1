<#
.SYNOPSIS
    Verifies that the local machine has everything AgentOps needs to run.

.DESCRIPTION
    Checks each prerequisite and reports OK / MISSING / UNREACHABLE with a
    remediation hint. Read-only: never installs or modifies anything.
#>
[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$FrontendDir = (Join-Path $PSScriptRoot '..\apps\web')
)

$ErrorActionPreference = 'Continue'
$script:Failures = 0

function Write-Header {
    Write-Host ''
    Write-Host 'AgentOps environment check' -ForegroundColor Cyan
    Write-Host '---------------------------' -ForegroundColor Cyan
}

function Test-Check {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Probe,
        [string]$Remediation = ''
    )

    try {
        $result = & $Probe
        if ($result -is [bool]) {
            if ($result) {
                Write-Host ("  [ OK ] {0}" -f $Name) -ForegroundColor Green
            } else {
                Write-Host ("  [FAIL] {0}" -f $Name) -ForegroundColor Red
                if ($Remediation) { Write-Host ("         -> {0}" -f $Remediation) -ForegroundColor Yellow }
                $script:Failures++
            }
            return
        }
        Write-Host ("  [ OK ] {0}: {1}" -f $Name, $result) -ForegroundColor Green
    } catch {
        Write-Host ("  [FAIL] {0}: {1}" -f $Name, $_.Exception.Message) -ForegroundColor Red
        if ($Remediation) { Write-Host ("         -> {0}" -f $Remediation) -ForegroundColor Yellow }
        $script:Failures++
    }
}

Write-Header

Write-Host 'Toolchain' -ForegroundColor White
Test-Check -Name 'git' -Probe { (git --version) } -Remediation 'Install Git for Windows.'
Test-Check -Name 'python 3.12' -Probe {
    $p = & py -3.12 -c 'import sys; print(sys.version.split()[0])' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'py -3.12 launcher not available' }
    $p
} -Remediation 'Install Python 3.12 (py -3.12 -m venv .venv).'
Test-Check -Name 'node' -Probe { (node --version) } -Remediation 'Install Node.js 20+.'
Test-Check -Name 'npm' -Probe { (npm --version) } -Remediation 'Install Node.js 20+.'

Write-Host ''
Write-Host 'Services' -ForegroundColor White
Test-Check -Name 'PostgreSQL service' -Probe {
    $svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $svc) { throw 'no postgresql* service found' }
    if ($svc.Status -ne 'Running') { throw "service is $($svc.Status)" }
    $svc.Name
} -Remediation 'Start it: Start-Service postgresql-x64-18'

Test-Check -Name 'PostgreSQL port 5432' -Probe {
    $conn = Get-NetTCPConnection -State Listen -LocalPort 5432 -ErrorAction SilentlyContinue
    if (-not $conn) { throw 'nothing listening on 5432' }
    'listening'
} -Remediation 'Start the PostgreSQL service.'

Test-Check -Name 'Database connection' -Probe {
    if (-not $DatabaseUrl) { throw 'DATABASE_URL not set (copy .env.example to backend/.env)' }
    $env:AGENTOPS_CHECK_URL = $DatabaseUrl
    $out = & py -3.12 -c @"
import os, sys
url = os.environ['AGENTOPS_CHECK_URL']
try:
    import psycopg
except ImportError:
    print('psycopg not installed yet (run scripts/bootstrap.ps1)'); sys.exit(0)
try:
    with psycopg.connect(url, connect_timeout=5) as conn:
        print(conn.execute('select current_user, current_database()').fetchone())
except Exception as exc:
    print('unreachable:', exc)
"@ 2>&1 | Out-String
    if ($out -match 'unreachable') { throw ($out.Trim()) }
    if ($out -match 'psycopg not installed') { 'psycopg pending bootstrap' }
    else { $out.Trim() }
} -Remediation 'See docs/deployment.md section 2 (password reset + role creation).'

Write-Host ''
Write-Host 'Optional services (dev can proceed without them)' -ForegroundColor White
Test-Check -Name 'Docker (container workflow)' -Probe {
    $d = & docker --version 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'docker not installed' }
    $d
} -Remediation 'Optional. The Compose path is exercised in CI.'

Test-Check -Name 'Redis (durable job queue)' -Probe {
    $r = & redis-cli --version 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'redis not installed' }
    $r
} -Remediation 'Optional. Falls back to the in-process worker (deviation D2).'

Test-Check -Name 'Ollama (local models)' -Probe {
    $o = & ollama --version 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'ollama not installed' }
    $o
} -Remediation 'Optional. Use the clearly-labelled simulation provider offline.'

Write-Host ''
if ($script:Failures -eq 0) {
    Write-Host 'All required checks passed.' -ForegroundColor Green
    exit 0
} else {
    Write-Host ("{0} required check(s) failed." -f $script:Failures) -ForegroundColor Red
    exit 1
}
