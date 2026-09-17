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

.PARAMETER SkipCompile
  Stage the backend as Python source instead of compiling it with Nuitka.
  Much faster, and useful while working on the staging or installer steps --
  but it ships readable source, so the release check is told to expect it and
  says so loudly. A release build never uses this.

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
  [switch]$SkipVerify,
  [switch]$SkipCompile
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

# -- 1b. Compile --------------------------------------------------------------
# This is the step the whole exercise is for. Nuitka translates the backend to
# C and compiles it to native code: there is no .pyc inside to extract and no
# decompiler that recovers the source, so a customer receives a program rather
# than a readable copy of how this works.
#
# What it is not: protection against a determined party. It raises the cost of
# casual reading and copying substantially; it does not prevent reverse
# engineering, and nothing here should be read as claiming otherwise. The
# database also sits on the customer's machine, so the schema and the data are
# readable by any administrator there whatever happens to the Python.

$compiledDir = Join-Path $root 'dist\compiled\cli.dist'

if ($SkipCompile) {
  Write-Step 'Compile'
  Write-Host "   SKIPPED -- the backend will be staged as readable Python source." -ForegroundColor Yellow
  Write-Host "   Never release a build made this way." -ForegroundColor Yellow
} else {
  Write-Step 'Compile'
  $python = Join-Path $root 'backend\.venv\Scripts\python.exe'
  if (-not (Test-Path $python)) {
    Stop-Build 'No virtual environment at backend\.venv.' 'Run: cd backend; uv sync --group build'
  }
  & $python -c "import nuitka" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Stop-Build 'Nuitka is not installed, so the backend cannot be compiled.' `
      "Install it with:`n    cd backend; uv sync --group build`n  Or build without compiling -- for debugging only -- with -SkipCompile."
  }

  # The options live in nuitka.args so that a change to how this is compiled is
  # a diff somebody can read. Comments and blank lines are stripped here.
  $argsFile = Join-Path $PSScriptRoot 'nuitka.args'
  if (-not (Test-Path $argsFile)) { Stop-Build "Missing $argsFile." }
  $nuitkaArgs = Get-Content $argsFile |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith('#') }

  $compileOut = Join-Path $root 'dist\compiled'
  if (Test-Path $compileOut) { Remove-Item -Recurse -Force $compileOut }
  New-Item -ItemType Directory -Force -Path $compileOut | Out-Null

  Write-Host "   compiling the backend -- this takes several minutes"
  Push-Location (Join-Path $root 'backend')
  try {
    $previous = $ErrorActionPreference
    # Nuitka reports progress on stderr, and in Windows PowerShell 5.1 that
    # aborts the script under 'Stop'. Same trap as start_backend.ps1.
    $ErrorActionPreference = 'Continue'
    & $python -m nuitka @nuitkaArgs `
      "--output-dir=$compileOut" "--file-version=$Version" "--product-version=$Version" `
      'app\cli.py'
    $ErrorActionPreference = $previous
  } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { Stop-Build 'Nuitka failed to compile the backend.' }

  $exe = Join-Path $compiledDir 'agency-server.exe'
  if (-not (Test-Path $exe)) {
    Stop-Build "Nuitka reported success but $exe is not there." `
      'Look in dist\compiled for what it actually produced.'
  }
  # A binary that cannot answer --version is not a binary worth shipping, and
  # this is the cheapest possible proof that it starts at all.
  $reported = (& $exe --version 2>&1 | Out-String).Trim()
  if ($reported -ne $Version) {
    Stop-Build "The compiled binary reports version '$reported', not '$Version'." `
      'That means it did not start, or it was built from a different tree.'
  }
  Write-Done "compiled, and it reports $reported"
}

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

# The backend. Compiled, unless told otherwise -- see Compile below.
$backendFrom = Join-Path $root 'backend'
$backendTo = Join-Path $staging 'backend'
New-Item -ItemType Directory -Force -Path $backendTo | Out-Null

if ($SkipCompile) {
  # By allow-list. Anything not named here does not reach a customer, which is
  # the property worth having: a new folder in backend\ is excluded until
  # somebody decides otherwise, rather than shipped until somebody notices.
  foreach ($item in @('app', 'alembic', 'alembic.ini', 'pyproject.toml')) {
    $source = Join-Path $backendFrom $item
    if (-not (Test-Path $source)) { Stop-Build "Missing $source." }
    Copy-Item -Path $source -Destination $backendTo -Recurse -Force
  }
  # Scripts by name, not the folder. scripts\ also holds the demo seeder, the
  # sample-data generator and the manual-test fixture builder -- tooling for
  # selling and developing this, carrying their own passwords, and none of it
  # is the product. Staging the folder wholesale put `DemoAdmin@12345` and
  # `Fixture@2026pw` into the customer payload, which the release check caught.
  $scriptsTo = Join-Path $backendTo 'scripts'
  New-Item -ItemType Directory -Force -Path $scriptsTo | Out-Null
  foreach ($script in @('__init__.py', 'migrate_all_stores.py',
                        'purge_retention.py', 'start_backend.ps1')) {
    $source = Join-Path $backendFrom "scripts\$script"
    if (-not (Test-Path $source)) { Stop-Build "Missing $source." }
    Copy-Item -Path $source -Destination $scriptsTo -Force
  }
} else {
  # The compiled build. Nuitka produced a directory of real files; all of it
  # goes, because Nuitka decided what the program needs and second-guessing
  # that by allow-list is how a DLL goes missing on a customer machine.
  #
  # There is no allow-list problem to solve here: the compiler put nothing in
  # that directory that was not reached from app\cli.py, so tests\, docs\ and
  # the developer's .env cannot be in it. The release check confirms it rather
  # than assuming it.
  Copy-Item -Path (Join-Path $compiledDir '*') -Destination $backendTo `
    -Recurse -Force

  # Alembic loads migrations by path at runtime -- it scans the directory and
  # calls spec_from_file_location per file -- so these stay as source. That is
  # the one deliberate exception to "no .py reaches a customer", and it is an
  # acceptable one: a migration is schema DDL, and the customer's own
  # PostgreSQL exposes that same schema to anyone who looks.
  Copy-Item -Path (Join-Path $backendFrom 'alembic') -Destination $backendTo `
    -Recurse -Force
  Copy-Item -Path (Join-Path $backendFrom 'alembic.ini') -Destination $backendTo -Force

  # The start script, which finds agency-server.exe beside it.
  $scriptsTo = Join-Path $backendTo 'scripts'
  New-Item -ItemType Directory -Force -Path $scriptsTo | Out-Null
  Copy-Item -Path (Join-Path $backendFrom 'scripts\start_backend.ps1') `
    -Destination $scriptsTo -Force
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
    # -AllowPython only when the compile step was skipped. It used to be
    # unconditional, because the backend was staged as source; leaving it
    # that way now would permanently switch off the one check that enforces
    # the point of all this -- that no readable source reaches a customer.
    if ($SkipCompile) {
      Write-Host "   -SkipCompile: .py files are expected, and this is not a releasable build" -ForegroundColor Yellow
      & $verify -Path $staging -AllowPython
    } else {
      & $verify -Path $staging
    }
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
