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
               <DataRoot>\pgdata with a generated superuser password, port 5433,
               register AgencyPlatformDB, configure, create the
               AgencyPlatformServer service, open the firewall if asked, wait
               for /health. On an upgrade: none of initdb, no new password --
               start the database, migrate every store, start the service,
               wait for /health.

    Client     Point the desktop client at a server: writes server_url into
               {app}\config\branding.json.

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
  [ValidateSet('Backup', 'Server', 'Client', 'Uninstall')]
  [string]$Action,
  [Parameter(Mandatory = $true)][string]$InstallDir,
  [string]$DataRoot = (Join-Path $env:ProgramData 'Agency Platform'),
  [string]$LogFile,
  [string]$PreviousVersion = 'unknown',
  [switch]$AllowLan,
  [string]$ServerUrl,
  [switch]$DeleteData
)

$ErrorActionPreference = 'Stop'

$DbService = 'AgencyPlatformDB'
$DbDisplayName = 'Agency Platform Database'
$ServerService = 'AgencyPlatformServer'
$ServerDisplayName = 'Agency Platform Server'
$DbPort = 5433
$ApiPort = 8000
$FirewallRule = 'AgencyPlatformServer-TCP-8000'
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

function Stop-Setup {
  <# The .iss shows everything from "Install stopped:" to the end. #>
  param([string]$Problem, [string]$Fix)
  Write-Log "Install stopped: $Problem"
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

# -- The server service -------------------------------------------------------

function Write-ServiceDefinition {
  param([string]$BindHost, [bool]$DependsOnDatabase)
  $exe = [System.Security.SecurityElement]::Escape($AgencyServer)
  $work = [System.Security.SecurityElement]::Escape($Backend)
  $logPath = [System.Security.SecurityElement]::Escape((Join-Path $Logs 'service'))
  $depend = if ($DependsOnDatabase) { "  <depend>$DbService</depend>" } else { '' }
  $xml = @"
<!-- Written by Setup. The service definition WinSW reads each time it starts. -->
<service>
  <id>$ServerService</id>
  <name>$ServerDisplayName</name>
  <description>The Agency Platform HTTP API. The desktop client connects to it.</description>
  <executable>$exe</executable>
  <arguments>serve --host $BindHost --port $ApiPort</arguments>
  <workingdirectory>$work</workingdirectory>
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
}

function Set-Firewall {
  $existing = Get-NetFirewallRule -Name $FirewallRule -ErrorAction SilentlyContinue
  if ($existing) { Remove-NetFirewallRule -Name $FirewallRule -ErrorAction SilentlyContinue }
  if (-not $AllowLan) { return }
  New-NetFirewallRule -Name $FirewallRule -DisplayName "$ServerDisplayName (TCP $ApiPort)" `
    -Description 'Lets other PCs on this private network reach the Agency Platform Server.' `
    -Direction Inbound -Protocol TCP -LocalPort $ApiPort -Profile Private -Action Allow | Out-Null
  Write-Log "  firewall: inbound TCP $ApiPort allowed on private networks"
}

# -- Actions ------------------------------------------------------------------

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

  $envValues = Read-EnvFile
  $dbHost = if ($envValues['AGENCY_DATABASE_HOST']) { $envValues['AGENCY_DATABASE_HOST'] } else { 'localhost' }
  $dbPortValue = if ($envValues['AGENCY_DATABASE_PORT']) { $envValues['AGENCY_DATABASE_PORT'] } else { '5432' }
  $user = $envValues['AGENCY_DATABASE_USERNAME']
  $defaultDatabase = $envValues['AGENCY_DATABASE_NAME']

  # Every store this server uses, from the registry, by the installed
  # program's own dry run -- the same enumeration migrate-all will upgrade.
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

  $pgDump = Join-Path $PgBin 'pg_dump.exe'
  if (-not (Test-Path -LiteralPath $pgDump)) {
    # An install from before the private database kept its data in a
    # PostgreSQL the customer installed; its pg_dump is the one to use.
    $found = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $found) { Stop-Setup 'No pg_dump was found to take the pre-upgrade backup.' 'Install the PostgreSQL client tools, or back up by hand, then run Setup again.' }
    $pgDump = $found.FullName
  }

  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $folder = Join-Path $DataRoot "backups\pre-upgrade-$PreviousVersion-$stamp"
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  Protect-AdminOnly $folder

  $env:PGPASSWORD = $envValues['AGENCY_DATABASE_PASSWORD']
  try {
    foreach ($target in $targets) {
      $name = if ($target.Schema) { "$($target.Database)--$($target.Schema).dump" } else { "$($target.Database).dump" }
      $file = Join-Path $folder $name
      $arguments = @('-h', $dbHost, '-p', $dbPortValue, '-U', $user, '-d', $target.Database,
        '-Fc', '--no-password', '-f', $file)
      if ($target.Schema) { $arguments += @('-n', $target.Schema) }
      Write-Log "  pg_dump $($target.Database)/$(if ($target.Schema) { $target.Schema } else { '*' })"
      $code = Invoke-Native -File $pgDump -Arguments $arguments
      if ($code -ne 0 -or -not (Test-Path -LiteralPath $file) -or (Get-Item -LiteralPath $file).Length -eq 0) {
        Stop-Setup "The backup of $($target.Database) failed, so the upgrade was not started." "Nothing was changed. The partial backup is in $folder."
      }
    }
  } finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
  }
  Write-Log "Backup written to $folder"

  # The binaries under {app}\pgsql are about to be replaced, and a running
  # postgres.exe holds them open.
  Stop-ServiceAndWait $DbService
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
    Initialize-Cluster -SuperuserPassword $superuserPassword
  } elseif (-not $hasCluster -and $envExists) {
    $envValues = Read-EnvFile
    if ($envValues['AGENCY_DATABASE_PORT'] -eq "$DbPort") {
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
  Remove-Item -LiteralPath $SuperuserFile -Force -ErrorAction SilentlyContinue
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
  Remove-NetFirewallRule -Name $FirewallRule -ErrorAction SilentlyContinue
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
  'Server' { Invoke-Server }
  'Client' {
    if (-not $ServerUrl) { Stop-Setup 'No server address was given.' }
    Set-DesktopServerUrl -Url $ServerUrl
  }
  'Uninstall' { Invoke-Uninstall }
}
exit 0
