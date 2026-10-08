# Inventory, batches and serial numbers

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-05 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Stock

Everything here lives under **Inventory**, in two groups that must be clicked
open: **Stock** (Inventory, Opening Stock, Physical Count, Stock Ledger,
Transactions, Stock Summary, Stock Search) and **Batch & Serial** (Batches,
Lots, Serial Numbers, Expiry Monitor). Transfer, Write off and Quarantine are
toolbar buttons on the Inventory tab and act on the selected row.
### TC-STOCK-001 — The summary and the rows agree; the ledger explains the balance

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN. (`QA-B` received 4 then 6 into MAIN: 10 on hand.)
- **Steps**
  1. As the prepared **Firm admin**, Stock > All Stock screens > Stock > **Inventory**, filter Product `QA-B` → Apply. Then **Stock Summary**.
  2. Stock > **Stock Ledger**, filter Product `QA-B` → Apply; open one row's detail (eye icon). Then Transaction type `GOODS_RECEIPT` → Apply.
- **Expect**
  - Step 1: one row, MAIN, Current **10**, Available 10, Reserved 0; the summary's figure for the product agrees.
  - Step 2: two `GOODS_RECEIPT` rows, +4 and +6, each naming its GRN, with the balance after each; the last equals Current. The detail dialog is titled "Ledger details". Filtering by type leaves the two. *(Known: the type list offers values the server never writes and lacks some it does — BACKLOG §31.13.)*
### TC-STOCK-002 — Moving stock between warehouses posts no journal

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse. (50 of `QA-P` in MAIN; an empty warehouse `QA-W2` under HO.)
- **Steps**
  1. As the prepared **Firm admin**, Stock > All Stock screens > Stock > Inventory → select the `QA-P` / MAIN row → **Transfer**: quantity **3**, **Move it to** `QA-W2 - Overflow qa`, reference `QA-TRF` → **Transfer**.
  2. Refresh; Stock Ledger for the product; Accounts > Journal Entries.
  3. Transfer again with quantity **999**.
- **Expect**
  - Step 1: the dialog "Transfer stock" says how much is available; toast "Stock transferred."
  - Step 2: MAIN **47**, `QA-W2` **3** (a row appears), the product's total unchanged at 50. Ledger: `TRANSFER_OUT` 3 at MAIN and `TRANSFER_IN` 3 at W2, both `QA-TRF`. Journal: **no** entry — the footnote says why.
  - Step 3: refused in the dialog, in a red banner with the error icon: "The source holds 47.0000 available, so 999 cannot be transferred out of it." — before anything is sent.
### TC-STOCK-003 — Writing off, and holding stock back

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps**
  1. As the prepared **Firm admin**, select `QA-P` / MAIN → **Write off**: quantity **1**, reason Damage, reference `QA-WO` → Write off. Check the ledger and Journal Entries.
  2. **Quarantine** → **Hold back**, quantity **2**, reference `QA-QH` → Hold back. Then Quarantine → **Release**, quantity 2, reference `QA-QR` → Release.
  3. Quarantine → Hold back with quantity **999**.
- **Expect**
  - Step 1: "Stock written off."; MAIN **49**; ledger `WRITE_OFF` 1 `QA-WO`; the journal shows it (Dr Inventory Adjustment / Cr Inventory).
  - Step 2: "Quarantine updated."; ledger `QUARANTINE_HOLD`, then `QUARANTINE_RELEASE`; **no** journal for either. Note what the row shows between hold and release — **(HTTP)** the inventory row read `current_quantity` 47, `available_quantity` 47, `quarantine_quantity` 2 after holding 2 of 49 (driven); the plan expected Current to stay put while Available fell, so record which way the screen shows it.
  - Step 3: refused by name: "There is … to hold, so 999 cannot be."
