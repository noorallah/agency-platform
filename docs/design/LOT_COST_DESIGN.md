# Cost per purchase lot: design note

**Status: design note for row L1 of `docs/CUSTOMER_BUILD_TASKS.md`, written
2026-10-13. Nothing in it is built.** It covers backlog 101 (cost per batch)
and backlog 103 (one stock structure for every product), and it is what rows
L2 and L3 are built from. The owner reads and approves it before any code.

Words used here. A **lot** is one purchase line's goods: its own cost, MRP,
selling prices, batch and expiry. A **batch** is the number the manufacturer
prints on the goods. Two deliveries of one printed batch are two lots.

## 1. What it does for the user

Every line of a purchase becomes a lot that remembers what it cost, its MRP,
its selling prices, its batch and expiry, and the supplier's bill it came on.
Goods with no printed batch get a lot reference of our own, which nobody
types and no print shows. At billing the bill maker sees the stock of the
item as rows, one per batch and price, nearest expiry first, and takes the
quantity from one or several. The bill line keeps the lots it took. A return
goes back into the same lot at the cost it left with, and from the lot the
supplier's bill is one step away. The books carry stock at what each lot cost:
the cost of a sale is the cost of the lots it took, oldest first unless the
bill maker chose otherwise.

### Worked example

One item, sold by the piece. Tax is left out; it is never part of cost.

| Step | What happens | Lot A | Lot B | Stock value |
| --- | --- | --- | --- | --- |
| 1 Oct, purchase | 100 at 40.00. MRP 60, expiry Mar 2027 | 100 at 40.00 = 4,000.00 | | 4,000.00 |
| 10 Oct, purchase | 100 at 42.00, 5% off, 10 free. MRP 65, expiry Jun 2027. 3,990.00 over 110 pieces | 100 at 40.00 | 110 at 36.27 = 3,990.00 | 7,990.00 |
| 15 Oct, sale of 150 | The picker offers lot A first (expires sooner). 100 from A, 50 from B | 0 | 60 at 36.27 = 2,176.36 | 2,176.36 |
| 20 Oct, customer returns 10 of the MRP 65 goods | Back into lot B, at the cost they left with | 0 | 70 at 36.27 = 2,539.09 | 2,539.09 |

- **Cost of the sale: 5,813.64** (4,000.00 from lot A and 1,813.64 from lot
  B). Today's method, one average of 38.05, would say 5,707.14, and would
  show the same margin on both rows.
- **The bill prints two rows**, 100 pieces at MRP 60 and 50 at MRP 65, each
  with its own batch and expiry, each at its own lot's selling price.
- **The return** puts 362.73 back into stock and takes 362.73 off cost of
  goods sold. Lot B names the goods receipt and the supplier's bill of 10
  October, so the 10 pieces can go back to that supplier against that bill,
  leaving stock at lot B's own cost.

## 2. What exists today, and what is missing

### Already there

