<#
.SYNOPSIS
  Install and start the Agency Platform on a Windows machine.

.DESCRIPTION
  One script from a machine with nothing on it to a running backend and a
  desktop client at the login screen. No Docker.

  It is safe to run twice. Every step checks what is already there and does
  only what is missing, so re-running after a failure continues rather than
  starting over, and re-running a working install changes nothing.

  What it will not do quietly:

  * It never overwrites an existing `backend/config/.env`. That file holds the
    JWT signing key and the database password; replacing it would invalidate
    every issued token and lock the application out of its own database.
  * It does not install system software unless asked with -InstallPrerequisites.
    Installing PostgreSQL on someone's machine is not a thing to do as a side
    effect of running a script that looked like it would set up an application.
  * It refuses to run against a half-configured TLS setup rather than falling
    back to plain HTTP while the operator believes otherwise.

.PARAMETER BindHost
  What the backend listens on. 127.0.0.1 (the default) is reachable only from
  this machine. Use 0.0.0.0 to serve clients on the local network.

.PARAMETER CertFile
  TLS certificate. With -KeyFile, the backend serves HTTPS. Without them it
  serves plain HTTP, which the desktop client accepts on a private network and
  refuses to a public address.

.PARAMETER DryRun
  Report every step and change nothing. Run this first on a machine you care
  about.

.EXAMPLE
  .\install.ps1 -DryRun
  Shows what would happen, touches nothing.

.EXAMPLE
  .\install.ps1
  Installs for this machine only, on http://127.0.0.1:8000.

.EXAMPLE
  .\install.ps1 -BindHost 0.0.0.0 -WithDemoData
  Serves the local network over plain HTTP and seeds the four demo firms.

.EXAMPLE
  .\install.ps1 -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key
  Serves the local network over HTTPS. Every client machine has to trust that
  certificate.
#>
[CmdletBinding()]
param(
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 8000,
  [string]$CertFile,
  [string]$KeyFile,
  [string]$DatabaseHost = 'localhost',
  [int]$DatabasePort = 5432,
  [string]$DatabaseName = 'agency_platform',
  [string]$DatabaseUser = 'postgres',
  [securestring]$DatabasePassword,
  [securestring]$AdminPassword,
  [switch]$WithDemoData,
  [switch]$InstallPrerequisites,
  [switch]$SkipStart,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$script:RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$script:BackendRoot = Join-Path $script:RepoRoot 'backend'
$script:EnvPath = Join-Path $script:BackendRoot 'config\.env'
$script:Venv = Join-Path $script:BackendRoot '.venv\Scripts\python.exe'
$script:Failed = $false

function Write-Step { param([string]$Text) Write-Host "`n== $Text" -ForegroundColor Cyan }
function Write-Done { param([string]$Text) Write-Host "   $Text" -ForegroundColor Green }
function Write-Skip { param([string]$Text) Write-Host "   $Text" -ForegroundColor DarkGray }
function Write-Warn { param([string]$Text) Write-Host "   $Text" -ForegroundColor Yellow }

function Stop-Install {
  param([string]$Problem, [string]$Fix)
  Write-Host "`nInstall stopped: $Problem" -ForegroundColor Red
  if ($Fix) { Write-Host "  $Fix" -ForegroundColor Red }
  exit 1
}

# -- 0. Arguments that contradict each other -------------------------------
# Caught before anything is changed, so a typo cannot leave a half-install.

if ($CertFile -and -not $KeyFile) { Stop-Install 'CertFile was given without KeyFile.' 'TLS needs both.' }
if ($KeyFile -and -not $CertFile) { Stop-Install 'KeyFile was given without CertFile.' 'TLS needs both.' }
foreach ($file in @($CertFile, $KeyFile)) {
  if ($file -and -not (Test-Path $file)) { Stop-Install "Certificate file not found: $file" }
}
$scheme = if ($CertFile) { 'https' } else { 'http' }

Write-Host "Agency Platform installer"
Write-Host "  repository: $script:RepoRoot"
Write-Host "  backend:    ${scheme}://${BindHost}:${Port}"
if ($DryRun) { Write-Host "  DRY RUN -- nothing will be changed" -ForegroundColor Yellow }

# -- 1. Prerequisites -------------------------------------------------------

Write-Step 'Checking prerequisites'

function Test-Command { param([string]$Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

$missing = @()

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $missing += @{ Name = 'Python 3.13+'; Winget = 'Python.Python.3.13' }
} else {
  $version = & python --version 2>&1
  if ($version -match '(\d+)\.(\d+)') {
    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 13)) {
      $missing += @{ Name = "Python 3.13+ (found $version)"; Winget = 'Python.Python.3.13' }
    } else { Write-Done "Python: $version" }
  }
}

