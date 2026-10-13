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
- **The bill prints** Box 3, Pcs 5, Free 0 + 2, Rate 10.00, Amount 410.00.

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

### 3.1 The quantity stays one figure in pieces; the pair is how it was typed

A line typed as boxes and pieces **is a line in the stock unit**. Its quantity
is the total in pieces (41), its rate is the rate of a piece, its conversion
factor is 1. Beside them the line keeps the pair as typed and the pack size
used. Total = boxes x pack size + pieces, and the server checks that sum.

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

A line is **either** a pair in the stock unit **or** a quantity in a named
unit as today. A pair sent beside another unit is refused by name. Existing
documents, and firms that type "2 BOX", are untouched.

### 3.2 Which pack an item uses

One pack per item per side, read from the item's own units. No new master.

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
  "3 boxes + 5" for ever, and its 41 pieces never move.
- A line that continues another line **inherits the source line's pack
  size**, not today's. An order of 3 boxes + 5 delivered after the change is
  still counted 12 to a box, and a return next year reads the bill's pack.
- A new document takes the pack size in force on its date. Editing a draft
  keeps the line's stored pack size unless its product changes.

### 3.4 What is typed, and what the server does with it

Every line write schema gains four optional fields. The quantity field each
schema has today stays required and stays the truth.

| Field | Meaning |
| --- | --- |
| `box_quantity` | Packs typed. Whole number, as BOX is a whole-number unit |
| `piece_quantity` | Loose stock units typed. May be more than a pack (2 boxes + 17 is accepted) |
| `free_box_quantity`, `free_piece_quantity` | The same for free goods |

Rules:

1. A pair is sent with the total. The server works out the pack size itself
   and refuses a total that is not boxes x pack size + pieces: "Line 2: 3
   boxes + 5 pieces of 12 is 41, not 40."
2. The client never sends the pack size. It is the server's to read and store.
3. A pair for an item with no pack is refused, naming the item.
4. `free_quantity` keeps its three answers: absent takes the offer, zero
   refuses it, a figure is the figure. A free pair needs `free_quantity`
   beside it and must add up to it. Free goods an offer gave, which nobody
   typed, store no pair; screens and prints show them split by the pack size.
5. **The pair is kept as typed.** 2 boxes + 17 stays 2 and 17; the screen
   shows "= 41 pcs (3 boxes + 5)" beside it and rewrites nothing.
6. A line sent with no pair is a line typed in pieces. Every client that
   exists today keeps working.
7. The whole-number rule is asked of what was typed: the box figure against
   the pack unit, the piece figure against the stock unit.
8. Update follows the standing rule: the document is dumped with
   `exclude_unset`, lines are reconciled on their line number, and a line's
   own fields are that line as sent.

### 3.5 Rate

**The rate is per piece, and only per piece.** It is what the requirement
asks, what the old program does, and what the stored `unit_price` already is.
The side panel shows the rate of a box (rate x pack size) for reading against
a supplier's price list. A box rate is not typed in L5: two rate boxes are two
chances to disagree, and a box rate that does not divide (100.00 over 12)
needs a rounding rule on every line. A firm that buys at a rate per box keeps
today's line in BOX.

Discounts, price lists, price levels, the price floor and the MRP ceiling are
all per stock unit already and are unchanged.

### 3.6 How the pair travels down the chain

| Document | Quantity the pair states | Pack size comes from |
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

- **Each line stores its own pair** for its own quantity. A part delivery of
  2 boxes + 0 against 3 boxes + 5 is a note line of 24 pieces with pair 2
  and 0.
- **What is left is shown, never stored**: 17 pieces left reads "1 box + 5".
  Caps and "left to bill" stay sums of pieces, as the rule on lifecycle
  status requires.
- **A document raised for the user** (the order and note behind a counter
  bill, the order and receipt behind a supplier's bill, a quotation turned
  into an order) is handed the pair with the quantity. The inheritance rule
  of `docs/PRICING_AND_PROMOTIONS.md` then covers the pair as it covers price
  and discount.
- **Free goods inherited pro rata** by a part bill stay a figure in pieces
  with no stored pair, shown split.
