# Hardware sizing

What this application needs to run, measured rather than estimated.

Every number below was taken on **2026-09-06** from the development machine
(Intel i9-13900H, 14 physical cores, 15.7 GB RAM, Windows 11, PostgreSQL 17 in
Docker) with the four demo firms and two financial years of seeded trading —
440,706 live rows across 397 tables in three schemas.

**Read the limits section before treating this as a capacity plan.** No load
test has been run. These are resting measurements of a working system, not
throughput figures.

---

## The short answer

| Role | CPU | RAM | Disk | Measured |
| --- | --- | --- | --- | --- |
| **Desktop client**, per user | any 64-bit | 4 GB | ~300 MB | 84 MB resident |
| **Server**, small office | 2 cores | 4 GB min, **8 GB comfortable** | 128 GB SSD | FastAPI 32 MB; PostgreSQL takes what it is given |
| **One machine running everything** | 4 cores | **8 GB** | 256 GB SSD | 4 GB works without Docker |
| **Development** (build + full suite) | 8+ cores | **16 GB min, 32 GB better** | 100 GB free | see below |

A mini PC with **8 GB, four cores and a 256 GB SSD**, running PostgreSQL
natively, serves a small office comfortably. The clients on the LAN are nearly
free.

Software prerequisites — Python 3.13, PostgreSQL 17, Flutter, Windows
Developer Mode — are in [RUNNING.md](RUNNING.md#prerequisites).

---

## RAM is the constraint

Nothing else comes close.

| Process | Resting |
| --- | --- |
| Flutter desktop client | **84 MB** |
| FastAPI backend (uvicorn, idle) | **32 MB** across 2 processes |
| PostgreSQL | **3.0 GiB** held, nearly all page cache |

PostgreSQL will use what it is given and shrink when it is not; the 3 GiB is
cache, not a requirement. It is the only component whose appetite is worth
tuning.

**Docker costs several GB before PostgreSQL starts.** On this machine Docker
Desktop's WSL2 backend is allocated **7.6 GiB**. A native PostgreSQL install
avoids that entirely, and it is the difference between 4 GB being workable and
not. Use Docker for development, native for a deployment.

---

## Disk is smaller than it looks

Four firms, two years of trading:

| | Size |
| --- | --- |
| All user tables, indexes included | **294 MB** |
| — of which prunable logs | **249 MB (85%)** |
| — of which actual business data | **~45 MB** |

That is roughly **11 MB per firm per year** of real business data. Disk will
never be your constraint. **Logs will**, and only if you let them:

```
firm_shared.audit_logs                     78 MB   225,921 rows
firm_shared.tax_rule_execution_logs        69 MB    24,017 rows
wholesale_hub.audit_logs                   54 MB   154,752 rows
wholesale_hub.tax_rule_execution_logs      44 MB    15,587 rows
```

`tax_rule_execution_logs` grows fastest — one row holding three JSON documents
per document line. **Nothing prunes any of this unless you turn the retention
service on**, and it is deliberately opt-in so that bringing the stack up does
not start deleting rows:

```powershell
docker compose --profile retention up -d
```

`AGENCY_RETENTION_INTERVAL_SECONDS` sets the period (default daily);
`AGENCY_RETENTION_MODE=--dry-run` makes it report instead of delete. Without
it, plan for the log tables to outgrow the business data by an order of
magnitude. **Enabling it on day one is the single setting that decides whether
the database is 300 MB or 3 GB in three years.**

### One caveat about this development database

`pg_database_size` reports **1,040 MB**, against 294 MB of actual tables. The
gap is **746 MB of bloated `pg_catalog`** — the cost of repeatedly creating and
dropping 183-table schemas during development, not of storing anything. A
deployment that provisions a firm once will not see it. Do not size a disk from
that number.

---

## CPU

Barely matters for serving. Two cores is enough for a small office; the
application is I/O-bound on PostgreSQL and the desktop client does its own
rendering.

It matters a great deal for **building and testing** — see below.

---

## The development machine is the heavy case

On the i9-13900H above, with the dev server, the desktop client and Docker all
running and 0.7 GB of RAM free:

| Task | Time |
| --- | --- |
| Full backend unit suite (1,237 tests) | **23 minutes** |
| Backend integration suite (48 tests) | 2m 19s |
| Full desktop suite (1,151 tests) | 3m 55s |
| `flutter build windows`, clean | ~60–125s |

On an idle machine the backend suite is about six minutes. The gap is memory
pressure, not clock speed — which is why 16 GB is the floor and 32 GB is where
it stops being something you think about. Each backend test file builds a whole
185-table SQLite schema, so the suite is allocation-heavy by design.

The Flutter Windows build also needs the **Visual Studio C++ toolchain**,
several GB on its own, and **Windows Developer Mode** enabled — the
secure-storage plugin needs symlinks and the build fails without it.

---

## Network

The desktop talks to the backend over REST only and never touches the
database, so a LAN deployment puts one server on the network and any number of
clients around it. `https` is required except to a private-network address,
where plain `http` is accepted — see the LAN transport rules in
`desktop/lib/core/api/api_client.dart`.

---

## Limits of these figures

- **No load test has been run.** There are no concurrent-user, throughput or
  response-time measurements anywhere in this repository. Everything above is
  a resting measurement of a working system.
- **The data is seeded, not real.** Four firms and two years of synthetic
  trading through the real services. A firm with a large product catalogue, a
  long customer list or heavy batch/serial tracking will differ.
- **One machine, one platform.** Windows 11 with PostgreSQL in Docker. Linux
  will use less; a native PostgreSQL install will use less.
- **A DATABASE-mode firm on a separate server** doubles the PostgreSQL
  footprint on that host. `agency_electrolink` here is 124 MB, of which 92 MB
  (74%) is prunable logs.

Re-derive rather than trust these after a few months. The command beside each
number is the honest way to check it.
