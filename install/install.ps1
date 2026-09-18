<#
.SYNOPSIS
  Install and start the Agency Platform on a Windows machine.

.DESCRIPTION
  One script from a machine with nothing on it to a running backend and a
  desktop client at the login screen. No Docker.

  It is safe to run twice. Every step checks what is already there and does
  only what is missing, so re-running after a failure continues rather than
  starting over, and re-running a working install changes nothing.

  What it will not do quietly:

  * It never overwrites an existing `backend/config/.env`. That file holds the
    JWT signing key and the database password; replacing it would invalidate
    every issued token and lock the application out of its own database.
  * It does not install system software unless asked with -InstallPrerequisites.
    Installing PostgreSQL on someone's machine is not a thing to do as a side
    effect of running a script that looked like it would set up an application.
  * It refuses to run against a half-configured TLS setup rather than falling
    back to plain HTTP while the operator believes otherwise.

.PARAMETER BindHost
  What the backend listens on. 127.0.0.1 (the default) is reachable only from
  this machine. Use 0.0.0.0 to serve clients on the local network.

.PARAMETER CertFile
  TLS certificate. With -KeyFile, the backend serves HTTPS. Without them it
  serves plain HTTP, which the desktop client accepts on a private network and
  refuses to a public address.

.PARAMETER DatabaseUser
  A PostgreSQL account that may create roles and databases, used **once** to
  set the application up and never stored. Only needed when PostgreSQL is
  already installed; when this script installs it, it sets this up itself.

.PARAMETER AppDatabaseUser
  The account the application itself runs as. It is created with a generated
  password, owns its own database and nothing else, and is not a superuser.
  The customer never types or sees this password.

.PARAMETER AdminPassword
  The first platform administrator's password. Generated and shown once at the
  end if not supplied, so an unattended install needs no input at all.

.PARAMETER InstallDir
  Where the application is installed. Asked for when this is run interactively
  and not supplied, offering C:\AgencyPlatform, a folder picker (answer B), or
  a typed path; pass it to install without a prompt, or pass the folder this
  script already sits in to install in place.

  Installing again over an existing directory **keeps the firm's data**:
  config\.env, logs\ and storage\ are never replaced, and the database is
  never touched -- it lives in PostgreSQL, not here.

.PARAMETER ConfigureOnly
  Skip the copy, because the files are already in place, and do the parts that
  must run on the machine itself: generate the configuration, build the Python
  environment, create the database account and database, and migrate every
  store. This is what the Windows installer calls once it has placed the files,
  so that configuration has one implementation rather than a second copy living
  inside an installer script.

.PARAMETER DryRun
  Report every step and change nothing. Run this first on a machine you care
  about.

.EXAMPLE
  .\install.ps1 -DryRun
  Shows what would happen, touches nothing.

.EXAMPLE
  .\install.ps1
  Installs for this machine only, on http://127.0.0.1:8000.

.EXAMPLE
  .\install.ps1 -BindHost 0.0.0.0 -WithDemoData
  Serves the local network over plain HTTP and seeds the four demo firms.

.EXAMPLE
  .\install.ps1 -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key
  Serves the local network over HTTPS. Every client machine has to trust that
  certificate.
