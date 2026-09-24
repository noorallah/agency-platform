# Installing the Agency Platform

For the person installing the system at a firm. It assumes no knowledge of
databases or the command line: every step says what to click and what you
should see. The short appendix at the end is for IT staff.

Developers: [`RUNNING.md`](RUNNING.md) is a working copy,
[`RELEASE_BUILD.md`](RELEASE_BUILD.md) is how this installer is built.

Checked against the repository on **2026-09-24**, version `1.0.0` (`VERSION`).

---

## 1. Before you start

One file, `AgencyPlatform-1.0.0-Setup.exe`, installs everything. It needs no
internet connection and downloads nothing: PostgreSQL, the server and the app
are all inside it.

**One PC is the server.** It keeps all the data and runs the server as a
Windows service. Every other PC runs only the app and connects to the server
over the office network. In a one-person office the server PC is the only PC.

| The PC | Needs |
| --- | --- |
| Server PC | 64-bit Windows 10 or 11, 4 GB memory (8 GB comfortable), 3 GB free disk (the install takes about 500 MB, the data grows from there), a power plan that never sleeps, an administrator account to install |
| Every other PC | 64-bit Windows 10 or 11, 4 GB memory, 300 MB free disk, a screen of 1366 × 768 or larger, an administrator account to install only |
| The network | The server PC reachable on TCP port 8000. Setup opens the Windows firewall for it when you ask it to |

Setup refuses to run on a PC with less than 4 GB of memory or less than 3 GB
of free disk, and says so.

**Windows will warn you.** This first release is not yet signed with a
publisher certificate, so when you start Setup, Windows SmartScreen shows
*Windows protected your PC* with an unknown publisher. Click **More info**,
then **Run anyway**. Then answer **Yes** to the administrator prompt. Nothing
else about the install is affected.

**Do not install on a PC that already has PostgreSQL on port 5433.** Setup
brings its own copy of PostgreSQL 17 and runs it on port 5433, so a normal
PostgreSQL installation on 5432 is left alone.

---

## 2. Install the server PC

Install the server PC first. The whole run takes about five minutes, most of
it on the last page.

1. Run `AgencyPlatform-1.0.0-Setup.exe`, get past SmartScreen (**More info**,
   **Run anyway**) and answer **Yes** to the administrator prompt.
2. **Destination**: leave it at `C:\Program Files\Agency Platform`, or choose
   another folder. Only the program goes there; the data and the logs always
   go under `C:\ProgramData\Agency Platform`, whatever you choose here.
3. **This PC**: choose **This PC: server and app**. Tick **Allow other PCs on
   this network to connect** if anyone else will use the system from another
   PC. Without the tick, the server answers only this PC and the firewall
   stays closed. You can add it later by running Setup again.
4. **Shortcuts**: leave *Create a desktop shortcut* ticked.
5. Click **Install**. Setup copies the files, installs the Microsoft Visual
   C++ runtime if the PC lacks it, and then shows *Setting up the database and
   the server. This can take a few minutes.* It creates the private PostgreSQL
   database, generates its passwords, registers two Windows services and waits
   until the server answers.
6. **The finished page shows the first sign-in.** Write it down or click
   **Copy**:
   - Sign in as: `platform-admin@agency.local`
   - Password: generated for this installation, shown once here

   The same details are saved in
   `C:\ProgramData\Agency Platform\first-login.txt`, which only administrators
   of the PC can open. Delete that file once the password has been changed.
7. Leave *Launch Agency Platform* ticked and click **Finish**. The app opens
   on the sign-in screen.

Setup registered two services that start with Windows and restart themselves
if they stop:

| Service | What it is |
| --- | --- |
| Agency Platform Database | PostgreSQL 17, private to this product, on port 5433 |
| Agency Platform Server | The server the apps connect to, on port 8000. It starts after the database |

**If the last page says the server could not be set up**, the files are
installed but nothing runs yet. The page names the reason and the log file.
Fix the reason and run the same Setup again: it is safe to repeat, it
continues from where it stopped, and its finished page shows the sign-in
again, because nobody has been able to change the password yet.

**Passwords you never see.** The database passwords are generated and stored
in `backend\config\.env` under the program folder, readable by administrators
only. Nobody needs to type them.

---

## 3. Install the app on every other PC

Find the server PC's address first. On the server PC, open a command prompt
and type `ipconfig`; the *IPv4 Address* line, for example `192.168.1.50`, is
what the other PCs connect to. The server must have been installed with
**Allow other PCs on this network to connect** ticked.

1. Run the same `AgencyPlatform-1.0.0-Setup.exe` on the other PC, past
   SmartScreen and the administrator prompt.
2. **This PC**: choose **App only: connect to a server on the network**.
3. **Server**: type the server's address with the port, for example
   `http://192.168.1.50:8000`. Setup checks that the server answers. If
   nothing answers, it says so and lets you keep the address anyway, because
   the server PC may simply be off.
