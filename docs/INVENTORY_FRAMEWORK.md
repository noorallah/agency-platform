# Inventory Framework

How much is where, how it got there, and what it is worth — three answers the
module has to keep consistent with each other.

Verified against the running backend and the seeded firms on 2026-08-13. Counts
and responses below were read from `/api/v1/inventory` and the stores
themselves, not remembered.

## The idea

A stock figure nobody can explain is worse than no stock figure. So the module
keeps three things and never lets them drift:

```
inventories            the projection  -- what is on hand now
inventory_transactions the movements   -- how it got there, with before/after
stock_ledger_entries   the ledger      -- the same movement, priced
product_valuations     the value       -- moving weighted average per product
```

Every change goes through one private method, `_stage_movement`. It reads the
buckets, applies the deltas, validates them, updates the projection, then writes
a transaction **and** its ledger entry together. Nothing writes stock any other
way — that is what makes the balance reconcilable against its own history.

The invariant, and it is checkable:

```sql
SELECT count(*) FROM inventories i
WHERE i.current_quantity <> (
  SELECT coalesce(sum(t.current_quantity_delta), 0)
  FROM inventory_transactions t WHERE t.inventory_id = i.id
);
-- must be 0
```

## The tables

| Table | Holds | Grain |
| --- | --- | --- |
| `inventories` | the projection, six quantity buckets and planning levels | firm + branch + warehouse + storage locator + product + batch |
| `inventory_transactions` | one row per movement, with previous and new values for every bucket | per movement |
| `stock_ledger_entries` | the same movement plus `unit_cost`, `total_cost`, `average_cost_after` | 1:1 with a transaction |
| `product_valuations` | `costing_method`, `quantity_on_hand`, `average_cost`, `total_value` | firm + product |
| `opening_stock_batches` | a DRAFT→POSTED document for day-one stock | firm + branch + warehouse |
| `opening_stock_lines` | its lines, each carrying the `transaction_id` that posted it | per batch |

All six are firm-owned and live in each firm's own store.

Note the grain difference that trips people up: **the projection is per
location, the valuation is per product.** One product held in two warehouses has
two `inventories` rows and one `product_valuations` row. A cost is a property of
the goods, not of the shelf they sit on.

## Stock is six numbers, not one

`inventories` carries `current`, `reserved`, `blocked`, `damaged`, `quarantine`
and `in_transit`, with

```
available = current - reserved - blocked
```

derived on every movement, plus the planning levels `minimum_level`,
`maximum_level`, `reorder_level` and `safety_stock`.

Each bucket has its own delta on a movement and each is validated non-negative,
so a reservation cannot exceed what is there. That is what lets the sales flow
be three movements instead of one:

```
sales order approved   RESERVE     +reserved            on hand unchanged
delivery note posted   UNRESERVE   -reserved
                       DISPATCH    -current
```

Stock is committed when the order is taken and only leaves the building at
dispatch, so two salespeople cannot promise the same box.

## The batch is part of the grain

Two batches of one medicine in one bay are not one stock figure. Only one of
them expires in March and only one of them is the one being recalled, so they
are two `inventories` rows: `batch_id` is part of the row's identity, not a
label on it. A product nobody tracks keeps its single row, whose `batch_id` is
NULL — two partial unique indexes say exactly that, because a single key over a
nullable column would let untracked stock duplicate freely.

Where each document stands:

| Document | What it does with the batch |
| --- | --- |
| `goods_receipt` | resolves the number typed off the carton, **creating** the batch when it is new |
| `delivery_note` | allocates across batches by earliest expiry, one movement per batch drawn from |
| `purchase_return` | posts against the batch the line names, and **never creates** one |

The asymmetry between the first and last row is deliberate. Goods that have
physically arrived have to be receivable, so an unknown number on a receipt is
registered and a typo is corrected afterwards; an unknown number on a return
names stock that was never taken in, so inventing the batch would write a
delivery that did not happen and leave the new batch holding a negative
quantity. It is refused instead.

Three levels decide whether any of this applies, and all three are enforced:

1. The firm's `BATCH_TRACKING` feature — whether the firm may use batches at
   all.
2. `products.require_batch_on_receipt` — a receipt line for this product with no
   batch number is refused, naming the product.
