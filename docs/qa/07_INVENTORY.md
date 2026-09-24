# Inventory, batches and serial numbers

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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
  2. Delivery Notes → **New** → the prepared order for 5 → read "Expected to ship from — earliest expiry first, decided at dispatch" → **Save** → **Approve** → **Dispatch**.
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
| 07-S11 | **Inventory → Batches** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S12 | **Inventory → Lots** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S13 | **Inventory → Serial Numbers** | Offered to any role holding `SERIAL_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 07-S14 | **Inventory → Expiry Monitor** | Offered to any role holding `BATCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