# PostgreSQL is deliberately not checked here. Looking for `psql` on PATH or a
# `postgresql*` service says nothing useful: on this project's own development
# machine the server runs in Docker, so both checks find nothing while the
# database works perfectly. The question that matters is whether the server
# answers, and that is asked in the database step below -- after the Python
# environment exists to ask it with.

if ($missing.Count -gt 0) {
  foreach ($item in $missing) { Write-Warn "missing: $($item.Name)" }
  if (-not $InstallPrerequisites) {
    $commands = ($missing | ForEach-Object { "winget install --id $($_.Winget) --accept-package-agreements --accept-source-agreements" }) -join "`n  "
    Stop-Install 'Prerequisites are missing.' "Install them and run again, or re-run with -InstallPrerequisites:`n  $commands"
  }
  if (-not (Test-Command 'winget')) {
    Stop-Install 'winget is not available, so prerequisites cannot be installed automatically.' 'Install Python 3.13+ and PostgreSQL 17 by hand, then run this again.'
  }
  foreach ($item in $missing) {
    if ($DryRun) { Write-Skip "would install $($item.Name) via winget"; continue }
    Write-Host "   installing $($item.Name)..."
    & winget install --id $item.Winget --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
      Stop-Install "winget could not install $($item.Name)." 'Check the network connection, or install it by hand and run this again.'
    }
  }
  Write-Warn 'A new terminal may be needed for the installed tools to appear on PATH.'
}

# -- 2. Configuration -------------------------------------------------------

Write-Step 'Configuration'

if (Test-Path $script:EnvPath) {
  Write-Skip "config\.env exists -- left alone (it holds the signing key and database password)"
} elseif ($DryRun) {
  Write-Skip 'would write backend\config\.env with a generated signing key'
} else {
  if (-not $DatabasePassword) { $DatabasePassword = Read-Host -AsSecureString "PostgreSQL password for '$DatabaseUser'" }
  if (-not $AdminPassword) { $AdminPassword = Read-Host -AsSecureString 'Password for the platform administrator (first login)' }

  $plainDb = [System.Net.NetworkCredential]::new('', $DatabasePassword).Password
  $plainAdmin = [System.Net.NetworkCredential]::new('', $AdminPassword).Password
  if ([string]::IsNullOrWhiteSpace($plainDb)) { Stop-Install 'The database password cannot be empty.' }
  if ([string]::IsNullOrWhiteSpace($plainAdmin)) { Stop-Install 'The administrator password cannot be empty.' }

  # A real signing key, not the development one. The application refuses to
  # start outside development with the development key, and this is what stops
  # an install inheriting it from the example file.
  $bytes = [byte[]]::new(48)
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $jwtKey = [Convert]::ToBase64String($bytes)

  $example = Join-Path $script:BackendRoot 'config\.env.example'
  if (-not (Test-Path $example)) { Stop-Install "Missing $example -- this does not look like a full checkout." }

  $lines = Get-Content $example | ForEach-Object {
    switch -Regex ($_) {
      '^AGENCY_ENVIRONMENT=' { 'AGENCY_ENVIRONMENT=production'; break }
      '^AGENCY_JWT_SECRET_KEY=' { "AGENCY_JWT_SECRET_KEY=$jwtKey"; break }
      '^AGENCY_DATABASE_PASSWORD=' { "AGENCY_DATABASE_PASSWORD=$plainDb"; break }
      '^AGENCY_BOOTSTRAP_ADMIN_PASSWORD=' { "AGENCY_BOOTSTRAP_ADMIN_PASSWORD=$plainAdmin"; break }
      '^AGENCY_DATABASE_HOST=' { "AGENCY_DATABASE_HOST=$DatabaseHost"; break }
      '^AGENCY_DATABASE_NAME=' { "AGENCY_DATABASE_NAME=$DatabaseName"; break }
      '^AGENCY_DATABASE_USERNAME=' { "AGENCY_DATABASE_USERNAME=$DatabaseUser"; break }
      '^# AGENCY_DATABASE_PORT=' { "AGENCY_DATABASE_PORT=$DatabasePort"; break }
      default { $_ }
    }
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $script:EnvPath) | Out-Null
  Set-Content -Path $script:EnvPath -Value $lines -Encoding utf8
  Write-Done 'wrote backend\config\.env with a generated signing key'
  Write-Warn 'Back that file up. Losing the signing key signs every user out; losing it and the database password locks the application out of its own data.'
}

# -- 3. Python environment --------------------------------------------------

Write-Step 'Python environment'

