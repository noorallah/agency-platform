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

- **The installer has never been installed anywhere.** The server program has
  been compiled on the development machine, and the setup program was first
  compiled there on 2026-09-18, but neither has been installed on a machine:
  the development machine is not a safe place to try, because the setup program
  would point itself at the development database. The test that matters, on a fresh
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

## 4. PostgreSQL: Setup brings its own

**Do not install PostgreSQL yourself.** Since round 1 of the installer, the
server's setup program carries a private PostgreSQL 17 (the EDB binaries, the
version pinned in `packaging/build_installer.ps1`) and sets it up on its own:

- the data goes in `C:\ProgramData\Agency Platform\pgdata`;
- it listens on port **5433**, so it never collides with a PostgreSQL that is
  already on the machine on 5432;
- it runs as the Windows service **Agency Platform Database**
  (`AgencyPlatformDB`), started automatically, as `NetworkService`;
- its superuser password is generated, used once to create the application's
  own account, and then deleted. Nobody types it and nobody needs it;
- its logs are `C:\ProgramData\Agency Platform\logs\database\postgresql-YYYY-MM-DD.log`.

It listens on this PC only, unless you tick **Allow other PCs on this network
to connect** during setup (section 5.1), in which case it also accepts this
PC's own private network(s) and nothing else (`pg_hba.conf`).

The application's database account is created for you: a login called
`agency_app` that is **not** a superuser and owns one database,
`agency_platform` (sourced: `install/install.ps1`,
`backend/app/core/database/bootstrap.py`).

An installation made by an earlier setup program, against a PostgreSQL you
installed yourself, keeps using that PostgreSQL when it is upgraded: setup
reads where it is from `config\.env` and does not move the data.

---

## 5. Install the server

### 5.1 Run the setup program

It needs 64-bit Windows 10 or 11, at least 4 GB of memory and 3 GB of free
disk, and refuses to start otherwise. It needs no internet connection.

