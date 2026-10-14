# Enterprise Batch, Lot, Serial & Expiry Management Architecture

## Phase 16B – Enterprise Traceability Framework

---

## Overview

Phase 16B introduces a complete enterprise-grade traceability layer above the Inventory Foundation (Phase 16A). It supports Batch, Lot, Serial Number, and Expiry tracking for multiple industries without redesigning any existing modules.

---

## Architecture

```
Product (products)
    ↓  [tracking flags: track_batch, track_lot, track_serial, track_expiry, ...]
Inventory (inventories)
    ↓
Batch / Lot (batches / lots)          ← NEW (Phase 16B)
    ↓
Serial Numbers (serial_numbers)       ← NEW (Phase 16B)
    ↓
Inventory Transactions (inventory_transactions)
  [+ optional batch_id / lot_id / serial_id FK]  ← EXTENDED
    ↓
Stock Ledger (stock_ledger_entries)
    ↓
Future: Purchase · Sales · Manufacturing · Returns · Warranty
```

---

## Database Design

### Table: `batches`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | Multi-tenant |
| batch_number | VARCHAR(100) | Unique per firm |
| supplier_batch | VARCHAR(100) | External reference |
| internal_batch | VARCHAR(100) | Internal reference |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| branch_id | UUID FK → branches | |
| storage_node_id | UUID FK → warehouse_storage_nodes | |
| vendor_id | UUID FK → vendors | Optional |
| manufacturing_date | DATE | |
| expiry_date | DATE | Required for medical/food |
| best_before_date | DATE | |
| shelf_life_days | INTEGER | |
| mrp | NUMERIC | The MRP printed on the batch, tax included, per stock unit; from the goods receipt line (A41, migration 0225) |
| selling_price | NUMERIC | The batch's own rate before tax, per stock unit; used when `price_from_batch` is on (A41) |
| status | ENUM | available, reserved, blocked, quarantine, expired, damaged, recalled, returned, destroyed |
| remarks | TEXT | |
| created_by / updated_by | UUID | Audit |
| created_at / updated_at / deleted_at | TIMESTAMP | Soft delete |

A batch holds **no quantity columns**. What a batch holds is the sum of its
`inventories` rows (`inventories.batch_id`), bucket by bucket -- current,
reserved, quarantine, damaged, blocked -- so there is one place a quantity
lives and nothing to fall out of step with it.

Creating, changing and deleting a batch, lot or serial number is audited as
`batch.created` / `batch.updated` / `batch.deleted` (likewise `lot.*` and
`serial_number.*`), with the record's fields in `after_data` (D-STK-10).

#### The lot's columns and tables (L2 step 1, migration 0369)

The tables cost per purchase lot is built on
(`docs/design/LOT_COST_DESIGN.md`, section 3.2). **Nothing reads them yet**:
every firm costs on one moving average per product, as before.

| Column on `batches` | Type | Notes |
|---|---|---|
| lot_reference | VARCHAR(40) | Our own reference, one per lot, unique per firm among live rows (`UQ_batches_firm_lot_reference_active`). Every batch that existed was numbered `B000001` onwards per firm, in the order made. Empty on a batch made since, until receiving issues one (step 3) |
| per_purchase_line | BOOLEAN | False on every batch today. True on a lot made for one purchase line |
| has_printed_batch | BOOLEAN | True today. False where the goods carry no printed batch |
| received_on | DATE | The day the lot arrived |
| source_document_type / _id / _line_id / _number | VARCHAR(30), UUID, UUID, VARCHAR(80) | What made the lot. Bare ids, no foreign key |

`UQ_batches_firm_batch_product` (firm, batch number, product) is now a
**partial unique index** covering rows where `per_purchase_line` is false.
For every batch that exists it refuses exactly what the old constraint
refused; a lot of one purchase line may repeat a printed number.

| Table | Holds |
|---|---|
| `batch_valuations` | What one lot is worth: `quantity_on_hand`, `unit_cost`, `total_value`, one row per `batch_id`. The shape of `product_valuations` one level down. Cleared with it by the history reset |
| `stock_lot_settings` | One live row per firm: `costing_method` (`AVERAGE` or `BY_LOT`), `switched_on`, `allow_billing_without_stock`. A firm with no row is on Average. No endpoint writes it yet |

#### How a lot is valued (L2 step 2)

`_apply_valuation` in `backend/app/inventory/services/inventory_service.py`
reads the method off the item's `product_valuations` row, which it already
loads. `WEIGHTED_AVERAGE` (every item today) is valued as before and writes
no `batch_valuations` row. `BY_LOT` goes to `_apply_lot_valuation`:

- goods arrive in the lot at the cost stated, and the lot's `unit_cost`
  becomes its value over its quantity, held at six decimals;
- goods leave at the lot's own cost, never the item's average, and the issue
  that empties the lot takes everything left, so a lot closes at exactly zero;
- goods coming back with no cost stated come back at the lot's cost;
- a reversal moves the value written on its original's stock ledger row, not
  today's cost, and the lot's cost is worked out again from what is left;
- the item's own row is still kept (quantity, value, and the average the two
  give) and moves by the same amount as the lot, so it is always the sum of
  its lots;
- a movement that names no lot is valued at the average, as before.

Nothing stamps an item `BY_LOT` yet but `tests/unit/test_lot_valuation.py`;
the switch-over (section 4.4 of the note) will. A landed cost still adds to
the item's figure only, until the step that puts it on the lot.

#### Stock arriving in lots (L2 step 3, migration 0379)

Every batch has a `lot_reference`, NOT NULL. `LotNumbering` in
`backend/app/inventory/services/lots.py` issues it from the firm's
*Stock Lot* series (prefix `LOT`), inside the caller's work and without
committing, the way a stock movement takes its number. Batches older
than the series keep the `B000001` numbers the migrations gave them.
The two creators are `create_batch` (the batch master) and
`_new_receipt_batch`, which `resolve_for_receipt` and `open_lot` share.

`costs_by_lot(session, firm_id)` reads `stock_lot_settings`; no row is
Average. For a firm on Average nothing else changed: a receipt or an
opening stock line joins the batch of that number or registers it, and
`resolve_for_receipt` never returns a lot of one purchase line.

For a firm costing by lot:

- `GoodsReceiptService._post_inventory` calls `open_lot` for every
  stocked line: always a new row, `per_purchase_line` true, the source
  `GOODS_RECEIPT` with the receipt, its line, its number and its date.
  Accepted, free, rejected and damaged units of the line all sit in it.
  Service and capital goods lines make none.
- A line with no printed batch, or of a product that keeps no batches,
  gets a lot whose `batch_number` is the lot reference and whose
  `has_printed_batch` is false.
- `stage_cancel` removes the receipt's lots (soft delete; the movements
  still name the row) after the stock has gone back. It is refused when
  any movement other than the receipt's own and its inspection holds
  names one of the lots.
- An opening stock line makes a lot the same way, source
  `OPENING_STOCK`, received on the line's `purchase_date` or the
  document's date. One document may hold the same item and batch twice.
- `valuation_for` stamps a new item's valuation row `BY_LOT`.

`opening_stock_lines` carries `mrp`, `selling_price`, `ptr`, `pts`,
`purchase_date` and `supplier_bill_reference`, for every firm; the file
template has a column for each. The key
`UQ_opening_stock_lines_batch_product_location` is dropped and a firm on
Average is refused the same item twice by the service.

#### Choosing the lot (L2 step 4)

For a firm costing by lot, lots leave nearest expiry first (no expiry
last), then oldest `received_on` (none last), then by `lot_reference`:
`lot_tie_break()` in `backend/app/inventory/services/lots.py`, ranked
explicitly so PostgreSQL and SQLite agree. `_expiry_ranked_rows` uses it
for reservation, release and dispatch; under the FIFO issue rule it ranks
by received date ahead of `created_at`. A firm on Average keeps the order
it had: expiry, then batch id.

`GET /api/v1/batches/availability` lists the lots in that order, one row
each, with `lot_reference`, `received_on` and `has_printed_batch` (false:
`batch_number` is our reference and no screen shows it as a batch). For a
by-lot firm each row carries `pick_group`, the same for lots that agree on
batch, expiry, MRP and the selling prices: the picker shows those as one
row and takes them in the order listed. `unit_cost` comes from
`batch_valuations` and only to a holder of `PRODUCT_VIEW_COST_PRICE`;
everybody else, and every firm on Average, gets null.

#### Selling by lot (L2 step 5)

Dispatch writes, on each `delivery_note_line_batches` row, the movement that
carried the lot out (`inventory_transaction_id`) and what its units cost off
the stock ledger (`cost_amount`, migration `20261014_0385`). A lot drawn
from two bins is still one row, with its first movement and the cost of
both. Rows chosen by a person are stamped at dispatch; rows nobody chose are
written then, as before. Every firm gets them, Average included.

A bill line's `cost_amount` is its note line's lots summed, pro rata to
what it bills (`_lot_costs` in `sales_invoice_service.py`). Only a line
whose lots cover all it delivered and all carry a cost reads that way; any
other line (dispatched before 0385, or stock with no batch) reads the
note's cost per product off the ledger, as it did. So two lines of one item
from two lots carry two costs, and two lines of one item on Average no
longer each carry the cost of both (D-SELL-99).

