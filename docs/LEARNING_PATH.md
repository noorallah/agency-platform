# Learning this codebase, module by module

A reading order for someone new to the platform, ordered by how much you have to
already know to make sense of a module — not by how interesting it is.

The ordering is measured rather than guessed. The dependency counts, line counts
and endpoint counts below were taken from the tree on 2026-08-10; re-measure with
the commands at the end if they look stale.

**Dependency count is the honest difficulty signal.** Size is not: the smallest
module in the repo imports twenty others, and the least-coupled one is 4,374
lines with no user interface. Both are covered under "Looks easy, isn't".

---

## Before any module: the frame

Skipping this makes every module look arbitrary, because most of what a router
does is compose framework pieces.

**`app/core/`** — the transport- and domain-independent framework: the
`ApiResponse`/`PaginatedResponse` envelope, error codes, pagination and
filtering, and `BaseEntity` (UUID id, created/updated actor, `version` for
optimistic concurrency, `is_deleted`/`deleted_at`). Every business entity
extends it. It holds no business entities itself, and it must stay that way.

**`app/common/scope.py`** — the single most important file to read early. Every
firm-owned router composes it, and it exists for a specific reason: `firms` and
`user_firms` live **only** in the platform schema, while a tenant session runs
`SET search_path TO "<firm schema>"` with no fallback. Resolving a firm on the
request session therefore raises `UndefinedTable` for every firm outside the
platform store. Every firm-owned router did exactly that until 2026-08-09.

Understanding multi-tenancy before anything else pays for itself. Requests carry
an `X-Firm-ID` header; `app/core/database/dependencies.py` decides whether the
session is the platform schema or a firm store, and a firm resolves to `SHARED`,
`SCHEMA` or `DATABASE`. Business services never know which — they receive a
`Session` and stay storage-agnostic.

Then read one router → service → repository chain end to end. Routers are thin
adapters (validate, resolve scope, delegate); services own transactions,
business rules and audit writes; repositories own soft-delete-aware queries.
That shape repeats in all 23 modules.

---

## The order

| # | Module | Deps | LOC | Routes | Why here |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | `firms` | 3 | 779 | 5 | The smallest complete module. **Platform-only, so there is no firm scoping to reason about** — you learn the five layers with one variable removed. |
| 2 | `customers` | 2 | 2,328 | 17 | The designated **reference master-data module**. Reviewed 2026-08-10 and found clean, so what you read is what was intended. Read the backend and its desktop workspace side by side. |
| 3 | `products` | 4 | 2,247 | 17 | The same shape plus configurable custom fields via `AttributeService`. |
| 4 | `vendors` | 2 | 2,556 | 23 | Reinforcement of the master pattern. Skim it if `customers` landed. |
| 5 | `branches` | 3 | 3,343 | 39 | Adds bulk endpoints and exclusivity flags (`is_default`) — both places real defects lived. |
| 6 | `business` | 3 | 2,871 | 30 | Business profiles, features and modules: what decides the capabilities a firm operates. |
| 7 | `uom` | 2 | 2,914 | 29 | Units, conversion rules and packaging. |
| 8 | `document_framework` | 2 | 2,248 | 15 | Document types, states, numbering and timeline events. Read before any document module. |
| 9 | `batch_serial` | 2 | 1,678 | 17 | Small and self-contained; batches, serials and expiry. |
| 10 | `tax` | 3 | 5,580 | 52 | The hardest of the frameworks. Do it last in this group, and do not skip it — see below. |
| 11 | `purchase` | 10 | 2,617 | 12 | The designated **reference transactional module**. |
| 12 | `goods_receipt` → `purchase_invoice` → `purchase_return` | 10–11 | ~8,100 | 50 | One chain, read in document order. |
| 13 | `sales_order` → `delivery_note` → `sales_invoice` | 11–13 | ~7,900 | 52 | The mirror chain on the sales side. |
| 14 | `inventory` | 5 | 4,357 | 19 | Only makes sense once you know what writes to it. |
| 15 | `finance` | 1 | 4,374 | 30 | The consequences of everything above. |
| — | `search` | **20** | 936 | 1 | Last, whenever you like. It reaches into nearly every module. |

### The difficulty cliff is between 10 and 11

Dependencies jump from 4 to 10. Everything before that you can hold in your
head. A document module coordinates ten others inside a single transaction —
stock movement, tax, numbering, the ledger, the source document it was built
from — and that is where the genuinely hard reasoning lives.

Do not try to shortcut into the document modules. They are where almost every
serious defect in this repository has been found, and they are unreadable
without the frameworks under them.

---

## How to read a module fastest

