<#
.SYNOPSIS
  Stop the backend and the desktop app, then start them again.

.DESCRIPTION
  stop_app.ps1 followed by start_app.ps1, with the same switches. Use it after
  pulling new code: the backend only reads its code and config when it starts.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File restart_app.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File restart_app.ps1 -BackendOnly
  Restart the backend and leave the desktop app open.
#>
param(
  [int]$Port = 8000,
  [switch]$BackendOnly,
  [switch]$DesktopOnly,
  [switch]$OldUi,
  [ValidateRange(1, 6)][int]$ui = 1
)

$ErrorActionPreference = 'Stop'

$stop = @{ Port = $Port }
if ($BackendOnly) { $stop.BackendOnly = $true }
if ($DesktopOnly) { $stop.DesktopOnly = $true }
& (Join-Path $PSScriptRoot 'stop_app.ps1') @stop

Start-Sleep -Seconds 2

$start = @{ Port = $Port }
if ($BackendOnly) { $start.BackendOnly = $true }
if ($DesktopOnly) { $start.DesktopOnly = $true }
if ($OldUi) { $start.OldUi = $true }
if ($ui -gt 1) { $start.ui = $ui }
& (Join-Path $PSScriptRoot 'start_app.ps1') @start