| Subject | What exists | Where |
| --- | --- | --- |
| Batch master | `batches`: number, expiry, manufacturing date, supplier, **MRP, selling price, PTR, PTS** per stock unit. Holds no quantity | `backend/app/batch_serial/models/batch_serial.py` |
| Stock by batch | `inventories` is one row per location and batch, or one row per location where the product keeps no batch (two partial unique indexes). Every movement and stock ledger row names its batch | `backend/app/inventory/models/inventory.py` |
| Cost | **One moving average per firm and product**, `product_valuations`. A receipt moves the average, an issue leaves at it. The row has a `costing_method` column, always `WEIGHTED_AVERAGE`, read by nothing | `_apply_valuation` in `backend/app/inventory/services/inventory_service.py` |
| One valuation point | Every movement of every module goes through `_stage_movement`, which values it and writes `unit_cost` and `total_cost` on the stock ledger row | same file |
| Cost of a purchase line | Net of line and bill discount, free units of the same product spread over all units, converted to the stock unit | `_receipt_unit_cost` in `backend/app/goods_receipt/services/goods_receipt_service.py` |
| Where stock arrives | Always the goods receipt. A firm that types only the supplier's bill gets its order and receipt raised for it, and the bill's approval completes the receipt | `backend/app/purchase_invoice/services/purchase_chain_service.py` |
| Bill rate differs from receipt | The whole difference posts to purchase price variance; stock is not corrected | `backend/app/purchase_invoice/services/price_variance.py`, `docs/LEDGER_POSTING_RULES.md` |
| Choosing a batch on a sale | Earliest expiry first among batches in date; a person may choose per line; the split that left is kept in `delivery_note_line_batches`; a skip is audited | `allocate_for_dispatch` in the inventory service; `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md` |
| Picker on screen | New UI, on the sales order, delivery note and sales bill editors. Shows expiry, MRP, rates, available | `desktop/lib/ui/workspace/batch_picker_panel.dart`, `GET /api/v1/batch-serial/batches/availability` |
| Price from the batch | PTR or PTS by the customer's trade class; MRP ceiling per batch; a firm switch to price from the batch's selling price | `backend/app/core/utils/pricing.py`, `backend/app/batch_serial/services/mrp_ceiling.py` |
| Cost on a bill line | `sales_invoice_lines.cost_amount`, snapshotted from the dispatch, used by commission on margin | `_dispatch_costs` in `backend/app/sales_invoice/services/sales_invoice_service.py` |
| Returns | A purchase return is raised off the receipt line and names its batch. A sales return is raised off the note or bill line and names one batch | `backend/app/purchase_return`, `backend/app/sales_return` |
| Ledger legs facing stock | Receipt, dispatch, both returns, adjustments and their reversals all read the value off the stock ledger row | `docs/LEDGER_POSTING_RULES.md`, first rule |
| Who may see cost | Permission `PRODUCT_VIEW_COST_PRICE`, seeded | `backend/app/identity/system_seed.py` |
| Stock valuation report | Quantity at the product's average as on any day, value at MRP beside it, compared with the Inventory account | `backend/app/inventory/services/stock_valuation.py` |
| A table called `lots` | A production lot master with its own screen. No stock movement writes it; `inventory_transactions.lot_id` is always empty | `backend/app/batch_serial/models/batch_serial.py` |

### Missing

1. **Cost per lot.** Two lots bought at 40.00 and 36.27 leave at one average.
2. **A lot per purchase line.** A second delivery of the same printed batch
   joins the first batch row (unique on firm, batch number, product), so its
   cost, and a different MRP or rate, cannot be told apart.
3. **A lot for goods with no batch.** Their stock is one row per location and
   names nothing.
4. **Where a lot came from.** A batch names its supplier, not the receipt
   line or the bill.
5. **Cost per bill line by lot.** `_dispatch_costs` splits a delivery note's
   cost over its lines by quantity, per product. Two lines of one item from
   two lots would share one blended cost.
6. **A return into several lots.** A sales return line names one batch.
7. **A returned or re-received unit comes back at today's average**, not at
   the cost it left with (`reverse_transaction`, `record_sales_return`).
8. **Opening stock by lot** has cost, batch and expiry per line, and no MRP
   or selling price (gap G1 of `docs/SWATHI_IMPORT_PLAN.md`).
9. **No costing method setting** a firm can choose, and no switch-over.

## 3. The design

### 3.1 The lot is the batch row, made finer

The lot is not a new record beside the batch. It **is** the `batches` row,
one per purchase line. Everything that already carries `batch_id` then
carries the lot with no new plumbing: stock rows, movements, the stock
ledger, reservations, the picker, the delivery note's split, transfers,
counts, repacks, serial numbers and every print that shows a batch.

This is how Marg and Busy keep it (a batch entry per purchase with its own
rates). It also settles backlog 103's open point: **a batch the system
keeps**, not an empty batch, for goods nobody types one for.

The other way, hidden cost layers beside the valuation (ERPNext, Odoo), was
set aside. A layer cannot be picked at billing, cannot hold a price of its
own, and cannot be named on a bill line, and the requirement asks all three.