- Rejected, damaged, scrap and "to shelf" figures are typed in pieces only.
  They are exceptions counted by hand, and four more pairs per line would
  crowd the receipt and return screens.
- A pair is allowed only where the source line is itself in the stock unit.
  Pieces typed against an older line in BOX go the existing road
  (`entered_quantity`).

### 3.7 Rounding

There is none to design. Quantity is boxes x a whole pack size + pieces, exact
at the four places a quantity holds. Money is pieces x rate per piece, rounded
where a line's amount is rounded today, and tax is worked on that. Parts of a
line add up because they are whole pieces. An item kept in a decimal unit
(25 kg bag) may type 2 bags + 3.5: the piece figure takes the stock unit's
own decimal rule.

### 3.8 Tables and columns

Six columns, the same six on each of the nine line tables in 3.6
(`sales_quotation_lines`, `sales_order_lines`, `delivery_note_lines`,
`sales_invoice_lines`, `sales_return_lines`, `purchase_order_lines`,
`goods_receipt_lines`, `purchase_invoice_lines`, `purchase_return_lines`),
declared once as a column mixin in `backend/app/uom/models/` so the nine
cannot drift.

| Column | Type | Meaning |
| --- | --- | --- |
| `pack_uom_id` | UUID, null, FK `uoms.id` RESTRICT, named `FK_<table>_pack_uom_id` | The pack's unit, for the word printed (BOX, CASE) |
| `pack_size` | Numeric(18,4), null | Stock units in one pack when the line was typed |
| `box_quantity` | Numeric(18,4), null | Packs typed |
| `piece_quantity` | Numeric(18,4), null | Loose units typed |
| `free_box_quantity` | Numeric(18,4), null | Free packs typed |
| `free_piece_quantity` | Numeric(18,4), null | Free loose units typed |

All null on every line that exists today, so there is no backfill.
`pack_uom_id` and `pack_size` are set on any new line of an item that has a
pack, pair or not, so its remainders can always be shown split.

Two switches, one per side, each a Boolean, not null, default false:
`sales_workflow_settings.box_and_piece_entry` and
`purchase_workflow_settings.box_and_piece_entry`.

