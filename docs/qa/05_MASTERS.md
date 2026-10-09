# Masters: customers, vendors, products, branches and warehouses

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > Documents > Proforma` is a screen in the
Documents column, and `Settings > Set up > Pricing > Price Lists` is the gear at the
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
  2. Sell > Receipts → **Record Receipt** → `QA-OB1`: read the bills offered. Sell > Money > **Collection Sheet**. Masters > **Statements** → the customer's ageing and statement.
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
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Item lists > **Principals** → New *Acme Foods*; **Brands** → New *Acme Gold* under it. Masters > Products → `QA-PM` → pick the brand → Save. Sell > Insight > **Sales Analysis** → group by Brand, then by Principal; filter by one. Back on the product open **Price changes** → add a revision with a price **dated next week** and another dated yesterday; import revisions from a file (one bad row). Quote the product today and with next week's date.
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
- **Steps:** as the prepared **Firm admin**: Masters > Customers → `QA-CM` → **Also a supplier** → pick the same-PAN vendor → Save; try the different-PAN vendor and a vendor already linked to another customer. Open **Combined statement**. On the vendor open **Also a customer**. Accounts > Books > **Party Adjustments** → set-off.
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
### TC-MAST-017 — A goods type, a category that carries it, and a product that takes it

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`). What the type fills on the product is TC-MAST-020.*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Steps:** as the prepared **Firm admin**: Settings > Firm > **Goods Types**. Read the list. On *Medicine* choose **Use in this firm**; then **Set defaults** → HSN `3004` and one of the firm's tax groups → Save. Add a type of the firm's own: code `QA-SEED`, name *Seeds*, Batches and Expiry date on → Save. Try to add another with code `MEDICINE`. Settings > Set up > Item lists > **Product Categories** → New *Tablets* → Goods type **Medicine** → Save; New *Sundries* leaving the type at *General (no tracking)*; New *Strips* under *Tablets* with no type of its own. Masters > Products → New in *Tablets*; another in *Tablets* > *Strips*; another in *Sundries*; another with no category. Read each product back over the API (`GET /api/v1/products/{id}`).
- **Expect:** the list shows five shared types (Medicine, Food, Cosmetics and personal care, Paint, Electronics) marked *Shared*, none in use on a firm whose profile starts with none, and what each tracks. A shared row offers *Use in this firm* and *Set defaults* and neither Edit nor Delete; over the API a change to one is refused *is a shared goods type and cannot be changed here*. The firm's own type is saved, is in use at once and is listed *Own*; the code `MEDICINE` is refused *already exists*. The category picker offers only types the firm uses, plus General. The products in *Tablets* and in *Strips* carry Medicine's `goods_type_id`; the ones in *Sundries* and with no category carry null. A default tax group the firm does not have is refused.
### TC-MAST-018 — A category changes type, a product changes category, and a type in use cannot go

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** Medicine, Food and Paint in use; a category *Syrups* carrying Medicine with one product in it; a category *Enamels* carrying Paint.
- **Steps:** as the prepared **Firm admin**: Product Categories → *Syrups* → rename it only → Save, and read its type. Change its goods type to **Food** → Save. Read the product that was already in it; create a second product in it. Move the first product to *Enamels*; then clear its category. Goods Types → on *Food* choose **Stop using**. Give *Syrups* the type *General*, then **Stop using** Food again. Add a type of the firm's own, file a category and a product under it, then delete the type; clear the category's type and delete again.
- **Expect:** a rename leaves the category's type alone. After the change to Food the product already filed keeps Medicine and the new one takes Food. Moving the first product to *Enamels* gives it Paint; clearing its category makes it General (null). *Stop using* is refused while a category carries the type -- *is still the goods type of category Syrups* -- and accepted once none does; products that hold the type keep it. Deleting the firm's own type is refused while a category carries it and, after that is cleared, while the product still does (*is still the goods type of product ...; deactivate it instead*).
### TC-MAST-019 — Who keeps goods types, and what a new firm starts with