On screens the word is **Lot**. In code and tables the name stays `batches`
and `batch_id`. The existing `lots` table is something else and is not used
(decision 6).

### 3.2 Tables and columns

All are firm-owned, extend `BaseEntity`, add no column called `version`,
name each foreign key `FK_<table>_<column>`, carry no foreign key to `firms`,
and declare `sqlite_where` beside `postgresql_where` on every partial index.
Each migration is idempotent (checks before `add_column` and `create_table`,
backfills only rows still at their default) and runs per store through
`scripts/migrate_all_stores.py`.

**`batches`, new columns**

| Column | Type | Meaning |
| --- | --- | --- |
| `lot_reference` | String(40), not null after backfill | Our own running reference, one per lot, unique per firm among live rows (`UQ_batches_firm_lot_reference_active`). From a numbering series, as stock movements take theirs (`backend/app/inventory/services/movement_numbering.py`) |
| `per_purchase_line` | Boolean, default false | True on a lot made for one purchase line. False on every batch that exists today |
| `has_printed_batch` | Boolean, default true | False where the goods carry no printed batch. `batch_number` then holds the lot reference, and no screen or print shows a batch for it |
| `received_on` | Date | The day the lot arrived. Orders lots of equal expiry, oldest first |
| `source_document_type`, `source_document_id`, `source_document_line_id`, `source_document_number` | String(30), two bare UUIDs, String(80) | What made the lot: `GOODS_RECEIPT`, `OPENING_STOCK`, `ADJUSTMENT`, `REPACK`, `CARRIED_FORWARD`. Bare ids, the convention every downstream document follows |

The key `UQ_batches_firm_batch_product` becomes a partial unique index over
the same three columns, covering only rows where `per_purchase_line` is
false. A firm on today's method keeps "the same number is the same batch",
held by the database. Lots per purchase line are free to repeat a printed
number.

**`batch_valuations`, new table: what each lot is worth**

| Column | Type | Meaning |
| --- | --- | --- |
| `firm_id` | UUID, indexed | The firm |
| `batch_id` | UUID, FK `batches.id` RESTRICT, unique | The lot |
| `product_id` | UUID, FK `products.id` RESTRICT | For sums per product |
| `quantity_on_hand` | Numeric(18,4) | What the firm owns of the lot, in every warehouse and bucket |
| `unit_cost` | Numeric(18,6) | Cost of one stock unit |
| `total_value` | Numeric(18,4) | Value left. The issue that empties the lot takes all of it, so a lot closes at exactly zero |

It is the shape of `product_valuations`, one level down, and like it holds
one figure per firm, not per warehouse, so a transfer moves no value. Cost
sits here and not on `batches` for two reasons: a batch stores no quantity
(the rule since `20260813_0073`), and a batch response can then never leak a
cost to somebody not allowed to see it.

**`stock_lot_settings`, new table: one row per firm**

| Column | Type | Meaning |
| --- | --- | --- |
| `firm_id` | UUID, one live row per firm | The firm. A firm with no row is on Average |
| `costing_method` | String(20), not null | `AVERAGE` or `BY_LOT` |
| `switched_on` | Date, null | The day the firm moved to `BY_LOT` |

`product_valuations.costing_method` already exists. The switch-over stamps
it per product, so the valuation reads the method off a row it already
loads, with no extra read per movement.

**Document lines**