One column on the customer, `customers.box_and_piece_entry`, Boolean, not
null, default false: this customer's selling documents open with the box
cells (the customer's answer of 2026-10-13, decision 5). It is read only
where the firm's selling switch is on. It is added in the same revision,
guarded the same way, and joins the customer form, the customer import
template and the customer response.

One column on each of the nine document headers, `box_and_piece_entry`,
Boolean, not null, default false: the layout this document was saved in
(the owner, 2026-10-13). It is declared once, in the same mixin file as the
line columns, and added in the same revision. It is written on create and
on update like any other header field, absent meaning leave it alone. A
document raised from another (order to note, note to bill, bill to return)
starts with its source's value. The server refuses a line holding a pair on
a document whose flag is off, so the flag and the lines cannot disagree.

Repo rules observed: the tables already extend `BaseEntity`; no column is
called `version`; the foreign key is named on its referring column; every
type is one SQLite holds. The migration is one revision, idempotent (it
checks each column before `add_column`), run per store through
`scripts/migrate_all_stores.py`. Item rows gain `pack_size` and
`pack_unit_code` on the response only, read once per page in bulk as
`pack_codes` is. Every field the desktop sends is declared on the write
schema in an earlier step than the screen that sends it.

## 4. Screens (new UI only)

**Which layout a document opens in.** A buying document follows the firm's
buying switch. A selling document, where the firm's selling switch is on,
follows its customer: **boxes and pieces** for a customer marked *Bills in
boxes and pieces*, **pieces only** for any other. The bill maker can change
it for the document in hand with one toggle above the lines, *Boxes and
pieces / Pieces only*; that changes nothing on the customer. **The choice
is saved on the document, and a saved document reopens as it was saved**,
whatever the customer's mark or the firm's switch says by then. A new
buying document takes the firm's buying switch and keeps it the same way.
Switching to pieces only on a document that has pairs keeps every total and
clears the pairs, after asking.

**The line.** In the boxes-and-pieces layout the line table of each editor
replaces Qty and Free with four narrow boxes:

| # | Product | HSN | Box | Pcs | Free box | Free pcs | Unit | Rate | Disc % | Taxable | GST | Amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Item A | 3004 | 3 | 5 | | 2 | PCS | 10.00 | | 410.00 | 12 | 459.20 |
| 2 | Item B (no pack) | 3304 | (closed) | 7 | (closed) | | PCS | 55.00 | | 385.00 | 18 | 454.30 |

- **Keyboard.** Product, Box, Pcs, Free box, Free pcs, Rate, Disc, then the
  next line; Tab and Enter both move on. For an item with no pack the two box
  cells are closed and the cursor passes over them.
- **No prefill.** Blank free boxes say nothing ("Blank takes the offer"); a
  typed 0 refuses it, the standing rule for discount and free boxes.
- **The side panel** for the line being typed: "Box of 12. 3 boxes + 5 pcs =
  41 pcs. Free 2 pcs. Rate of a box 120.00." An offer's free goods read
  "Free with (offer): 1 box + 2 pcs".
- **Continuing documents.** Delivering, Billing, Accepted and Returning each
  become the two boxes; Ordered, Delivered, Due and Left to bill read
  "3 + 5".
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
pieces*, off to start, and the customer list can be filtered by it. In the
boxes-and-pieces layout an item with a pack shows the four boxes and an item
without shows pieces only. There is no switch per item: leaving the Box cell
blank is typing in pieces.

**Prints.** Every document printed by the shared renderer (bill, order
confirmation, challan, purchase order, credit note, thermal bill):

| Paper | Today | With a pair on any line |
| --- | --- | --- |
| Full page | Qty, UOM; "10 + 1 free" under Qty | **Box**, **Pcs** take the place of Qty and UOM; free goods read "Free 0 + 2" |
| Half page | Qty, Free | **Box**, **Pcs**, **Free** ("0 + 2"), in the width Qty and Free hold now |
| 80 mm roll | Qty x rate | "3 box x 12 + 5" on the item's second row |

The Box cell says how many pieces a box holds, as the customer asked on
2026-10-13: 10 boxes of 12 print as **10 x 12**, so the paper can be checked
without the item list. A line with no box prints the cell empty.

The two columns appear only on a document where a line holds a pair, the way
the "rate incl. GST" column appears today. A line with no pair on such a
document prints its quantity under Pcs. The total quantity line prints pieces.
The customer's own sample bill prints one Qty and one Free column, so this
layout is ours and not a copy of theirs.
`InvoiceLineBlock` gains the four figures and the pack's word; the layouts do
no arithmetic.

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
| 1 | The six columns on nine tables through one mixin; the two switches; the customer's mark; the layout flag on the nine headers. Nothing reads them | **Yes** | Schema registry test; the PostgreSQL insert test for every deployed table |
| 2 | `pack_of`, and one small value object that checks a pair against a total and splits a total for display. Item rows answer `pack_size` and `pack_unit_code`, read in bulk | No | Unit tests: both sides, no pack, a dated change of pack size, statement count of the item list |
| 3 | Quotation and sales order: the four fields on write and read, the refusals of 3.4, the pair handed from quotation to order, offers' free goods on a pair line | No | Order tests; the worked example's sale to the paisa |
| 4 | Delivery note and sales bill: inherit the pack size, own pair, part delivery; the bill typed straight in and the counter bill hand the pair to the documents raised behind them; the preview route | No | Chain tests; a pack size changed between order and note |
| 5 | Sales return: pair, "of which free" pair, caps in pieces | No | The worked example's return |
| 6 | Purchase order and goods receipt; the supplier's minimum and the rate contract read a pair line rightly | No | The worked example's purchase: 132 in at 7.27 |
| 7 | Supplier's bill (and the order and receipt it raises) and purchase return | No | Chain tests; free goods back to the supplier |
| 8 | Prints: `InvoiceLineBlock`, full page, half page, roll, challan, purchase order, credit note | No | Print tests on the worked example; a mixed document; a bill that still fits half a page |
| 9 | The switch on both settings screens; the tick on the customer form, its import column and list filter; the toggle above the lines; the shared two-box cells; sales order, quotation and sales bill editors, with the Free boxes the direct bill lacks | No | Widget tests incl. keyboard order at 800x600; a guard that every line key the desktop sends is declared by the server |
| 10 | Delivery note, sales return, purchase order, goods receipt, supplier's bill and purchase return editors | No | Widget tests; clicked on a fixture firm |
| 11 | Pack scan on the counter bill; the split shown on stock screens and registers | No | Counter bill test; report tests |
| 12 | The import's pack from pieces per case; reference docs, user guide, QA cases; driven over HTTP end to end | No | The check file of the round |

## 7. What is deliberately not in this design

- **A rate per box typed on the line.** Shown, not typed (3.5).
- **Three levels on one line** (carton + box + piece). One pack and loose.
- **A pack size per lot.** The pack is the item's on the day. An item whose
  new supply comes 10 to a box where the old stock was 12 reads both in the
  new size from that date.
- **Tidying a pair**, and **pairs for rejected, damaged, scrap and to-shelf
  quantities.**
- **Opening stock, transfers, adjustments and counts typed as a pair.**
- **Restating old lines.** A line saved in BOX, or in pieces, stays as it is.
- **A switch per item**, and firm-chosen words for the two column headings.
- **A mark on the supplier.** Buying follows the firm's switch alone; nobody
  has asked for it per supplier.
- **A UQC mapping for GST returns**, and **the old UI**, which sends no pair
  and so goes on typing pieces.
- **Offers chosen on the bill line** (L6) and **the free quantity register**
  (backlog 99).

## 8. Decisions for the owner

Each has the recommended answer first.

1. **Which pack does an item use when it has several?**
   **Its own purchase unit on buying documents and its own sales unit on
   selling ones, each falling back to the other; nothing new to set up.**
   One pack per side is what Tally, Busy and Marg offer, and the unit set
   already records it. A carton above the box is scanned, not typed.
2. **Is the rate typed per piece only?**
   **Yes; the rate of a box is shown beside it and not typed.** It is the
   requirement and the old program's way, and one rate box cannot disagree
   with itself. A firm buying at a box rate keeps a line in BOX.
3. **Is 2 boxes + 17 pieces kept as typed, or tidied to 3 + 5?**
   **Kept as typed, with the tidy figure shown beside it.** A supplier's
   bill may really say 2 and 17, and the line should read as the paper does.
4. **How do boxes and pieces print on the bill?**
   **ANSWERED by the customer, 2026-10-13: both are shown, and the box
   figure says how many pieces a box holds.** So: two columns, Box and Pcs,
   in place of Qty, the Box cell reading "10 x 12", and Free as "0 + 2",
   only on a bill that has such a line. This fits the half page's present
   width.
5. **Who gets the two boxes?**
   **ANSWERED by the customer, 2026-10-13: it is chosen per customer, and
   the bill maker can change it on the bill in hand.** So: the firm's two
   switches stay as the master, off for every existing firm; with the
   selling switch on, a customer marked *Bills in boxes and pieces* gets
   the box cells and any other customer gets pieces only; a toggle above
   the lines overrides it for one document. The document keeps its own
   choice and reopens in it (the owner, 2026-10-13). Buying follows the
   firm's switch. An item with no pack shows pieces only; no switch per
   item.

## 9. Decided here by convention

| Point | Choice | After |
| --- | --- | --- |
| Stored truth | One quantity in the stock unit; the pair is how it was typed | Tally compound unit; Busy and Marg alternate quantity |
| Pack size on the line | Snapshotted; inherited by continuing lines | The repo's rule that a downstream document inherits its source |
| Pack size source | The item's dated conversion rule, never a second table | `docs/UOM_FRAMEWORK.md`: rules convert, packaging levels describe |
| Client sends | The pair and the total; the server reads the pack size and checks the sum | A flag or factor the caller sets is not a control |
| Free goods | A second pair, summing to `free_quantity`; blank and zero keep their meanings | `docs/PRICING_AND_PROMOTIONS.md` |
