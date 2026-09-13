<#
.SYNOPSIS
  Build the client as an Android app (APK) and, optionally, install it on a
  phone connected over USB.

.DESCRIPTION
  The client is designed for desktop screens of 1366x768 and up. This build
  exists so the screens can be opened on a phone or tablet for a look; results
  on a small screen do not stand in for the desktop test plan.

  The phone cannot reach "localhost" -- that is the phone itself -- so the app
  is built pointing at this computer's address on the local network, and the
  backend has to listen on the network too:

    cd ..\backend
    powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1 -BindHost 0.0.0.0 -NoReload

  and Windows Firewall has to let port 8000 in (once, from an administrator
  PowerShell):

    New-NetFirewallRule -DisplayName "Agency backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private

  The address can also be changed later on the app's sign-in screen.

  Needs the Android SDK (install Android Studio once, open it, let it install
  the SDK, then run `flutter doctor --android-licenses`).

.PARAMETER ServerUrl
  The backend address the app starts with. Defaults to http://<this PC's
  private IPv4>:8000.

.PARAMETER DebugBuild
  Build a debug APK instead of a release one (bigger and slower, but prints
  logs to `flutter logs`).

.PARAMETER Install
  After building, install the APK on the phone connected over USB (USB
  debugging on) with adb.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File build_android.ps1
  powershell -ExecutionPolicy Bypass -File build_android.ps1 -Install
  powershell -ExecutionPolicy Bypass -File build_android.ps1 -ServerUrl http://192.168.1.20:8000 -Install
#>
param(
  [string]$ServerUrl = '',
  [switch]$DebugBuild,
  [switch]$Install
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Find-AndroidSdk {
  foreach ($candidate in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk'))) {
    if ($candidate -and (Test-Path (Join-Path $candidate 'platform-tools'))) { return $candidate }
  }
  return $null
}

$sdk = Find-AndroidSdk
if (-not $sdk) {
  Write-Host 'The Android SDK was not found, so an APK cannot be built on this computer yet.' -ForegroundColor Red
  Write-Host '  1. Install Android Studio: https://developer.android.com/studio'
  Write-Host '  2. Open it once and let the setup wizard install the Android SDK.'
  Write-Host '  3. Run: flutter doctor --android-licenses   (accept the licences)'
  Write-Host '  4. Run this script again.'
  exit 1
}

if (-not $ServerUrl) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $ip) {
    Write-Host 'Could not find a private network address; pass -ServerUrl http://<this PC>:8000.' -ForegroundColor Red
    exit 1
  }
  $ServerUrl = "http://${ip}:8000"
}

$mode = if ($DebugBuild) { 'debug' } else { 'release' }
Write-Host "Building the $mode APK, pointing at $ServerUrl ..." -ForegroundColor Cyan
flutter pub get
flutter build apk "--$mode" "--dart-define=API_BASE_URL=$ServerUrl"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$apk = Join-Path $PSScriptRoot "build\app\outputs\flutter-apk\app-$mode.apk"
Write-Host "APK: $apk" -ForegroundColor Green
Write-Host 'Copy it to the phone and open it to install (allow installs from this source), or use -Install over USB.'

if ($Install) {
  $adb = Join-Path $sdk 'platform-tools\adb.exe'
  $devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice$' }
  if (-not $devices) {
    Write-Host 'No phone found. Connect it by USB, turn on USB debugging, accept the prompt on the phone, and retry.' -ForegroundColor Red
    exit 1
  }
  & $adb install -r $apk
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host 'Installed. Open "Agency Platform" on the phone.' -ForegroundColor Green
}

Write-Host "Reminder: the backend must listen on the network (-BindHost 0.0.0.0) and port 8000 must be open, or the app cannot sign in." -ForegroundColor Yellow
