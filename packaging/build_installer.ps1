<#
.SYNOPSIS
  Stage the product and compile the Windows installer.

.DESCRIPTION
  One command from a built repository to a single file a customer can run.

  Two steps, and the first is the one that matters: **staging decides what
  reaches a customer**. It copies only what the product needs, so the installer
  physically cannot ship a test, a Dockerfile or a developer's .env -- there is
  nothing in the staging directory to ship. The compiler then packages whatever
  is there, which is why the deny-list lives here and not in the .iss.

  The version comes from VERSION at the repository root, the single declared
  source; `tests/unit/test_version_is_declared_once.py` fails the build if any
  other file disagrees with it.

.PARAMETER Version
  Override the version. Normally omitted -- VERSION is the source.

.PARAMETER SkipInstaller
  Stage only, and do not compile. Useful for inspecting what would ship, and
  the only half of this that works without Inno Setup installed.

.PARAMETER SkipVerify
  Skip the release check. Provided for debugging a staging problem; a release
  build should never use it.

.EXAMPLE
  .\packaging\build_installer.ps1
  Stages, verifies and produces dist\windows\AgencyPlatform-1.0.0-Setup.exe

.EXAMPLE
  .\packaging\build_installer.ps1 -SkipInstaller
  Stages and verifies only, leaving dist\staging to look through.
