; Inno Setup script for the Agency Platform.
;
; Compiled by packaging\build_installer.ps1, which stages the payload and passes
; the version in. Do not run it by hand against a source tree: it installs a
; *staged* directory, deliberately, so what reaches a customer is only what the
; staging step chose to put there.
;
; Layout, and the reasoning:
;
;   {app}                        Program Files. Read-only once installed.
;     agency_desktop.exe           the client, with its DLLs and data\ beside it
;     backend\agency-server.exe    the server, compiled: it carries its own
;                                  Python and every dependency, so the machine
;                                  needs neither
;     backend\alembic\versions\    the migrations, which stay as source because
;                                  Alembic loads them by path at runtime
;     backend\config\.env          written by the configure step, then only read
;     packaging\install.ps1        the configure step itself
;
;   {commonappdata}\Agency Platform    ProgramData. Writable while running.
;     logs\                      AGENCY_LOG_DIRECTORY points here
;     storage\                   attachments
;
; Why config\.env sits under Program Files rather than ProgramData: alembic.ini
; declares `script_location = alembic` and `prepend_sys_path = .`, both relative
; to the working directory, so the server runs with its working directory set to
; {app}\backend and `Settings` reads `config/.env` from there. The compiled
; binary answers the same question the same way -- `application_root()` is the
; directory the executable sits in -- so the two cannot disagree. It is written once by an
; elevated installer and only read afterwards, so a read-only location is right.
; Logs are the part that must be writable, and an absolute path in that same
; file sends them to ProgramData.
;
; This installer places files and shortcuts. It does not invent secrets: the
; signing key, the database password and the `agency_app` role are generated per
; machine by the configure step below, which is the same install.ps1 that has
; always done it rather than a second copy of that logic.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef PayloadDir
  #define PayloadDir "..\dist\staging"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\windows"
#endif

; ExecAndCaptureOutput, which the configure step needs to read what went wrong,
; arrived in Inno Setup 6.3.
#if Ver < EncodeVer(6, 3, 0)
  #error Inno Setup 6.3 or later is required: winget install --id JRSoftware.InnoSetup
#endif

#define AppName "Agency Platform"
#define AppPublisher "Agency"
#define AppExeName "agency_desktop.exe"

[Setup]
; Never change this GUID. It is how Windows recognises an upgrade of this
; product rather than a second copy of it; a new one would install alongside the
; old and leave two entries in Add/Remove Programs.
AppId={{8F3B1C42-6D9E-4A57-9C21-5E7A4B0D3F18}
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
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Writing to Program Files, creating the ProgramData tree, and creating a
; PostgreSQL role all need it.
PrivilegesRequired=admin
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
DisableProgramGroupPage=yes
; Upgrading should not ask a customer where the product lives. It lives where it
; already lives.
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Dirs]
; Writable by ordinary users: the server writes here while running as whoever
; started it, which is not necessarily an administrator.
Name: "{commonappdata}\{#AppName}\logs"; Permissions: users-modify
Name: "{commonappdata}\{#AppName}\storage"; Permissions: users-modify

[Files]
; Everything the staging step produced. It contains no .env -- see the header.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
  WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; The configure step is not here. It used to be -- a hidden powershell entry --
; and Inno Setup does not look at a [Run] entry's exit code, so when it failed
; (no PostgreSQL, a wrong password, a fresh server it had no administrator
; account for) Setup still said it had finished and nobody was told. It runs
; from [Code] below, where the exit code and the output are both read.
Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName}"; \
  WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent; \
  Check: IsDatabaseReady

[UninstallDelete]
; Nothing here removes logs, storage, the configuration or the database. An
; uninstall takes the program away; it does not take the firm's records away.
; Removing those is a deliberate act, done by somebody who means it.
Type: filesandordirs; Name: "{app}\backend\__pycache__"

