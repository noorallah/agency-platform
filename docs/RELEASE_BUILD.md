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

and nothing else the customer needs. It runs five steps, and stops at the first
failure rather than producing something questionable:

| Step | What it does | Fails the build when |
| --- | --- | --- |
| Clean | empties `dist\staging` | — |
| Compile | Nuitka builds `agency-server.exe` from `app\cli.py` | Nuitka missing, compile fails, or the binary cannot answer `--version` |
| Stage | copies the client, the compiled backend, the migrations and `.env.example` | the client is not built, or a named file is missing |
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
| Inno Setup 6 | the installer | `winget install --id JRSoftware.InnoSetup` |

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
`migrate-all`, `purge-retention`, `where`, `--version` — so there is one thing
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

## The release check

`packaging/verify_release.ps1` is what makes "no source, no secrets, no
development files" a fact about the build rather than an intention. It exits
non-zero and the build stops before producing an installer.

It refuses a tree containing:

1. any `.py` outside `alembic\versions\`
2. any `.env` that is not `.env.example`
3. `tests`, `docs`, `.git`, `.github`, `.venv`, `__pycache__`, `Dockerfile`,
   `docker-compose.yml`, `uv.lock`, `.coverage`, `.pytest_cache`, `.mypy_cache`
4. mypy, pytest, black, ruff or coverage anywhere in the bundle
5. the known development passwords: `DemoAdmin@12345`, `Fixture@2026pw`,
   `Password@123`

It is runnable on its own against any directory, which is the point — pointing
it at an *installed* copy on a customer machine answers "what did we actually
give them" without reading a build log:

```powershell
.\packaging\verify_release.ps1 -Path "C:\Program Files\Agency Platform"
```

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
3. **Install it on this machine.** Confirm the Start Menu entry, Add/Remove
   Programs showing the publisher and version, and that the client reaches the
   backend.
4. **Install it again over the top.** `config\.env`, `logs\` and `storage\`
   must survive, and the database must be untouched.
5. **Uninstall.** The program goes; the database, the logs and the firm's
   attachments stay. Removing those is a deliberate act by somebody who means
   it.
6. **A clean virtual machine with no Python** — `where python` finds nothing.
   This is the only test that proves the compile was worth doing, and the only
   one that catches a dependency the build machine happened to have.

Step 6 has not been run yet. Until it has, this document should not be read as
saying the product installs on a machine with no Python; it says the build is
arranged so that it can.

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
