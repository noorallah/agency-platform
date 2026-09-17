<#
.SYNOPSIS
  Refuse to ship a tree that contains something it should not.

.DESCRIPTION
  A promise nobody checks is a promise that quietly stops being true. This is
  what makes "no source, no secrets, no development files" a fact about the
  build rather than an intention: it exits non-zero, and build_installer.ps1
  stops before producing an installer.

  Runnable on its own against any directory, which is the point -- pointing it
  at an *installed* copy on a customer machine answers "what did we actually
  give them" without reading a build log.

.PARAMETER Path
  The directory to inspect. Normally dist\staging.

.PARAMETER AllowPython
  Permit .py files anywhere. Only meaningful before the backend is compiled:
  until then the staged tree is Python source by design, and this switch says
  so out loud rather than silently weakening the check.

.EXAMPLE
  .\packaging\verify_release.ps1 -Path dist\staging
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Path,
  [switch]$AllowPython
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Path)) { Write-Host "No such directory: $Path" -ForegroundColor Red; exit 1 }
$root = (Resolve-Path $Path).Path
$problems = @()

function Report {
  param([string]$What, [string[]]$Found)
  if ($Found.Count -eq 0) {
    Write-Host ("   ok    {0}" -f $What) -ForegroundColor Green
  } else {
    Write-Host ("   FAIL  {0} -- {1} found" -f $What, $Found.Count) -ForegroundColor Red
    $Found | Select-Object -First 5 | ForEach-Object { Write-Host "           $_" -ForegroundColor Red }
    if ($Found.Count -gt 5) { Write-Host "           ... and $($Found.Count - 5) more" -ForegroundColor Red }
    $script:problems += $What
  }
}

Write-Host "Release check: $root"

# 1. Source. Alembic is the deliberate exception, and it is two things rather
#    than one -- the second was found by the first compiled build, on 2026-09-17:
#
#      alembic\versions\*.py  the migrations. Alembic loads them by path at
#                             runtime, calling spec_from_file_location per file.
#      alembic\env.py         the script Alembic *executes* to connect and run
#                             them. `command.upgrade` calls ScriptDirectory.
#                             run_env(), so without this file provisioning a
#                             firm fails on a customer's machine -- the one
#                             flow they perform unaided.
#
#    Both are schema plumbing rather than business logic, and the customer's own
#    PostgreSQL exposes that same schema to anyone who looks at it. Nothing else
#    may be source: `app\` is compiled into agency-server.exe.
$allowedSource = '\\alembic\\versions\\|\\alembic\\env\.py$'
$python = Get-ChildItem $root -Recurse -File -Filter *.py -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch $allowedSource } |
  ForEach-Object { $_.FullName.Substring($root.Length + 1) }
if ($AllowPython) {
  Write-Host ("   note  {0} .py files, allowed by -AllowPython (backend not compiled)" -f $python.Count) -ForegroundColor Yellow
} else {
  Report 'no Python source outside alembic' $python
}

# 2. A developer's configuration. .env.example is the template and belongs.
$envFiles = Get-ChildItem $root -Recurse -File -Force -Filter '.env*' -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -ne '.env.example' } |
  ForEach-Object { $_.FullName.Substring($root.Length + 1) }
Report 'no .env (only .env.example)' $envFiles

# 3. Things that belong to the repository, not to the product.
$repoOnly = @('tests', 'docs', '.git', '.github', '.venv', '__pycache__',
              'Dockerfile', 'docker-compose.yml', 'uv.lock', '.coverage',
              '.pytest_cache', '.mypy_cache')
if (-not $AllowPython) {
  # A compiled build has no Python package to describe, so a pyproject.toml in
  # the tree means the source-staging path ran -- which is the thing this check
  # exists to notice. It stays allowed under -AllowPython, where staging source
  # is what was asked for.
  $repoOnly += 'pyproject.toml'
}
$found = @()
foreach ($name in $repoOnly) {
  $found += Get-ChildItem $root -Recurse -Force -Filter $name -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName.Substring($root.Length + 1) }
}
Report 'no repository-only files' $found

# 4. The development toolchain, which is most of a virtual environment and none
#    of the product.
$devTools = @()
foreach ($name in @('mypy', 'pytest', '_pytest', 'black', 'ruff', 'coverage', 'mypyc')) {
  $devTools += Get-ChildItem $root -Recurse -Force -Directory -Filter $name -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName.Substring($root.Length + 1) }
}
Report 'no development toolchain' $devTools

# 5. Known development credentials. These are literals from this repository's
#    own seed scripts and settings defaults; finding one in a shipped tree means
#    something was packaged that should never have been.
# Passwords that would actually let somebody in. Deliberately *not* listed:
# the development JWT key and bootstrap password literals in settings.py and
# .env.example. Those are the values the application **refuses** outside
# development -- it compares against them to fail fast -- and the template the
# installer rewrites. They are guard rails, not credentials, and failing the
# build on them would teach whoever meets it to weaken the check.
$secrets = @(
  'DemoAdmin@12345',
  'Fixture@2026pw',
  'Password@123'
)
$leaked = @()
foreach ($file in Get-ChildItem $root -Recurse -File -Force -ErrorAction SilentlyContinue) {
  if ($file.Length -gt 2MB) { continue }
  if ($file.Extension -in @('.dll', '.exe', '.so', '.pyd', '.dat', '.otf', '.ttf', '.png', '.ico', '.zip')) { continue }
  $text = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
  if ($null -eq $text) { continue }
  foreach ($secret in $secrets) {
    if ($text.Contains($secret)) {
      $leaked += ("{0}  ({1})" -f $file.FullName.Substring($root.Length + 1), $secret)
    }
  }
}
Report 'no development credentials' $leaked

Write-Host ""
if ($problems.Count -eq 0) {
  Write-Host "Release check passed." -ForegroundColor Green
  exit 0
}
Write-Host ("Release check FAILED: {0}" -f ($problems -join '; ')) -ForegroundColor Red
Write-Host "No installer should be produced from this tree." -ForegroundColor Red
exit 1