### TC-STOCK-004 — A physical count posts only what was counted

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps:** as the prepared **Firm admin**, Stock > **Physical Count** → **+ New count**: branch HO, warehouse MAIN, today → Open. On the sheet find `QA-P - Fixture Product qa` (code and name, never an id); type **49** in Counted (Expected is 50); leave every other line blank. **Save progress**, close, reopen from the list → **Post count** → confirm.
- **Expect:** "PC-… opened over N lines." (N is every product in MAIN — other runs' too). Difference reads `-1` while typing. The list reads "1 of N lines counted", then "N lines · posted". After posting: MAIN **49**; ledger `ADJUSTMENT` −1 referencing the count; Journal Entries shows the adjustment; the uncounted lines moved nothing. The posted sheet is read-only: "Posted. The differences are in the ledger." If stock moved between opening the sheet and posting it, the difference posted is against the stock at posting, and the posted sheet's Expected column shows that figure, so Expected, Counted and Difference add up (`p_count_adds_up.py`).
### TC-STOCK-005 — Dispatch draws the earliest-expiring batch first

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (`QA-AMX` in three batches of 10: `-B1` **expired 30 days ago**, `-B2` expiring in 20 days, `-B3` in 400; an approved order for **5**.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Stock > **Batches**, search `QA-B`.
  2. Sell > Delivery Notes → **New** → the prepared order for 5 → read "Expected to ship from — earliest expiry first, decided at dispatch" (in the phase 2 editor the side panel instead lists the batches, already filled earliest expiry first; see TC-SELL-019) → **Save** → **Approve** → **Dispatch**.
  3. Batches again; Stock Ledger for `QA-AMX`.
  4. Stock > **Expiry Monitor**.
- **Expect**
  - Step 1: three batches, 10 available each, with their expiry dates.
  - Step 2–3: status DISPATCHED; ledger `DISPATCH` −5 referencing the note. **The 5 comes from `-B2`, the earliest batch that has *not* expired**; `-B1` is skipped. Fixed 2026-09-16; see defect **D-8-1**.
  - Step 4: the six cards — Expired Today, Expire in 7 Days, Expire in 30 Days, Total Expired, Quarantine, Recalled — with `-B1` counted as expired and `-B2` inside 30 days; then the **All Batches** grid (Batch #, Product, Status, Qty, Available, Expiry Date, Warehouse).
### TC-STOCK-006 — A delivery short of stock saves but will not dispatch

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (`QA-SHT` has **3** on hand and an approved order for **10**.)
- **Steps:** as the prepared **Firm admin**, Sell > Delivery Notes → **New** → the order for 10 → read the preview → Save → Approve → **Dispatch**.
- **Expect:** the preview ends "Short by … — there is not enough available stock to cover this line." Saving is allowed; **Dispatch is refused** with the server's sentence, "Insufficient available stock for dispatch line."; the note stays **APPROVED** and the ledger shows no DISPATCH.
### TC-STOCK-007 — A remembered filter from another firm is dropped

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (its platform admin can open both QA01 and the prepared firm.)
- **Steps:** sign in as the prepared **Platform admin**; switch into **QA01** → Stock > All Stock screens > Stock > Inventory → filter by any product → Apply. Switch into the prepared firm → the same tab.
- **Expect:** the tab renders; the remembered QA01 filter is dropped (the panel reads "Filters" with none active) and choosing the firm's own warehouse works. *(A remembered id from another firm used to take the section down with "This section failed to render".)*
### TC-STOCK-008 — Serial numbers carry their warranty

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty. (`QA-MIX`, 5 on hand, serials `QA-MIX-0001` to `-0005`.)
- **Steps:** as the prepared **Firm admin**, Stock > All Stock screens > Tracking > **Serial Numbers**; search `QA-MIX-`; open one row's detail; filter Status AVAILABLE.
- **Expect:** five rows, status AVAILABLE, warehouse MAIN; Warranty Start and End are empty until somebody enters them on the serial (a goods receipt carries no warranty dates; the prepared seeded serials carry a year). The detail is titled "Serial: QA-MIX-0001" with warranty start and end and the warehouse. The Status filter keeps all five.
### TC-STOCK-009 — A stock transfer as a document: dispatch, in transit, receive

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps:** as the prepared **Firm admin**: Stock > **Stock Transfers** → New from MAIN to the second warehouse, 20 of the product → Save. Open Stock > Stock Summary and Accounts > Journal Entries. **Dispatch**. Look at the two warehouses' stock and the valuation. Print the **challan**. **Receive** with 18 arrived, of which 3 damaged (the other 2 never arrived). Create a second transfer and **Cancel** it after dispatch; create a third and cancel it as a draft. Try to cancel the received one. Try to dispatch more than is free.
- **Expect:** the transfer is numbered **TO-…** with a timeline. Dispatch takes the quantity off MAIN at the moving average and puts it **in transit at the destination**, still owned at that figure: no journal is posted and the firm's valuation does not move; the destination's summary shows the goods on their way. The challan is a delivery challan without values. On receipt, each line says what arrived and what of it was damaged: 15 go on the shelf, **3 arrive blocked from sale** (as on a goods receipt), and the 2 that never arrived are written off to the inventory adjustment account at the average. Cancelling a dispatched transfer brings the goods back; a draft cancels freely; a received transfer is final. Dispatching more than is free is refused. The one-step Transfer on the Inventory tab still moves stock within a building. Batches travel as themselves; serial numbers are not carried yet.
### TC-STOCK-010 — Why stock is issued: internal use, staff, display, and the firm's own reasons

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a user holding INVENTORY_MANAGE_REASONS (the administrator).
- **Steps:** as the prepared **Firm admin**: Stock > All Stock screens > Stock > Inventory → select the product → **Write off** 2 with reason *Internal use*; again with *Staff* and *Display*; and once with *Damage*. Accounts > Ledgers: read the expense accounts. Settings > Stock > **Adjustment Reasons**: add a reason *Festival gift* with its own expense account; deactivate another. Write off 1 with the new reason. Post an adjustment with a reason code.
- **Expect:** the three new reasons post to their own expense accounts — *Stock Used in Business*, *Staff Welfare*, *Samples and Display* — and damage, expiry and loss stay on *Inventory Adjustment*. The reasons list is the firm's own (seeded on first read); the write-off and adjustment dialogs offer exactly the firm's active reasons and post to the reason's account. Without INVENTORY_MANAGE_REASONS the screen is read-only. A reason's account must be an expense or income account: Inventory, Cash, a party or Sales is refused by name (D-STK-31). Any seeded reason, Damage included, can be switched off, after which a write-off naming it is refused.
### TC-STOCK-011 — Repacking and bulk breaking

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a second product (the repacked pack) with a purchase price.
- **Steps:** as the prepared **Firm admin**: Stock > All Stock screens > Movements > **Repacking** → New: consume 10 of the bulk product, produce 40 of the small pack, wastage 1 percent. Post. Read the ledger and journals. Post another with no wastage. **Cancel** one.
- **Expect:** every consume line leaves stock at the product's moving average; the value consumed less the wastage share is spread over the produce lines in proportion to what each is worth at its purchase price (by quantity where none has a price) and the pack arrives **at that cost**; wastage is written off to inventory adjustment. With no wastage the books do not move. Cancelling reverses every movement and the wastage journal.
### TC-STOCK-012 — A kit is assembled, sold as itself, and dispatched by assembling

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a product `QA-KIT` of type **Bundle**; DET (100 in MAIN) and a second product as components.
- **Steps:** as the prepared **Firm admin**: Masters > Products → the kit → **Components**: DET × 2 and the other × 1 → Save. Then **Assemble** 5 kits; check stock of components and of the kit and the kit's cost. **Disassemble** 1. Raise an order for 8 kits, approve, create the delivery note and **Dispatch**. Try a kit inside the kit.
- **Expect:** Assemble is a repack: components leave at their average and the kit arrives carrying their cost (10 DET and 5 of the other for 5 kits). Disassemble returns components. The kit is stocked and sold as itself — reservation, cost of goods sold, invoice cost and returns work as for any product. Dispatching 8 with only 4 assembled **assembles the shortfall from the components inside the dispatch's own transaction**; the dispatch gate counts the line's own reservation (D-STK-16). A kit inside a kit is not supported. Assemble and Disassemble need INVENTORY_ADJUST.
### TC-STOCK-013 — Expiry rules, shelf life and the issue rule on the product

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** `QA-AMX` in three batches as in TC-STOCK-005; a goods receipt line to type.
- **Steps:** as the prepared **Firm admin**: Masters > Products → `QA-AMX` → **Stop selling N days before expiry** 20, **alert** 45, **return to supplier** 60; **Shelf life (days)** 365; **Batch issue rule** *FIFO*. Dispatch an order, then set *FEFO*, *PICK* and dispatch again. Receive a new batch giving only a manufacturing date; then one giving an expiry too. Stock > **Expiry Monitor** → *Return to supplier now*. Set the same three counts on the category and clear them on the product.
- **Expect:** a batch within the stop-sale days of expiry is passed over by the earliest-expiry pick while another batch can cover the line, and refused at dispatch where it is the only one (and in a delivery note's chosen-batch check); the picker uses the product's alert window; the monitor lists batches inside the return window (a product with no rule is never listed). A receipt line with a manufacturing date and no expiry is stored with expiry = manufacturing date + 365; a typed expiry stands; nothing is filled where the profile does not enable expiry tracking, and the batch keeps its manufacturing date and shelf life. FIFO ranks batches by when they were received; FEFO by expiry (the default); **PICK** keeps expiry order for holds but dispatch refuses by name until the line names its batches. Product, then category, then firm: the nearest set rule wins.
### TC-STOCK-014 — Count plans, ABC classes and blind sheets

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps:** as the prepared **Firm admin**: Stock > **Physical Count** → *Count plans* → New: warehouse MAIN, ABC class **A**, every 30 days, **Blind**. Draw the **sheet**. Open it: count a few lines, post. Look at the plan's next-due date. Try a posted variance above the limit if one is set.
- **Expect:** ABC class is worked out from the last year's dispatch value (the products making the first 80% are A, the next 15% B, the rest C; the list names only products that were dispatched, and one it does not name is C). The sheet counts exactly what the plan covers; a **blind** sheet hides the system quantity until it is posted. The plan's next count falls due its interval after the last sheet it drew was posted. The adjustment limits (TC-STOCK-016) apply on posting.
### TC-STOCK-015 — Evidence attached to adjustments and counts

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a photo or PDF file; the ATTACHMENTS feature enabled for the firm's profile.
- **Steps:** as the prepared **Firm admin**: Stock > All Stock screens > Stock > Inventory → **Adjust** (and then **Write off** and **Transfer**), pick a file in the dialog and save. Open the movement in Stock > All Stock screens > Stock > **Transactions** → **Evidence**. On a posted count sheet add another file. Delete one file.
- **Expect:** files named in the dialog are saved in the same transaction as the movement; a transfer's files sit on its outbound leg and are readable from either leg. The Evidence viewer lists name, type and caption for a movement or a count sheet; a posted sheet still takes files. Delete is soft and audited. Without the ATTACHMENTS feature the picker is not offered.
### TC-STOCK-016 — Large adjustments need approval

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a user with INVENTORY_ADJUST but a low limit (a Warehouse job), and the administrator with INVENTORY_MANAGE_SETTINGS.
- **Steps:** as the **Firm admin**: Settings > Stock > **Adjustment Limits** → Warehouse role limit **500** → Save. As the **Warehouse** user: write off stock worth 2,000 at cost. Press **Submit for approval**. As the administrator: Stock > All Stock screens > Movements > **Adjustment Approvals** → Approve; submit and **Reject** another with a reason; bulk-approve two.
- **Expect:** an adjustment or write-off worth more than the role's limit (quantity at the product's average cost) is refused when posted directly, naming the limit, and offers *Submit for approval*. A person whose own limit covers it approves the request and it posts unchanged through the same service; a rejection keeps its reason. A firm with no limits behaves as before.
- **Also (in packs, over HTTP):** the limit judges the pieces a pack moves. With a box of 12 at 60 a piece and a limit of 500, a write-off or an adjustment of **3 boxes** (`entered_uom_id` the box) is refused naming 2,160; a request for it says 2,160 and 36 pieces, the requester cannot approve it, and the administrator's approval takes 36 pieces off (D-STK-57; `docs/qa/checks/inventory/p_limit_in_packs.py`, round 9). The two forms on screen type pieces.
### TC-STOCK-017 — Incoming and outgoing on availability

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a sales order for the product approved for 6 and partly delivered.
- **Steps:** as the prepared **Firm admin**: Stock > **Stock Summary** → the *Product stock* table and *Warehouse stock*. Receive part of the purchase order and look again. Open the order editor's side panel under Stock.
- **Expect:** **Incoming** is approved purchase orders less completed receipts (stock units); **Outgoing** is the approved or partly delivered sales order lines less what has left less what is still reserved; **Projected** = available + incoming - outgoing. A product with no stock row but open orders is listed in the product table. The order editor shows incoming and outgoing for the warehouse it ships from. Reorder planning uses the same incoming figure.
### TC-STOCK-018 — Reservations lapse, and returned goods are held until checked

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Also needs:** the sales order of 12 approved and reserved; a delivered and invoiced sale to return.
- **Steps:** as the prepared **Firm admin**: Settings > Selling > **Sales Stages** → *Reservation lapses after* 7 days → Save; back-date the order's approval (or wait) and let the server's timer run; open the order. Press **Reserve again**. Then Settings > Stock > **Batch Rules** → *Hold returned goods for checking* on. Complete a sales return with some good, some damaged. Open Inventory. Select the quarantined row → **Release**. Cancel a second return.
- **Expect:** the order is flagged *Reservation lapsed* (not cancelled), its stock goes back to free, and it can still be dispatched from free stock; **Reserve again** holds it once more. Off by default. With the batch rule on, completing the return puts the **sellable** part in quarantine (still owned and valued), the damaged and scrapped parts as before; *Release* puts the checked goods on the shelf; cancelling the return takes it back out of quarantine.
### TC-STOCK-019 — Stock alerts on Home and turnover in the ageing

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** one product below reorder level, one out of stock, one over its maximum.
- **Steps:** as the prepared **Firm admin**: open Home and read the to-do. Reports > Operational → Stock ageing.
- **Expect:** Home lists stock lines to attend to, each counted with the worst rows: at or below reorder level, out of stock, over the maximum, batches near expiry, goods in transit, open count sheets. Where a kind has more than ten, the ten listed are the worst first: the largest shortfall, the largest excess, the nearest expiry; a product that is counted and not listed is less short than every one that is. The ageing report carries *issued last year* and *turnover* columns. Nothing is stored; the figures change as the stock does.
### TC-STOCK-020 — Barcode labels, and the product's selling status

*Added 2026-10-03 from the code and the build notes. Driven over HTTP on 2026-10-08 (inventory round 1, `docs/qa/checks/inventory/`); the screens were clicked separately.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a printer or the PDF preview; a goods receipt that stocked pieces.
- **Steps:** as the prepared **Firm admin**: Masters > Products → tick two products → **Print labels**: sheet 65-up, then 24-up, then the 50 × 25 mm roll; copies 2; used positions 1-3; price switch. On a goods receipt selection press **Print labels**. Try a cancelled receipt. Then set `QA-DET` to **Discontinued**; raise a quotation and an order; raise a purchase order. Reorder report. Set **Not for sale** on another product and try a quotation, an order and a purchase order.
- **Expect:** labels are Code 128 with name, barcode, MRP, our price, batch and expiry (the product code stands in for a missing barcode; an unencodable value is refused by product name); `skip` leaves used positions blank; the receipt's labels use the delivery's MRP and price, one per piece stocked, and a cancelled receipt is refused. A **Discontinued** product still sells but is refused on a purchase order by name and is not suggested by reorder planning (only active products are). **Not for sale** refuses the product on every new sales line whatever its status but it can still be bought.
### TC-STOCK-021 — Serial numbers follow a transfer, and opening stock types its units

*Added 2026-10-08 with the build (D-STK-40). Driven over HTTP by `docs/qa/checks/inventory/d_stk_19.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a second warehouse; a product whose goods type keeps serial numbers (Electronics), with no stock.
- **Steps:** as the prepared **Firm admin**: Inventory > Opening stock → new document for MAIN, the serial product, quantity 6, cost 10; type two numbers in **Serial numbers** and save; press **Post**. Reopen the draft, type all six, save, post. Inventory > Stock → **Transfer** 2 of the product to the second warehouse: save with no units picked, then with one, then with two. Inventory > Stock transfers → new transfer of the other 4, picking one unit; **Dispatch**; edit the draft and pick all four; dispatch; **Receive** with received 3, damaged 1, without ticking units, then ticking one as not arrived and one as damaged. Batches & serials > Serial numbers: read the six. Raise a delivery note from the second warehouse for two of the units that arrived, and try the damaged one. Start another transfer, dispatch it, **Cancel** it.
- **Expect:** the first post is refused asking for 4 more serial numbers; the second posts and the six units are **AVAILABLE** in MAIN, each trail starting on the opening stock document. The one-step transfer is refused until one unit is picked per unit moved, then the two units read the second warehouse. The transfer document saves with fewer units picked than it sends and is refused at dispatch until all four are picked; dispatched, its units read **IN_TRANSIT** and can be picked nowhere else. The receipt is refused until it says which unit did not arrive and which is damaged; then two units are AVAILABLE and one **DAMAGED** in the second warehouse and one is **LOST**. The delivery note for the two good units dispatches from the second warehouse; the damaged unit is refused. A cancelled transfer's units are AVAILABLE at the source again. An opening stock line of a serial product with no numbers at all still posts as a quantity.
### TC-STOCK-022 — An order owed more than is held ships what is on the shelf

*Added 2026-10-08 with the fix (D-STK-39). Driven over HTTP by `docs/qa/checks/inventory/p_backorder_ships.py` and `p_overreserve.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** two products with no batches, **4** of each in MAIN and nothing else held or ordered.
- **Steps:** as the prepared **Firm admin**: (a) raise and approve a sales order for **10** of the first product; raise a delivery note for **4** of it, approve and dispatch. (b) for the second product raise and approve an order for **3**, then another for **4**; raise and approve a note for each in full; dispatch the note of the **later** order, then the note of the **earlier** one, then the later one again. Open Inventory > Stock for both products.
- **Expect:** (a) the four ship; the stock row reads On hand 0, Reserved 6 -- the six still owed. (b) the later order's note is refused (*Insufficient available stock for dispatch line.*) both times; the earlier order's note ships its three, leaving On hand 1 and Reserved 4. Available reads below zero while an order is owed more than is held.
### TC-STOCK-023 — A kit takes a batch-tracked part earliest expiry first; serial-tracked goods are not repacked

*Added 2026-10-08 with the fix (D-STK-51, D-STK-52). Driven over HTTP by `docs/qa/checks/inventory/p_kit_tracked_parts.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the Medicine and Electronics goods types in use; a Medicine product **MED** received into MAIN as batch **KA** (4, expiring in 100 days) and batch **KB** (16, expiring in 300 days); an Electronics product **ELE** received with three serial numbers; a kit **KIT** (product type Bundle) with nothing assembled.
- **Steps:** as the prepared **Firm admin**: (a) on KIT set the components to **5 of MED** and assemble **1** in MAIN; open Inventory > Stock for MED. (b) assemble **4** more. (c) raise and approve a sales order for **3** of KIT, raise, approve and dispatch a delivery note for the three. (d) on Repacking, post a repack that consumes **1 of ELE** and produces 1 of any plain product; then one that consumes the plain product and produces **1 of ELE**. (e) on a second kit, set the components to **1 of ELE**.
- **Expect:** (a) the kit is assembled: KA reads 0 and KB 15 -- the four expiring first went, then one of the later batch; the repack shows one consumed line per batch. (b) refused, naming MED: fifteen are held and twenty are needed; nothing moves. (c) the note is dispatched, assembling the two kits it lacks: KB reads 5 and no kit is left. (d) both repacks are refused: *ELE is tracked by serial number, and a repack moves a quantity without naming units ...*; ELE still reads 3 on hand with three units Available. (e) refused: *A part tracked by serial number cannot go into a kit ...*.
### TC-STOCK-024 — A stock movement is dated inside an open period, a changed draft transfer moves on, and a posted count adds up

*Added 2026-10-09 with inventory round 4 (D-STK-41, D-STK-42, D-STK-45). Driven over HTTP by `docs/qa/checks/inventory/p_dates.py`, `p_stale_version.py` and `p_count_adds_up.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** books opened for the current year only; a plain product with **50** in MAIN; a second warehouse.
- **Steps:** as the prepared **Firm admin**: (a) Inventory > Stock → **Transfer** 1 to the second warehouse dated **2030-01-01**; the same date on **Quarantine**, on a new **Stock transfer** document, on a new **Physical count** and on a new **Repack**. (b) save a draft stock transfer of 2; open it on two computers; on the first change the quantity to 3 and save; on the second save without reloading. (c) open a physical count for MAIN; before counting, write off **10** of the product; type **49** as counted and post; open the posted sheet.
- **Expect:** (a) each is refused in words (*No open accounting period covers 2030-01-01 ...*) and nothing moves; dated today each saves. A firm that has never opened books is not asked. (b) the second save is refused (*This record changed since you loaded it*): a change to the lines alone moves the draft on. (c) the posted line reads **Expected 40, Counted 49, Variance +9** and the warehouse holds 49: the difference is measured against the stock at posting, and the three columns agree. A line nobody counted keeps the figure it was drawn up with.
### TC-STOCK-025 — What a product does not track is not recorded, what it tracks is asked for, and a serial number needs a unit

*Added 2026-10-09 with inventory round 4 (D-STK-43, D-STK-48, D-STK-50). Driven over HTTP by `docs/qa/checks/inventory/p_tracking.py`, `p_batch_dates.py` and `p_serial_past_stock.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the Medicine and Electronics goods types in use; a plain product **PLAIN**, a Medicine product **MED** (batch and expiry) and an Electronics product **ELE** (serial numbers), none with stock.
- **Steps:** as the prepared **Firm admin**: (a) receive 5 of PLAIN on a goods receipt, typing batch number **X1** on the line; open Stock > Batches and Inventory > Stock. (b) receive 5 of MED as batch **M1** with no expiry date; then with one. On Stock > Batches add batch **M2** for MED with no expiry date. (c) Stock > Serial Numbers → **Add Serial** for ELE. Post opening stock of **2** of ELE with no numbers typed; add two serial numbers, then a third. Mark the first **Scrapped**; add another; set the scrapped one back to Available.
- **Expect:** (a) the receipt completes; no batch X1 is registered and the five stand on the product's own row; the text stays on the receipt line as typed. (b) refused (*... tracks expiry, so batch M1 needs an expiry date ...*) on the receipt and on the batch master alike; with the date both save. A manufacturing date fills the expiry where the product has a shelf life. (c) with nothing held the number is refused (*The firm holds 0 of ... Receive the goods first ...*). Two are added against the two held; the third is refused (*This warehouse holds 2 of ... and 2 are already numbered*). A scrapped number is not counted, so one more is added; the scrapped number is then refused its way back.
### TC-STOCK-026 — Goods a customer returned damaged or as scrap are held as damaged, and a write-off takes them first

*Added 2026-10-09 with inventory round 4 (D-STK-46). Covered by `backend/tests/unit/test_inventory_round_4.py`; driven over HTTP by `docs/qa/checks/inventory/p_scrap_return.py` and, for a batch-tracked product, `p_scrap_return_batch.py` (round 5).*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a dispatched and invoiced sale of **10** of a plain product.
- **Steps:** as the prepared **Firm admin**: raise, approve and complete a sales return of **5**: 2 good, 1 damaged, 2 scrap. Open Inventory > Stock for the product. **Write off** 3. Cancel a second return that brought scrap in.
- **Expect:** the stock row reads **Damaged 3** (the damaged unit and the two scrapped) beside the good units held for checking; nothing returned stands outside a figure on the screen. The write-off of 3 takes the damaged figure to 0 before it touches quarantine or the shelf, and the stock value falls by their cost. A cancelled return takes its damaged and scrap units out again. Goods written off as *given to a customer* never come out of the damaged figure.
### TC-STOCK-027 — What a repack or a broken kit produces of a batch-tracked product goes into a named batch

*Added 2026-10-09 with inventory round 4 (D-STK-53). Driven over HTTP by `docs/qa/checks/inventory/p_repack_batchless.py` and `p_kit_break_batch.py`; on screen SC-ST-090 to 092.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the Medicine goods type in use; a Medicine product **MED** with batch **KA** in MAIN; a plain product with stock; a kit whose part is 5 of MED, one assembled in MAIN, and one more kit brought in as opening stock in a second warehouse.
- **Steps:** as the prepared **Firm admin**: (a) Repacking → **New repack**: consume 1 of the plain product, produce 1 of MED; read the produce line; **Post repack** with the Batch number empty. (b) type a new batch number and no expiry date; post. (c) type **KA**; post. (d) **Disassemble** the kit assembled in MAIN. (e) disassemble the kit in the second warehouse; then again naming the batch.
- **Expect:** (a) the produce line of MED shows **Batch number** and **Expiry date**; a line of the plain product shows neither; refused: *MED is kept in batches. Enter the batch the produced goods go into.* (b) refused: *... tracks expiry, so batch ... needs an expiry date ...*. (c) posted; KA holds one more and no stock of MED stands on a row with no batch. (d) the five parts go back into the batch the kit's last assembly drew from. (e) refused, naming the part (*Name the batch it goes back into*), nothing moves; with the batch named it breaks.
### TC-STOCK-028 — A delivery note line that names no bin takes the goods from the bins

*Added 2026-10-09 with inventory round 4 (D-STK-54). Driven over HTTP by `docs/qa/checks/inventory/p_bins.py` and `p_bin_batch_split.py`.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a warehouse with bin **B1**; a plain product with **4** in B1 and none on the warehouse's own row; a Medicine product with **3** of an early-expiring batch in B1 and **5** of a later batch on the warehouse's own row.
- **Steps:** as the prepared **Firm admin**: (a) raise and approve an order for 4 of the plain product; raise, approve and dispatch a delivery note for the four, naming no bin. (b) raise a note for 5 of it. (c) order 8 of the Medicine product; dispatch a note for 6, naming no bin and no batch. Open Inventory > Stock and the Stock Ledger.
- **Expect:** (a) dispatched: the four leave B1, and the movement names the bin. (b) refused, saying what stands free in each bin (*... in bin B1*). (c) the early batch leaves whole from the bin and three of the later batch from the warehouse's own row: two movements, no row below zero, and the two still owed stay reserved. A unit with a serial number is not drawn this way: it leaves from the bin named on the line.
### TC-STOCK-029 — Near expiry means the same batches on Home and on the batch card

*Added 2026-10-09 with inventory round 4 (D-STK-47). Covered by `backend/tests/unit/test_near_expiry_is_one_definition.py`; driven over HTTP by `docs/qa/checks/inventory/p_alert_windows.py` (round 5).*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a Medicine product with one batch expiring in **20** days on the shelf, one expiring in 20 days held in quarantine, and one expiring in **45** days; *Batch sale rules* at the default 30 days.
- **Steps:** as the prepared **Firm admin**: read the *near expiry* count on Home's stock alerts and on the Stock > Batches card. Set the firm's window to **60** days under *Batch sale rules*; read both again; read the Expiry Monitor's *7 days* and *30 days* cards.
- **Expect:** Home and the batch card count the **same two** batches at 30 days (a batch held in quarantine holds stock) and the same three at 60. The Expiry Monitor's two cards are named for their windows and do not move with the firm's setting.

### TC-STOCK-030 — A kit is made and broken on screen where a batch has to be named

*Added 2026-10-09 with inventory round 5 (D-UI-85). On screen SC-ST-094 to 097; the server's half is `docs/qa/checks/inventory/p_kit_break_batch.py` and `p_kit_tracked_parts.py`.*

- **Covers:** D-UI-85, D-STK-51, D-STK-53
- **Also needs:** the Medicine goods type in use; a Medicine product **MED** with batch **KA** holding stock in MAIN; a kit whose part is 1 of MED, **two** of it brought in as opening stock in MAIN and none assembled there.
- **Steps:** as the prepared **Firm admin**: Masters > Products, pick the kit. (a) **Disassemble kits**: MAIN, 1 kit, leave **Batch for MED** empty; Disassemble. (b) type **KA** in the box; Disassemble. (c) **Assemble kits**: MAIN, 1 kit; Assemble. (d) **Disassemble kits** again: MAIN, 1 kit, the box empty; Disassemble.
- **Expect:** (a) the dialog shows **Batch for MED** and is refused inside it: *MED is kept in batches, and no assembly of the kit in this warehouse says which batch it came from. Name the batch it goes back into.*; nothing moves. (b) the kit is broken and KA holds one more. (c) the Assemble dialog has no batch box for a kit that is not itself kept in batches; one kit more, one of MED less, taken from its batches earliest expiry first. (d) broken with the box empty: the part goes back into the batch the assembly took it from. A kit that is itself kept in batches shows **Batch number** and **Expiry date** on Assemble.

### TC-STOCK-031 — A kit that is itself kept in batches

*Added 2026-10-09 with inventory round 6. On screen SC-ST-098; over HTTP `docs/qa/checks/inventory/p_kit_batch_tracked_kit.py`.*

- **Covers:** D-UI-85, D-STK-53
- **Also needs:** the Medicine goods type in use; a plain product **PART** holding 10 in MAIN; a kit **under a Medicine category** (so it is kept in batches and dated) whose part is 2 of PART.
- **Steps:** as the prepared **Firm admin**: Masters > Products, pick the kit. (a) **Assemble kits**: MAIN, 1 kit, **Batch number** empty; Assemble. (b) Batch number **KX**, Expiry date 200 days on, 2 kits; Assemble. (c) Batch number **KY**, Expiry date 90 days on, 1 kit; Assemble. (d) Batch number **KX** again with an expiry date 5 days on, 1 kit; Assemble. (e) **Disassemble kits**: MAIN, 2 kits; Disassemble. (f) Disassemble 3 more.
- **Expect:** (a) the dialog shows **Batch number** and **Expiry date** and is refused inside it: *... is kept in batches. Name the batch the repacked goods go into: one it already has, or a new number with its dates.*; nothing moves. (b) and (c) the kits stand in KX (2) and KY (1) and PART holds 4. (d) accepted: the kit joins KX, and KX keeps the expiry date it was made with -- a date typed beside a batch that already exists is not taken, as on a goods receipt. (e) the kits leave soonest expiry first: KY is emptied, KX holds 2, PART holds 6. (f) refused naming the kit, with 2 held; nothing moves.
- **Also:** the component list of a kit (`GET /products/{id}/components`) says of each part whether it is kept in batches as the part is **now**: switch a part's batch tracking on, while it holds nothing, and the list follows without the kit being saved again. Moving a product to a category of another goods type changes its type and leaves its switches as they were.
- **Also (a note never assembles it):** with 2 of the kit in KX and parts on the shelf, a delivery note for **3** is refused at dispatch (*Insufficient available stock for dispatch line.*) and no part is taken; assemble 1 more into KX and the same note ships. A kit **not** kept in batches has what it lacks assembled behind the note. Over HTTP `docs/qa/checks/inventory/p_kit_batch_kit_dispatch.py` (round 7).

### TC-STOCK-032 — An opening-stock import refused at posting writes nothing

*Added 2026-10-09 with inventory round 8 (D-STK-56). Driven over HTTP by `docs/qa/checks/inventory/p_opening_import_json.py`.*

- **Covers:** D-STK-56
- **Also needs:** two plain products **P1** and **P2** holding nothing in MAIN, with no opening stock posted for either.
- **Steps:** **(HTTP)** as the prepared **Firm admin** (no screen offers this route; Opening Stock's **Import from file** is another route, over HTTP in `p_opening_import.py`): `POST /api/v1/inventory/opening-stock/import` as a form with `format=json` and a `payload` of one line. (1) Reference **OS-A**, 10 of P1. (2) Reference **OS-B**, 10 of P1 again. (3) Reference **OS-B**, 4 of P2. (4) Reference **OS-C**, 1 of P2 with `auto_post` false.
- **Expect:** (1) **201**, the document is POSTED and MAIN holds 10 of P1. (2) **422**, "Line 1 already has posted opening stock in this warehouse (OS-A). Opening stock is posted once per item; correct it with a stock adjustment."; the Opening Stock list shows **no** document OS-B and P1 still holds 10. (3) **201**, POSTED under OS-B: the refused import did not use the number up; MAIN holds 4 of P2. (4) **201**, a DRAFT that stocks nothing.

### TC-STOCK-033 — An opening-stock CSV with an unreadable cell is refused by line

*Added 2026-10-09 with inventory round 9 (D-STK-58). Driven over HTTP by `docs/qa/checks/inventory/p_opening_import_csv.py`.*

- **Covers:** D-STK-58
- **Also needs:** two plain products **P1** and **P2** holding nothing in MAIN, with no opening stock posted for either.
- **Steps:** **(HTTP)** as the prepared **Firm admin** (no screen offers this route): `POST /api/v1/inventory/opening-stock/import` as a form with `format=csv`, a reference number, today's posting date, the branch and MAIN, and a file headed `ProductId,Quantity`. (1) One row, 10 of P1. (2) Two rows of P2, the second with a product id of **not-an-id**. (3) The second row's quantity **lots**. (4) One row, quantity **-4**. (5) A column `ReorderLevel` holding **few**. (6) The heading alone. (7) A file that is not text; and `format=xlsx` with a file that is not a workbook. (8) The file of (2) corrected, under (2)'s number.
- **Expect:** (1) **201**, POSTED, MAIN holds 10 of P1. (2) to (5) **422** naming the line and the field (`lines[2].product_id`, `lines[2].quantity`, `lines[1].quantity`, `lines[1].reorder_level`); (6) **422**, "The file has no row with a ProductId and a Quantity, so nothing was imported."; (7) **422** each, saying the file is not UTF-8 text, or could not be opened as an XLSX workbook. After each refusal the Opening Stock list shows **no** document under that number and P2 holds nothing. (8) **201**, POSTED: the refused number was not used up.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 07-S01 | **Stock > All Stock screens > Stock > Inventory** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S02 | **Stock > All Stock screens > Stock > Transactions** | Offered to any role holding `INVENTORY_TRANSACTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S03 | **Stock > Stock Ledger** | Offered to any role holding `INVENTORY_LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S04 | **Stock > All Stock screens > Movements > Opening Stock** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S05 | **Stock > Physical Count** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S06 | **Stock > Stock Summary** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S07 | **Stock > All Stock screens > Stock > Stock Search** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S08 | **Stock > All Stock screens > Data > Import** | Offered to any role holding `INVENTORY_IMPORT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S09 | **Stock > All Stock screens > Data > Export** | Offered to any role holding `INVENTORY_EXPORT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S10 | **Settings > Stock > Inventory Settings** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S11 | **Stock > All Stock screens > Movements > Adjustment Approvals** | Offered to any role holding `INVENTORY_ADJUST`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S12 | **Stock > All Stock screens > Movements > Repacking** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S13 | **Stock > Stock Transfers** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S14 | **Settings > Stock > Adjustment Reasons** | Offered to any role holding `INVENTORY_VIEW` or `INVENTORY_ADJUST` or `INVENTORY_MANAGE_REASONS`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S15 | **Stock > Batches** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S16 | **Stock > All Stock screens > Tracking > Lots** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S17 | **Stock > All Stock screens > Tracking > Serial Numbers** | Offered to any role holding `SERIAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S18 | **Stock > Expiry Monitor** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
