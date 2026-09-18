# Installing the Agency Platform

For the IT person setting the system up at a firm, typically a small
distributor. It assumes no knowledge of Python and only a little of PostgreSQL
or the command line: every step says what to type, what you should see, and
what to do if you see something else.

If you are a developer setting up a working copy, read
[`RUNNING.md`](RUNNING.md) instead. If you are building the installer, read
[`RELEASE_BUILD.md`](RELEASE_BUILD.md). This page is about installing the
product on the machines a firm will actually use.

Checked against the repository on **2026-09-18**, version `1.0.0` (`VERSION`).

---

## Read this first: what has and has not been proven

Two things are not finished, and you should know them before you start.

- **The installer has never been tested on a clean machine.** It has been built
  and installed on the development machine, which already had Python,
  PostgreSQL and developer tools on it. The test that matters, on a fresh
  Windows machine with no Python, has not been run yet
  ([`RELEASE_BUILD.md`](RELEASE_BUILD.md), "Testing a release", step 6). The
  build is arranged so that it should work there. Nobody has seen it work.
  Treat your first installation as that test, and use a machine you can
  rebuild.
- **The installer is not code-signed.** No certificate exists yet. When you run
  `AgencyPlatform-1.0.0-Setup.exe`, Windows SmartScreen will warn that the
  publisher is unknown ("Windows protected your PC"). To go on, click
  **More info** and then **Run anyway**. The publisher shown is the placeholder
  `Agency` until a certificate and the legal company name are supplied
  (`packaging/AgencyPlatform.iss`, `packaging/nuitka.args`).

Where this page gives a figure, it says where the figure came from. **Sourced**
means it comes from a file in the repository, and that file is named.
**Measured** means it was measured on the development machine, and the date is
given. **Recommendation** means it is a judgement and nobody has measured it.
Treat recommendations as a starting point, not a guarantee.

---

## 1. What gets installed where

The platform has two parts, and they run on different machines:

| Part | Runs on | What it is |
| --- | --- | --- |
| **The server** | one machine | PostgreSQL 17 holds the data. `agency-server.exe` is the application, and it answers the clients over HTTP(S) on port 8000 |
| **The client** | every user's PC | `agency_desktop.exe`, the Windows program people use. It talks only to the server, never to the database, and keeps no business data of its own |

The server machine can also run the client, and in a one-person office it is
the only machine.

**There is one installer, and it contains both parts.**
`AgencyPlatform-<version>-Setup.exe` puts the client and the server in the same
folder, whichever machine you run it on. There is no separate client-only
installer yet (see [section 14](#14-known-gaps)). On a client PC the server half
is copied too, but you never start it.

What the setup program puts where (`packaging/AgencyPlatform.iss`):

| Location | Contents |
| --- | --- |
| `C:\Program Files\Agency Platform\` | the client: `agency_desktop.exe`, its DLLs, `data\` and `config\branding.json` |
| `C:\Program Files\Agency Platform\backend\` | the server: `agency-server.exe` with its DLLs, `alembic.ini`, `alembic\` (the database migrations), `scripts\start_backend.ps1` |
| `C:\Program Files\Agency Platform\backend\config\.env` | the server's settings, written on the machine at install time. **Never** copied from anywhere else |
| `C:\Program Files\Agency Platform\packaging\install.ps1` | the configuration step the setup program runs |
| `C:\ProgramData\Agency Platform\logs`, `...\storage` | created by the setup program. Nothing writes to them yet ([section 14](#14-known-gaps)) |
| Start Menu, and optionally the desktop | an **Agency Platform** shortcut to the client |

The server writes its logs to `backend\logs\` inside the installation folder.
The database lives inside PostgreSQL, not in any of these folders.

---

## 2. Requirements

### 2.1 Server machine

| | Minimum | Comfortable | Basis |
| --- | --- | --- | --- |
| **CPU** | 2 cores | 4 cores | Recommendation, from [`HARDWARE_SIZING.md`](HARDWARE_SIZING.md): the application is I/O-bound on PostgreSQL. No load test has been run |
| **RAM** | 4 GB | **8 GB** | Recommendation. Measured 2026-09-06, at rest: the backend used **32 MB**; PostgreSQL held **3.0 GiB**, nearly all of it page cache, and it shrinks when given less |
| **Disk** | 128 GB SSD | 256 GB SSD | Recommendation, leaving room for Windows, PostgreSQL, logs and backup copies. Measured: four firms with two years of trading came to **294 MB** of tables (2026-09-06), 85% of it logs. The installed program is about **240 MB** (the staged tree measured 240.1 MB on 2026-09-17, of which `agency-server.exe` was 153.6 MB) |
| **Power** | never sleeps | — | Everybody depends on the server. If it sleeps, every client stops. Set the power plan so it never sleeps |

A mini PC with 8 GB of RAM, four cores and a 256 GB SSD, running PostgreSQL
installed directly on Windows (not in Docker), is the setup
[`HARDWARE_SIZING.md`](HARDWARE_SIZING.md) recommends for a small office.
**4 GB is only workable without Docker**: Docker Desktop on its own took
7.6 GiB on the measuring machine.

**What these numbers do not tell you.** Nobody has measured how many users the
server can handle at once. Every figure above was taken on a working system at
rest, with made-up demo data. A firm with a very large product list or heavy
batch/serial tracking may need more.

### 2.2 Each client PC

| | Requirement | Basis |
| --- | --- | --- |
| **Windows** | Windows 10 or 11, **64-bit** (x64) | Sourced: the client's manifest declares Windows 10 and 11 (`desktop/windows/runner/runner.exe.manifest`), and the setup program installs on x64 only (`ArchitecturesAllowed=x64compatible` in `packaging/AgencyPlatform.iss`). Windows on ARM is untested |
| **RAM** | 4 GB | Recommendation. Measured: the client used **84 MB** at rest (2026-09-06) |
| **Disk** | about 250 MB free | The whole package is installed, server half included (240.1 MB staged, measured 2026-09-17) |
| **Screen** | 1366 × 768 or larger | Sourced: the smallest resolution every screen is designed for ([`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)) |
| **Network** | can reach the server on TCP port 8000 | Sourced: the default port (`backend/app/cli.py`, `install/install.ps1`) |
| **Rights** | an administrator account, **for installing only** | Sourced: `PrivilegesRequired=admin` in `packaging/AgencyPlatform.iss`. Everyday use needs no administrator rights |

