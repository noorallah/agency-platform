<#
.SYNOPSIS
  Start the backend and the desktop app on this PC, for development and demos.

.DESCRIPTION
  Starts the backend in a window of its own (through
  backend\scripts\start_backend.ps1) and waits until it answers, then starts
  the desktop app in a second window. Whatever is already running is left
  alone, so the script can be run twice.

  Stop both with stop_app.ps1; restart_app.ps1 does one after the other.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File start_app.ps1
  Backend on http://127.0.0.1:8000 and the phase 2 desktop app.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File start_app.ps1 -BackendOnly
  The backend alone.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File start_app.ps1 -OldUi
  The desktop app with the older shell instead of the phase 2 one.
#>
param(
  [int]$Port = 8000,
  [switch]$BackendOnly,
  [switch]$DesktopOnly,
  [switch]$OldUi
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$desktop = Join-Path $root 'desktop'
$healthUrl = "http://127.0.0.1:$Port/health"

function Test-Backend {
  try {
    return (Invoke-WebRequest -UseBasicParsing $healthUrl -TimeoutSec 3).StatusCode -eq 200
  } catch {
    return $false
  }
}

if (-not $DesktopOnly) {
  if (Test-Backend) {
    Write-Host "Backend is already running on port $Port."
  } else {
    Write-Host "Starting the backend on port $Port ..."
    $arguments = @(
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
      "`"$(Join-Path $backend 'scripts\start_backend.ps1')`"",
      '-SkipSync', '-NoReload', '-Port', $Port
    )
    Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $backend `
      -WindowStyle Minimized
    $ready = $false
    foreach ($attempt in 1..60) {
      Start-Sleep -Seconds 2
      if (Test-Backend) { $ready = $true; break }
    }
    if (-not $ready) {
      throw "The backend did not answer on $healthUrl within two minutes. Look at the newest file in backend\logs."
    }
    Write-Host "Backend is up: http://127.0.0.1:$Port/docs"
  }
}

if (-not $BackendOnly) {
  if (Get-Process agency_desktop -ErrorAction SilentlyContinue) {
    Write-Host 'The desktop app is already running.'
  } else {
    if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
      throw 'flutter is not on PATH, so the desktop app cannot be started from source.'
    }
    $target = if ($OldUi) { 'lib/main.dart' } else { 'lib/main_phase2.dart' }
    Write-Host "Starting the desktop app ($target); the first build takes about a minute ..."
    $command = "flutter run -d windows -t $target --dart-define=API_BASE_URL=http://127.0.0.1:$Port"
    # In a window of its own: closing that window closes the app.
    Start-Process cmd.exe -ArgumentList '/k', "title Agency desktop && $command" `
      -WorkingDirectory $desktop
  }
}

Write-Host 'Done. Stop everything with stop_app.ps1.'
