---
name: reset-demo-data
description: Rebuild the four demo firms and their trading history, or regenerate one firm's history on its own. Use when asked to reset, reseed, refresh or regenerate the demo/sample data, when the local stores look wrong or empty, or after a migration that changes what the seeders produce.
---

# Resetting the demo data

Two scripts and one rule about the order they run in.

`seed_multi_firm_demo.py` builds four firms across all three tenancy modes,
their masters, their opening stock, and two financial years of trading.
`generate_transaction_history.py` regenerates one firm's trading on its own.
Both drive the **real services**, so what they produce is what the application
could have produced — and a defect in any of the seven transactional modules
stops them. That makes a seed run a blunt integration test, and it has earned
that reputation: it has caught a dispatch gate reading one row of several, a
seeder wiping its own opening stock, and an index named for the wrong column.

Everything below was verified on 2026-08-14 against the local PostgreSQL.

## Migrate first, always

Run from `backend/`. Use the interpreter directly — `uv run` fails on this
machine with `uv trampoline failed to canonicalize script path`.

```bash
cd backend
./.venv/Scripts/python.exe scripts/migrate_all_stores.py --dry-run   # what is where
./.venv/Scripts/python.exe scripts/migrate_all_stores.py --yes       # bring all to head
```

**Never `alembic upgrade head` on its own here.** It advances exactly one
schema, chosen by `AGENCY_DATABASE_SCHEMA`, and the demo has four stores: the
platform schema, `firm_shared` (MEDI01 and FOOD01), `wholesale_hub` (WHOLE01)
and the `agency_electrolink` database (ELEC01). A store left behind is
invisible until a query hits a missing column. `migrate_all_stores.py`
enumerates them from the registry rather than a list somebody maintains, so a
firm on another server is upgraded on that server.

`--dry-run` prints the revision each store is at, which is the fastest way to
see drift.

If you ever set `AGENCY_DATABASE_SCHEMA` or `AGENCY_DATABASE_NAME` by hand to
migrate one store, clear them afterwards or every later command in the shell
talks to the wrong place:

```bash
# PowerShell
Remove-Item Env:\AGENCY_DATABASE_*
```

## Seeding

```bash
./.venv/Scripts/python.exe scripts/seed_multi_firm_demo.py                    # masters + 3 financial years
./.venv/Scripts/python.exe scripts/seed_multi_firm_demo.py --history-years 3  # more history
./.venv/Scripts/python.exe scripts/seed_multi_firm_demo.py --no-history       # masters only
```

Takes a few minutes. It is **destructive to trading history and only to
that**: masters — firms, users, branches, vendors, customers, products — are
left alone on a re-run, and each firm's documents, stock and ledger are
rebuilt. Anything created by hand through the API or the desktop is trading
history and will go. Say so before running it if the user has data they care
about.

One firm on its own, which is much faster:

```bash
./.venv/Scripts/python.exe scripts/generate_transaction_history.py --firm FOOD01 --years 3 --reset --yes
./.venv/Scripts/python.exe scripts/generate_transaction_history.py --dry-run
```

`--firm` is repeatable. Without `--reset` it appends to whatever is there.

## What a good run looks like

```
MEDI01 history: 3 financial year(s) | PO 29 | GRN 29 | SO 57 | DN 57 | INV 48
FOOD01 history: 3 financial year(s) | PO 29 | GRN 29 | SO 57 | DN 57 | INV 48
WHOLE01 history: 3 financial year(s) | PO 29 | GRN 29 | SO 57 | DN 57 | INV 48
ELEC01 history: 3 financial year(s) | PO 29 | GRN 29 | SO 57 | DN 57 | INV 48
```

The history exercises the pricing rules as well as the documents. One
customer per firm trades on a standing 7.5% discount, which every sale to them
picks up server-side; a discount on the whole bill lands every fourth month;
and a unit is thrown in free every third. None of it was there before
2026-08-23, so nothing in the demo showed a discount and nothing exercised the
apportionment across three tenancy modes. Checking that every discounted
invoice's line shares sum to its header figure is a one-line query worth
running after a seed:

```sql
SELECT count(*) FROM sales_invoices i WHERE i.bill_discount_amount <> (
  SELECT coalesce(sum(l.bill_discount_amount), 0) FROM sales_invoice_lines l
  WHERE l.sales_invoice_id = i.id);   -- must be 0
```

**Read the DN count against the SO count.** They should match. A shortfall
means deliveries were skipped, and the standalone script prints why:

```
note: 2023-08-22 sale: Insufficient available stock for dispatch line.
```

That is how a real dispatch defect was found: the two batch-tracked firms were
losing a third of their deliveries while the other two were fine. A gap between
firms is a signal, not noise — the four differ only in tenancy mode, business
profile and unit factors.