#>
[CmdletBinding()]
param(
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 8000,
  [string]$CertFile,
  [string]$KeyFile,
  [string]$DatabaseHost = 'localhost',
  [int]$DatabasePort = 5432,
  [string]$DatabaseName = 'agency_platform',
  [string]$DatabaseUser = 'postgres',
  [securestring]$DatabasePassword,
  [string]$AppDatabaseUser = 'agency_app',
  [securestring]$AdminPassword,
  [switch]$WithDemoData,
  [switch]$InstallPrerequisites,
  [string]$InstallDir,
  [switch]$ConfigureOnly,
  [switch]$SkipStart,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$script:RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$script:BackendRoot = Join-Path $script:RepoRoot 'backend'
$script:EnvPath = Join-Path $script:BackendRoot 'config\.env'
$script:Venv = Join-Path $script:BackendRoot '.venv\Scripts\python.exe'
$script:Failed = $false

function Write-Step { param([string]$Text) Write-Host "`n== $Text" -ForegroundColor Cyan }
function Write-Done { param([string]$Text) Write-Host "   $Text" -ForegroundColor Green }
function Write-Skip { param([string]$Text) Write-Host "   $Text" -ForegroundColor DarkGray }
function Write-Warn { param([string]$Text) Write-Host "   $Text" -ForegroundColor Yellow }

function Stop-Install {
  param([string]$Problem, [string]$Fix)
  Write-Host "`nInstall stopped: $Problem" -ForegroundColor Red
  if ($Fix) { Write-Host "  $Fix" -ForegroundColor Red }
  exit 1
}

function Invoke-Agency {
  <#
    Run one of the application's own commands, however this copy is built.

    A built copy is agency-server.exe and has no interpreter at all; a source
    checkout has the virtual environment. Both expose the same subcommands
    through app\cli.py, so the only difference is what gets launched -- which
    is the whole point of there being one entry point.

    It runs from the backend root, because alembic.ini's `script_location` and
    `prepend_sys_path` are both relative to the working directory.

    Output comes back on the pipeline -- captured if the caller assigns it,
    printed if not -- and $LASTEXITCODE is what says whether it worked.

    $ErrorActionPreference is relaxed for the duration. Native programs write
    progress to stderr -- alembic logs every migration step there -- and in
    Windows PowerShell 5.1 `2>&1` wraps each of those lines in an ErrorRecord,
    which under 'Stop' aborts the script on the first one. That is the same
    trap start_backend.ps1 documents, and it is why this is not simply inline.
  #>
  param([Parameter(Mandatory)][string[]]$Arguments)
  $compiled = Join-Path $script:BackendRoot 'agency-server.exe'
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  Push-Location $script:BackendRoot
  try {
    if (Test-Path $compiled) {
      return (& $compiled @Arguments 2>&1)
    }
    return (& $script:Venv -m app.cli @Arguments 2>&1)
  } finally {
    Pop-Location
    $ErrorActionPreference = $previous
  }
}

function Copy-Application {
  <#
    Copy the application to where it is being installed, keeping whatever the
    destination already holds that belongs to the firm rather than to us.

    Three directories survive an update, and the reasons differ:

      config\  the signing key and the database password. Replacing it signs
               every user out and locks the application out of its own data.
      logs\    the record of what the application did, which is often the
               only evidence when something went wrong before the update.
      storage\ whatever the firm has attached to its own records.

    .venv is deliberately NOT copied: it holds absolute paths from the machine
    that built it, so a copied one is broken in ways that surface much later.
    The Python step below rebuilds it at the destination.
  #>
  param([string]$From, [string]$To)

  # An allow-list, not a deny-list. It used to exclude four names and copy
  # everything else, which shipped tests\, docs\, Dockerfile, uv.lock and the
  # repository's own README to every customer. Naming what the application
  # actually needs is the only version of this that stays correct as the tree
  # grows.
  $ship = @('app', 'alembic', 'scripts', 'config', 'alembic.ini', 'pyproject.toml')
  $keep = @('config', 'logs', 'storage')
  New-Item -ItemType Directory -Force -Path $To | Out-Null

  $backendFrom = Join-Path $From 'backend'
  $backendTo = Join-Path $To 'backend'
  New-Item -ItemType Directory -Force -Path $backendTo | Out-Null

  foreach ($entry in Get-ChildItem -Force $backendFrom) {
    if ($entry.Name -notin $ship) { continue }
    $destination = Join-Path $backendTo $entry.Name
    if ($entry.Name -in $keep -and (Test-Path $destination)) {
      Write-Skip "kept the existing backend\$($entry.Name)"
      continue
    }
    if ($entry.PSIsContainer) {
      # Contents, not the folder. `Copy-Item -Recurse` onto a destination that
      # already exists puts the source folder *inside* it -- an app\app --
      # and leaves the original files untouched, so an update would ship the
      # old code and nest a duplicate tree. Found by installing twice.
      New-Item -ItemType Directory -Force -Path $destination | Out-Null
      Copy-Item -Path (Join-Path $entry.FullName '*') -Destination $destination -Recurse -Force
      if ($entry.Name -eq 'config') {
        # **A developer's .env must never reach a customer.** config\ is shipped
        # for .env.example, which the Configuration step reads as its template.
        # On a *fresh* install the destination config\ does not exist, so the
        # $keep rule above does not fire and the whole folder is copied --
        # including a .env holding the development signing key and database
        # password. The Configuration step would then find that file, report
        # "left alone", and never generate real credentials, so every customer
        # would share one signing key. Found reviewing the copy on 2026-09-17.
        Get-ChildItem -Force -Path $destination -Filter '.env*' |
          Where-Object { $_.Name -ne '.env.example' } |
          ForEach-Object {
            Remove-Item -Force $_.FullName
            Write-Skip "did not ship backend\config\$($_.Name)"
          }
      }
    } else {
      Copy-Item -Path $entry.FullName -Destination $destination -Force
    }
  }

  # The built client, if there is one. Its path shape is kept so everything
  # downstream finds it where it expects.
  $clientFrom = Join-Path $From 'desktop\build\windows\x64\runner\Release'
  if (Test-Path $clientFrom) {
    $clientTo = Join-Path $To 'desktop\build\windows\x64\runner\Release'
    New-Item -ItemType Directory -Force -Path $clientTo | Out-Null
    Copy-Item -Path (Join-Path $clientFrom '*') -Destination $clientTo -Recurse -Force
  }
}

function Select-InstallFolder {
  <#
    Show the Windows folder picker and return the chosen folder, or $null when
    it was cancelled or cannot be shown.

    The dialog needs a single-threaded apartment. install.bat launches Windows
    PowerShell 5.1, which is STA by default, but `powershell -MTA` or a host
    that is not would hang or throw inside ShowDialog -- so that case falls back
    to typing rather than failing the install.

    It is parented to a hidden topmost form. Without an owner the picker can
    open *behind* the console window it was asked from, and the installer then
    looks frozen while it waits for an answer nobody can see.
  #>
  if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') { return $null }
  try { Add-Type -AssemblyName System.Windows.Forms } catch { return $null }
  $owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
  $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
  $dialog.Description = 'Choose where to install the Agency Platform. Pick an empty folder, or any folder and an AgencyPlatform folder is made inside it.'
  $dialog.ShowNewFolderButton = $true
  $dialog.SelectedPath = "$env:SystemDrive\"
  try {
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
      return $dialog.SelectedPath
    }
    return $null
  } finally {
    $dialog.Dispose()
    $owner.Dispose()
  }
}

