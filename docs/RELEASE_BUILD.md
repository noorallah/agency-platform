# Building a release

How a checkout becomes the one file a customer runs, and what that file is
allowed to contain.

This is the **build** document. `docs/INSTALL_GUIDE.md` is what a customer
reads, `docs/RUNNING.md` is for working on this, and `docs/HARDWARE_SIZING.md`
says what to run it on.

---

## The one command

```powershell
.\packaging\build_installer.ps1
```

From a repository where the desktop client has been built, that produces:

```
dist\windows\AgencyPlatform-1.0.0-Setup.exe
```

and nothing else the customer needs: it is fully offline, and carries its own
PostgreSQL. It runs six steps, and stops at the first failure rather than
producing something questionable:

| Step | What it does | Fails the build when |
| --- | --- | --- |
| Clean | empties `dist\staging` and `dist\redist` | — |
| Fetch | makes sure the three pinned build inputs are in the cache and match their SHA-256 (see below) | a download fails, or a file does not match its pinned hash |
| Compile | Nuitka builds `agency-server.exe` from `app\cli.py` | Nuitka missing, compile fails, or the binary cannot answer `--version` |
| Stage | copies the client, the compiled backend, the migrations, `.env.example`, `install.ps1` and `server_setup.ps1`, the trimmed PostgreSQL under `pgsql\` and WinSW under `service\`; `vc_redist.x64.exe` goes to `dist\redist` | the client is not built, or a named file is missing |
| Verify | `verify_release.ps1` inspects what was staged | source, secrets, tests or the dev toolchain reached the tree |
| Installer | Inno Setup compiles `AgencyPlatform-<version>-Setup.exe` | Inno Setup missing, or it reports success without producing the file |

### Switches

| Switch | Use |
| --- | --- |
| `-Version 1.2.3` | override `VERSION`. Normally omitted. |
| `-SkipInstaller` | stage and verify only; leaves `dist\staging` to look through. The only half that works without Inno Setup. |
| `-SkipCompile` | stage the backend as **readable Python source**. Fast, for working on the staging or installer steps. Never release a build made this way — the verify step is told to expect source and says so. |
| `-SkipVerify` | skip the release check. For debugging a staging problem only. |
| `-Jobs 2` | cap how many C compilations run at once. The build picks a number from free memory and prints it; this overrides that. |
| `-LowMemory` | trade build speed for peak memory. The answer when the build is *killed* rather than failing. |
| `-ClientDir <path>` | stage a desktop client built somewhere else -- a worktree that has not run `flutter build windows` itself. |
| `-CacheDir <path>` | where the build inputs are kept. Defaults to `$env:AGENCY_BUILD_CACHE`, then `%LOCALAPPDATA%\agency-build-cache`. |

### Build inputs, pinned and cached

Three things in the installer are not built from this repository. Each is
**pinned** in `packaging/build_installer.ps1` -- version, URL and SHA-256 --
downloaded **once** into the cache, outside the repository, and checked against
its hash on every build. A mismatch stops the build: it means the download was
corrupted or the publisher changed the file, and the pin is not to be moved
until somebody knows which.

| Input | Pinned | Why |
| --- | --- | --- |
| PostgreSQL | EDB Windows x64 binaries zip, **17.11-1** (340 MB) | the private database. Extracted once into the cache; staged without pgAdmin, StackBuilder, docs, symbols, headers or PostgreSQL's own `test_*` programs -- 135 MB left. |
| WinSW | **2.12.0**, `WinSW-x64.exe` | runs `agency-server.exe serve` as the service `AgencyPlatformServer`. 3.x is still alpha. |
| Visual C++ runtime | 2015-2022 x64, **14.44.35211** | the client and the compiled server need it. The versioned URL `aka.ms/vs/17/release/vc_redist.x64.exe` redirected to on 2026-09-24, because the aka.ms link moves with every Visual Studio release. Setup runs it only when the machine's runtime is missing or older. |

To move one forward, change the three values together and build once with
network access. The cache is shared by every checkout and worktree on the
machine; deleting it only costs the next build a download.

**Budget memory, not time.** This is the constraint that actually bites: the
compile was killed outright on a 16 GB machine with an IDE open, which leaves no
error to read and looks like nothing happened. Close what you can, or cap the
jobs.

---

## What has to be installed on the build machine

| Tool | Why | Install |
| --- | --- | --- |
| Python 3.14 + `uv` | the backend | already needed to work on this |
| Nuitka | compiles the backend | `cd backend; uv sync --group build` |
| A C compiler | Nuitka emits C | MSVC (Visual Studio Build Tools). Nuitka offers to fetch MinGW if none is found; `--assume-yes-for-downloads` accepts. |
| Flutter SDK | the desktop client | `cd desktop; flutter build windows --release` |
| Inno Setup 6.3+ | the installer | `winget install --id JRSoftware.InnoSetup` (a per-user winget install under `%LOCALAPPDATA%\Programs` is found too) |
| Internet, once | the build inputs above | only when the cache does not have them yet |

`uv sync --group build` is deliberately separate from `--group dev`. The build
group belongs on a build machine; the dev group belongs on a developer's; and a
customer machine gets **neither** — `uv sync` with no group is what the
installer and `start_backend.ps1` run, and it takes only the runtime
dependencies.

---

## One version, declared once

`VERSION` at the repository root is the source. Everything else is stamped from
it, and `backend/tests/unit/test_version_is_declared_once.py` fails the build
when any of them disagrees:

- `desktop/pubspec.yaml` — feeds the client exe's own FileVersion through CMake
- `desktop/config/branding.json` — the version a user actually reads
- `backend/pyproject.toml` — the Python package
- `Settings.app_version` → `GET /health` → `agency-server --version`

Six places carried a version before 2026-09-17 and none agreed. The OpenAPI
version is deliberately not among them: it answers "which version of the HTTP
contract is this", which moves on its own schedule.

To cut a release, change `VERSION`, run the stamp, and build.

---

## Why Nuitka

The goal is that **a customer cannot easily read the implementation**. The
question was posed as "Java ships JARs — what is the Python equivalent?", and
the instructive part of that comparison is that a JAR does not protect Java
source either: bytecode decompiles almost perfectly, which is why shops that
care run ProGuard over it.

| Java | Python | Protection |
| --- | --- | --- |
| `.class` in a JAR | `.pyc` bytecode | weak — decompiles close to the original |
| JAR + ProGuard | PyArmor and similar | moderate, reversible with effort |
| Fat JAR / launcher exe | PyInstaller, cx_Freeze | weak — the archive extracts, leaving `.pyc` |
| **GraalVM native-image** | **Nuitka** | strongest available — real machine code |
| client–server | hosted backend | the only actual protection |

Nuitka translates Python to C and compiles it: there is no `.pyc` inside to
extract and no decompiler that recovers the source. Every other row leaves the
logic one tool away from being read.

`--standalone`, not `--onefile`: a onefile build unpacks itself to a temporary
directory on every start, which costs seconds each time and puts the whole
application somewhere world-readable while it runs — the opposite of the point.

### What is **not** claimed

- **Nuitka is not protection against a determined party.** It raises the cost
  of casual reading and copying substantially. It does not prevent reverse
  engineering, and this document will not be written as though it does.
- **The database is on the customer's machine.** Schema and data are readable
  by any administrator there whatever happens to the Python.
- **The durable answer, if this ever matters commercially, is hosting.** This
  product already has a client–server split; the backend merely *happens* to
  run on the customer's machine. That is a deployment choice, not an
  architectural one. Moving it to a server the vendor controls protects the
  logic completely and no compiler comes close. It is not available today — the
  product is deliberately on-premises and LAN-first, with no guaranteed
  internet — so this is a backlog item, not a change.

### The Nuitka options

`packaging/nuitka.args`, one per line, comments stripped by the build script.
They live in a file so that a change to how the product is compiled is a diff
somebody can read rather than a line buried in PowerShell.

The entries worth understanding are the ones a compiler cannot work out for
itself:

- `--include-module=openpyxl` — imported **lazily, inside functions, behind
  try/except**. A bundler that follows imports statically drops it, and the
  failure is at runtime on a customer machine rather than at build time.
- `--include-package=psycopg_binary` — `psycopg[binary]` loads `libpq`,
  `libssl` and `libcrypto` from it by a mangled name at import. Following
  `import psycopg` alone does not reach them; the symptom is *"no pq wrapper
  available"* on first connect.
- `--include-package-data=reportlab` — 32 font data files. Without them every
  PDF fails to render.
- `--include-package=alembic` — the migration path imports it in-process.

---

## The three things that had to change for this to be possible

Recorded here because each was a real obstacle, and because the reasoning is
what stops them being undone.

**1. Firm provisioning used to shell out to `python -m alembic`.** In a
compiled build `sys.executable` is the application and there is no `alembic`
module to hand it, so **creating a firm would have failed** — the one flow a
customer performs unaided. It runs in-process now, through `upgrade_store` in
`app/core/tenancy/migrations.py`, with the target passed on Alembic's
`Config.attributes` rather than through `os.environ`. See
`docs/TENANCY_AND_STORES.md`; the short version is that the environment, not
the subprocess, was the actual problem, and it must not come back.

**2. There is now one entry point, `backend/app/cli.py`.** Everything an
installed copy does is a subcommand of it — `serve`, `create-database`,
`migrate-all`, `firm-count`, `purge-retention`, `where`, `--version` — so there is one thing
to compile rather than seventeen scripts. `install.ps1` used to hold a Python
program in a here-string and pipe it into the interpreter on stdin, which
cannot work where there is no interpreter; that program is now
`app/core/database/bootstrap.py`.

`backend/tests/unit/test_cli_entry_point.py` pins every command line the
shipped scripts write, and fails the build if either of them reaches for
`-m alembic`, `-m uvicorn` or a `.py` by path again.

**3. Migrations stay as source, deliberately.** Alembic loads them by path at
runtime — it scans the directory and calls `spec_from_file_location` per file —
and 49 of the 135 import from `app.…`. They ship as `.py`, and
`verify_release.ps1` exempts `alembic\versions\` explicitly.

That is acceptable and worth stating plainly: a migration is schema DDL, and
the customer's own PostgreSQL exposes that same schema to anyone who looks at
it. `sourceless = true` would allow `.pyc` instead — bytecode, trivially
decompiled, and not worth the fragility.

---

## What Setup does

`packaging/AgencyPlatform.iss` places files and asks one question; everything
done to the machine itself is `packaging/server_setup.ps1`, whose exit code and
output the `.iss` reads, and which calls `install.ps1 -ConfigureOnly` for the
configuration rather than repeating it.

| When | What |
| --- | --- |
| Before anything | refuses anything but 64-bit Windows 10/11, less than 4 GB of memory or 3 GB free on the system drive, and a **downgrade** (the installed version is read from the uninstall key) |
| The question | **This PC: server and app** (default), with **Allow other PCs on this network to connect** (default off), or **App only**, which asks for the server's address and tests its `/health` |
| Server, fresh | `initdb` into `C:\ProgramData\Agency Platform\pgdata` with a generated superuser password (a pwfile, deleted after; kept admin-only in `setup-superuser.tmp` only until configuration succeeds, so a re-run can finish a failed one); port 5433, `localhost` or also this PC's private subnets; logs to `logs\database\postgresql-%Y-%m-%d.log`; `pg_ctl register` as `AgencyPlatformDB` (NetworkService, automatic). Then `install.ps1 -ConfigureOnly -RequireNoFirms`: `.env` for localhost:5433 with `AGENCY_LOG_DIRECTORY` under ProgramData, `create-database`, `migrate-all --yes`, `firm-count` which must print 0. Then WinSW registers `AgencyPlatformServer`, `sc.exe` moves it to the virtual account `NT SERVICE\AgencyPlatformServer` with failure restarts at 10/30/60 s and a dependency on `AgencyPlatformDB`, the firewall rule (TCP 8000, private profile) if the box was ticked, and a wait of up to 90 s for `/health`. The sign-in goes to the finished page (with **Copy**) and to `first-login.txt`, Administrators and SYSTEM only |
| Server, upgrade | **before any file is replaced**: stop the service, `pg_dump -Fc` every store `migrate-all --dry-run` lists on this PC to `backups\pre-upgrade-<old>-<stamp>\`, stop the database; a failed dump stops the upgrade with nothing changed. After: no initdb, no new password -- start the database, `migrate-all --yes`, start the service, check `/health` |
| App only | writes `server_url` into `{app}\config\branding.json`; no PostgreSQL, no backend, no service |
| Either | installs the bundled Visual C++ runtime when the machine's is missing or older |
| Uninstall | stops and removes both services and the firewall rule, removes the program, and asks *Also delete all data (database, backups, logs)?*, default **No** |

**Why a virtual account for the server.** `NT SERVICE\AgencyPlatformServer`
exists only for this service, has no password to manage, and can touch only
what Setup grants it: modify on `logs\` and `storage\`, read on `config\.env`.
WinSW itself installs services as LocalSystem, so Setup changes the account
afterwards with `sc.exe config obj=`, which is Windows' own documented route and
needs nothing from WinSW. The database runs as NetworkService, as the PostgreSQL
project's own installer does.

Every run writes
`C:\ProgramData\Agency Platform\logs\install\install-<version>-<yyyymmdd-HHmmss>.log`
-- Setup's own lines, everything the scripts printed, and Inno Setup's log
appended at the end -- and keeps the last ten. The administrator password never
reaches it.

## What an install creates

**In the database: the platform store and nothing else.** A fresh install runs
`create-database` then `migrate-all --yes`, and with no firm registered
`migrate-all` migrates the `platform` schema alone and prunes it down to the
platform tables, `alembic_version` and `audit_logs` (whose append-only trigger
stays). There is no `firm_shared` schema and no firm. The platform seed -- the
system permissions and roles, the bootstrap administrator, the job templates --
is written by the migrations into platform tables and is all there.

`firm_shared` is built when the first SHARED firm is created (or provisioned),
through the same path that builds a dedicated firm's store; that is also when
the business profiles, units and other reference data reach it, because they
are firm-store seed. An **upgrade** -- a database that already holds firms --
migrates every store, as it always did.

`agency-server firm-count` prints the number of live firms and exits 0; it
prints 0 on a database whose platform schema has not been migrated yet, and
exits 2 rather than printing anything when the server cannot be read. The
installer uses it to refuse a fresh install onto a database that already holds
firms. `docs/TENANCY_AND_STORES.md` has the detail.

**On disk: one log folder.** The installer sets `AGENCY_LOG_DIRECTORY` to
`C:\ProgramData\Agency Platform\logs`, and the server writes to its `server`
subfolder: `server-YYYY-MM-DD.log` and `errors-YYYY-MM-DD.log` (WARNING and
above), a new file each midnight and a numbered part at 50 MB within a day.
Files from before yesterday are gzipped, server logs are kept 30 days and error
logs 90 (`AGENCY_LOG_RETENTION_DAYS`, `AGENCY_LOG_ERROR_RETENTION_DAYS`), and the
whole folder is capped at 1 GB (`AGENCY_LOG_MAX_TOTAL_MB`), oldest files first.
The server applies that at startup and hourly, and `purge-retention --yes` does
too. `docs/LOGGING.md` has the detail.

**The customer guide travels with the installer.** Staging renders
`docs/INSTALL_GUIDE.md` -- the one source, which the guard tests also read --
into `Installation guide.html` with `packaging/render_guide.py` (the `markdown`
package, from the `build` group). It is staged at the root of the payload rather
than under `docs\`, because the release check treats a `docs` folder as
repository-only; Setup gives it a Start menu entry, and the build copies it to
`dist\windows\` beside `Setup.exe` so the two are handed on together. Links
between repository documents are reduced to their text, since nothing they
point at is beside a customer's copy.

---

## The release check

`packaging/verify_release.ps1` is what makes "no source, no secrets, no
development files" a fact about the build rather than an intention. It exits
non-zero and the build stops before producing an installer.

It refuses a tree containing:

1. any `.py` outside `alembic\` -- the whole directory, not just `versions\`; see below
2. any `.env` that is not `.env.example`
3. `tests`, `docs`, `.git`, `.github`, `.venv`, `__pycache__`, `Dockerfile`,
   `docker-compose.yml`, `uv.lock`, `.coverage`, `.pytest_cache`, `.mypy_cache`
4. mypy, pytest, black, ruff or coverage anywhere in the bundle
5. the known development passwords: `DemoAdmin@12345`, `Fixture@2026pw`,
   `Password@123`
6. seeders, demo tooling, fixtures and tests, **by name whatever the
   extension**: `generate_sample_data`, `generate_transaction_history`,
   `seed_multi_firm_demo`, `seed_tax_sample_data`, `seed_finance_defaults`,
   `verify_sample_data`, `reset_tenancy_layout`, `conftest`, anything with
   `fixture` in its name, and `test_*` / `*_test`. Unlike check 1 it stays on
   under `-SkipCompile`. It is why the staged PostgreSQL drops its own
   `test_cloexec.exe` and `test_decoding.dll`.

It is runnable on its own against any directory, which is the point — pointing
it at an *installed* copy on a customer machine answers "what did we actually
give them" without reading a build log:

```powershell
.\packaging\verify_release.ps1 -Path "C:\Program Files\Agency Platform"
```

**Alembic is the exception, and it is two things rather than one.** The
migrations under `alembic\versions\` were the expected one: Alembic
loads them by path at runtime. `alembic\env.py` is the one the first
compiled build found -- Alembic *executes* it, through
`ScriptDirectory.run_env()`, so without it `command.upgrade` cannot run and
**provisioning a firm fails on the customer's machine**, which is the one flow
they perform unaided. Both are schema plumbing rather than business logic, and
the customer's own PostgreSQL exposes that same schema to anyone who looks.
Nothing else may be source.

**Why the development JWT key and bootstrap password are not in the secret
list.** They are the values the application *refuses* outside development — it
compares against them to fail fast — and the template the installer rewrites.
They are guard rails, not credentials, and failing the build on them would
teach whoever met it to weaken the check.

---

## Signing

**Not enabled, and not configured in this repository.** Two things are needed
before it can be:

- an Authenticode code-signing certificate, supplied from outside the
  repository. **The certificate and its private key are never committed**, and
  no path to one is hard-coded here.
- the legal company name the certificate is issued to, which must match
  `AppPublisher` in `packaging/AgencyPlatform.iss` and `--company-name` in
  `packaging/nuitka.args`.

Until then, Windows SmartScreen will warn on first run of the installer. That
is the honest state: an unsigned installer is an unsigned installer, and
telling a customer to click through a warning is a cost of not having signed
it, not a defect to explain away.

When a certificate exists, signing belongs on two files — `agency-server.exe`
after Compile and the setup executable after Installer — driven by a
`SIGNING_ENABLED`-style switch that defaults to **off**, so an unsigned build
remains the default rather than a build failure on a machine with no
certificate.

---

## Testing a release

In order, because each step is cheaper than the next and catches different
things.

1. **`-SkipCompile -SkipInstaller`** — staging and the release check, in
   seconds. Catches a file that should not ship.
2. **A full build** — compile included. Catches a module Nuitka could not find,
   which is most of what goes wrong.
3. **Install it on a machine you can rebuild** -- since round 1 Setup creates
   services, a firewall rule and a database cluster, so a development machine is
   no longer a harmless place to try it. Confirm both services in
   `services.msc`, the Start Menu entry, Add/Remove Programs showing the
   publisher and version, and that the client reaches the backend.
4. **Install a newer build over the top.** A `backups\pre-upgrade-*` folder
   appears with one dump per store; `config\.env`, `pgdata\`, `logs\` and
   `storage\` survive; no new password is shown.
5. **Uninstall**, once answering **No** and once **Yes**. With No the program
   and both services go and the data stays; with Yes `C:\ProgramData\Agency
   Platform` goes too.
6. **A clean virtual machine with no Python** — `where python` finds nothing.
   This is the only test that proves the compile was worth doing, and the only
   one that catches a dependency the build machine happened to have.

Steps 1 to 3 were run for the first time on 2026-09-17, and what they produced
is worth recording so the next person knows what normal looks like:

| | |
| --- | --- |
| C files Nuitka generated | 1,909 |
| `agency-server.exe` | 153.6 MB |
| staged tree, client included | 240.1 MB |
| release check | passed, once `alembic\env.py` was exempted |
| `agency-server.exe --version` | `1.0.0` |
| `migrate-all --dry-run` | reached PostgreSQL through the bundled `psycopg_binary` and read all eight stores |

The staged backend contains **no `app\` directory at all** -- the 454 source
files are inside the executable. That is the whole point of this, stated as a
thing somebody can check rather than a claim.

**Budget hours, not minutes, on a machine that is also being used.** That build
took most of a day at two parallel jobs, and was killed twice before being run
under Task Scheduler, where the CLI's own watchdog could not reach it.

**`sys.frozen` is not how you detect a compiled build.** PyInstaller sets it;
**Nuitka does not**. The first build printed `frozen: False` from
`agency-server.exe`, which meant every branch written for a built copy was dead
in one -- `application_root()` returned the right answer only because Nuitka
keeps `__file__` pointing at the layout beside the executable, and
`serve --reload` had silently lost its guard. Nuitka's marker is
`__compiled__`; `app/core/paths.py::is_compiled_build` asks for both, and
`test_cli_entry_point.py` fails the build if anybody reaches for one again.

Step 6 has not been run yet. Until it has, this document should not be read as
saying the product installs on a machine with no Python; it says the build is
arranged so that it can, and that everything up to that point has been done.

---

## What goes wrong, and what it looks like

| Symptom | Cause |
| --- | --- |
| `no pq wrapper available` on first connect | `psycopg_binary` and its DLLs did not reach the bundle |
| A report fails only in the built copy | `reportlab`'s font data, or `openpyxl`, which is imported lazily |
| Creating a firm fails with a migration error | `alembic\versions\` did not reach the install, or `alembic.ini` is not beside the executable |
| The binary starts and exits silently | run it from a console with `where`; `agency-server where` prints the version, environment and the directory it thinks it is installed in |
| Nuitka cannot find a C compiler | install MSVC Build Tools, or let it fetch MinGW |
| The build stops with no error at all | **It was killed, not failed** — Windows ended it for memory. Nuitka runs one C compilation per core and each is most of a gigabyte; on a 16 GB machine with an IDE open that is enough to exhaust it. The build caps the job count from free memory and says so, but `-Jobs 2` and `-LowMemory` are there when that is not enough. |
| PowerShell aborts mid-build with `NativeCommandError` | Windows PowerShell 5.1 wraps native stderr in an ErrorRecord, and `$ErrorActionPreference = 'Stop'` aborts on the first one. The build script relaxes it around the compile for exactly this; `start_backend.ps1` documents the same trap. |

`agency-server where` exists for the fourth row. A built copy that will not
start is otherwise very hard to ask anything of.