*Added 2026-10-08 from the code (backlog 89, step 1); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Also needs:** on the same firm a **Firm manager** and a **Sales manager**; a second, new firm given the profile *Pharma Distribution* as its **first** profile, and a third given *General Agency Distribution*.
- **Steps:** as the **Firm manager**: open Goods Types and Product Categories; over the API `POST /api/v1/products/goods-types` and `PUT /api/v1/products/goods-types/{id}/use`. As the **Sales manager**: `GET /api/v1/products/goods-types`. As the **Firm admin**: the same two writes. As the platform administrator: read the goods types of the two new firms; on the pharmacy firm **Stop using** Medicine, change its profile to another and back, and read again.
- **Expect:** adding, changing, deleting and using a goods type need `CUSTOM_FIELD_MANAGE`: the firm administrator holds it and the writes succeed; the firm manager and the sales manager are refused 403 on the writes and can read the list (`PRODUCT_VIEW`). The pharmacy firm starts with Medicine in use and the agency firm with none. After Medicine is dropped and the profile is changed and changed back, Medicine is still not in use: a profile hands out its goods types once.
### TC-MAST-020 — A new product starts with its goods type's switches, HSN code and tax group

*Added 2026-10-08 from the code (backlog 89, step 2); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`): passes, with the receipt refused at completion.*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** Medicine in use with defaults HSN `3004` and one of the firm's tax groups; Electronics in use with no defaults; categories *Tablets* (Medicine), *Phones* (Electronics) and *Sundries* (General); a warehouse to receive into.
- **Steps:** as the prepared **Firm admin**, over the API: `POST /api/v1/products` in *Tablets* naming no switch, no HSN and no tax group (P1); in *Tablets* with `"track_batch": false` (P2); in *Tablets* with `"hsn_sac": "3003"` and another of the firm's tax groups (P3); in *Phones* naming no switch (P4); in *Sundries* naming no switch (P5); in *Sundries* with a `barcode`, a `qr_code`, `"track_warranty": true` and `"shelf_life_days": 365` (P6). Read each back. `GET /api/v1/products/metadata?category_id=<Tablets>`. `PUT` P5 moving it to *Tablets* and read it. `POST /api/v1/products/{P1}/duplicate`. Receive P1 on a goods receipt with no batch number and **complete** it, then with one; then `PUT` P1 with `"track_batch": false`.
- **Expect:** P1 has `track_batch`, `track_expiry`, `track_manufacturing_date`, `require_batch_on_receipt` and `require_batch_on_issue` true, serial and warranty false, `hsn_sac` `3004` and the default tax group. P2 has `track_batch` false, **both `require_batch_*` false**, and `track_expiry` still true. P3 keeps `3003` and its own tax group. P4 has `track_serial`, `track_warranty` and both `require_serial_*` true and no batch switch. P5 has every tracking switch false and no HSN. P6 is saved on any profile -- none of the four fields is refused with *does not enable*. The metadata names Medicine in `goods_type_id` and lists each type's nine `switches`. Moved to *Tablets*, P5 carries Medicine's `goods_type_id` and **its switches are unchanged**. The copy of P1 carries P1's switches. The receipt of P1 with no batch is saved as a draft and refused when it is **completed** (*must be received with a batch number*), and one with a batch completes; switching P1's batch tracking off is then refused because it holds stock.
### TC-MAST-021 — The product form shows its goods type's properties and no others

*Added 2026-10-08 from the code (backlog 89, step 2); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** the goods types, defaults and categories of TC-MAST-020; a **Sales manager** on the same firm.
- **Steps:** as the **Firm admin**: Masters > Products > New. Read the form before choosing a category. Choose *Tablets*; read the goods type line, the tracking section, HSN and tax group. Switch **Show all tracking options** on, then off. Switch *Track expiry* off and on; switch *Track batch* off and on. Change the category to *Phones*, then to *Sundries*. Type HSN `9999`, choose *Tablets* again. Type a barcode. Save. Open the saved product; open **Duplicate** on it. As the **Sales manager**: open the same product.
- **Expect:** with no category the line reads *Goods type: General*, the tracking section reads *No tracking for this goods type.* and offers only *Show all tracking options*. On *Tablets*: *Goods type: Medicine* (not a control), *Track batch*, *Track expiry* and *Track manufacturing date* on, *Require batch on receipt* and *on issue* on, no serial or warranty switch, HSN `3004` and the default tax group filled. *Show all* adds lot, serial and warranty and hides them again while they are off. *Track expiry* off hides shelf life and the three expiry rule boxes; *Track batch* off hides the issue rule and both *Require batch* switches, and they come back **off**. *Phones* shows serial and warranty and clears the HSN the type had filled; *Sundries* shows the hint. The typed `9999` survives the change back to *Tablets*. The barcode box accepts typing on any profile. The saved product reopens with the switches it was saved with and its stored goods type; the duplicate opens with the same switches. The sales manager sees the form read-only, as before. Opening a new product makes no server call of its own and each category picked makes one (`/products/metadata`); nothing calls `/products/goods-types`.
### TC-MAST-022 — A unit set fills a new product's units and its own conversion rule

*Added 2026-10-08 from the code (backlog 89, step 3); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** the goods types and categories of TC-MAST-020 (*Tablets* is Medicine, *Emulsions* is Paint, *Sundries* has no type); a **Sales manager** and a second firm in the same store.
- **Steps:** as the **Firm admin**: Set up > Unit Sets; read the list. Try to edit *Strip, box of 10*. Add *Jar, case of 6* (stock and sales unit Jar, purchase unit Case, factor 6, goods type Food). Add a second set with the same name; add one with a factor and the purchase unit equal to the stock unit. Masters > Products > New: choose *Tablets*, open the **Unit set** list; tick **Show all unit sets**; choose *Strip, box of 10*; save as `US-1`. New: *Tablets*, *Strip, box of 15*, save as `US-2`. New: *Tablets*, *Strip, box of 10*, then change the purchase unit to Carton and the conversion to 120, save as `US-3`. New: *Emulsions*; read the list; through *Show all* choose *Strip, box of 10*; save as `US-4`. New: *Sundries*, no unit set, save as `US-5`. New: no unit set, base unit Piece, purchase unit Box, conversion 12, save as `US-6`. Buy 2 Box of `US-1` on an order dated last year. Save a product `US-7` from *Jar, case of 6*, edit the set to factor 12, save `US-8` from it, delete the set, open `US-7`. Open `US-1` for editing. As the **Sales manager**: open Unit Sets and try to add one. As the second firm's admin: read the Unit Sets list.
- **Expect:** the list shows the eight shared sets marked Shared, with their goods types (*Bottle, carton of 24* under Medicine, Food and Cosmetics; *Piece, loose* as All goods). A shared set cannot be edited or deleted and says so. The firm's own set saves; the repeated name is refused by name; the factor between one and the same unit is refused. On *Tablets* the list offers Medicine's sets and the two tied to no type, and *Show all* adds the rest. Choosing a set fills the unit boxes, Allow decimal and the conversion box, all still editable. `US-1` has Strip/Box/Strip and its own rule 1 Box = 10 Strip; `US-2` 15; `US-3` Carton and 120 with the base unit still Strip. `US-4` saves with no refusal and no warning. `US-5` has no units and no rule; nothing was pre-filled. `US-6` has its own rule 1 Box = 12 Piece. The back-dated order line converts to 20 Strip. `US-7` keeps Case and 6 after the edit and after the delete; `US-8` took 12. Editing `US-1` shows *Units from: Strip, box of 10*, no unit set list and no conversion box. The sales manager reads the list and is refused the add. The second firm sees the shared sets and not *Jar, case of 6*. Opening the product form makes no call to `/uom-framework/unit-sets` and none for a profile's default units.
### TC-MAST-023 — A batch, a serial and their dates are allowed by the product's switches, not the firm's profile

*Added 2026-10-08 from the code (backlog 89, step 4); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** a **Sales manager** (or any user without `BATCH_CREATE`) on the same firm. The firm's profile does not matter and may have none of the expiry, batch or serial features.
- **Steps:** as the **Firm admin**: create three products. `TR-MED`: batch, expiry and manufacturing date tracking on. `TR-PAINT`: batch tracking on, expiry off. `TR-PHONE`: serial and warranty tracking on, batch off. Then, through Inventory > Batches and Serial Numbers: (a) add a batch with an expiry date for `TR-MED`; (b) add a batch with an expiry date for `TR-PAINT`, then the same batch without the expiry; (c) add a batch for `TR-PHONE`; (d) add a serial with warranty dates for `TR-PHONE`, then a serial for `TR-PAINT`; (e) set the `TR-PAINT` batch from (b) on hold; (f) Masters > Customers: save a customer with a minimum shelf life of 90 days. As the **Sales manager**: (g) repeat (a) with a new batch number.
- **Expect:** (a) accepted. (b) the first is refused with 422 naming `TR-PAINT` and expiry ("does not track expiry dates, so expiry_date cannot be set. Switch it on for the product first."); the second is accepted. (c) refused with 422: `TR-PHONE` is not tracked by batch. (d) the phone's serial is accepted; the paint's is refused with 422, not tracked by serial. (e) accepted, although the product's switch could now be off: an existing batch can always be held. (f) accepted on a firm whose profile has no expiry feature. (g) refused with 403 for the missing permission, and no batch is written.
### TC-MAST-024 — An extra field is shown and required by goods type, customer group and supplier type

*Added 2026-10-08 from the code (backlog 89, step 5); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** goods types *Medicine* and *Paint* in use, category *Tablets* (Medicine), *Emulsions* (Paint) and *Sundries* (no type); customer groups *Contractors* and *Retailers*; supplier types *Importer* and *Local*; a **Firm manager** on the same firm. The firm's profile does not matter.
- **Steps:** as the **Firm admin**, under Set up > Custom Fields: add the firm's own fields `SHADE_CODE` (product), `CONTRACTOR_REG_NO` (customer) and `IMPORT_EXPORT_CODE` (supplier). Add three rules: `SHADE_CODE` for goods type *Paint*, not compulsory; `CONTRACTOR_REG_NO` for customer group *Contractors*, compulsory; `IMPORT_EXPORT_CODE` for supplier type *Importer*, compulsory. Then: (a) open a new product and pick *Emulsions*, then *Tablets*, then *Sundries*; (b) save a customer in *Contractors* with the registration number empty, then filled; (c) save a customer in *Retailers*, and one in no group; (d) send, over the API, a *Retailers* customer carrying a value for `CONTRACTOR_REG_NO`; (e) move the customer of (b) to *Retailers* and save; (f) save a supplier of type *Importer* without the code, then with it, and one of type *Local* without it; (g) add the *Contractors* rule a second time; (h) add a rule for `SHADE_CODE` naming customer group *Contractors*. As the **Firm manager**: (i) add any rule.
- **Expect:** (a) *Shade Code* is offered for *Emulsions*, optional, and is not offered for *Tablets* or *Sundries*. (b) the first save is refused, "Required attributes are missing"; the second is accepted and the value reads back. (c) both accepted; neither form shows the field. (d) refused with 422, "do not apply". (e) accepted; the registration number the customer already held is still stored and still shown. (f) refused, then accepted; the *Local* supplier is accepted without it. (g) refused with 409, "already exists". (h) refused with 422: a product field cannot name a customer group. (i) refused with 403, and no rule is written.
### TC-MAST-025 — A firm switches a shared extra field off, and its values are kept

*Added 2026-10-08 from the code (backlog 89, step 5); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** one **shared** customer field (added by the platform administrator under Platform > Dynamic Attributes, for example `TRADE_LICENCE_NO`); a second firm in the **same store** -- two firms of the shared store, which the `shared-pair` preparation gives; the `product-master` firm and a second preparation firm are stores of their own, where a shared field of one does not exist in the other, so step (e) cannot be driven on them; a **Firm manager** on the first firm.
- **Steps:** as the **Firm admin** of the first firm: (a) save a customer with a value in the shared field; (b) under Set up > Custom Fields, switch the shared field off for this firm; (c) open that customer, and open a new customer; (d) send, over the API, a new customer carrying a value for the field; (e) open a new customer in the **second** firm; (f) switch the field on again and open the first customer; (g) try the switch on one of the firm's **own** fields. As the **Firm manager**: (h) switch the shared field off.
- **Expect:** (b) accepted; the list shows the field as off for this firm. (c) the existing customer still shows the value it holds; the new customer is not offered the field. (d) refused with 422, "do not apply". (e) the second firm is still offered the field. (f) the value saved in (a) is there, unchanged. (g) refused with 404: a firm's own field is retired by making it inactive. (h) refused with 403. The audit trail of the first firm holds two `firm_custom_field.use_changed` rows, off then on.
### TC-MAST-026 — The Inventory menu shows only the tracking the firm's goods need

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** a firm of its own with **no** goods type in use, no category carrying a type, and no product with a tracking switch on; the shared goods types *Paint* (batch only), *Electronics* (serial and warranty) and *Medicine*; a second user on the firm whose role lacks `BATCH_VIEW`; a second firm in the same store holding one product with *Track batch* on and no goods type (the old kind, filed before goods types existed).
- **Steps:** as the **Firm admin** of the first firm: (a) sign in and open the Inventory menu (Stock, and Tracking). (b) Set up > Goods Types: **Use in this firm** on *Paint*; file a category *Enamels* under it. Without signing out, read the menu; then sign out and in again and read it. (c) Use *Electronics* the same way, sign out and in. (d) Stop using both types after clearing the categories' types; sign out and in. (e) As the user without `BATCH_VIEW`: with Paint in use again, sign in and read the menu. (f) As the **Firm admin** of the second firm: sign in and read the menu. (g) Switch from the first firm to the second and back through the firm switcher. (h) Read `GET /api/v1/business-framework/active-modules` with no `X-Firm-ID` header, then with each firm.
- **Expect:** (a) Batches, Lots, Serial Numbers and Expiry Monitor are all absent; the rest of Stock is there. (b) before signing in again the menu is unchanged (the answer is read at sign-in and at a firm switch); after it Batches and Lots show and Serial Numbers and Expiry Monitor do not. (c) Serial Numbers is added; Expiry Monitor is still absent, Paint and Electronics track no expiry. (d) all four are gone again. (e) the user without `BATCH_VIEW` does not see Batches or Lots although the firm's goods need them. (f) Batches and Lots show, because a live product has *Track batch* on although the firm uses no goods type; Serial Numbers does not. (g) the menu changes with the firm each time, with no further sign-in. (h) the INVENTORY row carries `goods_tracking` as a list (for the first firm `BATCH` while Paint is in use, `BATCH` and `SERIAL` once Electronics is too); every other row carries null; with no `X-Firm-ID` the call answers 200 with an empty list, because the modules are kept in each firm's store and there is no firm to answer for (it answered 503 before D-CFG-26). The client does not ask while no firm is selected, and shows every screen. Opening the menu makes no extra request beyond the `active-modules` call the shell already makes at start.
### TC-MAST-027 — A product import with no switch columns takes its category's goods type

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** categories *Tablets* (goods type Medicine), *Emulsions* (Paint), *Sundries* (no type) and *Strips* under *Tablets* with no type of its own; a user on the same firm whose role lacks `PRODUCT_IMPORT`.
- **Steps:** as the **Firm admin**: Masters > Products > Import > download the template and read the columns. Build a file from the template that **omits** the TrackBatch, TrackExpiry and TrackSerial columns, with four new products: `IM-MED` in *Tablets*, `IM-SUB` in *Tablets* with sub category *Strips*, `IM-PAINT` in *Emulsions*, `IM-GEN` in *Sundries*. Check, then Import; open the four products. Build a second file with the three columns present: `IM-NO` in *Tablets* with TrackExpiry **No** and the other two blank; `IM-YES` in *Sundries* with TrackBatch **Yes**; `IM-BAD` in *Sundries* with TrackBatch `maybe`. Check; read the problems; remove the bad row; Import; open the products. As the user without `PRODUCT_IMPORT`: open the Products screen and call the import check over the API.
- **Expect:** the template lists the three tracking columns as optional ("Blank takes the goods type of the product's category.") and a UnitSet column. The first check is clean and the import writes four products: `IM-MED` and `IM-SUB` track batch, expiry and manufacturing date (the sub category with no type takes its parent's); `IM-PAINT` tracks batch only; `IM-GEN` tracks nothing. In the second file `IM-NO` tracks batch and manufacturing date but not expiry (a cell saying No wins); `IM-YES` tracks batch only (the file's Yes) and nothing else although the category has no type; `IM-BAD` is named in the check by row and column and the file does not import until it is removed. The user without `PRODUCT_IMPORT` has no Import button, and the same call over the API answers 403.
### TC-MAST-028 — The UnitSet column fills a new product's units and its pack rule

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day and corrected: a Unit beside a UnitSet is passed over with a warning (D-MST-17).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** the shared unit sets (*Strip, box of 10* is tied to Medicine, *Piece, loose* is tied to no type); categories *Tablets* (Medicine) and *Emulsions* (Paint); one existing product `UX-OLD` in *Tablets* with its own units.
- **Steps:** as the **Firm admin**: download the template and read the Lists sheet. Build a file with a UnitSet column: (1) `UX-1` in *Tablets*, UnitSet `Strip, box of 10`, no Unit; (2) `UX-2` in *Tablets*, UnitSet `Strip, box of 10`, Unit `Box`; (3) `UX-3` in *Tablets*, UnitSet `Blister, box of 99`; (4) `UX-4` in *Emulsions*, UnitSet `Strip, box of 10`; (5) `UX-5` in *Emulsions*, UnitSet `Piece, loose`; (6) `UX-OLD` again, UnitSet `Strip, box of 10`. Check. Remove row 3 and check again, then Import. Open each product. Repeat the file with the column headed `Pack size`.
- **Expect:** the Lists sheet has a Unit set column holding every set offered to the firm. The first check names row 3 as a problem on UnitSet ("'Blister, box of 99' is not an active unit set.") and imports nothing. After row 3 is removed the check is clean in problems but lists three warnings under "3 to look at. These do not stop the import.": row 2 on Unit ("is passed over: the unit set 'Strip, box of 10' fills this product's units and its pack conversion."), row 4 ("is marked for other goods types than this product's. It is imported as written.") and row 6 ("is passed over: a unit set fills a new product only, and this product keeps its units."). Import writes `UX-1` with the set's units and its own pack conversion (1 Box = 10 Strip), `UX-2` exactly as `UX-1` -- the set's units and the same conversion, its own Unit passed over (kept, the Unit made the purchase unit the stock unit and the conversion was dropped without a word: D-MST-17) -- `UX-4` with the Strip set as written, `UX-5` with Piece and no conversion. `UX-OLD` keeps its units and gains no conversion. The `Pack size` heading is read as the UnitSet column.
### TC-MAST-029 — What a business profile no longer does

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode. (, plus a platform administrator)
- **Also needs:** a firm on the **Generic** business profile (nothing but `ATTACHMENTS`); a **Firm manager** on it; a second firm on the **Pharmacy** profile; the sales hierarchy levels saved for the Generic firm by the **platform administrator** before step (d) -- a route needs them, and the firm administrator is refused that save (403).
- **Steps:** as the platform administrator: Settings > Business profile > Feature Management; read the list. Open the Generic profile and read its features. As the **Firm admin** of the Generic firm: (a) save a product with a barcode and a QR code; (b) on a product with *Track serial* and *Track warranty* on, add a serial number with warranty dates; (c) on a product with *Track expiry* on, add a batch with an expiry date; (d) Masters > Territory: create a route; (e) Masters > Warehouses: add a second warehouse; (f) record a vehicle number on a delivery note; (g) attach a file to a sales order. As the **Firm manager** of the same firm: repeat (c). As the platform administrator: assign the **Pharmacy** profile to the Generic firm and read the goods types of the firm; then assign the Generic profile again; read the goods types of the pharmacy firm.
- **Expect:** the feature list holds five rows -- Attachments, Vehicle Tracking, Drug License, Commission and Batch PTR / PTS -- and none of Batch Tracking, Expiry Tracking, Serial Number, Warranty, Barcode, QR Code, Territory, Multiple Warehouses or Approval Workflow. The Generic profile lists Attachments only. (a) to (e) are accepted with no refusal naming a profile or a feature. (f) is refused with 403 ("This firm's business profile does not enable VEHICLE_TRACKING, so ... cannot be set."): vehicle details are one of the five firm features and Generic does not map it. (g) is accepted. The firm manager's batch is refused for the missing permission when the role lacks `BATCH_CREATE`, and for no reason to do with the profile otherwise. Assigning Pharmacy to the Generic firm hands it **no** goods type and writes no `goods_type.starting_set` row: a firm takes its profile's goods types with its **first** profile only, as TC-MAST-019 says. Assigning Generic back changes nothing, and the pharmacy firm's goods types are unchanged by the round trip.
### TC-MAST-030 — Copying a product keeps its pack size

*Added 2026-10-08 from the code (backlog 89, step 6); driven over HTTP the same day (`docs/qa/GOODS_TYPES_API_CHECK_ROUND_1_2026-10-08.md`). The steps that read a screen were clicked the same day where `docs/qa/SCREEN_FLOW_CHECK_GOODS_TYPES_2026-10-08.md` lists them (cases in `docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md`).*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** a product `CP-SET` created from the unit set *Strip, box of 10*, then given its own conversion of 12 (1 Box = 12 Strip); a product `CP-HAND` with units typed by hand and no unit set; a user on the same firm whose role lacks `PRODUCT_CREATE`.
- **Steps:** as the **Firm admin**: Duplicate `CP-SET`, save the copy as `CP-SET-2`. Duplicate `CP-HAND`, save as `CP-HAND-2`. Stop offering the set *Strip, box of 10* (deactivate it if it is the firm's own, or use a firm-made copy of it), then duplicate `CP-SET` again as `CP-SET-3`. As the user without `PRODUCT_CREATE`: try to duplicate `CP-SET`.
- **Expect:** `CP-SET-2` shows *Units from: Strip, box of 10* and has its own pack conversion at the **source's** factor, 12, not the set's 10. `CP-HAND-2` has no unit set and the same units as its source, with a conversion only if the source had one. `CP-SET-3` keeps the units and the conversion but not the set's name, because the set is no longer offered. Over all three the source product is unchanged. The user without `PRODUCT_CREATE` is refused (403) and no product is written.
### TC-MAST-031 — Goods type in the analyses, the stock reports and the product list

*Added 2026-10-08 from the code (backlog 89, step 8); driven over HTTP the same day (`docs/qa/GOODS_TYPES_REPORTS_CHECK_2026-10-08.md`). Not yet clicked on screen.*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** the goods types and categories of TC-MAST-020 (*Tablets* is Medicine, *Sundries* has no type); a product `GR-MED` under *Tablets* and a product `GR-PLAIN` under *Sundries*, each with opening stock; one approved sales invoice and one approved supplier bill holding a line of each product, dated this month.
- **Steps:** as the **Firm admin**: (a) Sales Analysis, rows *Goods type*, this month; then columns *Month*. (b) Filter *Goods type* = Medicine, rows *Product*. (c) Click the Medicine cell of (a) for its invoices; try the General cell. (d) Purchase Analysis, rows *Goods type*. (e) Reports > Stock valuation, Stock ageing, Dead stock (days 1): read the *Goods type* column. (f) Masters > Products > Filters: *Goods type* = Medicine, Apply; then General; then Any. (g) Ask Sales Analysis for *Goods type* on both rows and columns.
- **Expect:** (a) two rows, *General* and *Medicine*, whose totals add up to the grand total; each holds the value of its own product's line and both count the one invoice. (b) only `GR-MED`. (c) the Medicine cell lists the invoice with the value of the Medicine line; the General cell does not open, as no cell of an unfiled value does. (d) *General* and *Medicine* with the two bill lines. (e) `GR-MED` reads Medicine and `GR-PLAIN` reads General on all three; the valuation's total, books and difference rows show no goods type. (f) Medicine lists `GR-MED` and no product without a type; General lists `GR-PLAIN` and no Medicine product; the count under the list matches; Any lists both. A firm that uses no goods type is not offered the filter. (g) refused: "Choose a different dimension for the columns."
### TC-MAST-032 — A pack's barcode finds its product, and the counter bill adds what the pack holds

*Added 2026-10-08 from the code (backlog 89, market gap 3); the server's half driven over HTTP the same day (`docs/qa/checks/goods_types/tc_mast_032.py`). The scan field and the product boxes are covered by widget tests; not yet clicked on screen.*

- **Preconditions:** A firm administrator of QA01, and a product `QA-PM` *Slot Check*: category *Shelf*, tax profile group GST_18_LOCAL, base, inventory and sales unit PIECE, purchase unit BOX, and a *Case* barcode.
- **Also needs:** a product `PK-SOAP` with its own barcode `PK-OWN` and stock in the counter's warehouse; a product `PK-TEA` with none. Under Masters > Packaging Levels, on `PK-SOAP`: a level *Carton*, unit BOX, 24 to the base unit, barcode `PK-CTN`, EAN `PK-EAN`. A cash customer.
- **Steps:** as the **Firm admin**: (a) Packaging Levels: scan `PK-CTN`, then `PK-OWN`. (b) Sales > new counter bill: scan `PK-OWN`, then `PK-CTN`, then `PK-CTN` again, then `PK-OWN`. (c) On a new counter bill scan `PK-CTN` first. (d) Scan a code nothing carries. (e) New sales order: click the first line's product box, type `PK-CTN`, press Enter; do the same on a quotation, a sales invoice, a purchase order and a supplier bill. (f) Masters > Products: search `PK-CTN`, then `PK-EAN`. (g) Give `PK-TEA` a level *Box* with barcode `PK-BOTH` and `PK-SOAP` a level *Pallet* with UPC `PK-BOTH`; scan `PK-BOTH` on the counter bill, then search it under Products. (h) Delete the *Carton* level; scan `PK-CTN` on the counter bill. As the **Sales manager**: (i) scan `PK-EAN` on a counter bill; try to add a level under Packaging Levels. As another firm's administrator: (j) scan `PK-CTN`.
- **Expect:** (a) *Carton* of `PK-SOAP`, one scan is 24 base units; then the product itself, one base unit. (b) the one line of `PK-SOAP` reads 1, then 25, then 49, then 50; after each carton the line beside the scan field reads *Carton (BOX) of PK-SOAP: 24 ... added.* and after the single piece it is gone; no second line appears, and the scan field keeps the focus throughout. (c) a new line of `PK-SOAP` with quantity 24. (d) *No product has the barcode ...*, the bill unchanged. (e) on each of the five documents the line takes `PK-SOAP`; its quantity is left for the person to type. (f) each search lists `PK-SOAP` alone. (g) the scan is refused in the server's words -- *2 products or packaging levels carry the code PK-BOTH* -- and nothing is added; the product search lists both products. (h) *No product has the barcode "PK-CTN"*. (i) the scan adds 24; the sales manager is refused a new level (403). (j) not found: another firm's pack answers nothing.
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
