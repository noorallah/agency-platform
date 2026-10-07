# Module status

What each module is for, what is built, and what is still open.

**Refreshed on 2026-10-05 without starting the application or running a
suite**, after the purchasing build (PG-1 to PG-14, `docs/BACKLOG.md` §86) and
the selling build (SG-1 to SG-9, §87). Rows and numbers marked *(10-05)* were
counted in the source tree that day; every other number keeps the date it
already carried. **The 23 features of those two builds were merged on their
own tests: none has been through a full test suite, a CI run or a hand test,
and no demo firm exercises one.** Their rows say *Built 2026-10-05*, which by
this file's own definition below is short of **Built**.

The summary counts were re-derived on **2026-10-01**; on **2026-10-03**, after the
Wave 1-3 backlog build, the migration head, the OpenAPI operation count and the
table count were re-read from the running application and the route count of
every module the build touched was re-counted (marked *(re-counted 10-03)*;
see the note under the table). They come from the running
application (OpenAPI, `Base.metadata`, the module catalogue and the suites);
the per-module rows below were compiled on **2026-09-05** from the running
application and the four demo firms. Neither is from memory. Route and report counts are read off the OpenAPI
schema; table and row counts off the deployed schemas. Re-derive them rather
than trusting this file after a few months — a stale status line is worse than
no status line, because it talks the next reader out of checking. The finance
entry in `CLAUDE.md` claimed for months that automatic GL posting was not
built, long after eleven modules were posting, and it survived exactly because
nobody re-derived it.

