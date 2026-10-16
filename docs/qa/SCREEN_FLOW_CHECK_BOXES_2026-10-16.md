# Screen cases, boxes and pieces (L5): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_bp_test.dart`. Build row L5, steps 9 to 11
(`docs/CUSTOMER_BUILD_TASKS.md`); the HTTP halves are
`docs/qa/checks/box_piece/p_bp_01..07`.
Firm **TEST03** (*Test Fixtures Lot Firm*), the `lot-firm` fixture reused as
it stood, both `box_and_piece_entry` switches already on
(`docs/qa/checks/box_piece/setup.py`). Users: `t1016gxe3.lotadmin@fixtures.local`
(Firm admin) and `t1016gxe3.lotviewer@fixtures.local` (VIEWER), password
`Fixture@2026pw`. Window 1600x1000.

Every run makes its own masters over HTTP, as the admin, **before the app
starts**, named with the minute and the user (`1209A` = 12:09, admin):

- item **P** `0B<tag>-P` (*BP box <tag>*): kept, based and stocked in PIECE,
  sold and bought in BOX, with its own rule 1 BOX = 12 PIECE from 2026-04-01;
- item **N** `0B<tag>-N` (*BP loose <tag>*): pieces only;
- customers *BP boxed cust* (`BC<tag>`, Bills in boxes and pieces) and
  *BP plain cust* (`BD<tag>`, not), supplier *BP supplier* (`BV<tag>`, Buys in
  boxes and pieces);
- a purchase order of 89 pieces of P at pack 12 (flag on), approved, and its
  receipt completed: 89 in stock.

The `continue` part adds: order A of 41 at pack 12 approved, its note
dispatched, a **draft bill** of the note and a **draft return** of 5; order B
of 41 approved with nothing delivered; a **draft PO** of 41; an approved PO
of 41 with a **draft receipt**; a **draft supplier's bill** of the 89 received.
The SI counter step turns the order and note stages off over HTTP and puts
them back right after its save and again in `finally`.

## How to run it

From `desktop/` in Git Bash, one run at a time, each in a brand-new
`TEMP`/`TMP` folder:

```
IT_EMAIL=t1016gxe3.lotadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1500 bash integration_test/run.sh sc_bp_test.dart
IT_EMAIL=t1016gxe3.lotviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1500 bash integration_test/run.sh sc_bp_test.dart
```

`IT_PART=settings`, `parties`, `order`, `quote`, `counter`, `continue`,
`prnew` (the purchase return alone) or `stock` (comma separated) runs those
parts; the masters are made every time. The viewer runs `settings`,
`parties`, `order` (its own steps BP-V-1/2) and `stock`.

**This machine fought the runs.** Of 27 runs, 13 died with "did not
complete" (`PathNotFoundException ... flutter_test_listener.*`) partway, most
during the `continue` part's HTTP set-up; parts were then run on their own.
Three times, after such a death, the linker could no longer write
`build\windows\x64\runner\Debug\agency_desktop.exe` at that path
(`LNK1104`; even a plain file write of that one name was refused, any other
name was not) and the worktree had to be moved (`git worktree move`) to a new
folder and rebuilt; it is now `D:\ws\agencyApp\ws-click-bp-d`.

## What was clicked, and the values seen

