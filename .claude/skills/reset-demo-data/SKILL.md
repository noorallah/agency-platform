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

**`--reset` on its own leaves the firm with no opening stock, and it will not
match its siblings.** Opening stock is history, so the reset clears it, and
only `seed_multi_firm_demo.py` lays it back down -- only that script holds the
blueprint saying which products sit on the day-one shelf and how many. A firm
regenerated alone therefore trades from goods receipts only and quietly loses
the dispatches those receipts cannot cover: WHOLE01 comes out at **DN 57**
against **SO 58** where the full seed gives 58 for all four. The script says so
now, in a note above the shortfall it causes, and names the script to run
instead. Reach for the standalone path to regenerate quickly while iterating;
reach for `seed_multi_firm_demo.py` whenever the four firms need to agree.

## What a good run looks like

```
MEDI01 history: 3 financial year(s) | PO 30 | GRN 30 | PINV 30 | PRET 6 | PROMO 4 | QT 29 | SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | ADV 9 | LOY 7 | TCS 27-30 | TGT 2 | PAY 2
FOOD01 history: 3 financial year(s) | PO 30 | GRN 30 | PINV 30 | PRET 6 | PROMO 4 | QT 29 | SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | ADV 9 | LOY 7 | TCS 27-30 | TGT 2 | PAY 2
WHOLE01 history: 3 financial year(s) | PO 30 | GRN 30 | PINV 30 | PRET 6 | PROMO 4 | QT 29 | SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | ADV 9 | LOY 7 | TCS 27-30 | TGT 2 | PAY 2
ELEC01 history: 3 financial year(s) | PO 30 | GRN 30 | PINV 30 | PRET 6 | PROMO 4 | QT 29 | SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | ADV 9 | LOY 7 | TCS 27-30 | TGT 2 | PAY 2
```

**`seed_multi_firm_demo.py` prints the notes now, not only the counts.** It
printed the tally line and dropped `tally.skipped` on the floor, so every
document a run could not raise was invisible from the multi-firm entry point
while the standalone script showed it -- which is the entry point everybody
uses. The first run after fixing it immediately reported two firms seeding a
different set of commission rules from the other two.

**The purchase counts drift by a cycle with the date.** The generator derives
its periods from today, so `PO`/`GRN`/`PINV` read 29 or 30 and `PRET` 5 or 6
depending on when the run happens. `TCS` varies for a different reason and
legitimately: the section only charges above a per-buyer threshold, so a firm
whose customers cross it on a different receipt collects on a different number
of them. Everything else should match.

**A re-run prints `incentives: everybody already has a rule, so no ladder was
seeded` on every firm, and that is correct.** Commission *rules* survive a
reset by design, so a second run finds the four arrangements already there and
does not duplicate them. It reads like the ladder is missing; check before
believing it -- `commission_rule_slabs` should hold 2 rows per firm, and the
report below is the real test.

**The four firms should agree line for line.** They differ only in tenancy
mode, business profile and unit factors, so a count that differs is a signal.
`PRET` read 1 and 2 on the two batch-tracked firms while the others read 5,
with no refusal printed at the top level -- the notes said a traced product may
only be issued from a batch, so a return has to name the one going back.

**`RCPT` should be roughly three quarters of `INV`.** Money coming in arrived
on 2026-08-23; before that every store held zero settlements, so receivables
only ever grew and the commission report -- which is earned on money
*collected* -- could only ever answer zero. One invoice in four is deliberately
left outstanding and one in four paid in part, because a demo where every bill
is settled has nothing for an ageing report to show.

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

**`PF` should read 14.** Proformas arrived on 2026-09-03 and every store held
zero, which looks exactly like a firm nobody has ever asked for one. Every
fourth order gets one, issued rather than left in draft, because a proforma is
what a buyer asks for when they need a figure before the goods move -- not
something every sale produces.

**`LOY` should read 7.** Every store runs a loyalty scheme -- two points per
hundred, worth a rupee each, a floor of fifty and a two-year life -- and one
bill in seven is part-settled with what the customer has earned. `LOY` counts
the redemptions; the earnings are one per approved invoice, so the ledger holds
about fifty-six rows a firm.

**`ADV` should read 9.** A deposit is taken against one order in six, a third
of its value, and applied to the bill when it is raised. Before this every
`settlements.sales_order_id` was NULL and
`POST /api/v1/receipts/{id}/allocate` was reachable by nothing -- which is how
`ADVANCE_APPLY` sat unreachable from the day the settlements module shipped.

**`TCS` is the one count that legitimately differs between the firms**, and
reads 27 to 30. Tax collected at source is charged when a buyer's payments
pass a threshold, and each firm's buyers get there on their own trading, which
differs by tax rate and unit factor. Every other count should still match line
for line.

The demo scales the buyer threshold to **five thousand rupees**. The statutory
figure is fifty lakh and a demo customer pays a few thousand a year, so at the
real number the mechanism could never fire -- which is the state seeding it
exists to get out of. Fifty thousand was tried first and every store still
reported zero. Only that figure and the stated preceding-year turnover are
scaled; the rate, the excess-only rule and the per-buyer financial year are
the section's own.

