# Inventory, batches and serial numbers

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-10-03 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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
  1. As the prepared **Firm admin**, Inventory → Stock → **Inventory**, filter Product `QA-B` → Apply. Then **Stock Summary**.
  2. Inventory → Stock → **Stock Ledger**, filter Product `QA-B` → Apply; open one row's detail (eye icon). Then Transaction type `GOODS_RECEIPT` → Apply.
- **Expect**
  - Step 1: one row, MAIN, Current **10**, Available 10, Reserved 0; the summary's figure for the product agrees.
  - Step 2: two `GOODS_RECEIPT` rows, +4 and +6, each naming its GRN, with the balance after each; the last equals Current. The detail dialog is titled "Ledger details". Filtering by type leaves the two. *(Known: the type list offers values the server never writes and lacks some it does — BACKLOG §31.13.)*
### TC-STOCK-002 — Moving stock between warehouses posts no journal

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse. (50 of `QA-P` in MAIN; an empty warehouse `QA-W2` under HO.)
- **Steps**
  1. As the prepared **Firm admin**, Inventory → Stock → Inventory → select the `QA-P` / MAIN row → **Transfer**: quantity **3**, **Move it to** `QA-W2 - Overflow qa`, reference `QA-TRF` → **Transfer**.
  2. Refresh; Stock Ledger for the product; Finance → Journal Entries.
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
- **Steps:** as the prepared **Firm admin**, Inventory → Stock → **Physical Count** → **Open Count**: branch HO, warehouse MAIN, today → Open. On the sheet find `QA-P - Fixture Product qa` (code and name, never an id); type **49** in Counted (Expected is 50); leave every other line blank. **Save progress**, close, reopen from the list → **Post count** → confirm.
- **Expect:** "PC-… opened over N lines." (N is every product in MAIN — other runs' too). Difference reads `-1` while typing. The list reads "1 of N lines counted", then "N lines · posted". After posting: MAIN **49**; ledger `ADJUSTMENT` −1 referencing the count; Journal Entries shows the adjustment; the uncounted lines moved nothing. The posted sheet is read-only: "Posted. The differences are in the ledger."
### TC-STOCK-005 — Dispatch draws the earliest-expiring batch first

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (`QA-AMX` in three batches of 10: `-B1` **expired 30 days ago**, `-B2` expiring in 20 days, `-B3` in 400; an approved order for **5**.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Inventory → **Batch & Serial** → **Batches**, search `QA-B`.
  2. Delivery Notes → **New** → the prepared order for 5 → read "Expected to ship from — earliest expiry first, decided at dispatch" (in the phase 2 editor the side panel instead lists the batches, already filled earliest expiry first; see TC-SELL-019) → **Save** → **Approve** → **Dispatch**.
  3. Batches again; Stock Ledger for `QA-AMX`.
  4. Inventory → Batch & Serial → **Expiry Monitor**.
- **Expect**
  - Step 1: three batches, 10 available each, with their expiry dates.
  - Step 2–3: status DISPATCHED; ledger `DISPATCH` −5 referencing the note. **The 5 comes from `-B2`, the earliest batch that has *not* expired**; `-B1` is skipped. Fixed 2026-09-16; see defect **D-8-1**.
  - Step 4: the six cards — Expired Today, Expire in 7 Days, Expire in 30 Days, Total Expired, Quarantine, Recalled — with `-B1` counted as expired and `-B2` inside 30 days; then the **All Batches** grid (Batch #, Product, Status, Qty, Available, Expiry Date, Warehouse).
### TC-STOCK-006 — A delivery short of stock saves but will not dispatch

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (`QA-SHT` has **3** on hand and an approved order for **10**.)
- **Steps:** as the prepared **Firm admin**, Delivery Notes → **New** → the order for 10 → read the preview → Save → Approve → **Dispatch**.
- **Expect:** the preview ends "Short by … — there is not enough available stock to cover this line." Saving is allowed; **Dispatch is refused** with the server's sentence, "Insufficient available stock for dispatch line."; the note stays **APPROVED** and the ledger shows no DISPATCH.
### TC-STOCK-007 — A remembered filter from another firm is dropped

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it. (its platform admin can open both QA01 and the prepared firm.)
- **Steps:** sign in as the prepared **Platform admin**; switch into **QA01** → Inventory → Stock → Inventory → filter by any product → Apply. Switch into the prepared firm → the same tab.
- **Expect:** the tab renders; the remembered QA01 filter is dropped (the panel reads "Filters" with none active) and choosing the firm's own warehouse works. *(A remembered id from another firm used to take the section down with "This section failed to render".)*
### TC-STOCK-008 — Serial numbers carry their warranty

- **Preconditions:** A firm on the **Electronics** profile, with a serial-tracked product that carries a warranty. (`QA-MIX`, 5 on hand, serials `QA-MIX-0001` to `-0005`.)
- **Steps:** as the prepared **Firm admin**, Inventory → Batch & Serial → **Serial Numbers**; search `QA-MIX-`; open one row's detail; filter Status AVAILABLE.
- **Expect:** five rows, status AVAILABLE, Warranty End a year from today, warehouse MAIN. The detail is titled "Serial: QA-MIX-0001" with warranty start and end and the warehouse. The Status filter keeps all five.
### TC-STOCK-009 — A stock transfer as a document: dispatch, in transit, receive

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps:** as the prepared **Firm admin**: Stock → Movements → **Stock Transfers** → New from MAIN to the second warehouse, 20 of the product → Save. Open Stock → Stock → Stock Summary and Accounts → Journal Entries. **Dispatch**. Look at the two warehouses' stock and the valuation. Print the **challan**. **Receive** with 18 arrived, of which 3 damaged (the other 2 never arrived). Create a second transfer and **Cancel** it after dispatch; create a third and cancel it as a draft. Try to cancel the received one. Try to dispatch more than is free.
- **Expect:** the transfer is numbered **TO-…** with a timeline. Dispatch takes the quantity off MAIN at the moving average and puts it **in transit at the destination**, still owned at that figure: no journal is posted and the firm's valuation does not move; the destination's summary shows the goods on their way. The challan is a delivery challan without values. On receipt, each line says what arrived and what of it was damaged: 15 go on the shelf, **3 arrive blocked from sale** (as on a goods receipt), and the 2 that never arrived are written off to the inventory adjustment account at the average. Cancelling a dispatched transfer brings the goods back; a draft cancels freely; a received transfer is final. Dispatching more than is free is refused. The one-step Transfer on the Inventory tab still moves stock within a building. Batches travel as themselves; serial numbers are not carried yet.
### TC-STOCK-010 — Why stock is issued: internal use, staff, display, and the firm's own reasons

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a user holding INVENTORY_MANAGE_REASONS (the administrator).
- **Steps:** as the prepared **Firm admin**: Stock → Stock → Inventory → select the product → **Write off** 2 with reason *Internal use*; again with *Staff* and *Display*; and once with *Damage*. Accounts → Books → Ledgers: read the expense accounts. Settings (gear) → Stock → **Adjustment Reasons**: add a reason *Festival gift* with its own expense account; deactivate another. Write off 1 with the new reason. Post an adjustment with a reason code.
- **Expect:** the three new reasons post to their own expense accounts — *Stock Used in Business*, *Staff Welfare*, *Samples and Display* — and damage, expiry and loss stay on *Inventory Adjustment*. The reasons list is the firm's own (seeded on first read); the write-off and adjustment dialogs offer exactly the firm's active reasons and post to the reason's account. Without INVENTORY_MANAGE_REASONS the screen is read-only.
### TC-STOCK-011 — Repacking and bulk breaking

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a second product (the repacked pack) with a purchase price.
- **Steps:** as the prepared **Firm admin**: Stock → Movements → **Repacking** → New: consume 10 of the bulk product, produce 40 of the small pack, wastage 1. Post. Read the ledger and journals. Post another with no wastage. **Cancel** one.
- **Expect:** every consume line leaves stock at the product's moving average; the value consumed less the wastage share is spread over the produce lines in proportion to what each is worth at its purchase price (by quantity where none has a price) and the pack arrives **at that cost**; wastage is written off to inventory adjustment. With no wastage the books do not move. Cancelling reverses every movement and the wastage journal.
### TC-STOCK-012 — A kit is assembled, sold as itself, and dispatched by assembling

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a product `QA-KIT` of type **Bundle**; DET (100 in MAIN) and a second product as components.
- **Steps:** as the prepared **Firm admin**: Masters → Items → Products → the kit → **Components**: DET × 2 and the other × 1 → Save. Then **Assemble** 5 kits; check stock of components and of the kit and the kit's cost. **Disassemble** 1. Raise an order for 8 kits, approve, create the delivery note and **Dispatch**. Try a kit inside the kit.
- **Expect:** Assemble is a repack: components leave at their average and the kit arrives carrying their cost (10 DET and 5 of the other for 5 kits). Disassemble returns components. The kit is stocked and sold as itself — reservation, cost of goods sold, invoice cost and returns work as for any product. Dispatching 8 with only 4 assembled **assembles the shortfall from the components inside the dispatch's own transaction**; the dispatch gate counts the line's own reservation (D-STK-16). A kit inside a kit is not supported. Assemble and Disassemble need INVENTORY_ADJUST.
### TC-STOCK-013 — Expiry rules, shelf life and the issue rule on the product

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** `QA-AMX` in three batches as in TC-STOCK-005; a goods receipt line to type.
- **Steps:** as the prepared **Firm admin**: Masters → Items → Products → `QA-AMX` → **Stop selling N days before expiry** 20, **alert** 45, **return to supplier** 60; **Shelf life (days)** 365; **Batch issue rule** *FIFO*. Dispatch an order, then set *FEFO*, *PICK* and dispatch again. Receive a new batch giving only a manufacturing date; then one giving an expiry too. Stock → Tracking → **Expiry Monitor** → *Return to supplier now*. Set the same three counts on the category and clear them on the product.
- **Expect:** a batch within the stop-sale days of expiry is refused at dispatch (and in a delivery note's chosen-batch check); the picker uses the product's alert window; the monitor lists batches inside the return window (a product with no rule is never listed). A receipt line with a manufacturing date and no expiry is stored with expiry = manufacturing date + 365; a typed expiry stands; nothing is filled where the profile does not enable expiry tracking, and the batch keeps its manufacturing date and shelf life. FIFO ranks batches by when they were received; FEFO by expiry (the default); **PICK** keeps expiry order for holds but dispatch refuses by name until the line names its batches. Product, then category, then firm: the nearest set rule wins.
### TC-STOCK-014 — Count plans, ABC classes and blind sheets

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Steps:** as the prepared **Firm admin**: Stock → Movements → **Physical Count** → *Count plans* → New: warehouse MAIN, ABC class **A**, every 30 days, **Blind**. Draw the **sheet**. Open it: count a few lines, post. Look at the plan's next-due date. Try a posted variance above the limit if one is set.
- **Expect:** ABC class is worked out from the last year's dispatch value (the products making the first 80% are A, the next 15% B, the rest and anything not dispatched C). The sheet counts exactly what the plan covers; a **blind** sheet hides the system quantity until it is posted. The plan's next count falls due its interval after the last sheet it drew was posted. The adjustment limits (TC-STOCK-016) apply on posting.
### TC-STOCK-015 — Evidence attached to adjustments and counts

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a photo or PDF file; the ATTACHMENTS feature enabled for the firm's profile.
- **Steps:** as the prepared **Firm admin**: Stock → Stock → Inventory → **Adjust** (and then **Write off** and **Transfer**), pick a file in the dialog and save. Open the movement in Stock → Stock → **Transactions** → **Evidence**. On a posted count sheet add another file. Delete one file.
- **Expect:** files named in the dialog are saved in the same transaction as the movement; a transfer's files sit on its outbound leg and are readable from either leg. The Evidence viewer lists name, type and caption for a movement or a count sheet; a posted sheet still takes files. Delete is soft and audited. Without the ATTACHMENTS feature the picker is not offered.
### TC-STOCK-016 — Large adjustments need approval

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** a user with INVENTORY_ADJUST but a low limit (a Warehouse job), and the administrator with INVENTORY_MANAGE_SETTINGS.
- **Steps:** as the **Firm admin**: Settings (gear) → Stock → **Adjustment Limits** → Warehouse role limit **500** → Save. As the **Warehouse** user: write off stock worth 2,000 at cost. Press **Submit for approval**. As the administrator: Stock → Movements → **Adjustment Approvals** → Approve; submit and **Reject** another with a reason; bulk-approve two.
- **Expect:** an adjustment or write-off worth more than the role's limit (quantity at the product's average cost) is refused when posted directly, naming the limit, and offers *Submit for approval*. A person whose own limit covers it approves the request and it posts unchanged through the same service; a rejection keeps its reason. A firm with no limits behaves as before.
### TC-STOCK-017 — Incoming and outgoing on availability

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a sales order for the product approved for 6 and partly delivered.
- **Steps:** as the prepared **Firm admin**: Stock → Stock → **Stock Summary** → the *Product stock* table and *Warehouse stock*. Receive part of the purchase order and look again. Open the order editor's side panel under Stock.
- **Expect:** **Incoming** is approved purchase orders less completed receipts (stock units); **Outgoing** is the approved or partly delivered sales order lines less what has left less what is still reserved; **Projected** = available + incoming - outgoing. A product with no stock row but open orders is listed in the product table. The order editor shows incoming and outgoing for the warehouse it ships from. Reorder planning uses the same incoming figure.
### TC-STOCK-018 — Reservations lapse, and returned goods are held until checked

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Also needs:** the sales order of 12 approved and reserved; a delivered and invoiced sale to return.
- **Steps:** as the prepared **Firm admin**: Settings (gear) → Selling → **Sales Stages** → *Reservation lapses after* 7 days → Save; back-date the order's approval (or wait) and let the server's timer run; open the order. Press **Reserve again**. Then Settings (gear) → Stock → **Batch Rules** → *Hold returned goods for checking* on. Complete a sales return with some good, some damaged. Open Inventory. Select the quarantined row → **Release**. Cancel a second return.
- **Expect:** the order is flagged *Reservation lapsed* (not cancelled), its stock goes back to free, and it can still be dispatched from free stock; **Reserve again** holds it once more. Off by default. With the batch rule on, completing the return puts the **sellable** part in quarantine (still owned and valued), the damaged and scrapped parts as before; *Release* puts the checked goods on the shelf; cancelling the return takes it back out of quarantine.
### TC-STOCK-019 — Stock alerts on Home and turnover in the ageing

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, 50 of a product in MAIN, and an empty second warehouse.
- **Also needs:** one product below reorder level, one out of stock, one over its maximum.
- **Steps:** as the prepared **Firm admin**: open Home and read the to-do. Reports → Operational → Stock ageing.
- **Expect:** Home lists stock lines to attend to, each counted with the worst rows: at or below reorder level, out of stock, over the maximum, batches near expiry, goods in transit, open count sheets. The ageing report carries *issued last year* and *turnover* columns. Nothing is stored; the figures change as the stock does.
### TC-STOCK-020 — Barcode labels, and the product's selling status

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a printer or the PDF preview; a goods receipt that stocked pieces.
- **Steps:** as the prepared **Firm admin**: Masters → Items → Products → tick two products → **Print labels**: sheet 65-up, then 24-up, then the 50 × 25 mm roll; copies 2; used positions 1-3; price switch. On a goods receipt selection press **Print labels**. Try a cancelled receipt. Then set `QA-DET` to **Discontinued**; raise a quotation and an order; raise a purchase order. Reorder report. Set **Not for sale** on another product and try a quotation, an order and a purchase order.
- **Expect:** labels are Code 128 with name, barcode, MRP, our price, batch and expiry (the product code stands in for a missing barcode; an unencodable value is refused by product name); `skip` leaves used positions blank; the receipt's labels use the delivery's MRP and price, one per piece stocked, and a cancelled receipt is refused. A **Discontinued** product still sells but is refused on a purchase order by name and is not suggested by reorder planning (only active products are). **Not for sale** refuses the product on every new sales line whatever its status but it can still be bought.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 07-S01 | **Inventory → Inventory** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S02 | **Inventory → Transactions** | Offered to any role holding `INVENTORY_TRANSACTION_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S03 | **Inventory → Stock Ledger** | Offered to any role holding `INVENTORY_LEDGER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S04 | **Inventory → Opening Stock** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S05 | **Inventory → Physical Count** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S06 | **Inventory → Stock Summary** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S07 | **Inventory → Stock Search** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S08 | **Inventory → Import** | Offered to any role holding `INVENTORY_IMPORT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S09 | **Inventory → Export** | Offered to any role holding `INVENTORY_EXPORT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S10 | **Inventory → Settings** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S11 | **Inventory → Adjustment Approvals** | Offered to any role holding `INVENTORY_ADJUST`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S12 | **Inventory → Repacking** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S13 | **Inventory → Stock Transfers** | Offered to any role holding `INVENTORY_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S14 | **Inventory → Adjustment Reasons** | Offered to any role holding `INVENTORY_VIEW` or `INVENTORY_ADJUST` or `INVENTORY_MANAGE_REASONS`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S15 | **Inventory → Batches** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S16 | **Inventory → Lots** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S17 | **Inventory → Serial Numbers** | Offered to any role holding `SERIAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S18 | **Inventory → Expiry Monitor** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
