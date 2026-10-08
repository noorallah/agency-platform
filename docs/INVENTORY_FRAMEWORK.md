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

Each bucket has its own delta on a movement and each is validated non-negative.
`available` is not a bucket and may read below zero: an order holds its whole
quantity, and the part no stock covers is a back order (see *Traps*). That is
what lets the sales flow be three movements instead of one:

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
| opening stock | resolves the number on the day-one paperwork, **creating** the batch when it is new |
| `goods_receipt` | resolves the number typed off the carton, **creating** the batch when it is new |
| `sales_order` | holds batches by earliest expiry when the order is approved |
| `delivery_note` | releases those batches and allocates by earliest expiry, one movement per batch |
| `purchase_return` | posts against the batch the line names, and **never creates** one |
| repack, kit assembly | draws what it consumes by earliest expiry; what it produces names its batch, **creating** it when the number is new |

The asymmetry between the first and last row is deliberate. Goods that have
physically arrived have to be receivable, so an unknown number on a receipt is
registered and a typo is corrected afterwards; an unknown number on a return
names stock that was never taken in, so inventing the batch would write a
delivery that did not happen and leave the new batch holding a negative
quantity. It is refused instead.

Three levels decide whether any of this applies, and all three are enforced:

1. The product's `track_batch` switch -- whether a batch may be added by hand
   for it (a receipt still creates its batch). Since 2026-10-08 this is the
   product's, not the firm's profile (`docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`).
2. `products.require_batch_on_receipt` — a receipt line for this product with no
   batch number is refused, naming the product.
3. `products.require_batch_on_issue` — stock of this product cannot leave
   unidentified. Dispatch drops untracked stock from its candidates and comes up
   short rather than shipping goods nobody can trace; a purchase return, which
   is also stock leaving, refuses a line with no batch number.

`GET /inventory/summary/by-product` totals a product across its batches, which
is the figure that used to be a single row.

**A reservation names its batch too.** Approving a sales order holds particular
stock, not just the product: the movement goes to the batch rows by earliest
expiry, so dispatch releases the batch it is about to draw from. What no batch
can cover is held with no batch, because that part is a back order and there is
nothing behind it. Before this, every reservation landed on the untracked row —
which for a batch-tracked firm holds nothing — driving its available negative
while the batch rows sat apparently free, ready to be promised to somebody else.

**Stock is a sum, not a row.** Anything asking how much of a product is on hand
in one place has to add its rows up, because a batch-tracked product is one row
per batch. The dispatch gate in `delivery_note` and the stock figures on a sales
order line both read a single row with `scalar()` until 2026-08-13 — which
returns the first of several and mentions nothing — so a line of eighty was
refused with sixty in March and forty in June, while the allocator on the next
line would have split it happily.

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

### Built since, and how it is written

Warehouse transfers (`TRANSFER_OUT` / `TRANSFER_IN`), physical counts
(`PhysicalCountService`, each difference an `ADJUSTMENT` with `reference_type`
`PHYSICAL_COUNT`), write-offs (`WRITE_OFF`) and quarantine
(`QUARANTINE_HOLD` / `QUARANTINE_RELEASE`) are all built. `GOODS_ISSUE`,
`PHYSICAL_COUNT`, `DAMAGE`, `EXPIRY`, `QUARANTINE` and `CORRECTION` were once
declared in the enum and never written; they stay out of it, because naming
them in the API advertised movements that do not exist (D-STK-10).

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

**A movement that posts no journal still keeps to the periods.** A transfer,
a quarantine hold, a transfer document, a count and a repack call
`assert_stock_date_in_open_period` (`app/finance/services/document_posting.py`)
with the date they carry, and are refused where no open accounting period
covers it -- the answer a write-off already got from its journal (D-STK-41).
The rule holds only for a firm that has opened books; one with no period at
all keeps any date. `stage_quarantine` does not ask, because its composing
caller is a goods receipt whose journal has already answered.

**A stale save is refused, except on a count sheet.** Every versioned stock
record reads `If-Match` on its edit and answers 409 to an older version. A
draft transfer's lines are replaced on each save, and the save moves the
transfer's version even when nothing on its header changed (D-STK-42). A count
sheet is the one exception, on purpose: two people fill one sheet, a save
writes only the lines it names, and so `PUT /inventory/counts/{id}` does not
read `If-Match`. Two saves of the same line keep the later figure.

**A posted count line adds up.** While a sheet is a draft, Expected is what
the row held when the sheet was drawn up. Posting measures each counted line
against what the row holds at that moment and writes that figure into
Expected, so Expected, Counted and Variance agree on the posted sheet
(D-STK-45). A line nobody counted keeps the figure it was drawn up with.

**Near expiry means one thing.** Home's stock alerts and the batch card count
a batch that still holds stock -- on the shelf, in quarantine, damaged or
blocked -- and expires inside the firm's own window (*Batch sale rules*, 30
days unless the firm set another). The expiry dashboard's 7 and 30 day cards
are named for their windows and do not follow the setting (D-STK-47).