function Resolve-PickedFolder {
  <#
    Turn a folder chosen in the picker into the folder to install into.

    The application is copied *into* the target -- backend\, desktop\ and the
    rest land directly under it -- so picking D:\ or Program Files would scatter
    it across a folder that holds other things. A picked folder is used as it is
    only when it is empty (somebody made it for this, often with the dialog's own
    New Folder button) or already holds an install (this is an update);
    anything else gets an AgencyPlatform folder inside it.
  #>
  param([Parameter(Mandatory)][string]$Picked)
  $isInstall = (Test-Path (Join-Path $Picked 'backend\config\.env')) -or
    (Test-Path (Join-Path $Picked 'backend\agency-server.exe'))
  $isEmpty = -not (Get-ChildItem -Force -LiteralPath $Picked -ErrorAction SilentlyContinue |
    Select-Object -First 1)
  if ($isInstall -or $isEmpty) { return $Picked }
  return (Join-Path $Picked 'AgencyPlatform')
}

# -- 0. Where this is being installed --------------------------------------

$script:SourceRoot = $script:RepoRoot
if (-not $InstallDir -and -not $DryRun -and [Environment]::UserInteractive) {
  $default = 'C:\AgencyPlatform'
  while (-not $InstallDir) {
    $answer = Read-Host "Install where? [Enter for $default, B to browse, or type a folder]"
    if ([string]::IsNullOrWhiteSpace($answer)) {
      $InstallDir = $default
    } elseif ($answer.Trim() -in @('b', 'browse')) {
      $picked = Select-InstallFolder
      if ($picked) {
        $InstallDir = Resolve-PickedFolder -Picked $picked
        Write-Host "  chosen: $InstallDir"
      } else {
        Write-Warn 'No folder was chosen. Press Enter for the default, B to browse again, or type a folder.'
      }
    } else {
      $InstallDir = $answer.Trim()
    }
  }
}

