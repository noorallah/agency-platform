<#
.SYNOPSIS
  Sync, migrate and serve the backend.

.DESCRIPTION
  Defaults to 127.0.0.1 over plain HTTP, which is the right thing for a
  developer on one machine and reachable by nothing else.

  A LAN deployment -- clients on other machines in the same building -- needs
  -BindHost 0.0.0.0. That is the deployment the product is for, and the desktop
  client accepts plain http:// to a private address for exactly this case.

  -CertFile and -KeyFile serve HTTPS instead. Prefer them on any network the
  firm does not control: without them the traffic, including the password on
  the login request, is readable by anything else on the wire.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1
  Serves http://127.0.0.1:8000 for local development.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1 -BindHost 0.0.0.0 -NoReload
  Serves plain HTTP to the local network.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1 -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key -NoReload
  Serves HTTPS to the local network. Every client machine has to trust the
  certificate, which for a self-signed one means installing it in the Windows
  trust store.
#>
param(
  [switch]$SkipSync,
  [switch]$NoReload,
  [string]$LogPath,
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 8000,
  [string]$CertFile,
  [string]$KeyFile
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

# A certificate is only half of a TLS server, so refuse the half-configured
# case rather than starting on plain HTTP while the operator believes otherwise.
if ($CertFile -and -not $KeyFile) {
  throw 'CertFile was given without KeyFile. TLS needs both.'
}
if ($KeyFile -and -not $CertFile) {
  throw 'KeyFile was given without CertFile. TLS needs both.'
}
foreach ($file in @($CertFile, $KeyFile)) {
  if ($file -and -not (Test-Path $file)) {
    throw "Certificate file not found: $file"
  }
}

$uvicornArgs = @(
  'run',
  '--no-sync',
  'uvicorn',
  'app.main:app',
  '--host',
  $BindHost,
  '--port',
  "$Port"
)
if ($CertFile) {
  $uvicornArgs += @('--ssl-certfile', $CertFile, '--ssl-keyfile', $KeyFile)
}
if (-not $NoReload) {
  $uvicornArgs += '--reload'
}

$scheme = if ($CertFile) { 'https' } else { 'http' }
Write-Host "Serving ${scheme}://${BindHost}:${Port}"
if (-not $CertFile -and $BindHost -ne '127.0.0.1') {
  Write-Host 'Plain HTTP on a network interface: passwords cross the wire in clear text.' -ForegroundColor Yellow
}

"[$(Get-Date -Format o)] Starting backend API..." | Tee-Object -FilePath $LogPath -Append
& uv @uvicornArgs 2>&1 | Tee-Object -FilePath $LogPath -Append
exit $LASTEXITCODE