| | |
| --- | ---: |
| Backend modules (packages with a router) | 62 *(10-05: `ls backend/app/*/api/router.py`)* |
| API endpoints | 761 *(2026-10-01, not re-derived)* |
| Report endpoints | 58 *(2026-10-01, not re-derived)* |
| Desktop screens (catalog tabs) | 99 *(2026-10-01, not re-derived)* |
| Report catalogue entries (`report_catalog.dart`) | 102 *(10-05: `id:` entries in the file)* |
| Tables per firm store | 311 (328 with the platform's 17) *(10-05: `docs/TABLE_CATALOGUE.md`, generated at #1166)* |
| Permission codes | 232 in 38 groups *(10-05: `PERMISSION_GROUPS`)* |
| Control account purposes | 64 *(10-05: `len(ControlAccountPurpose)`)* |
| Tests passing | 2,376 backend unit + 52 integration + 2,221 desktop *(2026-10-01, not re-run)* |
| Migration head | `20261005_0326` *(10-05: the newest file in `backend/alembic/versions`)* |

At #947 (2026-10-02, night) the OpenAPI schema holds **926 operations on 695
paths, 88 of them under a `/reports` path**, and `Base.metadata` **237
tables** (221 per firm store plus the platform's 16). The table above was not
recounted the same way, so compare the two only by re-running both. The route
counts in the rows marked *(re-counted 10-02)* are OpenAPI operations under
the module's path prefix on that day.

At 2026-10-03 (after the Wave 1-3 build) the OpenAPI schema holds **1,186
operations on 898 paths, 98 of them under a `/reports` path**, and
`Base.metadata` **301 tables**. The table above was not recounted that way and
the test and screen counts in it are of 2026-10-01 (the suites were not run for
this refresh), so compare only by re-running. The route counts marked
*(re-counted 10-03)* are OpenAPI operations under the module's path prefix on
that day; report counts are the operations under a `/reports` path of that
prefix.

At 2026-10-05 (after the purchasing and selling builds) **nothing was read
from a running application**, so the OpenAPI operation count, the paths, the
`Base.metadata` count and the suite totals above are still the 10-03 and 10-01
figures and are certainly low. What was counted in the source: 62 packages
with a `router.py`; 328 `__tablename__` declarations under `backend/app`,
agreeing with `docs/TABLE_CATALOGUE.md` (328 tables, 17 of them platform-only);
102 report ids in `report_catalog.dart`; migration head `20261005_0326`. Route
counts marked *(counted 10-05)* are the `@router` decorators in that package's
`api/` folder, a different method from the OpenAPI count of 10-03 they replace; on each of
the nine older modules whose count moved, the increase matches the routes the
two builds added there. Suite sizes were not taken: no suite was collected or run.

## How to read this

A module is **built** when it has endpoints, a screen that reaches them, tests,
**and** seeded data that exercises it end to end. Anything short of that is
said plainly here, because the gap between "the code exists" and "somebody can
use it" is where nearly every defect in this project has lived — a route
declared below `/{id}`, a client method with no button, a report whose filter
no seeded row satisfies.

- **Built** — reachable, tested, exercised by the demo.
- **Partial** — works, but something named below is missing.
- **Open** — needs a decision, or is not started.

---

## Selling — quotation to cash

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Quotations `app/quotation` | 22 *(counted 10-05)* | 2 | Built | *10-05: files can be attached (SG-6).* Offer, accept, convert. Expiry derives from `valid_until`, never a stored status. *Rate includes GST* since 2026-10-02 (A32): the rate typed at shelf price is read back to pre-tax and kept as typed. Enquiries convert into one (SEL-10); a blank unit price is filled from the customer's price level; extra document fields carry from it to the order (MST-6); free-issue-only and not-for-sale products are refused on its lines. |
| Sales orders `app/sales_order` | 36 *(counted 10-05)* | 6 | Built | *10-05: files can be attached (SG-6); a service line reserves no stock (SG-3).* Status follows its deliveries. A hold is a flag, not a status, so part-shipped progress survives it. *Rate includes GST* since 2026-10-02 (A32). Wave 1-3: multi-level approval (`app/approvals`) gates approval; a reservation lapses after the firm's days and *Reserve again* takes it back (STK-12); price levels fill a blank price (SEL-9); outgoing quantity feeds availability (STK-10); has a printable order. |
| Delivery notes `app/delivery_note` | 36 *(counted 10-05)* | 6 | Built | *10-05: the transporter master (`transporters`, four routes here) with a carrier picker and freight terms on the note (SG-5); files (SG-6); a service line moves no stock (SG-3). The phase 2 editor only creates notes, so a raised note's carrier cannot be changed on screen.* Moves stock and cost of goods sold. Inherits the order line's price rather than re-reading the masters. Batches can be chosen per line since 2026-10-02 (backlog 79), a pinned order batch is picked first, and the challan prints one row per batch with its MRP. A note no invoice bills raises its own e-way bill (§77 row 9). Pick list and loading sheet PDFs (SEL-13); a kit short of assembled stock assembles from its components at dispatch (STK-15); the batch issue rule and expiry stop window apply (STK-5, STK-11). |
| Sales invoices `app/sales_invoice` | 38 *(counted 10-05)* | 15 *(counted 10-05)* | Built; the 10-05 additions unproven | *10-05: GST sales register and HSN summary of sales (SG-1); the walk-in cash sale with a buyer's name on the bill (SG-2); charges with their own GST, credited to 4050 (SG-4; not carried from the order, cannot be credited); files (SG-6); hold and recall of a counter bill (SG-7). Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it.* Prints a real GST invoice with the CGST/SGST split and an HSN summary, the offers given and what was saved. Money taken at the counter is entered on the bill and becomes a receipt on approval. Sales Analysis: any one or two dimensions, with drill-down (2026-10-01). Several delivery notes on one bill, customer first (SEL-1); counter billing with a scanner and split tenders (SEL-12); a UPI QR on the print (MSG-2); *falling due* report (ACC-6); multi-level approval; a customer pending approval cannot be billed (SEL-15). |
| Sales returns `app/sales_return` | 26 *(counted 10-05)* | 4 | Built | *10-05: files (SG-6); a returned service puts nothing on a shelf (SG-3, no test of its own).* Reverses stock, cost and the customer balance by the deltas the original row stored. A completed return of billed goods is e-invoiced as a credit note (D-TAX-2, A45) and prints with its IRN. Sellable goods can be held in quarantine until checked (STK-13); a late return warns (GST-1). |
| Credit notes `app/credit_note` | 12 *(re-counted 10-03)* | 3 | Built | Names the invoice **line**, so the tax reversed is the tax charged. Approval is a separate permission. Printable and e-invoiced as CRN since 2026-10-02 (§77 rows 4, 11). A credit note after 30 November following the supply's year warns (GST-1); the filing checks list it (GST-5). |
| Customer debit notes `app/customer_debit_note` | 10 *(re-counted 10-02)* | 1 | Built 2026-10-02 | The credit note turned round (§77 row 5): charges tax at the invoice line's rate, owed on the invoice (A40). Printable, and e-invoiced as DBN (§77 rows 4, 11). |
| Proformas `app/proforma` | 8 | 2 | Built | Posts nothing, and draws its own `PI` series so GSTR-1's declared invoice range stays whole. |
| Receipts and refunds `app/settlements` | 15 *(re-counted 10-03)* | 3 | Built | *10-05: a payment in a foreign bill's currency posts the exchange difference; a payment ahead of any bill proposes TDS 194C / 194J (PG-12, PG-5).* Money in and out through one document. Allocating posts no journal — the receipt already did. Receipts carry their payment mode and instrument date (ACC-3); early-payment discount is prefilled (SEL-14). Refunds are 5 routes more; payments, payment runs and post-dated cheques are in their own rows below. |
| Customers `app/customers` | 48 *(re-counted 10-03; same count 10-05)* | 1 | **Partial** | *10-05: the one* Cash sale *customer per firm (SG-2), a collector (SG-8) and a trade class for PTR / PTS (PG-14).* Statements and ageing reconcile to the account. Credit control ships in **warn** mode; no firm has chosen **block**. A GSTIN or PAN may repeat, warned by name (A7); a minimum shelf life per customer (79 row 6). Wave 1-3: *Pending approval* for new outlets (SEL-15); cash-discount terms and overdue interest with a debit-note action (SEL-14); a combined statement with a linked supplier (ACC-11); bank accounts and files (MST-4); duplicate warning and merge (MST-3); codes from a series (MST-5); PAN check report (PLT-11); statement PDF for reminders (MSG-3). |
| Price lists `app/pricing` | 12 *(re-counted 10-03)* | 0 | Built | Quantity ladders. A customer's own list **replaces** the firm-wide one rather than amending it. Price levels, rates per level per product, and a level on a customer or group (SEL-9); a price list can be scoped to a supplier (BUY-3). The resolver reads a product's price revision in force (MST-2). |
| Promotions `app/promotions` | 17 *(re-counted 10-03)* | 3 | Built | Offers stack and compound, or a firm gives the best one only; a percentage may be capped. Coupons, gifts and free shipping; *Try offers* before launch. A claim counts at approval, never while pricing. Wave 1-3 added buy-X-get-Y-at-a-discount, combo price, festival bonus points, customer-history and weekday/time conditions, bulk single-use coupon codes and a CSV export, offer copying, and the principal who funds an offer (SEL-2 to SEL-8, SEL-11). |
| Enquiries `app/enquiry` | 9 | 1 | Built 2026-10-03 | Leads and enquiries with follow-ups, converted into a customer and a quotation in one transaction; a lost enquiry carries a reason and has a report (SEL-10, A133). Quotation permissions, no new codes. Not built: a Home gadget and reminders. |
| Approvals `app/approvals` | 7 | 0 | Built 2026-10-03 | Up to three levels of sign-off by amount and role for sales orders, sales invoices, purchase orders and purchase bills, with bulk reject (PLT-1, A131). With no rule for a total nothing changes. |
| Principal claims `app/principal_claims` | 8 | 0 | Built 2026-10-03 | What a principal owes for the schemes it funds, expiry write-offs and damaged returns, raised once each, settled by its credit note or payment (SEL-11, A128). Free quantity on a bill line is not yet counted as a scheme cost. |
| Loyalty `app/loyalty` | 10 | 3 | Built | One ledger for points and cashback. Redeeming **settles** the bill, so the full GST is charged. |
| Commission `app/commission` | 13 | 0 | Built | Ladders, margin basis, caps and targets. A payout is snapshotted at accrual and posts on approval. |
| Territory and beats `app/sales` | 64 *(re-counted 10-02)* | 0 | Built | Routes, salesman coverage, beat plans, call lists. Nine plans a firm, weekly through monthly. Holds the places masters too: India Post's districts, towns, PIN codes and localities load by state, and the southern states come with every store (B6). |
| TCS 206C(1H) `app/tcs` | 4 | 0 | Built | Charged on the **receipt**, on the excess over the threshold only. Disabled by default. |
| Collection follow-up `app/collections` | 6 *(counted 10-05)* | 0 | Built 2026-10-05 | Promises to pay per bill or per account with a derived status (pending, due today, kept, broken, withdrawn), the collection sheet and its PDF, the chase list, a collector on the customer (SG-8, #1161, #1164). Sell > All Sell screens > Money > Collection Sheet and Payment Promises. Posts nothing. Not built: a promise for the account from the screen, the promise on the statement, a reminder from a broken promise. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Counter shifts `app/counter_shifts` | 6 *(counted 10-05)* | 0 | Built 2026-10-05 | A cashier's till: float, expected cash derived from the cash tenders, a counted close whose difference posts to 6960 *Cash Short and Over* (SG-7, #1165, #1167). The counter bill's shift strip and Sell > All Sell screens > Documents > Counter Shifts. A bill paid at the counter is stamped with the open shift of the cashier who made it, and with its approver's only when the maker has none open (D-SELL-51, fixed #1174). Not built: a counter refund, denominations, hand-over. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Customer rebates `app/customer_rebates` | 9 *(counted 10-05)* | 1 | Built 2026-10-05 | Turnover rebate agreements for a customer or a customer group: accrue (Dr rebates allowed, Cr customer rebate payable), reverse, settle by a party adjustment of kind CUSTOMER_REBATE; a statement and a report (SG-9, #1166). **The screen exists since #1168**: Sell > All Sell screens > Documents > Customer Rebates. *Settle against bills* is shown on `PARTY_ADJUSTMENT_MANAGE` alone, so a sales manager is not offered it (D-SELL-52, fixed #1174). No GST on a rebate; settling by a GST credit note is not built. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Document files `app/document_files` | 0 of its own | 0 | Built 2026-10-05 | The shared store behind **Attachments** on the purchase bill and goods receipt (PG-4) and on the quotation, order, delivery note, invoice and return (SG-6): PDF, JPG or PNG up to 10 MB, bytes in the firm's store. Its routes are on each document's router (four each). OCR is not built. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |

## Buying — order to payment

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Purchase orders `app/purchase` | 51 *(re-counted 10-03; same count 10-05)* | 9 | Built | *10-05: a rate contract's rate and a supplier scheme's free goods on the line, with a free-only line priced live (PG-9, PG-11); Send by WhatsApp (PG-7, template only); Currency and Exchange rate on the order, and a Capital goods tick on its line (D-BUY-39, D-BUY-40, fixed #1175).* Approval cannot be skipped; status follows the receipts. Reports added 2026-09-04. Reorder from typed levels or from sales since 2026-10-02 (backlog 69 row 12). Each line carries a derived quantity picture (received, returned, invoiced, still to come, still to bill) and the order a billing status and a complete flag beside its status (A33). Wave 1-3: requisitions with convert and raise-from-reorder (BUY-7); amendment with a revision list (BUY-8); supplier rates and catalogue fill a blank price (BUY-3, BUY-4); order multiples (BUY-5); expected date from lead time (BUY-6); a purchase budget checked at approval (BUY-14); supplier performance and price trend reports (BUY-12). |
| Goods receipts `app/goods_receipt` | 25 *(counted 10-05)* | 5 | Built; the 10-05 additions unproven | *10-05: serial numbers on the line with a range fill (PG-10); PTR and PTS on a batch line (PG-14); files (PG-4).* Posts stock and the ledger. A cancellation values the reversal from the **movement**, not the document. Records the inward e-way bill, warned above the firm's limit (§78 row 6), and each batch's MRP (A41). Quality inspection holds received goods in quarantine until decided (BUY-9); the scheme a free line came under (BUY-1); barcode labels for what a receipt stocked (STK-16); shelf life fills an expiry (STK-18). |
| Purchase invoices `app/purchase_invoice` | 35 *(counted 10-05)* | 16 *(counted 10-05)* | Built; the 10-05 additions unproven | *10-05: GST purchase register and HSN summary (PG-1); payables by supplier and month (PG-2); pay at approval (PG-3); files (PG-4); TDS 194C / 194J proposed and posted (PG-5); TCS charged by the supplier (PG-6); a bill in the supplier's currency (PG-12); a capital-goods line that raises an asset (PG-13). Fixed the same day (#1175): the registers and GSTR-3B's input side show a foreign bill in rupees (D-BUY-35), the Approve dialog's TDS proposal is the server's (D-BUY-37), a bill is held to its order's currency (D-BUY-39), and a line received as capital goods is capitalised by its bill (D-BUY-40). A debit note or a return against a foreign bill posts rupees at the bill's rate (D-BUY-41), and GSTR-2B, rule 37 and rule 42 read rupees (D-CMP-23). Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it.* Approval clears the accrual, after which the receipt can no longer be cancelled. Purchase price variance and Purchase Analysis (2026-10-01). Records the supplier's IRN, warned when an e-invoicing supplier's bill has none (§78 row 5). A debit note's excess over its bill is supplier credit (A4). A bill outside the firm's price tolerance is held for a person with the over-tolerance permission (BUY-10); several receipts on one bill (SEL-1); a *falling due* report (ACC-6); a bill after its credit's last date warns (GST-3). |
| Purchase returns `app/purchase_return` | 22 *(re-counted 10-03)* | 6 | Built | Damaged and expired reports have rows only since 2026-09-04 — no seeded line carried the flags before. Each return records an outcome -- credit, replacement or refund (A34) -- and a return off a paid bill leaves a supplier credit (D-BUY-20); one off a reverse-charge bill takes its share of the reverse charge off. |
| Vendors `app/vendors` | 51 *(re-counted 10-03; same count 10-05)* | 1 | Built | *10-05: a currency (PG-12); 194C and 194J as the usual TDS section, with individual / HUF and technical services (PG-5).* Categories and types reachable since the route-order fix. Child collections merge on a partial edit. GST type and *Supplier e-invoices* (§78 rows 2, 5). Wave 1-3: standing discount (BUY-3), catalogue (BUY-4), lead-time summary (BUY-6), ratings (BUY-15), the gifts register and 194R summary (BUY-2), a usual TDS section (ACC-7), a linked customer (ACC-11), duplicate warning and merge (MST-3). |
| Supplier rebates `app/supplier_rebates` | 7 | 0 | Built 2026-10-03 | Volume rebate agreements: accrue (Dr rebate receivable), reverse, settle by a party adjustment of kind SUPPLIER_REBATE (BUY-13, A124). |
| Requests for quotation `app/rfq` | 13 *(counted 10-05)* | 0 | Built 2026-10-05 | RFQ to several suppliers, their quotes, a comparison by rate after discount with the lowest marked, a choice per line, one draft order per chosen supplier; from an approved requisition (PG-8, #1127, #1128). Buy > All Buy screens > Documents > Requests for quotation. Emailing the RFQ is not built. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Rate contracts `app/rate_contracts` | 9 *(counted 10-05)* | 0 | Built 2026-10-05 | A rate, discount and optional quantity for a supplier and period; ranks above the supplier price list on an order line; drawn and remaining derived; over-drawing warns; expired is derived by date (PG-9, #1129, #1130). Buy > All Buy screens > Documents > Rate contracts. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Supplier schemes `app/supplier_schemes` | 5 *(counted 10-05)* | 0 | Built 2026-10-05 | "Buy n, get m" of the same or another product, for one supplier or all, dated; fills a blank free quantity on the order (PG-11, #1133, #1134). Buy > All Buy screens > Documents > Supplier schemes. "10+2" on the printed order is not built. Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Bills of entry `app/bill_of_entry` | 7 *(counted 10-05)* | 0 | Built 2026-10-05 | The customs document of an import: basic duty and surcharge landed on the linked receipts' stock, IGST claimed (GSTR-3B 4(A)(1)), customs payable booked; with the foreign-currency bill, payment and revaluation of PG-12 (#1135, #1136, #1137). Buy > All Buy screens > Documents > Bills of entry. Not built: the Bill of Entry in the GST purchase register and against GSTR-2B; returns and debit notes in another currency (D-BUY-41). An import runs on the full chain since #1175: the order carries the currency and rate (D-BUY-39). Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Landed costs `app/landed_costs` | 4 | 0 | Built 2026-10-03 | Freight, duty and handling spread over completed receipts by value, quantity or weight; the on-hand share revalues stock and the sold share goes to cost of goods sold (BUY-16, A129). |
| Payments, payment runs and post-dated cheques `app/settlements` | 42 | 0 | Built | *10-05: a payment in a foreign bill's currency with the exchange gain or loss (PG-12); the dialog's 194C / 194J hint follows the amount typed (D-BUY-36, fixed #1175).* Payments (20 routes), payment runs with a generic NEFT bank file (8, BUY-11; the firm's own bank layout is open) and the post-dated cheque registers (14, ACC-2); cheque printing on a CTS-2010 leaf (ACC-12). *(re-counted 10-03)* |

## Stock — what is on the shelf

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Inventory `app/inventory` | 71 *(re-counted 10-03)* | 6 | Built | Summaries by firm, branch, warehouse and product; ledger, counts, transfers, write-offs. Wave 1-3: stock transfers as a document with in-transit stock (STK-1); repacking (STK-4); count plans and blind sheets (STK-6); adjustment reasons, role limits and an approval queue (STK-3, STK-7, STK-8); evidence files (STK-9); incoming and outgoing on availability (STK-10); stock alerts for Home (STK-14); free-goods report (BUY-1). |
| Batches and serials `app/batch_serial` | 22 *(counted 10-05)* | 0 | **Partial** | *10-05: serials are created at the goods receipt and a unit's trail starts there (PG-10); a batch carries PTR and PTS behind the feature `BATCH_PTR_PTS` (PG-14). Both unproven.* Batch and expiry are exercised by two demo firms. **No firm serialises**, so that half runs on tests alone. §79 complete on 2026-10-02: availability for the picker on the delivery note and the counter bill, the firm's batch rules, minimum shelf life per customer, a pinned batch on the order, and a batch's own MRP and selling price. Per-product expiry rules and a *returns due* list (STK-5); an issue rule per product (STK-11). |
| Products `app/products` | 37 *(re-counted 10-03)* | 0 | Built | *10-05: a product of type SERVICE moves no stock in the sales chain (SG-3, `stockless.py`).* Custom fields live in typed columns, so a list can filter and index on them. A preferred supplier, which reorder orders from (A18). Wave 1-3: principals and brands (MST-1), price revisions with an effective date (MST-2), kits (STK-15), barcode labels (STK-16), discontinued and not-for-sale (STK-17), shelf life (STK-18), codes from a series (MST-5). |
| Units and packaging `app/uom` | 29 | 0 | **Partial** | Conversions drive all seven document types. Packaging levels and barcode lookup have a screen and no seeded rows. |
| Branches and warehouses `app/branches` | 43 *(re-counted 10-03)* | 0 | Built | Imports stage and commit once, so a clash cannot half-apply a file. A branch can carry its own GSTIN, which sets the supplier on its documents and scopes GSTR-1 and 3B (STK-2, A127). |

## Money — the books and the filings

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Finance `app/finance` | 81 *(counted 10-05)* | 7 | **Partial** | *10-05: TDS 194C / 194J settings and proposals beside 194Q (PG-5; D-FIN-25 fixed by `20261005_0323`; the settings card's rate labels and refusals, D-BUY-38, fixed #1175); period-end revaluation of foreign payables (PG-12); 64 control account purposes.* Chart of accounts, years, periods, journals, trial balance, P&L, balance sheet. **Eleven modules post automatically.** Cost and profit centres have screens and a journal-line picker since 2026-09-08; no seeded firm uses them. Wave 1-3: cash flow statement (ACC-9), TDS challans and a supplier's usual TDS section (ACC-7), TDS 194Q (ACC-8), firm bank details with masking (ACC-4), attachments on journals, receipts and payments (ACC-10), the close checklist and ageing settings (ACC-5, ACC-6), Export to Tally (MSG-5). |
| Fixed assets `app/fixed_assets` | 17 *(counted 10-05)* | 1 | Built 2026-10-05 | Asset classes (five seeded), the register, depreciation runs by period pro rata by days, disposal with its gain or loss, a per-asset schedule and the Income-tax block schedule; an asset is raised by a bill line marked capital goods (PG-13, #1138). Accounts > All Accounts screens > Fixed assets. Not built: capitalising goods already in stock, GST on the sale of an asset, an Income-tax book posting. A firm that types its receipts marks the line capital goods on the order or the receipt, and it is received without entering stock (D-BUY-40, fixed #1175, migration `20261005_0326`). Own tests only: not through the full suite, CI or a hand test, and no demo firm uses it. |
| Bank reconciliation `app/bank_reconciliation` | 11 | 0 | Built 2026-10-03 | Statements imported through the shared importer, matched to postings on the bank ledger (auto-match on amount, date within 3 days and reference), and a reconciliation statement as on a date (ACC-1, A125). |
| GST returns `app/gst_returns` | 29 *(re-counted 10-03)* | 0 | Built | *10-05: 3B 4(A)(1) import of goods reads posted Bills of Entry (PG-12); a charge on a sales bill is declared under its own SAC (SG-4).* GSTR-1 and 3B, derived on every read so a cancelled invoice drops out; GST payment; the **tax calendar** on Home with *Mark filed* (`gst_return_filings`); GSTR-2B import and reconciliation, with an optional matched-only claim (A36); rule 37 reversal and reclaim (§78 row 4). No demo firm has imported a 2B. Wave 1-3: filed GSTR-1 kept as a snapshot with amendments (GST-6), quarterly filing and PMT-06 (GST-7), GST checks before filing (GST-5), rule 42 (GST-4; rule 43 open), a GSTIN per branch (STK-2). |
| E-invoicing `app/einvoice` | 20 *(re-counted 10-02)* | 0 | **Partial** | Invoices, credit notes, customer debit notes and sales returns register through the firm's route: **sandbox**, or **offline** (export the portal's bulk-upload JSON, import its result, A42). No B2B document prints or is emailed without its IRN (A43); the 30-day limit and the *To register* list (A44); e-way bills without an IRN, on a challan or by hand, above the firm's limit. Direct NIC and GSP routes are not built. |

## Configuration — how one firm differs from the next

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Business profiles `app/business` | 38 *(re-counted 10-03)* | 0 | **Partial** | **5 features declared** (`ATTACHMENTS`, `VEHICLE_TRACKING`, `DRUG_LICENSE`, `COMMISSION`, `BATCH_PTR_PTS`), all implemented; the other 17 were withdrawn on 2026-10-08 by `20261008_0353` (what goods look like is each product's own switches, filled by its goods type). A profile now decides modules, menus, the five features and the goods types a new firm starts with (see `BUSINESS_PROFILE_FRAMEWORK.md`, which also lists which profiles are now identical). Custom fields extend any module without a migration. Extra fields on six documents (MST-6) and a firm's own custom fields (MST-8); features and modules created at runtime reach every store (MST-7). |
| Tax framework `app/tax` | 54 *(re-counted 10-03)* | 0 | Built | Rules attach to the transaction, never the product. First match wins and evaluation stops. The tax rule that taxed a line is kept on it (GST-8). |
| Document framework `app/document_framework` | 17 | 0 | Built | Types, states, print templates and numbering. A firm administers its own series as of 2026-09-05. |
| Identity and roles `app/identity` | 25 | 0 | Built | 232 permission codes in 38 groups on 2026-10-05 (count `PERMISSION_GROUPS` rather than trusting this), all seeded, and all visible to the guard that checks they are. |
| File imports `app/imports` | 4 *(re-counted 10-02)* | 0 | Built 2026-10-02 | Column mapping for every file import (products, customers, suppliers, opening bills, opening stock), with mappings saved per firm by name (`import_mappings`, B3). The imports themselves stay in their modules on `app/common/file_import.py`. |

## Platform — the parts a firm never sees

| Module | Routes | Reports | State | Notes |
| --- | ---: | ---: | --- | --- |
| Firms and tenancy `app/firms` | 6 | 0 | Built | Shared schema, dedicated schema, or dedicated database — possibly on another server. Provisioning is an explicit action. |
| Audit trail `app/common/audit` | 1 | 0 | Built | Append-only, enforced by a trigger in **every** schema. Per store, so no single query answers "everything that happened". A firm can grant its own trail with `FIRM_AUDIT_LOG_VIEW` (B1). A search box across action, record type and people (PLT-8). |
| Diagnostics `app/diagnostics` | 3 | 0 | Built | A screenshot joins its traceback by request id, and a fault fingerprints on this codebase's frames rather than the ASGI plumbing. Also `agency-server quick-check` (2026-10-02): the read-only sanity check of a running server, module by module (`quick_check.py`, `route_walk.py`). |
| Messaging `app/messaging` | 18 *(re-counted 10-03; same count 10-05)* | 0 | Built 2026-10-01 | *10-05: a purchase order can be sent by WhatsApp on the event `PURCHASE_ORDER_SENT` (PG-7).* Email, WhatsApp and SMS, off until the firm switches it on with its own provider accounts. A failed send never blocks a document. Overdue reminders stop 90 days past due (A12); an invoice email waits for the IRN (A43). Not exercised by any demo firm. Share by hand on WhatsApp, a UPI line, reminders and sending other documents (MSG-1 to MSG-4). Also the lapse of reservations is run from its worker. |
| Notifications `app/notifications` | 2 | 0 | Built 2026-10-03 | The bell: derived on read (orders and bills to approve, sign-offs, requisitions, adjustments, failed messages, stock alerts); only what a person has read is stored (PLT-2, A123). Firm-scoped, not under `/me`. |
| Report layouts `app/report_layouts` | 3 | 0 | Built 2026-10-03 | A person's saved layouts of the analysis screens (RPT-1) beside sales analysis by ordered basis, previous year and margin (RPT-1) and the purchase equivalents (RPT-2, no migration). |
| Global search `app/search` | 1 | 0 | Built | Platform-owned definitions read the platform store; before that every Ctrl+K inside a firm answered 503. |

---

# What is pending, and why

Grouped by what is actually blocking each one. **Three of the four groups are
waiting on a decision rather than on code.**

## Deferred by the owner

Do not start licensing unprompted. The section exists so the thinking does not
have to be redone.

**Emailing a document to the party it names** is no longer deferred: it was
built on 2026-10-01 as `app/messaging` (email, WhatsApp and SMS, off until each
firm switches it on with its own accounts; `docs/MESSAGING_FRAMEWORK.md`). No
demo firm has switched it on, so the sending path runs on tests alone.

**Licensing** (`docs/BACKLOG.md` §2). A `LICENSE_MANAGE` permission, a
`LICENSE_ADMIN` role and a `license_error` code exist and are unused — there is
no model, endpoint or screen. Five questions decide the shape: what is
licensed, what expiry does, phone-home or offline key, who issues one, and what
a firm sees as it approaches the limit.

## Built 2026-10-03, waiting on something outside the code

The Wave 1-3 build (96 items, `docs/BACKLOG_BUILD_PLAN.md` section 4) finished
on 2026-10-03. What it deliberately did **not** build, and what unblocks each
(plan section 5.1):

- **The 26Q FVU text file** -- kept for last by the owner; the TDS registers and
  challans it needs exist (ACC-7).
- **Live e-invoice and e-way bill** through NIC or a GSP; **real messaging
  sends** (the firm's own SMTP, WhatsApp and SMS accounts); **payment links**.
- **A bank's own payment-run layout** (the generic NEFT file is built, BUY-11);
  **rule 43** of the common-credit reversal (GST-4); an inter-GSTIN transfer
  raised as a paired invoice and bill (STK-2).
- **Licensing**, the **clean-machine installer test**, salesman app and
  portals, and **bill of supply**. (Sign-in and branding were built on
  2026-10-04; **import bill of entry**, **RFQ** and **rate contracts** on
  2026-10-05, and came off this list.)

The demo seeders do not drive the new modules above (enquiries, bank
reconciliation, landed costs, principal claims and the rest) yet: they run on
their unit tests and the live checks made while building them. Run
the *which columns does no live row populate?* sweep below on them before
calling any of them proven.

## Built 2026-10-05, not yet proven

The purchasing build (PG-1 to PG-14) and the selling build (SG-1 to SG-9), 23
features, were merged between #1116 and #1168 with #1172 after them. Each was
merged on its own targeted tests. As of this refresh:

- **No full backend or desktop suite and no CI run has been taken over them**,
  and nobody has driven one by hand. The 116 manual cases (TC-BUY-029 to 092,
  TC-SELL-036 to 087 in `docs/qa/`) were written from the code and are unrun.
- **No seeder drives any of them.** `generate_transaction_history.py` names
  their tables only in its reset list (D-CFG-24). Run the *which columns does
  no live row populate?* sweep below on them before calling one proven.
- **Eight defects were found by reading the code while the cases were
  written, and all eight were fixed the same day**: D-SELL-51 and D-SELL-52
  (#1174), D-BUY-35 to D-BUY-40 (#1175). Three found on the way are fixed too:
  D-FIN-25 (#1163), D-CFG-24 and D-BUY-34 (#1172).
- **Five more found while fixing them were fixed the same day** (#1177):
  D-BUY-41 (a debit note or a purchase return against a foreign-currency bill
  posts rupees at the bill's rate), D-CMP-23 (GSTR-2B matching and rule 37
  read rupees), D-BUY-42 (the bill editor starts in its order's currency),
  D-BUY-43 (a supplier rebate counts a foreign bill in rupees) and D-UI-11.
  One is open: D-UI-12, the order editor in a window 600 high.
- **Not built from the same two audits** (§86, §87): recurring bills, job
  work, drop-ship, consignment, supplier credit limit, early-payment discount
  terms, goods in transit, a scheme linked to the customer promotion it funds,
  "10+2" on the print, OCR, emailing an RFQ; and on the selling side van
  sales, export and SEZ, warranty, packing slip, bulk price revision, customer
  item codes, CRM activities, brokers and the rest of §87 rows 10 to 31.

## Waiting on a product decision

**Three features that were not gated are gone (2026-10-08).** `TERRITORY`,
`APPROVAL_WORKFLOW` and `MULTIPLE_WAREHOUSES` were enforced nowhere, so every
firm already used them; `20261008_0353` withdrew the three catalogue rows. Nothing
is left waiting on that decision.

**Three accounting questions deliberately left unanswered.** Each is defensible
as it stands and each would move real money if changed.

1. **Commission is measured on the document total, which includes tax.**
   Changing it moves every payout, past reports included.
2. **`additional_charges` sits outside the tax base.** Right for additions that
   genuinely are outside it; worth confirming against how firms use the field.
   Note that `freight_amount` is deliberately **inside** the base and reaches
   the lines, because a delivery charge is part of the value of the supply.
3. **A loyalty redemption settles the bill rather than discounting it**, so the
   full GST is charged on the supply. Treating it as a discount would reduce
   the taxable value and so the tax collected — a tax decision, and not one a
   module should take quietly.

## Declared, not built

Nothing. The six industry features that carried `is_implemented = false` (`IMEI`,
`PRESCRIPTION_REQUIRED`, `RECIPE_MANAGEMENT`, `KITCHEN_MANAGEMENT`,
`SERVICE_CONTRACTS`, `PROJECT_MANAGEMENT`) were withdrawn from the catalogue on
2026-10-08 by `20261008_0353`, with every profile's mapping to them. All five
features that remain are implemented. The business modules KITCHEN, RECIPES,
PROJECTS and CONTRACTS are untouched.

**A flag recording what the codebase does has to be revisited when the codebase
does it**: `COMMISSION` once outlived its flag (2026-09-03), and nothing but a
survey finds the next one.

## Built, but nothing exercises it

**This is the category that matters most.** Of 182 tables, 42 hold no live row
in any store. Most are attachments and notes nobody wrote, which is fine. These
five are not, and each is a code path the demo cannot reach:

| What | Table | Consequence |
| --- | --- | --- |
| ~~Shortened sales chains~~ | `sales_workflow_settings` | **Seeded 2026-09-08**: FOOD01 leaves the delivery note to the service, so every one of its invoices is billed off the order and `SalesChainService` dispatches the goods. The other three firms still type all four. |
| ~~Credit blocking~~ | `credit_control_settings` | **Seeded 2026-09-08**: every firm has a policy row, MEDI01's is `BLOCK`, and CityMed Clinic sits on a 20,000 limit the history crosses -- the refused approvals appear in the seeder's notes and the orders stay unapproved. |
| ~~Serial numbers~~ | `serial_numbers`, `lots` | **Seeded 2026-09-08**: ELEC01's mixer grinder is serialised and carries up to twenty serials with warranty dates, laid onto the stock the history left. `lots` still holds nothing. |
| ~~Packaging levels~~ | `product_packaging_levels` | **Seeded 2026-09-08**: each firm's first product carries a `Case` level with a barcode. |
| ~~Cost and profit centres~~ | `cost_centers`, `profit_centers` | Screens since 2026-09-08 (Finance › Cost Centres / Profit Centres), the two flags on the chart-of-accounts form, and a picker on a journal line whose account requires one. **Seeded 2026-09-08**: two cost centres, two profit centres and one posted expense journal naming them, per firm. No seeded account requires one, deliberately -- the automatic postings name no centre and would be refused. |

Asking this question — *which columns does no live row populate?* — found four
defects in a single day on 2026-09-04:

- every purchase order carried a **null `buyer_id`**, so the platform-store
  read behind the by-buyer report was exercised by nothing;
- **zero coupons** in any store, so the whole claimed-by-name path was undriven;
- `purchase_return_lines.is_damaged` and `is_expired` false on every row, so
  two shipped reports **could only ever answer an empty grid**;
- a promotion seeded with no conditions matched every line of every document
  and, because a promotion outranks the tiers below it, **silently switched off
  three tiers of the pricing chain** — one line in 58 orders reached any of
  them.

The sweep is worth re-running whenever a feature lands.

---

## Where the ground truth is

Four demo firms trade three financial years across all three tenancy modes:
**MEDI01** and **FOOD01** share `firm_shared`, **WHOLE01** has its own schema,
**ELEC01** its own database. They agree line for line —

```
PO 32 | GRN 30 | PINV 30 | PRET 6 | PROMO 5 | IRN 17 | EWB 8 | QT 29
SO 58 | DN 58 | INV 49 | RCPT 37 | SRET 8 | CN 9 | PF 14 | TGT 2 | PAY 2
```

— which is what makes a divergence a signal worth chasing. WHOLE01 is the one
exception and it is explained: it carries a customer created by hand during
testing with no GST number, so four of its invoices cannot be registered and it
reads `IRN 13 | EWB 6`.

`scripts/verify_sample_data.py` checks five invariants in every store: stock
value against the inventory control account, every accounting period balancing,
customer outstanding against the receivable control account, every settlement
carrying its journal, and every approved invoice having posted. All five pass
in all three stores.

## See also

- `docs/MODULE_REVIEW_CHECKLIST.md` — the per-module review checklist and what
  each review found. 54 rows.
- `docs/BACKLOG.md` — the deferred items in full, with the questions each needs
  answered.
- `docs/SALES_FRAMEWORK.md`, `PURCHASE_FRAMEWORK.md`, `TAX_FRAMEWORK.md`,
  `UOM_FRAMEWORK.md`, `TERRITORY_FRAMEWORK.md`,
  `BUSINESS_PROFILE_FRAMEWORK.md` — the reference for each framework.
- `docs/SALES_TO_RECEIPT_FLOW.md`, `PURCHASE_TO_PAYMENT_FLOW.md` — the ledger
  lines each step of a document chain raises, driven against a running backend.