## Checking the result

**Run `scripts/verify_sample_data.py` first.** It was rewritten on 2026-08-14
and is the fastest answer to whether the books hold:

```bash
./.venv/Scripts/python.exe scripts/verify_sample_data.py
```

It enumerates every firm store from the registry the way `migrate_all_stores.py`
does, reports all of them rather than stopping at the first failure, and exits
non-zero if any check failed. The five checks are the defects that actually
shipped: stock value against the inventory control account, every accounting
period balancing, customer outstanding against the receivable control account,
every settlement carrying its journal, and every approved invoice having
posted. It found a valuation leak in sales returns within minutes of existing.

This paragraph used to say the script did not work and should not be offered,
which was true of the version that predated multi-tenancy and had not been
updated since.

These checks do work, and each has caught something real:

```bash
./.venv/Scripts/python.exe -c "
from app.core.config.settings import Settings
from app.core.database.config import database_config_from_settings
from sqlalchemy import create_engine, text
eng = create_engine(database_config_from_settings(Settings()).url)
with eng.connect() as c:
    c.execute(text('SET search_path TO \"firm_shared\"'))
    print('drifted rows:', c.execute(text('''
        SELECT count(*) FROM inventories i WHERE i.current_quantity <> (
          SELECT coalesce(sum(t.current_quantity_delta),0) FROM inventory_transactions t
          WHERE t.inventory_id = i.id)
    ''')).scalar())
    print('negative available:', c.execute(text(
        'SELECT count(*) FROM inventories WHERE available_quantity < 0')).scalar())
    for t in ('OPENING_STOCK','GOODS_RECEIPT','RESERVE','UNRESERVE','DISPATCH'):
        named = c.execute(text(f\"SELECT count(*) FROM inventory_transactions WHERE transaction_type='{t}' AND batch_id IS NOT NULL\")).scalar()
        anon = c.execute(text(f\"SELECT count(*) FROM inventory_transactions WHERE transaction_type='{t}' AND batch_id IS NULL\")).scalar()
        print(f'{t:15} batch: {named:4}  untracked: {anon:4}')
"
```

- **drifted rows must be 0.** The projection has to equal the sum of its own
  movements; that invariant is the point of the module.
- **negative available must be 0.** It was the symptom of reserving a product
  whose stock is held in batches.
- **Both batch and untracked movements should appear.** MEDI01 and FOOD01 trace
  their medicines and packaged food; their vitamins and biscuits are
  deliberately untraced, and WHOLE01 and ELEC01 trace nothing. All zero in the
  batch column means batch tracking stopped being exercised.

`scripts/sql/check_backend_data.sql` holds hand queries for a deeper look.
**Read its header first** — firm-owned tables exist once per store, so a query
answers for whichever schema the connection is pointed at.

## Traps

- **Migrate before seeding, not after.** The seeders build some objects with
  `Base.metadata.create_all`, so a store can hold a table the migrations have
  not reached and the drift will not surface until something queries a column.
- **Opening stock is history.** `reset_history` deletes it along with the
  documents, which is why the seeder resets *before* laying the day-one shelf
  down. Anything that reorders that will silently produce stores whose opening
  stock documents have no movements behind them.
- **Batches survive a reset.** `batches` is not in `RESET_ORDER`, so batch
  records outlive the movements that created them. Regenerating reuses them by
  number rather than duplicating, and a leftover batch correctly reports zero
  because a batch's quantity is derived from the stock rows.
- **`generate_sample_data.py` is a different dataset.** One firm, `NAVK_CPL`,
  a handful of documents dated this month. Do not mix the two.
- **`reset_tenancy_layout.py --yes` is a different order of destruction.** It
  drops and rebuilds the platform and `firm_shared` schemas. Only reach for it
  when the layout itself is wrong, and tell the user plainly first.

## Logging in afterwards

Every seeded user has the password `DemoAdmin@12345`:

| User | Firms |
| --- | --- |
| `master.ops@agency.local` | all four |
| `medi01.admin@agency.local` | MEDI01 (PHARMACY, shared schema) |
| `food01.admin@agency.local` | FOOD01 (FOOD, shared schema) |
| `whole01.admin@agency.local` | WHOLE01 (WHOLESALE, dedicated schema) |
| `elec01.admin@agency.local` | ELEC01 (ELECTRONICS, dedicated database) |

`platform-admin@agency.local` is not one of these: it must change its password
on first use and every platform-admin route refuses it until then. Do not
rotate it to get a token — that invalidates the value in `config/.env`. Use
`master.ops@agency.local` instead.

See the `run-app` skill for starting the backend and driving it with `curl`.