### 2.3 Operating system for the server

**Windows 10 or 11, 64-bit.** The server program is a 64-bit Windows
executable, and the setup program refuses to install anywhere else (sourced:
`packaging/AgencyPlatform.iss`).

**Windows Server is a recommendation, and it is untested.** Nothing in the
server is specific to desktop Windows. Even so, nobody has installed it on
Windows Server, so treat Windows Server 2019 or later as a reasonable guess.

### 2.4 Software

| Software | Where | Required? | Basis |
| --- | --- | --- | --- |
| **PostgreSQL 17** | server | **Yes.** It is the only other software the server needs | Sourced: the primary target database (`CLAUDE.md`, [`TENANCY_AND_STORES.md`](TENANCY_AND_STORES.md)). The installer script names the package `PostgreSQL.PostgreSQL.17` (`install/install.ps1`) |
| Python | anywhere | **No.** `agency-server.exe` is compiled and carries its own | Sourced: [`RELEASE_BUILD.md`](RELEASE_BUILD.md). Not yet proven on a clean machine, as noted above |
| Windows PowerShell 5.1 | server | Yes, for the configuration step and `start_backend.ps1` | It ships with Windows 10 and 11 |
| Microsoft Visual C++ Redistributable (x64) | client, possibly server | **Unknown.** See below | Not verified |

**The Visual C++ runtime is an open question.** A Flutter Windows program
normally needs Microsoft's Visual C++ runtime DLLs. This repository's build does
not copy them into the package; nothing in `packaging/` or `desktop/windows/`
mentions them. Most Windows 10 and 11 machines already have them, because other
programs install them. The clean-machine test would settle whether a new machine
does. If `agency_desktop.exe` or `agency-server.exe` will not start and Windows
reports a missing `VCRUNTIME140.dll` or `MSVCP140.dll`, install the
**Microsoft Visual C++ Redistributable for Visual Studio 2015–2022 (x64)** from
Microsoft and try again.

### 2.5 Network

- **One TCP port, 8000 by default**, open on the server to the office network.
  The clients connect to it and nothing else. The database port (5432) never
  needs to be open to the network when PostgreSQL runs on the server machine
  itself.
- **The server needs no internet connection.** It downloads nothing. The only
  download during setup is PostgreSQL, if you use `winget` to install it.
