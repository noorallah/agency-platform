<#
.SYNOPSIS
  The machine-level half of the Windows installer: the private database, the
  server as a service, the firewall, the pre-upgrade backup and the uninstall.

.DESCRIPTION
  AgencyPlatform.iss places files; this script does everything that has to
  happen on the machine itself, and the .iss reads its exit code and its output.
  Configuration -- config\.env, the database account, the migrations -- is still
  install.ps1 -ConfigureOnly, called from here, so it keeps one implementation.

  Actions:

    Backup     Before an upgrade replaces any file. Stops AgencyPlatformServer,
               dumps every store this server uses (read from the *installed*
               agency-server's `migrate-all --dry-run`) to
               <DataRoot>\backups\pre-upgrade-<old>-<stamp>\, then stops
               AgencyPlatformDB so its binaries can be replaced. Exits non-zero
               if any dump fails, and the .iss stops the upgrade.

    Server     After the files are in place. On a fresh machine: initdb into
               <DataRoot>\pgdata with a generated superuser password, on the
               first free port of 5433-5440,
               register AgencyPlatformDB, configure, create the
               AgencyPlatformServer service, open the firewall if asked, wait
               for /health. On an upgrade: none of initdb, no new password --
               start the database, migrate every store, start the service,
               wait for /health.

    Client     Point the desktop client at a server: writes server_url into
               {app}\config\branding.json.

    CheckPort  Whether -ApiPort is free for the server (D-SETUP-9). Exit 0
               when it is, or when this install already holds it; exit 3 and
               name the program holding it otherwise. The .iss runs it when
               the Ports page is left.

    Uninstall  Stop and remove both services and the firewall rule; with
               -DeleteData, also the database, backups and logs.

  Every line it prints also goes to -LogFile. The one secret it hands back --
  the first administrator password -- is printed on stdout for the .iss and is
  never written to the log.

.NOTES
  Service accounts, and why:

    AgencyPlatformDB      NT AUTHORITY\NetworkService, the account the
                          PostgreSQL project's own installer uses. pg_ctl
                          register takes it by name and it needs no password.
    AgencyPlatformServer  the virtual account NT SERVICE\AgencyPlatformServer.
                          Least privilege by construction: it exists only for
                          this service, holds no password, and can touch only
                          what is granted to it below -- modify on the logs and
                          storage folders, read on config\.env. WinSW installs
                          the service as LocalSystem; `sc.exe config obj=` then
                          moves it to the virtual account, which is the
                          documented way to use one and needs nothing from WinSW.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Backup', 'DailyBackup', 'Server', 'Client', 'Uninstall', 'CheckPort')]
  [string]$Action,
  [Parameter(Mandatory = $true)][string]$InstallDir,
  [string]$DataRoot = (Join-Path $env:ProgramData 'Agency Platform'),
  [string]$LogFile,
  [string]$PreviousVersion = 'unknown',
  [switch]$AllowLan,
  [string]$ServerUrl,
  # The server's port. 0 keeps the one an earlier install used, else 8000.
  [int]$ApiPort = 0,
  [switch]$DeleteData,
  # How many daily backups -DailyBackup keeps; older ones are deleted.
  [int]$KeepDaily = 7
)

$ErrorActionPreference = 'Stop'

$DbService = 'AgencyPlatformDB'
$DbDisplayName = 'Agency Platform Database'
$ServerService = 'AgencyPlatformServer'
$ServerDisplayName = 'Agency Platform Server'
# The private database takes the first free port of these on a fresh
# install and keeps it: an upgrade reads it back from its own postgresql.conf.
$DbPortRange = 5433..5440
$DbPort = $DbPortRange[0]
$DefaultApiPort = 8000
$FirewallRule = 'AgencyPlatformServer-TCP'
# The name the rule had while the port was fixed; removed on upgrade.
$LegacyFirewallRule = 'AgencyPlatformServer-TCP-8000'
$BackupTask = 'Agency Platform daily backup'
$AdminAccount = 'platform-admin@agency.local'

# Well-known SIDs, so nothing here depends on the display language of Windows:
# "Administrators" is "Administratoren" on a German machine.
$SidAdministrators = '*S-1-5-32-544'
$SidSystem = '*S-1-5-18'
$SidNetworkService = '*S-1-5-20'
$SidUsers = '*S-1-5-32-545'
$SidAuthenticatedUsers = '*S-1-5-11'
$SidEveryone = '*S-1-1-0'
$ServiceAccount = "NT SERVICE\$ServerService"

