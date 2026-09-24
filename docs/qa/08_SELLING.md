# Selling: quotation to cash, returns and credit notes

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Selling — quotation to cash

| Preparation | Starts you with |
| --- | --- |
| `selling-firm` | customers **`QA-C01` Vijaya** (7.5% standing discount, Retailer segment, **no PAN**) and **`QA-C02` Anand** (Wholesaler, PAN, its own `NEGOTIATED` list at 9.25%); **`QA-DET`** at 84, GST 18 local, 100 in MAIN; the firm-wide **`STANDING`** list on DET with breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; promotions **BULK5** (7.5% on a line of 25+), **BIGORDER** (200 off a bill of 4,500+, ends the stack), **CLEARANCE** (1% on a line of 40+), **WELCOME** (2.5%, coupon only: `WELCOME10`, `WELCOME10B`); **TCS on** with a threshold of 0 (0.1%, 1% without a PAN); loyalty 2 points per 100 |
| `selling-ordered` | … and Vijaya's order for **12** with coupon `WELCOME10`, approved |
| `selling-delivered` | … and notes for **5** and **7**, both dispatched |
| `selling-invoiced` | … and the note for 5 **billed and approved: 483.21** |
| `selling-paid` | … and receipts of **241.60** and **341.61** (241.61 applied), and the note for 7 billed and approved (676.49) |