1. Copy `AgencyPlatform-1.0.0-Setup.exe` to the server and double-click it.
2. SmartScreen warns about an unknown publisher. Click **More info**, then
   **Run anyway** (see [Read this first](#read-this-first-what-has-and-has-not-been-proven)).
3. Accept the administrator prompt. Setup needs administrator rights.
4. Accept the default folder, `C:\Program Files\Agency Platform`, or choose
   another with **Browse**. When you upgrade later, setup reuses whatever folder
   you pick now.
5. **This PC**: choose **This PC: server and app**. Tick **Allow other PCs on
   this network to connect** if other PCs will use this server; it is off by
   default, and without it the server answers this PC only.
6. Setup shows "Setting up the database and the server..." while it creates the
   database, writes `config\.env`, builds the platform tables, checks that the
   database holds no firm (a fresh install must find none, or it stops), and
   registers the server as the Windows service **Agency Platform Server**
   (`AgencyPlatformServer`). The service starts automatically, restarts itself
   after a failure, and runs as its own least-privilege account,
   `NT SERVICE\AgencyPlatformServer`. With the box ticked it listens on the
   network and Windows Firewall gets one rule: inbound TCP 8000, private
   networks only. Setup then waits up to 90 seconds for the server to answer.
7. **If that worked**, the last page shows the first administrator's sign-in
   and password, with a **Copy** button. They are also saved in
   `C:\ProgramData\Agency Platform\first-login.txt`, readable by administrators
   only; delete that file once the password has been changed at the first
   sign-in, which the application requires.

   **If it did not**, setup says so with the reason, the last page says the
   server is not set up, and **Launch Agency Platform** is not offered. **Run
   setup again** once the cause is fixed: it carries on from where it stopped.
   Everything it did, except the password, is in
   `C:\ProgramData\Agency Platform\logs\install\install-<version>-<date-time>.log`
   (the last ten runs are kept).

**Launch Agency Platform**, ticked on the last page, opens the client pointed at
`http://127.0.0.1:8000`. Sections 5.3 to 5.5 -- starting the server, starting it
automatically, the firewall -- are what setup has just done; they remain for an
installation made from a folder (section 11).

### 5.2 Check the settings, or finish by hand

Setup does all of this for you (section 5.1). Come here to check what it wrote,
to fix the two template lines below, or to do the database part by hand when
running setup again is not an option. Every command below is safe to repeat:
each checks first and does only what is missing.

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

The file sets no version (the program's own is used) and names no second
database server; the `AGENCY_TENANCY_CONNECTION_PROFILES` example in it is
commented out. Uncomment and fill it in only when a firm is to keep its data on
another server ([section 7.2](#72-firms-that-keep-their-data-in-their-own-database)).
To edit the file, run Notepad as administrator.

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

- **`-SkipSync`** says not to run `uv sync`, a developer tool that is not
  installed here. The script also skips it by itself whenever
  `agency-server.exe` is beside it, so leaving the switch out does no harm; it
  is kept because it is what the installer passes.
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
2. On the **This PC** page, choose **App only: connect to a server on the
   network**. Setup installs no PostgreSQL, no server and no service.
3. On the **Server** page, type the server's address, for example
   `http://192.168.1.50:8000`. Setup asks it for `/health`; if nothing answers
   it says so and lets you keep the address anyway (the server PC may simply
   be off). The server must have been installed with **Allow other PCs on this
   network to connect** ticked.
4. Setup writes the address into `config\branding.json` beside the program, so
   it holds for **every Windows user** of the PC, and remembers it for the next
   upgrade.

**Changing the server later.** On the sign-in screen, click the **gear icon**
(*Application Settings*), type the address in **API URL** and click **Save**.
That choice is **per Windows user**, in
`%APPDATA%\.agency_platform\desktop_preferences.json`, and wins over the
address setup wrote (sourced: `desktop/lib/app.dart`, `resolveServerUrl`). An
address the client will not accept is refused with a message explaining why
(see [section 2.5](#25-network)).

**Before the sign-in screen**, the client shows *Connecting to server...* and
asks the server every 2 seconds for up to a minute. If it never answers, it
says *The Agency Platform Server service is not running* and offers **Retry**,
**Open logs folder**, and **Continue to sign-in** (to reach the gear and
correct a wrong address).

**`config\branding.json`** sits beside `agency_desktop.exe`, in
`C:\Program Files\Agency Platform\config\`. Besides `server_url`, it sets only
what the program displays: application and company names, logo and splash
images, the version shown, support e-mail and website, copyright, and the
sign-in screen colours (sourced: `desktop/config/branding.json`,
`desktop/lib/core/branding/branding_config.dart`). If a value in that file is
broken, the client falls back to built-in defaults and still starts.

**Client logs** go to
`C:\ProgramData\Agency Platform\logs\client\<Windows user>\client-YYYY-MM-DD.log`,
one file a day, kept 14 days; where that folder cannot be written, to
`%APPDATA%\.agency_platform\logs` instead. **Open logs folder** in Application
Settings opens `C:\ProgramData\Agency Platform\logs`.


---

## 7. First sign-in

**The first account** is `platform-admin@agency.local`.

**Its first password** is shown once: on the last page of the setup program
(section 5.1), or at the end of an `install.ps1` or `install.bat` run. If it was
not written down, it is `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` in
`C:\Program Files\Agency Platform\backend\config\.env`: open that file in
Notepad **run as administrator** and copy the value.

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

1. Ask users to close the client.
2. Run the new `AgencyPlatform-<version>-Setup.exe` on the server. It installs
   into the same folder without asking (`UsePreviousAppDir=yes`), does not ask
   **This PC** again, and **refuses to install an older version** over a newer
   one.
3. Before it replaces a single file, setup stops **Agency Platform Server** and
   backs up every store the server uses -- the platform store, the shared firm
   store and every firm with its own schema or database on this PC -- with
   `pg_dump`, to
   `C:\ProgramData\Agency Platform\backups\pre-upgrade-<old version>-<date-time>\`.
   **If any backup fails, the upgrade stops there and nothing is changed.** A
   firm whose store is on another server is named in the log and not backed up
   here: back that server up yourself.
4. It then replaces the program files, runs `agency-server migrate-all --yes`
   (every store, store by store, and a failure is named), starts the service
   and waits for it to answer. It does **not** re-create the database or
   generate new passwords: `config\.env` and the database are left as they are.
5. Update each client PC by running the same setup program there. It remembers
   the server address.

**An upgrade keeps your data**, and so does uninstalling: Add/Remove Programs
stops and removes both services and the firewall rule and removes the program,
then asks **Also delete all data (database, backups, logs)?**, with **No** as
the default. Answer **No** and a later install picks the data up where it was
left. **Yes cannot be undone.**

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
- **An unattended install (`/VERYSILENT`) cannot be given the PostgreSQL
  administrator account**, because that is typed on a setup page. On a fresh
  server it fails, with the reason in `setup-configure.log` and section 5.2 as
  the way through.
- **No Windows service and no scheduled tasks** are registered, whether for the
  server, retention or backups. Sections 5.4 and 10 give recommended tasks.
- **No backup or restore** ([section 9](#9-backups); `docs/BACKLOG.md` item 35).
- **No client-only installer.** Every client PC gets the server program too;
  choosing **A client** only stops setup from configuring it.
- **The server address is not set at install time.** Each Windows user on each
  PC types it into Application Settings.
- **Unused ProgramData folders.** `C:\ProgramData\Agency Platform\logs` and
  `storage` are created, but the configuration step never points
  `AGENCY_LOG_DIRECTORY` there. Logs go under `Program Files`, which is why the
  server needs administrator or SYSTEM rights.
- **A firm with its own database on the same server** needs `CREATEDB` on
  `agency_app`, which the installer does not grant. See section 7.2.
- **The Visual C++ runtime is not bundled,** and whether a new machine needs it
  is untested. See section 2.4.
