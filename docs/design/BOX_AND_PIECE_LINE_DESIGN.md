# A box count and a piece count on one line: design note

**Status: design note for row L4 of `docs/CUSTOMER_BUILD_TASKS.md`, written
2026-10-13. Nothing in it is built.** Row L5 is built from it. The owner reads
and approves it before any code. Its sister note is
`docs/design/LOT_COST_DESIGN.md` (row L1); the two were checked against each
other and section 5 says how they meet.

Words used here. The **stock unit** is the unit an item's stock is counted in
(a piece, a strip). A **pack** is the larger unit the item comes in (a box, a
case) and the **pack size** is how many stock units it holds. A **pair** is
the two figures typed on a line: so many packs and so many loose pieces.

**Answered by the owner on 2026-10-13** and written in below: an item has a
box and a piece and no third level; the rate is always per piece; boxes and
pieces are converted, so 2 boxes + 17 becomes 3 + 5 and every figure
downstream (dispatch, what is left, the print) is worked the same way; a
supplier carries the same mark a customer does; a document keeps the layout
it was saved in; stock is shown in boxes by a toggle.

## 1. What it does for the user

On every buying and selling document a line can be typed as two figures, boxes
and loose pieces, where today it takes one quantity in one unit. The rate is
the rate of one piece. Free goods are typed the same way, as free boxes and
free pieces. The screen shows the total in pieces beside what was typed, the
bill prints the boxes and the pieces, and stock, tax and the books go on
working in pieces exactly as they do now. An item that has no pack shows one
quantity box, as today.

### Worked example

One item, kept in pieces, packed 12 to a box. GST 12%.

| Step | Typed | In pieces | Money | Stock |
| --- | --- | --- | --- | --- |
| Purchase | 10 boxes + 0 pieces at 8.00 a piece; free 1 box + 0 pieces | 120 bought, 12 free | Taxable 960.00, GST 115.20, bill 1,075.20 | 132 in, at 960.00 over 132 = 7.27 each |
| Sale | 3 boxes + 5 pieces at 10.00 a piece; free 0 boxes + 2 pieces | 41 charged, 2 free | Taxable 410.00, GST 49.20, bill 459.20 | 43 out; 89 left, shown as 7 boxes + 5 pieces |
| Part delivery of that sale | 2 boxes + 0 pieces now, the rest later | 24 now; 17 charged and 2 free still owed | Nothing billed yet | 24 out |
| Customer returns | 1 box + 1 piece | 13 | Credit 130.00 + GST 15.60 = 145.60 | 13 back in |

- **The tax base is pieces times the rate of a piece**: 41 x 10.00. The free
  2 pieces are worth nothing on the bill and carry no tax, as today.
- **Nothing is rounded.** No figure such as 3.4167 of a box exists anywhere.
- **Boxes are always full boxes.** Typing 2 boxes + 17 pieces turns into
  3 + 5 as the cell is left, and that is what every later document shows.
- **The bill prints** Qty 3/5 (x12), Free 0/2, Rate 10.00, Amount 410.00.

## 2. What exists today, and what is missing

### Already there

