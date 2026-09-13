<#
.SYNOPSIS
  Generate the mobile (Android) build of the client: an installable APK kept
  in desktop\dist\android, one file per build.

.DESCRIPTION
  A separate build from the Windows client. Run it whenever a phone build is
  wanted; it needs no phone connected and no backend running. Each run leaves
  a new file named with the version, the date and time, and the build type,
  so earlier builds are kept:

    desktop\dist\android\AgencyPlatform-1.0.0+1-20260913-1830-release.apk

  Install it by copying the file to the phone and opening it (allow installs
  from that source when Android asks), or pass -Install with the phone
  connected over USB and USB debugging on.

  The app starts pointed at -ServerUrl, or at this PC's private network
  address, port 8000. Either way it can be changed on the phone afterwards:
  sign-in screen -> Application Settings -> API URL. For the phone to reach
  the backend, the backend must listen on the network
  (scripts\start_backend.ps1 -BindHost 0.0.0.0 -NoReload) and port 8000 must
  be open in Windows Firewall.

  The screens are the desktop layouts. They open on a phone, but they were
  designed for 1366x768 and up; a tablet held landscape fits far better.

  Needs the Android SDK once: install Android Studio, let it install the SDK
  and "Android SDK Command-line Tools", then run
  `flutter doctor --android-licenses`.

.PARAMETER ServerUrl
  The backend address the app starts with, e.g. http://192.168.1.20:8000.
  Defaults to this PC's private IPv4 address on port 8000.

.PARAMETER DebugBuild
  Build a debug APK instead of a release one (larger and slower; its logs can
  be read with `flutter logs` while the phone is connected).

.PARAMETER Install
  Also install the new APK on the phone connected over USB.

.PARAMETER OutDir
  Where to keep the APKs. Defaults to desktop\dist\android.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File build_android.ps1
  powershell -ExecutionPolicy Bypass -File build_android.ps1 -ServerUrl http://192.168.1.20:8000
  powershell -ExecutionPolicy Bypass -File build_android.ps1 -Install
#>
param(
  [string]$ServerUrl = '',
  [switch]$DebugBuild,
  [switch]$Install,
  [string]$OutDir = ''
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
  Write-Host 'The Android SDK was not found, so the mobile build cannot be generated on this computer yet.' -ForegroundColor Red
  Write-Host '  1. Install Android Studio: https://developer.android.com/studio'
  Write-Host '  2. Open it once and let the setup wizard install the Android SDK.'
  Write-Host '  3. Settings > Languages & Frameworks > Android SDK > SDK Tools: tick "Android SDK Command-line Tools (latest)", Apply.'
  Write-Host '  4. Run: flutter doctor --android-licenses   (accept the licences)'
  Write-Host '  5. Run this script again.'
  exit 1
}

if (-not $ServerUrl) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress
  if ($ip) {
    $ServerUrl = "http://${ip}:8000"
  } else {
    $ServerUrl = 'http://localhost:8000'
    Write-Host 'No private network address found; the app will start pointed at localhost. Set the real address on the phone: sign-in screen > Application Settings > API URL.' -ForegroundColor Yellow
  }
}

$mode = if ($DebugBuild) { 'debug' } else { 'release' }
$version = ((Get-Content pubspec.yaml | Where-Object { $_ -match '^version:' }) -replace '^version:\s*', '').Trim()
if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot 'dist\android' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "Generating the mobile $mode build $version, starting at $ServerUrl ..." -ForegroundColor Cyan
flutter pub get
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
flutter build apk "--$mode" "--dart-define=API_BASE_URL=$ServerUrl"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$built = Join-Path $PSScriptRoot "build\app\outputs\flutter-apk\app-$mode.apk"
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$kept = Join-Path $OutDir "AgencyPlatform-$version-$stamp-$mode.apk"
Copy-Item -LiteralPath $built -Destination $kept -Force
Write-Host "Mobile build: $kept" -ForegroundColor Green
Write-Host 'Install: copy the file to the phone and open it, or run again with -Install over USB.'

if ($Install) {
  $adb = Join-Path $sdk 'platform-tools\adb.exe'
  $devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice$' }
  if (-not $devices) {
    Write-Host 'No phone found. Connect it by USB, turn on USB debugging, accept the prompt on the phone, and retry.' -ForegroundColor Red
    exit 1
  }
  & $adb install -r $kept
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host 'Installed. Open "Agency Platform" on the phone.' -ForegroundColor Green
}