4. Click **Install**, then **Finish**. The app opens and connects to that
   server.

No database and no service is installed on an app-only PC. The address is
remembered for every Windows user of that PC and for the next upgrade.

**Changing the server address later.** On the sign-in screen, click the gear
icon (*Application Settings*), type the address in **API URL** and click
**Save**. That choice is per Windows user and wins over what Setup wrote.
Plain `http://` is accepted only to an address on your own network; anything
reached over the internet needs `https://` (see the appendix).

---

## 4. First sign-in and the first firm

Sign in as `platform-admin@agency.local` with the password from the finished
page. The app asks you to change it at once, and the old one stops working
from then on.

The new password needs at least 12 characters with an uppercase letter, a
lowercase letter, a digit and a symbol, and may not repeat any of the
account's last five. Five wrong passwords in a row lock an account for 15
minutes.

**A fresh install holds no firm.** The platform administrator belongs to no
firm, so every business screen stays closed until a firm exists and people
are added to it:

1. Open **Firms** and create the firm: its name, code, GST number and address.
2. Open the firm's **Set up** panel. It lists what the firm still needs before
   it can trade: open books, the GST template, control accounts and the
   default branch, each with a button.
3. Create the firm's people under **Users**, give each a role, and add them to
   the firm.
4. Sign out. From now on, everyday work is done by those people, not by the
   platform administrator.

Every PC signs in with its own user account; the platform administrator's is
for administration only.
[`platform-administration-guide.md`](platform-administration-guide.md) walks
through firms, roles and users in detail.

---

## 5. Where everything lives

The program is under Program Files and never changes while running.
Everything that changes, the database, the logs and the backups, is under
`C:\ProgramData\Agency Platform`.

| What | Where |
| --- | --- |
| The app and the server | `C:\Program Files\Agency Platform` |
| The database files | `C:\ProgramData\Agency Platform\pgdata` (managed by PostgreSQL, not files you handle) |
| All logs | `C:\ProgramData\Agency Platform\logs` (Start menu: **Agency Platform logs**) |
| Pre-upgrade backups | `C:\ProgramData\Agency Platform\backups` |
| Attachments | `C:\ProgramData\Agency Platform\storage` |
| The first sign-in | `C:\ProgramData\Agency Platform\first-login.txt` (administrators only, delete once used) |
| Server settings and passwords | `C:\Program Files\Agency Platform\backend\config\.env` (administrators only) |

**Every log is in one folder, and cleans itself up.** Nothing in `logs` needs
tending: each part writes one file a day and removes its own old files.

| Folder under `logs` | Written by | Kept |
| --- | --- | --- |
| `install` | Each Setup run, one file per run | The last 10 runs |
| `server` | The server, one file a day plus a separate errors file | 30 days, errors 90 days, and never more than 1 GB in total |
| `service` | The Windows service wrapper around the server | 8 files of 10 MB |
| `database` | PostgreSQL, one file a day | Rotated daily by PostgreSQL |
| `client\<Windows user>` | The app, one file a day per user of the PC | 14 days |

On an app-only PC only `install` and `client` exist. **Open logs folder** on
the app's connecting screen and in Application Settings opens the same folder.

---

## 6. Upgrading, backups and uninstalling

**Upgrading** is running the newer Setup on the server PC, then on each
app-only PC. Ask everyone to close the app first.

1. Setup installs into the same folder without asking, and does not ask
   *This PC* again.
2. Before it replaces a single file it stops the server and backs up every
   database to
   `C:\ProgramData\Agency Platform\backups\pre-upgrade-<old version>-<date>`.
   If that backup fails, the upgrade stops there and nothing has changed.
3. It then replaces the program, upgrades the database, starts the server
   again and waits for it to answer. Passwords and settings are kept; the
   finished page says *Sign in as before*.
4. Setup refuses to install an older version over a newer one, because the
   database has already moved past what the older version understands.

**Backups are your job in this release.** The only backup the product takes
is the one before an upgrade. Until a scheduled backup ships, copy the whole
of `C:\ProgramData\Agency Platform` to another drive or PC regularly, with
the two services stopped, plus a copy of
`C:\Program Files\Agency Platform\backend\config\.env`. A backup contains
passwords and sign-in tokens, so keep it where only administrators can reach
it. A backup is only proven once it has been restored; try that once on a
spare PC.

**Uninstalling** is *Agency Platform* in **Add or remove programs**. It stops
and removes both services and the firewall rule, removes the program, and
then asks *Also delete all data (database, backups, logs)?* with **No** as
the default. Answer **No** and a later install picks the data up exactly
where it was left. **Yes cannot be undone.**

---

## 7. When something goes wrong