| Subject | What exists | Where |
| --- | --- | --- |
| One unit per line | A line holds one quantity and names one unit. It can be boxes, or pieces, never both | `SalesOrderLineWrite` in `backend/app/sales_order/schemas/sales_order.py`, `PurchaseLineWrite` in `backend/app/purchase/schemas/purchase.py`, and the seven other line schemas |
| Conversion to stock | A line in boxes is converted to stock units by a dated, numbered rule, and the line keeps the factor and the rule's number. An unknown pair of units is refused, never counted at 1 | `convert_quantity`, `stock_unit_of`, `buying_units_of` in `backend/app/uom/services/uom_service.py`; `docs/UOM_FRAMEWORK.md` |
| Pack size of an item | A unit set ("Strip, box of 10") fills the item's units and writes the item's own rule, purchase unit to stock unit | `backend/app/uom/services/unit_sets.py`, `products.purchase_uom_id`, `uom_conversion_rules` |
| Loose pieces off a box line | A bill or a return may be typed in pieces against a line in boxes. The row keeps the box figure and, beside it, what was typed (`entered_quantity`) | Migration `20261006_0343`; `continued_quantity`, `stated_line` in the uom service |
| Free goods | One figure, `free_quantity`, in the line's own unit, on all nine line tables. Blank means "the offer decides", zero means "none" | The line models under `backend/app/*/models/`; `docs/PRICING_AND_PROMOTIONS.md` |
| Offers count pieces | An offer counts stock units and gives stock units. Free pieces earned by a line in boxes become a free line of their own, in pieces | Same doc, D-PRC-39 |
| Price lists, commission per unit | Count stock units | Same doc, the table "Which quantity each thing counts" |
| What the bill prints | One Qty figure with its unit, and the free figure: "10 + 1 free" on A4, a Free column on the half page | `backend/app/sales_invoice/services/invoice_pdf.py`, `half_page_pdf.py`, `invoice_print_service.py` |
| Pack barcodes | A pack's barcode is read on the counter bill (adds the pack's pieces) and in the product box of five editors (finds the item) | `docs/UOM_FRAMEWORK.md`, "Where a pack's code is read" |
| Line editors, new UI | One **Qty** box, one **Free** box, a **Unit** column. On the sales order, the quotation and the sales bill the unit is shown, not chosen: the line is in the item's stock unit. The purchase order has a unit list | `desktop/lib/ui/sales/sales_order_editor_phase2.dart`, `sales_invoice_editor_phase2.dart`, `desktop/lib/ui/purchases/purchase_order_editor_phase2.dart`, columns from `desktop/lib/phase2/document_page.dart` |
| Old program | Its item list holds pieces per case | `docs/SWATHI_IMPORT_PLAN.md`, section 1 and gap G4 |

### Missing

1. **Two figures on one line**, and **free goods as two figures.** 3 boxes
   + 5 pieces is typed today as 41 pieces, or as two lines.
2. **The pack size kept on the line.** A line in pieces does not say it was
   12 to a box that day.
3. **Boxes and pieces on any print.**
4. **The pack size on the item row the screens read.** The desktop knows the
   item's units, not how many pieces its box holds.
5. **A Free box on a sales bill typed straight in.** The new UI's bill of
   products has Qty and Unit and no Free column, though the server accepts
   `free_quantity` on such a line. The first customer bills this way.
6. **A switch** saying whether a firm types boxes and pieces.

## 3. The design

### 3.1 The quantity stays one figure in pieces; boxes and pieces are worked out from it

A line typed as boxes and pieces **is a line in the stock unit**. Its quantity
is the total in pieces (41), its rate is the rate of a piece, its conversion
factor is 1. Beside them the line keeps the pack size used, and nothing
else: **boxes = the whole packs in the total, pieces = what is over.** The
pair is worked out wherever it is shown and is never stored, so it cannot
disagree with the quantity (the owner's answer 3: converting makes dispatch
and every other sum the same sum).

Why this and not a line in boxes with a fraction:

- About 160 places read a line's quantity as a count in the line's unit: every
  "already billed", every cap, the order's status, commission, offers, claims
  (`docs/UOM_FRAMEWORK.md`, "The storage decision"). In pieces they all stay
  right with no change.
- A box line holding pieces needs 3.4167 boxes. That road cost eight defects
  in one day (D-PRC-37 and after). A piece line has no fraction to go wrong.
- Rate per piece is the requirement, and it is already what `unit_price`
  means on a line in the stock unit.
- GSTR-1's HSN rows and the e-invoice state pieces on one row, where a box
  line and a piece line of one item make two rows today.

This is Tally's compound unit ("Box of 12 Pcs") and the main and alternate
quantity of Busy and Marg: one stock figure, two entry figures.

