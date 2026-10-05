# Masters: customers, vendors, products, branches and warehouses

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

## Customers

A customer carries more than any one screen shows — addresses and contacts
that are replaced as a whole, a credit limit, payment terms, a standing
discount, a segment. **An update that dumps its whole write model turns an
omission into an instruction**, and it shipped twice here; these cases check
that an edit changes what it names and nothing else.

### TC-CUST-001 — Changing one field leaves everything else alone

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100. (`QA-CM`, Master Check: one billing address, one contact, credit limit 50,000, 30 days, 7.5% standing discount, segment `QA-RET`, phone +919800000100.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Masters > Customers → open `QA-CM` → Edit.
  2. Change only the **phone** to `+919800000199` → Save → reopen.
- **Expect:** the phone is new; the address (12 Fixture Street, City qa), the contact (Fixture Contact), **credit limit 50,000**, **payment terms 30**, **standing discount 7.5%** and the segment are all **unchanged**, and the outstanding balance is unchanged (0.00). Check each one.
### TC-CUST-002 — The place picker loads each rung from the one above

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100. (QA01's store holds India and, under it, yours **State qa → District qa → City qa**.)
- **Steps**
  1. As the prepared **Firm admin**, Masters > Customers → New: code `QA-GEO`, name `Place Check qa`, type Business, currency INR. In the address: country **India**, then **State qa**, then **District qa**, then **City qa**; line 1 and PIN filled.
  2. Save; reopen.
- **Expect**
  - Step 1: each rung loads **immediately** after the one above is chosen — choosing the country fills the states at once, not after a second click. *(It shipped loading from the value the parent had not rebuilt yet.)*
  - Step 2: the place is still chosen, and the text fields agree with it: city `City qa`, state `State qa`, country `IN`. The ids are the truth; the text is derived from them.
### TC-CUST-003 — The credit policy: readable by whoever it warns, writable by one permission

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps**
  1. As the prepared **Firm admin**, Masters > Customers → toolbar **Settings**.
  2. Sign in as the prepared **Seller** (`SALES_EXECUTIVE`) → Masters > Customers → Settings.
  3. **(HTTP)** As the seller, `PUT /api/v1/customers/credit-settings` with `{"enforcement": "OFF", "warn_at_percent": "80", "block_at_percent": "100"}`.
- **Expect**
  - Step 1: **Credit policy** — "When a customer reaches their limit" **Warn**, warn at 80, block at 100 (QA01 has no policy row, so the default applies), editable.
  - Step 2: the dialog **opens read-only**, with "Changing the policy needs the manage customer settings permission." *(The plan said the action is not offered to a salesperson; it is offered on `CUSTOMER_VIEW` on purpose — someone the policy warns should see the rule behind the warning.)*
  - Step 3: **403**.
### TC-CUST-004 — A credit limit warns and does not block

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps**
  1. As the prepared **Firm admin**, edit `QA-CM`: credit limit `1` → Save.
  2. Sell > Sales Orders → New: customer `QA-CM`, one line `QA-P` quantity 2 at 100 → Create draft → **Approve**.
- **Expect:** a warning names the exposure — "Master Check qa would be at …% of a 1.00 credit limit, leaving … available." — and the order **is approved**. QA01 is in warn mode (no policy row), so nothing blocks.
### TC-CUST-005 — Statement and ageing agree with the account

- **Preconditions:** As *invoiced*, with the invoice of 590.00 and a receipt of 200.00 applied to it. (Fixture Buyer qa owes 590 on one invoice and has paid 200 against it.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Masters > Customers → `QA-C` → **Statement** for this financial year.
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
### TC-CUST-007 — A customer's money terms need the settings permission

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a **Sales Manager** and a **Firm Manager** user in the firm, beside the prepared Firm admin and Seller (Field Sales). The prepared customer `QA-CM` carries credit limit 50,000, payment terms 30 days and standing discount 7.5%.
- **Steps**
  1. As the prepared **Seller**: Masters > Customers → **New**. Look at **Credit limit**, **Default discount %**, **Opening balance**, **Payment terms (days)**, **Cash discount (days)** and **Cash discount %**. Type a code and a name only → Save.
  2. **(HTTP)** As the seller, `POST /api/v1/customers` five times, each with one of `credit_limit` 50000, `opening_balance` 1500, `payment_terms_days` 30, `cash_discount_percent` 2 with `cash_discount_days` 10, `default_discount_percent` 12.5. Then once with every one of them sent as 0.
  3. As the **Sales Manager**: Masters > Customers → `QA-CM` → **Edit**. Look at the same six boxes. Change only the name → Save.
  4. **(HTTP)** As the Sales Manager, `PUT /api/v1/customers/{id}` with the whole record and one figure changed: payment terms 30 to 45; then the credit limit; then the standing discount; then each set to 0.
  5. As the Sales Manager: Masters > Customers → **Import**, a file that names `QA-CM` with *update existing* chosen and a changed credit limit, credit days, opening balance or discount; then a file that changes only its name.
  6. As the **Firm Manager**, then the **Firm admin**: edit `QA-CM` and change payment terms to 45 → Save.
- **Expect**
  - Step 1: the six boxes are locked, with "Set by somebody with the manage customer settings permission." beneath; the customer saves with none of them.
  - Step 2: each of the five is refused with **403** and nothing is created: "<code>: giving a customer a credit limit needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS). Leave it at zero, or ask somebody who holds it.", and the same sentence for "an opening balance", "credit days", "cash-discount terms" and "a standing discount". Every term sent as zero is not a term: 201.
  - Step 3: the six boxes are locked on an edit too; the name saves and the terms are as they were.
  - Step 4: each is refused with **403**, "Changing a customer's credit days needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)." (and "…credit limit…", "…standing discount…"); setting one to zero is a change and is refused the same way. After every refusal the customer is unchanged.
  - Step 5: the import reports the problem on the row in the same words and updates nothing; the file that changes only the name updates the name. The batch import (`POST /api/v1/customers/import`) answers the same way.
  - Step 6: the Firm Manager's and the administrator's changes save.
### TC-CUST-008 — An opening balance typed on the customer is collected as a bill

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** nothing beyond the prepared Firm admin; the case makes its own customers.
- **Steps**
  1. As the prepared **Firm admin**: Masters > Customers → **New**: code `QA-OB1`, a name, **Opening balance** `1500`, **Payment terms (days)** `30` → Save. Open it again and read **Opening bills**. Accounts > Journal Entries.
  2. Sell > Receipts → **Record Receipt** → `QA-OB1`: read the bills offered. Sell > All Sell screens > Money > **Collection Sheet**. Masters > **Statements** → the customer's ageing and statement.
  3. Record Receipt: Amount `2000`, applied to the row → Save. Then Amount `600`, Cash, applied to the row → Save. Read the three lists and the customer again.
  4. Masters > Customers → `QA-OB1` → Opening bills → **Cancel** on the row, with a reason.
  5. In **Opening bills** press **Add opening bill**: any reference, 250 → Save.
  6. New customer `QA-OB2` with **Opening balance** `-300` → Save; read its Opening bills.
- **Expect**
  - Step 1: Outstanding **1,500.00**. Opening bills holds **one** row, 1,500.00, standing for the figure typed. One journal, reference `<code>-OB`: Dr 1100 Trade Receivables 1,500.00 / Cr 3000 Opening Balance Equity 1,500.00.
  - Step 2: Record Receipt lists one row **Opening balance**, 1,500.00, due the day it was entered plus 30 days; the collection sheet and the ageing list the same row, and the statement shows the opening balance once, not twice.
  - Step 3: 2,000 is refused: "Invoice Opening balance has 1500.00 outstanding, so 2000.00 cannot be allocated to it." The 600 is taken (Dr 1000 Cash 600.00 / Cr 1100 Trade Receivables 600.00) and the row reads **900.00** on Record Receipt, the collection sheet and the ageing, and the customer's Outstanding is 900.00. Paid in full, the row leaves all three.
  - Step 4: refused: "OBC-… is the opening balance entered on the customer, not a bill of its own. Set the customer's opening balance to 0 to take it back; reverse any receipt taken against it first."
  - Step 5: refused: "… carries an opening balance of 1500.00. Enter the opening balance either as one figure on the customer or bill by bill, not both…"
  - Step 6: a negative opening balance (money the firm owes the customer) makes no bill.
### TC-CUST-009 — Correcting an opening balance: after a reversed receipt, and after a cancelled invoice

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.*** The cancelled-invoice half (D-MST-16) is unit-tested and **has not been driven on a running server**.

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a customer `QA-OB3` created by the Firm admin with **Opening balance** `1500`, and a receipt of `600` applied to its *Opening balance* row (as TC-CUST-008 steps 1 and 3). A second customer `QA-OB4` with **Opening balance** `1500` and nothing received.
- **Steps**
  1. As the prepared **Firm admin**: Masters > Customers → `QA-OB3` → Edit → **Opening balance** `400` → Save. Try `0`, then `2000`.
  2. Sell > Receipts → select the receipt of 600 → **Reverse** with a reason. Edit the customer again: **Opening balance** `400` → Save. Read Opening bills, Record Receipt and Journal Entries.
  3. Edit once more: **Opening balance** `0` → Save. Then **Delete** the customer.
  4. For `QA-OB4`: sell it 1 of the prepared product `QA-P` and take the sale to an **approved** invoice. Edit the customer: **Opening balance** `400` → Save.
  5. **Cancel** that invoice with a reason. Edit the customer: **Opening balance** `400` → Save.
- **Expect**
  - Step 1: each is refused and the figure stays 1,500: "Opening balance cannot be changed while other entries stand on <code>'s account: receipt RC-… of 600.00. Reverse or cancel them first. Where the customer has really traded, leave the opening balance and correct what is owed with a credit note or an adjustment."
  - Step 2: with the receipt reversed the change saves. Opening bills shows the bill of 1,500.00 **Cancelled** ("The customer's opening balance was revised.") and **one** standing bill of **400.00**; Record Receipt lists one row of 400.00. Two journals: `<code>-OB-REV` mirrors the first, and `<code>-OB2` posts Dr 1100 Trade Receivables 400.00 / Cr 3000 Opening Balance Equity 400.00.
  - Step 3: at 0 no bill stands, the lists are empty and one more journal takes the 400.00 back; the customer can then be deleted.
  - Step 4: refused in the same words, naming the invoice: "…: invoice SI-… of …. Reverse or cancel them first. …"
  - Step 5: once the invoice is cancelled it no longer holds the figure, and the change to 400 saves as in step 2.
### TC-CUST-010 — Recording, cancelling and importing opening bills needs the settings permission

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/PURCHASING_API_CHECK_ROUND_4_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a **Sales Manager** and a **Firm Manager** user in the firm; a customer `QA-OB5` with one opening bill of `5000` the Firm admin entered (Masters > Customers → the customer → Opening bills → **Add opening bill**), and a customer `QA-OB6` with none.
- **Steps**
  1. As the **Sales Manager**: Masters > Customers → `QA-OB5` → **Opening bills**. Look for **Add opening bill** and for **Cancel** on the row; look for **Import opening bills** on the Customers toolbar.
  2. **(HTTP)** As the Sales Manager: `POST /api/v1/customers/{id}/opening-bills` for `QA-OB6` with 900; `POST /api/v1/customers/opening-bills/{bill_id}/cancel` on the bill of 5,000; `POST /api/v1/customers/opening-bills/import`; `POST /api/v1/customers/opening-bills/import-file` with `apply=false`, then `apply=true`.
  3. As the **Firm Manager**: on `QA-OB6` → Opening bills → **Add opening bill**: reference `OLD-7`, amount `900`, **dated today** → Save. Add another dated **tomorrow**. Then **Cancel** the bill of 900 with a reason. As the **Firm admin**: Customers toolbar → **Import opening bills** with a file of one bill: Check, then Apply.
- **Expect**
  - Step 1: the list of opening bills opens and reads the 5,000.00; **Add opening bill**, **Cancel** and **Import opening bills** are not offered.
  - Step 2: each is refused with **403**: "Recording a customer's opening bill needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; "Cancelling a customer's opening bill needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)."; and for the import, the file check and the file apply, "Importing customers' opening bills needs the manage customer settings permission (CUSTOMER_MANAGE_SETTINGS)." After each the customer owes what it owed (0.00 and 5,000.00) and no journal is written. A Customer Support user is refused the two import routes earlier, with "You do not have permission to perform this action.", because the job cannot import customers at all.
  - Step 3: the bill dated today saves and posts (Dr 1100 Trade Receivables 900.00); the one dated tomorrow is refused: "An opening bill is one raised before the books here start, so its date cannot be after <today>.", where today is the firm's own day. The cancel reverses the journal. The file check reports one bill to create and writes nothing; Apply posts it. The same date rule holds for a supplier's opening bill.
---

## Vendors, products, branches and warehouses

The same rule as customers: an edit changes what it names. Vendors had six
child collections emptied by any edit that did not send them; a branch rename
cleared its street lines, city, default flag and GST registration, and a
warehouse rename its capability flags.

### TC-MAST-001 — A vendor edit keeps all six child collections

- **Preconditions:** A firm administrator of QA01, and a vendor `QA-V` *Supply Check* with one contact, address, bank account, tax record, attachment and note; a vendor category `QA-CAT` and type `QA-TYP`. (`QA-V`, Supply Check: one contact, address, bank account, tax record, attachment and note.)
- **Steps:** as the prepared **Firm admin**, Masters > Vendors → Edit `QA-V` → change only the phone → Save → reopen.
- **Expect:** the contact, address, bank account, tax record, attachment and note are **all still there**.
### TC-MAST-002 — Vendor categories and types

- **Preconditions:** A firm administrator of QA01, and a vendor `QA-V` *Supply Check* with one contact, address, bank account, tax record, attachment and note; a vendor category `QA-CAT` and type `QA-TYP`.
- **Steps**
  1. As the prepared **Firm admin**, Settings > Set up > Party lists > **Vendor Categories**; then **Vendor Types**. Add one to each: `QA-CAT2` / `QA-TYP2`.
  2. Edit `QA-V`: category `QA-CAT`, type `QA-TYP` → Save → reopen.
- **Expect**
  - Step 1: both lists load — the prepared `QA-CAT` and `QA-TYP` are in them — and both accept a new row. *(These returned nothing until the route order was fixed, and until 2026-09-11 the sidebar opened a "coming soon" placeholder — BACKLOG §26.)*
  - Step 2: both held, and the six child collections are still there.
### TC-MAST-003 — A product's slots

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode. (`QA-PM`, Slot Check.)
- **Steps:** as the prepared **Firm admin**, Masters > Products → open `QA-PM`.
- **Expect:** category **Shelf qa**; tax profile group **GST_18_LOCAL**; base, inventory and sales units **PIECE**, purchase unit **BOX** — each read as a name, not an id.
### TC-MAST-004 — A rename keeps a branch's address, city, GST registration and default flag

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (in **QA02**: `QA-BR`, Keep Branch, default, GST registered, 1 Keep Street / Keep Nagar, City qa.)
- **Steps:** sign in as the prepared **QA02 admin** → Masters > Branches → Edit `QA-BR` → rename to `Kept Branch renamed` → Save → reopen. **(HTTP)** `GET /api/v1/branches/{id}` to check the PAN — the desktop branch form has no PAN field, so the screen cannot show it survived.
- **Expect:** both street lines, the city (and its state), **GST registration** and **Default** are all unchanged on screen; the HTTP call shows the PAN unchanged too.
### TC-MAST-005 — A rename keeps a warehouse's capacity and capability flags

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (`QA-WH`, Keep Warehouse, 1000 SQFT, default; on: temperature controlled, cold storage, receiving area, dispatch area, inspection area, loading dock; off: hazardous, returns area, packing area.)
- **Steps:** as the prepared **QA02 admin**, Masters > Warehouses → Edit `QA-WH` → rename → Save → reopen.
- **Expect:** capacity 1000 SQFT, Default, and **every flag exactly as listed** — the six on still on, the three off still off. *(Until 2026-09-11 a warehouse with no capacity could not be saved at all — BACKLOG §28.)*
### TC-MAST-006 — An import with one bad row imports nothing

- **Preconditions:** A firm administrator of QA02 with a default branch and warehouse, and two import files (one valid, one with a bad row). (prints the paths of two files, **Import, clash** (five rows; the fifth reuses `QA-BR`) and **Import, clean** (the first four).)
- **Steps**
  1. As the prepared **QA02 admin**, Masters > Branches → **Import** → the **clash** file.
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
- **Steps:** as the prepared **Firm admin**, Settings > Set up > Item lists > **Packaging Levels** (or Ctrl+K and the screen's name) → product `QA-PM` → type the barcode into "Scan or type a code" → **Look up**.
- **Expect:** resolves to **Slot Check qa**, level **Case**, **12** base units. No scanner needed: a scanner only types the digits and presses Enter.
### TC-MAST-009 — One company, two customer accounts

*Added 2026-10-02 (decision A7).*

- **Preconditions:** a customer `QA-HO` with GSTIN `29AAACP1234C1Z5`.
- **Steps:** Masters > Customers → **New**: code `QA-KA2`, GSTIN `29AAACP1234C1Z5` → Save; on the question, **Cancel**; then Save again → **Save anyway**. New again: code `QA-TN`, GSTIN `33AAACP1234C1Z9` → Save → Save anyway. Then New with code `QA-HO` again.
- **Expect:** the first save asks "Same GSTIN or PAN on another customer", naming **QA-HO** for both the GSTIN and the PAN; Cancel keeps everything typed and saves nothing; Save anyway saves. `QA-TN` is asked about the PAN only, and its PAN box holds `AAACP1234C` (filled from the GSTIN, no longer left blank). A second `QA-HO` is refused: "Customer code QA-HO already exists in this firm."

### TC-MAST-010 — Mapping another software's export on import

*Added 2026-10-02 (decision B3).*

- **Preconditions:** a CSV with the headings `Account No`, `Ledger Name`, `GSTIN/UIN`, `Remarks` and two customer rows (as a Tally ledger export might be).
- **Steps:** Masters > Customers → "..." → **Import** → choose the file. Look at the mapping table. Leave `Account No` as *Not imported* and press **Check**. Then map `Account No` → **Code**, `Remarks` → *Not imported* → **Save mapping as...** "Tally ledgers" → **Check** → **Import**. Close, open Import again with the same file, choose *Saved mappings* → "Tally ledgers".
- **Expect:** the table shows each heading with sample values; `Ledger Name` is already mapped to **Name** and `GSTIN/UIN` to **GSTIN**; `Account No` starts *Not imported*. With Code unmapped, Check is held back with a warning that the required **Code** column is not mapped. Mapped, the check is clean and the import creates both customers. The saved mapping fills the table the same way on the second open.
---

### TC-MAST-011 — Principals and brands, and a price revision with an effective date

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Item lists > **Principals** → New *Acme Foods*; **Brands** → New *Acme Gold* under it. Masters > Products → `QA-PM` → pick the brand → Save. Sell > All Sell screens > Insight > **Sales Analysis** → group by Brand, then by Principal; filter by one. Back on the product open **Price history** → add a revision with a price **dated next week** and another dated yesterday; import revisions from a file (one bad row). Quote the product today and with next week's date.
- **Expect:** principals and brands are masters with their own screens; the product carries a brand (text brands that existed are carried over); sales analysis offers Brand and Principal as dimensions and filters. A price revision is the price **in force on the document's date**: today's quote takes yesterday's revision, a quote dated next week takes the later one; the unit-price resolver and a blank price on a purchase order read it. The import checks every row and writes nothing if one is bad.
### TC-MAST-012 — A duplicate warning, and merging two customers

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a second customer *Master Check Stores* (same name once trade words are set aside) with the same GSTIN or the same last ten digits of phone, carrying an approved invoice and a receipt; the same for two vendors; a user holding CUSTOMER_DELETE and VENDOR_DELETE.
- **Steps:** as the prepared **Firm admin**: Masters > **Customers** → New, type the name *M/s Master Check Traders* and the same phone → before Save read the warning. Open the list, select the **duplicate** → **Merge into...** → pick `QA-CM` (the survivor) → confirm. Open the survivor's statement and balances. Repeat for vendors. Then try to merge a duplicate that has an invoice dated in a **closed financial year**.
- **Expect:** the warning (not a block) names customers sharing a GSTIN, the last ten digits of a phone, or the same name once punctuation and words like stores, traders, pvt, ltd and M/s are set aside. The merge re-points every document and ledger row that named the duplicate in **one transaction**; where a unique key would collide the survivor's row is kept (per-period ledger amounts are added); stored balances are summed; the duplicate is soft-deleted and records which customer it was merged into. A duplicate with an invoice or settlement in a locked financial year is refused. Without CUSTOMER_DELETE (VENDOR_DELETE) the merge is refused.
### TC-MAST-013 — A customer's bank accounts and files

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a sales manager and an accountant; a PDF.
- **Steps:** as the prepared **Firm admin**: Masters > Customers → `QA-CM` → **Bank accounts** → add an account (name, number `1234567890123456`, IFSC) → Save. Open **Files** → add the PDF; delete it. Sign in as the **Sales manager** and open the same tabs. Look at the customer's audit trail.
- **Expect:** the list of accounts is replaced as a whole on save. The administrator sees the number whole; the sales manager and accountant, who do not hold CUSTOMER_MANAGE_BANK_DETAILS, see only the last four digits; the audit trail shows it masked. Files are references (name, type, path, caption); a delete is soft and audited.
### TC-MAST-014 — A customer who is also a supplier

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** a vendor with the **same PAN** as the customer, and another vendor with a different PAN; an approved sales invoice to the customer and a supplier bill from the vendor.
- **Steps:** as the prepared **Firm admin**: Masters > Customers → `QA-CM` → **Also a supplier** → pick the same-PAN vendor → Save; try the different-PAN vendor and a vendor already linked to another customer. Open **Combined statement**. On the vendor open **Also a customer**. Accounts > All Accounts screens > Books > **Party Adjustments** → set-off.
- **Expect:** a link is accepted only for the firm's own live, unclaimed vendor with the same PAN; the others are refused by name. The combined statement merges the customer and supplier statements in date order with a running **net**; it needs CUSTOMER_VIEW plus VENDOR_VIEW. The supplier editor shows the link back. The set-off dialog preselects the linked party.
### TC-MAST-015 — Codes issued from a series

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**: Masters > Customers → New and look at the Code box; leave it blank and save. Do the same for a vendor and a product. Then create a customer typing the code `CUS-00009` and another with a blank code.
- **Expect:** the editor says *Blank: issued on save*. The saved codes come from the series — **CUS**, **SUP**, **PRD** — five digits, with no financial year in them and no yearly reset. A typed code stands and the counter steps over it, so the next blank one does not collide with it.
### TC-MAST-016 — Customer and supplier PAN reports

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Also needs:** one customer with no PAN and one with a malformed PAN (import it through the customer import); a vendor with the same two faults.
- **Steps:** as the prepared **Firm admin**: Reports > Financial → **Customer PAN check**; then **Supplier PAN check**. As a role without CUSTOMER_VIEW open the first.
- **Expect:** each report lists the live parties whose PAN is missing or fails the format, with six columns; a party with a good PAN is not listed. The customer report needs CUSTOMER_VIEW and the supplier report VENDOR_VIEW.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 05-S01 | **Masters > Customers** | Offered to any role holding `CUSTOMER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S02 | **Sell > Customer Statements** | Offered to any role holding `CUSTOMER_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S03 | **Masters > Products** | Offered to any role holding `PRODUCT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S04 | **Masters > Vendors** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S05 | **Settings > Set up > Party lists > Vendor Categories** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S06 | **Settings > Set up > Party lists > Vendor Types** | Offered to any role holding `VENDOR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S07 | **Masters > Branches** | Offered to any role holding `BRANCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S08 | **Masters > Warehouses** | Offered to any role holding `WAREHOUSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S09 | **Settings > Set up > Locations > Storage Areas** | Offered to any role holding `STORAGE_AREA_MANAGE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S10 | **Settings > Set up > Locations > Warehouse Types** | Offered to any role holding `WAREHOUSE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S11 | **Settings > Set up > Locations > Branch Types** | Offered to any role holding `BRANCH_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S12 | **Settings > Firm > Financial Years** | Offered to any role holding `FINANCIAL_YEAR_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 05-S13 | **Settings > Firm > Firm Settings** | Offered to any role holding `FIRM_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
