# Running the application

Two processes, started separately:

- **backend** — FastAPI, owns all business logic and the database
- **desktop** — Flutter Windows client, talks to the backend over REST only

The desktop is useless without the backend, so start the backend first.

`backend/README.md` and `desktop/README.md` document each side in depth. This
page is the shortest path from a clean checkout to a signed-in application, and
the traps that actually cost time.

---

## Prerequisites

| Need | Version | Check |
| --- | --- | --- |
| Python | 3.13+ | `python --version` |
| PostgreSQL | 17 | `psql --version` |
| Flutter | with Windows desktop support | `flutter doctor` |
| Windows Developer Mode | enabled | `start ms-settings:developers` |

Developer Mode is not optional on Windows: the secure-storage plugin needs
symlinks, and the desktop build fails without it.

---

## First time only

Run these once, from `backend`.

### 1. Configuration

```powershell
Copy-Item config\.env.example config\.env
```

`config/.env` is never committed. The defaults point at a local PostgreSQL as
`postgres/postgres` on `localhost:5432`; edit it if yours differs.

### 2. Dependencies

```powershell
uv sync --group dev
```

> **If `uv` fails with `uv trampoline failed to canonicalize script path`**, that
> is a Windows `uv` launcher bug, not a project problem. Every `uv run X`
> below has a direct equivalent — use `.\.venv\Scripts\python.exe -m X`. All the
> commands on this page are written both ways where it matters.

### 3. Create the database

```powershell
createdb -U postgres agency_platform
```

### 4. Apply migrations to **every** store, not just one

This is the single biggest operational trap in the repository.

`alembic/env.py` migrates **exactly one schema per run**, chosen by
`AGENCY_DATABASE_SCHEMA` (default `platform`). A bare `alembic upgrade head`
advances only the platform schema and silently leaves every firm data schema
behind. The drift is invisible until a query hits a missing column.

Start with the two schemas that always exist:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head                # platform
$env:AGENCY_DATABASE_SCHEMA="firm_shared"
.\.venv\Scripts\python.exe -m alembic upgrade head                # firm_shared
Remove-Item Env:\AGENCY_DATABASE_SCHEMA
```

### 5. Seed the demo data

```powershell
.\.venv\Scripts\python.exe scripts\seed_multi_firm_demo.py
```

This creates four firms across all three storage modes and drives **two
financial years of real trading** through the actual services, so stock moves,
receivables build and the ledger balances the way they would in use. It takes a
few minutes. Add `--no-history` for masters only.

### 6. Migrate the dedicated firm stores

The seeder provisions dedicated schemas and databases, so these targets only
exist now. Enumerate them rather than trusting a list:

```powershell
.\.venv\Scripts\python.exe -c "import sqlalchemy as sa; from app.core.config.settings import Settings; s=Settings(); e=sa.create_engine(f'postgresql+psycopg://{s.database_username}:{s.database_password.get_secret_value()}@{s.database_host}:{s.database_port or 5432}/{s.database_name}'); c=e.connect(); c.execute(sa.text('SET search_path TO platform')); [print(r) for r in c.execute(sa.text('SELECT f.code, m.deployment_mode, m.schema_name, m.database_name FROM firms f LEFT JOIN firm_storage_mappings m ON m.firm_id=f.id ORDER BY f.code'))]"
```

With the stock demo data that returns WHOLE01 (`SCHEMA`, `wholesale_hub`) and
ELEC01 (`DATABASE`, `agency_electrolink` / `electrolink_ops`):

```powershell
$env:AGENCY_DATABASE_SCHEMA="wholesale_hub"
.\.venv\Scripts\python.exe -m alembic upgrade head

$env:AGENCY_DATABASE_NAME="agency_electrolink"
$env:AGENCY_DATABASE_SCHEMA="electrolink_ops"
.\.venv\Scripts\python.exe -m alembic upgrade head

Remove-Item Env:\AGENCY_DATABASE_*      # or the next command runs against the wrong store
```

Confirm every store reports the same revision:

```powershell
.\.venv\Scripts\python.exe -m alembic current      # expect a revision + "(head)"
```

---

## Every time

### Backend

```powershell
cd backend
powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1
```

That syncs dependencies, applies migrations **to the default schema only**,
serves on `http://localhost:8000`, and writes a log file. Or run it directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Confirm before starting the client — the first tells you the app is up, the
second that it can reach the database:

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/health/database
```

`http://localhost:8000/docs` is the interactive API.