| Table | Change | Why |
| --- | --- | --- |
| `goods_receipt_lines` | None in L2. It already carries batch, expiry, MRP, selling price, PTR, PTS | One receipt line makes one lot |
| `purchase_invoice_lines` | None. Each already names its receipt line | Lot to receipt line to bill line is the trace |
| `delivery_note_line_batches` | Add `inventory_transaction_id` (bare UUID) and `cost_amount` Numeric(18,4) | The lots a line took, each with the movement that carried it and what it cost. Fixes gap 5 |
| `sales_invoice_lines` | None. A bill line reads its lots through the note line it bills | Every sale ships through a delivery note, typed or raised for it. One record of what left, not two that can disagree |
| `sales_return_line_batches` | New: `sales_return_line_id` (FK, CASCADE), `firm_id`, `batch_id` (FK RESTRICT), `quantity`, `cost_amount`, `inventory_transaction_id` | A return line can go back into several lots |
| `purchase_return_lines` | None. `batch_id` is filled from the receipt line it is raised off | The lot is known, not typed |
| `opening_stock_lines` | Add `mrp`, `selling_price`, `ptr`, `pts`, `purchase_date`, `supplier_bill_reference` (text). Drop the second key `UQ_opening_stock_lines_batch_product_location`; a firm on Average keeps that refusal in the service | Day-one stock is lots too, and two old lots of one batch at two costs must fit on one document |

### 3.3 Where the lot is created: the goods receipt

**Chosen: when the goods receipt completes.** That is the one place stock
arrives today, whether a person types the receipt or the supplier's bill
raises and completes it. Stock that is on the shelf must be sellable the
same minute, and a sale needs a lot to take from. Creating the lot at the
bill would leave goods received on Monday and billed on Thursday with no lot
for three days.

For this customer's way of working, one screen where the supplier's bill is
typed and stock arrives, the receipt and the bill are the same moment, so
the lot carries the bill's own figures.

Rules at the receipt, for a firm costing by lot:

- Every stocked receipt line makes **one new lot**, always. A line with a
  printed batch keeps that number; a line without gets our reference. No
  joining an earlier lot, even at the same cost: the customer's old program
  works this way, the trace to one supplier bill stays exact, and there is
  no comparison that has to be right to the last paisa.
- Free units of the same item arrive in the line's lot and lower its cost. A
  different item given free is its own line, so its own lot, at zero cost.
- Rejected and damaged units sit in the same lot, blocked from sale.
- Service and capital goods lines make no lot, as they make no stock today.
- Cancelling a receipt removes its lot. It is refused once any of the lot
  has been sold, transferred or returned.

**When the bill's rate is not the receipt's** (a firm that types both): the
lot is corrected for the units still in it, and the share of units already
gone posts to purchase price variance. Today the whole difference goes to
variance. See decision 3.

### 3.4 Choosing the lot at billing

1. Lots past their expiry on the document's date are left out, as today.
2. **Nearest expiry first.** Lots with no expiry come after dated ones.
3. Equal expiry, or none: **oldest `received_on` first**, then lot
   reference. So goods with no batch leave first in, first out.
4. The picker shows one row per **batch, expiry, MRP and selling prices**.
   Lots that agree on all four are one row with their total; the server
   takes the oldest first inside the row. Lots that differ are separate
   rows, which is "pick per price and batch".
5. The bill maker may change the split. A choice that is not the default is
   audited (`fefo_skipped` today), and the firm's existing batch rules still
   apply: near expiry, customer's minimum shelf life, reason required.
6. A sales order's reservation holds lots in the same order, and a pinned
   batch becomes a pinned lot.
7. The MRP ceiling and price from the batch work per lot, unchanged.

The rate a line starts at keeps today's order: typed, price list, the lot's
own rate, price level, product price.

### 3.5 What each document stores

| Document | Stores | Cost it moves at |
| --- | --- | --- |
| Goods receipt line | Its lot (`batch_id`) | The line's net cost per unit, as worked out today |
| Supplier's bill line | The receipt line; the lot through it | Corrects the lot only if its rate differs |
| Sales order line | A pinned lot, optional | None; a hold moves no value |
| Delivery note line | Its lots in `delivery_note_line_batches`, with quantity, movement and cost | Each lot's own cost |
| Sales bill line | Nothing new; `cost_amount` is the sum of its note line's lots, pro rata where part of the line is billed | Read, not moved |
| Sales return line | Its lots in `sales_return_line_batches`. Only lots its source line shipped may be named; by default the last lot taken is the first refilled | The cost each unit left with |
| Purchase return line | The lot of the receipt line it is raised off | The lot's cost |
| Cancelling any of these | Puts back, or takes out, the same lots | The value of the original movement, not today's cost |