3. `products.require_batch_on_issue` — stock of this product cannot leave
   unidentified. Dispatch drops untracked stock from its candidates and comes up
   short rather than shipping goods nobody can trace; a purchase return, which
   is also stock leaving, refuses a line with no batch number.

`GET /inventory/summary/by-product` totals a product across its batches, which
is the figure that used to be a single row.

**Every response names the batch.** A stock row carries `batch_id`,
`batch_number` and `batch_expiry_date`; a movement and its ledger entry carry
`batch_id` and `batch_number`. The grain changed before the responses did, so
for a while two rows of one product in one bay were indistinguishable to any
caller and "which movements touched this batch" could only be asked in SQL —
which is the question a recall is.

**A batch stores no quantities.** It carries identity — the number, who
supplied it, when it expires, whether it is blocked — and what it is holding is
a sum of the stock rows carrying its id, computed by
`InventoryService.stock_by_batch` and reported by the batch API. It used to
store both: six columns written by the batch endpoint and reconciled against
`inventories` by nothing, so the seeded demo store held one batch claiming ten
units while no stock row anywhere had any of it (`20260813_0073` dropped them).

The consequence for callers: **a batch cannot be created holding stock.**
`POST /batch-serial/batches` no longer accepts a quantity and refuses one that
is sent. Stock arrives through a document — a goods receipt, an opening stock
batch, an adjustment — because a quantity with no movement behind it is exactly
what the ledger invariant above exists to refuse.

## The movement vocabulary

Seven types, written by the service and declared by `InventoryTransactionType`:

| Type | Written by | Effect |
| --- | --- | --- |
| `OPENING_STOCK` | posting an opening stock batch | +current |
| `GOODS_RECEIPT` | `goods_receipt` | +current, moves the average |
| `RETURN` | `purchase_return` | −current |
| `RESERVE` | `sales_order` approval | +reserved |
| `UNRESERVE` | `delivery_note`, or releasing an order | −reserved |
| `DISPATCH` | `delivery_note` | −current |
| `ADJUSTMENT` | `create_adjustment` | ± any bucket |

Plus reversals: `reverse_transaction` writes `<TYPE>_REVERSAL` and stamps
`reversal_of_transaction_id`. It refuses to reverse the *same row* twice, but
reversing a reversal is legal — so **the stored vocabulary is open-ended and no
closed set can enumerate it.** Both the filter and the response take a plain
string for that reason.

The enum previously declared fourteen members, of which the system wrote six,
and three of the written ones were missing entirely. Filtering the transaction
list by `RESERVE` was rejected as an invalid value while `RESERVATION` — which
nothing has ever written — was accepted and matched nothing. Three of the four
movement types in a live store could not be filtered for at all. The enum now
names what the service writes, and
`tests/unit/test_inventory_transaction_vocabulary.py` compares the two lists so
they cannot drift apart again.

### Not built

There is **no stock transfer between warehouses** and **no physical count
reconciliation** in this module, and no dedicated damage, expiry or quarantine
write-off movement — the buckets exist and only `ADJUSTMENT` can move them.
`GOODS_ISSUE`, `TRANSFER_IN`, `TRANSFER_OUT`, `PHYSICAL_COUNT`, `DAMAGE`,
`EXPIRY`, `QUARANTINE` and `CORRECTION` were declared in the enum and are
recorded here instead, because naming them in the API advertised features that
do not exist.

## Who writes stock

Four modules hold an `InventoryService` and call it as part of their own
transaction:

| Module | Method |
| --- | --- |
| `goods_receipt` | `record_goods_receipt` |
| `sales_order` | `record_sales_order_reservation`, `release_sales_order_reservation` |
| `delivery_note` | `record_delivery_note_dispatch` |
| `purchase_return` | `record_purchase_return` |

Plus opening stock batches, `create_adjustment` and `reverse_transaction` from
the inventory API itself. **Sales invoices do not move stock** — the delivery
note does. Invoicing is a receivable and a tax event, not a stock event.

## Valuation

A moving weighted average per firm and product, rolled forward in
`_apply_valuation`:

- a **receipt** moves the average toward the price paid;
- an **issue** consumes at the average and leaves it alone, which is what makes
  the value released equal the cost of goods sold;
- a **zero-quantity movement** — a reservation, a status change — shifts no
  value at all;
- a receipt **with no stated cost is valued at the current average**, not at
  zero, so an unpriced movement cannot silently destroy the average.