if ($InstallDir -and $ConfigureOnly) {
  # Already installed by whoever called us; just work where they put it.
  $script:RepoRoot = [System.IO.Path]::GetFullPath(
    [System.IO.Path]::Combine((Get-Location).Path, $InstallDir))
  $script:BackendRoot = Join-Path $script:RepoRoot 'backend'
  $script:EnvPath = Join-Path $script:BackendRoot 'config\.env'
  $script:Venv = Join-Path $script:BackendRoot '.venv\Scripts\python.exe'
  Write-Host "  configuring: $script:RepoRoot"
} elseif ($InstallDir) {
  $target = [System.IO.Path]::GetFullPath(
    [System.IO.Path]::Combine((Get-Location).Path, $InstallDir))
  $here = [System.IO.Path]::GetFullPath($script:SourceRoot)
  if ($target.TrimEnd('\') -ieq $here.TrimEnd('\')) {
    Write-Host "  installing in place: $here"
  } elseif ($DryRun) {
    Write-Host "  would install into: $target"
  } else {
    $updating = Test-Path (Join-Path $target 'backend\config\.env')
    Write-Host ("  {0}: {1}" -f $(if ($updating) { 'updating' } else { 'installing into' }), $target)
    Copy-Application -From $script:SourceRoot -To $target
    # Everything from here on refers to the installed copy, not the source.
    $script:RepoRoot = $target
    $script:BackendRoot = Join-Path $target 'backend'
    $script:EnvPath = Join-Path $script:BackendRoot 'config\.env'
    $script:Venv = Join-Path $script:BackendRoot '.venv\Scripts\python.exe'
    Write-Done "application copied to $target"
  }
}

# -- 0b. Arguments that contradict each other ------------------------------
# Caught before anything is changed, so a typo cannot leave a half-install.

if ($CertFile -and -not $KeyFile) { Stop-Install 'CertFile was given without KeyFile.' 'TLS needs both.' }
if ($KeyFile -and -not $CertFile) { Stop-Install 'KeyFile was given without CertFile.' 'TLS needs both.' }
foreach ($file in @($CertFile, $KeyFile)) {
  if ($file -and -not (Test-Path $file)) { Stop-Install "Certificate file not found: $file" }
}
$scheme = if ($CertFile) { 'https' } else { 'http' }

Write-Host "Agency Platform installer"
Write-Host "  repository: $script:RepoRoot"
Write-Host "  backend:    ${scheme}://${BindHost}:${Port}"
if ($DryRun) { Write-Host "  DRY RUN -- nothing will be changed" -ForegroundColor Yellow }

# -- 1. Prerequisites -------------------------------------------------------

Write-Step 'Checking prerequisites'

function Test-Command { param([string]$Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function New-Secret {
  # Deliberately no quotes, backslashes, spaces or semicolons. This value is
  # inlined into `CREATE ROLE ... PASSWORD '...'` -- PostgreSQL takes no bind
  # parameter there and rejects the statement outright -- and it is written to
  # a .env file read as plain text. Both are places where a stray quote turns
  # a password into a syntax error, which is the trap the compose file already
  # documents for its own JSON.
  param([int]$Length = 28)
  $alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_.~'
  $bytes = [byte[]]::new($Length)
  # Create().GetBytes(), not Fill(). Fill() is .NET Core only and this script
  # runs under Windows PowerShell 5.1 -- install.bat invokes `powershell`, not
  # `pwsh` -- where the call does not exist. Getting that wrong does not fail
  # loudly: the byte array stays all zeros and every generated secret becomes
  # the same predictable string.
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Protect-File {
  # The .env holds the signing key, the database password and the bootstrap
  # administrator password. On a shared machine a standard user can otherwise
  # read all three. This does not defend against an administrator -- nothing
  # on that machine does -- it stops casual and accidental exposure.
  param([string]$Path)
  try {
    $acl = Get-Acl $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($account in @('BUILTIN\Administrators', 'NT AUTHORITY\SYSTEM', $env:USERNAME)) {
      $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $account, 'FullControl', 'Allow')
      $acl.AddAccessRule($rule)
    }
    Set-Acl -Path $Path -AclObject $acl
    return $true
  } catch {
    return $false
  }
}

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  return ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Update-SessionPath {
  # winget writes the new entries to the registry, not to this process. Without
  # this, installing Python and then using it in the same run cannot work: the
  # script would install it, print a note about opening a new terminal, and
  # then fail on `python -m venv` two steps later.
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
}

function Get-RealPython {
  # `python` on a machine that has never had Python is the Microsoft Store app
  # execution alias under WindowsApps: Get-Command finds it, running it prints
  # no version and opens the Store instead. Treating that as "Python is here"
  # is worse than finding nothing, because the run then fails later and
  # somewhere else. Returns the version string, or $null.
  $command = Get-Command python -ErrorAction SilentlyContinue
  if (-not $command) { return $null }
  if ($command.Source -and $command.Source -like '*\WindowsApps\*') { return $null }
  # No 2>&1 here. In Windows PowerShell 5.1 that wraps a native program's
  # stderr in an ErrorRecord, and with $ErrorActionPreference = 'Stop' the
  # first such line ends the script -- which is exactly how this installer
  # once died after "Applying migrations...". stderr is left where it is.
  $version = & $command.Source --version
  if ($LASTEXITCODE -ne 0) { return $null }
  if ($version -match '(\d+)\.(\d+)') { return $version }
  return $null
}

$missing = @()

# A released copy is compiled: agency-server.exe carries its own Python and
# every dependency, so the machine needs neither. Asking for Python there would
# stop an install that was always going to work, or -- worse, with
# -InstallPrerequisites -- put a Python on a customer's machine to satisfy a
# check rather than a need.
$script:Compiled = Test-Path (Join-Path $script:BackendRoot 'agency-server.exe')

if ($script:Compiled) {
  Write-Done 'this is a compiled build -- no Python is needed on this machine'
} else {
  $version = Get-RealPython
  if (-not $version) {
    # Covers all three: no python at all, the Store stub, and a python that is
    # on PATH but cannot run. Previously a stub fell through every branch
    # silently and the installer carried on as though Python were present.
    $missing += @{ Name = 'Python 3.13+'; Winget = 'Python.Python.3.13' }
  } elseif ($version -match '(\d+)\.(\d+)') {
    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 13)) {
      $missing += @{ Name = "Python 3.13+ (found $version)"; Winget = 'Python.Python.3.13' }
    } else { Write-Done "Python: $version" }
  }
}

# PostgreSQL is deliberately not checked here. Looking for `psql` on PATH or a
# `postgresql*` service says nothing useful: on this project's own development
# machine the server runs in Docker, so both checks find nothing while the
# database works perfectly. The question that matters is whether the server
# answers, and that is asked in the database step below -- after the Python
# environment exists to ask it with.

if ($missing.Count -gt 0) {
  foreach ($item in $missing) { Write-Warn "missing: $($item.Name)" }
  if (-not $InstallPrerequisites) {
    $commands = ($missing | ForEach-Object { "winget install --id $($_.Winget) --accept-package-agreements --accept-source-agreements" }) -join "`n  "
    Stop-Install 'Prerequisites are missing.' "Install them and run again, or re-run with -InstallPrerequisites:`n  $commands"
  }
  if (-not (Test-Command 'winget')) {
    Stop-Install 'winget is not available, so prerequisites cannot be installed automatically.' 'Install Python 3.13+ and PostgreSQL 17 by hand, then run this again.'
  }
  if (-not $DryRun -and -not (Test-Administrator)) {
    Stop-Install 'Installing prerequisites needs an elevated shell.' 'Right-click install.bat and choose Run as administrator, or install Python 3.13+ and PostgreSQL 17 by hand and run this again without -InstallPrerequisites.'
  }
  foreach ($item in $missing) {
    if ($DryRun) { Write-Skip "would install $($item.Name) via winget"; continue }
    Write-Host "   installing $($item.Name)..."
    & winget install --id $item.Winget --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
      Stop-Install "winget could not install $($item.Name)." 'Check the network connection, or install it by hand and run this again.'
    }
  }
  if (-not $DryRun) {
    Update-SessionPath
    if (-not (Get-RealPython)) {
      Stop-Install 'Python was installed but this shell still cannot run it.' 'Close this window, open a new one, and run the installer again -- it will continue from here.'
    }
    Write-Done 'PATH refreshed for this session'
  }
}