**The stock account and the valuation can part by paise.** Stock is valued to
four places and the ledger posts two, so a movement's journal is the rounded
share of a figure the valuation keeps whole. It is a known limit (D-STK-20,
D-PRC-56): paise per product, gone when the product is sold out, and the
trial balance always balances.

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
- **The damaged bucket is filled two ways, and they are not the same place.**
  Goods that arrive damaged on a goods receipt or a transfer stay in
  `current` and are counted in `blocked` as well as `damaged`. Goods a
  customer sends back damaged **or as scrap** (D-STK-46) are in `damaged`
  alone, outside `current`, because they never go back on the shelf. A
  write-off takes that second kind first, then quarantine, then the shelf;
  it reads it as `damaged - blocked`, which can fall short on a row that
  also holds stock blocked for another reason and never runs over. Goods
  written off as given to a customer are never drawn from it.
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
- **A stock row is edited for its levels, never for what it is.**
  `PUT /inventory/{id}` changes the minimum, maximum, reorder and safety
  levels and the status. It used to write the body's product and place onto
  the row, which turned ten of one product into ten of another with no
  movement behind it (D-STK-24). Goods move by a transfer.
- **Nothing leaves that is not there, unless the product says it may.** A
  transfer, a write-off, a return to the supplier, a repack's consume line and
  a negative adjustment are each refused beyond what the location holds; only
  a product with *allow negative stock* goes below zero (D-STK-26, 27). An
  adjustment is judged against what is held, not what is free, because a
  count that finds fewer than are promised to orders still has to be posted;
  a repack is judged against what is free.
- **A batch, a lot or a serial number that anything stands on is not
  deleted.** Stock, a movement or a document naming it refuses the delete and
  says what to do instead; one typed by mistake still goes (D-STK-25). Two
  references are bare ids with no foreign key -- `physical_count_lines.batch_id`
  and the principal claims -- and the guard cannot see them.
- **A reason for an adjustment posts to an expense or income account.** A
  control account is allowed only where it is the inventory adjustment or one
  of the issue accounts; pointing a reason at Inventory made a write-off move
  the stock and not the books (D-STK-31).
- **An export is the whole list.** It reads page after page until there are
  no more, quotes a field that holds a comma, and writes a cell beginning
  `=`, `+`, `-` or `@` as text (`app/core/utils/csv_text.py`; D-STK-33, 34).
- **A serial number goes where its goods go** (D-STK-40). A serial records
  the warehouse its unit is in and a dispatch refuses a unit that is not in
  the warehouse the line ships from, so anything that moves serial-tracked
  stock between warehouses names the units and moves them
  (`app/inventory/services/transfer_serials.py`): `serial_ids` on
  `POST /inventory/transfers` and on a transfer document's lines, and
  `short_serial_ids` / `damaged_serial_ids` on its receipt. A unit in transit
  is `IN_TRANSIT`, so nothing else can pick it; a damaged one lands `DAMAGED`
  and is put back to `AVAILABLE` by hand on Serial Numbers when the blocked
  stock is released. A line dispatched before this was built carries no
  units and is received as a quantity. An opening stock line types its units
  as a goods receipt does (`opening_serials.py`,
  `opening_stock_line_serials`); a line naming none still posts, because
  stores seeded or opened before this are already in that state.
- **A hold with no stock behind it stops nobody.** An order holds its whole
  quantity at approval, so `reserved` can exceed what a row holds and the rest
  is a back order. The dispatch gate read the plain sum, and the goods that
  *were* there could not leave: four held and one order for ten could not ship
  the four; an order for three could not ship beside a later one for four
  (D-STK-39). Where a row is short of its holds, `shippable_past_back_orders`
  reads them in the order they were made -- the stock stands behind the
  earliest first -- and tells the gate and `allocate_for_dispatch` what this
  order may draw. Its own hold never stands in its own way; a later order
  still waits for an earlier one, and a sale with no order behind it still
  cannot take held stock. A row that covers its holds is read exactly as
  before. Anything else that gates on `available` for an order's own goods
  has to ask the same question.
- **A repack draws from the batches, and names no units** (D-STK-51,
  D-STK-52). A product held in batches is several stock rows, and a consume
  line naming no batch used to be read against the row with no batch: a kit
  with a batch-tracked part was refused with "free 0" beside a full shelf.
  `RepackService._lines_by_batch` splits such a line the way a dispatch is
  split (`allocate_for_repack`: earliest expiry first, expired and
  stop-selling stock passed over and named) and writes one repack line per
  batch, which is what lets a cancel put each batch back. Kits are assembled
  through the same call, so the rule is theirs too. A serial-tracked product
  is refused on either side of a repack and as a kit's part, because a
  quantity moved with no unit named leaves the units reading AVAILABLE for
  goods that are gone. A *produced* line of a batch-tracked product names
  the batch it goes into (D-STK-53): by id, or by a number that
  `resolve_for_receipt` finds or opens with the line's dates, so a batch
  made by a repack is held to the same dates as one made by a receipt. A
  line naming none is refused. A broken kit gives a batch-tracked part back
  to the batch its most recent assembly in that warehouse drew it from
  (the last line of that repack), unless the request names another in
  `part_batches`; with neither it is refused. A kit that is itself kept in
  batches takes its batch on the assembly request and is not assembled by
  a delivery note, which has nowhere to name one.
- **A delivery note line that names no bin asks the warehouse**
  (D-STK-54). The warehouse's own row leaves first, because the
  order's hold is there; what it cannot cover is drawn from the bins by
  the product's issue rule across them, and each movement names the bin
  it left (`InventoryService.allocate_across_bins`). The line keeps no
  bin of its own, so a return of those goods comes back to the
  warehouse's own row. A unit with a serial number and a line whose
  batches a person chose are not drawn from bins: the line names the
  bin, and a refusal says what stands free in each. An order's hold is
  not moved onto a bin, so an order that names no bin does not keep
  goods in a bin from a note that names it.

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
