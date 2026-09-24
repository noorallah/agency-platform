# Masters: customers, vendors, products, branches and warehouses

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Customers

A customer carries more than any one screen shows — addresses and contacts
that are replaced as a whole, a credit limit, payment terms, a standing
discount, a segment. **An update that dumps its whole write model turns an
omission into an instruction**, and it shipped twice here; these cases check
that an edit changes what it names and nothing else.

### TC-CUST-001 — Changing one field leaves everything else alone

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100. (`QA-CM`, Master Check: one billing address, one contact, credit limit 50,000, 30 days, 7.5% standing discount, segment `QA-RET`, phone +919800000100.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Masters → Customers → open `QA-CM` → Edit.
  2. Change only the **phone** to `+919800000199` → Save → reopen.
- **Expect:** the phone is new; the address (12 Fixture Street, City qa), the contact (Fixture Contact), **credit limit 50,000**, **payment terms 30**, **standing discount 7.5%** and the segment are all **unchanged**, and the outstanding balance is unchanged (0.00). Check each one.
### TC-CUST-002 — The place picker loads each rung from the one above

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100. (QA01's store holds India and, under it, yours **State qa → District qa → City qa**.)
- **Steps**
  1. As the prepared **Firm admin**, Customers → New: code `QA-GEO`, name `Place Check qa`, type Business, currency INR. In the address: country **India**, then **State qa**, then **District qa**, then **City qa**; line 1 and PIN filled.
  2. Save; reopen.
- **Expect**
  - Step 1: each rung loads **immediately** after the one above is chosen — choosing the country fills the states at once, not after a second click. *(It shipped loading from the value the parent had not rebuilt yet.)*
  - Step 2: the place is still chosen, and the text fields agree with it: city `City qa`, state `State qa`, country `IN`. The ids are the truth; the text is derived from them.
### TC-CUST-003 — The credit policy: readable by whoever it warns, writable by one permission

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps**
  1. As the prepared **Firm admin**, Customers → toolbar **Settings**.
  2. Sign in as the prepared **Seller** (`SALES_EXECUTIVE`) → Customers → Settings.
  3. **(HTTP)** As the seller, `PUT /api/v1/customers/credit-settings` with `{"enforcement": "OFF", "warn_at_percent": "80", "block_at_percent": "100"}`.
- **Expect**
  - Step 1: **Credit policy** — "When a customer reaches their limit" **Warn**, warn at 80, block at 100 (QA01 has no policy row, so the default applies), editable.
  - Step 2: the dialog **opens read-only**, with "Changing the policy needs the manage customer settings permission." *(The plan said the action is not offered to a salesperson; it is offered on `CUSTOMER_VIEW` on purpose — someone the policy warns should see the rule behind the warning.)*
  - Step 3: **403**.
### TC-CUST-004 — A credit limit warns and does not block

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps**
  1. As the prepared **Firm admin**, edit `QA-CM`: credit limit `1` → Save.
  2. Sales Orders → New: customer `QA-CM`, one line `QA-P` quantity 2 at 100 → Create draft → **Approve**.
- **Expect:** a warning names the exposure — "Master Check qa would be at …% of a 1.00 credit limit, leaving … available." — and the order **is approved**. QA01 is in warn mode (no policy row), so nothing blocks.
### TC-CUST-005 — Statement and ageing agree with the account

- **Preconditions:** As *invoiced*, with the invoice of 590.00 and a receipt of 200.00 applied to it. (Fixture Buyer qa owes 590 on one invoice and has paid 200 against it.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Customers → `QA-C` → **Statement** for this financial year.
  2. **Ageing**.
- **Expect**
  - Step 1: opening 0.00; the invoice (debit 590, balance 590), then the receipt (credit 200, balance **390**); closing **390.00** — the customer's current balance. Lines are in date order and the running balance is recomputed, not read off the stored snapshot.
  - Step 2: total outstanding **390.00**, all of it in the 0–29 day bucket; the buckets sum to the total, and the reconciliation line has nothing to explain (no unapplied credits, no charges not billed).
### TC-CUST-006 — Segments: assigning one, and refusing to delete one in use

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps**
  1. As the prepared **Firm admin**, edit `QA-CM` → segment `QA-WHL` (Wholesaler qa) → Save → reopen.
  2. Customers toolbar → **Groups** → **Remove** on `QA-WHL`.
- **Expect**
  - Step 1: the segment holds.
  - Step 2: refused — "1 customer(s) are still in Wholesaler qa. Move them first, or the group would vanish from every list while staying on their records." `ondelete="RESTRICT"` is no guard on a soft-deleted table, so the service refuses.
---

## Vendors, products, branches and warehouses

The same rule as customers: an edit changes what it names. Vendors had six
child collections emptied by any edit that did not send them; a branch rename
cleared its street lines, city, default flag and GST registration, and a
warehouse rename its capability flags.

### TC-MAST-001 — A vendor edit keeps all six child collections

- **Preconditions:** A firm administrator of QA01, and a vendor `QA-V` *Supply Check* with one contact, address, bank account, tax record, attachment and note; a vendor category `QA-CAT` and type `QA-TYP`. (`QA-V`, Supply Check: one contact, address, bank account, tax record, attachment and note.)
- **Steps:** as the prepared **Firm admin**, Masters → Vendors → Edit `QA-V` → change only the phone → Save → reopen.
- **Expect:** the contact, address, bank account, tax record, attachment and note are **all still there**.
### TC-MAST-002 — Vendor categories and types

- **Preconditions:** A firm administrator of QA01, and a vendor `QA-V` *Supply Check* with one contact, address, bank account, tax record, attachment and note; a vendor category `QA-CAT` and type `QA-TYP`.
- **Steps**
  1. As the prepared **Firm admin**, Masters → **Vendor Categories**; then **Vendor Types**. Add one to each: `QA-CAT2` / `QA-TYP2`.
  2. Edit `QA-V`: category `QA-CAT`, type `QA-TYP` → Save → reopen.
- **Expect**
  - Step 1: both lists load — the prepared `QA-CAT` and `QA-TYP` are in them — and both accept a new row. *(These returned nothing until the route order was fixed, and until 2026-09-11 the sidebar opened a "coming soon" placeholder — BACKLOG §26.)*
  - Step 2: both held, and the six child collections are still there.
### TC-MAST-003 — A product's slots

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode. (`QA-PM`, Slot Check.)
- **Steps:** as the prepared **Firm admin**, Masters → Products → open `QA-PM`.
- **Expect:** category **Shelf qa**; tax profile group **GST_18_LOCAL**; base, inventory and sales units **PIECE**, purchase unit **BOX** — each read as a name, not an id.
### TC-MAST-004 — A rename keeps a branch's address, city, GST registration and default flag

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (in **QA02**: `QA-BR`, Keep Branch, default, GST registered, 1 Keep Street / Keep Nagar, City qa.)
- **Steps:** sign in as the prepared **QA02 admin** → Masters → Branches → Edit `QA-BR` → rename to `Kept Branch renamed` → Save → reopen.
- **Expect:** both street lines, the city (and its state), **GST registration**, the PAN and **Default** are all unchanged.
### TC-MAST-005 — A rename keeps a warehouse's capacity and capability flags

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (`QA-WH`, Keep Warehouse, 1000 SQFT, default; on: temperature controlled, cold storage, receiving area, dispatch area, inspection area, loading dock; off: hazardous, returns area, packing area.)
- **Steps:** as the prepared **QA02 admin**, Masters → Warehouses → Edit `QA-WH` → rename → Save → reopen.
- **Expect:** capacity 1000 SQFT, Default, and **every flag exactly as listed** — the six on still on, the three off still off. *(Until 2026-09-11 a warehouse with no capacity could not be saved at all — BACKLOG §28.)*
### TC-MAST-006 — An import with one bad row imports nothing

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (prints the paths of two files, **Import, clash** (five rows; the fifth reuses `QA-BR`) and **Import, clean** (the first four).)
- **Steps**
  1. As the prepared **QA02 admin**, Masters → Branches → **Import** → the **clash** file.
  2. Select the refusal text with the mouse; press the copy icon beside it.
  3. Import the **clean** file.
- **Expect**
  - Step 1: **nothing** imported, and the dialog says so. The import stages and commits once.
  - Step 2: the message selects, and the copy icon puts the whole text on the clipboard.
  - Step 3: all four rows go in: `QA-I1` to `-I4`.
### TC-MAST-007 — Sample files and exports round-trip

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row).
- **Steps**
  1. As the prepared **QA02 admin**, Branches → Import → **Sample file**; save it. Open it, change the example code `BR_NORTH` to `QA-NORTH` (otherwise a second run meets the first run's branch), save; import it.
  2. Warehouses → Import → Sample file; look at its branch column.
  3. Branches → **Export**; Warehouses → Export. Then Export again and dismiss the save dialog.
- **Expect**
  - Step 1: eleven column headings and one example row; previews as "1 rows ready" and imports. Reopen it: display name, both address lines and the currency are filled (multi-word headings were silently dropped until 2026-09-11 — BACKLOG §31.4).
  - Step 2: the example names a branch **by code**, prefilled with this firm's first branch.
  - Step 3: a save dialog suggesting `branches.csv` / `warehouses.csv`; the notice names the full path; the file holds the grid's rows in the **same columns the importer reads**. Dismissing says no file was saved.
### TC-MAST-008 — A carton barcode finds its product

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode. (`QA-PM` has a **Case** level of 12 pieces with the barcode the preparation printed.)
- **Steps:** as the prepared **Firm admin**, Administration → Configuration → UOM & Packaging → **Packaging Levels** (or Ctrl+K and the screen's name) → product `QA-PM` → type the barcode into "Scan or type a code" → **Look up**.
- **Expect:** resolves to **Slot Check qa**, level **Case**, **12** base units. No scanner needed: a scanner only types the digits and presses Enter.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 05-S01 | **Masters → Customers** | Offered to any role holding `CUSTOMER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S02 | **Masters → Statements** | Offered to any role holding `CUSTOMER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S03 | **Masters → Products** | Offered to any role holding `PRODUCT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S04 | **Masters → Vendors** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S05 | **Masters → Vendor Categories** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S06 | **Masters → Vendor Types** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S07 | **Masters → Branches** | Offered to any role holding `BRANCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S08 | **Masters → Warehouses** | Offered to any role holding `WAREHOUSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S09 | **Masters → Storage Areas** | Offered to any role holding `STORAGE_AREA_MANAGE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S10 | **Masters → Warehouse Types** | Offered to any role holding `WAREHOUSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S11 | **Masters → Branch Types** | Offered to any role holding `BRANCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S12 | **Masters → Settings** | Offered to any role holding `BRANCH_VIEW` or `WAREHOUSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S13 | **Masters → Financial Years** | Offered to any role holding `FINANCIAL_YEAR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S14 | **Masters → Firm Settings** | Offered to any role holding `FIRM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