# -- 2. Configuration -------------------------------------------------------

Write-Step 'Configuration'

if (Test-Path $script:EnvPath) {
  Write-Skip "config\.env exists -- left alone (it holds the signing key and database password)"
} elseif ($DryRun) {
  Write-Skip 'would write backend\config\.env with a generated signing key'
} else {
  # Nothing here is asked of the customer. The application's own database
  # password is generated and never shown -- it is written to config\.env and
  # used from there. The administrator password is generated too when none was
  # given, and reported once at the end, because somebody has to be able to
  # sign in.
  $script:AppDbPassword = New-Secret
  $plainDb = $script:AppDbPassword
  if ($AdminPassword) {
    $plainAdmin = [System.Net.NetworkCredential]::new('', $AdminPassword).Password
    if ([string]::IsNullOrWhiteSpace($plainAdmin)) { Stop-Install 'The administrator password cannot be empty.' }
  } else {
    $plainAdmin = New-Secret -Length 20
    $script:GeneratedAdminPassword = $plainAdmin
  }

  # A real signing key, not the development one. The application refuses to
  # start outside development with the development key, and this is what stops
  # an install inheriting it from the example file.
  $bytes = [byte[]]::new(48)
  # See New-Secret: Fill() does not exist under Windows PowerShell 5.1, which
  # is the shell install.bat launches. This generated the signing key, so the
  # failure mode was an application signing every token with a key of zeros.
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  $jwtKey = [Convert]::ToBase64String($bytes)

  $example = Join-Path $script:BackendRoot 'config\.env.example'
  if (-not (Test-Path $example)) { Stop-Install "Missing $example -- this does not look like a full checkout." }

  $lines = Get-Content $example | ForEach-Object {
    switch -Regex ($_) {
      '^AGENCY_ENVIRONMENT=' { 'AGENCY_ENVIRONMENT=production'; break }
      '^AGENCY_JWT_SECRET_KEY=' { "AGENCY_JWT_SECRET_KEY=$jwtKey"; break }
      '^AGENCY_DATABASE_PASSWORD=' { "AGENCY_DATABASE_PASSWORD=$plainDb"; break }
      '^AGENCY_BOOTSTRAP_ADMIN_PASSWORD=' { "AGENCY_BOOTSTRAP_ADMIN_PASSWORD=$plainAdmin"; break }
      '^AGENCY_DATABASE_HOST=' { "AGENCY_DATABASE_HOST=$DatabaseHost"; break }
      '^AGENCY_DATABASE_NAME=' { "AGENCY_DATABASE_NAME=$DatabaseName"; break }
      '^AGENCY_DATABASE_USERNAME=' { "AGENCY_DATABASE_USERNAME=$AppDatabaseUser"; break }
      '^# AGENCY_DATABASE_PORT=' { "AGENCY_DATABASE_PORT=$DatabasePort"; break }
      default { $_ }
    }
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $script:EnvPath) | Out-Null
  Set-Content -Path $script:EnvPath -Value $lines -Encoding utf8
  Write-Done "wrote backend\config\.env -- signing key and database password generated, database account '$AppDatabaseUser'"
  if (Protect-File $script:EnvPath) {
    Write-Done 'config\.env restricted to administrators and this account'
  } else {
    Write-Warn 'Could not restrict permissions on config\.env -- check who can read it.'
  }
  Write-Warn 'Back that file up. Losing the signing key signs every user out; losing it and the database password locks the application out of its own data.'
}