### 3.6 The other ways stock moves

| Movement | Rule |
| --- | --- |
| Transfer between warehouses or branches | The lot travels with its reference, cost and prices. No value moves, as today |
| Adjustment down, write-off, expiry, breakage | Names its lots (the same default order) and leaves at their cost |
| Adjustment up, stock found at a count | Into a lot the person names, at that lot's cost; or a new lot, source `ADJUSTMENT`, at a typed cost, the item's newest lot cost when left blank |
| Physical count | One count line per stock row, which is already one per lot and place |
| Opening stock | Every line is a lot, source `OPENING_STOCK`, with its cost, MRP, prices, batch, expiry and purchase date |
| Quarantine, damage | A bucket inside the lot's own stock row. No value moves |
| Repack, kits | What is used leaves its lots at their cost; what is made is a new lot, source `REPACK`, costed at the value used |
| Serial numbers | A unit already belongs to a batch, so to a lot. Unchanged |
| Landed cost added later | Onto the lots of that receipt for the units still in them; the share of units gone posts to purchase price variance |
| A principal's price cut, a supplier's rebate by credit note | Unchanged: income or variance, never back into a lot (`docs/LEDGER_POSTING_RULES.md`) |
| Negative stock | Refused for a firm costing by lot: a sale with no lot has no cost and nothing to trace. Decision 4 |

Units: a lot's cost, MRP and prices are per stock unit, as batch prices and
the average are today. A line in boxes converts the way it does now
(`docs/UOM_FRAMEWORK.md`).

## 4. Books

### 4.1 How value is worked out

- **Stock value** is the sum of what is left in every lot.
- **Cost of goods sold** on a dispatch is the sum of the value taken from
  each lot it drew.
- **First in, first out** is the order lots are offered and taken in. The
  cost booked is always that of the lots actually taken, so when the bill
  maker picks a newer lot the books follow the goods. Marg, Busy and SAP
  Business One cost batch goods this way.
- Inside one lot the cost is one figure. It changes only by a correction
  (section 3.3), a landed cost, or units coming back at another cost.
- `product_valuations` is still kept for every item: quantity, total value,
  and the average the two give. Reports and checks that want one figure per
  item read it; it no longer decides what a movement is worth.

### 4.2 What changes in ledger posting

The rule in `docs/LEDGER_POSTING_RULES.md` stands: a leg facing stock is
valued from the movement. Every posting already reads the stock ledger row,
so the accounts and the journals do not change. The value on the row does.

| Event | Journal (unchanged) | Value, for a firm costing by lot |
| --- | --- | --- |
| Goods receipt | Dr Inventory, Cr goods received not invoiced | The lot's cost |
| Supplier's bill at another rate | Difference to purchase price variance | Units still in the lot: Dr or Cr Inventory, and the lot is corrected. Units gone: variance, as now |
| Dispatch | Dr cost of goods sold, Cr Inventory | Sum of the lots taken |
| Sales return | Dr Inventory, Cr cost of goods sold | The cost the units left with |
| Purchase return | Cr Inventory at the movement, Dr payable at the document, gap to variance | The lot's cost, so no gap when the supplier credits what was charged |
| Cancelled receipt, dispatch or return | The mirror of the original | The original movement's value, so no gap |
| Adjustment, write-off | As today | The lot's cost |
| Transfer, quarantine, reservation | Nothing | Nothing |

One new movement type, `COST_CORRECTION`, moves value and no quantity, the
way `LANDED_COST` does today.

Two things get better as a side effect. A lot closes at exactly zero, so the
paise the stock account and the valuation can part by (D-STK-20) no longer
build up. And a purchase return of what was bought leaves no variance.

### 4.3 The costing method is a firm setting

`AVERAGE` (today) or `BY_LOT`, per firm, in `stock_lot_settings`. Not per
item: one firm, one method, one stock figure the accountant can state in a
sentence. Tally and ERPNext allow a method per item; we do not need it and
it doubles every test. A firm on `AVERAGE` behaves exactly as today in
stock rows, picking, cost and reports.

