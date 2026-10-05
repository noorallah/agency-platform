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

`customers.minimum_shelf_life_days` (migration 0223; the field needs the
firm's EXPIRY_TRACKING feature) is how many days goods must have left when they
reach the customer -- a hospital or a chain often asks for six months. It is
read on the delivery note's date as a date the goods must last to. Earliest-
expiry allocation **passes over** a batch expiring before it, exactly as it
passes over an expired one (`allocate_for_dispatch(keep_until=)`), and names it
if the rest fall short; so with nobody choosing, a compliant batch simply goes.
The picker's availability takes `customer_id`, flags such a batch
`short_for_customer` and never pre-fills it; `batch-check` reports
`SHORT_SHELF_LIFE` and `would_block`. A batch chosen by hand anyway meets
`shelf_life_policy`.

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

**Price from batch** (`batch_sale_settings.price_from_batch`, off): where a
line's batch is chosen, the screen fills its rate from the batch's selling
price, ahead of the price list. The server takes the rate it is sent, as for
any rate.

§79 is complete.

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
3. **FEFO / FIFO allocation** is not implemented — batch data is ready but the allocation engine belongs to Purchase/Sales phases.
4. **QC Hold integration** — `blocked_qty` and `quarantine` status are data-model ready but no QC module enforces them yet.
5. **Lot hierarchy depth** — `parent_lot_id` supports one level of parent; deep multi-level lot trees may require recursive CTE queries (not yet implemented).
6. **Serial movement history** — current model records current status/owner but does not yet maintain a full movement log table. Extension point: `serial_movements` table in Phase 18.

---

## Breaking Changes

None. All existing APIs and tables are unchanged. New columns on `products` and `inventory_transactions` are nullable with `server_default=False` to avoid migration failures on populated databases.

---

_Phase 16B completed. Ready for Phase 17 (Purchase) integration._