**`CN` should read 9.** Credit notes arrived on 2026-09-03 and every store
held zero of them, so the GSTR-1 CDNR section answered empty everywhere --
which looks exactly like a firm that has issued none. One invoice in five is
credited a tenth of a line, as a rate agreed after the bill went out:
deliberately not a sales return, because a return moves stock and this does
not, and seeding both is what makes the difference visible in the data rather
than only in the docs. The first run of it found the third copy of the
four-decimals-into-a-two-decimal-receivable defect, which had made every
approval of such a note fail outright.

**Each firm carries seven beat plans as of 2026-09-04**, and every store held
zero before that: `GET /call-lists` and a plan's own call list both answered
an empty page for every firm and every date, so the feature looked unbuilt in
exactly the way the whole territory module did before 2026-08-16.

The plans are **derived from each route's own working days**, not from the
list the seeder would have written the route with -- a plan naming a weekday
its route does not work reports *"the route does not work on this day"* for
ever, which is the empty screen the plans exist to fill, with extra rows.

`_node` keeps those days in step: a day the script means a round to work and
the store does not have is added, and **nothing is ever removed**. The service
replaces the day set, so the union is sent rather than the intended list, and
a day somebody added by hand survives a reseed. `WHOLE01-R-N1` had drifted to
Monday alone where every sibling works Monday, Wednesday and Friday, which
left that firm two blank weekdays; it is back in step. Narrowing a round is a
decision and this script does not reverse it -- it only fills gaps, the same
rule the GSTIN, HSN and tax-profile backfills follow.

All four firms now show a round every weekday and none at the weekend.

One plan per firm carries explicit customer stops; the rest fall back to every
customer on their territory in visit order, which is the ordinary arrangement.
Seeding one of each exercises both paths.

**`_node` now backfills a missing route profile.** `WHOLE01-R-S1` had been
seeded before the profile was part of the route list, so it was not a route at
all and every beat plan against it was refused -- the fourth instance of a
master field added later never reaching a store already seeded. Backfilled
only where missing, never overwritten.

**`TGT` and `PAY` should read 2 and 2.** Targets and commission payouts
arrived on 2026-09-03, and before that every store held zero of both: no firm
had a number to measure its salesmen against, and commission reported what was
owed while nothing was ever paid. Each firm now carries four commission
arrangements rather than one -- the firm-wide default, one person's own flat
rate, a **product-scoped** rate for that same person, and a **ladder** with a
floor and a target bonus for the other -- because the module is about
precedence and a demo where everybody earns the same shows none of it.

Reading WHOLE01's report over the whole history is the quickest check that the
precedence is alive: one salesman comes out at **3.17%**, which is neither of
the two rates that govern them and could only be a blend of 4% of *value* on
most lines and 15% of *margin* on the scoped product. The other comes out at
around **1.34%**, off the bottom band of their ladder. One target is met and
one missed, so both states appear on screen.

That first figure was 5.06% until 2026-09-03, when the scoped rule was changed
to pay on margin. A margin rule and a value rule are only told apart by looking
if the numbers differ enough that nobody mistakes it for rounding, which is why
the seeded rate jumped from 6% to 15% at the same time.

The scoped rule names a **product** rather than a category on purpose: these
firms carry a single category, so a category rule would cover every line and
be indistinguishable from an unscoped one -- the precedence it exists to show
would be invisible in the very data seeded to show it.

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
- **`sales_targets` and `commission_payouts` are reset with the history; the
  commission *rules* are not.** A rule is an arrangement that outlives any
  particular year. A seeded target is *derived from* what was sold, so leaving
  it behind while the trading is rebuilt leaves a number measured against
  sales that no longer exist. A payout references the journal entries the
  reset clears, so one that outlived them would be a debt the books cannot
  explain.
- **`proforma_invoices` and its lines are in the reset order**, before the
  sales orders they state. They post nothing, so there is no journal to worry
  about -- only the order.
- **`loyalty_entries` is in the reset order and `loyalty_settings` is not**,
  for the same reason as TCS: a scheme is an arrangement about the firm, and
  rebuilding the trading does not change what a point is worth. This was the
  sixth table set to arrive with a feature and need adding to that list, and
  it was found the way the others were -- a `--reset` failing outright on a
  foreign key the second time it ran.
- **`tcs_collections` is in the reset order and `tcs_settings` is not.** The
  collections hang off the settlements the reset clears; the settings are an
  arrangement about the firm, like a commission rule, and rebuilding the
  trading does not change whether a firm is in scope for the section. The
  seeder does rewrite them on every run, though -- leaving a stale row in
  place is what made one store collect twenty-seven times while its three
  identical siblings collected nothing.
- **`credit_notes` and `credit_note_lines` are in the reset order**, before
  the sales returns, because a credit note points at an invoice and at a
  journal entry the reset clears. That is the fourth table set to arrive with
  a feature; assume the fifth will too.
- **`promotion_redemptions` and `promotion_coupons` were missing from the
  reset order** until 2026-09-03, so `--reset` failed outright on any firm
  whose documents had claimed an offer -- a foreign key violation, not a quiet
  skip. That is the third time a table arrived with a feature and this list
  did not learn about it; the settlements omission was the first.
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
