<#
.SYNOPSIS
  Stop the desktop app and the backend started by start_app.ps1.

.DESCRIPTION
  Closes the desktop app and the window it was started from, then stops
  whatever serves the backend port, however it was started (start_app.ps1,
  start_backend.ps1 or the scheduled task on a developer's PC). The database
  is not touched.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File stop_app.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File stop_app.ps1 -BackendOnly
#>
param(
  [int]$Port = 8000,
  [switch]$BackendOnly,
  [switch]$DesktopOnly
)

$ErrorActionPreference = 'Continue'

function Stop-Tree([int]$ProcessId) {
  # The process and everything it started: uvicorn's worker, flutter's tools.
  & cmd.exe /c "taskkill /PID $ProcessId /T /F >nul 2>&1"
}

if (-not $BackendOnly) {
  $apps = @(Get-Process agency_desktop -ErrorAction SilentlyContinue)
  foreach ($app in $apps) { Stop-Tree $app.Id }
  # The `flutter run` console that started it, if one is still open.
  $consoles = @(Get-CimInstance Win32_Process |
      Where-Object { $_.CommandLine -match 'flutter(\.bat)?"?\s+run\s+-d\s+windows' -or
        $_.CommandLine -match 'flutter_tools\.snapshot.*\srun\s' })
  foreach ($console in $consoles) { Stop-Tree $console.ProcessId }
  if ($apps.Count -or $consoles.Count) { Write-Host 'Desktop app stopped.' }
  else { Write-Host 'The desktop app was not running.' }
}

if (-not $DesktopOnly) {
  # A scheduled task that serves this port would start it again otherwise.
  & cmd.exe /c "schtasks /end /tn agency-backend-$Port >nul 2>&1"
  $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique)
  $servers = @(Get-CimInstance Win32_Process |
      Where-Object { $_.CommandLine -match "--port\s+$Port\b" -and
        $_.CommandLine -match 'uvicorn|agency-server|app\.cli' })
  $wrappers = @(Get-CimInstance Win32_Process |
      Where-Object { $_.Name -eq 'powershell.exe' -and
        $_.CommandLine -match 'start_backend\.ps1' -and $_.ProcessId -ne $PID })
  $ids = @($owners) + @($servers | ForEach-Object { $_.ProcessId }) +
    @($wrappers | ForEach-Object { $_.ProcessId }) | Sort-Object -Unique
  foreach ($id in $ids) { Stop-Tree ([int]$id) }
  Start-Sleep -Seconds 1
  $left = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
  if ($left.Count) { Write-Host "Something still listens on port $Port. Close it by hand." }
  elseif ($ids.Count) { Write-Host "Backend on port $Port stopped." }
  else { Write-Host "The backend was not running on port $Port." }
}