The challan and the bill print lots that agree on printed batch, expiry,
date of making and MRP as one row with their total (`_merged` in
`challan_print_service.py`), and a lot with `has_printed_batch` false prints
no batch, so our own reference never reaches paper. No response carries a
lot's cost yet: the screens (step 11) and L3's margin read it with the
`PRODUCT_VIEW_COST_PRICE` check.

#### Returns by lot (L2 step 6)

A firm costing by lot takes a customer's goods back into the lots the
source line shipped (`_lots_going_back` in `sales_return_service.py`): the
delivery line's `delivery_note_line_batches` rows, less what live returns of
the same goods (off the note or off a bill of it) already put back. The last
lot taken is the first refilled, read as the dispatch order backwards
(nearest expiry, then oldest received, then our reference). Each lot's units
come back at the cost they left with, the row's `cost_amount` over its
quantity; a row with no cost (before 0385) leaves the lot's own cost. A line
that names a batch goes back only into the shipped lots of that batch, by
printed number or by our reference, and a batch the line did not ship is
refused. A line that fits one lot moves once in the unit it was typed in; a
line split over lots moves once per lot in the stock unit, the sellable,
damaged and scrapped parts handed out lot by lot in that order. Whatever the
shipped lots cannot take comes back with no lot, at the item's average.