**The app shows *Connecting to server…* and then *The Agency Platform Server
service is not running*.** The app asks the server every two seconds for up
to a minute before saying this. On the server PC, open **Services** (type
*services* in the Start menu), find **Agency Platform Server** and click
**Start**; if it will not stay started, restart the PC. The screen offers
**Retry**, **Open logs folder** and **Continue to sign-in**, the last of which
reaches the gear icon so a wrong address can be corrected.

**The app on another PC cannot connect, but the app on the server PC can.**
The server was installed without **Allow other PCs on this network to
connect**. Run Setup again on the server PC and tick it. Also check that both
PCs are on the same network and that the address typed matches the server's
`ipconfig` address.

**Setup's last page says the server could not be set up.** Read the reason on
the page, then the newest file in
`C:\ProgramData\Agency Platform\logs\install`, which records every step of
that run. `C:\ProgramData` is a hidden folder, so paste that path into the
Explorer address bar or the Run box rather than browsing to it; the logs are
never under the program folder. Fix the cause and run Setup again; its
finished page shows the sign-in again.

**The password from the finished page was lost.** It is in
`C:\ProgramData\Agency Platform\first-login.txt` until the first sign-in
changed it. Open that file as an administrator.

**Which log to read**

| Symptom | Log |
| --- | --- |
| Setup failed or the server never started after install | `logs\install\<newest file>` |
| The server stops or answers with errors | `logs\server\<today's file>` and the errors file beside it |
| The service starts and stops at once | `logs\service` |
| The database will not start | `logs\database\postgresql-<today>.log` |
| The app misbehaves on one PC | `logs\client\<that Windows user>` on that PC |

When you ask for help, send the newest file from the folder that matches, and
the version shown on the sign-in screen.

---

## 8. What this first release does not do yet

- **It is unsigned.** SmartScreen warns and the publisher reads *Agency*
  until a certificate and the final company name are in place.
- **No scheduled backup.** Only the pre-upgrade backup is automatic. Copy the
  data folder yourself until a backup job ships.
- **No licence.** This build runs without one. Licensing arrives in a later
  release and will not disturb an installed copy.
- **Old database rows are not pruned automatically.** Sign-in history and the
  tax calculation log grow until an administrator runs the retention job
  (appendix); the server holds its own log files to 1 GB, but the database is
  not capped.
- **This is the first build to be installed anywhere.** It has been checked
  against the files it is built from, not yet on a customer's PC. Install it
  on a PC you can rebuild, and keep the install log.

---

## Appendix for IT staff

Everything here is optional. The commands run on the server PC in a
PowerShell window opened **as administrator**, from the backend folder:

```powershell
cd "C:\Program Files\Agency Platform\backend"
```

**What the server thinks it is.** `.\agency-server.exe where` prints the
version, the environment and the folder it runs from. `.\agency-server.exe
migrate-all --dry-run` lists every database the server uses and the revision
each is at. Try both first when the server will not start.

**Pruning old database rows.** The database keeps sign-in history, expired
sign-in tokens, old password history, the tax engine's calculation log and
error reports. Nothing removes them unless you run this:

```powershell
.\agency-server.exe purge-retention --dry-run   # report what would go
.\agency-server.exe purge-retention --yes       # delete it
```

By default it keeps sign-in history and the tax log for 365 days, error
reports for 90 days, expired tokens for 7 days and the last 10 passwords per
user; each has a switch, for example `--login-history-days 180`. The audit
trail is never pruned. To run it nightly, register a Task Scheduler task as
SYSTEM with the backend folder as its working directory.

**HTTPS.** Plain HTTP is fine on an office network you control, because the
app refuses `http://` to any address that is not private. On any other
network, give the server a certificate: stop **Agency Platform Server**, open
`C:\Program Files\Agency Platform\service\AgencyPlatformServer.xml` as an
administrator, add `--ssl-certfile C:\certs\erp.crt --ssl-keyfile
C:\certs\erp.key` to the `<arguments>` line, and start the service again.
Both files are required; the server refuses to start with only one. Every app
PC must trust the certificate, so a self-signed one has to be imported into
each PC's Windows certificate store. Setup rewrites that XML on the next
upgrade, so repeat the edit afterwards.

**A firm on its own database or another server.** By default every firm's
data lives in the private database and needs nothing more. A firm can be
given its own schema, its own database, or a database on another server, and
its storage is then built with **Provision storage** on the Firms screen
([`TENANCY_AND_STORES.md`](TENANCY_AND_STORES.md)). A database on another
server needs a connection profile in `AGENCY_TENANCY_CONNECTION_PROFILES` in
`backend\config\.env`, naming that server's host, port, user and password,
and the server must be restarted after the edit: it reads profiles only at
start, and until then refuses the new profile by name.

**Installing from a folder instead of Setup.** `install\install.bat` in the
repository installs against a PostgreSQL the customer already runs, without
the private database or the services. It is the developer's path and is not
described here; [`RELEASE_BUILD.md`](RELEASE_BUILD.md) covers it.