A line typed as boxes and pieces is always in the stock unit. Existing
documents, and firms that type "2 BOX" on a line in boxes, are untouched.

### 3.2 Which pack an item uses

**Box and piece, two levels only** (the owner's answer 1). One pack per item
per side, read from the item's own units. No new master. Most items have
one box, used on both sides; the table says which wins where the item's
buying and selling units differ.

| Document side | The pack is |
| --- | --- |
| Buying | The item's purchase unit, where it is not the stock unit. Else its sales unit |
| Selling | The item's sales unit, where it is not the stock unit. Else its purchase unit |

The pack size is the factor of the item's conversion rule from that unit to
the stock unit **on the document's date**, through the resolver every line
uses today (the item's own rule before the firm-wide one). It must be a whole
number greater than 1. Otherwise the item has no pack and its lines show
pieces only.

A new helper `pack_of(product, side, on_date)` beside `stock_unit_of` is the
one answer, for the server and for the item rows the desktop reads. Larger
packagings (carton, pallet) in `product_packaging_levels` are scanned, not
typed. An item sold in a third pack still takes a line in that unit.

### 3.3 When the pack size changes later

A supplier moves from 12 to a box to 10. The firm adds a new version of the
rule from that date; nobody edits the old one (`docs/UOM_FRAMEWORK.md`,
"Effective dating").

- A saved line keeps **its own** `pack_size`. It reads and reprints
  "3 x 12 + 5" for ever, and its 41 pieces never move.
- A line that continues another line **inherits the source line's pack
  size**, not today's. An order of 3 boxes + 5 delivered after the change is
  still counted 12 to a box, and a return next year reads the bill's pack.
- A new document takes the pack size in force on its date. Editing a draft
  keeps the line's stored pack size unless its product changes.

### 3.4 What is typed, and what the server does with it

The two cells are a way of typing one quantity. The screen adds them up and
sends the quantity in pieces in the field every line has today. **No
quantity field is added to any write schema.**

Each line write schema gains one optional field:

| Field | Meaning |
| --- | --- |
| `pack_size` | The pack size the screen used to add the two cells up. Sent only by a line typed as boxes and pieces |

Rules:

1. The server works out the item's pack size itself (3.2), or takes the
   source line's (3.3), and stores it on the line. It never trusts the one
   sent.
2. Where `pack_size` is sent and differs from the server's, the line is
   refused: "Line 2: a box of this item holds 10, not 12. Open the line
   again." This is the one way the two cells could add up to a wrong total:
   an item row read before its pack changed.
3. **Boxes are always full boxes.** The screen turns 2 + 17 into 3 + 5 as
   the cell is left and says so once ("17 pieces is 1 box + 5"). Nothing
   else is possible, because only the total is kept.
4. `free_quantity` is typed the same way, as two cells that add up to the
   one figure the line has today, and keeps its three answers: absent takes
   the offer, zero refuses it, a figure is the figure. Free goods an offer
   gave are shown split by the same sum.
5. A line sent with no `pack_size` is a line typed in pieces. Every client
   that exists today keeps working, and the same line can be shown either
   way.
6. The whole-number rule is asked of the total against the stock unit, as
   today.
7. Update follows the standing rule: the document is dumped with
   `exclude_unset`, lines are reconciled on their line number, and a line's
   own fields are that line as sent.

### 3.5 Rate

**The rate is per piece, and only per piece** (the owner's answer 2: always
per piece). It is what the requirement asks, what the old program does, and what the stored `unit_price` already is.
The side panel shows the rate of a box (rate x pack size) for reading against
a supplier's price list. A box rate is not typed in L5: two rate boxes are two
chances to disagree, and a box rate that does not divide (100.00 over 12)
needs a rounding rule on every line. A firm that buys at a rate per box keeps
today's line in BOX.

Discounts, price lists, price levels, the price floor and the MRP ceiling are
all per stock unit already and are unchanged.

### 3.6 How the pack size travels down the chain

| Document | Quantity shown as boxes and pieces | Pack size comes from |
| --- | --- | --- |
| Quotation line | `quantity` | The item, on the quotation's date |
| Sales order line | `quantity` | The item; or the quotation line it came from |
| Delivery note line | `current_delivery_quantity` | The order line |
| Sales bill line | `current_invoice_quantity` | The note or order line; the item for a bill typed straight in |
| Sales return line | `current_return_quantity` | The note or bill line |
| Purchase order line | `ordered_quantity` | The item |
| Goods receipt line | `accepted_quantity` | The order line |
| Supplier's bill line | `current_invoice_quantity` | The receipt line; the item for a bill typed straight in |
| Purchase return line | `current_return_quantity` | The receipt line |

- **Every quantity of a line is shown by the one sum**, at that line's own
  pack size: ordered, delivering now, delivered, left, billed, returned. A
  part delivery of 24 against 41 reads 2 x 12 + 0 now and 1 x 12 + 5 left.
  This is what the owner's answer 3 is for: dispatch and every remainder
  come out in full boxes without anybody working them out.
- **Nothing about the pair is stored or inherited**, only the pack size. Caps
  and "left to bill" stay sums of pieces, as the rule on lifecycle status
  requires.
- **A document raised for the user** (the order and note behind a counter
  bill, the order and receipt behind a supplier's bill, a quotation turned
  into an order) takes its source line's pack size and the header's layout
  flag.
- Rejected, damaged, scrap and "to shelf" figures are typed in pieces only.
  They are exceptions counted by hand, and four more pairs per line would
  crowd the receipt and return screens.
- The two cells are offered only where the source line is itself in the
  stock unit. Pieces typed against an older line in BOX go the existing
  road (`entered_quantity`).

### 3.7 Rounding

There is none to design. Quantity is a count of pieces; boxes are its whole
packs and pieces the rest, exact at the four places a quantity holds. Money is pieces x rate per piece, rounded
where a line's amount is rounded today, and tax is worked on that. Parts of a
line add up because they are whole pieces. An item kept in a decimal unit
(25 kg bag) may type 2 bags + 3.5: the loose figure takes the stock unit's
own decimal rule and is always less than one pack.

### 3.8 Tables and columns

Two columns, the same two on each of the nine line tables in 3.6
(`sales_quotation_lines`, `sales_order_lines`, `delivery_note_lines`,
`sales_invoice_lines`, `sales_return_lines`, `purchase_order_lines`,
`goods_receipt_lines`, `purchase_invoice_lines`, `purchase_return_lines`),
declared once as a column mixin in `backend/app/uom/models/` so the nine
cannot drift.

| Column | Type | Meaning |
| --- | --- | --- |
| `pack_uom_id` | UUID, null, FK `uoms.id` RESTRICT, named `FK_<table>_pack_uom_id` | The pack's unit, for the word printed (BOX, CASE) |
| `pack_size` | Numeric(18,4), null | Stock units in one pack when the line was written |

Both null on every line that exists today, so there is no backfill; such a
line is shown split by the item's pack size on the document's date. They are
set on any new line of an item that has a pack, however it was typed. The
first draft of this note kept four more columns for the pair as typed; with
boxes always full boxes they would only repeat the quantity, so they are
gone.

Two switches, one per side, each a Boolean, not null, default false:
`sales_workflow_settings.box_and_piece_entry` and
`purchase_workflow_settings.box_and_piece_entry`.

One column on the customer, `customers.box_and_piece_entry`, Boolean, not
null, default false: this customer's selling documents open with the box
cells (the customer's answer of 2026-10-13, decision 5). It is read only
where the firm's selling switch is on. It is added in the same revision,
guarded the same way, and joins the customer form, the customer import
template and the customer response.

The same column on the supplier, `vendors.box_and_piece_entry`, for buying
documents (the owner's answer 4: suppliers supply in boxes and pieces too).
Read only where the firm's buying switch is on; on the supplier form, its
import template and its response.

One column on each of the nine document headers, `box_and_piece_entry`,
Boolean, not null, default false: the layout this document was saved in
(the owner, 2026-10-13). It is declared once, in the same mixin file as the
line columns, and added in the same revision. It is written on create and
on update like any other header field, absent meaning leave it alone. A
document raised from another (order to note, note to bill, bill to return)
starts with its source's value. The flag says how the document is shown
and typed; the lines are the same lines either way.

Repo rules observed: the tables already extend `BaseEntity`; no column is
called `version`; the foreign key is named on its referring column; every
type is one SQLite holds. The migration is one revision, idempotent (it
checks each column before `add_column`), run per store through
`scripts/migrate_all_stores.py`. Item rows gain `pack_size` and
`pack_unit_code` on the response only, read once per page in bulk as
`pack_codes` is. Every field the desktop sends is declared on the write
schema in an earlier step than the screen that sends it.

## 4. Screens (new UI only)

**Which layout a document opens in.** Where the firm's switch for that side
is on, a new document follows its party: **boxes and pieces** for a customer
marked *Bills in boxes and pieces* or a supplier marked *Buys in boxes and
pieces*, **pieces only** for any other. The bill maker can change
it for the document in hand with one toggle above the lines, *Boxes and
pieces / Pieces only*; that changes nothing on the customer. **The choice
is saved on the document, and a saved document reopens as it was saved**,
whatever the party's mark or the firm's switch says by then. Switching
either way changes no quantity: the same lines are shown as one figure or
as two.

**The line.** In the boxes-and-pieces layout the line table of each editor
replaces Qty and Free with four narrow boxes:

| # | Product | HSN | Box | Pcs | Free box | Free pcs | Unit | Rate | Disc % | Taxable | GST | Amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Item A | 3004 | 3 | 5 | | 2 | PCS | 10.00 | | 410.00 | 12 | 459.20 |
| 2 | Item B (no pack) | 3304 | (closed) | 7 | (closed) | | PCS | 55.00 | | 385.00 | 18 | 454.30 |

- **Keyboard.** Product, Box, Pcs, Free box, Free pcs, Rate, Disc, then the
  next line; Tab and Enter both move on. Pieces typed past a full box move
  into the Box cell as the cell is left. For an item with no pack the two box
  cells are closed and the cursor passes over them.
- **No prefill.** Blank free boxes say nothing ("Blank takes the offer"); a
  typed 0 refuses it, the standing rule for discount and free boxes.
- **The side panel** for the line being typed: "Box of 12. 3 boxes + 5 pcs =
  41 pcs. Free 2 pcs. Rate of a box 120.00." An offer's free goods read
  "Free with (offer): 1 box + 2 pcs".
- **Continuing documents.** Delivering, Billing, Accepted and Returning each
  become the two boxes; Ordered, Delivered, Due and Left to bill read
  "3 x 12 + 5".
- **The sales bill typed straight in gains the free boxes** it lacks today,
  switch on or off (one Free box where the switch is off).
- One shared widget in `desktop/lib/ui/workspace/` draws and reads the cells
  for all nine editors, so there is one implementation of the sum.
- **Calls.** None new. The pack size rides on the item rows each editor
  already reads. The switch rides on the stages settings the order and bill
  editors already read, and on a call already made in the others. The
  customer's mark rides on the customer row the picker already returns. The
  live totals come from today's preview call, which takes the same line
  fields.

**Lists and views.** Document lists show totals and do not change. A
document's view and its lines read "3 box + 5 pcs (41)".

**The switches.** *Sales Stages* and *Purchase Settings* each get one row:
"Type quantities as boxes and pieces". Off for every existing firm. With the
selling switch on, the customer form shows one tick, *Bills in boxes and
pieces*, off to start, and the customer list can be filtered by it. With
the buying switch on, the supplier form shows *Buys in boxes and pieces*
the same way. In the
boxes-and-pieces layout an item with a pack shows the four boxes and an item
without shows pieces only. There is no switch per item: leaving the Box cell
blank is typing in pieces.

**Stock, shown as boxes and pieces** (the owner, 2026-10-13: it makes a
count easy to check against the shelf). Where either of the firm's switches
is on, every screen and report that states a stock quantity of an item with
a pack has a toggle, *Show boxes*, remembered per user: stock on hand, the
stock ledger, the stock statement and valuation, the batch (lot) list and
the below-reorder list. On, 89 pieces of a 12-pack read **7 x 12 + 5** with
the 89 kept beside it; an item with no pack reads pieces. The figure is
worked out for display by the one shared formatter from the quantity the
screen already holds and the item's pack size today: nothing is stored, no
call is added, and the Excel download writes boxes, pieces and total as
three number columns.

**The stock count.** The same toggle is on the count screen and its sheet:
on, the expected stock and the difference read as boxes and pieces. The
counted quantity is still typed in pieces. It is a way of showing and
nothing more (the owner, 2026-10-13).

**Prints.** Every document printed by the shared renderer (bill, order
confirmation, challan, purchase order, credit note, thermal bill):

| Paper | Today | In the boxes-and-pieces layout |
| --- | --- | --- |
| Full page | Qty, UOM; "10 + 1 free" under Qty | The **Qty** cell reads **3/5 (x12)**; free goods read "Free 0/2" |
| Half page | Qty, Free | **Qty** "3/5 (x12)", **Free** "0/2", in the columns the page has now |
| 80 mm roll | Qty x rate | "3/5 (x12)" on the item's second row |

**The form is the customer's own** (the owner, 2026-10-13, option B, after
the customer's sample bill with boxes was read): one Qty cell, boxes before
the slash and loose pieces after it, so 3 boxes and no pieces is **3/0**.
His bill does not say what a box holds; ours adds it in brackets, **(x12)**,
as the owner asked, so the paper can be checked without the item list. No
column is added and none is renamed, which is why the half page keeps its
widths. The owner may change the form later; it lives in one formatter.

- An item with no pack prints a plain quantity, as today ("2.00"), also as
  on his bill.
- The total quantity under the lines reads the same way: boxes before the
  slash, loose pieces and the pieces of items with no pack after it.
- This form prints only on a document saved in the boxes-and-pieces
  layout. Any other document prints its quantities as today.
- `InvoiceLineBlock` gains the box figure, the piece figure and the pack
  size for the charged and the free quantity; the layouts do no arithmetic.

## 5. Effect on existing features

| Feature | Effect |
| --- | --- |
| Stock | None. Movements, reservations and balances are in stock units and are handed the same figure as today. Stock screens may show "7 boxes + 5" beside 89 through one shared formatter |
| Lots (L1 note) | No conflict. A lot's quantity, cost, MRP and prices are per stock unit, and a pair line is in stock units. One receipt line still makes one lot. The lot picker counts pieces; its rows may show boxes beside them. Where one line leaves from two lots, each printed row's boxes and pieces are worked from that row's pieces by the line's pack size; the typed pair belongs to the whole line. L1 says `goods_receipt_lines` gets no change in L2; L5 adds these six columns, which L2 does not read. A pack size per lot is not kept (section 7) |
| Price lists, price levels, commission per unit, credit and discount limits, price floor | None. All are per stock unit; 3 boxes + 5 asks the list at 41 |
| Offers (buy N get M) | Counted in pieces, as now. The free pieces go **on the line itself**, since the line is in pieces; the separate free line that a box line needs (D-PRC-39) does not arise. Shown as boxes + pieces |
| Supplier schemes, free goods in | The same: counted and given in pieces, typed as a pair. They lower the cost per piece as today |
| Free quantity register (backlog 99) | Its figures are pieces, which is what the lines will hold. Nothing here blocks it |
| Returns | Typed as a pair, capped in pieces, at the source line's pack size. "Of which free" is a pair too |
| GST, e-invoice, GSTR-1 | State pieces at the rate of a piece, on one HSN row per item. No UQC change |
| Reports | Quantities stay pieces. Sales and purchase registers and the stock statement may show the split through the shared formatter. No report is re-keyed |
| Supplier's order minimum and multiple | These count the buying unit. For a pair line the server compares boxes x pack size + pieces converted to that unit, so "minimum 5 boxes" still holds. A small change in the purchase order service, in step 6 |
| Rate contract kept per box | Not read by a line in pieces today. Step 6 converts its rate by the pack size, as `price_in_unit` does for price levels |
| Pack barcode | Counter bill: a pack scan adds 1 to Box where the pack scanned is the line's pack, else its pieces to Pcs. The product box in the editors still only finds the item |
| Import from the old program | Pieces per case becomes the item's pack: stock unit piece, purchase unit case, the item's own rule (gap G4 of `docs/SWATHI_IMPORT_PLAN.md`). Bills brought in as history carry pieces; whether the old lines keep cases apart was not established (see the report with this note) |

## 6. Build steps for L5

Each step is mergeable and testable alone. After every step a firm with the
switch off behaves exactly as before. Steps 1 to 8 are server only.

| # | Step | Migration | Proved by |
| --- | --- | --- | --- |
| 1 | The two columns on nine tables through one mixin; the two switches; the customer's and the supplier's mark; the layout flag on the nine headers. Nothing reads them | **Yes** | Schema registry test; the PostgreSQL insert test for every deployed table |
| 2 | `pack_of`, and one small value object that splits a total into full boxes and pieces and adds two cells up. Item rows answer `pack_size` and `pack_unit_code`, read in bulk | No | Unit tests: both sides, no pack, a dated change of pack size, statement count of the item list |
| 3 | Quotation and sales order: the pack size stored and answered, the `pack_size` precondition of 3.4, the header flag, the pack size handed from quotation to order, offers' free goods shown split | No | Order tests; the worked example's sale to the paisa |
| 4 | Delivery note and sales bill: inherit the pack size, part delivery shown in full boxes; the bill typed straight in and the counter bill hand the pair to the documents raised behind them; the preview route | No | Chain tests; a pack size changed between order and note |
| 5 | Sales return: the pack size of the line returned, caps in pieces | No | The worked example's return |
| 6 | Purchase order and goods receipt; the supplier's minimum and the rate contract read a pair line rightly | No | The worked example's purchase: 132 in at 7.27 |
| 7 | Supplier's bill (and the order and receipt it raises) and purchase return | No | Chain tests; free goods back to the supplier |
| 8 | Prints: `InvoiceLineBlock`, the one formatter for "3/5 (x12)", full page, half page, roll, challan, purchase order, credit note, the total quantity | No | Print tests on the worked example; a mixed document; a bill that still fits half a page; the customer's sample (`bill with box.pdf` in the customer papers, never copied here) read beside ours |
| 9 | The switch on both settings screens; the tick on the customer and supplier forms, their import columns and list filters; the toggle above the lines; the shared two-box cells; sales order, quotation and sales bill editors, with the Free boxes the direct bill lacks | No | Widget tests incl. keyboard order at 800x600; a guard that every line key the desktop sends is declared by the server |
| 10 | Delivery note, sales return, purchase order, goods receipt, supplier's bill and purchase return editors | No | Widget tests; clicked on a fixture firm |
| 11 | Pack scan on the counter bill; *Show boxes* on the stock screens, reports, their downloads and the count screen, display only | No | Counter bill test; report tests; the toggle changes no stored figure and adds no call |
| 12 | The import's pack from pieces per case; reference docs, user guide, QA cases; driven over HTTP end to end | No | The check file of the round |

## 7. What is deliberately not in this design

- **A rate per box typed on the line.** Shown, not typed (3.5).
- **Three levels on one line** (carton + box + piece). One pack and loose.
- **A pack size per lot.** The pack is the item's on the day. An item whose
  new supply comes 10 to a box where the old stock was 12 reads both in the
  new size from that date.
- **Keeping a line as typed where it is not full boxes** (2 + 17). Boxes are
  always full boxes.
- **Two cells for rejected, damaged, scrap and to-shelf quantities.**
- **Opening stock, transfers, adjustments and counts typed as a pair.** They
  are shown as boxes and pieces by the toggle and typed in pieces.
- **Restating old lines.** A line saved in BOX, or in pieces, stays as it is.
- **A switch per item**, and firm-chosen words for the two column headings.
- **A UQC mapping for GST returns**, and **the old UI**, which sends no pair
  and so goes on typing pieces.
- **Offers chosen on the bill line** (L6) and **the free quantity register**
  (backlog 99).

## 8. Decisions for the owner

Each has the recommended answer first.

1. **Which pack does an item use when it has several?**
   **ANSWERED by the owner, 2026-10-13: box and piece only.** Two levels,
   one box per item. Where an item's buying and selling units differ, each
   side uses its own (3.2). A carton above the box is scanned, not typed.
2. **Is the rate typed per piece only?**
   **ANSWERED by the owner, 2026-10-13: always per piece.** The rate of a
   box is shown beside it and not typed.
3. **Is 2 boxes + 17 pieces kept as typed, or tidied to 3 + 5?**
   **ANSWERED by the owner, 2026-10-13: converted.** Boxes are always full
   boxes, so dispatch, what is left and the print are all the same sum. The
   line therefore stores no pair at all, only the pack size (3.1, 3.8).
4. **How do boxes and pieces print on the bill?**
   **ANSWERED by the owner, 2026-10-13, option B: as the customer's own
   bill prints them, with the box size added.** One Qty cell reading
   "3/5 (x12)", and Free as "0/2". The first answer here was two columns,
   Box and Pcs; the customer's sample bill with boxes, read the same day,
   prints "3/0" in the Qty cell, and his staff and shops know that form. It
   can be changed later.
5. **Who gets the two boxes?**
   **ANSWERED by the customer, 2026-10-13: it is chosen per customer, and
   the bill maker can change it on the bill in hand.** So: the firm's two
   switches stay as the master, off for every existing firm; with the
   selling switch on, a customer marked *Bills in boxes and pieces* gets
   the box cells and any other customer gets pieces only; a toggle above
   the lines overrides it for one document. The document keeps its own
   choice and reopens in it (the owner, 2026-10-13). A supplier carries the
   same mark for buying documents (the owner's answer 4). An item with no
   pack shows pieces only; no switch per item.

No decision in this note is open. Two further points were put to the owner
and closed on 2026-10-13. **An item has one box size, the one set on the
item**: if a supply arrives packed differently, it is still counted by the
item's own box and the rest as pieces; a pack size per lot is not wanted
(section 7). **Box and piece are the only two units a line is typed in**,
and nothing is priced by the box.

## 9. Decided here by convention

| Point | Choice | After |
| --- | --- | --- |
| Stored truth | One quantity in the stock unit; boxes and pieces are worked out from it | Tally compound unit; Busy and Marg alternate quantity |
| Pack size on the line | Snapshotted; inherited by continuing lines | The repo's rule that a downstream document inherits its source |
| Pack size source | The item's dated conversion rule, never a second table | `docs/UOM_FRAMEWORK.md`: rules convert, packaging levels describe |
| Client sends | The total, and the pack size it added up with; the server reads the pack size itself and refuses a different one | A flag or factor the caller sets is not a control |
| Free goods | Two more cells that add up to `free_quantity`; blank and zero keep their meanings | `docs/PRICING_AND_PROMOTIONS.md` |