### 4.4 A firm already trading on Average: the switch-over

The method is changed by its own action, never by saving a settings form,
and never silently.

1. Somebody with the finance settings permission asks to switch, naming the
   day. The screen first shows what will happen: items, stock value, the
   date.
2. In one transaction per firm, every item's stock on hand becomes lots,
   source `CARRIED_FORWARD`:
   - a batch that exists becomes a lot of its own;
   - stock with no batch becomes one lot per item with our reference, and
     its stock rows now name it;
   - each lot's cost is **the item's average on that day**.
3. **Nothing is re-valued and no journal is posted.** Each item's lots add
   up to its value before the switch to the paisa, any rounding difference
   on its largest lot. The totals are compared before and after, and the
   switch rolls back if one item differs.
4. From then on new receipts make lots at their own cost, and old stock
   leaves at the carried average until it is gone.
5. A stock movement dated before `switched_on` is refused afterwards, as a
   date in a closed period is. Stock value as on an earlier day is still
   read the old way, so past reports do not move.
6. The switch is one way (decision 2). The start of a financial year is the
   natural day, and the screen says so.

A new firm that starts on `BY_LOT` has nothing to carry: its opening stock
is entered as lots.

## 5. Effect on existing features

| Feature | Effect |
| --- | --- |
| Stock valuation report | For a firm by lot: value is the sum of lots; a past day is the signed sum of movement values up to it, added up by the database. A drill-down lists an item's lots with cost, MRP and value. The comparison with the Inventory account stays |
| Value at MRP (backlog 109) | Already per batch, so already per lot |
| Stock ageing | Today it assumes FIFO because movements do not say which unit left. By lot it reads `received_on` and is exact |
| Batch stock, expiry monitor, near-expiry alerts | Work per lot. Lots of one printed batch can be shown summed, with the lots beneath |
| Margin reports, sales analysis | Margin per bill line becomes exact per lot. A margin-by-lot report is new |
| Sales returns | Back into the lot, at the cost out. `hold returns until checked` unchanged |
| Purchase returns | Out of the receipt line's lot. Capped by what is left in that lot |
| Price lists, promotions, loyalty | Work on the item, so a new lot needs nothing set up. The line's starting rate keeps its order (section 3.4). An offer's free goods leave from lots like any units |
| Price floor and below-cost warning | Judged against the cost of the lots the line takes, where known; the item's average before a lot is chosen |
| Commission on margin | Reads `cost_amount` on the bill line, which becomes the lots' cost. The snapshot rule is unchanged |
| Supplier free goods, principal claims at cost | Read the lot's cost |
| GST, e-invoice, TDS and TCS | No effect. Tax is never part of cost |
| Prints | Bill and challan already print a row per batch with expiry and MRP. Rows that agree are merged; the lot reference and the cost never print |
| The import (`docs/SWATHI_IMPORT_PLAN.md`) | Closes gap G1. Step 9, opening stock by lot, becomes possible: the template gains MRP, prices, purchase date and supplier bill reference. History bills (way A) move no stock and are not affected |
| Permissions | Lot cost and margin are sent only to holders of `PRODUCT_VIEW_COST_PRICE` and are left out of the response for others, not hidden by the screen |
| Stock rows | One per lot and place. Emptied lots keep a zero row, so stock lists show rows holding stock unless asked, and the by-item summary stays the first view |
| Performance | Lots grow with purchase lines, not with bills: a firm of 2,400 sales bills in five months had about 1,500 purchase lines. Each movement reads and writes one more row by a unique key. Picking reads an item's lots holding stock, through the index already there. Lists read lot costs once per page (`children_by_parent`), and id lists go through `over_chunks`. The valuation and the stock statement are re-timed on PERF01 (110,000 invoices) before the work is called done, with a `BY_LOT` variant of `scripts/seed_volume_firm.py` |

