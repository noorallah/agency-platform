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

.PARAMETER Jobs
  How many C compilations run at once. Nuitka's default is one per core, which
  is right on a build machine and is how this gets killed on a developer's:
  each MSVC process is most of a gigabyte and there are hundreds of modules.

.PARAMETER LowMemory
  Tell Nuitka to trade build speed for peak memory. Slower, and the answer
  when the build is killed rather than failing -- a killed build leaves no
  error to read, which is what makes it worth naming here.

.PARAMETER ClientDir
  A built desktop client to stage instead of desktop\build\windows\x64\runner\
  Release. For building the installer from a worktree that has not built the
  client itself; a release build normally omits it.

.PARAMETER CacheDir
  Where the three downloaded build inputs are kept between builds -- the
  PostgreSQL binaries, WinSW and the Visual C++ runtime. Outside the
  repository, so a clean checkout does not download 350 MB again and nothing
  large is ever committed. Defaults to $env:AGENCY_BUILD_CACHE, then
  %LOCALAPPDATA%\agency-build-cache.

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
  [switch]$SkipCompile,
  [int]$Jobs = 0,
  [switch]$LowMemory,
  [string]$ClientDir,
  [string]$CacheDir
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$staging = Join-Path $root 'dist\staging'
# Installed by Setup to {tmp} and run, never copied to Program Files -- so it
# is staged beside the payload rather than inside it.
$redistStaging = Join-Path $root 'dist\redist'
$output = Join-Path $root 'dist\windows'

if (-not $CacheDir) {
  $CacheDir = if ($env:AGENCY_BUILD_CACHE) { $env:AGENCY_BUILD_CACHE } else {
    Join-Path $env:LOCALAPPDATA 'agency-build-cache'
  }
}

# -- Pinned build inputs --------------------------------------------------------
# Each is downloaded once into the cache and checked against its SHA-256 on
# every build, so what reaches a customer is exactly what was reviewed here. To
# move one forward, change the version, the URL and the hash together; a
# mismatch stops the build rather than shipping whatever the URL serves today.
$PostgresVersion = '17.11-1'
$PinnedInputs = @(
  @{
    Name   = "PostgreSQL $PostgresVersion binaries (EDB, Windows x64)"
    File   = "postgresql-$PostgresVersion-windows-x64-binaries.zip"
    Url    = "https://get.enterprisedb.com/postgresql/postgresql-$PostgresVersion-windows-x64-binaries.zip"
    Sha256 = '6EABDF00D2893713B75DB4336A23C3FDF505F056E217EC6E2E95D901750CFEA3'
  },
  @{
    # WinSW 2.12.0 is the current stable release; 3.x is still alpha.
    Name   = 'WinSW 2.12.0 (x64)'
    File   = 'WinSW-x64-2.12.0.exe'
    Url    = 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'
    Sha256 = '05B82D46AD331CC16BDC00DE5C6332C1EF818DF8CEEFCD49C726553209B3A0DA'
  },
  @{
    # 14.44.35211. The versioned URL aka.ms/vs/17/release/vc_redist.x64.exe
    # redirected to on 2026-09-24; the aka.ms link itself moves with every
    # Visual Studio release, which a pinned hash cannot follow.
    Name   = 'Visual C++ 2015-2022 runtime 14.44.35211 (x64)'
    File   = 'vc_redist-14.44.35211.x64.exe'
    Url    = 'https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe'
    Sha256 = 'CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B'
  }
)
# The runtime the bundled vc_redist carries, handed to the .iss so Setup
# installs it only when the machine has an older one or none.
$VcRuntimeMinor = 44

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
foreach ($dir in @($staging, $redistStaging)) {
  if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
New-Item -ItemType Directory -Force -Path $staging, $redistStaging, $output | Out-Null
Write-Done 'staging directory is empty'

# -- 1a. Fetch ------------------------------------------------------------------
# The installer is fully offline: everything a customer machine needs is inside
# Setup.exe. What this repository does not build -- PostgreSQL, the service
# wrapper, the C++ runtime -- is fetched here, once, into a cache outside the
# repository, and checked against its pinned hash on every build.

Write-Step 'Fetch'
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
Write-Host "   cache: $CacheDir"

function Get-PinnedInput {
  param([hashtable]$Item)
  $target = Join-Path $CacheDir $Item.File
  $partial = "$target.tmp"
  foreach ($candidate in @($target, $partial)) {
    if (-not (Test-Path $candidate)) { continue }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash
    if ($hash -eq $Item.Sha256) {
      if ($candidate -ne $target) { Move-Item -Force -LiteralPath $candidate -Destination $target }
      Write-Done "$($Item.Name): cached, hash verified"
      return $target
    }
    Write-Host "   $($Item.Name): cached copy has the wrong hash -- fetching again" -ForegroundColor Yellow
    Remove-Item -Force -LiteralPath $candidate
  }
  Write-Host "   $($Item.Name): downloading $($Item.Url)"
  $previousProgress = $ProgressPreference
  $ProgressPreference = 'SilentlyContinue'   # the progress bar makes this ten times slower
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Item.Url -OutFile $partial
  } catch {
    Stop-Build "Could not download $($Item.Name): $($_.Exception.Message)" `
      "Check the network, or place the file in $CacheDir as $($Item.File) by hand."
  } finally { $ProgressPreference = $previousProgress }
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash
  if ($hash -ne $Item.Sha256) {
    Remove-Item -Force -LiteralPath $partial
    Stop-Build "$($Item.Name) does not match its pinned SHA-256 (got $hash)." `
      'Either the download was corrupted or the publisher changed the file. Do not update the pin without finding out which.'
  }
  Move-Item -Force -LiteralPath $partial -Destination $target
  Write-Done "$($Item.Name): downloaded, hash verified"
  return $target
}