$InstallDir = $InstallDir.TrimEnd('\')
$Backend = Join-Path $InstallDir 'backend'
$EnvPath = Join-Path $Backend 'config\.env'
$ReadyMarker = Join-Path $Backend 'config\database-ready'
$AgencyServer = Join-Path $Backend 'agency-server.exe'
$PgBin = Join-Path $InstallDir 'pgsql\bin'
$PgData = Join-Path $DataRoot 'pgdata'
$Logs = Join-Path $DataRoot 'logs'
$SuperuserFile = Join-Path $DataRoot 'setup-superuser.tmp'
$FirstLogin = Join-Path $DataRoot 'first-login.txt'
# Which ports this install chose, so an upgrade and a repair keep them.
$PortsFile = Join-Path $DataRoot 'ports.json'
$ServiceDir = Join-Path $InstallDir 'service'
$WinSw = Join-Path $ServiceDir "$ServerService.exe"
$WinSwXml = Join-Path $ServiceDir "$ServerService.xml"

# -- Output -------------------------------------------------------------------

function Write-Log {
  param([string]$Text)
  # Write-Host, not Write-Output: this is called inside functions that return
  # a value, and Write-Output would become part of it. A -File run with its
  # stdout redirected -- which is how the .iss runs this -- still prints it.
  Write-Host $Text
  if ($LogFile) {
    try {
      $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
      Add-Content -LiteralPath $LogFile -Value "$stamp [setup] $Text" -Encoding UTF8
    } catch {
      # A log that cannot be written must not stop the install it records.
    }
  }
}

# What a stop is called in the log. The .iss finds "Install stopped:"; the
# scheduled backup says what it is instead.
$StopWord = 'Install stopped'

function Stop-Setup {
  <# The .iss shows everything from "Install stopped:" to the end. #>
  param([string]$Problem, [string]$Fix)
  Write-Log "${StopWord}: $Problem"
  if ($Fix) { Write-Log "  $Fix" }
  exit 1
}

function Invoke-Native {
  <#
    Run a program, log every line it prints, and return its exit code.

    $ErrorActionPreference is relaxed for the call: Windows PowerShell 5.1
    wraps a native program's stderr in an ErrorRecord, and under 'Stop' the
    first progress line on stderr would end the script. Same trap as
    install.ps1 and start_backend.ps1.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$File,
    [string[]]$Arguments = @(),
    [string]$WorkingDirectory,
    [switch]$Quiet
  )
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  if ($WorkingDirectory) { Push-Location $WorkingDirectory }
  try {
    $script:NativeOutput = @(& $File @Arguments 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
  } finally {
    if ($WorkingDirectory) { Pop-Location }
    $ErrorActionPreference = $previous
  }
  if (-not $Quiet) { foreach ($line in $script:NativeOutput) { Write-Log "    $line" } }
  return $code
}

# -- Helpers ------------------------------------------------------------------

function New-Secret {
  <#
    Same alphabet and generator as install.ps1's: no quotes, backslashes,
    spaces or semicolons, because the value is written into files read as
    plain text and inlined into SQL.
  #>
  param([int]$Length = 28)
  $alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_.~'
  $bytes = New-Object byte[] $Length
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Protect-AdminOnly {
  <# Administrators and SYSTEM, nobody else, nothing inherited. #>
  param([string]$Path)
  $code = Invoke-Native -File 'icacls.exe' -Quiet -Arguments @(
    $Path, '/inheritance:r', '/grant:r', "${SidAdministrators}:F", "${SidSystem}:F")
  if ($code -ne 0) { Write-Log "  warning: could not restrict $Path" }
}

function Protect-DataRoot {
  <#
    The data folder holds the raw database files, the attachments and every
    pre-upgrade dump. Left to inherit from ProgramData, every local Windows
    user can read and create files in it, which reads every firm's data
    without signing in (D-QA-3). So: nothing inherited, Administrators and
    SYSTEM full control, and each service granted only the folder it writes.
    Run on every install and upgrade, so an existing install is corrected too.
  #>
  $code = Invoke-Native -File 'icacls.exe' -Quiet -Arguments @(
    $DataRoot, '/inheritance:r', '/grant:r', "${SidAdministrators}:(OI)(CI)F", "${SidSystem}:(OI)(CI)F")
  if ($code -ne 0) { Stop-Setup "Could not restrict $DataRoot." ($script:NativeOutput -join ' ') }
  # Explicit grants an earlier install or another tool may have left. Only
  # explicit entries are removed; logs\client keeps its own users-modify.
  foreach ($dir in @($DataRoot, $PgData, $Logs, (Join-Path $DataRoot 'storage'), (Join-Path $DataRoot 'backups'))) {
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    Invoke-Native -File 'icacls.exe' -Quiet -Arguments @(
      $dir, '/remove:g', $SidUsers, $SidAuthenticatedUsers, $SidEveryone) | Out-Null
  }
  # Every user's desktop client writes under logs\client (the .iss grants it
  # users-modify); list-only on logs itself lets the Start-menu "logs"
  # shortcut open, while the server's and the database's logs stay closed.
  Grant-Access -Path $Logs -Account $SidUsers -Rights 'RX'
  Grant-Access -Path (Join-Path $Logs 'client') -Account $SidUsers -Rights '(OI)(CI)M'
  # The database runs as NetworkService. Initialize-Cluster grants this on a
  # fresh cluster; repeating it here covers an upgrade whatever its history.
  if (Test-Path -LiteralPath $PgData) {
    Grant-Access -Path $PgData -Account $SidNetworkService -Rights '(OI)(CI)M'
  }
  Grant-Access -Path (Join-Path $Logs 'database') -Account $SidNetworkService -Rights '(OI)(CI)M'
  Write-Log "  $DataRoot restricted to Administrators, SYSTEM and the two services"
}

function Grant-Access {
  param([string]$Path, [string]$Account, [string]$Rights)
  $code = Invoke-Native -File 'icacls.exe' -Quiet -Arguments @($Path, '/grant', "${Account}:$Rights")
  if ($code -ne 0) { Stop-Setup "Could not grant $Account access to $Path." ($script:NativeOutput -join ' ') }
}

function Read-EnvFile {
  $values = @{}
  if (-not (Test-Path -LiteralPath $EnvPath)) { return $values }
  foreach ($line in Get-Content -LiteralPath $EnvPath) {
    if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2].Trim() }
  }
  return $values
}

function Get-ServiceOrNull {
  param([string]$Name)
  return Get-Service -Name $Name -ErrorAction SilentlyContinue
}

function Stop-ServiceAndWait {
  param([string]$Name, [int]$Seconds = 60)
  $service = Get-ServiceOrNull $Name
  if (-not $service) { return }
  if ($service.Status -ne 'Stopped') {
    Write-Log "  stopping $Name"
    try { Stop-Service -Name $Name -Force -ErrorAction Stop } catch { Write-Log "  $($_.Exception.Message)" }
    try {
      $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds($Seconds))
    } catch {
      Stop-Setup "The $Name service did not stop within $Seconds seconds."
    }
  }
}