## 6. Build steps for L2

Each step is one pull request, mergeable and testable alone. A firm on
`AVERAGE` must behave exactly as before after every step.

| # | Step | Migration | Proved by |
| --- | --- | --- | --- |
| 1 | The tables: new `batches` columns with `lot_reference` backfilled, the key made partial, `batch_valuations`, `stock_lot_settings`. No behaviour changes | **Yes** | Schema registry test; the PostgreSQL insert test for every deployed table |
| 2 | The valuation: `_apply_valuation` values by lot where the item's method is `BY_LOT`; a reversal carries the original movement's value. The method is set only by a test fixture | No | Unit tests of the worked example in section 1, to the paisa |
| 3 | Receiving: every stocked receipt line of a by-lot firm makes a lot with its source; cancelling removes it. Opening stock lines as lots, with the new columns and the import template | **Yes** (opening stock) | Receipt and opening stock tests; drive over HTTP on a fixture firm |
| 4 | Choosing: the order of section 3.4, lots for goods with no batch, the availability route answers lot rows with cost only to those allowed | No | Allocation tests on PostgreSQL for the ordering; picker route tests |
| 5 | Selling: the delivery note keeps each lot's movement and cost; the bill line's cost is read per line; prints merge equal rows | **Yes** | Two lines of one item from two lots show two costs; print tests |
| 6 | Returns: sales return into the lots it left, with `sales_return_line_batches`; purchase return out of the receipt's lot; every cancel path | **Yes** | The return of the worked example; cancel tests leave no variance |
| 7 | The rest of stock: transfers, adjustments, write-offs, counts, quarantine, repack; negative stock refused | No | One test per row of section 3.6 |
| 8 | Bill rate correction and landed cost onto the lot (`COST_CORRECTION`) | No | Ledger tests: Inventory account equals the sum of lots |
| 9 | The switch-over action, its preview, the proof by totals, the refusal of earlier dates, the settings screen | No | Integration test on PostgreSQL across two stores; a firm with two years of history switched and compared |
| 10 | Reports: valuation by lot and its drill-down, ageing from `received_on`, margin by lot, price floor on lot cost | No | Report tests; totals agree with the Inventory account |
| 11 | Screens, new UI only: lot rows in the picker, the lot's page with its trace (receipt, supplier's bill, sales, returns), cost shown by permission | No | Widget tests; clicked on a fixture firm |
| 12 | Seeders, PERF01 re-timed, reference docs, user guide, QA cases, then an inventory round and a finance round on a by-lot firm | No | `scripts/time_routes.py`; the round's check file |

## 7. What L3 needs from the lot

L3 is built later. This is what the lot must carry for it, and where.

| L3 needs | Where it lives | In L2 or L3 |
| --- | --- | --- |
| The purchase price the margin is worked on | `batch_valuations.unit_cost`, before GST | L2 |
| The margin used, changeable on the purchase line | `margin_percent` on `goods_receipt_lines` and on `batches` | L3 adds both |
| The default margin by goods type | `default_margin_percent` on `firm_goods_types` (`backend/app/products/models/goods_type.py`) | L3 |
| The worked-out price, belonging to that lot only | The lot's own rate columns on `batches`. A price worked out for one lot never touches the item's price or another lot | L2 keeps them per lot; L3 fills them |
| Retail and wholesale price per lot | `batches` already holds three rates: `selling_price`, `ptr`, `pts`. Proposed: retail is `selling_price`, wholesale is `ptr`, no new columns | L3, with M13 |
| Rounding to the nearest rupee, as a setting | One more column on `stock_lot_settings` | L3 |
| GST on top | Lot rates are before tax, as every rate in the ranking is. L3 decides whether the rounded figure is the rate before tax or the price with tax | L3 |
| Cost and margin on the bill line, on screen only | The line's lots and their cost (section 3.5), sent only to `PRODUCT_VIEW_COST_PRICE`, and read by no print service | L2 sends cost; L3 shows margin |

## 8. What is deliberately not in this design