$fetched = @{}
foreach ($item in $PinnedInputs) { $fetched[$item.File] = Get-PinnedInput $item }
$postgresZip = $fetched["postgresql-$PostgresVersion-windows-x64-binaries.zip"]
$winswExe = $fetched['WinSW-x64-2.12.0.exe']
$vcRedist = $fetched['vc_redist-14.44.35211.x64.exe']

# Extracted once per version into the cache: the zip is 340 MB and expanding it
# is most of a minute, which is not worth paying on every build.
$postgresExtracted = Join-Path $CacheDir "pgsql-$PostgresVersion"
if (-not (Test-Path (Join-Path $postgresExtracted 'pgsql\bin\postgres.exe'))) {
  Write-Host "   extracting PostgreSQL $PostgresVersion"
  if (Test-Path $postgresExtracted) { Remove-Item -Recurse -Force $postgresExtracted }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::ExtractToDirectory($postgresZip, $postgresExtracted)
}
Write-Done "PostgreSQL $PostgresVersion ready to stage"

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

  # Memory, not time, is what stops this build. Nuitka runs one C compilation
  # per core by default and each is most of a gigabyte; on a 16 GB machine with
  # an IDE open, Windows killed the build outright -- which leaves no error to
  # read and looks like nothing happened. Cap the jobs when the machine is not
  # obviously large enough, and say so rather than deciding silently.
  $tuning = @()
  if ($Jobs -gt 0) {
    $tuning += "--jobs=$Jobs"
  } else {
    $freeGb = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    # Roughly a gigabyte per concurrent compilation, and leave some for the
    # rest of the machine.
    $affordable = [math]::Max(1, [math]::Floor($freeGb / 1.5))
    $cores = [Environment]::ProcessorCount
    if ($affordable -lt $cores) {
      Write-Host "   $freeGb GB free: limiting to $affordable parallel compilations (of $cores cores)" -ForegroundColor Yellow
      $tuning += "--jobs=$affordable"
    }
  }
  if ($LowMemory) { $tuning += '--low-memory' }

  Write-Host "   compiling the backend -- this takes several minutes"
  Push-Location (Join-Path $root 'backend')
  try {
    $previous = $ErrorActionPreference
    # Nuitka reports progress on stderr, and in Windows PowerShell 5.1 that
    # aborts the script under 'Stop'. Same trap as start_backend.ps1.
    $ErrorActionPreference = 'Continue'
    & $python -m nuitka @nuitkaArgs @tuning `
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

  # --version proves the binary starts; it imports none of the application.
  # The first installed copy passed it here and failed on the customer's PC
  # at the first pydantic model it imported (Nuitka + PEP 695 generic
  # classes, 2026-09-24). `check` builds the whole application and its
  # OpenAPI document, so anything the compiler broke fails here, on this
  # machine, with a traceback to read. Logs go to a scratch folder: the
  # application configures its log file on construction, and that must not
  # land inside the tree about to be staged.
  $checkLogs = Join-Path $env:TEMP 'agency-build-check-logs'
  $previousLogDir = $env:AGENCY_LOG_DIRECTORY
  $env:AGENCY_LOG_DIRECTORY = $checkLogs
  try {
    $checkOut = (& $exe check 2>&1 | Out-String).Trim()
  } finally {
    if ($null -eq $previousLogDir) { Remove-Item Env:\AGENCY_LOG_DIRECTORY -ErrorAction SilentlyContinue }
    else { $env:AGENCY_LOG_DIRECTORY = $previousLogDir }
    Remove-Item -Recurse -Force -LiteralPath $checkLogs -ErrorAction SilentlyContinue
  }
  if ($LASTEXITCODE -ne 0 -or $checkOut -notmatch '^ok:') {
    Write-Host $checkOut
    Stop-Build 'The compiled binary cannot build the application.' `
      'The traceback above is from the compiled copy; the same code runs under the interpreter. Look for something the compiler handles differently (tests/unit/test_no_generic_class_syntax.py records one).'
  }
  Write-Done "and it builds the application ($checkOut)"
}

# -- 2. Stage -----------------------------------------------------------------

Write-Step 'Stage'