if (Test-Path $script:Venv) {
  Write-Skip '.venv exists'
} elseif ($DryRun) {
  Write-Skip 'would create backend\.venv and install dependencies'
} else {
  Push-Location $script:BackendRoot
  try {
    if (Test-Command 'uv') {
      & uv sync
      if ($LASTEXITCODE -ne 0) { Stop-Install 'uv sync failed.' 'Check the network connection and run again.' }
    } else {
      & python -m venv .venv
      & $script:Venv -m pip install --upgrade pip --quiet
      & $script:Venv -m pip install -e . --quiet
      if ($LASTEXITCODE -ne 0) { Stop-Install 'Installing Python dependencies failed.' 'Check the network connection and run again.' }
    }
  } finally { Pop-Location }
  Write-Done 'dependencies installed'
}

if (-not $DryRun -and -not (Test-Path $script:Venv)) {
  Stop-Install 'The virtual environment was not created.' 'Run again, or create it by hand with: python -m venv backend\.venv'
}

# -- 4. Database ------------------------------------------------------------

Write-Step 'Database'

if ($DryRun) {
  Write-Skip "would create the database '$DatabaseName' if it does not exist"
} else {
  $createDb = @'
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config.settings import Settings
from app.core.database.config import database_config_from_settings

settings = Settings()
url = make_url(database_config_from_settings(settings).url)
target = url.database
# Connect to the maintenance database: you cannot create a database from
# inside itself.
admin = url.set(database="postgres")
engine = create_engine(admin.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
try:
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
        ).scalar()
        if exists:
            print(f"exists:{target}")
        else:
            conn.execute(text(f'CREATE DATABASE "{target}"'))
            print(f"created:{target}")
except Exception as exc:  # noqa: BLE001 - the message is the whole point here
    print(f"error:{exc}", file=sys.stderr)
    raise SystemExit(2)
'@
  Push-Location $script:BackendRoot
  try {
    $result = $createDb | & $script:Venv - 2>&1
    if ($LASTEXITCODE -ne 0 -and $InstallPrerequisites -and $DatabaseHost -in @('localhost', '127.0.0.1', '::1')) {
      # The server did not answer and the caller asked for prerequisites, so
      # this is the clean-machine case: install PostgreSQL and ask once more.
      # Probing first is what stops a machine that already runs PostgreSQL --
      # in Docker, in WSL, on another box -- being given a second copy it does
      # not need.
      if (-not (Test-Command 'winget')) {
        Stop-Install 'PostgreSQL did not answer and winget is not available to install it.' 'Install PostgreSQL 17 by hand, then run this again.'
      }
      Write-Host '   PostgreSQL did not answer. Installing it...'
      & winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements --silent
      if ($LASTEXITCODE -ne 0) { Stop-Install 'winget could not install PostgreSQL.' 'Check the network connection, or install it by hand and run this again.' }
      Write-Warn 'PostgreSQL installed. Its service may need a moment, and this shell may need to be reopened for new PATH entries.'
      Start-Sleep -Seconds 10
      $result = $createDb | & $script:Venv - 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
      $advice = @(
        "  Checked ${DatabaseHost}:${DatabasePort} as '$DatabaseUser'.",
        '  Likely causes, in the order worth checking:',
        '    - PostgreSQL is not running (a service, a container, or another machine).',
        "    - The password in backend\config\.env does not match the server's.",
        '    - The host or port is wrong -- pass -DatabaseHost and -DatabasePort.',
        '    - PostgreSQL is not installed. Re-run with -InstallPrerequisites, or:',
        '        winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements'
      ) -join "`n"
      Stop-Install 'Could not reach PostgreSQL.' "$result`n$advice"
    }
    if ("$result" -like 'created:*') { Write-Done "created database '$DatabaseName'" } else { Write-Skip "database '$DatabaseName' exists" }
  } finally { Pop-Location }
}

# -- 5. Migrations ----------------------------------------------------------
# Every store, not just the platform schema. `alembic upgrade head` advances
# one schema chosen by AGENCY_DATABASE_SCHEMA, so a firm store is silently left
# behind and nothing reports it until a query hits a missing column.

Write-Step 'Migrations'

Push-Location $script:BackendRoot
try {
  if ($DryRun) {
    & $script:Venv scripts/migrate_all_stores.py --dry-run
    if ($LASTEXITCODE -ne 0) { Write-Warn 'Could not read the stores. On a fresh machine that is expected: the database does not exist yet.' }
  } else {
    & $script:Venv scripts/migrate_all_stores.py --yes
    if ($LASTEXITCODE -ne 0) { Stop-Install 'One or more stores failed to migrate.' 'The output above names which. Fix it and run this again -- the script reports every store rather than stopping at the first.' }
    Write-Done 'every store is at head'
  }
} finally { Pop-Location }