# -- 3. Python environment --------------------------------------------------

Write-Step 'Python environment'

if ($script:Compiled) {
  # Nothing to build. The compiled binary carries its own interpreter and every
  # dependency, which is the whole reason a customer machine needs no network
  # access at this step and no toolchain afterwards.
  Write-Skip 'not needed -- this build carries its own'
} elseif (Test-Path $script:Venv) {
  Write-Skip '.venv exists'
} elseif ($DryRun) {
  Write-Skip 'would create backend\.venv and install dependencies'
} else {
  Push-Location $script:BackendRoot
  try {
    if (Test-Command 'uv') {
      & uv sync
      if ($LASTEXITCODE -ne 0) { Stop-Install 'uv sync failed.' 'Check the network connection and run again.' }
    } else {
      & python -m venv .venv
      & $script:Venv -m pip install --upgrade pip --quiet
      & $script:Venv -m pip install -e . --quiet
      if ($LASTEXITCODE -ne 0) { Stop-Install 'Installing Python dependencies failed.' 'Check the network connection and run again.' }
    }
  } finally { Pop-Location }
  Write-Done 'dependencies installed'
}

if (-not $DryRun -and -not $script:Compiled -and -not (Test-Path $script:Venv)) {
  Stop-Install 'The virtual environment was not created.' 'Run again, or create it by hand with: python -m venv backend\.venv'
}

# -- 4. Database ------------------------------------------------------------

Write-Step 'Database'