**Start with `tests/unit/test_<module>.py`, not the router.** The unit tests
build a SQLite in-memory database and call the route functions directly with
hand-constructed `Principal` and scope objects. That means one file shows you
the intended call sequence, the permission codes involved and the expected
shape of the result, with no server and no PostgreSQL. It is the closest thing
to an executable specification the module has.

Then, in order:

1. `models/` — what is stored, and which columns are indexed
2. `api/router.py` — the surface, the permission codes, the scope dependency
3. `services/` — the rules and the transaction boundary
4. `repositories/` — the queries, and how soft delete is honoured

Finally read that module's row in
[`MODULE_REVIEW_CHECKLIST.md`](MODULE_REVIEW_CHECKLIST.md). Its Findings column
is a list of what actually broke there — cancel leaving stock posted, totals
computed twice with different formulas, lines re-inserted on edit and leaving
downstream references dangling. Every checklist item derives from a defect that
really happened, so it is the quickest way to learn where a module's sharp edges
are before you touch it.

Run what you read. `docs/RUNNING.md` gets you a signed-in client with four demo
firms and two years of trading history, so you can watch a module behave.

---

## Looks easy, isn't

**`finance` has the lowest coupling in the repo — one dependency — and is not a
beginner module.** 4,374 lines, 30 endpoints, **no desktop UI at all**, and
automatic GL posting from invoices is not built: it needs a per-firm
control-account mapping design that does not exist yet. Low coupling does not
mean simple.

**`sales` (territory and routes) sounds like a small master** and is 4,496 lines
across 44 endpoints — larger than `inventory`.

**`tax` is not a side feature.** `TaxRuleService.simulate` is called once per
line by all seven transactional modules while a document is being built, on the
caller's session. It **is** the tax calculation, not a preview, which is why it
must never commit. You cannot trust any document total until you have read it.
It is also where `included_in_price` and `REVERSE_CHARGE` are decided, and those
must not be added to a document total.

**`search` is 936 lines and one endpoint** — and imports twenty modules. Its
size says nothing about the difficulty of reading it.

**`app/platform`, `app/tenant` and `app/infrastructure` exist on disk and are
empty.** They are untracked leftovers of a deletion: eleven docstring-only
packages were removed on 2026-08-09 because they advertised subsystems that do
not exist — backup, licensing, scheduling, notifications, file storage. Do not
go looking in them, and do not recreate an empty package to reserve a name.

---

## Two conventions worth learning before you write anything

**A permission code you enforce must also be seeded.** Any code passed to
`require_permission` must exist in `PERMISSION_GROUPS` in
`app/identity/system_seed.py`. An unseeded code has no permission row, so it
cannot be attached to any role, and the endpoint silently becomes
platform-admin-only. Twelve codes were in that state until 2026-08-09; a test
now fails the build if it recurs.

**Migrations advance one schema per run.** `AGENCY_DATABASE_SCHEMA` chooses it,
default `platform`. Firm-owned tables live in `firm_shared` and in every
dedicated firm store, so a bare `alembic upgrade head` leaves firm data behind
and the drift is invisible until a query hits a missing column. See
[`RUNNING.md`](RUNNING.md).

---

## Re-measuring

Dependency counts, the thing this ordering rests on:

```powershell
cd backend
foreach ($d in Get-ChildItem app -Directory) {
  if ($d.Name -in 'core','__pycache__') { continue }
  $deps = Get-ChildItem $d.FullName -Recurse -Filter *.py |
    Select-String -Pattern 'from app\.([a-z_]+)' -AllMatches |
    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } |
    Where-Object { $_ -notin @('core', $d.Name) } | Sort-Object -Unique
  '{0,-20} {1,3}  {2}' -f $d.Name, $deps.Count, ($deps -join ' ')
}
```

A module reporting `0` with no names is one of the empty leftover directories,
not a module with no dependencies.

Endpoint counts per module come from the debt inventory table in
[`MODULE_REVIEW_CHECKLIST.md`](MODULE_REVIEW_CHECKLIST.md), which also records
per-module ruff, mypy, unit-test and desktop coverage.

---

## Where to go next

- [`RUNNING.md`](RUNNING.md) — get it running, with demo logins
- [`MODULE_REVIEW_CHECKLIST.md`](MODULE_REVIEW_CHECKLIST.md) — per-module debt and what has broken
- [`BUSINESS_PROFILE_FRAMEWORK.md`](BUSINESS_PROFILE_FRAMEWORK.md) — capabilities and custom fields
- [`MULTI_INDUSTRY_ERP_ARCHITECTURE.md`](MULTI_INDUSTRY_ERP_ARCHITECTURE.md) — the wider design
- `desktop/docs/DESKTOP_FRAMEWORK.md` — the client, once you start reading UI