Automatic GL posting from stock movements is **not** built; see the finance note
in `CLAUDE.md`.

## Opening stock

A two-step document rather than a direct write: create a batch as `DRAFT`, then
`post` it. Posting is what emits `OPENING_STOCK` movements and stamps each line
with the `transaction_id` it produced, so day-one stock is as explainable as
everything after it. Batches can be built from JSON, CSV or XLSX
(`/opening-stock/import`).

## API surface

Everything under `/api/v1/inventory`:

| Route | Permission |
| --- | --- |
| `GET /`, `/{id}`, `/summary`, `/summary/by-firm`, `/summary/by-branch`, `/summary/by-warehouse` | `INVENTORY_VIEW` |
| `POST /`, `PUT /{id}`, `DELETE /{id}`, `POST /adjustments` | `INVENTORY_ADJUST` |
| `GET /transactions` | `INVENTORY_TRANSACTION_VIEW` |
| `GET /ledger` | `INVENTORY_LEDGER_VIEW` |
| `GET /export` | `INVENTORY_EXPORT` |
| `POST /opening-stock`, `/opening-stock/{id}/post` | `OPENING_STOCK_CREATE` |
| `PUT /opening-stock/{id}` | `OPENING_STOCK_UPDATE` |
| `POST /opening-stock/import` | `INVENTORY_IMPORT` |

## Live, in the seeded data

```
firm_shared     6 inventory rows    396 transactions    396 ledger entries
RESERVE 114 | DISPATCH 112 | UNRESERVE 112 | GOODS_RECEIPT 58

AMOX500   on hand 700.0000   valuation 700.0000 @ 99.198838
PARA650   on hand 770.0000   valuation 770.0000 @ 101.577497
```

Transactions and ledger entries are equal in number, every projection equals the
sum of its own transactions, and every valuation quantity equals stock on hand.

## Traps

- **The projection is derived; the ledger is the truth.** Anything that clears
  history must clear `inventories` with it. `generate_transaction_history.py`
  named that table `inventory_records` — which does not exist — and skipped it
  silently, so every regeneration left the old balance standing and stacked new
  receipts on top. One store reached 4,547 units on hand with 700 accounted for.
  Fixed, and guarded by `tests/unit/test_history_reset_tables.py`.
- **Do not type the movement filter as a closed set.** Reversals of reversals
  make the stored vocabulary unbounded. Both the response and the filter take a
  string; the enum documents what the service writes.
- **The valuation is per product, the projection per location.** Summing
  `inventories.current_quantity` for a product should equal
  `product_valuations.quantity_on_hand`; if it does not, a movement bypassed
  `_stage_movement`.
- **A sales invoice moves no stock.** Reconciling stock against invoices will
  not balance — reconcile against delivery notes.
- **`ADJUSTMENT` is the only way into the damaged, quarantine and in-transit
  buckets.** They are not dead columns, but nothing routine fills them.
- **Movements are timed by the statement clock, not the transaction clock.**
  `func.now()` is PostgreSQL's `transaction_timestamp()`, so every row a request
  writes shares an instant -- a delivery note's UNRESERVE and DISPATCH were
  indistinguishable and the ledger could return them either way round, showing a
  balance of 90, then 72, then 90. `inventory_transactions` and
  `stock_ledger_entries` default `created_at` to `clock_timestamp()`
  (`app/core/database/clock.py`, `20260813_0069`); every other table keeps one
  instant per request, which is the honest answer for a business record. The
  sort still ends with an id tiebreaker, because paging over a tie can hand the
  same row to two pages.

## Where the code is

| Concern | File |
| --- | --- |
| Tables | `backend/app/inventory/models/inventory.py` |
| Movements, valuation, opening stock | `backend/app/inventory/services/inventory_service.py` |
| Endpoints | `backend/app/inventory/api/router.py` |
| Contracts and the movement enum | `backend/app/inventory/schemas/inventory.py` |
| Tests | `backend/tests/unit/test_inventory_foundation.py`, `test_inventory_transaction_vocabulary.py` |
| Desktop | `desktop/lib/ui/inventory/` |

## Related

- `docs/UOM_FRAMEWORK.md` — quantities are converted to the inventory unit
  before they reach a movement
- `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md` — batch and serial tracking
- `docs/BUSINESS_PROFILE_FRAMEWORK.md` — which firms operate which capabilities