if ($DryRun) {
  Write-Skip "would create the database '$DatabaseName' if it does not exist"
} else {
  # The application's own account and database, created with a privileged
  # connection that is used for this step and then forgotten. Everything
  # afterwards -- migrations, the server itself -- runs as the application
  # account, which owns its database and is not a superuser.
  #
  # The credentials arrive by environment variable rather than on the command
  # line, where `ps` and the console history would show them.
  # The program that does this used to live here, in a here-string piped
  # into the interpreter on stdin. That cannot work on a machine with no
  # interpreter -- which is the machine a built copy is for -- so it has moved
  # into app\core\database\bootstrap.py and is reached as a subcommand.
  # The output shape is unchanged; the lines below still parse it.
  Push-Location $script:BackendRoot
  try {
    if ($DatabasePassword) {
      $env:INSTALL_ADMIN_USER = $DatabaseUser
      $env:INSTALL_ADMIN_PASSWORD =
        [System.Net.NetworkCredential]::new('', $DatabasePassword).Password
    }
    $result = Invoke-Agency -Arguments @('create-database')
    if ($LASTEXITCODE -ne 0 -and $InstallPrerequisites -and $DatabaseHost -in @('localhost', '127.0.0.1', '::1')) {
      # The server did not answer and the caller asked for prerequisites, so
      # this is the clean-machine case: install PostgreSQL and ask once more.
      # Probing first is what stops a machine that already runs PostgreSQL --
      # in Docker, in WSL, on another box -- being given a second copy it does
      # not need.
      if (-not (Test-Command 'winget')) {
        Stop-Install 'PostgreSQL did not answer and winget is not available to install it.' 'Install PostgreSQL 17 by hand, then run this again.'
      }
      if (-not (Test-Administrator)) {
        Stop-Install 'Installing PostgreSQL needs an elevated shell.' 'Right-click install.bat and choose Run as administrator, or install PostgreSQL 17 by hand and run this again.'
      }
      Write-Host '   PostgreSQL did not answer. Installing it...'
      & winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements --silent
      if ($LASTEXITCODE -ne 0) { Stop-Install 'winget could not install PostgreSQL.' 'Check the network connection, or install it by hand and run this again.' }
      Write-Warn 'PostgreSQL installed. Its service may need a moment, and this shell may need to be reopened for new PATH entries.'
      Start-Sleep -Seconds 10
      $result = Invoke-Agency -Arguments @('create-database')
    }
    if ($LASTEXITCODE -ne 0) {
      $advice = @(
        "  Checked ${DatabaseHost}:${DatabasePort} as '$DatabaseUser'.",
        '  Likely causes, in the order worth checking:',
        '    - PostgreSQL is not running (a service, a container, or another machine).',
        "    - The password in backend\config\.env does not match the server's.",
        '    - The host or port is wrong -- pass -DatabaseHost and -DatabasePort.',
        '    - PostgreSQL is not installed. Re-run with -InstallPrerequisites, or:',
        '        winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements'
      ) -join "`n"
      Stop-Install 'Could not reach PostgreSQL.' "$result`n$advice"
    }
    foreach ($line in @("$result" -split "`n")) {
      switch -Regex ($line.Trim()) {
        '^role-created:(.+)$' { Write-Done "created database account '$($Matches[1])' (not a superuser)" }
        '^role-updated:(.+)$' { Write-Skip "database account '$($Matches[1])' exists -- password re-set to match config\.env" }
        '^created:(.+)$' { Write-Done "created database '$($Matches[1])', owned by '$AppDatabaseUser'" }
        '^exists:(.+)$' { Write-Skip "database '$($Matches[1])' exists" }
      }
    }
  } finally {
    # The privileged password lives no longer than the step that needs it.
    Remove-Item Env:\INSTALL_ADMIN_USER -ErrorAction SilentlyContinue
    Remove-Item Env:\INSTALL_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    Pop-Location
  }
}

# -- 5. Migrations ----------------------------------------------------------
# Every store, not just the platform schema. `alembic upgrade head` advances
# one schema chosen by AGENCY_DATABASE_SCHEMA, so a firm store is silently left
# behind and nothing reports it until a query hits a missing column.

Write-Step 'Migrations'

if ($DryRun) {
  Invoke-Agency -Arguments @('migrate-all', '--dry-run')
  if ($LASTEXITCODE -ne 0) { Write-Warn 'Could not read the stores. On a fresh machine that is expected: the database does not exist yet.' }
} else {
  Invoke-Agency -Arguments @('migrate-all', '--yes')
  if ($LASTEXITCODE -ne 0) { Stop-Install 'One or more stores failed to migrate.' 'The output above names which. Fix it and run this again -- it reports every store rather than stopping at the first.' }
  Write-Done 'every store is at head'
}

# -- 6. Demo data (optional) ------------------------------------------------

if ($WithDemoData) {
  Write-Step 'Demo data'
  # The one step that is not part of the product. The seeder is tooling for
  # showing this to somebody -- it carries its own passwords, and the release
  # build does not stage it -- so a built copy has no seeder and no interpreter
  # to run one with. Say that, rather than failing three lines later with a
  # path that does not exist.
  if (-not (Test-Path $script:Venv)) {
    Stop-Install 'This copy has no demo seeder.' 'Demo data is for a development checkout; a released build ships the product only. Create a firm from the Firms screen instead.'
  }
  if ($DryRun) {
    Write-Skip 'would seed four demo firms and three financial years of trading'
  } else {
    Push-Location $script:BackendRoot
    try {
      & $script:Venv scripts/seed_multi_firm_demo.py
      if ($LASTEXITCODE -ne 0) { Stop-Install 'Seeding the demo data failed.' 'The application is installed and migrated; re-run the seeder by hand to see the failure.' }
      Write-Done 'demo firms seeded'
    } finally { Pop-Location }
  }
}

# -- 7. Desktop client ------------------------------------------------------

Write-Step 'Desktop client'

