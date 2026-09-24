; Inno Setup script for the Agency Platform.
;
; Compiled by packaging\build_installer.ps1, which stages the payload and passes
; the version in. Do not run it by hand against a source tree: it installs a
; *staged* directory, deliberately, so what reaches a customer is only what the
; staging step chose to put there.
;
; The Setup.exe this produces is fully offline and asks one question: is this PC
; the server (with the app), or only the app, connecting to a server elsewhere.
;
; Layout, and the reasoning:
;
;   {app}                        Program Files. Read-only once installed.
;     agency_desktop.exe           the client, with its DLLs and data\ beside it
;     config\branding.json         the client's branding, and server_url: the
;                                  address Setup points it at
;     backend\agency-server.exe    the server, compiled (server role only)
;     backend\alembic\versions\    the migrations, which stay as source because
;                                  Alembic loads them by path at runtime
;     backend\config\.env          written by the configure step, then only read
;     pgsql\                       the private PostgreSQL 17 (server role only)
;     service\                     WinSW, as AgencyPlatformServer.exe, and the
;                                  XML Setup writes beside it (server role only)
;     packaging\install.ps1        the configure step
;     packaging\server_setup.ps1   the machine-level step: database, services,
;                                  firewall, pre-upgrade backup, uninstall
;
;   {commonappdata}\Agency Platform    ProgramData. Writable while running.
;     pgdata\                    the database cluster, owned by NetworkService
;     logs\install\              one file per Setup run, the last ten kept
;     logs\server\ logs\service\ the server and its service wrapper
;     logs\database\             PostgreSQL, postgresql-YYYY-MM-DD.log
;     logs\client\<user>\        the desktop client, per Windows user
;     backups\                   pre-upgrade dumps
;     storage\                   attachments
;     first-login.txt            the generated sign-in; Administrators only
;
; Why config\.env sits under Program Files rather than ProgramData: alembic.ini
; declares `script_location = alembic` and `prepend_sys_path = .`, both relative
; to the working directory, so the server runs with its working directory set to
; {app}\backend and `Settings` reads `config/.env` from there.
;
; This file places files and asks the question. Everything done to the machine
; itself is server_setup.ps1, which calls install.ps1 for the configuration, so
; neither is a second copy of logic that lives somewhere else. Their exit codes
; and output are read here: Inno Setup ignores a [Run] entry's exit code, which
; is how an earlier version said "finished" over a failed configure step.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef PayloadDir
  #define PayloadDir "..\dist\staging"
#endif
#ifndef RedistDir
  #define RedistDir "..\dist\redist"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\windows"
#endif
; The minor version of the Visual C++ runtime vc_redist.x64.exe carries. Setup
; runs it only when the machine has an older runtime or none.
#ifndef VcRuntimeMinor
  #define VcRuntimeMinor "44"
#endif

; ExecAndCaptureOutput, which the machine-level step needs to read what went
; wrong, arrived in Inno Setup 6.3.
#if Ver < EncodeVer(6, 3, 0)
  #error Inno Setup 6.3 or later is required: winget install --id JRSoftware.InnoSetup
#endif

#define AppName "Agency Platform"
#define AppPublisher "Agency"
#define AppExeName "agency_desktop.exe"
#define AppIdGuid "8F3B1C42-6D9E-4A57-9C21-5E7A4B0D3F18"