Sign in as the prepared **Firm admin** unless a case says otherwise.
Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sales Returns are
sidebar entries of their own; Credit Notes and Proforma are under **Sales**.
A resolved rate is not printed on a saved document: reopen the editor
(**Revise** on a quotation, **Edit** on a draft order) and read the helper
under the blank Discount % box — "Last priced at N% by the price list" (or a
promotion, or the customer's standing rate).

### TC-SELL-001 — The price list's first break outranks a standing discount

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Quotations → **New Quotation**: customer `QA-C01`; **Add line** `QA-DET` quantity **12**, Discount % empty (helper: "Blank takes this customer's 7.5%, or a price list where one applies.") → **Create draft** → **Revise**.
- **Expect:** "QT-… drafted, good until … Nothing is reserved by it." Under the blank box: "Last priced at **2**% by the price list." — STANDING's first break beats Vijaya's 7.5% standing rate.
### TC-SELL-002 — A ladder takes the highest break at or below the quantity

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** a quotation for `QA-C01`, DET quantity **18**, Discount % empty → Create draft → Revise.
- **Expect:** "Last priced at **6.75**% by the price list" — the break at 18, not the first one above zero. Revising 12 → 18 on one quotation and saving gives the same, because a revision prices resolved lines afresh.
### TC-SELL-003 — A customer's own list replaces the firm-wide ladder

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** a quotation for `QA-C02` (Anand), DET quantity **18** → Create draft → Revise.
- **Expect:** "Last priced at **9.25**% by the price list" — Anand's `NEGOTIATED` list replaces STANDING rather than amending it.
### TC-SELL-004 — A promotion outranks both lists; a typed zero refuses them all

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps**
  1. A quotation for `QA-C02`, DET quantity **30** → Create draft → Revise.
  2. Revise: type **0** in Discount % → Save revision → Revise.
- **Expect**
  - Step 1: "Last priced at **7.5**% by a promotion" — BULK5 applies at 25+ and a promotion outranks either list.
  - Step 2: the box itself reads **0** (a typed rate is kept) and the line total is the full 30 × 84 = 2,520 before tax. Zero is a refusal of every arrangement, not a silence.
### TC-SELL-005 — An accepted quotation converts once

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** a quotation for `QA-C02`, DET 12 → Create draft → **Mark as sent** → **Customer accepted** (give a reason) → **Convert to order**. Then look for Convert again.
- **Expect:** toasts "QT-… marked as sent…", "QT-… accepted. Converting it is what creates the order.", "QT-… became SO-…. The order reserves the stock when it is approved." Afterwards **no Convert to order**. **(HTTP)** `POST /api/v1/quotations/{id}/convert` with `{"order_date": "<today>"}` → **422**, "Quotation QT-… already became SO-….".
### TC-SELL-006 — A coupon reaches its offer; a code nobody recognises gives nothing and refuses nothing

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps**
  1. Sales Orders → **New Order**: `QA-C01`, ships from MAIN, DET **12**, Discount % blank, **Coupon** `WELCOME10` → **Create draft** → **Edit**.
  2. Replace the coupon with `WELCOME10B` → Save order → Edit.
  3. Coupon `NOSUCHCODE` → Save order → Edit.
- **Expect**
  - Step 1: "Order drafted. Approve it to commit the stock and the credit."; "Last priced at **2.5**% by a promotion" — the coupon's offer **replaces** the list's 2%, it does not compound onto it.
  - Step 2: still **2.5** — a second code on the same offer.
  - Step 3: "Order updated."; the helper falls back to "Last priced at **2**% by the price list". The Coupon helper says "Unrecognised codes are ignored".
### TC-SELL-007 — Approving reserves the stock and claims the offer

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps:** Inventory → Stock → Inventory, filtered to `QA-DET`. Then Reports → Operational Reports → **Promotion claims**.
- **Expect:** MAIN: Current **100**, Reserved **12**, Available **88**. The claims report lists `WELCOME`, coupon `WELCOME10`, Vijaya, the order, **CLAIMED** (it was PENDING while a draft; only a claim at approval counts against a limit).
### TC-SELL-008 — A hold stops a delivery; releasing restores the status it had

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps**
  1. Select the prepared order → **Hold**, reason `awaiting cheque` → Hold. Then Delivery Notes → **New** → that order → **Save Delivery Note**.
  2. Select the order → **Release**.
- **Expect**
  - Step 1: "SO-… is on hold."; Status **APPROVED (on hold)**. The note is refused **on save**: "SO-… is on hold and cannot be dispatched ("awaiting cheque"). Release it first." Reserved stays **12** — a hold says "not yet", not "never".
  - Step 2: "SO-… released."; Status plain **APPROVED** — the status it had, not a reset.
### TC-SELL-009 — Part deliveries move the order's status

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps**
  1. Delivery Notes → **New** → the order; Delivering **5**, warehouse MAIN → Save → **Approve** → **Dispatch** (an approved note moves nothing). Refresh.
  2. New again: Delivering defaults to the remaining **7** → Save, Approve, Dispatch, Refresh.
- **Expect**
  - Step 1: "Delivery note DN-… created as a draft. Dispatching it is what moves the stock."; the note **DISPATCHED**; the order **PARTIALLY_DELIVERED**; MAIN on hand **95**, Reserved **7**; ledger `DISPATCH` −5; Journal Entries has the note's cost-of-goods entry.
  - Step 2: the order **DELIVERED** (only once both notes are dispatched); ledger `DISPATCH` −7; Reserved **0**, on hand **88**.
### TC-SELL-010 — A delivery ships the deal the order struck

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Steps:** open the note for 5 and read its line's Unit Price and discount; open the order and compare.
- **Expect:** **identical** — 84 less 2.5%, from the coupon on the order. The note does not re-read the customer's current rate or price list.
### TC-SELL-011 — Billing a note: the cap, the approval and its journal

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Steps**
  1. Sales Invoices → **New Invoice** → **Bill this delivery note** → the note for **5** (it reads "dispatched 5 · at 84 less 2.5%"). Type **6** into Bill.
  2. Set Bill back to **5** → **Create draft** → select it → **Approve**.
  3. Finance → Journal Entries → the invoice's `SI-…` entry → **View**. Masters → Customers → `QA-C01`.
- **Expect**
  - Step 1: refused before sending: "Only 5.0 left to bill." (an API client gets "Invoice quantity exceeds the available source quantity.").
  - Step 2: "Invoice created as a draft. Approve it to post the journal."; **APPROVED**.
  - Step 3: Dr **1100 Trade Receivables 483.21**, Cr **Sales 409.50**, Cr **Output Tax 73.71** — one tax line; the CGST/SGST split is on the invoice. Vijaya's Outstanding **483.21**.
### TC-SELL-012 — Print settings and a printed bill

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps:** select the invoice → **Print settings** icon → How many copies **2**, Copy 1 label / Copy 2 label (they prefill ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER) → save → **Print**.
- **Expect:** the PDF carries the CGST/SGST split, an HSN column, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and two labelled copies. Saving print settings needs `SETTINGS_UPDATE`, which the firm admin holds. *(The prepared firm and customer carry no GSTIN and the product no HSN, so those cells print empty; QA01's did.)*
### TC-SELL-013 — Receipts charge TCS; an excess with nothing else owed becomes an advance

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps**
  1. Finance → Receipts → **Record Receipt**: `QA-C01`, Amount **241.60**, Bank; under **Apply to invoices** type 241.60 into the invoice's **Apply** box → Record receipt. Customers → C01.
  2. Record Receipt again: Amount **341.61**, type **241.61** into Apply → Record receipt. Customers → C01.
- **Expect**
  - Step 1: the TCS notice (small text under **Against order (optional)**) charges **1%** — Vijaya has no PAN — **2.42** on 241.60. "RC-… recorded and posted to the ledger."; the row reads "Cleared SI-…". Outstanding **244.03** (483.21 − 241.60 + 2.42).
  - Step 2: TCS **3.42**; the running line says 100.00 left over before saving. The invoice drops out of the outstanding list. Customers: Outstanding **3.42** (this receipt's TCS) and Advance **97.58** — the excess over everything owed. *(QA01's Vijaya owed on older bills, so there the excess came off the account instead; this firm has none.)*
### TC-SELL-014 — Applying an advance posts nothing; reversing a receipt puts everything back

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table. (the second receipt has 100.00 unallocated; Vijaya: Outstanding 679.91, Advance 97.58.)
- **Steps**
  1. Finance → Receipts → on the **341.61** receipt, **Apply to an invoice** → the invoice for 7 → Amount **97.58** → Apply. Then try to apply **5** more.
  2. On the **241.60** receipt → **Reverse**, give a reason → Reverse. Then Reverse it again.
- **Expect**
  - Step 1: "RC-… applied to SI-…"; the dialog says "Nothing moves in the ledger. The money arrived when the receipt was recorded." — Journal Entries has **no** new entry. Customers: Outstanding **584.75**, Advance **2.42** (the net owed is unchanged). Applying 5 more is refused: "RC-… has only 2.42 left unapplied."
  - Step 2: "RC-… reversed."; badge **Reversed**; Journal Entries shows `RC-…-REV` and the receipt's TCS reversed. Outstanding rises by **239.18** — the 241.60 less the 2.42 TCS that is also undone. Reversing again: "RC-… has already been reversed."
### TC-SELL-015 — A sales return is capped at what was dispatched

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps:** Sales Returns → **New Return** → Returned against the invoice (entries read "SI-… · date · Vijaya Stores qa") → Line 1 → Taken back into MAIN → Quantity returned **9** → Create draft. Then **2** → Create draft → **Approve** → **Complete**.
- **Expect:** 9 is refused: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5.0000 sent, 0.0000 already returned)."). With 2: "SR-… created as a draft…", "SR-… approved. Nothing has moved yet…", "SR-… completed: 2 back on the shelf and 193.28 credited to the customer." Ledger `SALES_RETURN` +2; Outstanding down **193.28** (2 × 84 less 2.5% plus 18%).
### TC-SELL-016 — A credit note reverses the tax the line was charged, and no more than the line

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps**
  1. Sales → Credit Notes → **Raise credit note**: the invoice, Line 1, Reason Rate difference, **Credit, before tax** **50** → Raise → row's **Approve**.
  2. Raise again on the same line with **400**.
- **Expect**
  - Step 1: the row reads `59.00 (tax 9.00)` — 18%, the rate that line was charged. "CN-… — approved. The credit and the tax are on the ledger." Outstanding down **59**.
  - Step 2: refused: "A credit note cannot credit more than the line was charged: 409.5000 charged, 50.0000 already credited."
### TC-SELL-017 — A proforma posts nothing and does not follow the order afterwards

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps**
  1. Sales → Proforma → **New** → the prepared order ("SO-… — Vijaya Stores qa — total") → Raise → **Issue**. Journal Entries; Customers → C01.
  2. Sales Orders → the order → **Cancel**. Proforma → Refresh → reopen the proforma.
- **Expect**
  - Step 1: "PF-… raised. Issue it when the customer needs it." then "PF-… issued."; a `PF` series number (never `PI`, which purchase invoices use); **nothing** posted; Outstanding unchanged; the pane says "Not a tax invoice — no input tax credit is available against this document."
  - Step 2: the proforma's lines and totals are unchanged — snapshotted when it was raised.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 08-S01 | **Quotations** | Offered to any role holding `SALES_VIEW` or `SALES_QUOTATION_CREATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S02 | **Sales Orders** | Offered to any role holding `SALES_VIEW` or `SALES_CREATE` or `SALES_UPDATE` or `SALES_IMPORT` or `SALES_EXPORT` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S03 | **Delivery Notes → Delivery Notes** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S04 | **Sales Invoices → Sales Invoices** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S05 | **Sales Returns** | Offered to any role holding `SALES_VIEW` or `SALES_RETURN` or `SALES_UPDATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S06 | **Sales → Proforma** | Offered to any role holding `PROFORMA_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S07 | **Sales → Credit Notes** | Offered to any role holding `CREDIT_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