$desktopExe = Join-Path $script:RepoRoot 'desktop\build\windows\x64\runner\Release\agency_desktop.exe'
if (Test-Path $desktopExe) {
  Write-Done 'client is built'
} elseif (Test-Command 'flutter') {
  if ($DryRun) {
    Write-Skip 'would build the desktop client with flutter build windows --release'
  } else {
    Push-Location (Join-Path $script:RepoRoot 'desktop')
    try {
      & flutter build windows --release --dart-define="API_BASE_URL=${scheme}://${BindHost}:${Port}"
      if ($LASTEXITCODE -ne 0) { Write-Warn 'Building the client failed. The backend is installed; build the client by hand.' }
      else { Write-Done 'client built' }
    } finally { Pop-Location }
  }
} else {
  Write-Warn 'No built client and no Flutter SDK. The backend is usable on its own; install Flutter to build the client, or copy a build from another machine.'
}

# -- 8. Start ---------------------------------------------------------------

# One command line, used both to start the backend below and as the hint printed
# when this run does not start it -- so the hint is the command that works.
# They used to be built separately, and the hint left out -SkipSync: followed
# on an installed copy, start_backend.ps1 then reached for `uv`, which a
# customer machine does not have.
#
# Each part is quoted when it holds a space. Windows PowerShell 5.1's
# Start-Process joins an -ArgumentList array with bare spaces, so a folder like
# D:\My Apps\AgencyPlatform -- easy to pick in the folder browser -- arrived as
# two arguments and the backend never started.
$startScript = Join-Path $script:BackendRoot 'scripts\start_backend.ps1'
$startArgs = @('-ExecutionPolicy', 'Bypass', '-File', $startScript,
  '-BindHost', $BindHost, '-Port', "$Port", '-NoReload', '-SkipSync')
if ($CertFile) { $startArgs += @('-CertFile', $CertFile, '-KeyFile', $KeyFile) }
$startLine = ($startArgs | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join ' '

if ($SkipStart -or $DryRun) {
  Write-Step 'Done'
  Write-Host "   Start the backend with:"
  Write-Host "     powershell $startLine"
  if ($script:GeneratedAdminPassword) {
    Write-Host "   Sign in as: platform-admin@agency.local"
    Write-Host "   Password:   $script:GeneratedAdminPassword" -ForegroundColor Yellow
    Write-Host "   Write that password down now. It is not shown again." -ForegroundColor Yellow
  }
  exit 0
}

Write-Step 'Starting the backend'
if (-not $CertFile -and $BindHost -ne '127.0.0.1') {
  Write-Warn 'Plain HTTP on a network interface: passwords cross the wire in clear text. Use -CertFile and -KeyFile on any network you do not control.'
}

Start-Process -FilePath 'powershell' -ArgumentList $startLine

Write-Host '   waiting for the backend to answer...'
$healthy = $false
foreach ($attempt in 1..30) {
  Start-Sleep -Seconds 2
  try {
    $uri = "${scheme}://${BindHost}:${Port}/health"
    if ($BindHost -eq '0.0.0.0') { $uri = "${scheme}://127.0.0.1:${Port}/health" }
    # -SkipCertificateCheck is PowerShell 6+, and install.bat runs Windows
    # PowerShell 5.1. Passing it there throws a parameter error that reads like
    # the backend failed, so it is only added when the shell has it.
    $webArgs = @{ Uri = $uri; TimeoutSec = 4; ErrorAction = 'Stop'; UseBasicParsing = $true }
    if ((Get-Command Invoke-WebRequest).Parameters.ContainsKey('SkipCertificateCheck')) {
      $webArgs['SkipCertificateCheck'] = $true
    }
    $response = Invoke-WebRequest @webArgs
    if ($response.StatusCode -eq 200) { $healthy = $true; break }
  } catch { continue }
}
if (-not $healthy) {
  Stop-Install 'The backend did not answer /health within a minute.' 'Look at the newest file in backend\logs for the reason.'
}
Write-Done "backend answering on ${scheme}://${BindHost}:${Port}"

if (Test-Path $desktopExe) {
  Start-Process -FilePath $desktopExe
  Write-Done 'client started'
}

Write-Host "`nInstalled." -ForegroundColor Green
Write-Host "  Sign in as: platform-admin@agency.local"
if ($script:GeneratedAdminPassword) {
  # The one secret a person has to carry away. It is generated rather than
  # asked for, so this is the only place it is ever shown -- it is written to
  # config\.env, which is restricted, and never printed again.
  Write-Host "  Password:   $script:GeneratedAdminPassword" -ForegroundColor Yellow
  Write-Host "  Write that password down now. It is not shown again." -ForegroundColor Yellow
} else {
  Write-Host "  Password:   the administrator password you supplied."
}
Write-Host "  It must be changed on first use, and it has no firm membership, so create a firm before opening firm screens."