[Code]
{ First-run configuration: generate the signing key and database password,
  create the `agency_app` role and the database, migrate every store. It is
  install.ps1 -ConfigureOnly, the same implementation install.bat uses, and it
  is safe to repeat -- every step checks first -- so it runs on an upgrade too.

  What this adds over the old [Run] entry is that its outcome is read:

  * A fresh PostgreSQL has no `agency_app` role, and creating one needs an
    administrator account. The Database page asks for it, once, and hands it
    over in environment variables rather than on the command line, where the
    process list would show it. It is never written anywhere.
  * A failure is shown, with the installer's own reason, and the finished page
    says the database is not set up rather than "installed". The whole output
    goes to the logs folder -- minus the administrator password line.
  * On success the generated administrator password is shown on the finished
    page. The step prints it once and nothing else ever will; a hidden window
    used to swallow it, leaving it readable only in config\.env.

  The page is skipped once a run has succeeded (the marker file below), which is
  what an upgrade looks like. It is shown again after a failure, so running
  Setup again is the repair -- config\.env already exists by then and is left
  alone, and the role is moved to the password it holds. }

const
  AdminAccount = 'platform-admin@agency.local';
  { A line break. Not written as #13#10 at the start of a line, which the
    preprocessor reads as a directive of its own. }
  NL = #13#10;

var
  DatabasePage: TInputQueryWizardPage;
  DatabaseReady: Boolean;
  ConfigureRan: Boolean;
  GeneratedPassword: String;
  FailureReason: String;

function SetEnvironmentVariable(lpName: String; lpValue: String): Integer;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function ReadyMarker(Dir: String): String;
begin
  Result := AddBackslash(Dir) + 'backend\config\database-ready';
end;

function ConfigureLog: String;
begin
  Result := ExpandConstant('{commonappdata}\{#AppName}\logs\setup-configure.log');
end;

function IsDatabaseReady: Boolean;
begin
  Result := DatabaseReady;
end;

procedure InitializeWizard;
begin
  DatabasePage := CreateInputQueryPage(wpSelectDir,
    'Database',
    'The PostgreSQL server {#AppName} keeps its data in.',
    'PostgreSQL 17 must already be installed and running.' + NL + NL +
    'Setup creates the application''s own database account and database. ' +
    'That needs a PostgreSQL administrator account, once: the password is ' +
    'used for this step only and is not stored.');
  DatabasePage.Add('Server:', False);
  DatabasePage.Add('Port:', False);
  DatabasePage.Add('Administrator account:', False);
  DatabasePage.Add('Administrator password:', True);
  DatabasePage.Values[0] := 'localhost';
  DatabasePage.Values[1] := '5432';
  DatabasePage.Values[2] := 'postgres';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = DatabasePage.ID) and FileExists(ReadyMarker(WizardDirValue));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID <> DatabasePage.ID then Exit;
  Port := StrToIntDef(Trim(DatabasePage.Values[1]), 0);
  if Trim(DatabasePage.Values[0]) = '' then begin
    MsgBox('Enter the PostgreSQL server: localhost when it runs on this machine.', mbError, MB_OK);
    Result := False;
  end else if (Port < 1) or (Port > 65535) then begin
    MsgBox('The port must be a number from 1 to 65535. PostgreSQL uses 5432 unless it was changed.', mbError, MB_OK);
    Result := False;
  end else if Trim(DatabasePage.Values[2]) = '' then begin
    MsgBox('Enter a PostgreSQL administrator account. The one PostgreSQL creates is called postgres.', mbError, MB_OK);
    Result := False;
  end;
end;

function StartsWith(Prefix, S: String): Boolean;
begin
  Result := Copy(S, 1, Length(Prefix)) = Prefix;
end;

procedure RunConfigure;
var
  Params, Line: String;
  Output: TExecOutput;
  Lines: TArrayOfString;
  ResultCode, I, Count, StoppedAt, From: Integer;
  Launched, AskedForDatabase: Boolean;
