---
name: run-app
description: Launch and drive this platform for real — the FastAPI backend and the Flutter Windows desktop client — to confirm a change works in the running app rather than only in tests. Use when asked to run, start, smoke-test or screenshot the app, or to verify a backend endpoint or a desktop screen end to end.
---

# Running the agency platform

Two processes: the FastAPI backend (all business logic) and the Flutter
Windows client (REST only, no database). The backend is where every
behavioural change lives and is fully drivable with `curl`. The desktop
client can be launched and inspected but **cannot be clicked** — see
[Driving the desktop](#driving-the-desktop).

Everything below was verified on 2026-08-10 against the seeded local
database.

## Backend

Run from `backend/`. Use the interpreter directly — `uv run` fails on this
machine with `uv trampoline failed to canonicalize script path`.

```bash
cd backend
./.venv/Scripts/python.exe -m alembic current        # expect: a revision + "(head)"
(./.venv/Scripts/python.exe -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8010 > uvicorn-run.log 2>&1 &)
sleep 12
curl -s http://127.0.0.1:8010/health
```

Pick a port other than 8000: a dev server is often already running there,
and **it will be serving stale code**. That cost real time once — an
endpoint appeared fixed because the old process had an older module
loaded. If you must reuse 8000, prove the code is current first, e.g.
`curl -s .../openapi.json` and look for a schema field your change added.

Errors return `{"success": false, ...}` with a generic message; the
traceback is in the log:

```bash
tail -40 uvicorn-run.log | grep -vE "site-packages|^\s+\^" | tail -20
```

### Logging in

`platform-admin@agency.local` (password in `config/.env` as
`AGENCY_BOOTSTRAP_ADMIN_PASSWORD`) returns `must_change_password: true`
and every platform-admin route then answers `authorization_denied`. That
is the identity hardening working. **Do not rotate it** just to get a
token — you would invalidate the value in `config/.env`.

Use a seeded user instead:

| User | Password | Source |
|---|---|---|
| `whole01.admin@agency.local` and friends | `DemoAdmin@12345` | `scripts/seed_multi_firm_demo.py` (`DEMO_PASSWORD`) |
| users created by the sample-data script | `Password@123` | `scripts/generate_sample_data.py` (`DEVELOPMENT_PASSWORD`) |

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8010/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"whole01.admin@agency.local","password":"DemoAdmin@12345"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['data']['access_token'])")

# /me/firms returns {id, code, name, is_primary}: the firm id is `id`.
FIRM=$(curl -s http://127.0.0.1:8010/api/v1/me/firms -H "Authorization: Bearer $TOKEN" \
  | python -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])")
```

Never write the token to a file inside the repo. A previous run committed
one; `.tok` and `uvicorn-*.log` are now in `backend/.gitignore`.

### Calling firm-owned endpoints

Everything except `/health` and `/api/v1/{auth,users,roles,permissions,firms,dashboard,me}`
needs `X-Firm-ID`. Without it a firm-owned route resolves no tenant.

```bash
curl -s "http://127.0.0.1:8010/api/v1/inventory/ledger?page=1&page_size=4" \
  -H "Authorization: Bearer $TOKEN" -H "X-Firm-ID: $FIRM"
```

Useful smoke targets, each exercising a different subsystem:

```bash
# stock movements, running balances, pagination metadata
/api/v1/inventory/ledger?page=1&page_size=4
/api/v1/inventory/transactions?page=1&page_size=4

# document lists — all report total_records / total_pages
/api/v1/purchase-returns  /api/v1/sales-orders  /api/v1/delivery-notes  /api/v1/goods-receipts

# the tax engine, which decides money on every document line
POST /api/v1/tax-framework/simulate
  {"transaction_type":"SALES_INVOICE","transaction_date":"2026-06-01",
   "tax_profile_id":"<id>","invoice_value":"1000"}
```

The seeded wholesale firm carries GST profiles named by group
(`GST_18_LOCAL`, `GST_18_INTERSTATE`, …) and six country-scoped rules.
Simulating `SALES_INVOICE` on `GST_18_LOCAL` should return CGST 9 + SGST 9;
simulating `SALES_INTERSTATE` on the same profile should match
`INTERSTATE_GST_18` and return a single IGST 18. If the interstate case
returns CGST/SGST and `matched_rule_id: null`, rule scoping has regressed.

## Desktop

```bash
cd desktop
(flutter run -d windows --dart-define=API_BASE_URL=http://127.0.0.1:8010 \
    > run.log 2>&1 &)
```

First build takes ~30s. Success looks like `√ Built ...agency_desktop.exe`
followed by a Dart VM Service URL. A red-screen build failure appears in
`run.log` as an exception — read it before concluding anything.

```bash
powershell -Command "Get-Process agency_desktop | Select-Object Id,MainWindowTitle,Responding"
```

### Driving the desktop

**Screenshots do not work, and a white frame does not mean a broken app.**
The Flutter surface is GPU-composited: `Graphics.CopyFromScreen` captures
the physical screen (blank in a non-interactive session) and `PrintWindow`
with `PW_RENDERFULLCONTENT` captures the DWM title bar and nothing else.
Both were tried; both produce white.

Inspect the live widget tree through the Dart VM Service instead — this is
real evidence about what rendered:

```bash
VM=$(grep -oE "http://127.0.0.1:[0-9]+/[A-Za-z0-9_=-]+/" run.log | head -1)
ISO=$(curl -s "${VM}getVM" | python -c "import json,sys; print(json.load(sys.stdin)['result']['isolates'][0]['id'])")
curl -s "${VM}ext.flutter.debugDumpApp?isolateId=$ISO" \
  | python -c "
import json,sys,re
data=json.load(sys.stdin)['result']['data']
print('widgets:', len(data.splitlines()))
for l in data.splitlines():
    if re.search(r'LoginScreen|DesktopShell|Text\(\"', l): print(' ', l.strip()[:120])
" | head -20
```

A freshly launched client sits on `LoginScreen`. A tree of a few hundred
widgets and no exception in `run.log` means the app is alive and drawing.

There is **no click automation**. Flutter on Windows has no Playwright
equivalent, and `flutter_driver` is not wired up in this repo. To exercise
a screen you either add a widget test under `desktop/test/` (fast, and
where the existing coverage lives) or add `flutter_driver` and write a
driver. Do not claim a screen was verified by clicking when it was not.

## Cleanup

`pkill` does **not** reach native Windows processes. It exits 0 and leaves
the server running, which then serves stale code to the next run — this
bit me while testing this very skill: a pre-fix server stayed on 8010 and
an endpoint I had already repaired kept returning 500.

```bash
powershell -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" |
  Where-Object { \$_.CommandLine -like '*uvicorn*' } |
  ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
powershell -Command "Stop-Process -Name agency_desktop -Force -ErrorAction SilentlyContinue"
rm -f desktop/run.log backend/uvicorn-run.log
git status --short          # expect nothing
```

To see what is still listening before you start:

```bash
powershell -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" |
  Where-Object { \$_.CommandLine -like '*uvicorn*' } |
  Select-Object ProcessId,@{n='port';e={if(\$_.CommandLine -match '--port (\d+)'){\$matches[1]}}}"
```

## What "verified" honestly means here

- **Backend change** → drive the endpoint with `curl`, read the body, and
  say what it returned. This is a full verification.
- **Desktop change** → the widget test is the verification; launching adds
  that the app builds, boots and renders. Say which of the two you did.
