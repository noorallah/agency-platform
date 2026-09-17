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
; First-run configuration: generate the signing key and database password,
; create the `agency_app` role and the database, migrate every store. Safe to
; repeat -- every step checks first -- so it runs on an upgrade too and does
; nothing where nothing is needed.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\packaging\install.ps1"" -InstallDir ""{app}"" -ConfigureOnly -SkipStart"; \
  WorkingDir: "{app}"; StatusMsg: "Setting up the database. This can take a few minutes..."; \
  Flags: runhidden waituntilterminated

Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName}"; \
  WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Nothing here removes logs, storage, the configuration or the database. An
; uninstall takes the program away; it does not take the firm's records away.
; Removing those is a deliberate act, done by somebody who means it.
Type: filesandordirs; Name: "{app}\backend\__pycache__"