- **Plain `http://` works only on your own network.** The client accepts
  `https://` to any address. It accepts `http://` only to a private-network
  address: `localhost`, `127.x`, `10.x`, `172.16.x` to `172.31.x`, `192.168.x`,
  `169.254.x`, a name with no dots, or a name ending in `.local`, `.lan`,
  `.internal` or `.home.arpa` (sourced: `normalizeServerUrl` and
  `isPrivateNetworkHost` in
  `desktop/lib/core/preferences/desktop_preferences_service.dart`). Anything
  else needs HTTPS, set up as in [section 5.6](#56-https-optional).

> **Plain HTTP sends passwords across the network in clear text.** On an office
> network you control, with no internet exposure, that is usually accepted. On
> any network you do not control, use HTTPS.

---

## 3. Before you start

Decide these four things and write them down:

1. **Which machine is the server.** It has to stay on, and its address should
   not change. Give it a fixed IP address, or a DHCP reservation on the router,
   for example `192.168.1.50`. Every client stores that address.
2. **The PostgreSQL superuser password.** You choose it when you install
   PostgreSQL. It is used once, to create the application's own database
   account, and the application never stores it.
3. **Who the first administrator is.** The platform comes with one account,
   `platform-admin@agency.local`. Its first password is generated during
   installation. Whoever signs in first must change it.
4. **Where backups go.** The platform has no backup of its own yet
   ([section 9](#9-backups)), so decide now where a nightly copy goes, and keep
   it off the server.

You do **not** choose the application's database password. The installer
generates it, writes it to `backend\config\.env`, and nobody needs to type it.

---

## 4. Install PostgreSQL 17 on the server

Skip this if PostgreSQL 17 is already installed and running.

Either install it with `winget`, in an administrator PowerShell window:

```powershell
winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements
```

or download the Windows installer from
<https://www.postgresql.org/download/windows/> and run it.

During installation:

- **Set a password for the `postgres` superuser, and keep it.** You need it
  once, in [section 5.2](#52-finish-the-configuration).
- Leave the port at **5432**. That is what the platform expects
  (`AGENCY_DATABASE_PORT=5432`, which the configuration step writes).
- Leave the service set to start automatically.

**Keep PostgreSQL on the same machine as the server** (recommendation). The
installer assumes `localhost`, and it means port 5432 never has to be opened to
the network. A database on a separate machine does work: set
`AGENCY_DATABASE_HOST` in `config\.env`. You then have to open that machine to
the server yourself, in `postgresql.conf` (`listen_addresses`) and
`pg_hba.conf`.

You do not create the application's database account by hand. Step 5.2 creates
it for you: a login called `agency_app` that is **not** a superuser and owns one
database, `agency_platform` (sourced: `install/install.ps1`,
`backend/app/core/database/bootstrap.py`).

---

## 5. Install the server

### 5.1 Run the setup program

1. Copy `AgencyPlatform-1.0.0-Setup.exe` to the server and double-click it.
2. SmartScreen warns about an unknown publisher. Click **More info**, then
   **Run anyway** (see [Read this first](#read-this-first-what-has-and-has-not-been-proven)).
3. Accept the administrator prompt. Setup needs administrator rights.
4. Accept the default folder, `C:\Program Files\Agency Platform`, or choose
   another with **Browse**. When you upgrade later, setup reuses whatever folder
   you pick now.
5. At the end, setup shows "Setting up the database. This can take a few
   minutes..." while it runs the configuration step. **That step runs hidden,
   and setup does not report whether it worked.**

On the last page, **Start Agency Platform** opens the client. Its sign-in will
fail until the server is running (section 5.3). That failure is expected.

### 5.2 Finish the configuration

**Do this step even if setup appeared to succeed.** The setup program runs the
configuration step in a hidden window and does not pass it the PostgreSQL
superuser password (sourced: the `[Run]` entry in
`packaging/AgencyPlatform.iss`). Without that password it can write
`config\.env`, but on a fresh PostgreSQL it cannot create the application's
database account. Setup ignores the failure, so nothing on screen tells you. It
also means the generated administrator password is never displayed; it stays in
`config\.env` (section 7). Every command below is safe to repeat: each checks
first and does only what is missing.

Open **Windows PowerShell as administrator**. The settings file can only be read
by administrators. Then:

```powershell
cd "C:\Program Files\Agency Platform\backend"
```

**Always run `agency-server.exe` from this folder.** It reads its settings from
`config\.env` relative to the folder you are in. Run from anywhere else, it
finds no settings, falls back to development defaults, and cannot connect.

**a. Check that the settings file exists.**

```powershell
Test-Path .\config\.env
```

If this prints `False`, the configuration step did not get as far as writing it.
Run it yourself, visibly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "..\packaging\install.ps1" -InstallDir "C:\Program Files\Agency Platform" -ConfigureOnly -SkipStart
```

It writes `config\.env`, then stops at "Could not reach PostgreSQL" because it
has no superuser password. That is expected. Carry on with step b. **Note the
`Password:` line** if it prints one: that is the administrator's first password.

The settings it writes, and why they matter (sourced:
`backend/app/core/config/settings.py`, `install/install.ps1`):

| Setting | Written as | Why |
| --- | --- | --- |
| `AGENCY_ENVIRONMENT` | `production` | Turns on the three refusals below |
| `AGENCY_JWT_SECRET_KEY` | 48 random bytes | The server **refuses to start** in production with the development key. Changing it later signs every user out |
| `AGENCY_DATABASE_PASSWORD` | generated | The server refuses to start in production with `postgres` |
| `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` | generated | **Required** outside development. It is the first administrator's first password |
| `AGENCY_DATABASE_HOST` / `_PORT` / `_NAME` / `_USERNAME` | `localhost` / `5432` / `agency_platform` / `agency_app` | Where the database is |
| `AGENCY_LOG_DIRECTORY` | `logs` | Relative to the backend folder, which puts the logs in `backend\logs\` |

Two lines in that file come from the template and need attention. To edit it,
run Notepad as administrator:

- **`AGENCY_TENANCY_CONNECTION_PROFILES`**: the template ships an active example
  profile, `REMOTE_A`, pointing at `127.0.0.1:5433` with the password
  `CHANGE_ME`. It is harmless unless a firm is created against it. **Put a `#`
  at the start of that line** unless you are setting up a second database
  server ([section 7.2](#72-firms-that-keep-their-data-in-their-own-database)).
- **`AGENCY_APP_VERSION=0.1.0`**: this overrides the real version. **Delete the
  line**, or `/health` and `agency-server where` will report `0.1.0`.

**b. Create the database account and the database.** The superuser password is
passed in an environment variable rather than typed on the command line, so it
does not end up in the console history:

```powershell
$env:INSTALL_ADMIN_USER = 'postgres'
$env:INSTALL_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host -AsSecureString 'postgres superuser password')).Password
.\agency-server.exe create-database
Remove-Item Env:\INSTALL_ADMIN_USER, Env:\INSTALL_ADMIN_PASSWORD
```

Expect:

```
role-created:agency_app
created:agency_platform
```

`role-updated` or `exists` mean the account or database was already there,
which is fine. `role-updated` also resets the account's password to the one in
`config\.env`. An `error:` line names the problem: usually a wrong superuser
password, or PostgreSQL not running.

**c. Build the database tables.** Always use `migrate-all`. It upgrades every
store the platform knows about, not just the first one:

```powershell
.\agency-server.exe migrate-all --dry-run
.\agency-server.exe migrate-all --yes
```

The dry run lists each store and its current revision. `--yes` upgrades them
and ends with each store `upgraded to head`. If any store fails, the command
names it and exits non-zero. It does not stop at the first failure.

**d. Confirm what you have.**

```powershell
.\agency-server.exe --version
.\agency-server.exe where
```

`where` prints the version, the environment (it should say `production`), the
installation folder and `compiled: True`. If it reports a problem with settings,
the message names the setting.

### 5.3 Start the server

Use the start script. It upgrades every store first, then serves, and logs both
to `backend\logs\backend-<date>.log`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Program Files\Agency Platform\backend\scripts\start_backend.ps1" -SkipSync -NoReload -BindHost 0.0.0.0
```

- **`-SkipSync`** is required on an installed copy. Without it the script first
  runs `uv sync`, a developer tool that is not installed here.
- **`-NoReload`** is required too, because a compiled copy refuses reload mode.
- **`-BindHost 0.0.0.0`** lets other PCs connect. Leave it out and the server
  answers only this machine (`127.0.0.1`).
- `-Port 8001` changes the port, if 8000 is taken.

The window stays open while the server runs, and closing it stops the server.
You can also run the server directly, from the backend folder, with
`.\agency-server.exe serve --host 0.0.0.0 --port 8000`. That skips the automatic
upgrade.

Check it from the server itself: open `http://127.0.0.1:8000/health` in a
browser. It should return a small JSON answer.

**Run the server as an administrator or as SYSTEM.** The settings file can only
be read by administrators, SYSTEM and the account that installed it (sourced:
`Protect-File` in `install/install.ps1`). The log folder is under
`Program Files`, which ordinary users cannot write to.

### 5.4 Start the server automatically

**The platform does not register a Windows service or a scheduled task.**
Nothing in the repository does. Until it does, the recommendation is a Task
Scheduler task that runs the start script as SYSTEM when the machine boots. In
an administrator PowerShell window:

```powershell
$script = 'C:\Program Files\Agency Platform\backend\scripts\start_backend.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -SkipSync -NoReload -BindHost 0.0.0.0"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Agency Platform server' -Action $action `
  -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest
```

`-ExecutionTimeLimit ([TimeSpan]::Zero)` matters. By default Task Scheduler
stops a task after three days, and it would stop the server with it.

Start it now with `Start-ScheduledTask -TaskName 'Agency Platform server'`, then
restart the machine once to confirm the server comes back by itself. This setup
is a recommendation and has not been tested with this product.

### 5.5 Open the firewall port

Clients on other PCs need TCP 8000 open on the server. This rule is a
recommendation. It opens the port to private and domain networks only, not
public ones:

```powershell
New-NetFirewallRule -DisplayName 'Agency Platform server' -Direction Inbound `
  -Protocol TCP -LocalPort 8000 -Action Allow -Profile Domain,Private
```

Make sure Windows treats the office network as **Private**. If it thinks the
network is Public, this rule does not apply.

### 5.6 HTTPS (optional)

Use HTTPS on any network you do not control, or when clients connect by a
public address. The server takes a certificate and its key (sourced:
`backend/app/cli.py`, `backend/scripts/start_backend.ps1`):

```powershell
... start_backend.ps1 -SkipSync -NoReload -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key
```

You must give both files. The server refuses to start with only one of them
rather than falling back to HTTP. **Every client PC must trust the
certificate.** For a self-signed certificate, that means importing it into each
PC's Windows certificate store. The client refuses a certificate it does not
trust, and it is meant to.

### 5.7 Check from another PC

From a client PC, open `http://<server address>:8000/health` in a browser, for
example `http://192.168.1.50:8000/health`. If it does not answer, check in this
order: the server is running with `-BindHost 0.0.0.0`, the firewall rule is in
place and the network is Private, and the address is right.

---

## 6. Install the client on each PC

1. Run the same `AgencyPlatform-1.0.0-Setup.exe` and get past SmartScreen as in
   section 5.1. Setup needs an administrator account.
2. The setup program runs its hidden configuration step on every machine. On a
   client PC, where there is no PostgreSQL, it writes a `backend\config\.env`
   and then stops quietly. **Ignore the server half on a client PC.** Do not
   start it and do not register the task from section 5.4.
3. Start **Agency Platform** from the Start Menu.

**Point the client at the server.** Nothing sets the server address at install
time. On the sign-in screen:

1. Click the **gear icon** (tooltip: *Application Settings*) at the top.
2. In **API URL**, type the server's address, for example
   `http://192.168.1.50:8000`, or `https://...` if you set up HTTPS.
3. Click **Save**.

An address the client will not accept is refused with a message explaining why
(see [section 2.5](#25-network)). The address is saved **for each Windows user**,
in `%APPDATA%\.agency_platform\desktop_preferences.json` (sourced:
`desktop/lib/core/preferences/desktop_preferences_service.dart`,
`desktop/lib/core/platform/app_storage.dart`). Each person who signs in to
Windows on that PC sets it once. **Recent Servers** in the same dialog remembers
earlier addresses. Without a saved address, the client uses
`http://localhost:8000`, which is right only on the server machine itself.

**`config\branding.json` does not set the server address.** It sits beside
`agency_desktop.exe`, in `C:\Program Files\Agency Platform\config\`, and sets
only what the program displays: application and company names, logo and splash
images, the version shown, support e-mail and website, copyright, and the sign-in
screen colours (sourced: `desktop/config/branding.json`,
`desktop/lib/core/branding/branding_config.dart`). The shipped support details
are placeholders (`support@example.com`, `https://example.com/support`). If a
value in that file is broken, the client falls back to built-in defaults and
still starts.

---

## 7. First sign-in

**The first account** is `platform-admin@agency.local`.

**Its first password** is `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` in
`C:\Program Files\Agency Platform\backend\config\.env`. The setup program never
displays it, so open that file in Notepad **run as administrator** and copy the
value. If you ran `install.ps1` or `install.bat` yourself, it was printed once at
the end.

On first sign-in you **must change the password** (sourced: the seeded account
is created with `force_password_change` set, in
`backend/alembic/versions/20260728_0001_identity_security.py`). The new password
must have at least **12 characters**, including an uppercase letter, a lowercase
letter, a digit and a symbol. It may not repeat any of the account's last five
passwords (sourced: `desktop/lib/ui/identity/change_password_dialog.dart`,
`AGENCY_SECURITY_PASSWORD_HISTORY_COUNT=5`). After the change, the value in
`config\.env` no longer signs anyone in. Leave it in the file anyway, because
the server needs the setting to start.

Five wrong passwords in a row lock an account for 15 minutes
(`AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS`, `AGENCY_SECURITY_LOCKOUT_MINUTES`).

### 7.1 Next: create a firm

The platform administrator belongs to no firm, so every firm screen stays closed
to them until a firm exists and people are added to it. Create the firm on the
**Firms** screen, then use its **Set up** panel, which shows what the firm still
needs before it can trade. [`platform-administration-guide.md`](platform-administration-guide.md)
walks through creating firms, roles and users, and
[`USER_ADMINISTRATION_GUIDE.md`](USER_ADMINISTRATION_GUIDE.md) covers people.

### 7.2 Firms that keep their data in their own database

By default a firm's data lives in the shared store, inside `agency_platform`,
and needs nothing more. A firm can instead be given its own schema, or its own
database, possibly on another server. In that case you build its storage with
**Provision storage** on the Firms screen
([`TENANCY_AND_STORES.md`](TENANCY_AND_STORES.md)).

- **Own schema** (`SCHEMA`): works with the account the installer created,
  because that account owns the `agency_platform` database.
- **Own database on the same server** (`DATABASE`, no connection profile):
  provisioning creates the new database **as `agency_app`**, which the installer
  created **without** the right to create databases (sourced:
  `_create_database_if_missing` in `backend/app/core/tenancy/lifecycle.py`,
  `backend/app/core/database/bootstrap.py`). Reading the code, provisioning
  should fail with a permission error. Nobody has tried it on an installed copy.
  If you need this mode, the smallest fix is to let that account create
  databases. As the `postgres` superuser, run `ALTER ROLE agency_app CREATEDB;`.
  That is a recommendation, and it widens the account's rights.
- **Own database on another server**: add a connection profile to
  `AGENCY_TENANCY_CONNECTION_PROFILES` in `config\.env`. It names that server's
  host, port, user and password, and the user must be allowed to create
  databases. **Restart the server** after editing the file, then create the firm.
  The server reads profiles only when it starts, and until then it refuses the
  new profile by name.

---

## 8. Upgrading to a new version

1. **Take a backup first** ([section 9](#9-backups)).
2. **Stop the server** and ask users to close the client. Recommendation: setup
   cannot replace files that are in use. If you used the task from section 5.4,
   run `Stop-ScheduledTask -TaskName 'Agency Platform server'`, then check that
   no `agency-server.exe` is left in Task Manager.
3. Run the new `AgencyPlatform-<version>-Setup.exe`. It installs into the same
   folder without asking (`UsePreviousAppDir=yes`), and Windows treats it as an
   upgrade rather than a second copy.
4. **Upgrade every store**, from an administrator PowerShell window:

   ```powershell
   cd "C:\Program Files\Agency Platform\backend"
   .\agency-server.exe migrate-all --dry-run
   .\agency-server.exe migrate-all --yes
   ```

   Setup also tries this in its hidden step, and `start_backend.ps1` does it on
   every start. Running it here is the only way to **see** the result. It covers
   the platform store, the shared firm store, and **every** firm with its own
   schema or database, including firms on another server. Those servers must be
   reachable, and their profiles must still be in `config\.env`. If one store
   fails, the others are still upgraded, and the failure is named.
5. Start the server again, then update each client PC by running the same setup
   program there.

**An upgrade keeps your data.** The database lives in PostgreSQL, and setup
never touches it except through the migration step, which only adds to it.
`config\.env`, which holds the signing key and database password, was created
on the machine rather than installed, so setup does not replace it. **Uninstalling
leaves the database, `config\.env` and the logs in place** (sourced:
`[UninstallDelete]` in `packaging/AgencyPlatform.iss`, [`RELEASE_BUILD.md`](RELEASE_BUILD.md)).
Removing those is a deliberate job for someone who means it.

---

## 9. Backups

**The platform has no backup of its own.** There is no backup script, screen or
scheduled job (sourced: `docs/BACKLOG.md`, item 35). Until there is, arrange
one yourself. Two things are essential:

1. **Every database the platform uses.** The platform database,
   `agency_platform`, holds the user accounts, the firm registry and the shared
   firm store. Every firm with its own database has another one, possibly on
   another server. To list them, run `.\agency-server.exe migrate-all --dry-run`
   from the backend folder: every line names a store and the database it is in.
   **Include firms that were deleted.** Their data is still there, and the
   dry run does not list them.
2. **`backend\config\.env`.** It holds the signing key and the database
   password. Without it, the application cannot open its own database. It also
   holds secrets, so store the copy where only administrators can read it.

A recommended nightly job is a Task Scheduler task on the server that runs
PostgreSQL's own `pg_dump` for each database and copies the files off the
machine. For example, with PostgreSQL's default install path:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe' -U postgres -F c `
  -f "D:\Backups\agency_platform-$(Get-Date -Format yyyyMMdd).dump" agency_platform
```

To run it unattended, give it the password through a
`%APPDATA%\postgresql\pgpass.conf` file belonging to the task's account, never
on the command line. **A backup file is itself sensitive.** It contains password
hashes and sign-in tokens, so protect it like `config\.env`.

**Nobody has test-restored a backup of this product.** A backup is only proven
once it has been restored. Try it once on a spare machine before you rely on it.

---

## 10. Pruning old log rows (retention)

The database collects rows that are only useful for a while: expired sign-in
tokens, sign-in history, old password history, the tax engine's calculation
log, and error reports. **Nothing removes them unless you turn it on.** Pruning
is off by default because it deletes rows. The tax calculation log grows
fastest. On the measuring machine the log tables were 85% of the database
([`HARDWARE_SIZING.md`](HARDWARE_SIZING.md)).

The server includes the job (sourced: `backend/app/cli.py`,
`backend/app/core/tenancy/retention.py`). It covers every store, the same way
`migrate-all` does:

```powershell
cd "C:\Program Files\Agency Platform\backend"
.\agency-server.exe purge-retention --dry-run    # report what would go
.\agency-server.exe purge-retention --yes        # delete it
```

What it keeps by default: refresh tokens for 7 days after they expire, sign-in
history for 365 days, the last 10 passwords per user, the tax calculation log
for 365 days, and error reports for 90 days. Each has a switch, for example
`--login-history-days 180`. The audit trail is **not** pruned: it is
append-only by design.

**Nothing schedules the job on an installed copy**, so add one yourself. As a
recommendation, run it daily as SYSTEM. The working directory has to be the
backend folder, as in section 5.2:

```powershell
$backend = 'C:\Program Files\Agency Platform\backend'
$action = New-ScheduledTaskAction -Execute "$backend\agency-server.exe" `
  -Argument 'purge-retention --yes' -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName 'Agency Platform retention' -Action $action `
  -Trigger $trigger -User 'SYSTEM'
```

Run it with `--dry-run` by hand once first, so you see what it would remove.

---

## 11. Installing from a folder instead (`install.bat`)

Use this route when you were given the platform as a **folder** rather than as
`AgencyPlatform-<version>-Setup.exe`. It runs the same configuration step
visibly, it can install PostgreSQL for you, and it starts the server and the
client at the end.

What the folder needs depends on what is in it. If it holds a compiled
`backend\agency-server.exe`, no Python is needed. If it holds the Python source
instead, the machine needs **Python 3.13 or later** and an internet connection
to download the libraries (sourced: `install/install.ps1`). The client has to
be in the folder already built, or the Flutter SDK has to be installed.

Extract the folder, open it, and **double-click `install.bat`**. A window opens
and asks where to install:

```
Install where? [Enter for C:\AgencyPlatform, B to browse, or type a folder]:
```

Press **Enter** to accept `C:\AgencyPlatform`, type a folder and press Enter,
or type **B** and press Enter to pick a folder in the Windows folder picker. A
picked folder is used as-is if it is empty or already holds an installation;
otherwise an `AgencyPlatform` folder is made inside it, so picking `D:\`
installs into `D:\AgencyPlatform`. Cancelling the picker asks again.

A complete run looks like this:

```
Agency Platform installer
  repository: C:\AgencyPlatform
  backend:    http://127.0.0.1:8000

== Checking prerequisites
   this is a compiled build -- no Python is needed on this machine

== Configuration
   wrote backend\config\.env -- signing key and database password generated,
   database account 'agency_app'
   config\.env restricted to administrators and this account

== Python environment
   not needed -- this build carries its own

== Database
   created database account 'agency_app' (not a superuser)
   created database 'agency_platform', owned by 'agency_app'

== Migrations
   every store is at head

== Desktop client
   client is built

== Starting the backend
   waiting for the backend to answer...
   backend answering on http://127.0.0.1:8000

Installed.
  Sign in as: platform-admin@agency.local
  Password:   7hK2-mQp9vTx4Rn6
  Write that password down now. It is not shown again.
```

**Write that password down before you close the window.**

Useful switches, passed after `install.bat`:

| Switch | What it does |
| --- | --- |
| `-DryRun` | Reports every step as "would…" and changes nothing. Safe on a machine already in use |
| `-InstallPrerequisites` | Installs what is missing through `winget`: PostgreSQL 17, and Python for a source copy. Needs **Run as administrator** |
| `-DatabasePassword (Read-Host -AsSecureString)` | The PostgreSQL superuser password, for when PostgreSQL is already installed. Run from a PowerShell window, with `.\install.ps1` in place of `install.bat` |
| `-BindHost 0.0.0.0` | Serves the other PCs on the network, not just this one |
| `-CertFile ... -KeyFile ...` | Serves HTTPS. You must give both files; one alone is refused |
| `-InstallDir C:\AgencyPlatform` | Installs or updates at that folder without asking |

Installing PostgreSQL through `winget` is the slow part. On a fresh machine,
ten to fifteen minutes is normal.

**If it stops.** It stops at the first real problem and names it. It is **safe
to run again**: every step checks first, so a second run continues from where
the first one stopped.

| What it says | What it means | What to do |
| --- | --- | --- |
| `Prerequisites are missing.` | Python is missing, for a source copy | Run `install.bat -InstallPrerequisites`, or install it yourself |
| `Installing prerequisites needs an elevated shell.` | Installing software needs administrator rights | Right-click `install.bat`, then **Run as administrator** |
| `Could not reach PostgreSQL.` | The database is not running, is somewhere else, or no superuser password was given | The message lists the likely causes, most likely first |
| `One or more stores failed to migrate.` | A database upgrade did not finish | The output names the store. Fix it, then run again |

**To update** a folder installation, extract the new version somewhere else,
**not** over the installed folder. Then run its installer against the same
place: `install.bat -InstallDir C:\AgencyPlatform`. `backend\config\.env`,
`backend\logs\` and `backend\storage\` at the destination are kept.

---

## 12. Where things are

For an installation made with the setup program:

| | |
| --- | --- |
| The client | `C:\Program Files\Agency Platform\agency_desktop.exe` |
| The server | `C:\Program Files\Agency Platform\backend\agency-server.exe` |
| Server settings | `...\backend\config\.env`, readable by administrators only |
| Server logs | `...\backend\logs\application.log`, plus `backend-<date>.log` from the start script |
| Starting the server by hand | `...\backend\scripts\start_backend.ps1 -SkipSync -NoReload` |
| What the client displays | `C:\Program Files\Agency Platform\config\branding.json` |
| Each user's client settings | `%APPDATA%\.agency_platform\desktop_preferences.json` |
| The database | inside PostgreSQL, managed by it. It is not a file you handle |

A folder installation uses the same layout under the folder you chose, for
example `C:\AgencyPlatform\backend\...`.

`.\agency-server.exe where`, run from the backend folder, prints the version,
the environment and the folder the server thinks it is installed in. Try it
first when the server will not start.

---

## 13. Common questions

**Do I need to be an administrator?**
To install, yes, on every machine. To run the server, it has to be an
administrator or SYSTEM, because of who can read `config\.env`. To use the
client, no.

**What is the database password?**
The installer generates it and writes it to `backend\config\.env`. Nobody sees
it and nobody needs to type it. Only administrators can read that file.

**Can I move the installation to another folder later?**
Install to the new place and restore the database. Moving the folder by hand
leaves paths pointing at the old one.

**Does it need the internet?**
Only to download PostgreSQL, and only if you install it with `winget`. The
platform itself downloads nothing, at any point. Once installed, it runs
entirely on your own network.

**Can two copies share one PostgreSQL server?**
Yes, if each has its own database name. A folder installation takes
`-DatabaseName` for that. It is rarely what anyone wants.

---

## 14. Known gaps

These are things an installation needs that the repository does not provide
yet, or does not provide reliably. Each was found by reading the files named on
2026-09-18. None of them has been reproduced on a clean machine, because no
clean-machine install has been run.

- **No clean-machine test.** See [Read this first](#read-this-first-what-has-and-has-not-been-proven).
- **Unsigned installer.** SmartScreen warns, and the publisher reads `Agency`.
  This is waiting on a certificate and the legal company name.
- **The setup program's configuration step cannot create the database on a
  fresh PostgreSQL.** It runs hidden, gets no superuser password, and its exit
  code is not checked. Section 5.2 is the workaround.
- **The generated administrator password is never shown** after an install made
  with the setup program. It has to be read out of `config\.env`.
- **No Windows service and no scheduled tasks** are registered, whether for the
  server, retention or backups. Sections 5.4 and 10 give recommended tasks.
- **No backup or restore** ([section 9](#9-backups); `docs/BACKLOG.md` item 35).
- **No client-only installer.** Every client PC gets the server half and a
  `config\.env` of its own.
- **The server address is not set at install time.** Each Windows user on each
  PC types it into Application Settings.
- **Unused ProgramData folders.** `C:\ProgramData\Agency Platform\logs` and
  `storage` are created, but the configuration step never points
  `AGENCY_LOG_DIRECTORY` there. Logs go under `Program Files`, which is why the
  server needs administrator or SYSTEM rights.
- **The settings template carries development leftovers** into a production
  `config\.env`: `AGENCY_APP_VERSION=0.1.0` and an active `REMOTE_A` connection
  profile. See section 5.2.
- **A firm with its own database on the same server** needs `CREATEDB` on
  `agency_app`, which the installer does not grant. See section 7.2.
- **The Visual C++ runtime is not bundled,** and whether a new machine needs it
  is untested. See section 2.4.
- **The hint `install.ps1` prints** for starting the server leaves out
  `-SkipSync`, which an installed copy needs. See section 5.3.