$client = if ($ClientDir) { $ClientDir } else { Join-Path $root 'desktop\build\windows\x64\runner\Release' }
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
# The machine-level half: the private database, the service, the firewall,
# the pre-upgrade backup and the uninstall. It calls install.ps1 rather than
# repeating it.
Copy-Item -Path (Join-Path $PSScriptRoot 'server_setup.ps1') -Destination $packagingTo -Force
Write-Done 'configure step staged'

# The customer's installation guide, rendered from docs\INSTALL_GUIDE.md --
# the one source, which the repository's guard tests also read. It is staged
# at the root, not under docs\, because the release check treats a docs
# folder as repository-only. It lands in the Start menu of an installed copy
# and, at the end, beside Setup.exe so the two travel together.
$guideName = 'Installation guide.html'
$guideSource = Join-Path $root 'docs\INSTALL_GUIDE.md'
$guideStaged = Join-Path $staging $guideName
$guidePython = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $guideSource)) { Stop-Build "Missing $guideSource." }
& $guidePython (Join-Path $PSScriptRoot 'render_guide.py') $guideSource $guideStaged
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $guideStaged)) {
  Stop-Build 'The installation guide could not be rendered.' `
    "It needs the markdown package from the build group:`n    cd backend; uv sync --group build"
}
Write-Done 'installation guide staged'

# The private PostgreSQL. Only what a server needs to run: pgAdmin,
# StackBuilder, the documentation, the debug symbols and the C headers are
# roughly two thirds of the zip and none of them is used on a customer machine.
$pgsqlFrom = Join-Path $postgresExtracted 'pgsql'
$pgsqlTo = Join-Path $staging 'pgsql'
$pgsqlDrop = @('pgAdmin 4', 'StackBuilder', 'doc', 'symbols', 'include')
New-Item -ItemType Directory -Force -Path $pgsqlTo | Out-Null
foreach ($entry in Get-ChildItem -Force $pgsqlFrom) {
  if ($entry.Name -in $pgsqlDrop) { continue }
  Copy-Item -Path $entry.FullName -Destination $pgsqlTo -Recurse -Force
}
# PostgreSQL's own test programs: bin\test_cloexec.exe and the
# test_decoding example plugin. Not used by a server, and the release check
# refuses anything named like a test.
Get-ChildItem -Path $pgsqlTo -Recurse -File -Filter 'test_*' | Remove-Item -Force
foreach ($required in @('bin\postgres.exe', 'bin\initdb.exe', 'bin\pg_ctl.exe', 'bin\pg_dump.exe',
                        'bin\pg_isready.exe', 'share\postgresql.conf.sample')) {
  if (-not (Test-Path (Join-Path $pgsqlTo $required))) { Stop-Build "The PostgreSQL stage lacks $required." }
}
$pgSize = [math]::Round((Get-ChildItem $pgsqlTo -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Done "PostgreSQL $PostgresVersion staged ($pgSize MB; pgAdmin, StackBuilder, docs, symbols and headers dropped)"

# The service wrapper, named after the service so WinSW finds its XML beside it.
$serviceTo = Join-Path $staging 'service'
New-Item -ItemType Directory -Force -Path $serviceTo | Out-Null
Copy-Item -Path $winswExe -Destination (Join-Path $serviceTo 'AgencyPlatformServer.exe') -Force
Write-Done 'service wrapper staged'

Copy-Item -Path $vcRedist -Destination (Join-Path $redistStaging 'vc_redist.x64.exe') -Force
Write-Done 'Visual C++ runtime staged (run by Setup when missing, never copied to Program Files)'

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
# winget installs Inno Setup per user unless told otherwise, which puts it
# under LOCALAPPDATA rather than Program Files.
$iscc = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
  Stop-Build 'Inno Setup 6 is not installed, so the installer cannot be compiled.' `
    "Install it with:`n    winget install --id JRSoftware.InnoSetup`n  Then run this again. The staged tree is ready at $staging."
}

& $iscc "/DAppVersion=$Version" "/DPayloadDir=$staging" "/DRedistDir=$redistStaging" `
  "/DOutputDir=$output" "/DVcRuntimeMinor=$VcRuntimeMinor" `
  (Join-Path $PSScriptRoot 'AgencyPlatform.iss')
if ($LASTEXITCODE -ne 0) { Stop-Build 'Inno Setup failed to compile the installer.' }

$setup = Join-Path $output "AgencyPlatform-$Version-Setup.exe"
if (-not (Test-Path $setup)) { Stop-Build "Inno Setup reported success but $setup is not there." }

$setupSize = [math]::Round((Get-Item $setup).Length / 1MB, 1)
# The guide beside the installer, so whoever hands Setup.exe on can hand the
# instructions on with it. The installed copy carries its own.
Copy-Item -Path $guideStaged -Destination (Join-Path $output $guideName) -Force
Write-Step 'Done'
Write-Host "   $setup" -ForegroundColor Green
Write-Host "   $setupSize MB -- this is the only file a customer needs."
Write-Host "   $(Join-Path $output $guideName) -- the guide to send with it."