begin
  ConfigureRan := True;
  AskedForDatabase := not FileExists(ReadyMarker(ExpandConstant('{app}')));

  { -NonInteractive: nobody can answer a prompt in a hidden window, so one
    must fail rather than wait for ever. }
  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\packaging\install.ps1') + '" -InstallDir "' +
    ExpandConstant('{app}') + '" -ConfigureOnly -SkipStart';
  if AskedForDatabase then begin
    Params := Params + ' -DatabaseHost "' + Trim(DatabasePage.Values[0]) +
      '" -DatabasePort ' + Trim(DatabasePage.Values[1]);
    SetEnvironmentVariable('INSTALL_ADMIN_USER', Trim(DatabasePage.Values[2]));
    SetEnvironmentVariable('INSTALL_ADMIN_PASSWORD', DatabasePage.Values[3]);
  end;

  WizardForm.StatusLabel.Caption := 'Setting up the database. This can take a few minutes...';
  try
    Launched := ExecAndCaptureOutput('powershell.exe', Params, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode, Output);
  finally
    { The child has read them by now; this process keeps them no longer. }
    SetEnvironmentVariable('INSTALL_ADMIN_USER', '');
    SetEnvironmentVariable('INSTALL_ADMIN_PASSWORD', '');
  end;

  { One list, stdout then stderr, with the password line kept out of it. }
  Count := 0;
  SetArrayLength(Lines, GetArrayLength(Output.StdOut) + GetArrayLength(Output.StdErr));
  StoppedAt := -1;
  for I := 0 to GetArrayLength(Output.StdOut) - 1 do begin
    Line := Trim(Output.StdOut[I]);
    if StartsWith('Password:', Line) then begin
      GeneratedPassword := Trim(Copy(Line, Length('Password:') + 1, Length(Line)));
      Line := 'Password:   (shown on the finished page, not logged)';
    end;
    if StartsWith('Install stopped:', Line) then StoppedAt := Count;
    Lines[Count] := Line;
    Count := Count + 1;
  end;
  for I := 0 to GetArrayLength(Output.StdErr) - 1 do begin
    Lines[Count] := Trim(Output.StdErr[I]);
    Count := Count + 1;
  end;
  SetArrayLength(Lines, Count);
  SaveStringsToUTF8File(ConfigureLog, Lines, False);

  DatabaseReady := Launched and (ResultCode = 0);
  if DatabaseReady then begin
    SaveStringToFile(ReadyMarker(ExpandConstant('{app}')),
      'Database set up by Setup {#AppVersion}.' + NL, False);
    Log('Configure step succeeded.');
    Exit;
  end;

  { The installer's own words: from "Install stopped:" to the end, or failing
    that the last lines it wrote. }
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
      FailureReason := 'The configure step exited with code ' + IntToStr(ResultCode) + ' and said nothing.';
  end;
  Log('Configure step failed: ' + FailureReason);
  SuppressibleMsgBox(
    '{#AppName} is installed, but its database could not be set up, so it cannot be used yet.' +
    NL + NL + FailureReason + NL +
    'Fix that and run this Setup again. It is safe to repeat and continues from where it stopped.' +
    NL + NL + 'Everything the step printed is in:' + NL + ConfigureLog,
    mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then RunConfigure;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID <> wpFinished) or not ConfigureRan then Exit;
  if not DatabaseReady then
    WizardForm.FinishedLabel.Caption :=
      '{#AppName}''s files are installed, but its database is not set up, ' +
      'so it cannot be used yet.' + NL + NL + FailureReason + NL +
      'Run this Setup again once that is fixed. The full output is in ' + ConfigureLog + '.'
  else if GeneratedPassword <> '' then
    WizardForm.FinishedLabel.Caption :=
      '{#AppName} is installed and its database is ready.' + NL + NL +
      'Sign in as:  ' + AdminAccount + NL +
      'Password:    ' + GeneratedPassword + NL + NL +
      'Write that password down now. It is not shown again, and it must be ' +
      'changed at the first sign-in.';
end;