### Desktop

In a **second terminal you leave open**:

```powershell
cd desktop
flutter pub get
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
```

First build takes around 90 seconds. Success looks like
`√ Built build\windows\x64\runner\Debug\agency_desktop.exe` followed by a Dart
VM Service URL.

> **Do not background `flutter run`.** Detaching it closes its stdin, and it
> then quits and takes the application window with it — the log shows
> `Lost connection to device`. Keep it in a terminal.

If the native runner directories are missing, generate them once:

```powershell
flutter create --platforms=windows,linux,macos .
```

### Pointing the client at another machine

The client is REST-only, so it can run anywhere that can reach the backend:

```powershell
flutter run -d windows --dart-define=API_BASE_URL=http://192.168.1.20:8000
```

The client enforces HTTPS for everything except loopback, so a remote backend
over plain HTTP will be refused. That decision is still open — see
`docs/BACKLOG.md`.

---

## Signing in

All demo users share the password `DemoAdmin@12345`.

| Email | Firms | Use for |
| --- | --- | --- |
| `whole01.admin@agency.local` | WHOLE01 | Everyday testing — this firm has the trading history |
| `medi01.admin@agency.local` | MEDI01 | Shared-store firm |
| `food01.admin@agency.local` | FOOD01 | The other shared-store firm |
| `elec01.admin@agency.local` | ELEC01 | Dedicated-database firm |
| `master.ops@agency.local` | all four | Firm switching and multi-firm cases |

`platform-admin@agency.local` is different: its password is
`AGENCY_BOOTSTRAP_ADMIN_PASSWORD` in `config/.env`, it must change its password
on first login, and it has no firm membership so it cannot open firm-owned
screens at all. That is deliberate — platform admins are not exempt from
supplying a firm context. **Do not rotate it** to get past the prompt; that
invalidates the value in `config/.env`.

---

## Confirming it works

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\unit -q          # ~3 min
.\.venv\Scripts\python.exe -m pytest tests\integration -q   # needs PostgreSQL; skips cleanly without

cd ..\desktop
flutter analyze
flutter test
```

`scripts\sql\check_backend_data.sql` holds queries for inspecting seeded data by
hand. Read its header first — firm-owned tables exist once per store, so the
schema you query decides which firm's data you see.

For manual testing, `docs/MANUAL_UI_TEST_PLAN.md` has the full case list.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `uv trampoline failed to canonicalize script path` | Windows `uv` launcher bug. Use `.\.venv\Scripts\python.exe -m <tool>`. |
| A query fails on a column that exists in the model | A firm store was not migrated. Re-run step 6 for **every** target. |
| Endpoint behaves as though your fix is missing | A stale server is still bound to the port, serving old code. `Stop-Process` it — `pkill` does **not** reach native Windows processes and exits 0 while leaving it running. |
| `/health` works, `/health/database` fails | Check `AGENCY_DATABASE_*` in `config/.env`; the API starts without opening a connection, so this is the real connectivity check. |
| `401` on every request | Access tokens are short lived; sign in again. The client auto-retries a refresh once. |
| `403` with a valid login | Missing `X-Firm-ID`, no active membership in that firm, or the role lacks the permission. Platform authority does not bypass firm scope. |
| Desktop window vanishes immediately | `flutter run` was backgrounded. Run it in a terminal you leave open. |
| Desktop build fails on symlinks | Enable Windows Developer Mode. |
| `alembic upgrade head --sql` fails at `20260728_0004` | Intended — that revision inspects a live schema. Use `upgrade 20260728_0003 --sql` for offline DDL. |

### Stopping cleanly

Stop the desktop by closing its window or pressing `q` in the `flutter run`
terminal. For the backend, `Ctrl+C` in its terminal; if it was started detached:

```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Stop-Process -Name agency_desktop -Force -ErrorAction SilentlyContinue
```

---

## Resetting

Destructively rebuild the local tenancy layout:

```powershell
.\.venv\Scripts\python.exe scripts\reset_tenancy_layout.py --yes
```

Then re-run steps 4 to 6. Rebuild one firm's trading history on its own:

```powershell
.\.venv\Scripts\python.exe scripts\generate_transaction_history.py --firm WHOLE01 --years 2 --reset --yes
```