function Start-ServiceAndWait {
  param([string]$Name, [int]$Seconds = 60)
  $service = Get-ServiceOrNull $Name
  if (-not $service) { Stop-Setup "The $Name service does not exist." }
  if ($service.Status -ne 'Running') {
    Write-Log "  starting $Name"
    try { Start-Service -Name $Name -ErrorAction Stop } catch {
      Stop-Setup "The $Name service would not start: $($_.Exception.Message)" "Its log is under $Logs."
    }
    try {
      $service.WaitForStatus('Running', [TimeSpan]::FromSeconds($Seconds))
    } catch {
      Stop-Setup "The $Name service did not start within $Seconds seconds." "Its log is under $Logs."
    }
  }
}

function Wait-Database {
  <# pg_isready until the private cluster accepts connections. #>
  param([int]$Seconds = 60)
  $isReady = Join-Path $PgBin 'pg_isready.exe'
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    $code = Invoke-Native -File $isReady -Quiet -Arguments @('-h', 'localhost', '-p', "$DbPort")
    if ($code -eq 0) { return }
    Start-Sleep -Seconds 2
  }
  Stop-Setup "The database did not accept connections within $Seconds seconds." "Its log is in $Logs\database."
}

function Wait-Health {
  <# /health on the loopback address, whatever the service binds to. #>
  param([int]$Seconds = 90)
  $uri = "http://127.0.0.1:$ApiPort/health"
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
      if ($response.StatusCode -eq 200) { return $true }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

function Set-DesktopServerUrl {
  <#
    Write server_url into the client's branding.json, the machine-wide file
    the desktop reads beside its executable. By regular expression rather than
    ConvertTo-Json, which would reformat the file and, in Windows PowerShell
    5.1, cannot write UTF-8 without a byte-order mark -- and a BOM makes the
    client's JSON parser reject the file and fall back to its defaults.
  #>
  param([string]$Url)
  $path = Join-Path $InstallDir 'config\branding.json'
  if (-not (Test-Path -LiteralPath $path)) {
    Write-Log "  warning: no $path -- the client will ask for the server address"
    return
  }
  $text = [System.IO.File]::ReadAllText($path)
  $escaped = $Url.Replace('\', '\\').Replace('"', '\"')
  if ($text -match '"server_url"\s*:') {
    $text = [regex]::Replace($text, '"server_url"\s*:\s*"[^"]*"', ('"server_url": "' + $escaped + '"'))
  } else {
    $opening = [regex]'^\s*\{'
    $text = $opening.Replace($text, ("{`r`n  `"server_url`": `"$escaped`","), 1)
  }
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
  Write-Log "  the desktop client points at $Url"
}

function Get-PrivateSubnets {
  <#
    The private IPv4 networks this PC is on, as CIDR, for pg_hba.conf. Only
    RFC 1918 ranges: a public address is never let in, whatever the box said.
  #>
  $subnets = @()
  foreach ($address in Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue) {
    $ip = $address.IPAddress
    $prefix = [int]$address.PrefixLength
    if ($ip -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)') { continue }
    if ($prefix -lt 8 -or $prefix -gt 32) { continue }
    $bytes = ([System.Net.IPAddress]::Parse($ip)).GetAddressBytes()
    [Array]::Reverse($bytes)
    $value = [BitConverter]::ToUInt32($bytes, 0)
    $mask = [uint32]([math]::Pow(2, 32) - [math]::Pow(2, 32 - $prefix))
    $network = [BitConverter]::GetBytes([uint32]($value -band $mask))
    [Array]::Reverse($network)
    $subnets += ('{0}/{1}' -f ([System.Net.IPAddress]::new($network)).ToString(), $prefix)
  }
  return $subnets | Select-Object -Unique
}

# -- The private PostgreSQL ---------------------------------------------------

function Initialize-Cluster {
  param([string]$SuperuserPassword)
  $initdb = Join-Path $PgBin 'initdb.exe'
  if (-not (Test-Path -LiteralPath $initdb)) { Stop-Setup "The database program is missing: $initdb" }

  # The superuser password reaches initdb in a file, never on the command
  # line, and that file is deleted as soon as initdb has read it.
  $pwDir = Join-Path $env:TEMP ("agency-initdb-" + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force -Path $pwDir | Out-Null
  $pwFile = Join-Path $pwDir 'pwfile'
  try {
    [System.IO.File]::WriteAllText($pwFile, $SuperuserPassword, (New-Object System.Text.UTF8Encoding($false)))
    Write-Log "  initdb into $PgData"
    $code = Invoke-Native -File $initdb -Arguments @(
      '-D', $PgData, '-U', 'postgres', "--pwfile=$pwFile", '-E', 'UTF8',
      '--no-locale', '-A', 'scram-sha-256')
    if ($code -ne 0) { Stop-Setup 'initdb could not create the database cluster.' 'The output above says why.' }
  } finally {
    Remove-Item -LiteralPath $pwDir -Recurse -Force -ErrorAction SilentlyContinue
  }

  $logDir = (Join-Path $Logs 'database').Replace('\', '/')
  $listen = if ($AllowLan) { '*' } else { 'localhost' }
  $settings = @(
    '',
    '# -- Agency Platform (written by Setup) --',
    "port = $DbPort",
    "listen_addresses = '$listen'",
    'logging_collector = on',
    "log_directory = '$logDir'",
    "log_filename = 'postgresql-%Y-%m-%d.log'",
    'log_rotation_age = 1d',
    'log_rotation_size = 0',
    'log_truncate_on_rotation = off'
  )
  Add-Content -LiteralPath (Join-Path $PgData 'postgresql.conf') -Value $settings -Encoding ASCII

  if ($AllowLan) {
    $subnets = @(Get-PrivateSubnets)
    $hba = @('', '# -- Agency Platform: this PC''s private network(s) (written by Setup) --')
    foreach ($subnet in $subnets) { $hba += "host    all    all    $subnet    scram-sha-256" }
    Add-Content -LiteralPath (Join-Path $PgData 'pg_hba.conf') -Value $hba -Encoding ASCII
    Write-Log ("  database accepts this PC's private network: {0}" -f $(if ($subnets) { $subnets -join ', ' } else { 'none found' }))
  }

  # The service runs as NetworkService, which must own its data and its logs.
  Grant-Access -Path $PgData -Account $SidNetworkService -Rights '(OI)(CI)M'
  Grant-Access -Path (Join-Path $Logs 'database') -Account $SidNetworkService -Rights '(OI)(CI)M'
}

function Register-DatabaseService {
  if (Get-ServiceOrNull $DbService) { return }
  $pgCtl = Join-Path $PgBin 'pg_ctl.exe'
  Write-Log "  registering the $DbService service"
  $code = Invoke-Native -File $pgCtl -Arguments @(
    'register', '-N', $DbService, '-U', 'NT AUTHORITY\NetworkService',
    '-D', $PgData, '-S', 'auto', '-w')
  if ($code -ne 0) { Stop-Setup "Could not register the $DbService service." }
  # pg_ctl names the service and its display name alike; the name people see
  # in services.msc should say what it is.
  Invoke-Native -File 'sc.exe' -Quiet -Arguments @('config', $DbService, 'DisplayName=', $DbDisplayName) | Out-Null
  Invoke-Native -File 'sc.exe' -Quiet -Arguments @('description', $DbService,
    'The database the Agency Platform Server keeps its data in.') | Out-Null
  Invoke-Native -File 'sc.exe' -Quiet -Arguments @('failure', $DbService, 'reset=', '3600',
    'actions=', 'restart/10000/restart/30000/restart/60000') | Out-Null
}

# -- Ports (D-SETUP-9) --------------------------------------------------------

function Get-PortOwner {
  <# The process listening on a TCP port, or $null when nothing is. #>
  param([int]$Port)
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $listener) { return $null }
  return Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
}

function Test-PortFree {
  <# Whether nothing listens on the port, on any address. #>
  param([int]$Port)
  $socket = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
  try {
    $socket.Start()
    return $true
  } catch {
    return $false
  } finally {
    try { $socket.Stop() } catch { }
  }
}

function Get-PortOwnerText {
  <# "program.exe (process 1234)", for a message naming what holds a port. #>
  param([int]$Port)
  $owner = Get-PortOwner $Port
  if (-not $owner) { return 'another program' }
  return "$($owner.ProcessName).exe (process $($owner.Id))"
}

function Test-OursOnPort {
  <# Whether the process on the port is this install's server or database. #>
  param([int]$Port)
  $owner = Get-PortOwner $Port
  if (-not $owner) { return $false }
  try { $path = $owner.Path } catch { $path = $null }
  if (-not $path) { return $false }
  return $path.StartsWith($InstallDir, [System.StringComparison]::OrdinalIgnoreCase)
}

function Read-Ports {
  <# What an earlier install chose, or an empty object. #>
  if (-not (Test-Path -LiteralPath $PortsFile)) { return [pscustomobject]@{} }
  try {
    return Get-Content -LiteralPath $PortsFile -Raw | ConvertFrom-Json
  } catch {
    return [pscustomobject]@{}
  }
}

function Save-Ports {
  param([int]$Database, [int]$Server)
  $json = [pscustomobject]@{ database = $Database; server = $Server } | ConvertTo-Json
  [System.IO.File]::WriteAllText($PortsFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-ClusterPort {
  <# The port the private database was set up on, read from its own config. #>
  $conf = Join-Path $PgData 'postgresql.conf'
  if (-not (Test-Path -LiteralPath $conf)) { return $null }
  $port = $null
  foreach ($line in Get-Content -LiteralPath $conf) {
    if ($line -match '^\s*port\s*=\s*(\d+)') { $port = [int]$Matches[1] }
  }
  return $port
}

function Select-DbPort {
  <# The first port of the range nothing is listening on. #>
  foreach ($port in $DbPortRange) {
    if (Test-PortFree $port) { return $port }
    Write-Log "  port $port is in use by $(Get-PortOwnerText $port); trying the next"
  }
  Stop-Setup ("Every port from {0} to {1} is in use, so the database has nowhere to listen." -f
    $DbPortRange[0], $DbPortRange[-1]) 'Stop one of the programs using them and run Setup again.'
}

function Resolve-ApiPort {
  <# -ApiPort when given, else what an earlier install used, else 8000. #>
  if ($ApiPort -gt 0) { return $ApiPort }
  $remembered = (Read-Ports).server
  if ($remembered) { return [int]$remembered }
  if (Test-Path -LiteralPath $WinSwXml) {
    $xml = Get-Content -LiteralPath $WinSwXml -Raw
    if ($xml -match '--port\s+(\d+)') { return [int]$Matches[1] }
  }
  return $DefaultApiPort
}

function Assert-ApiPortFree {
  <# Refuse a server port another program holds, naming it. #>
  param([int]$Port)
  if ($Port -lt 1024 -or $Port -gt 65535) {
    Stop-Setup "Port $Port cannot be used for the server." 'Choose a port from 1024 to 65535.'
  }
  if ((Test-PortFree $Port) -or (Test-OursOnPort $Port)) { return }
  Stop-Setup "Port $Port, which the server listens on, is in use by $(Get-PortOwnerText $Port)." `
    'Run Setup again and choose another port on the Ports page, or stop that program.'
}

function Invoke-CheckPort {
  $port = if ($ApiPort -gt 0) { $ApiPort } else { $DefaultApiPort }
  if ($port -lt 1024 -or $port -gt 65535) {
    Write-Host "Port $port cannot be used: choose one from 1024 to 65535."
    exit 3
  }
  if ((Test-PortFree $port) -or (Test-OursOnPort $port)) { exit 0 }
  Write-Host "Port $port is in use by $(Get-PortOwnerText $port)."
  exit 3
}

# -- The server service -------------------------------------------------------

function Write-ServiceDefinition {
  param([string]$BindHost, [bool]$DependsOnDatabase)
  $exe = [System.Security.SecurityElement]::Escape($AgencyServer)
  $work = [System.Security.SecurityElement]::Escape($Backend)
  $logPath = [System.Security.SecurityElement]::Escape((Join-Path $Logs 'service'))
  $depend = if ($DependsOnDatabase) { "  <depend>$DbService</depend>" } else { '' }
  # Where "Back up now" writes and where the backups screen looks, and the
  # pg_dump it uses: the private PostgreSQL's when there is one, else the
  # server finds one itself (app/core/tenancy/backup.py).
  $backupDir = [System.Security.SecurityElement]::Escape((Join-Path $DataRoot 'backups'))
  $environment = "  <env name=`"AGENCY_BACKUP_DIRECTORY`" value=`"$backupDir`"/>"
  if (Test-Path -LiteralPath (Join-Path $PgBin 'pg_dump.exe')) {
    $pgBinXml = [System.Security.SecurityElement]::Escape($PgBin)
    $environment += "`r`n  <env name=`"AGENCY_BACKUP_PG_BIN`" value=`"$pgBinXml`"/>"
  }
  $xml = @"
<!-- Written by Setup. The service definition WinSW reads each time it starts. -->
<service>
  <id>$ServerService</id>
  <name>$ServerDisplayName</name>
  <description>The Agency Platform HTTP API. The desktop client connects to it.</description>
  <executable>$exe</executable>
  <arguments>serve --host $BindHost --port $ApiPort</arguments>
  <workingdirectory>$work</workingdirectory>
$environment
  <startmode>Automatic</startmode>
$depend
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <onfailure action="restart" delay="60 sec"/>
  <resetfailure>1 hour</resetfailure>
  <stoptimeout>30 sec</stoptimeout>
  <logpath>$logPath</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
</service>
"@
  [System.IO.File]::WriteAllText($WinSwXml, $xml, (New-Object System.Text.UTF8Encoding($false)))
}

function Register-ServerService {
  param([bool]$DependsOnDatabase)
  if (-not (Test-Path -LiteralPath $WinSw)) { Stop-Setup "The service wrapper is missing: $WinSw" }
  if (-not (Get-ServiceOrNull $ServerService)) {
    Write-Log "  registering the $ServerService service"
    $code = Invoke-Native -File $WinSw -Arguments @('install')
    if ($code -ne 0) { Stop-Setup "Could not register the $ServerService service." }
  }
  # The virtual account, the failure actions and the dependency are set with
  # sc.exe every time, so an upgrade corrects a service an earlier version
  # registered differently rather than trusting it.
  $code = Invoke-Native -File 'sc.exe' -Arguments @('config', $ServerService, 'obj=', $ServiceAccount, 'start=', 'auto')
  if ($code -ne 0) { Stop-Setup "Could not set $ServerService to run as $ServiceAccount." }
  $depend = if ($DependsOnDatabase) { $DbService } else { '/' }
  Invoke-Native -File 'sc.exe' -Quiet -Arguments @('config', $ServerService, 'depend=', $depend) | Out-Null
  Invoke-Native -File 'sc.exe' -Quiet -Arguments @('failure', $ServerService, 'reset=', '3600',
    'actions=', 'restart/10000/restart/30000/restart/60000') | Out-Null

  # What the virtual account may touch: its logs, the attachments, and --
  # read only -- its configuration. Program Files is readable by every account.
  Grant-Access -Path $Logs -Account $ServiceAccount -Rights '(OI)(CI)M'
  Grant-Access -Path (Join-Path $DataRoot 'storage') -Account $ServiceAccount -Rights '(OI)(CI)M'
  Grant-Access -Path $EnvPath -Account $ServiceAccount -Rights 'R'
  # Backups: read every kind, so the backups screen can list them, and write
  # only backups\manual, where "Back up now" puts its own.
  $manual = Join-Path $DataRoot 'backups\manual'
  New-Item -ItemType Directory -Force -Path $manual | Out-Null
  Grant-Access -Path (Join-Path $DataRoot 'backups') -Account $ServiceAccount -Rights '(OI)(CI)RX'
  Grant-Access -Path $manual -Account $ServiceAccount -Rights '(OI)(CI)M'
}

function Set-Firewall {
  foreach ($name in @($FirewallRule, $LegacyFirewallRule)) {
    if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) {
      Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
    }
  }
  if (-not $AllowLan) { return }
  New-NetFirewallRule -Name $FirewallRule -DisplayName "$ServerDisplayName (TCP $ApiPort)" `
    -Description 'Lets other PCs on this private network reach the Agency Platform Server.' `
    -Direction Inbound -Protocol TCP -LocalPort $ApiPort -Profile Private -Action Allow | Out-Null
  Write-Log "  firewall: inbound TCP $ApiPort allowed on private networks"
}

# -- Actions ------------------------------------------------------------------

function Get-BackupPlan {
  <#
    Everything a dump needs: where the database is, as whom, which stores, and
    which pg_dump. Every store comes from the registry, by the installed
    program's own dry run -- the same enumeration migrate-all will upgrade.
  #>
  $envValues = Read-EnvFile
  $plan = [pscustomobject]@{
    Host     = if ($envValues['AGENCY_DATABASE_HOST']) { $envValues['AGENCY_DATABASE_HOST'] } else { 'localhost' }
    Port     = if ($envValues['AGENCY_DATABASE_PORT']) { $envValues['AGENCY_DATABASE_PORT'] } else { '5432' }
    User     = $envValues['AGENCY_DATABASE_USERNAME']
    Password = $envValues['AGENCY_DATABASE_PASSWORD']
    Targets  = @()
    PgDump   = $null
  }
  $defaultDatabase = $envValues['AGENCY_DATABASE_NAME']

  $targets = @()
  if (Test-Path -LiteralPath $AgencyServer) {
    $code = Invoke-Native -File $AgencyServer -Arguments @('migrate-all', '--dry-run') -WorkingDirectory $Backend
    if ($code -ne 0) { Stop-Setup 'Could not list the stores to back up.' 'The output above says why. Nothing was changed.' }
    foreach ($line in $script:NativeOutput) {
      if ($line -match '^\s+.+\((?<db>[^/()]+)/(?<schema>[^\s/()]+)(?: on (?<where>[^)]+))?\): at ') {
        $where = $Matches['where']
        if ($where -and $where -ne 'platform server') {
          Write-Log "  skipped $($Matches['db'])/$($Matches['schema']): it lives on '$where', not on this PC"
          continue
        }
        $targets += [pscustomobject]@{ Database = $Matches['db']; Schema = $Matches['schema'] }
      }
    }
  }
  if ($targets.Count -eq 0) {
    # A copy staged from source has no agency-server.exe to ask. Dump the
    # configured database whole, which is a superset of every schema in it.
    if (-not $defaultDatabase) { Stop-Setup 'config\.env names no database, so there is nothing to back up.' }
    $targets += [pscustomobject]@{ Database = $defaultDatabase; Schema = $null }
  }
  $plan.Targets = $targets

  $pgDump = Join-Path $PgBin 'pg_dump.exe'
  if (-not (Test-Path -LiteralPath $pgDump)) {
    # An install from before the private database kept its data in a
    # PostgreSQL the customer installed; its pg_dump is the one to use.
    $found = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $found) { Stop-Setup 'No pg_dump was found to take the backup.' 'Install the PostgreSQL client tools, or back up by hand.' }
    $pgDump = $found.FullName
  }
  $plan.PgDump = $pgDump
  return $plan
}

function Write-StoreDumps {
  <# One custom-format dump per store into $Folder; stops on the first failure. #>
  param($Plan, [string]$Folder, [string]$FailureFix)
  New-Item -ItemType Directory -Force -Path $Folder | Out-Null
  Protect-AdminOnly $Folder
  # Read-only for the server, so its backups screen can show this folder.
  # Not fatal: before the first install the account does not exist yet.
  Invoke-Native -File 'icacls.exe' -Quiet -Arguments @($Folder, '/grant', "${ServiceAccount}:(OI)(CI)RX") | Out-Null
  $env:PGPASSWORD = $Plan.Password
  try {
    foreach ($target in $Plan.Targets) {
      $name = if ($target.Schema) { "$($target.Database)--$($target.Schema).dump" } else { "$($target.Database).dump" }
      $file = Join-Path $Folder $name
      $arguments = @('-h', $Plan.Host, '-p', $Plan.Port, '-U', $Plan.User, '-d', $target.Database,
        '-Fc', '--no-password', '-f', $file)
      # -n takes a pattern and folds an unquoted one to lower case, so
      # -n SNTEST01 matched nothing and wrote an empty file. Quoted, it
      # matches exactly; \" is how Windows PowerShell 5.1 hands a native
      # program a literal double quote.
      if ($target.Schema) { $arguments += @('-n', ('\"' + $target.Schema.Replace('"', '""') + '\"')) }
      Write-Log "  pg_dump $($target.Database)/$(if ($target.Schema) { $target.Schema } else { '*' })"
      $code = Invoke-Native -File $Plan.PgDump -Arguments $arguments
      if ($code -ne 0 -or -not (Test-Path -LiteralPath $file) -or (Get-Item -LiteralPath $file).Length -eq 0) {
        Stop-Setup "The backup of $($target.Database) failed." $FailureFix
      }
    }
  } finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
  }
}

function Invoke-Backup {
  if (-not (Test-Path -LiteralPath $EnvPath)) {
    Write-Log 'No config\.env: nothing is installed to back up.'
    return
  }
  Write-Log "Backing up before the upgrade from $PreviousVersion"
  Stop-ServiceAndWait $ServerService
  if (Get-ServiceOrNull $DbService) {
    Start-ServiceAndWait $DbService
    Wait-Database
  }

  $plan = Get-BackupPlan
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $folder = Join-Path $DataRoot "backups\pre-upgrade-$PreviousVersion-$stamp"
  Write-StoreDumps -Plan $plan -Folder $folder `
    -FailureFix "The upgrade was not started and nothing was changed. The partial backup is in $folder."
  Write-Log "Backup written to $folder"

  # The binaries under {app}\pgsql are about to be replaced, and a running
  # postgres.exe holds them open.
  Stop-ServiceAndWait $DbService
}

function Invoke-DailyBackup {
  <#
    The scheduled backup (D-QA-4). Before it, backups\ filled only when Setup
    ran an upgrade, so a firm that never upgraded had no backup at all.
    pg_dump reads a consistent snapshot of a running database, so nothing is
    stopped: people keep working through it. Keeps the newest $KeepDaily.
  #>
  $script:StopWord = 'Backup failed'
  if (-not (Test-Path -LiteralPath $EnvPath)) { Stop-Setup 'No config\.env: nothing is installed to back up.' }
  $daily = Join-Path $DataRoot 'backups\daily'
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $folder = Join-Path $daily $stamp
  Write-Log "Daily backup into $folder"
  # A run that failed left a folder with no .complete marker. It is not a
  # backup: retention ignores it, and the next run clears it away here.
  if (Test-Path -LiteralPath $daily) {
    Get-ChildItem -LiteralPath $daily -Directory |
      Where-Object { -not (Test-Path -LiteralPath (Join-Path $_.FullName '.complete')) } |
      ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "  removed the unfinished backup $($_.Name)"
      }
  }
  $plan = Get-BackupPlan
  Write-StoreDumps -Plan $plan -Folder $folder -FailureFix 'The earlier daily backups are kept. See this log.'
  [System.IO.File]::WriteAllText((Join-Path $folder '.complete'), "$stamp`r`n")
  Write-Log "Backup written to $folder"

  $complete = @(Get-ChildItem -LiteralPath $daily -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '.complete') } |
    Sort-Object Name -Descending)
  foreach ($old in ($complete | Select-Object -Skip $KeepDaily)) {
    Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
    Write-Log "  removed the old backup $($old.Name)"
  }
}

function Register-DailyBackup {
  <#
    A Windows scheduled task, as SYSTEM, every day at 02:00 -- and as soon as
    the PC is next on if it was off then. Registered again on every install,
    upgrade and repair, so an existing install gains it and a moved install
    points at the right script.
  #>
  $scriptPath = Join-Path $InstallDir 'packaging\server_setup.ps1'
  if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Log "  warning: $scriptPath is missing, so no daily backup is scheduled"
    return
  }
  $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Action DailyBackup " +
    "-InstallDir `"$InstallDir`" -DataRoot `"$DataRoot`""
  try {
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -Daily -At '02:00'
    $principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $BackupTask -Action $action -Trigger $trigger -Principal $principal `
      -Settings $settings -Force `
      -Description "Backs up every Agency Platform database to $DataRoot\backups\daily, keeping the last $KeepDaily." |
      Out-Null
    Write-Log "Daily backup scheduled at 02:00 into $DataRoot\backups\daily (keeps $KeepDaily)"
  } catch {
    # The product works without it; say so loudly rather than fail the install.
    Write-Log "  warning: the daily backup could not be scheduled: $($_.Exception.Message)"
  }
}

function Invoke-Server {
  foreach ($dir in @($DataRoot, $Logs, (Join-Path $Logs 'install'), (Join-Path $Logs 'server'),
      (Join-Path $Logs 'service'), (Join-Path $Logs 'database'), (Join-Path $Logs 'client'),
      (Join-Path $DataRoot 'storage'), (Join-Path $DataRoot 'backups'))) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  Protect-DataRoot

  $envExists = Test-Path -LiteralPath $EnvPath
  $hasCluster = Test-Path -LiteralPath (Join-Path $PgData 'PG_VERSION')
  $ready = Test-Path -LiteralPath $ReadyMarker
  $superuserPassword = $null
  $privateDatabase = $true
  $script:ApiPort = Resolve-ApiPort
  if ($hasCluster) {
    $clusterPort = Get-ClusterPort
    if ($clusterPort) { $script:DbPort = $clusterPort }
  }

  if ($hasCluster -and (Test-Path -LiteralPath $SuperuserFile)) {
    # A previous run created the cluster and stopped before configuring it.
    $superuserPassword = (Get-Content -LiteralPath $SuperuserFile -Raw).Trim()
  }

  if (-not $hasCluster -and -not $envExists) {
    Write-Log 'Database: creating the private PostgreSQL'
    $superuserPassword = New-Secret
    # Kept, admin-only, until configuration succeeds, so that running Setup
    # again after a failure can finish the job. Deleted at the end.
    [System.IO.File]::WriteAllText($SuperuserFile, $superuserPassword, (New-Object System.Text.UTF8Encoding($false)))
    Protect-AdminOnly $SuperuserFile
    $script:DbPort = Select-DbPort
    Write-Log "  the database will listen on port $DbPort"
    Initialize-Cluster -SuperuserPassword $superuserPassword
  } elseif (-not $hasCluster -and $envExists) {
    $envValues = Read-EnvFile
    # Setup's own database, by where .env points -- any port of the range.
    if ($envValues['AGENCY_DATABASE_HOST'] -eq 'localhost' -and
        $DbPortRange -contains [int]("0" + $envValues['AGENCY_DATABASE_PORT'])) {
      Stop-Setup "config\.env points at the private database, but $PgData holds none." 'Restore the pgdata folder from a backup, or uninstall with "delete all data" and install again.'
    }
    # An install from before the private database: its data is in a
    # PostgreSQL the customer runs. Leave it there.
    Write-Log "Database: using the existing server named in config\.env ($($envValues['AGENCY_DATABASE_HOST']):$($envValues['AGENCY_DATABASE_PORT']))"
    $privateDatabase = $false
  } elseif ($hasCluster -and -not $envExists -and -not $superuserPassword) {
    Stop-Setup "$PgData holds a database from an earlier installation, but its configuration is gone." 'Restore backend\config\.env from a backup, or move the pgdata folder aside and run Setup again.'
  } else {
    Write-Log 'Database: the private PostgreSQL is already there -- initdb skipped, no password changed'
  }

  if ($privateDatabase) {
    Register-DatabaseService
    $dbService = Get-ServiceOrNull $DbService
    if ((-not $dbService -or $dbService.Status -ne 'Running') -and -not (Test-PortFree $DbPort) -and
        -not (Test-OursOnPort $DbPort)) {
      Stop-Setup "Port $DbPort, which the Agency Platform database listens on, is in use by $(Get-PortOwnerText $DbPort)." 'Stop that program and run Setup again.'
    }
    Start-ServiceAndWait $DbService
    Wait-Database
  }

  # -- Configure: install.ps1, the one implementation of it -------------------
  Write-Log 'Configuring (install.ps1 -ConfigureOnly)'
  $installScript = Join-Path $InstallDir 'packaging\install.ps1'
  $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $installScript,
    '-InstallDir', $InstallDir, '-ConfigureOnly', '-SkipStart')
  if (-not $envExists) {
    $arguments += @('-DatabaseHost', 'localhost', '-DatabasePort', "$DbPort", '-LogDirectory', $Logs)
  }
  if (-not $ready) { $arguments += '-RequireNoFirms' }
  if ($superuserPassword) {
    $env:INSTALL_ADMIN_USER = 'postgres'
    $env:INSTALL_ADMIN_PASSWORD = $superuserPassword
  }
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $output = @(& powershell.exe @arguments 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previous
    Remove-Item Env:\INSTALL_ADMIN_USER -ErrorAction SilentlyContinue
    Remove-Item Env:\INSTALL_ADMIN_PASSWORD -ErrorAction SilentlyContinue
  }
  $adminPassword = $null
  foreach ($line in $output) {
    $trimmed = $line.Trim()
    if ($trimmed -match '^Password:\s+(\S+)$') {
      $adminPassword = $Matches[1]
      Write-Log '    Password:   (shown on the finished page and in first-login.txt, not logged)'
      continue
    }
    Write-Log "    $line"
  }
  if ($code -ne 0) {
    # install.ps1 has already said "Install stopped: ..." above.
    exit 1
  }
  if (-not $adminPassword -and -not $ready) {
    # An earlier run wrote config\.env and stopped before the server answered
    # (the ready marker is only written after /health does). install.ps1 keeps
    # an existing .env and so prints no password, and the finished page would
    # say "sign in as before" to somebody who has never signed in. Nobody can
    # have changed the bootstrap password without a running server, so the one
    # in the file is still the one that works: show it again.
    $adminPassword = (Read-EnvFile)['AGENCY_BOOTSTRAP_ADMIN_PASSWORD']
    if ($adminPassword) {
      Write-Log '    Password:   (the earlier run never finished; shown again from config\.env, not logged)'
    }
  }

  # -- The server as a service --------------------------------------------------
  $bindHost = if ($AllowLan) { '0.0.0.0' } else { '127.0.0.1' }
  Write-Log "Service: $ServerService on ${bindHost}:$ApiPort as $ServiceAccount"
  Stop-ServiceAndWait $ServerService
  Assert-ApiPortFree $ApiPort
  Write-ServiceDefinition -BindHost $bindHost -DependsOnDatabase $privateDatabase
  Register-ServerService -DependsOnDatabase $privateDatabase
  Set-Firewall
  Start-ServiceAndWait $ServerService

  Write-Log "Waiting for http://127.0.0.1:$ApiPort/health (up to 90 s)"
  if (-not (Wait-Health -Seconds 90)) {
    Stop-Setup 'The server did not answer /health within 90 seconds.' "Its logs are in $Logs\server and $Logs\service."
  }
  Write-Log 'The server is answering.'

  [System.IO.File]::WriteAllText($ReadyMarker, "Database set up by Setup.`r`n")
  Register-DailyBackup
  Remove-Item -LiteralPath $SuperuserFile -Force -ErrorAction SilentlyContinue
  Save-Ports -Database $DbPort -Server $ApiPort
  Set-DesktopServerUrl -Url "http://127.0.0.1:$ApiPort"

  if ($adminPassword) {
    $text = @(
      'Agency Platform -- first sign-in',
      '',
      "Sign in as: $AdminAccount",
      "Password:   $adminPassword",
      '',
      'The password must be changed at the first sign-in. Delete this file once you have.'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($FirstLogin, $text + "`r`n")
    Protect-AdminOnly $FirstLogin
    Write-Log "First sign-in saved to $FirstLogin (Administrators and SYSTEM only)"
    # For the .iss only: stdout, never the log file.
    Write-Host "admin-user:$AdminAccount"
    Write-Host "admin-password:$adminPassword"
  }
}

function Invoke-Uninstall {
  Write-Log 'Removing the services'
  Stop-ServiceAndWait $ServerService
  if (Get-ServiceOrNull $ServerService) {
    if (Test-Path -LiteralPath $WinSw) { Invoke-Native -File $WinSw -Arguments @('uninstall') | Out-Null }
    if (Get-ServiceOrNull $ServerService) { Invoke-Native -File 'sc.exe' -Arguments @('delete', $ServerService) | Out-Null }
  }
  Stop-ServiceAndWait $DbService
  if (Get-ServiceOrNull $DbService) {
    $pgCtl = Join-Path $PgBin 'pg_ctl.exe'
    if (Test-Path -LiteralPath $pgCtl) { Invoke-Native -File $pgCtl -Arguments @('unregister', '-N', $DbService) | Out-Null }
    if (Get-ServiceOrNull $DbService) { Invoke-Native -File 'sc.exe' -Arguments @('delete', $DbService) | Out-Null }
  }
  foreach ($name in @($FirewallRule, $LegacyFirewallRule)) {
    Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
  }
  Unregister-ScheduledTask -TaskName $BackupTask -Confirm:$false -ErrorAction SilentlyContinue
  if ($DeleteData) {
    Write-Log "Deleting all data under $DataRoot"
    Remove-Item -LiteralPath $DataRoot -Recurse -Force -ErrorAction SilentlyContinue
    # The configuration names a database that no longer exists; keeping it
    # would make the next install read as an upgrade of nothing.
    foreach ($file in @($EnvPath, $ReadyMarker)) {
      Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
    }
  }
}

switch ($Action) {
  'Backup' { Invoke-Backup }
  'DailyBackup' {
    if (-not $LogFile) {
      $backupLogs = Join-Path $Logs 'backup'
      New-Item -ItemType Directory -Force -Path $backupLogs | Out-Null
      $LogFile = Join-Path $backupLogs ("daily-{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
    }
    Invoke-DailyBackup
  }
  'Server' { Invoke-Server }
  'Client' {
    if (-not $ServerUrl) { Stop-Setup 'No server address was given.' }
    Set-DesktopServerUrl -Url $ServerUrl
  }
  'Uninstall' { Invoke-Uninstall }
  'CheckPort' { Invoke-CheckPort }
}
exit 0
