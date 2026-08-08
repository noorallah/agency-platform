param(
  [switch]$SkipSync,
  [switch]$NoReload,
  [string]$LogPath
)

$ErrorActionPreference = 'Stop'

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $backendRoot

if (-not (Test-Path 'config\.env')) {
  throw 'Missing config\.env. Copy config\.env.example to config\.env first.'
}

if ([string]::IsNullOrWhiteSpace($LogPath)) {
  $logDir = Join-Path $backendRoot 'logs'
  $logName = 'backend-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss')
  $LogPath = Join-Path $logDir $logName
}

$logDirectory = Split-Path -Parent $LogPath
if (-not [string]::IsNullOrWhiteSpace($logDirectory)) {
  New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
}

Write-Host "Log file: $LogPath"

if (-not $SkipSync) {
  & uv sync --group dev 2>&1 | Tee-Object -FilePath $LogPath -Append
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

"[$(Get-Date -Format o)] Applying migrations..." | Tee-Object -FilePath $LogPath -Append
& uv run --no-sync python -m alembic upgrade head 2>&1 | Tee-Object -FilePath $LogPath -Append
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

$uvicornArgs = @(
  'run',
  '--no-sync',
  'uvicorn',
  'app.main:app',
  '--host',
  '127.0.0.1',
  '--port',
  '8000'
)
if (-not $NoReload) {
  $uvicornArgs += '--reload'
}

"[$(Get-Date -Format o)] Starting backend API..." | Tee-Object -FilePath $LogPath -Append
& uv @uvicornArgs 2>&1 | Tee-Object -FilePath $LogPath -Append
exit $LASTEXITCODE
