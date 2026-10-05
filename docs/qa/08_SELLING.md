# Selling: quotation to cash, returns and credit notes

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > All Sell screens > Documents > Proforma` is a screen that is not
daily work, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-04 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Selling — quotation to cash

| Preparation | Starts you with |
| --- | --- |
| `selling-firm` | customers **`QA-C01` Vijaya** (7.5% standing discount, Retailer segment, **no PAN**) and **`QA-C02` Anand** (Wholesaler, PAN, its own `NEGOTIATED` list at 9.25%); **`QA-DET`** at 84, GST 18 local, 100 in MAIN; the firm-wide **`STANDING`** list on DET with breaks 0 → 2%, 15 → 4.25%, 18 → 6.75%; promotions **BULK5** (7.5% on a line of 25+), **BIGORDER** (200 off a bill of 4,500+, ends the stack), **CLEARANCE** (1% on a line of 40+), **WELCOME** (2.5%, coupon only: `WELCOME10`, `WELCOME10B`); **TCS on** with a threshold of 0 (0.1%, 1% without a PAN) -- which collects nothing on a receipt dated from 1 April 2025, when section 206C(1H) was omitted; loyalty 2 points per 100 |
| `selling-ordered` | … and Vijaya's order for **12** with coupon `WELCOME10`, approved |
| `selling-delivered` | … and notes for **5** and **7**, both dispatched |
| `selling-invoiced` | … and the note for 5 **billed and approved: 483.21** |
| `selling-paid` | … and receipts of **241.60** and **341.61** (241.61 applied), and the note for 7 billed and approved (676.49) |

Sign in as the prepared **Firm admin** unless a case says otherwise.
Quotations, Sales Orders, Delivery Notes and Sales Invoices are on the Sell
menu; Sales Returns and Credit Notes are under Sell > **Returns & notes**;
Proforma is under Sell > All Sell screens > Documents.
A resolved rate is not printed on a saved document: reopen the editor
(**Revise** on a quotation, **Edit** on a draft order) and read the helper
under the blank Discount % box — "Last priced at N% by the price list" (or a
promotion, or the customer's standing rate).

### TC-SELL-001 — The price list's first break outranks a standing discount

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** Sell > Quotations → **New Quotation**: customer `QA-C01`; **Add line** `QA-DET` quantity **12**, Discount % empty (helper: "Blank takes this customer's 7.5%, or a price list where one applies.") → **Create draft** → **Revise**.
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
  1. Sell > Sales Orders → **New Order**: `QA-C01`, ships from MAIN, DET **12**, Discount % blank, **Coupon** `WELCOME10` → **Create draft** → **Edit**.
  2. Replace the coupon with `WELCOME10B` → Save order → Edit.
  3. Coupon `NOSUCHCODE` → Save order → Edit.
- **Expect**
  - Step 1: "Order drafted. Approve it to commit the stock and the credit."; "Last priced at **2.5**% by a promotion" — the coupon's offer **replaces** the list's 2%, it does not compound onto it.
  - Step 2: still **2.5** — a second code on the same offer.
  - Step 3: "Order updated."; the helper falls back to "Last priced at **2**% by the price list". The Coupon helper says "Unrecognised codes are ignored".
### TC-SELL-007 — Approving reserves the stock and claims the offer

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps:** Stock > All Stock screens > Stock > Inventory, filtered to `QA-DET`. Then Reports > Operational → **Promotion claims**.
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
  1. Sell > Delivery Notes → **New** → the order; Delivering **5**, warehouse MAIN → Save → **Approve** → **Dispatch** (an approved note moves nothing). Refresh.
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
  1. Sell > Sales Invoices → **New Invoice** → **Bill this delivery note** → the note for **5** (it reads "dispatched 5 · at 84 less 2.5%"). Type **6** into Bill.
  2. Set Bill back to **5** → **Create draft** → select it → **Approve**.
  3. Accounts > Journal Entries → the invoice's `SI-…` entry → **View**. Masters > Customers → `QA-C01`.
- **Expect**
  - Step 1: refused before sending: "Only 5.0 left to bill." (an API client gets "Invoice quantity exceeds the available source quantity.").
  - Step 2: "Invoice created as a draft. Approve it to post the journal."; **APPROVED**.
  - Step 3: Dr **1100 Trade Receivables 483.21**, Cr **Sales 409.50**, Cr **Output Tax 73.71** — one tax line; the CGST/SGST split is on the invoice. Vijaya's Outstanding **483.21**.
### TC-SELL-012 — Print settings and a printed bill

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps:** select the invoice → **Print settings** icon → How many copies **2**, Copy 1 label / Copy 2 label (they prefill ORIGINAL FOR RECIPIENT / DUPLICATE FOR TRANSPORTER) → save → **Print**.
- **Expect:** the PDF carries the CGST/SGST split, an HSN column, the HSN-wise summary, "AMOUNT CHARGEABLE, IN WORDS", and two labelled copies. Saving print settings needs `SETTINGS_UPDATE`, which the firm admin holds. *(Whichever of the firm's GSTIN, the customer's GSTIN and the product's HSN are blank on your firm print empty on the copy; check the ones that are blank on yours rather than assuming all three are. The prepared product carries no HSN, so that column is always empty here; Vijaya carries no GSTIN either way.)*
### TC-SELL-013 — A receipt collects no TCS from 1 April 2025; an excess with nothing else owed becomes an advance

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps**
  1. Sell > Receipts → **Record Receipt**: `QA-C01`, Amount **241.60**, Bank; under **Apply to invoices** type 241.60 into the invoice's **Apply** box → Record receipt. Masters > Customers → C01.
  2. Record Receipt again: Amount **341.61**, type **241.61** into Apply → Record receipt. Masters > Customers → C01.
- **Expect**
  - Step 1: no TCS is added, although the firm has TCS switched on; the server's reason is "Section 206C(1H) was omitted by the Finance Act 2025 from 1 April 2025, so nothing is collected under it on a receipt from that date." "RC-… recorded and posted to the ledger."; the row reads "Cleared SI-…". Outstanding **241.61** (483.21 − 241.60).
  - Step 2: the running line says 100.00 left over before saving. The invoice drops out of the outstanding list. Customers: Outstanding **0.00** and Advance **100.00** — the excess over everything owed. *(WHOLE01's Vijaya owed on older bills, so there the excess came off the account instead; this firm has none.)*
  - Accounts > Journal Entries: one entry per receipt, **Dr 1010 Bank / Cr 1100 Trade Receivables**, and no `TCS-RC-…` entry.
### TC-SELL-014 — Applying an advance posts nothing; reversing a receipt puts everything back

- **Preconditions:** As *selling-invoiced*, plus the two receipts and the second invoice in the preparation table. (the second receipt has 100.00 unallocated; Vijaya: Outstanding 676.49, Advance 100.00.)
- **Steps**
  1. Sell > Receipts → on the **341.61** receipt, **Apply to an invoice** → the invoice for 7 → Amount **95** → Apply. Then try to apply **10** more.
  2. On the **241.60** receipt → **Reverse**, give a reason → Reverse. Then Reverse it again.
- **Expect**
  - Step 1: "RC-… applied to SI-…"; the dialog says "Nothing moves in the ledger. The money arrived when the receipt was recorded." — Journal Entries has **no** new entry. Customers: Outstanding **581.49**, Advance **5.00** (the net owed is unchanged). Applying 10 more is refused: "RC-… has only 5.00 left unapplied."
  - Step 2: "RC-… reversed."; badge **Reversed**; Journal Entries shows `RC-…-REV`. Outstanding rises by **241.60** to **823.09**; Advance stays 5.00. Reversing again: "RC-… has already been reversed."
### TC-SELL-015 — A sales return is capped at what was dispatched

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps:** Sell > Returns & notes > Sales Returns → **New Return** → Returned against the invoice (entries read "SI-… · date · Vijaya Stores qa") → Line 1 → Taken back into MAIN → Quantity returned **9** → Create draft. Then **2** → Create draft → **Approve** → **Complete**.
- **Expect:** 9 is refused: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5.0000 sent, 0.0000 already returned)."). With 2: "SR-… created as a draft…", "SR-… approved. Nothing has moved yet…", "SR-… completed: 2 back on the shelf and 193.28 credited to the customer." Ledger `SALES_RETURN` +2; Outstanding down **193.28** (2 × 84 less 2.5% plus 18%). Loyalty: the return takes back about **3.87** of the bill's 9.66 points (D-SELL-47); cancelling the return gives them back.
### TC-SELL-016 — A credit note reverses the tax the line was charged, and no more than the line

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps**
  1. Sell > Returns & notes > Credit Notes → **Raise credit note**: the invoice, Line 1, Reason Rate difference, **Credit, before tax** **50** → Raise → row's **Approve**.
  2. Raise again on the same line with **400**.
- **Expect**
  - Step 1: the row reads `59.00 (tax 9.00)` — 18%, the rate that line was charged. "CN-… — approved. The credit and the tax are on the ledger." Outstanding down **59**. Loyalty: about **1.18** of the bill's points come back (D-SELL-47).
  - Step 2: refused: "A credit note cannot credit more than the line was charged: 409.5000 charged, 50.0000 already credited."
### TC-SELL-017 — A proforma posts nothing and does not follow the order afterwards

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Steps**
  1. Sell > All Sell screens > Documents > Proforma → **New** → the prepared order ("SO-… — Vijaya Stores qa — total") → Raise → **Issue**. Journal Entries; Masters > Customers → C01.
  2. Sell > Sales Orders → the order → **Cancel**. Proforma → Refresh → reopen the proforma.
- **Expect**
  - Step 1: "PF-… raised. Issue it when the customer needs it." then "PF-… issued."; a `PF` series number (never `PI`, which purchase invoices use); **nothing** posted; Outstanding unchanged; the pane says "Not a tax invoice — no input tax credit is available against this document."
  - Step 2: the proforma's lines and totals are unchanged — snapshotted when it was raised.
---

### TC-SELL-018 — Why the goods go out, and dispatch before the invoice

- **Preconditions:** As *selling-firm*, plus the order described in the preparation table, approved.
- **Also needs:** *sell-ready*: an approved sales order for 10 of `QA-S` with stock.
- **Steps:** as the prepared **Firm admin**: Settings > Tax > **GST Documents**: leave *Dispatch of a sale before its invoice* at **Warn** → Save. Sell > Delivery Notes → **New** off the order for 2, **Reason** *Sale* → Save → Approve → **Dispatch**. Repeat with **Reason** *Supply on approval*. Then set the policy to **Block** and dispatch a *Sale* note. Then on another approved *Sale* note use **Dispatch and invoice**. Then a note with **Reason** *Other* and no words. Print one challan.
- **Expect:** under Warn, Dispatch on a *Sale* note shows the GST message with **Dispatch and invoice / Dispatch anyway / Cancel**; *Dispatch anyway* dispatches and the audit trail keeps the warning. *Supply on approval* dispatches with no question. Under Block there is no *Dispatch anyway*. **Dispatch and invoice** dispatches the note and creates an **approved** invoice of it in one step ("Dispatched and invoiced as SI-…"); if the invoice is refused (e.g. price below its floor) nothing is dispatched. *Other* without words is refused ("Say why…"). The challan print shows **Reason**. *Van or route sale* dispatches freely unless **Van or route sales need the invoice** is switched on.
### TC-SELL-019 — Choosing batches on a delivery note

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** the product `QA-AMX` in three batches of 10 as in TC-STOCK-005 (one expired, one within 30 days, one later); an approved sales order for 8 of it, and a second one.
- **Steps:** Sell > Delivery Notes → **New** off the order. Look at the side panel's batch list. (a) Change nothing → Save → Approve → **Dispatch**. On a second order: (b) type 8 against the *later* batch and 0 against the earlier → Save → Approve → Dispatch. (c) Split 5 + 3 across the two in-date batches → dispatch → **Print** the challan. (d) Type only 6 in total → Save → Approve → Dispatch. (e) Edit a box, then **Use earliest expiry**.
- **Expect:** every batch is listed nearest expiry first with expiry, days left and *can take*; the expired one is greyed and cannot be typed into; the next one is marked near expiry; the boxes start at the earliest-expiry split. (a) ships the nearest in-date batch, as before. (b) ships the later batch, the earlier one's stock is free again, and the audit trail shows **delivery_note.fefo_skipped** with both splits. (c) the challan prints **two rows** for the line, quantities 5 and 3, values adding up to the line. (d) the panel flags that 6 of 8 are chosen, Save works, and Dispatch is refused. (e) the boxes return to the earliest-expiry split. The near-expiry window is a fixed 30 days and no setting yet asks for a reason on a skip.
### TC-SELL-020 — Charging a customer more after the invoice

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** an approved invoice to a **registered** customer for 10 at 100 + 18% GST (1,180.00), nothing received on it.
- **Steps:** as a **Sales manager** (hire one if the preparation has none): Sell > Returns & notes > **Debit Notes** → **New** → pick the invoice → reason *Price increase* → 100 on its line → watch the tax → **Save**. Try **Approve**. As the **Firm admin**: approve it. Then Sell > Receipts → New for the customer. Then GST Returns → GSTR-1 and GSTR-3B for the month. Then try to cancel the **invoice**. Then record a receipt of 1,250.00 against the invoice and try to cancel the **debit note**.
- **Expect:** the preview shows tax **18.00**, total **118.00** (the invoice line's rate). The sales manager can raise but is not offered **Approve**. After approval the customer's balance is **118.00** higher, and Record Receipt lists the invoice at **1,298.00** owing, one row not two. GSTR-1 CDNR shows the note as type **D** against the invoice, taxable 100, CGST 9 + SGST 9; GSTR-3B 3.1(a) is 100 higher. Cancelling the invoice is refused naming the debit note. With 1,250.00 received, cancelling the debit note is refused ("Money received on invoice SI-… has already met 70.00 of this debit note. Reverse that receipt first, then cancel the note."); after reversing the receipt it cancels and the balance drops back. A customer debit note prints (A4, its own **Print**).
### TC-SELL-021 — Rate includes GST on an order and a quotation

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**, Sell > Quotations → **New** for `QA-C01`. Switch **Rate includes GST** on, type a rate of **118** on a line taxed at 18%, with quantity 10 → Save. Reopen it, then **Print**. Convert it to a sales order and open the order. Then Settings > Selling > **Sales Stages** → *Rates typed on a bill include GST* on → Save, and start another new sales order.
- **Expect:** while the switch is on the Rate column is labelled as the shelf price and the totals show a taxable value of 1,000.00 with 180.00 tax, total 1,180.00. Reopening shows 118 as typed; the print shows both rates. The order opens with the switch **on** and the same typed rate, and the customer is billed what was quoted. A bill raised from the order prints only the pre-tax rate. A new order starts with the switch on only after the setting is saved; an order made by converting a quotation never reads the setting a second time.
### TC-SELL-022 — Batch rules: near expiry, a reason, and the price floor

*Added 2026-10-02 (backlog 79 row 6, A2).*

- **Preconditions:** the shop from TC-SELL-019 (a batch expiring within 30 days and a later one, 10 each). The product's **minimum selling price** 150. Settings > Selling > **Price Floor**: *Block*.
- **Steps:** Settings > Stock > **Batch Rules**: note the defaults, then set *A near-expiry batch leaving* to **Need a reason** → Save. (a) A sales order for 2 at **100** → Approve. (b) A sales order for 15 at 100 → Approve. (c) A delivery note off order (a), batches untouched → Save → Approve → **Dispatch**; cancel the reason prompt; Dispatch again and give *Short-dated stock cleared*. (d) Set *FEFO skip* to **Need a reason**; a note choosing the *later* batch → Dispatch. (e) Untick *may be sold below the price floor* → repeat (a).
- **Expect:** the defaults read 30 days, Warn, Record, ticked. (a) approves although 100 is below 150; its timeline names the near-expiry batch. (b) is refused below the minimum price when the order is **approved**, not when it is saved, and the message quotes the rate after any standing discount -- 15 takes the later batch too, which is fresh stock. (c) the prompt names the line and the near-expiry batch; cancelling dispatches nothing; with the reason it dispatches and Settings > Platform > System > Audit Logs shows **delivery_note.near_expiry_dispatched** with the reason. (d) asks for a reason before dispatching; **delivery_note.fefo_skipped** keeps it. (e) is refused like (b).

### TC-SELL-023 — Choosing batches on a counter bill

*Added 2026-10-02 (backlog 79 row 2).*

- **Preconditions:** a firm with the delivery note stage **off** (Settings > Selling > Sales Stages). A batch-tracked product with two in-date batches, an earlier and a later expiry, 10 each, in the default warehouse.
- **Steps:** Sell > Sales Invoices > **+ New by product** (the counter bill): the product, quantity 4. Open the line's batches: note the pre-fill. Put 4 on the **later** batch → Save → reopen the draft and look at the batches → change to 1 earlier + 3 later → Save → **Approve**. Then a second bill of 4 with the batches untouched → Approve.
- **Expect:** the picker lists both batches with expiry and days left, the earlier one pre-filled with 4. The saved draft shows 4 on the later batch. After approval, stock of the earlier batch is down by 1 and the later by 3 (Stock > Batches), and Settings > Platform > System > Audit Logs shows **delivery_note.fefo_skipped**. The untouched bill draws 4 from the earlier batch, as before.

### TC-SELL-024 — A customer's minimum shelf life

*Added 2026-10-02 (backlog 79 row 6).*

- **Preconditions:** a firm whose business profile has expiry tracking. A batch-tracked product with a batch expiring in about 4 months and one in about 9 months, 10 each. A customer with **Minimum shelf life** 180 days (Masters > Customers → edit). An approved sales order of 8 for that customer.
- **Steps:** (a) Sell > Delivery Notes → New off the order, batches untouched → Save → Approve → **Dispatch**. (b) A second order and note: open the batch picker. (c) Put 8 on the 4-month batch → Save → Approve → Dispatch. (d) Settings > Stock > **Batch Rules**: *short of the customer's minimum shelf life* → **Warn** → Save, and dispatch (c) again.
- **Expect:** (a) ships the **9-month** batch -- the 4-month one is passed over without anybody choosing. (b) the 4-month batch carries **Too short for customer** and the pre-fill is on the 9-month one. (c) Dispatch is refused with a message naming the batch and the customer's minimum; no reason prompt is offered. (d) it dispatches, and Settings > Platform > System > Audit Logs shows **delivery_note.short_shelf_life_dispatched**.

### TC-SELL-025 — Pinning the batch a customer asked for

*Added 2026-10-02 (backlog 79 row 4).*

- **Preconditions:** a batch-tracked product with an earlier and a later in-date batch, 10 each, and one expired batch with stock.
- **Steps:** Sell > Sales Orders → New: 5 of the product, **Batch** = the later batch → Save → Approve. Stock > Batches. Sell > Delivery Notes → New off the order → look at the batch picker → Approve → Dispatch. Then an order for 12 pinning the later batch → Approve. Then an order pinning the expired batch → Approve.
- **Expect:** approval holds 5 of the **later** batch and nothing of the earlier. The note opens with 5 on the later batch, and dispatch ships it (audit trail: **delivery_note.fefo_skipped**). The order for 12 holds 10 of the later batch and leaves 2 as a back order -- the earlier batch stays free. Pinning the expired batch is refused at approval naming it.

### TC-SELL-026 — A batch's own MRP

*Added 2026-10-02 (backlog 79 row 7, A41).*

- **Preconditions:** a batch-tracked product; the delivery note stage off (counter bills).
- **Steps:** Goods Receipt for the product: batch `B1`, **MRP** 120, **Selling price** 95; a second line batch `B2`, MRP 100. Complete it. Settings > Stock > Batch Rules: tick *Take a line's rate from its batch's selling price*. Counter bill: the product, 4, choose `B1` → look at the rate → Save → Approve → **Print**. Then a counter bill of 4 from `B2` at rate **110** (no tax) → Approve.
- **Expect:** the batch screen shows B1 at MRP 120 / 95 and B2 at 100. The picker lists each batch's MRP. Choosing B1 fills the rate **95**. The printed bill has an **MRP** column, 120 on the B1 row. The B2 bill at 110 is refused, quoting the rate **with tax**: on a product taxed at 18%, "charges 129.80 a unit with tax, above the MRP of 100.00 printed on the batch it ships" (110.00 only where the product carries no tax).
---

### TC-SELL-027 — Several delivery notes on one bill: customer first

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Also needs:** a second customer with one dispatched, unbilled delivery note; for the clash, a third dispatched note for Vijaya that names a **different salesman** from the notes of 5 and 7 (set the salesman on the order it came from). For the supplier half, `po-received` (receipts of 4 and 6).
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → New → bill from delivery notes. (a) Look at the first question asked. Pick Vijaya. (b) Tick the notes of 5 and 7 → create the draft. (c) Start again and also try to tick the third note. (d) Start again and pick the second customer. Then Buy > **Purchase Invoices** → New → from receipts: pick the supplier and tick the receipts of 4 and 6.
- **Expect:** (a) the editor asks for the **customer** first and lists only customers that have notes left to bill. Vijaya opens a tick list: number, date, order and the amount left to bill before tax. (b) the two notes can be ticked together and make one draft bill. (c) the third note cannot be ticked beside notes of another salesman, and says which field it clashes on (the server names the field -- "All source documents must belong to the same salesman." -- and not the note; a note that names nobody never clashes); the same holds for branch, territory or route. (d) a customer with a single note has it ticked already, without being asked. The supplier bill asks for the **supplier** first and lists that supplier's receipts; the only field a receipt can clash on is the branch.
### TC-SELL-028 — An enquiry becomes a customer and a quotation

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the product `QA-DET`; a role holding SALES_VIEW, SALES_QUOTATION_CREATE and SALES_UPDATE (the firm administrator does).
- **Steps:** as the prepared **Firm admin**: Sell > All Sell screens > Documents > **Enquiries** → New. Type a **prospect** (name, company, phone in the form +91…, email, city) instead of picking a customer; source, salesman, expected value, expected close date, next follow-up date; one line for `QA-DET` × 10 and a second line with a description only. Save. (a) Try **Convert to quotation**. (b) Give the second line a product and convert again. (c) Open the new quotation and convert it to a sales order. (d) Raise a second enquiry for a prospect, add a follow-up note with a new next date, then mark it **Lost** with a reason from the list. (e) Open the **Follow-ups due** view; then Reports > Operational → **Enquiries lost**.
- **Expect:** the enquiry is numbered **ENQ-…** and opens as new. (a) conversion is refused while a line has no product. (b) a customer is created from the prospect (code from the customer series, the firm's currency) and a draft quotation with the lines; the enquiry shows the quotation and the customer. (c) once the order is made the enquiry reads **WON**. (d) the follow-up is kept with its date and the enquiry's next follow-up moves; Lost needs a reason chosen from a fixed list. (e) the due view lists enquiries whose next follow-up is today or earlier and not closed; the lost report counts the lost enquiries and totals their expected value by reason. There is no Home gadget and no reminder yet.
### TC-SELL-029 — Counter billing with a barcode scanner and a split of tenders

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** `QA-DET` given a barcode (Masters > Products → the product → barcode); a USB scanner in keyboard mode, or type the barcode and press Enter; a thermal printer or the PDF preview.
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → New by product for Vijaya. Click the **scan field**, scan `QA-DET`, scan it again. Add a split of tenders: part **Cash**, the rest **UPI**; then give more cash than the balance. Press **Save & print (F9)**. Then try a tender total above the bill by editing it and saving.
- **Expect:** the first scan adds a line, the second raises its quantity by 1. The tender panel shows the balance and, for cash over the balance, the change to give back. F9 saves, approves, prints the thermal bill and opens the next blank bill. The bill shows as paid: one receipt per tender is recorded, cash into the cash book, UPI through the bank with mode UPI, each allocated to the bill. A tender total above the bill saves as a draft and is refused when the bill is **approved**: "600.00 was received against a bill of 472.0000. Enter what the bill is paid with; change is handed back." Receipts appear under Sell > **Receipts**.
### TC-SELL-030 — Picking list and loading sheet

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Steps:** as the prepared **Firm admin**: Sell > **Delivery Notes**; tick both notes (5 and 7) → **Pick list**. Then with the same ticks → **Loading sheet**. Try the buttons with nothing ticked, and as a role without SALES_VIEW.
- **Expect:** each button gives an A4 PDF. The pick list sums the ticked notes **by product** (12 of `QA-DET`, free goods included, in stock units), by batch where a note chose one and "earliest expiry first" where it left the batch to dispatch. The loading sheet has one drop per note in the order the round visits the customers, with the note's value and what its bills still owe. Nothing is written: the notes are unchanged. With nothing ticked the buttons are disabled or the request is refused by name.
### TC-SELL-031 — Cash discount for early payment, and interest on overdue bills

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** the invoice of 483.21 nothing has been received on; an invoice that is already past its due date (back-date one, or use the due date on the bill).
- **Steps:** as the prepared **Firm admin**: Masters > **Customers** → Vijaya → terms → cash discount **2% within 10 days**. Settings > Selling > **Credit Control** → set an overdue interest rate (say 18% a year) and a grace of 5 days → Save. Sell > **Receipts** → Record Receipt for Vijaya on the day of the invoice. Then open **Customer Statements** for a customer with an overdue bill and press **Raise interest debit note**. Then clear the customer's own discount days and look again.
- **Expect:** Record Receipt prefills the discount allowed (2% of what the bill still owes) while the bill is inside its 10 days, and not after; accepting it posts the discount as *Discount Allowed* and leaves the bill's tax alone. A customer with no days of their own takes the firm's terms; zero days refuses a discount. The statement shows the interest accrued on each overdue bill at the yearly rate (365-day year) for the days past due once the grace days have run. *Raise interest debit note* makes a **draft** customer debit note with the reason *Late payment interest*, taxed at the bill's own rates; interest is only charged when somebody raises it. A receipt, credit note or return changes the figures at once. Raising the note needs CUSTOMER_DEBIT_NOTE_MANAGE.
### TC-SELL-032 — A new outlet waits for office approval

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a **Field Sales** user (SALES_EXECUTIVE) beside the firm administrator.
- **Steps:** as the **Firm admin**: Settings > Selling > **Sales Stages** → switch on *New outlets need approval* → Save. As the **Field Sales** user: Masters > **Customers** → New, save. Try to raise a quotation, an order, and a bill for it; try to change its status. Sign in as the **Firm admin**: filter the list by **Pending approval**, tick the new customer → **Approve**; also tick two more pending ones → **Approve** (bulk). Switch the setting off and create another customer as the field user.
- **Expect:** the field user's new customer is saved with status **Pending approval** (badge in the list; a filter finds it) and a bill for it is refused when it is raised, naming the reason ("… is a new outlet waiting for approval, so it cannot be billed yet. Its orders are kept; approve the customer to bill them."); quotations and orders for it are still accepted and kept; the field user cannot move it on. The administrator's Approve (single and bulk) activates it, after which it can be billed. With the setting off a non-approver's new customer starts active. Approving needs CUSTOMER_APPROVE.
### TC-SELL-033 — Named price levels, and a customer's own level

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Price Levels** → New *Dealer* and *Retail*. Masters > Products → `QA-DET` → price levels → Dealer 70, Retail 90. Masters > Customers → Anand → Price level *Dealer* (and, separately, a customer **group** with level *Retail*, Vijaya in it). Sell > **Quotations** → New for Anand: add DET and leave **Unit price** blank. Repeat for Vijaya. Then add a price list that has a **Rate** for DET and repeat for Anand.
- **Expect:** the blank price is filled with the customer's level rate (Dealer 70 for Anand, the group's Retail 90 for Vijaya — the customer's own level wins over the group's) before the GST-inclusive conversion; lines the server filled are not converted again. A price list **Rate** wins over the level, and the level wins over the product's own price. The same holds on a sales order. A typed unit price is kept as typed.
### TC-SELL-034 — A UPI QR on the invoice, and sharing it on WhatsApp by hand

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** the approved invoice of 483.21 for Vijaya, who has a phone number; a browser or WhatsApp installed for the wa.me link. No messaging account is needed.
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → Print settings → UPI ID `shop@upi` → Save; try `shop` alone. Print the approved invoice (A4, then the 80 mm roll). Receive part of the bill, print again; receive the rest, print again. Select the approved invoice → **WhatsApp**. Look at Vijaya's timeline.
- **Expect:** the UPI ID must look like `name@handle`. A bill that stands and still owes money prints *Scan to pay by UPI*: a QR with the payee, the amount still owing, INR and the bill number, plus the amount and the UPI ID beside it, in the A4 footer and under the total on the roll. A part-paid bill asks only for the rest; a paid one prints none; a draft or cancelled bill prints none. *WhatsApp* saves the PDF in Downloads, opens the folder with the file selected and opens WhatsApp web (wa.me) with the covering note (and the UPI line); the bill's timeline reads *WhatsApp shared by hand to …* and never "sent".
### TC-SELL-035 — Payment reminders and other documents sent by hand

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** Settings > Firm > **Messaging** switched on with an email account for the firm (see the messaging setup guide) for the email halves; a customer who owes nothing; a customer set to *No reminders*; a quotation, a sales order, a receipt and a purchase order.
- **Steps:** as the prepared **Firm admin**: Sell > **Customer Statements** → Vijaya → **Remind**; choose email. Then select the approved invoice → **Remind** → WhatsApp. Try Remind for the customer who owes nothing and for the *No reminders* customer. Then use **Send** (email) on a quotation, a sales order, a receipt and a purchase order; print the order and the receipt.
- **Expect:** the reminder sends the customer's **statement of account** as a PDF: the movement from the oldest unpaid bill to today, the closing balance, the unpaid bills with days overdue, and the UPI line where it applies. Email queues an outbox row and the worker sends it; WhatsApp opens WhatsApp web (wa.me) as in TC-SELL-034 and is recorded in the customer's audit trail. A customer who owes nothing and one marked *No reminders* are refused by name on both roads. The five documents send by email with a covering note and the PDF rendered at send time; a cancelled document or a reversed receipt is refused. The order and the receipt each have a Print (the receipt on A5).

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 08-S01 | **Sell > Quotations** | Offered to any role holding `SALES_VIEW` or `SALES_QUOTATION_CREATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S02 | **Sell > Sales Orders** | Offered to any role holding `SALES_VIEW` or `SALES_CREATE` or `SALES_UPDATE` or `SALES_IMPORT` or `SALES_EXPORT` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S03 | **Sell > Delivery Notes** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S04 | **Sell > Sales Invoices** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S05 | **Sell > Returns & notes > Sales Returns** | Offered to any role holding `SALES_VIEW` or `SALES_RETURN` or `SALES_UPDATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S06 | **Sell > All Sell screens > Documents > Proforma** | Offered to any role holding `PROFORMA_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S07 | **Sell > Returns & notes > Credit Notes** | Offered to any role holding `CREDIT_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
