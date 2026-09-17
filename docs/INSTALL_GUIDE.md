# Installing the Agency Platform

For the person setting the system up at a firm. It assumes no knowledge of
Python, PostgreSQL or the command line — every step says what to type, what you
should see, and what to do if you see something else.

If you are a developer setting up a working copy, read
[`RUNNING.md`](RUNNING.md) instead. This page is about installing the product on
the machine a firm will actually use.

---

## 1. What the machine needs

One Windows machine acts as the **server**. It holds the database and runs the
application. Everyone else runs the **client**, which talks to it over the
network and stores nothing of its own.

| | Minimum | Comfortable |
| --- | --- | --- |
| **Server** (small office) | 2 cores, 4 GB RAM, 128 GB SSD | 4 cores, **8 GB RAM**, 256 GB SSD |
| **Each client PC** | any 64-bit Windows, 4 GB RAM | — |

A mini PC with 8 GB, four cores and a 256 GB SSD serves a small office
comfortably. Disk is rarely the constraint: four firms with two years of trading
measured **294 MB**, and about 85% of that was logs rather than business data.

**Windows 10 or 11**, or Windows Server 2019 onwards.

**It does not need to be a powerful machine, but it does need to stay on.** The
server is what everyone else depends on; if it sleeps, the clients stop working.
Set the power plan so it never sleeps.

### Software — one thing, and the installer handles it

**PostgreSQL 17** is the only other software this needs, and the installer can
install it for you. If you would rather install it first, or your IT policy
requires it: <https://www.postgresql.org/download/windows/>

**Python is not needed.** The server ships as a single compiled program that
carries everything it needs. Nothing has to be downloaded for it, and nothing it
uses can be broken by something else on the machine changing its own Python.

> If you are following older notes that say Python 3.13 is required, they
> describe the way this was installed before it was packaged. A copy installed
> from `AgencyPlatform-Setup.exe` needs no Python at all.

---

## 2. Before you start

Have these three things decided:

1. **Where the application lives.** The default is `C:\AgencyPlatform`. Any
   folder will do; avoid `C:\Program Files`, which needs extra permissions for
   every update.
2. **Whether other machines connect to it.** If the server is used only by the
   person sitting at it, nothing more is needed. If others connect, see
   [section 6](#6-letting-other-machines-connect).
3. **Who the first administrator is.** You get a password for them at the end;
   write it down somewhere safe before you close the window.

You do **not** need to choose a database password. The installer creates the
database account and its password, and you never see or type it.

---

## 3. Installing

Extract the folder you were given, open it, and **double-click `install.bat`**.

A window opens and asks where to install:

```
Install where? [C:\AgencyPlatform, or a path of your own]:
```

Press **Enter** to accept the default, or type a folder and press Enter.

### What you should see

The installer reports each step as it finishes. A complete run looks like this:

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

== Done
   Sign in as: platform-admin@agency.local
   Password:   7hK2-mQp9vTx4Rn6
   Write that password down now. It is not shown again.
```

The client then opens at the login screen. **Sign in with the address and
password shown.** You will be asked to change the password on first use.

### It takes a few minutes

Installing PostgreSQL, if it is missing, is the slow part. Ten to fifteen
minutes on a fresh machine is normal. Nothing has gone wrong if a step
sits for a while.

---

## 4. Trying it first, changing nothing

To see exactly what would happen without touching the machine:

```
install.bat -DryRun
```

Every step is reported as "would…" and nothing is installed, created or
started. Safe to run on a machine already in use.

---

## 5. If something goes wrong

The installer stops at the first real problem and tells you what to do. It is
**safe to run again** — it checks each step and continues from where it stopped,
and running it on a working installation changes nothing.

| What it says | What it means | What to do |
| --- | --- | --- |
| `Prerequisites are missing.` | PostgreSQL is not installed | Run `install.bat -InstallPrerequisites` to let it install it |
| `Installing prerequisites needs an elevated shell.` | Installing software needs Administrator | Right-click `install.bat` → **Run as administrator** |
| `Could not reach PostgreSQL.` | The database is not running, or is elsewhere | The message lists the causes in the order worth checking |
| `One or more stores failed to migrate.` | A database upgrade did not finish | The output names which one. Fix, then run again |

If it stops with something not listed here, the last lines on screen name the
step and the reason. Keep that window open — it is the fastest route to an
answer.

---

## 6. Letting other machines connect

By default the server answers **only the machine it runs on**. To serve other
PCs in the office:

```
install.bat -BindHost 0.0.0.0
```

Then on each client PC, point the application at the server's address — for
example `http://192.168.1.50:8000`.

> **Plain HTTP sends passwords across the network in clear text.** On an office
> network you control, with no internet exposure, that is usually accepted. On
> any network you do not control, install with a certificate:
>
> ```
> install.bat -BindHost 0.0.0.0 -CertFile C:\certs\erp.crt -KeyFile C:\certs\erp.key
> ```
>
> Half a TLS setup is refused rather than quietly falling back to HTTP.

You may also need to allow port 8000 through Windows Firewall on the server.

---

## 7. Updating to a new version

Extract the new version somewhere — **not** over the top of the installed
folder — and run its installer pointed at the same place:

```
install.bat -InstallDir C:\AgencyPlatform
```

**Your data is not touched.** Three things at the destination are kept as they
are:

| Kept | Why it matters |
| --- | --- |
| `backend\config\.env` | The signing key and database password. Replacing it would sign every user out and lock the application out of its own data |
| `backend\logs\` | The record of what the application did, which is often the only evidence when something went wrong before the update |
| `backend\storage\` | Files attached to the firm's own records |

The **database is never touched by an update** — it lives inside PostgreSQL,
not in the installation folder. Updates only add to it, through the migration
step.

---

## 8. What to back up

Two things, and neither is optional:

1. **The PostgreSQL database.** This is the firm's entire business record.
2. **`backend\config\.env`.** It holds the signing key and the database
   password. Lose it and the application cannot open its own database.

> There is no automatic backup yet. Until there is, arrange one — a nightly
> copy of the database and that one file, kept off the machine.

---

## 9. Where things are

| | |
| --- | --- |
| The application | the folder you chose, e.g. `C:\AgencyPlatform` |
| Settings | `backend\config\.env` — restricted to administrators |
| Logs | `backend\logs\application.log` |
| The database | inside PostgreSQL, managed by it, not a file you handle |
| Starting the server by hand | `backend\scripts\start_backend.ps1` |

---

## 10. Common questions

**Do I need to be an administrator?**
Only to install PostgreSQL. If it is already installed, an ordinary account is
enough.

**Can I install it twice on one machine?**
Yes, into different folders — but they would share one PostgreSQL server, and
each needs its own database name (`-DatabaseName`). It is rarely what anyone
wants.

**What is the database password?**
Generated during installation, written to `backend\config\.env`, and never
shown. Nobody needs to type it. The file is restricted so that a standard user
on the machine cannot read it.

**Can I move the installation to another folder later?**
Install to the new place and restore the database. Moving the folder by hand
leaves paths pointing at the old one.

**Does it need the internet?**
Only to install PostgreSQL, and only if PostgreSQL is not already there. The
application itself downloads nothing at any point. Once installed it runs
entirely on your own network.