#>
[CmdletBinding()]
param(
  [string]$Version,
  [switch]$SkipInstaller,
  [switch]$SkipVerify
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$staging = Join-Path $root 'dist\staging'
$output = Join-Path $root 'dist\windows'

function Write-Step { param([string]$Text) Write-Host "`n== $Text" -ForegroundColor Cyan }
function Write-Done { param([string]$Text) Write-Host "   $Text" -ForegroundColor Green }
function Stop-Build {
  param([string]$Problem, [string]$Fix)
  Write-Host "`nBuild stopped: $Problem" -ForegroundColor Red
  if ($Fix) { Write-Host "  $Fix" -ForegroundColor Red }
  exit 1
}

if (-not $Version) {
  $versionFile = Join-Path $root 'VERSION'
  if (-not (Test-Path $versionFile)) { Stop-Build "No VERSION file at $versionFile." }
  $Version = (Get-Content $versionFile -Raw).Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  Stop-Build "VERSION is '$Version', which is not a release number." 'Expected something like 1.0.0.'
}

Write-Host "Agency Platform installer build"
Write-Host "  version:  $Version"
Write-Host "  staging:  $staging"
Write-Host "  output:   $output"

# -- 1. Clean -----------------------------------------------------------------
# A stale staging directory is how a file that was removed from the product
# keeps shipping. Start from nothing, every time.

Write-Step 'Clean'
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force -Path $staging, $output | Out-Null
Write-Done 'staging directory is empty'

# -- 2. Stage -----------------------------------------------------------------

Write-Step 'Stage'

$client = Join-Path $root 'desktop\build\windows\x64\runner\Release'
if (-not (Test-Path (Join-Path $client 'agency_desktop.exe'))) {
  Stop-Build 'The desktop client has not been built.' `
    'Run: cd desktop; flutter build windows --release'
}
# The client's own directory shape has to survive: the runner hardcodes
# DartProject(L"data"), so agency_desktop.exe, its DLLs and data\ must stay
# siblings. Copying the contents preserves exactly that.
Copy-Item -Path (Join-Path $client '*') -Destination $staging -Recurse -Force
Write-Done 'client staged'

# The backend, by allow-list. Anything not named here does not reach a customer,
# which is the property worth having: a new folder in backend\ is excluded until
# somebody decides otherwise, rather than shipped until somebody notices.
$backendFrom = Join-Path $root 'backend'
$backendTo = Join-Path $staging 'backend'
New-Item -ItemType Directory -Force -Path $backendTo | Out-Null
foreach ($item in @('app', 'alembic', 'alembic.ini', 'pyproject.toml')) {
  $source = Join-Path $backendFrom $item
  if (-not (Test-Path $source)) { Stop-Build "Missing $source." }
  Copy-Item -Path $source -Destination $backendTo -Recurse -Force
}

# Scripts by name, not the folder. scripts\ also holds the demo seeder, the
# sample-data generator and the manual-test fixture builder -- tooling for
# selling and developing this, carrying their own passwords, and none of it is
# the product. Staging the folder wholesale put `DemoAdmin@12345` and
# `Fixture@2026pw` into the customer payload, which the release check caught.
$scriptsTo = Join-Path $backendTo 'scripts'
New-Item -ItemType Directory -Force -Path $scriptsTo | Out-Null
foreach ($script in @('__init__.py', 'migrate_all_stores.py', 'purge_retention.py',
                      'start_backend.ps1')) {
  $source = Join-Path $backendFrom "scripts\$script"
  if (-not (Test-Path $source)) { Stop-Build "Missing $source." }
  Copy-Item -Path $source -Destination $scriptsTo -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $backendTo 'config') | Out-Null
Copy-Item -Path (Join-Path $backendFrom 'config\.env.example') `
  -Destination (Join-Path $backendTo 'config') -Force
Write-Done 'backend staged'

# The configure step the installer runs, so that configuration has one
# implementation rather than a copy inside the .iss.
$packagingTo = Join-Path $staging 'packaging'
New-Item -ItemType Directory -Force -Path $packagingTo | Out-Null
Copy-Item -Path (Join-Path $root 'install\install.ps1') -Destination $packagingTo -Force
Write-Done 'configure step staged'

# Compiled caches travel badly and belong to the build machine.
Get-ChildItem -Path $staging -Recurse -Force -Directory `
  | Where-Object { $_.Name -in @('__pycache__', '.pytest_cache', '.mypy_cache') } `
  | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$size = [math]::Round((Get-ChildItem $staging -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Done "staged $size MB"

# -- 3. Verify ----------------------------------------------------------------

if (-not $SkipVerify) {
  Write-Step 'Verify'
  $verify = Join-Path $PSScriptRoot 'verify_release.ps1'
  if (Test-Path $verify) {
    # -AllowPython until the backend is compiled (plan phase 3). The staged
    # tree is Python source by design today, so the check would fail on every
    # build and teach whoever met it to pass -SkipVerify -- which would switch
    # off the credential and repository-file checks as well. Remove this switch
    # when agency-server.exe replaces backendpp\.
    Write-Host "   backend is not compiled yet: .py files are expected" -ForegroundColor Yellow
    & $verify -Path $staging -AllowPython
    if ($LASTEXITCODE -ne 0) {
      Stop-Build 'The staged tree failed its release check.' `
        'The output above names what was found. No installer was produced.'
    }
  } else {
    Write-Host "   (no verify_release.ps1 yet)" -ForegroundColor DarkGray
  }
}

# -- 4. Compile ---------------------------------------------------------------

if ($SkipInstaller) {
  Write-Step 'Done'
  Write-Host "   Staged only. Look through: $staging"
  exit 0
}

Write-Step 'Installer'
$iscc = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
  Stop-Build 'Inno Setup 6 is not installed, so the installer cannot be compiled.' `
    "Install it with:`n    winget install --id JRSoftware.InnoSetup`n  Then run this again. The staged tree is ready at $staging."
}

& $iscc "/DAppVersion=$Version" "/DPayloadDir=$staging" "/DOutputDir=$output" `
  (Join-Path $PSScriptRoot 'AgencyPlatform.iss')
if ($LASTEXITCODE -ne 0) { Stop-Build 'Inno Setup failed to compile the installer.' }

$setup = Join-Path $output "AgencyPlatform-$Version-Setup.exe"
if (-not (Test-Path $setup)) { Stop-Build "Inno Setup reported success but $setup is not there." }

$setupSize = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Step 'Done'
Write-Host "   $setup" -ForegroundColor Green
Write-Host "   $setupSize MB -- this is the only file a customer needs."