Each lot refilled is a `sales_return_line_batches` row (migration
`20261014_0386`): quantity in stock units, the movement, and what it carried
off the stock ledger. Cancelling reverses every movement the line made (its
own `inventory_transaction_id` and every lot row's), each at the value its
original carried, and marks the rows deleted, so the lots hold exactly what
they held before and the goods may come back again. A serial-tracked line,
and every line of a firm on Average, comes back in one movement as before;
on Average a line that names a batch also writes its one lot row.

A purchase return leaves the lot its receipt line made: where the receipt
line resolved a batch and the return names no other, `_resolve_return_batch`
in `purchase_return_service.py` takes that row, not a lookup by number. In a
by-lot firm a printed number can name several lots and unprinted goods carry
none, so the number alone took another delivery's lot or the untracked row.
The movement leaves at the lot's own cost, so a return of what was bought
leaves no variance.

#### The rest of stock by lot (L2 step 7)

Section 3.6 of `docs/design/LOT_COST_DESIGN.md`, in
`inventory_service.py`, `stock_transfers.py` and `repacking.py`. No
migration. A firm on Average moves exactly as before.

- **A movement that names no lot.** For a firm costing by lot every unit is
  in a lot, so a write-off, an adjustment down, a quarantine hold or release,
  a transfer and a transfer document's line that name none take the first
  lot, in the order goods leave (nearest expiry, then oldest received), that
  holds the whole quantity at that place (`_lot_to_take`). One movement names
  one lot: a quantity no single lot holds is refused with each lot and what
  it holds, to be taken lot by lot. Where only the row with no batch (stock
  from before the switch-over) holds it, that row is used as before. A count
  line counts one stock row, so one that counts short stays on that row.
- **Value.** A lot named leaves at its own cost (step 2). A transfer's
  arriving leg, and a transfer document's in-transit leg, carry exactly the
  value the leaving leg took (`_Movement.carries`), so the lot's cost stands
  to the paisa; on Average they still arrive at the average. A hold moves no
  value.
- **Stock found.** An adjustment up, or a count finding more, that names no
  lot opens a new lot, source `ADJUSTMENT`, pointing at the movement
  (`_found_lot`, `_trace_lot_to`), at the cost typed in the adjustment's new
  `unit_cost`, else the item's newest valued lot's cost, else the average.
  A named lot takes goods at its own cost. `unit_cost` is refused anywhere
  else: on a named lot, on a movement down and on a firm on Average.
- **Repack and kits.** A consume line naming no batch is drawn from lots as a
  dispatch is, whether or not the item is batch-tracked; each leaves at its
  lot's cost. Each produce line opens a new lot, source `REPACK`, costed at
  its share of the value used; a batch the line names lends the lot its
  printed number, dates, MRP and selling price and is never joined. A cancel
  removes the repack's lots, as a receipt's cancel does.
- **Negative stock.** Refused for a firm costing by lot even where the item
  allows it, in `_refuse_below_zero` (adjustment, repack) and on a purchase
  return. Billing without stock, where the firm allows it and the bill maker
  confirms, is step 7a.

#### Billing without stock (L2 step 7a)

Section 3.7 of `docs/design/LOT_COST_DESIGN.md`, in
`app/inventory/services/lot_shortfalls.py`, the dispatch
(`delivery_note_service.py`), the goods receipt, the sales return and the
year-close. Migration `20261014_0387` (`lot_shortfalls`,
`lot_shortfall_settlements`). A firm on Average, and a by-lot firm that has
not switched it on, are refused exactly as before.

- **The switch.** `stock_lot_settings.allow_billing_without_stock` and the
  item's own `allow_negative_stock`, both on, on a firm costing by lot
  (`LotShortfallService.may_bill_short`). A line whose batches or serial
  units were chosen is never billed short: what was chosen has to be there.
  `PUT /inventory/lot-settings` sets the switch (step 9).
- **The question.** A dispatch that needs more than the lots hold answers 422
  "Line n: no stock of ... Bill anyway?" with `details.confirm` =
  `BILL_WITHOUT_STOCK`, until the caller sends `bill_without_stock=true`
  (`app/inventory/api/without_stock.py`) on `POST /delivery-notes/{id}/dispatch`,
  `.../dispatch-and-invoice` or `POST /sales-invoices/{id}/approve`. Who
  confirmed and when is kept on the shortfall row.
- **The cost for now.** What the lots hold leaves first, as any dispatch.
  The rest leaves the line's place with no lot named, taking that row below
  zero, at the item's newest lot cost (`newest_lot_cost` in `lots.py`), or
  its average where no lot of it was ever valued (`_ship_short`). One
  `lot_shortfalls` row per such movement. What still waits is derived: the
  row's quantity less its live `lot_shortfall_settlements`.
- **When the purchase is typed.** Completing a goods receipt takes each
  stocked line into its lot (step 3), then covers the units waiting in that
  warehouse, oldest sale first, out of what the lot holds free
  (`settle_from_lot`): one `LOT_SETTLEMENT` pair per share, out of the lot at
  its cost and onto the emptied row at exactly the share of the sale's cost
  it replaces (`_Movement.value`), and a `delivery_note_line_batches` row so
  the sale's line names the lot. The lot's cost less the cost used is posted
  on the receipt's date (`post_cost_correction`, reference `<GRN>-LS`): Dr
  cost of goods sold, Cr Inventory, or the other way. A receipt whose lot
  covered a sale can no longer be cancelled whole, as for any lot that moved.
- **A return first.** A sales return of the line brings the waiting units
  back first, with no lot, at the cost they left at, and records a
  `RETURNED` settlement; cancelling the return reverses that movement at the
  same value and deletes the row, so the units wait again.
- **Nothing waits unseen.** `GET /inventory/lot-shortfalls` lists every
  open row with its age (cost only to `PRODUCT_VIEW_COST_PRICE`); its screen
  is step 11. A financial year cannot be closed while a row dated in it is
  open (`assert_none_open`, called by `close_financial_year`).
- **Books.** Until settled the item's value is the lots less the units owed
  (it may read below zero). Once settled the cost of the sale is what its lot
  cost: the sale's own movement plus the correction. Stock ageing treats a
  `LOT_SETTLEMENT` as internal, like a transfer.

### A bill's rate and a landed cost onto the lot (L2 step 8)

`docs/design/LOT_COST_DESIGN.md`, section 3.3 and decision 3. For a firm
costing by lot, value that arrives after the goods lands on the lot the
goods came in, never on the item as a whole, so the Inventory account stays
the sum of the lots. A firm on Average is untouched.

- **A value-only movement on a lot.** `InventoryService.stage_revaluation`
  moves value and no quantity. Where the item is costed by lot and the
  batch it names has a `batch_valuations` row, the value goes onto that lot
  (its value and unit cost move) and the item's running figure moves with
  it; the ledger entry's `unit_cost` records what each unit then in the lot
  gained. A lot with nothing left in it cannot carry value.
- **The supplier's bill at another rate** (`app/purchase_invoice/services/lot_rate.py`).
  At approval, per bill line raised off a receipt line with a valued lot:
  the bill line's net before tax (in rupees) less the receipt's movement
  cost for the units billed (pro rata, as the accrual clears it), times the
  share of the receipt line's units the lot still holds, goes onto the lot
  as a `COST_CORRECTION` movement dated the bill (reference type
  `PURCHASE_INVOICE`). The journal gains an Inventory leg for it and the
  variance shrinks by as much; the share for units already gone stays
  purchase price variance. A cheaper bill lowers the lot, never below
  nothing.
- **Cancelling the bill** takes back off each lot what it still holds of the
  correction (`value_left_in_lot`: the per-unit gain times the units the lot
  holds now, reference type `PURCHASE_INVOICE_CANCEL`). The reversal credits
  Inventory with that and sends the rest -- what left with units since -- to
  purchase price variance (`reverse_with_stock_back`).
- **A landed cost and a bill of entry** (`land_on_receipt_lines`) read the
  receipt line's own lot for the units still held, not the item's quantity
  on hand: freight on a lot that is gone is all cost of goods sold even when
  newer lots of the item are on the shelf. Cancelling takes back only what
  the lot still holds (`take_off_receipt_lines` returns what came off) and
  the reversal sends the rest to cost of goods sold, where the units sold
  since took it (`reverse_landing`).
- The stock valuation report counts a `COST_CORRECTION` as value in with no
  quantity, as it does a `LANDED_COST`.

### The switch-over (L2 step 9)

`docs/design/LOT_COST_DESIGN.md`, section 4.4, in
`app/inventory/services/lot_switch_over.py` (`LotSwitchOverService`). No
migration: `stock_lot_settings` already carries `costing_method`,
`switched_on` and `allow_billing_without_stock`.

- **Routes** (`/api/v1/inventory`). `GET /lot-settings` (`INVENTORY_VIEW`)
  and `PUT /lot-settings` (`INVENTORY_MANAGE_SETTINGS`, body
  `{allow_billing_without_stock}`) answer `{costing_method, switched_on,
  allow_billing_without_stock, version}` with the version as an `ETag`.
  `GET /lot-settings/switch-preview?on=` answers `{on, suggested_on, items,
  lots, quantity, stock_value, refusals}` and writes nothing. `POST
  /lot-settings/switch` with `{on}` switches, or answers 422 naming every
  refusal (also in `details.refusals`).
- **What the switch does**, in one transaction committed once: the settings
  row is locked (made if missing); each batch that holds stock becomes a lot
  (source `CARRIED_FORWARD`, its `received_on` kept, else the day); each
  item's stock that names no batch becomes one new lot with our reference
  and no printed batch, and every such stock row, in any warehouse, now names
  it; each lot gets a `batch_valuations` row at the item's average, the
  rounding on its largest lot; every `product_valuations.costing_method` of
  the firm reads `BY_LOT`; the firm reads `BY_LOT` from the day. Each item's
  lots are then compared with its value and quantity, and any difference
  undoes the whole switch. No journal, no re-valuation, no saved bill line
  touched.
- **Rule 5.** `InventoryService._stage_movement`, the one place a movement
  is staged, refuses any movement dated before `switched_on`
  (`switch_over_day` in `lots.py`). A firm on Average, or one that started by
  lot, has no such day.
- **The Settings screen.** The Stock subject's `costing-method` step reads
  "Average" or "By lot since <day>" (`app/settings_sections/services/stock.py`).

DECIDED: (57) A lot's quantity is what the firm **owns** of it: the sum over
its movements of `owned_quantity_delta`, else `current_quantity_delta`,
leaving out quarantine holds and releases -- exactly what the valuation
rolls. The buckets alone cannot say it (a damaged return is owned without
being on the shelf).

DECIDED: (58) Refused, in plain words, naming the items: already by lot; a
day after today; a day before the latest stock movement; an item below zero
(any lot, any stock row, or its valuation); an item whose movements do not
add up to the quantity it is valued at; and an item with unbatched stock
reserved for an order or in transit -- releasing or receiving it later would
look for a stock row with no batch that no longer exists.

DECIDED: (59) Every lot's unit cost is the item's average as stored (six
places). Each lot's value is quantity times that, to the storage scale
(`quantize_money`, four places), and the residual goes on the lot holding
most (ties by id), so the lots sum to the item's value exactly; the issue
that empties a lot takes the residual with it.

DECIDED: (60) A batch turned into a lot keeps `per_purchase_line` false, so
the firm's "same number, same batch" key still holds for it; the new lot for
unbatched stock is made as any lot is (`open_lot`), with no branch or
warehouse, as it spans them. Both name the settings row as their source
document, numbered `CARRIED FORWARD <day>`; each batch changed is audited
(`batch.carried_forward`), and the switch itself
(`stock_lot_settings.switched_to_by_lot`) with the counts and value.

DECIDED: (61) The permission is `INVENTORY_MANAGE_SETTINGS`, not a finance
code as section 4.4 rule 1 says: the method is a stock setting kept on an
inventory table, and the code is already held by the firm administrator and
withheld from the inventory manager. No new code.

DECIDED: (62) `PUT` writes only `allow_billing_without_stock`, refused while
the firm is on Average where it has no effect. A firm with no row reads
Average with `version` null and no `ETag`.

DECIDED: (63) The suggested day is the start of the financial year the books
hold for today, else the firm's own start month; with no `on` the preview
previews that day. The stock value goes only to a holder of
`PRODUCT_VIEW_COST_PRICE`, as the shortfall list's cost does.

DECIDED: (64) A reversal of a movement made before the switch is dated the
day it is made, as every reversal is, so rule 5 does not stop it; it moves
the stock row the original moved, which now names the lot.

### Reports by lot (L2 step 10)

`docs/design/LOT_COST_DESIGN.md`, section 5 and section 3.7, in
`app/inventory/services/stock_valuation.py` (`lot_stock`,
`StockValuationService.lots`) and `app/inventory/services/stock_ageing.py`.
No migration. A firm on Average reports exactly as before.

- **Stock valuation.** For a firm costing by lot an item's line is the sum of
  its lots as on the day, and the cost rate is that value over the quantity.
  Units billed before their lot (step 7a) and still waiting on the day are
  a line of their own, `row_type` `OWED`, *Units owed to lots*, before the
  grand total, so the total still compares with the Inventory account.
- **The drill-down.** `GET /api/v1/inventory/reports/stock-valuation/lots`
  (`INVENTORY_VIEW` or `REPORT_VIEW`, as the valuation; `to_date`,
  `warehouse_id`, `product_id`): one row per lot holding stock with its
  reference, printed batch (blank where the goods carry none), received and
  expiry dates, MRP, quantity, cost rate, value and value at MRP. The rows
  add up to the grand total less the units owed. Desktop entry
  `stock-valuation-lots` in `report_catalog.dart`.
- **Stock ageing.** Each lot's quantity is aged from its own `received_on`
  and valued at its own cost: exact, no FIFO assumption.

DECIDED: (65) A day before the firm switched (`switched_on`) is valued and
aged on Average, as the firm was then, and the drill-down lists nothing for
it.

DECIDED: (66) A lot's value on a day is what `batch_valuations` holds now
less the signed value of the lot's movements dated after the day, added up
by the database -- read backwards, because a lot carried forward at the
switch-over has movements from before it that name no batch. A lot's
quantity is the sum of what its movements did to the owned quantity up to
the day, matched through the stock row (the movement's batch, else its
row's, which the switch-over pointed at the lot). A movement's signed value
is its `total_cost` with the direction of its owned delta, else its shelf
delta; a value-only movement (landed cost, correction) carries its own sign.

DECIDED: (67) The units owed are each shortfall dated on or before the day
less its settlements dated on or before it, at the cost used; quantity and
value are stated negative, since they are what the books hold below the
lots. With a warehouse named, only that warehouse's. A settlement deleted by
a cancelled return reads as never made, also for a day before the cancel.

DECIDED: (68) Stock that names no lot and is not owed -- a customer's goods
back from a sale that left with no lot (decision 29) -- is counted in the
item's line and listed in the drill-down as one row with no reference, so
the drill-down still adds up to the item.

DECIDED: (69) With a warehouse named, a lot's value is its whole value pro
rata to the units in that warehouse: a lot has one cost.

DECIDED: (70) An item is worth its lots' value rounded once to the books'
two places; each lot is rounded on its own and the residual put on the lot
worth most, so the drill-down adds up to the item to the paisa.

DECIDED: (71) The stock statement (`StockStatementService`) folds the units
owed back into each item's line (`valuation(..., owed_apart=False)`), so its
opening, in, out and closing still add up movement by movement.

DECIDED: (72) On a firm on Average the drill-down answers an empty list:
the books hold one average per item, and listing batches at it would show a
breakdown nothing records.

DECIDED: (73) The drill-down's cost rate and value are left out (null), not
zeroed, without `PRODUCT_VIEW_COST_PRICE`, as the shortfall list's are. The
valuation route itself still sends cost to every holder of its permissions,
unchanged.

DECIDED: (74) A by-lot item holding no units but some value (a lot emptied
with value left on it) keeps its line, so the total never parts from the
books without saying where.

DECIDED: (75) In the ageing a lot with no received date, and stock that
names no lot, go in the oldest bucket. Slow-moving and dead stock still value
at the item's average; this step does not change them.

**Margin by lot** (`GET /api/v1/sales-invoices/reports/margin-by-lot`,
`app/sales_invoice/services/lot_margin.py`) gives one row per item and lot:
quantity sold, sales value, cost, margin and margin %, the last three only to
a holder of `PRODUCT_VIEW_COST_PRICE`.

DECIDED: (76) It counts bills APPROVED or CLOSED by bill date, lines shipped
by a delivery note only, and returns COMPLETED or CLOSED by return date, as
the sales analysis does. A lot's quantity and cost are its
`delivery_note_line_batches` row scaled by the share billed; its sales value
is the line's taxable value split by lot quantity; a return takes back
quantity, value and cost per lot from `sales_return_line_batches`. A lot with
any row holding no cost shows no cost rather than zero. A firm on Average
sees one row per batch for batch-tracked items, at the cost they left with.

**The price floor** (`app/sales_order/services/price_floor.py`) judges a line
of a by-lot firm against the cost of its lots where they are known: the batch
an order line pins, or the lots its bill's delivery note line recorded.

DECIDED: (77) Several lots are a quantity-weighted mean; a line with any lot
holding no cost, or no lot at all, is judged on the item's average as before.
A firm on Average never reads lot costs.

### The lot's trail (L2 step 11)

`docs/design/LOT_COST_DESIGN.md`, section 6 row 11.
`GET /api/v1/batch-serial/batches/{batch_id}/trail` (`BATCH_VIEW`, as the batch
itself; 404 for an unknown or another firm's batch) answers `LotTrail`: the
batch as `GET /batches/{batch_id}` gives it, its lot reference, whether the
goods carry a printed batch, the day it arrived, what made it
(`source_type`), its unit cost now from `batch_valuations`, and its events
oldest first. Built in `app/batch_serial/services/lot_history.py` on the
shape of `serial_history`: one read for the movements, one per document type
for the headers, one each for supplier and customer names, one for the
supplier's bills and one for the sales bills. No migration.

Event types: `GOODS_RECEIPT`, `OPENING_STOCK`, `PURCHASE_INVOICE`,
`DELIVERY_NOTE`, `SALES_INVOICE`, `SALES_RETURN`, `PURCHASE_RETURN`,
`STOCK_TRANSFER`, `ADJUSTMENT`, `REPACK`, `COST_CORRECTION`, `OTHER`.

DECIDED: (78) The movements are the `inventory_transactions` rows carrying
the lot's `batch_id`. An event's quantity is what the valuation counts: the
owned delta where the movement records one, else the shelf delta, so + is
into the lot and - out of it. A movement that changed neither (a reservation
or its release, a move between buckets that owned nothing new) is not listed.
A cost correction or landed cost is listed as `COST_CORRECTION` at zero, and
a reversal (`X_REVERSAL`) as the type it reverses, with its own sign.

DECIDED: (79) A movement names its document by `reference_type` and number,
not by id, so the document is found by its number within the firm. Where
none is kept under it (a write-off, a receipt recorded straight to stock)
the event has no `document_id` and shows the movement's own number and date.
`reference_type` decides the event type where it names a document; a
write-off or adjustment is `ADJUSTMENT`, a transfer leg `STOCK_TRANSFER`,
anything else `OTHER`.

DECIDED: (80) The supplier's bill is each APPROVED or CLOSED purchase
invoice line billing a receipt line that holds the lot (the receipt line's
`batch_id`, or the lot's own source line), at quantity zero and its net
before tax. The sales bill is each APPROVED or CLOSED sales invoice line
continuing a delivery note line that drew from the lot, the join
`LotMarginService` makes, at zero and the line's value before tax split by
the lot's share of the note line's quantity, as the margin by lot splits it.
Drafts and cancelled bills are not listed.

DECIDED: (81) `cost_amount` is the ledger entry's `total_cost` for a
movement, as stored, and the bill line's amount for a bill. It and
`unit_cost` are left out (null), not zeroed, without
`PRODUCT_VIEW_COST_PRICE` -- the sales bill's amount too, since one field
carries both.

DECIDED: (82) Order: the arrival -- the first movement into the lot -- comes
first; then by date, and within a day the movement, then the bill, then the
cost the bill moved. Party: the supplier on a receipt, supplier's bill or
purchase return, the customer on a delivery note, sales bill or sales
return, none otherwise (a cost correction included).

DECIDED: (83) `has_printed_batch` is the batch's own column, the one
`batch_availability` reads; there is no second rule.

### Table: `lots`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | |
| lot_number | VARCHAR(100) | Unique per firm |
| lot_type | ENUM | production, mixing, manufacturing, assembly |
| parent_lot_id | UUID FK → lots | Self-referential for lot hierarchy |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| quantity | DECIMAL | |
| available_qty | DECIMAL | |
| status | ENUM | open, closed, quarantine, recalled, destroyed |
| remarks | TEXT | |
| Audit columns | | |

### Table: `serial_numbers`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| firm_id | UUID FK → firms | |
| serial_number | VARCHAR(200) | Unique per firm among live rows, case ignored (`UQ_serial_numbers_firm_serial_active`, PG-10) |
| product_id | UUID FK → products | |
| warehouse_id | UUID FK → warehouses | |
| branch_id | UUID FK → branches | |
| inventory_id | UUID FK → inventories | |
| batch_id | UUID FK → batches | Optional link to batch |
| manufactured_date | DATE | |
| warranty_start | DATE | |
| warranty_end | DATE | |
| current_owner | VARCHAR(255) | Customer / department |
| asset_ref | VARCHAR(100) | Asset management reference |
| status | ENUM | available, reserved, sold, installed, returned, repaired, scrapped, lost |
| remarks | TEXT | |
| Audit columns | | |

### Extended: `inventory_transactions`

Three nullable FK columns added:

| Column | Type | Notes |
|---|---|---|
| batch_id | UUID FK → batches | Optional |
| lot_id | UUID FK → lots | Optional |
| serial_id | UUID FK → serial_numbers | Optional |

### Extended: `products`

Eleven boolean tracking flags added:

| Column | Default |
|---|---|
| track_batch | false |
| track_lot | false |
| track_serial | false |
| track_expiry | false |
| track_manufacturing_date | false |
| track_warranty | false |
| allow_negative_stock | false |
| require_batch_on_receipt | false |
| require_batch_on_issue | false |
| require_serial_on_receipt | false |
| require_serial_on_issue | false |

---

## REST APIs

Base: `/api/v1/batch-serial`

### Batch Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /batches | List batches (paginated, filterable) |
| POST | /batches | Create batch |
| GET | /batches/{id} | Get batch detail |
| PUT | /batches/{id} | Update batch |
| DELETE | /batches/{id} | Soft delete batch |
| GET | /batches/summary | Expiry/status summary |
| GET | /batches/availability | What a sale line can take from each batch, with expiry and days left (79 row 1) |
| GET / PUT | /sale-settings | The firm's batch rules, `batch_sale_settings` (79 row 6) |

### Lot Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /lots | List lots |
| POST | /lots | Create lot |
| GET | /lots/{id} | Get lot detail |
| PUT | /lots/{id} | Update lot |
| DELETE | /lots/{id} | Soft delete lot |

### Serial Number Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /serials | List serial numbers |
| POST | /serials | Create serial |
| GET | /serials/{id} | Get serial detail |
| PUT | /serials/{id} | Update serial |
| DELETE | /serials/{id} | Soft delete serial |
| GET | /serials/{id}/trail | The unit and every document it moved on, its receipt first (PG-10) |

### Dashboard Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /expiry-dashboard | Expiry summary (today/7d/30d/expired/quarantine/recalled) |

### Query Parameters (batches / lots / serials)

- `firm_id` (required)
- `product_id`, `warehouse_id`, `branch_id`, `vendor_id`
- `status`
- `expiry_before`, `expiry_after` (batches)
- `search` — matches batch/lot/serial number
- `page`, `page_size`

---

## RBAC Permissions

```
BATCH_VIEW      — view batch list and details
BATCH_CREATE    — create new batches
BATCH_UPDATE    — edit batch details
BATCH_DELETE    — soft-delete batches
BATCH_RESTORE   — restore deleted batches
SERIAL_VIEW     — view serial numbers
SERIAL_CREATE   — create serial numbers
SERIAL_UPDATE   — update serial numbers
SERIAL_DELETE   — delete serial numbers
SERIAL_RESTORE  — restore deleted serial numbers
```

---

## Desktop UI

### Module Catalog Tabs (Inventory Module)

| Tab ID | Section | Description |
|---|---|---|
| `batches` | BatchSerialSection.batches | Batch Master list |
| `lots` | BatchSerialSection.lots | Lot Master list |
| `serials` | BatchSerialSection.serials | Serial Number list |
| `expiry-monitor` | BatchSerialSection.expiryMonitor | Expiry dashboard |

### BatchManagementPage Sections

**Batches tab**
- `EnterpriseDataGrid<BatchRecord>` — Batch#, Product, Qty, Expiry, Status, Warehouse
- `FilterPanel` — status, warehouse, product, expiry range
- `DetailsPanel` — full batch details including date fields, quantities
- Context actions: `view`, `edit`, `delete`
- `WorkspaceContextAction.edit` opens `_BatchFormDialog`

**Lots tab**
- `EnterpriseDataGrid<LotRecord>` — Lot#, Type, Product, Qty, Status
- `FilterPanel` — status, lot type
- `DetailsPanel` — lot fields, parent lot
- `_LotFormDialog`

**Serials tab**
- `EnterpriseDataGrid<SerialRecord>` — Serial#, Product, Status, Warranty End
- `FilterPanel` — status, product
- `DetailsPanel` — serial fields, warranty info
- `_SerialFormDialog`

**Expiry Monitor tab**
- `ExpiryDashboard` widget showing 6 metric cards:
  - Expired Today, Expire in 7 Days, Expire in 30 Days
  - Total Expired, Quarantine, Recalled

---

## Business Profile Integration

The framework is driven by Business Profile feature flags. No values are hardcoded.

| Profile | Batch | Lot | Serial | Expiry |
|---|---|---|---|---|
| Medical/Pharmacy | ✓ Required | Optional | Optional | ✓ Required |
| Food | ✓ Required | Optional | ✗ | ✓ Required |
| Electronics | Optional | ✗ | ✓ Required | ✗ |
| Manufacturing | ✓ | ✓ Required | Optional | ✗ |
| General Trading | Configurable | Configurable | Configurable | Configurable |

The `BusinessProfileFeatureFlag` and `ProductConfig` tables (Phase 10) control which fields are required/optional per profile.

---

## Inventory Integration

- `InventoryTransaction` now has optional FK columns: `batch_id`, `lot_id`, `serial_id`
- These are populated at receipt/issue time when the product tracking flags demand it
- Stock ledger entries remain unchanged — traceability is at the transaction layer

---

## A serial's status moves with the stock (D-STK-4)

Until 2026-09-19 nothing outside `app/batch_serial` read or wrote
`serial_numbers`, and no movement set `inventory_transactions.serial_id`: a
mixer grinder that left on a delivery note kept its serial `AVAILABLE` for
ever. The owner decided on 2026-09-18 that **the storekeeper picks the
units**:

- **A delivery note line for a serial-tracked product** (`products.track_serial`)
  names the units going out in `serial_ids` -- the product's `AVAILABLE`
  serials in the line's warehouse. Saving refuses a unit named twice, of
  another product, in another warehouse, or not `AVAILABLE`; a draft may be
  picked short.
- **Dispatch refuses** until the line names exactly one serial per unit
  leaving (`delivered_quantity`, free goods included, in the stock unit),
  naming the line and the shortfall, and re-checks each unit -- two drafts may
  pick the same one, and only the first to ship takes it. Each unit then
  becomes `SOLD`, `current_owner` becomes the customer's name, and an audit
  row `serial_number.sold` is written, all inside the dispatch's own
  transaction.
- **A sales return line** names the units coming back, from those whose
  latest dispatch was the source line (`GET
  /api/v1/sales-returns/returnable-serials` lists them; a return against a
  bill reaches the note line through the bill line's source). Completing it
  refuses unless there is one serial per unit returned, then makes each
  `AVAILABLE` in the warehouse, branch and stock row the goods landed in
  (`serial_number.returned`). Cancelling a completed return makes them `SOLD`
  again (`serial_number.return_cancelled`) -- and is refused if one of them has
  been sold on since.
- **A delivery note cannot be cancelled once dispatched**, so there is no
  dispatch reversal to undo.

`document_line_serials` (migration `20260919_0138`) holds the picks: one row
per unit per line, with the document, the line, the movement that carried the
unit and when (`moved_at`, empty while it is only picked). A dispatch posts one
movement per **batch** drawn from, not one per unit, so the rows are where a
movement's units are listed; `inventory_transactions.serial_id` is set only
where a movement carried exactly one unit. `app/batch_serial/services/serial_trail_service.py`
owns all of it and never commits.

Decisions taken, following what Tally, SAP Business One, Odoo and Zoho do:

- **The document that issues the stock names the units.** A firm whose
  delivery note stage is off bills and ships in one step, so the bill line
  carries `serial_ids` and the sales chain hands them to the note it raises;
  a bill naming none for a serial-tracked product is refused by name before
  anything is staged. A bill of a note already dispatched names none -- its
  units were picked on the note -- and is refused if it tries.
- **A unit of a batch-tracked product leaves from its own batch.** Where the
  picked serials carry a `batch_id`, the dispatch draws from those batches
  instead of the earliest-expiry allocation, refusing a unit whose batch has
  expired or holds too little here; units with no batch leave the choice to
  the allocator, and a line mixing the two is refused.
- **The count is in the stock unit.** A line entered in another unit is
  counted by the server after conversion; the desktop checks the count only
  where the two units are the same.
- A return with damaged or scrap quantity still makes every returned unit
  `AVAILABLE`, as the owner specified; the stock row puts the damaged units in
  the damaged bucket, but the serial does not say which unit is which.

## The trail starts at the receipt (PG-10, backlog 86 #11)

Until 2026-10-05 a serial-tracked product arrived on a goods receipt with no
serials at all; units were numbered by hand in the serial master, or minted by
the history generator as they were sold. Now the receipt line carries them:

- **A goods receipt line** for a serial-tracked product takes
  `serial_numbers: list[str] | null` -- typed, scanned, or filled from a range
  (`POST /api/v1/goods-receipts/serials/expand` with `{prefix, start, count,
  width}` returns the list and saves nothing). Absent or null leaves what the
  line holds; `[]` clears it. Each number is trimmed and blanks are dropped;
  a number typed twice in the request, or already carried by a live unit of
  the firm, is refused by name. A product nobody tracks by serial refuses a
  non-empty list. The line response carries `serial_numbers` and
  `serial_tracked`.
- **Opening stock types its units the same way** (D-STK-40): `serial_numbers`
  on an opening stock line, held in `opening_stock_line_serials` (migration
  `20261008_0354`) and made into units at posting, whose first pick is
  `OPENING_STOCK`. A draft's lines are replaced on every save, so absent
  there means none. A line that names some must name one per unit of its
  stock quantity; a line that names none posts as a quantity.
- **A transfer names the units it moves** (D-STK-40), as `document_line_serials`
  rows: `STOCK_MOVE` for the one-step transfer, whose line is its outbound
  movement, and `STOCK_TRANSFER` for a line of the transfer document. The
  statuses `IN_TRANSIT` and `DAMAGED` exist for the document's two steps.
  `SerialTrailService.move_units` is the one place a transfer changes a
  unit's status and place.
- **A draft holds them as typed**, in `goods_receipt_line_serials` (migration
  `20261005_0311`), and may be short. Nothing is a unit yet, so two drafts may
  type the same number.
- **Completing the receipt refuses** until each serial-tracked line has one
  serial per unit put on the shelf -- accepted plus free, in the stock unit --
  naming the line, and re-checks every number against the firm's live units.
  Each then becomes a `serial_numbers` row, `AVAILABLE` in the receipt's
  warehouse with the line's batch, and a moved `document_line_serials` row
  (`GOODS_RECEIPT`) names the receipt line and its movement: the start of the
  unit's trail (`serial_number.received`).
- **Cancelling a completed receipt** soft-deletes those units and their
  receipt picks (`serial_number.receipt_cancelled`), which frees the numbers
  -- and is refused if any unit is no longer `AVAILABLE` or has moved on any
  other document since, even one sold and returned.
- **A purchase return line** of a serial-tracked product names the units
  going back in `serial_numbers`, resolved to the product's live units
  (case ignored). Each must be `AVAILABLE` and have arrived on a receipt from
  the return's supplier. The return renumbers its lines on every save, so a
  line that says nothing keeps its picks by line number. Completion refuses
  unless there is one per unit leaving (counted off the movement, in the stock
  unit), re-checks each and that it is in the line's warehouse, and marks them
  `RETURNED` (`serial_number.returned_to_supplier`). Cancelling a completed
  return puts them back `AVAILABLE`; cancelling a draft forgets its picks.
- **A unit is unique in the firm, not per product.** The old key (firm,
  serial, product, deleted rows included) gave way to a partial unique index
  on `(firm_id, upper(serial_number))` over live rows. The migration stops,
  naming them, if a store already holds repeats.
- **The trail**, `GET /api/v1/batch-serial/serials/{id}/trail`, lists every
  document the unit moved on -- number, date, supplier or customer -- with the
  receipt first, then in the order they moved.

Decisions taken: free goods carry serials like paid ones; the count is in the
stock unit; a receipt raised by a supplier bill (`PurchaseChainService`)
carries no serials, so a serial-tracked product is received on a goods receipt
rather than billed straight in; `IN_STOCK` in the backlog is the existing
`AVAILABLE` status, which dispatch already requires.
- `require_serial_on_issue` / `require_serial_on_receipt` are still read by
  nothing -- `track_serial` alone decides.
- Receiving stock (goods receipt, opening stock) numbers no units; serials are
  still created on the Serial Numbers screen or by the seeders.

---

## Traceability Strategy

### Forward Trace (from Batch)
```
Batch → InventoryTransaction (receipt) → Inventory
     → Future: SalesLine (issue)
     → Future: ManufacturingOrder
     → Future: ReturnLine
```

### Backward Trace (from Serial)
```
SerialNumber → batch_id → BatchRecord → vendor_id → Vendor
           → inventory_id → Inventory → warehouse → Branch
           → Future: SalesLine → Customer
```

### Extension Points
Each of `batches`, `lots`, `serial_numbers`, and `inventory_transactions` has FK slots ready for:
- Purchase Order Line (`purchase_line_id`) — future Phase 17
- Sales Order Line (`sales_line_id`) — future Phase 18
- Manufacturing Order (`manufacturing_order_id`) — future Phase 20
- Quality Control Hold (`qc_hold_id`) — future

---

## Future Integrations

### Purchase Module (Phase 17)
- GRN will populate `batch_id` / `lot_id` / `serial_id` on `InventoryTransaction`
- Batch receives `vendor_id` automatically from GRN

### Sales Module (Phase 18)
- Issue transactions record batch/serial consumed
- Serial status transitions: `available → sold` -- built for delivery notes
  and sales returns on 2026-09-19; see "A serial's status moves with the
  stock" above

### Manufacturing (Phase 20)
- Lot hierarchy (`parent_lot_id`) supports mixing/blending traceability
- Manufacturing orders create both input (consumed) and output (produced) lot transactions

### Warranty Management (future)
- `SerialNumber.warranty_end` is the extension point
- Warranty claim module reads serial status and flips to `returned` / `repaired`

### FEFO, and choosing a batch on a sale (backlog 79, decision A38)

Reservation and dispatch draw **earliest expiry first among batches in date**
(judged on the document's own date; a batch is out of date *on* its expiry day,
and one marked EXPIRED by hand is too -- `BatchRecord.expired_condition`).
Since 2026-10-02 a person may override that per delivery line:

- **`GET /api/v1/batch-serial/batches/availability`** -- a product's batches in
  one warehouse, nearest expiry first: on hand, reserved, available,
  `available_to_line` (adds back the asking order line's own hold, which
  dispatch lets go first), days to expiry, `expired`, `near_expiry` (window
  `near_expiry_days`, default 30) and `fefo`, the split dispatch would draw for
  `quantity` -- the picker's pre-fill. Open to `BATCH_VIEW`, `INVENTORY_VIEW`
  or `SALES_VIEW`, because whoever writes the note holds a sales code.
- **`delivery_note_line_batches`** (migration 0214) -- `batches` on a delivery
  line write: absent keeps the choice, `[]` clears it to FEFO. Refused on
  write: another product's batch, a batch named twice, any pick on a
  serial-tracked product (its units decide the batch). Refused at dispatch:
  picks that do not add up to the line's stock quantity, an expired batch.
  Release prefers the chosen batches (`allocate_for_release(prefer=)`), so the
  order's own hold never stands in the way of its own pick.
- **After dispatch the table is what left**, chosen or not: with no choice the
  FEFO split drawn is written there. The challan prints **one row per batch**
  (quantity, free goods and value apportioned, residual on the last row) and
  turns on the batch and expiry columns whenever a line carries a batch.
- **A choice that is not the FEFO split** is audited as
  `delivery_note.fefo_skipped`, with both splits.

### The firm's batch rules (backlog 79 row 6, decision A2)

`batch_sale_settings` (migration 0217), one row per firm; a firm with no row
shares the defaults. `GET/PUT /api/v1/batch-serial/sale-settings` -- reading
is open to whoever may use the picker, writing needs `SALES_MANAGE_SETTINGS`,
beside the price floor, because these rules constrain who may sell what.
`BatchSalePolicyService` (`app/batch_serial/services/batch_sale_policy.py`)
is the one implementation.

| Rule | Default | What it does |
| --- | --- | --- |
| `near_expiry_days` | 30 | A batch expiring within this many days of the document's date is near expiry. The availability endpoint uses it when `near_expiry_days` is not passed |
| `near_expiry_policy` | `WARN` | WARN records a near-expiry batch leaving (`delivery_note.near_expiry_dispatched`, and `batch_warnings` on the DISPATCHED event). REASON refuses a dispatch by hand until `batch_reason` is given, naming the line and batch |
| `fefo_skip_policy` | `RECORD` | RECORD audits a skip as before. REASON refuses it without `batch_reason`, which `delivery_note.fefo_skipped` then keeps beside both splits |
| `near_expiry_below_floor` | on | A2: a line drawn **wholly** from near-expiry batches may be sold below its price floor. The finding is still made and kept as `price_near_expiry` on the APPROVED event with the batches named; it neither warns nor blocks |
| `shelf_life_policy` | `BLOCK` | A batch **chosen by hand** that expires before the customer's minimum shelf life: BLOCK refuses the dispatch -- on a bill's own dispatch too, because it is the customer's rule rather than a question for whoever dispatches -- and WARN records it (`delivery_note.short_shelf_life_dispatched`) |

**Judged where a person dispatches**: `POST /delivery-notes/{id}/dispatch`
and `/dispatch-and-invoice` take `batch_reason` as a query parameter (the
licence override's shape), and completing an approved note is judged too. A
bill shipping the notes it raised for itself (a counter bill, the sales chain)
records near-expiry batches but is never refused -- the counter has no picker
yet. `GET /delivery-notes/{id}/batch-check` predicts what dispatch will meet
-- the chosen split, or the FEFO pre-fill -- so the screen asks for the reason
first; dispatch stays the authority.

**Which batches a line takes, for the floor**: on a bill from a dispatched
note, the batches the note recorded (`delivery_note_line_batches`); otherwise
the earliest-expiry split of the line's warehouse on the document's date,
counting a note line's own order hold as its own. A sales order is judged
before it reserves, so its split is what reservation is about to take. Cost
stays one moving average per product; only the floor's bite changes.

### Batches on a counter bill (backlog 79 row 2)

A counter bill raises its own order and delivery note when the draft is saved,
and its approval dispatches that note. `batches` on a bill line (stock units)
is handed to the note line it raises, exactly as `serial_ids` are
(`SalesChainService._note_line`), so dispatch draws the chosen batches; on an
edit of the draft the bill's lines name that note, and their `batches` are
restated on its line (`DeliveryNoteService.set_line_batches`, shared with the
note's own editor). Absent leaves the choice -- earliest expiry first -- and an
empty list clears it. A bill billing a note somebody else typed is refused
`batches`: that note chose its own. Each bill line's response carries the
batches its note line takes. The batch rules judge a bill's dispatch as a
record only (no reason asked), as before.

### A customer's minimum shelf life (backlog 79 row 6)

`customers.minimum_shelf_life_days` (migration 0223; any firm may record it,
and it only bites on goods whose product tracks expiry) is how many days goods must have left when they
reach the customer -- a hospital or a chain often asks for six months. It is
read on the delivery note's date as a date the goods must last to. Earliest-
expiry allocation **passes over** a batch expiring before it, exactly as it
passes over an expired one (`allocate_for_dispatch(keep_until=)`), and names it
if the rest fall short; so with nobody choosing, a compliant batch simply goes.
The picker's availability takes `customer_id`, flags such a batch
`short_for_customer` and never pre-fills it; `batch-check` reports
`SHORT_SHELF_LIFE` and `would_block`. A batch chosen by hand anyway meets
`shelf_life_policy`.

**A batch is out of date on its expiry date, everywhere** (D-STK-17,
2026-10-06). `BatchRecord.expired_condition` has always said so, and the
picker, a pinned order, a batch picked on a note and a counter bill each
refused such a batch on that day. Earliest-expiry allocation alone read
"before the date", so the batch nobody was allowed to choose was the one
chosen for an order that named none, reserved and shipped. The allocator's
`_expired_batches` now passes it over on the date too, and a serial in such a
batch is refused the same day. The day before, it is still the first to go.
The shelf-life and stop-selling tests are a different question -- good *on*
the day the goods must last to is long enough -- and are unchanged.

**The reservation follows the same rule** (D-SELL-58). Approval reads the
customer's minimum shelf life on the order's date and passes over a short
batch exactly as dispatch will (`allocate_for_reservation(keep_until=)`; both
go through `_without_short_dated`, which also applies the product's own
stop-selling window). The hold used to go on the earliest batch regardless,
so the next order took the only batch that suited and the first order's
dispatch was refused with stock on the shelf. What suitable stock cannot
cover is a back order whose movement names the batch passed over. A pinned
batch is not filtered: the customer asked for it, and it is judged when it
ships. A counter bill line drawn wholly from one batch it chose pins that
batch on the order it raises, so the draft holds the batch it will ship.

**Dispatch lets go of the order's own hold first.** A stock row's
`reserved_quantity` is the sum of every order's hold on that batch and does
not say whose. The stock ledger does -- every hold and release carries the
order's number -- so `InventoryService.held_by_reference` reads what one
order still holds, batch by batch, and `allocate_for_release(own=)` frees
those first, each up to what the order holds there. Releasing by expiry
alone freed another order's hold on the earlier batch, kept this order's on
the later one, and refused its dispatch "short by 6" for stock it had itself
reserved (D-SELL-58, second half). The batch picker reads the same figure, so
"available to line" and the pre-fill name the batch the line really holds.

**A counter bill line split across batches holds each for what was picked**
(D-SELL-81). One of the early batch and three of the late held all four on
the early one: three held that would never ship, and the three that would
left open to any other order, whose taking them refused the bill's approval.
An order line has one batch to pin and a split has several, so the split is
not stored: the chain hands it to the approval that holds the stock
(`stage_approval(held_batches=)`, `_held_as_chosen`), which holds each batch
as a pinned one is held -- what a batch cannot cover is a back order, never
a hold on another batch. No column was added. Picks that do not add up to
what the line reserves -- half typed, or a gift an offer added -- are held
earliest expiry first as before; the bill's approval is what refuses them.
Reserving a counter bill's hidden order again by hand (`reserve_again`)
still holds earliest first, because nothing on the order remembers the
split.

**Withdrawing an order lets go of its own hold first too.** Cancelling or
releasing an order went by expiry alone, so an order held on a later batch
let go of another order's hold on the earlier one and kept its own: the
totals were right and each batch was wrong. Found while fixing D-SELL-81,
where every changed pick withdraws an order; `_release_inventory` now passes
`own=` exactly as dispatch does.

**The back-order report reads stock by batch** (D-SELL-60): stock in an
expired batch is not counted, and a pinned line is measured against its own
batch alone.

### Pinning a batch on the order (backlog 79 row 4)

`sales_order_lines.pinned_batch_id` (migration 0224) is the batch the customer
asked for. Approval holds **that batch and no other**
(`allocate_for_reservation(only_batch=)`): what it cannot cover is a back
order rather than a quiet hold on another batch, and a pinned batch out of
date on the order's date is refused by name. A delivery note line raised from
the order starts with the pinned batch picked, so dispatch ships it -- and the
audit trail records it as a FEFO skip where it was not the earliest, which is
the record wanted. The person may still change the pick on the note.

### A batch's own MRP (backlog 79 row 7, decision A41)

The manufacturer prints a different MRP on each batch, so it lives on the batch
(`batches.mrp`, tax included, and `selling_price`, before tax, both per stock
unit; migration 0225), as Marg and Busy keep it. The goods receipt line carries
them (`goods_receipt_lines.mrp` / `.selling_price`) to the batch it creates,
and fills an existing batch only where it has none -- the print on a batch does
not change. The batch screen edits them, and the picker shows them.

**No bill charges above it.** At a bill's approval, once its own notes have
shipped, each line billing a delivery note is judged per charged stock unit --
net of discounts, with tax, freight left out -- against the lowest MRP among
the batches its note line takes, the product's MRP standing in for a batch with
none; above it is refused naming the line, the rate and the MRP. The challan
and the tax invoice print one row per batch with its expiry and **MRP**.

**And it is refused where the price is struck, not three documents later
(D-PRC-7, 2026-10-06).** The bill is the last document of a sale: an order of
one, pinned to a batch printed 120.00, at 130 (145.60 with tax) was saved and
approved, its note was dispatched, and only then was the bill refused, with
the goods already out. The judge is one function now,
`refuse_above_batch_mrp` in `app/batch_serial/services/mrp_ceiling.py`, with
the one wording -- "Line 1: charges 145.60 a unit with tax, above the MRP of
120.00 printed on the batch it ships." -- asked at every point a price meets a
known batch:

- a **sales order line saved with a pinned batch** (create and edit);
- a **counter bill at save**, through the order it raises -- a line drawn from
  one batch is pinned to it, and one drawn from several is held to the lowest
  of them by `SalesChainService._refuse_above_chosen_mrp`;
- a **delivery note at dispatch**, once each line knows the batches it draws
  from -- chosen by a person, carried by a serial, or allocated earliest
  expiry first -- and before any stock moves, so nothing has left when it is
  refused;
- the **bill at approval**, as before, which still catches an MRP corrected
  downward after the goods left.

**An order line with no pin is not judged when it is saved.** No batch is known
yet, and guessing the one the allocator will choose later would refuse an
order for a batch it may never ship; such a line is judged at dispatch. A
note that chooses its batches is likewise judged at dispatch, not when the
draft is saved. Free goods charge nothing and are not counted.

**The MRP is the price of a stock unit, and the judge does the conversion
(D-PRC-36, 2026-10-06).** A pharmacy sells by the strip and the box, and the
pack the MRP is printed on is the piece. AMX, 12 to a box, GST 12%, a batch
printed 120.00: 1 BOX at 1,200.00 is 1,344.00 with tax, **112.00 a piece**.
The order and the dispatch judged it so and 12 pieces left; the bill's
approval then refused it as "charges 1344.00 a unit with tax", and billed as
12 PIECE as "16134.45 a unit" -- the bill multiplied by its own
`conversion_factor`, which is the unit the bill was *typed* in against the
note's (a twelfth for pieces against a box), not the note line's factor into
stock. The goods were out and no bill of them could be approved.

Each caller used to work out the stock units itself, which is how one of four
came to differ. `refuse_above_batch_mrp` now takes the line **as it stands**
-- `paid`, the `quantity` it pays for in the line's own unit, and
`stock_units_per_unit`, how many stock units one of that unit holds -- and
divides once. The order and the note hand over their own `conversion_factor`;
the bill, whose line is counted and priced in its note line's unit whatever
unit it was typed in, hands over the **note line's** factor
(`_stock_units_per_note_unit`). So a bill reaches the verdict its dispatch
reached: a box at 1,320.00 is refused everywhere as "charges 123.20 a unit
with tax", exactly as 12 PIECE at 110.00 is, and the unit named in the
refusal is always the stock unit.

**Price from batch** (`batch_sale_settings.price_from_batch`, off): where a
line's batch is chosen, the screen fills its rate from the batch's selling
price, ahead of the price list. The server takes the rate it is sent, as for
any rate.

§79 is complete.

### What a product's switches allow (backlog 89, 2026-10-08)

Added 2026-10-08, not yet tested by hand. Whether a batch, a serial number, an
expiry date, a manufacturing date, a shelf life or a warranty may be recorded is
decided by **the product's own switches, never by the firm's business profile**.
Before this, the batch and lot writes, the serial writes and the date fields were
gated by catalogue features on the profile. All of that is gone.
The rules live in `app/batch_serial/services/product_tracking.py`
(`tracked_product`, `assert_product_keeps`, `assert_product_fields`,
`FIELD_SWITCHES`, `RECORD_SWITCHES`).

| Record or field | Product switch | Asked when | Refusal |
| --- | --- | --- | --- |
| Add a batch by hand | `track_batch` | `POST /batches` | 422 "<CODE> is not tracked by batch, so a batch cannot be added for it. Switch batch tracking on for the product first." |
| Add a lot by hand | `track_lot` or `track_batch` | `POST /lots` | 422, same shape |
| Add a serial by hand | `track_serial` | `POST /serials` | 422, same shape |
| `expiry_date`, `best_before_date`, `shelf_life_days` | `track_expiry` | the field is filled | 422 "<CODE> does not track expiry dates, so expiry_date cannot be set. Switch it on for the product first." |
| `manufacturing_date` | `track_manufacturing_date` | the field is filled | 422, same shape |
| `warranty_start`, `warranty_end` | `track_warranty` | the field is filled | 422, same shape |

- A field is judged only when it is filled (blank always passes), and on an
  update only when the save actually changes it.
- A batch, lot or serial that already exists can always be changed or removed,
  whatever the switch says now, so a batch can still be held or recalled.
- A goods receipt still creates its batch whatever `track_batch` says (goods that
  arrived must be receivable; `require_batch_on_receipt` still refuses a line
  with no batch). The receipt's batch is refused an expiry date if the product
  does not track expiry (when the receipt completes, as before). The batch keeps
  the manufacturing date only where the product has `track_manufacturing_date`
  and the shelf life only where it has `track_expiry`. The line's expiry is
  filled from manufacturing date plus the product's shelf life only for a
  product with `track_expiry`.
- The desktop goods receipt editors show Expiry date where the line's product
  has `track_expiry` and Manufactured on where it has `track_manufacturing_date`;
  a product not in the loaded list is offered both.
- `BATCH_PTR_PTS` (price to retailer and stockist on a batch) is unchanged: it is
  still a feature of the firm's profile, as are ATTACHMENTS, VEHICLE_TRACKING and
  DRUG_LICENSE.
- The feature rows for these switches (and for barcode and QR code) were removed
  from the catalogue and from every profile on 2026-10-08 by `20261008_0353`.
  See `docs/GOODS_TYPES.md`.
- **The menus follow the goods.** Batches and Lots show in the desktop only when
  a goods type the firm uses, or a live product of the firm, has `track_batch`;
  Serial Numbers on `track_serial`; Expiry Monitor on `track_expiry`. The server
  answers it as `goods_tracking` on the INVENTORY row of
  `GET /api/v1/business-framework/active-modules`
  (`GoodsTypeRepository.tracking_in_use`); added on 2026-10-08, not yet tested by
  hand. See `docs/BUSINESS_PROFILE_FRAMEWORK.md`, *Menus follow the goods*.
- **A batch, lot or serial moved to another product is judged against that
  product** (D-STK-22, 2026-10-08). An update naming a new `product_id` used to
  be judged against the old one. `_product_after` in
  `batch_serial_service.py` asks the new product what a record added by hand
  is asked: it must be the firm's own, track such a record, and allow every
  dated field the record already holds. A record that stock, a movement or a
  serial stands on cannot change product at all (*cannot be moved to another
  product*), and a product cannot be cleared off a record. A serial number is
  refused a batch of another product, on create and on update.
- **A batch does not expire before it is made** (D-STK-23). `assert_date_order`
  refuses an expiry or best-before date earlier than the manufacturing date on
  a batch added or edited by hand, judged on what the batch will hold; the same
  day is allowed. A goods receipt is not asked: goods on the dock are received.
- **A batch, lot or serial added from the screen names its product** (D-UI-72,
  2026-10-08). The three dialogs under **Stock > Batches / Lots / Serial
  Numbers** had no product box, so the server refused every one of them
  (`product_id: Field required`) and the rules above could not be met from a
  screen at all. Each now opens with a product box that searches as it is
  typed (`ProductSearchBox`), says *Choose the product this batch is of.* when
  none is picked, and keeps what was typed when the server refuses. An edit
  does not offer the box: a record keeps its product.

### What a switch requires (inventory round 4, 2026-10-08)

The switches above say what a product *may* carry. Three rules, agreed by the
owner on 2026-10-08, say what follows from them when goods arrive or a unit is
numbered.

- **A batch number typed for a product that keeps no batches is ignored**
  (D-STK-43). The receipt, or the opening stock, goes through; the goods land
  on the product's own stock row; no batch is registered. The text stays on
  the line as what was typed. `track_batch` is the switch read, in
  `GoodsReceiptService` where a receipt is stocked and in
  `InventoryService._opening_stock_batch_id`.
- **A batch of a product that tracks expiry has to carry an expiry date**
  (D-STK-48, `assert_expiry_stated` in `product_tracking.py`). The batch
  master refuses a new batch without one, and a receipt or opening stock is
  refused when it would register one. Only the manufacturing date typed is
  enough where there is a shelf life -- the line's or the product's -- since
  that fills the expiry, on the master as on a receipt. A batch registered
  before the rule takes the date the next delivery states and is refused with
  none. An edit is judged only when it touches the date, so an old undated
  batch can still be held or recalled.
- **Add Serial stops at the stock held** (D-STK-50,
  `BatchSerialService._assert_unit_is_held`). A unit that is on hand
  (`AVAILABLE`, `RESERVED`, `DAMAGED`) is counted against what the warehouse
  holds of the product on the shelf, in quarantine, damaged or blocked; one
  more than that is refused in words. A unit naming no warehouse is judged
  against everything the firm holds. An edit that moves a unit to another
  warehouse or product, or brings a sold or scrapped unit back on hand, is
  judged as a new unit there is. Units a receipt, opening stock or a transfer
  number are not asked: those number exactly what they bring. Units numbered
  above the stock before the rule are left as they are.

### Batch-wise PTR / PTS (PG-14, backlog 86 #22, 55 G5)

A pharma or FMCG distributor keeps two trade rates on every batch beside its
MRP, as Marg does: the **price to retailer** and the **price to stockist**
(`batches.ptr` / `batches.pts`, per stock unit before tax; migration
`20261005_0316`). Both are optional and belong to the business feature
`BATCH_PTR_PTS` (seeded implemented, and switched on for the PHARMACY, FOOD and
WHOLESALE profiles only where missing).

**Captured at receipt.** A goods receipt line takes `ptr` / `pts` beside `mrp`;
`assert_feature_fields` refuses them only when sent by a firm whose profile
lacks the feature. A line sending one needs a batch number (the rates have
nowhere else to go), and neither may exceed the MRP -- the line's own when it
states one, and again on completion against the MRP the batch will carry
(`assert_trade_rates_within_mrp`). Completion hands them to the batch: set on a
new batch; on an existing one the batch keeps its own unless the receipt
states a different rate, which then stands and is audited as
`batch.rates_updated` with the old pair. Blank never clears. The batch's own
create and update take the same fields under the same gate and cap.

**PTS at or below PTR at or below MRP** (D-PRC-18, 2026-10-06). A batch with
PTR 90 and PTS 95 was accepted: the stockist, who sells on to the retailer,
was charged more than the retailer. The same function holds the order of the
two rates, with an MRP on file or without one, on every path that writes a
rate -- the receipt's line, its completion against the rate the batch already
holds, and the batch's create and update: "PTS 95.00 cannot exceed the PTR
90.00: a stockist buys at or below the price to a retailer." Equal is in
order. No import file carries the two rates, so there is no fifth path.

**Shown in the picker.** `BatchAvailability` (the batch picker's availability
rows) and `BatchResponse` carry `ptr` and `pts` beside `mrp` and
`selling_price`.

**Charged by trade class.** `customers.trade_class` is RETAILER, STOCKIST or
OTHER (null reads as OTHER). Where a sales line leaves from a known batch -- a
pinned batch on the order, or a counter bill line whose `batches` name a single
batch -- and its price is blank, the batch's PTR (retailer) or PTS (stockist)
is the starting price: below an agreed price list, above the price level and
the product's price, never above anything typed. See
`docs/PRICING_AND_PROMOTIONS.md`, "The price a line starts at".

---

### A lot's two margins (L3, 2026-10-15)

For a firm costing by lot the lot carries `retail_margin_percent` and `wholesale_margin_percent` beside its `ptr` (retail) and `pts` (wholesale), handed over from the receipt line that made it; see `docs/PRICING_AND_PROMOTIONS.md`, "Retail and wholesale margins on the lot". The batch's own edit (the lot page) is gated on `BATCH_UPDATE`; such a firm does not also need `BATCH_PTR_PTS`. A changed price works its margin back from the lot's cost. The batch answer carries `mrp_warning`, judged at the tax of the receipt line that brought the lot in (a lot no receipt brought in is judged at no tax). A firm on Average keeps the PG-14 rules above.

## How batch stock is stored, in plain terms

A batch is **not** a separate product. The product is one row in `products`;
each batch of it is a row in `batches` (number, expiry, manufacturing date,
MRP, selling rate, PTR, PTS). Stock on hand is in `inventories`: **one row
per location for a product that tracks no batch, one row per batch in that
location for one that does** -- the batch column is simply empty for the
first kind. `products` holds no stock figure; every total is added up from
those rows. Each movement (`inventory_transactions`, `stock_ledger_entries`)
names its batch. Cost is in `product_valuations`, one moving average per
product and not per batch (backlog 101).

| Product | Warehouse | Batch | On hand |
| --- | --- | --- | --- |
| Paracetamol 500 (tracks batch) | Main | B001 | 60 |
| Paracetamol 500 | Main | B002 | 100 |
| Paracetamol 500 | Branch | B002 | 40 |
| Sugar 1 kg (no batch) | Main | | 500 |
| Sugar 1 kg | Branch | | 120 |

Paracetamol is 200 in all, 140 of it batch B002, 160 of it in Main: three
sums over the same rows. A receipt of more Sugar into Main raises its one row;
a receipt of a new batch adds a row to `batches` and a stock row; more of an
existing batch raises that batch's row. Free units arrive in the batch of the
receipt line that carries them.

Price lists, offers, tax and reports work on the product, so a new batch
needs nothing set up again -- which is what an item per batch would cost.

## Import / Export

Existing platform import/export framework applies:

| Operation | Format | Endpoint |
|---|---|---|
| Batch Import | CSV / XLSX | POST `/api/v1/batch-serial/batches/import` (future) |
| Serial Import | CSV / XLSX | POST `/api/v1/batch-serial/serials/import` (future) |
| Batch Export | CSV / XLSX | GET `/api/v1/batch-serial/batches/export` (future) |
| Serial Export | CSV / XLSX | GET `/api/v1/batch-serial/serials/export` (future) |

Desktop Import Wizard (Phase 16A.1 pattern) can be reused directly for batch/serial bulk import.

---

## Migration

File: `backend/alembic/versions/20260801_0020_enterprise_batch_serial_expiry.py`

Operations (in order):
1. Create `batches` table
2. Create `lots` table
3. Create `serial_numbers` table
4. `ALTER TABLE products ADD COLUMN track_batch ...` (11 columns)
5. `ALTER TABLE inventory_transactions ADD COLUMN batch_id ...` (3 columns)

Down migration reverses all operations.

---

## Audit

All three new entities (`BatchRecord`, `LotRecord`, `SerialNumber`) extend `BaseEntity` which provides:
- `created_by`, `created_at`
- `updated_by`, `updated_at`
- `deleted_by`, `deleted_at` (soft delete)

Status transitions are recorded via the existing `record_audit` service.

---

## Test Coverage

### Backend (10 new unit tests)

- `test_batch_crud` — create/read/update/delete batch
- `test_batch_soft_delete` — soft delete leaves record with `deleted_at`
- `test_lot_crud` — create/read/update/delete lot
- `test_serial_crud` — create/read/update/delete serial
- `test_serial_soft_delete`
- `test_batch_summary` — aggregation by status
- `test_expiry_dashboard` — dashboard counters
- `test_batch_list_filtering` — status + warehouse filters
- `test_serial_status_transition` — available → sold
- `test_multi_firm_isolation` — batches are firm-scoped

### Desktop (4 new widget tests)

- `batch management page shows empty state for batches section`
- `batch management page renders batch grid when batches are returned`
- `serial management page shows empty state for serials section`
- `lot management page shows empty state for lots section`

---

## Known Issues / Technical Debt

1. **Import/Export endpoints** for batch and serial are not yet implemented — only the data model and framework hooks exist. Tracked for Phase 17+.
2. **Recall Workflow** is not implemented — `status = recalled` can be set manually via API but no automated notification/workflow exists.
3. **FEFO allocation is built** (see *FEFO, and choosing a batch on a sale* above); this line said otherwise until 2026-10-10. FIFO as a costing method is not: cost is one moving average per product (backlog 101).
4. **QC Hold integration** — `blocked_qty` and `quarantine` status are data-model ready but no QC module enforces them yet.
5. **Lot hierarchy depth** — `parent_lot_id` supports one level of parent; deep multi-level lot trees may require recursive CTE queries (not yet implemented).
6. **Serial movement history** — current model records current status/owner but does not yet maintain a full movement log table. Extension point: `serial_movements` table in Phase 18.

---

## Breaking Changes

None. All existing APIs and tables are unchanged. New columns on `products` and `inventory_transactions` are nullable with `server_default=False` to avoid migration failures on populated databases.

---

_Phase 16B completed. Ready for Phase 17 (Purchase) integration._