[Setup]
; Never change this GUID. It is how Windows recognises an upgrade of this
; product rather than a second copy of it; a new one would install alongside the
; old and leave two entries in Add/Remove Programs.
AppId={{{#AppIdGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=AgencyPlatform-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
; 64-bit Windows 10 or 11, nothing older and nothing 32-bit.
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Program Files, services, the firewall and ProgramData ACLs all need it.
PrivilegesRequired=admin
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
DisableProgramGroupPage=yes
; Upgrading should not ask a customer where the product lives. It lives where it
; already lives.
UsePreviousAppDir=yes
; Inno's own log is appended to logs\install\install-<version>-<stamp>.log when
; Setup ends, so one file tells the whole story of a run.
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WinVersionTooLowError=Agency Platform needs 64-bit Windows 10 or Windows 11.
OnlyOnTheseArchitectures=Agency Platform needs 64-bit Windows 10 or Windows 11 on an x64 processor.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Dirs]
Name: "{commonappdata}\{#AppName}"
Name: "{commonappdata}\{#AppName}\logs"
Name: "{commonappdata}\{#AppName}\logs\install"
; Every Windows user's desktop client writes its own subfolder here.
Name: "{commonappdata}\{#AppName}\logs\client"; Permissions: users-modify
Name: "{commonappdata}\{#AppName}\storage"; Check: IsServer

[Files]
; The client and the two scripts, for every role.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; \
  Excludes: "\backend\*,\pgsql\*,\service\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; The server, its database and its service wrapper: the server role only. An
; app-only PC gets no PostgreSQL and no service.
Source: "{#PayloadDir}\backend\*"; DestDir: "{app}\backend"; Check: IsServer; \
  Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\pgsql\*"; DestDir: "{app}\pgsql"; Check: IsServer; \
  Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\service\*"; DestDir: "{app}\service"; Check: IsServer; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; The same script again, extracted to {tmp} before anything is replaced: an
; upgrade's backup has to run the *new* script, because the installed version
; may predate it.
Source: "{#PayloadDir}\packaging\server_setup.ps1"; Flags: dontcopy
; Run from {tmp} when the machine lacks the runtime; never left behind.
Source: "{#RedistDir}\vc_redist.x64.exe"; DestDir: "{tmp}"; \
  Flags: deleteafterinstall; Check: VCRedistNeeded

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\{#AppName} logs"; Filename: "{commonappdata}\{#AppName}\logs"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Ticked by default. The client reads server_url from config\branding.json,
; which the machine-level step has just pointed at this PC's server or the one
; typed in.
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
  WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent; \
  Check: CanStart

[UninstallDelete]
; Written by Setup, so the uninstaller does not know about it on its own.
Type: files; Name: "{app}\service\AgencyPlatformServer.xml"
Type: filesandordirs; Name: "{app}\backend\__pycache__"

[Code]
const
  NL = #13#10;
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#AppIdGuid}}_is1';
  VcRuntimeKey = 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';
  { "4 GB" of RAM reads as a little under 4096 MB once the firmware has taken
    its share, so the floor is set just below it. }
  MinMemoryMB = 3800;
  MinFreeDiskMB = 3072;
  KeepInstallLogs = 10;

type
  TMemoryStatusEx = record
    dwLength: DWORD;
    dwMemoryLoad: DWORD;
    ullTotalPhys: Int64;
    ullAvailPhys: Int64;
    ullTotalPageFile: Int64;
    ullAvailPageFile: Int64;
    ullTotalVirtual: Int64;
    ullAvailVirtual: Int64;
    ullAvailExtendedVirtual: Int64;
  end;

var
  RolePage: TInputOptionWizardPage;
  LanCheck: TNewCheckBox;
  ServerPage: TInputQueryWizardPage;
  InstalledVersion: String;
  InstallLogPath: String;
  ServerReady: Boolean;
  ServerStepRan: Boolean;
  FailureReason: String;
  AdminUser: String;
  AdminPassword: String;
  CredentialsLabel: TNewStaticText;
  UserEdit: TNewEdit;
  PasswordEdit: TNewEdit;
  CopyButton: TNewButton;

function GlobalMemoryStatusEx(var lpBuffer: TMemoryStatusEx): BOOL;
  external 'GlobalMemoryStatusEx@kernel32.dll stdcall';

function SetEnvironmentVariable(lpName: String; lpValue: String): Integer;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ -- The install log ---------------------------------------------------------- }

procedure InstallLog(Text: String);
begin
  Log(Text);
  if InstallLogPath <> '' then
    SaveStringToFile(InstallLogPath,
      GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':') + ' [setup.exe] ' + Text + NL, True);
end;

{ Keep the newest KeepInstallLogs - 1, so this run's makes KeepInstallLogs.
  The names end in yyyymmdd-hhnnss.log, which sorts as time does whatever the
  version in front of it. }
procedure PruneInstallLogs(Dir: String);
var
  Rec: TFindRec;
  Names, Keys: TArrayOfString;
  Count, I, J: Integer;
  Swap: String;
begin
  Count := 0;
  if FindFirst(Dir + '\install-*.log', Rec) then begin
    try
      repeat
        SetArrayLength(Names, Count + 1);
        SetArrayLength(Keys, Count + 1);
        Names[Count] := Rec.Name;
        Keys[Count] := Copy(Rec.Name, Length(Rec.Name) - 18, 19);
        Count := Count + 1;
      until not FindNext(Rec);
    finally
      FindClose(Rec);
    end;
  end;
  for I := 0 to Count - 2 do
    for J := 0 to Count - 2 - I do
      if Keys[J] < Keys[J + 1] then begin
        Swap := Keys[J]; Keys[J] := Keys[J + 1]; Keys[J + 1] := Swap;
        Swap := Names[J]; Names[J] := Names[J + 1]; Names[J + 1] := Swap;
      end;
  for I := KeepInstallLogs - 1 to Count - 1 do
    DeleteFile(Dir + '\' + Names[I]);
end;

procedure StartInstallLog;
var
  Dir: String;
begin
  Dir := ExpandConstant('{commonappdata}\{#AppName}\logs\install');
  if not ForceDirectories(Dir) then Exit;
  PruneInstallLogs(Dir);
  InstallLogPath := Dir + '\install-{#AppVersion}-' +
    GetDateTimeString('yyyymmdd-hhnnss', #0, #0) + '.log';
  InstallLog('Agency Platform Setup {#AppVersion}');
end;

{ -- Checks before anything is shown ------------------------------------------ }

function TotalMemoryMB: Int64;
var
  Status: TMemoryStatusEx;
begin
  Result := 0;
  Status.dwLength := SizeOf(Status);
  if GlobalMemoryStatusEx(Status) then
    Result := Status.ullTotalPhys div (1024 * 1024);
end;

function FreeDiskMB(Path: String): Int64;
var
  Free, Total: Int64;
begin
  Result := -1;
  if GetSpaceOnDisk64(Path, Free, Total) then
    Result := Free div (1024 * 1024);
end;

function NextVersionPart(var S: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', S);
  if P = 0 then begin
    Result := StrToIntDef(S, 0);
    S := '';
  end else begin
    Result := StrToIntDef(Copy(S, 1, P - 1), 0);
    Delete(S, 1, P);
  end;
end;

{ -1, 0 or 1, comparing dotted numbers part by part. }
function CompareVersions(A, B: String): Integer;
var
  I, X, Y: Integer;
begin
  Result := 0;
  for I := 1 to 4 do begin
    X := NextVersionPart(A);
    Y := NextVersionPart(B);
    if X < Y then begin Result := -1; Exit; end;
    if X > Y then begin Result := 1; Exit; end;
  end;
end;

function ReadInstalledVersion: String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', Result) then
    if not RegQueryStringValue(HKLM32, UninstallKey, 'DisplayVersion', Result) then
      Result := '';
end;

function IsUpgrade: Boolean;
begin
  Result := InstalledVersion <> '';
end;

function InitializeSetup: Boolean;
var
  Memory, Disk: Int64;
begin
  Result := True;
  StartInstallLog;

  Memory := TotalMemoryMB;
  InstallLog('Memory: ' + IntToStr(Memory) + ' MB');
  if (Memory > 0) and (Memory < MinMemoryMB) then begin
    InstallLog('Refused: less than 4 GB of memory.');
    SuppressibleMsgBox('{#AppName} needs at least 4 GB of memory. This PC has ' +
      IntToStr(Memory) + ' MB.', mbCriticalError, MB_OK, IDOK);
    Result := False;
    Exit;
  end;

  Disk := FreeDiskMB(ExpandConstant('{sd}\'));
  InstallLog('Free disk on ' + ExpandConstant('{sd}') + ': ' + IntToStr(Disk) + ' MB');
  if (Disk >= 0) and (Disk < MinFreeDiskMB) then begin
    InstallLog('Refused: less than 3 GB free.');
    SuppressibleMsgBox('{#AppName} needs at least 3 GB of free disk space on ' +
      ExpandConstant('{sd}') + '. There is ' + IntToStr(Disk) + ' MB.',
      mbCriticalError, MB_OK, IDOK);
    Result := False;
    Exit;
  end;

  InstalledVersion := ReadInstalledVersion;
  if IsUpgrade then begin
    InstallLog('Installed version: ' + InstalledVersion);
    if CompareVersions(InstalledVersion, '{#AppVersion}') > 0 then begin
      InstallLog('Refused: downgrade from ' + InstalledVersion + '.');
      SuppressibleMsgBox('{#AppName} ' + InstalledVersion + ' is installed, and this Setup is ' +
        'the older version {#AppVersion}.' + NL + NL +
        'Setup will not replace a newer version with an older one: the database has ' +
        'already been upgraded past what this version understands.',
        mbCriticalError, MB_OK, IDOK);
      Result := False;
    end;
  end else
    InstallLog('No earlier installation found: a fresh install.');
end;

{ -- The one question ---------------------------------------------------------- }

function IsClient: Boolean;
begin
  Result := RolePage.SelectedValueIndex = 1;
end;

function IsServer: Boolean;
begin
  Result := not IsClient;
end;

function CanStart: Boolean;
begin
  Result := IsClient or ServerReady;
end;

function VCRedistNeeded: Boolean;
var
  Installed, Major, Minor: Cardinal;
  Found: Boolean;
begin
  Found := RegQueryDWordValue(HKLM32, VcRuntimeKey, 'Installed', Installed) and
    RegQueryDWordValue(HKLM32, VcRuntimeKey, 'Major', Major) and
    RegQueryDWordValue(HKLM32, VcRuntimeKey, 'Minor', Minor);
  if not Found then
    Found := RegQueryDWordValue(HKLM64, VcRuntimeKey, 'Installed', Installed) and
      RegQueryDWordValue(HKLM64, VcRuntimeKey, 'Major', Major) and
      RegQueryDWordValue(HKLM64, VcRuntimeKey, 'Minor', Minor);
  Result := not (Found and (Installed = 1) and (Major = 14) and (Minor >= {#VcRuntimeMinor}));
end;

procedure RoleChanged(Sender: TObject);
begin
  LanCheck.Enabled := RolePage.SelectedValueIndex = 0;
end;

procedure InitializeWizard;
begin
  RolePage := CreateInputOptionPage(wpSelectDir,
    'This PC',
    'What will this PC do?',
    'One PC keeps the data and runs the server. Every other PC runs only the ' +
    'app and connects to it over the network.',
    True, False);
  RolePage.Add('This PC: server and app');
  RolePage.Add('App only: connect to a server on the network');
  RolePage.CheckListBox.Height := ScaleY(56);
  RolePage.CheckListBox.OnClickCheck := @RoleChanged;

  LanCheck := TNewCheckBox.Create(RolePage);
  LanCheck.Parent := RolePage.Surface;
  LanCheck.Top := RolePage.CheckListBox.Top + RolePage.CheckListBox.Height + ScaleY(12);
  LanCheck.Left := ScaleX(20);
  LanCheck.Width := RolePage.SurfaceWidth - ScaleX(20);
  LanCheck.Caption := 'Allow other PCs on this network to connect';
  LanCheck.Checked := GetPreviousData('AllowLan', '0') = '1';

  if GetPreviousData('MachineRole', 'server') = 'client' then
    RolePage.SelectedValueIndex := 1
  else
    RolePage.SelectedValueIndex := 0;
  RoleChanged(nil);

  ServerPage := CreateInputQueryPage(RolePage.ID,
    'Server',
    'Which server does this PC connect to?',
    'Type the address of the PC running the Agency Platform Server, for example ' +
    'http://192.168.1.50:8000. Setup checks that it answers.');
  ServerPage.Add('Server address:', False);
  ServerPage.Values[0] := GetPreviousData('ServerUrl', 'http://');

  { The finished page's sign-in block: hidden until there is one to show. }
  CredentialsLabel := TNewStaticText.Create(WizardForm);
  CredentialsLabel.Parent := WizardForm.FinishedPage;
  CredentialsLabel.Left := WizardForm.FinishedLabel.Left;
  CredentialsLabel.Caption := 'Sign in with:';
  CredentialsLabel.Visible := False;

  UserEdit := TNewEdit.Create(WizardForm);
  UserEdit.Parent := WizardForm.FinishedPage;
  UserEdit.Left := WizardForm.FinishedLabel.Left;
  UserEdit.Width := WizardForm.FinishedLabel.Width;
  UserEdit.ReadOnly := True;
  UserEdit.Visible := False;

  PasswordEdit := TNewEdit.Create(WizardForm);
  PasswordEdit.Parent := WizardForm.FinishedPage;
  PasswordEdit.Left := WizardForm.FinishedLabel.Left;
  PasswordEdit.Width := WizardForm.FinishedLabel.Width;
  PasswordEdit.ReadOnly := True;
  PasswordEdit.Visible := False;

  CopyButton := TNewButton.Create(WizardForm);
  CopyButton.Parent := WizardForm.FinishedPage;
  CopyButton.Left := WizardForm.FinishedLabel.Left;
  CopyButton.Width := ScaleX(96);
  CopyButton.Height := WizardForm.NextButton.Height;
  CopyButton.Caption := 'Copy';
  CopyButton.Visible := False;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = RolePage.ID then
    { An upgrade keeps the role it was installed with. }
    Result := IsUpgrade and (GetPreviousData('MachineRole', '') <> '')
  else if PageID = ServerPage.ID then
    Result := IsServer or (IsUpgrade and (GetPreviousData('ServerUrl', '') <> ''));
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if IsClient then begin
    SetPreviousData(PreviousDataKey, 'MachineRole', 'client');
    SetPreviousData(PreviousDataKey, 'ServerUrl', Trim(ServerPage.Values[0]));
  end else
    SetPreviousData(PreviousDataKey, 'MachineRole', 'server');
  if LanCheck.Checked and IsServer then
    SetPreviousData(PreviousDataKey, 'AllowLan', '1')
  else
    SetPreviousData(PreviousDataKey, 'AllowLan', '0');
end;

{ http://host:port with no trailing slash; http:// added when left out. }
function NormalizeServerUrl(Url: String): String;
begin
  Result := Trim(Url);
  if (Pos('://', Result) = 0) and (Result <> '') then Result := 'http://' + Result;
  while (Length(Result) > 0) and (Result[Length(Result)] = '/') do
    Result := Copy(Result, 1, Length(Result) - 1);
end;

function ServerAnswers(Url: String): Boolean;
var
  Http: Variant;
begin
  Result := False;
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(3000, 3000, 5000, 5000);
    Http.Open('GET', Url + '/health', False);
    Http.Send('');
    Result := Http.Status = 200;
  except
    Result := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Url: String;
begin
  Result := True;
  if CurPageID <> ServerPage.ID then Exit;
  Url := NormalizeServerUrl(ServerPage.Values[0]);
  if (Url = '') or (Url = 'http:') or (Url = 'https:') then begin
    MsgBox('Type the server''s address, for example http://192.168.1.50:8000.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  ServerPage.Values[0] := Url;
  WizardForm.NextButton.Enabled := False;
  try
    if ServerAnswers(Url) then begin
      InstallLog('Server ' + Url + ' answered /health.');
      Exit;
    end;
  finally
    WizardForm.NextButton.Enabled := True;
  end;
  InstallLog('Server ' + Url + ' did not answer /health.');
  Result := MsgBox('Nothing answered at ' + Url + '/health.' + NL + NL +
    'Check the address, that the server PC is on and that its firewall allows ' +
    'port 8000.' + NL + NL + 'Use this address anyway? It can be changed later ' +
    'in the app''s Application Settings.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

{ -- Running server_setup.ps1 ---------------------------------------------------- }

function StartsWith(Prefix, S: String): Boolean;
begin
  Result := Copy(S, 1, Length(Prefix)) = Prefix;
end;

{ Runs the script, returns whether it succeeded, and leaves the reason in
  FailureReason when it did not: from "Install stopped:" to the end, or failing
  that the last lines it printed. The script logs its own output to the install
  log; the administrator password never reaches that file or this one. }
function RunSetupScript(Script, Arguments: String): Boolean;
var
  Params, Line: String;
  Output: TExecOutput;
  Lines: TArrayOfString;
  ResultCode, I, Count, StoppedAt, From: Integer;
  Launched: Boolean;
begin
  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Script + '" ' +
    Arguments + ' -InstallDir "' + ExpandConstant('{app}') + '"';
  if InstallLogPath <> '' then Params := Params + ' -LogFile "' + InstallLogPath + '"';
  InstallLog('Running server_setup.ps1 ' + Arguments);
  Launched := ExecAndCaptureOutput('powershell.exe', Params, ExpandConstant('{tmp}'),
    SW_HIDE, ewWaitUntilTerminated, ResultCode, Output);

  Count := 0;
  StoppedAt := -1;
  SetArrayLength(Lines, GetArrayLength(Output.StdOut) + GetArrayLength(Output.StdErr));
  for I := 0 to GetArrayLength(Output.StdOut) - 1 do begin
    Line := Trim(Output.StdOut[I]);
    if StartsWith('admin-user:', Line) then begin
      AdminUser := Copy(Line, Length('admin-user:') + 1, Length(Line));
      Continue;
    end;
    if StartsWith('admin-password:', Line) then begin
      AdminPassword := Copy(Line, Length('admin-password:') + 1, Length(Line));
      Continue;
    end;
    if StartsWith('Install stopped:', Line) then StoppedAt := Count;
    Lines[Count] := Line;
    Count := Count + 1;
  end;
  for I := 0 to GetArrayLength(Output.StdErr) - 1 do begin
    Lines[Count] := Trim(Output.StdErr[I]);
    InstallLog('stderr: ' + Lines[Count]);
    Count := Count + 1;
  end;
  SetArrayLength(Lines, Count);

  Result := Launched and (ResultCode = 0);
  if Result then begin
    InstallLog('server_setup.ps1 succeeded.');
    Exit;
  end;
  if not Launched then
    FailureReason := 'Windows PowerShell could not be started: ' + SysErrorMessage(ResultCode)
  else begin
    From := StoppedAt;
    if From < 0 then From := Count - 12;
    if From < 0 then From := 0;
    FailureReason := '';
    for I := From to Count - 1 do
      if Lines[I] <> '' then FailureReason := FailureReason + Lines[I] + NL;
    if FailureReason = '' then
      FailureReason := 'The step exited with code ' + IntToStr(ResultCode) + ' and said nothing.';
  end;
  InstallLog('server_setup.ps1 failed (exit ' + IntToStr(ResultCode) + ').');
end;

{ An upgrade of a server stops it and dumps every store before a single file is
  replaced. A failed backup stops the upgrade here, with nothing changed. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not IsUpgrade or IsClient then Exit;
  ExtractTemporaryFile('server_setup.ps1');
  WizardForm.PreparingLabel.Caption := 'Backing up the database before the upgrade...';
  if not RunSetupScript(ExpandConstant('{tmp}\server_setup.ps1'),
      '-Action Backup -PreviousVersion "' + InstalledVersion + '"') then
    Result := 'The backup taken before an upgrade failed, so nothing was changed.' + NL + NL +
      FailureReason + NL + 'The full output is in ' + InstallLogPath;
end;

procedure InstallVCRedist;
var
  ResultCode: Integer;
  Redist: String;
begin
  Redist := ExpandConstant('{tmp}\vc_redist.x64.exe');
  if not FileExists(Redist) then begin
    InstallLog('Visual C++ runtime: already present.');
    Exit;
  end;
  WizardForm.StatusLabel.Caption := 'Installing the Visual C++ runtime...';
  if Exec(Redist, '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    InstallLog('Visual C++ runtime: vc_redist exited ' + IntToStr(ResultCode) +
      ' (0 installed, 1638 a newer one is present, 3010 needs a restart)')
  else
    InstallLog('Visual C++ runtime: could not run vc_redist: ' + SysErrorMessage(ResultCode));
end;

procedure SetUpServer;
var
  Arguments: String;
begin
  ServerStepRan := True;
  WizardForm.StatusLabel.Caption :=
    'Setting up the database and the server. This can take a few minutes...';
  Arguments := '-Action Server';
  if LanCheck.Checked then Arguments := Arguments + ' -AllowLan';
  ServerReady := RunSetupScript(ExpandConstant('{app}\packaging\server_setup.ps1'), Arguments);
  if ServerReady then Exit;
  SuppressibleMsgBox(
    '{#AppName} is installed, but its server could not be set up, so it cannot be used yet.' +
    NL + NL + FailureReason + NL +
    'Fix that and run this Setup again. It is safe to repeat and continues from where it stopped.' +
    NL + NL + 'Everything it did is in:' + NL + InstallLogPath,
    mbError, MB_OK, IDOK);
end;

procedure SetUpClient;
begin
  if not RunSetupScript(ExpandConstant('{app}\packaging\server_setup.ps1'),
      '-Action Client -ServerUrl "' + NormalizeServerUrl(ServerPage.Values[0]) + '"') then
    InstallLog('Could not write the server address: ' + FailureReason);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    InstallVCRedist;
    if IsClient then SetUpClient else SetUpServer;
  end;
end;

{ -- The finished page ----------------------------------------------------------- }

procedure CopyCredentials(Sender: TObject);
var
  ResultCode: Integer;
begin
  { Through the environment, not the command line, where the process list
    would show the password. }
  SetEnvironmentVariable('AGENCY_SETUP_CLIPBOARD',
    'Sign in as: ' + AdminUser + NL + 'Password: ' + AdminPassword);
  try
    Exec('powershell.exe',
      '-NoProfile -NonInteractive -Command "Set-Clipboard -Value $env:AGENCY_SETUP_CLIPBOARD"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  finally
    SetEnvironmentVariable('AGENCY_SETUP_CLIPBOARD', '');
  end;
  if ResultCode = 0 then CopyButton.Caption := 'Copied';
end;

procedure ShowCredentials;
var
  Y: Integer;
begin
  WizardForm.FinishedLabel.Caption :=
    '{#AppName} is installed, and its server is running as a Windows service.' + NL + NL +
    'Sign in with the account below. The password must be changed at the first ' +
    'sign-in. It is also saved, for administrators only, in ' +
    ExpandConstant('{commonappdata}\{#AppName}\first-login.txt') + '.';
  WizardForm.FinishedLabel.AdjustHeight;
  Y := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(10);
  CredentialsLabel.Top := Y;
  UserEdit.Top := CredentialsLabel.Top + CredentialsLabel.Height + ScaleY(4);
  UserEdit.Text := AdminUser;
  PasswordEdit.Top := UserEdit.Top + UserEdit.Height + ScaleY(4);
  PasswordEdit.Text := AdminPassword;
  CopyButton.Top := PasswordEdit.Top + PasswordEdit.Height + ScaleY(6);
  CopyButton.OnClick := @CopyCredentials;
  CredentialsLabel.Visible := True;
  UserEdit.Visible := True;
  PasswordEdit.Visible := True;
  CopyButton.Visible := True;
  WizardForm.RunList.Top := CopyButton.Top + CopyButton.Height + ScaleY(10);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID <> wpFinished then Exit;
  if IsClient then begin
    WizardForm.FinishedLabel.Caption :=
      '{#AppName} is installed and connects to ' + NormalizeServerUrl(ServerPage.Values[0]) +
      '.' + NL + NL + 'To change the server later, click the gear (Application Settings) ' +
      'on the sign-in screen.';
    Exit;
  end;
  if not ServerStepRan then Exit;
  if not ServerReady then
    WizardForm.FinishedLabel.Caption :=
      '{#AppName}''s files are installed, but its server is not set up, ' +
      'so it cannot be used yet.' + NL + NL + FailureReason + NL +
      'Run this Setup again once that is fixed. The full log is ' + InstallLogPath + '.'
  else if AdminPassword <> '' then
    ShowCredentials
  else
    WizardForm.FinishedLabel.Caption :=
      '{#AppName} is upgraded to {#AppVersion}, and its server is running again. ' +
      'Sign in as before.';
end;

procedure DeinitializeSetup;
var
  InnoLog: AnsiString;
begin
  { Inno's own log, appended, so one file holds the whole run. }
  if (InstallLogPath <> '') and LoadStringFromFile(ExpandConstant('{log}'), InnoLog) then
    SaveStringToFile(InstallLogPath, NL + '---- Inno Setup log ----' + NL + InnoLog, True);
end;

{ -- Uninstall ---------------------------------------------------------------- }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Arguments: String;
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  Arguments := '-Action Uninstall';
  { Default No: an uninstall takes the program away, not the firm's records. }
  if SuppressibleMsgBox('Also delete all data (database, backups, logs)?' + NL + NL +
      'Choose No to keep them: installing again later picks the data up where it ' +
      'was left. Yes cannot be undone.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    Arguments := Arguments + ' -DeleteData';
  Exec('powershell.exe', '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\packaging\server_setup.ps1') + '" ' + Arguments +
    ' -InstallDir "' + ExpandConstant('{app}') + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Log('server_setup.ps1 -Action Uninstall exited ' + IntToStr(ResultCode));
end;