- **A costing method per item**, or LIFO, standard cost, monthly average.
- **Moving a firm on Average onto the lot structure** while it stays on
  Average. Backlog 103's single stock shape for every firm is a later item
  (decision 5).
- **Switching back** from by lot to Average.
- **The margin, the rounding and the retail and wholesale labels.** L3.
- **History bills and replaying old years** (import ways A and B). A return
  against a history bill has no lot in our stock; it will need a rule when
  history bills are designed (proposed: a new lot at a typed cost).
- **Custom fields on a lot** (shade, grade), named in backlog 103.
- **The free quantity register** and **discount sources** (backlog 99, 100).
- **Box count and piece count on one line** (L4) and **offers on the bill
  line** (L6).
- **A lot per warehouse.** Cost is one figure per lot across the firm, as
  the average is today.
- **Removing the old `lots` table.** See decision 6.

## 9. Decisions for the owner

Each has the recommended answer first.

1. **Is the costing method a firm setting, Average or By lot?**
   **Yes: per firm, By lot for the first customer's firms, every existing
   firm stays on Average until switched.** One method per firm is what an
   accountant can sign; a method per item doubles the testing for no asked
   need. To confirm with the CA: the cost of a sale is the cost of the lots
   actually taken, first in first out being the default order.
2. **May a firm switch, and may it switch back?**
   **Any day, one way, stock carried in at that day's average, nothing
   re-valued.** Going back would have to melt lots into an average and lose
   every trace; the start of a financial year is the suggested day.
3. **The supplier's bill comes at another rate than the receipt.**
   **Correct the lot for the units still in it; the share already sold goes
   to purchase price variance.** Stock then stands at what was really paid.
   It cannot arise where the bill itself brings the stock in, which is how
   the first customer works. The CA confirms.
4. **Selling an item with no stock in any lot.**
   **Refuse it for a firm costing by lot.** A sale with no lot has no cost
   and no supplier's bill behind it. The purchase is typed first; the item's
   own "allow negative stock" switch is ignored for such a firm.
5. **Should firms on Average also get a lot per purchase line now?**
   **No, later and as its own item.** It would reshape the stock of every
   firm already trading for no change they asked for. L2 builds the one
   structure; moving the rest onto it is a migration to do once the first
   customer is live on it.
6. **The word Lot is already a menu (production lots).**
   **Call the new thing Lot on screen, and hide the old Lots menu for
   firms costing by lot.** Nothing in stock writes the old table. Removing
   it altogether is a clean-up to agree separately.

## 10. Decided here by convention

Recorded so nobody has to ask again.

| Point | Choice | After |
| --- | --- | --- |
| What the lot is | The batch row, one per purchase line | Marg, Busy |
| Where the lot is made | Goods receipt completion | Where stock arrives; ERPNext, Tally |
| Same batch, second delivery | A new lot, always | The customer's old program; Marg |
| Goods with no batch | Our lot reference, never shown or printed | Backlog 103, "a batch the system keeps" |
| Order of leaving | Nearest expiry, then oldest received, then lot reference | FEFO then FIFO; Marg |
| Cost when the pick is overridden | The lot actually taken | SAP Business One batch costing |
| Free units of the same item | In the line's lot, lowering its cost | Today's rule |
| A different item given free | Its own lot at zero cost | Today's rule |
| Sales return | Same lot, at the cost it left with; last lot taken refilled first | Backlog 103 |
| Purchase return | The receipt line's own lot, at its cost | Better than ERPNext and Odoo, which use an ordinary issue |
| Transfer | The lot travels; one cost per lot firm-wide | Today's rule for the average |
| Stock found | An existing lot, or a new one at a typed cost | Tally |
| Landed cost after receipt | Onto units still in the lot; the rest to variance | ERPNext, without a repost |
| Later rebates and price cuts | Never into a lot | The existing ledger rule |
| Cost storage | Its own table, not on the batch | Batches hold no quantity; cost must not leak |
| Method stored | Per firm, stamped per item at the switch | One read per movement |