| Id | Step | Firm admin | Viewer | Screen vs server |
| --- | --- | --- | --- | --- |
| BP-SET | Settings > Selling > Sales stages > Open: the box row | PASS | PASS | Switch on (admin may change it, viewer may not); server `box_and_piece_entry` true |
| BP-SET | Settings > Buying > Purchase settings > Buying stages Open: the box row | PASS | PASS | As above, purchase settings |
| BP-PARTY | Customers: Filters > *Bills in boxes and pieces* Yes > Apply | PASS | PASS | Boxed customer listed, plain one gone; `GET /customers?box_and_piece_entry=true` the same |
| BP-PARTY | Customer form: the tick | PASS | PASS | Tick on, server true; editable for the admin, not the viewer (opened with Open) |
| BP-PARTY | Suppliers: Filters > *Buys in boxes and pieces* Yes | PASS | PASS | Boxed supplier listed; server the same |
| BP-PARTY | Supplier form: the tick | PASS | **FAIL** | Admin: tick on, server true. Viewer: no Edit, Open or View at all (D-UI-113) |
| BP-PARTY | Plain customer ticked and saved (admin) | PASS | — | "Customer updated."; server `box_and_piece_entry` true |
| BP-PARTY | The server refuses the viewer the tick | — | PASS | `PUT /customers/{id}` 403 |
| BP-SO-1 | New order, boxed customer, item P | PASS | — | Toggle *Boxes and pieces / Pieces only* in the Product heading; Box, Pcs, Free box, Free pcs headings and four cells |
| BP-SO-2 | 2 box + 17 pcs, leave the cell | PASS | — | Cells 3 / 5, note "17 pcs is 1 box + 5", side panel "Box of 12. 3 boxes + 5 pcs = 41 pcs. Rate of a box 120.00." |
| BP-SO-3 | Pieces only, then back | PASS | — | Qty heading, line Qty 41, box cells gone; back on: 3 / 5 |
| BP-SO-4 | Line 2 item N | PASS | — | Box and Free box cells closed; 15 typed stays 15 |
| BP-SO-5 | Save draft | PASS | — | "Order drafted."; server header flag true, line 1 quantity 41.0000 pack 12.0000, line 2 15 with no pack |
| BP-SO-6 | Pack 12 sent for item N (HTTP) | PASS | — | 422 "Line 1: this item has no box to type it in. Type the quantity in pieces." |
| BP-QT-1/2 | New quotation, same typing, saved | PASS | — | Cells 3 / 5, same note and side panel; server QT flag true, 41.0000 pack 12.0000 |
| BP-SB-1/2 | Counter bill (stages off), same typing, saved as draft | PASS | — | Toggle on, cells 3 / 5, side panel as above; server SI flag true, 41 at pack 12; draft cancelled (200), stages put back |
| BP-DN | New delivery note on order B | PASS | — | Toggle on, "3 x 12 + 5", cells 3 / 5; server order line 41 pack 12 |
| BP-SI | Draft bill of note A (Edit) | PASS | — | "dispatched 3 x 12 + 5", cells 3 / 5; server pack 12, flag true |
| BP-SR | Draft return of note A (Edit) | PASS | — | "3 x 12 + 5", cells - / 5 (5 returned); server pack 12 |
| BP-PO | Draft purchase order of 41 (Edit) | PASS | — | Cells 3 / 5 (a PO continues nothing); server pack 12, flag true |
| BP-GR | Draft receipt on the PO of 41 (Edit) | PASS | — | "3 x 12 + 5", cells 3 / 5; server pack 12 |
| BP-PI | Draft supplier's bill of the receipt of 89 (Edit) | PASS | — | "7 x 12 + 5", cells 7 / 5; server pack 12 |
| BP-PR | New purchase return of the receipt of 89 | PASS | — | Toggle on, "7 x 12 + 5", cells 7 / 5; server receipt line 89 pack 12 |
| BP-ST | Stock > Inventory, item P, *Show boxes* | PASS | PASS | Row 89 / 89 before, "7 x 12 + 5 (89)" in Current and Available after; server `current_quantity` 89.0000, pack 12 BOX |
| BP-V-1 | Viewer opens a saved boxed order | — | PASS after fix | No New; Open gives the view: line "PIECE ... 41.0000"; before the fix it read **BOX 41.0000** (D-UI-112) |
| BP-V-2 | Viewer posts an order in boxes (HTTP) | — | PASS | 403 |

Tallies (last result of each step over the part runs, the HTTP set-up steps
included): Firm admin passed 27, failed 0, not run 2 (print, scan); Viewer
passed 10, failed 1 (BP-PARTY supplier form, D-UI-113, open), not run 2.
No app error and no overflow in any run.

## Defects

| Id | Severity | Screen | What | Status | Guard |
| --- | --- | --- | --- | --- | --- |
| D-UI-112 | Medium | Sales order and sales bill views (Open on a saved document) | A line typed in boxes and pieces is stored in the stock unit (`inventory_uom_id` PIECE, no `sales_uom_id`); the view's Unit fell back to the product's selling unit, so 41 pieces read **"BOX 41.0000"**, 41 boxes (492 pieces) to anyone reading it. | Fixed: `DocumentLineLabels.unitOf` takes `stockUnitId`; the order and bill views pass the line's `inventory_uom_id` | `document_line_units_test.dart`: *a line counted in the stock unit shows it, not the selling unit (D-UI-112)* |
| D-UI-113 | Medium | Suppliers list | The supplier toolbar has no View/Open (only Edit, shown with VENDOR_UPDATE) and the form has no read-only mode, so a user without the update right cannot open a supplier at all: the viewer sees *Buys in boxes and pieces* only as a list filter. The customer list offers Open in a read-only form. | **Open**, not fixed here: needs a read-only supplier form | — |

Observation, not registered: the delivery note view builds its Unit the same
way from `sales_uom_id` only (`delivery_note_management_page.dart`); its line
model does not read `inventory_uom_id`, so a boxed note line probably reads
BOX there too. Not clicked.

## Not clicked

- Prints (*3/5 (x12)*): the printing round.
- A pack scan on the counter bill (step 11): needs a scanner.
- Stock ledger, valuation, batches, count sheet and below-reorder with *Show
  boxes*: only the Inventory list was clicked.
- Typing boxes on the purchase-side editors and the delivery note, return and
  bill of notes (only their continuing figures and loaded cells were read);
  none of those was saved from the screen.
- The delivery note and purchase return drafts open as views, not editors
  (no Edit on a draft), so they were checked through **New** instead.
- Free box / Free pcs with an offer; the customer import's *BoxesAndPieces*
  column; the 800x600 layout.