# -- 6. Demo data (optional) ------------------------------------------------

if ($WithDemoData) {
  Write-Step 'Demo data'
  if ($DryRun) {
    Write-Skip 'would seed four demo firms and three financial years of trading'
  } else {
    Push-Location $script:BackendRoot
    try {
      & $script:Venv scripts/seed_multi_firm_demo.py
      if ($LASTEXITCODE -ne 0) { Stop-Install 'Seeding the demo data failed.' 'The application is installed and migrated; re-run the seeder by hand to see the failure.' }
      Write-Done 'demo firms seeded'
    } finally { Pop-Location }
  }
}

# -- 7. Desktop client ------------------------------------------------------

Write-Step 'Desktop client'

$desktopExe = Join-Path $script:RepoRoot 'desktop\build\windows\x64\runner\Release\agency_desktop.exe'
if (Test-Path $desktopExe) {
  Write-Done 'client is built'
} elseif (Test-Command 'flutter') {
  if ($DryRun) {
    Write-Skip 'would build the desktop client with flutter build windows --release'
  } else {
    Push-Location (Join-Path $script:RepoRoot 'desktop')
    try {
      & flutter build windows --release --dart-define="API_BASE_URL=${scheme}://${BindHost}:${Port}"
      if ($LASTEXITCODE -ne 0) { Write-Warn 'Building the client failed. The backend is installed; build the client by hand.' }
      else { Write-Done 'client built' }
    } finally { Pop-Location }
  }
} else {
  Write-Warn 'No built client and no Flutter SDK. The backend is usable on its own; install Flutter to build the client, or copy a build from another machine.'
}

# -- 8. Start ---------------------------------------------------------------

if ($SkipStart -or $DryRun) {
  Write-Step 'Done'
  Write-Host "   Start the backend with:"
  $startArgs = "-BindHost $BindHost -Port $Port"
  if ($CertFile) { $startArgs += " -CertFile `"$CertFile`" -KeyFile `"$KeyFile`"" }
  Write-Host "     powershell -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1 $startArgs -NoReload"
  exit 0
}

Write-Step 'Starting the backend'
if (-not $CertFile -and $BindHost -ne '127.0.0.1') {
  Write-Warn 'Plain HTTP on a network interface: passwords cross the wire in clear text. Use -CertFile and -KeyFile on any network you do not control.'
}

$startScript = Join-Path $script:BackendRoot 'scripts\start_backend.ps1'
$startArgs = @('-BindHost', $BindHost, '-Port', "$Port", '-NoReload', '-SkipSync')
if ($CertFile) { $startArgs += @('-CertFile', $CertFile, '-KeyFile', $KeyFile) }
Start-Process -FilePath 'powershell' -ArgumentList (@('-ExecutionPolicy', 'Bypass', '-File', $startScript) + $startArgs)

Write-Host '   waiting for the backend to answer...'
$healthy = $false
foreach ($attempt in 1..30) {
  Start-Sleep -Seconds 2
  try {
    $uri = "${scheme}://${BindHost}:${Port}/health"
    if ($BindHost -eq '0.0.0.0') { $uri = "${scheme}://127.0.0.1:${Port}/health" }
    # -SkipCertificateCheck is PowerShell 6+, and install.bat runs Windows
    # PowerShell 5.1. Passing it there throws a parameter error that reads like
    # the backend failed, so it is only added when the shell has it.
    $webArgs = @{ Uri = $uri; TimeoutSec = 4; ErrorAction = 'Stop'; UseBasicParsing = $true }
    if ((Get-Command Invoke-WebRequest).Parameters.ContainsKey('SkipCertificateCheck')) {
      $webArgs['SkipCertificateCheck'] = $true
    }
    $response = Invoke-WebRequest @webArgs
    if ($response.StatusCode -eq 200) { $healthy = $true; break }
  } catch { continue }
}
if (-not $healthy) {
  Stop-Install 'The backend did not answer /health within a minute.' 'Look at the newest file in backend\logs for the reason.'
}
Write-Done "backend answering on ${scheme}://${BindHost}:${Port}"

if (Test-Path $desktopExe) {
  Start-Process -FilePath $desktopExe
  Write-Done 'client started'
}

Write-Host "`nInstalled." -ForegroundColor Green
Write-Host "  Sign in as platform-admin@agency.local with the administrator password you set."
Write-Host "  It must be changed on first use, and it has no firm membership, so create a firm before opening firm screens."
