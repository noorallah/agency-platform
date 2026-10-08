# Selling: quotation to cash, returns and credit notes

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
  - Step 3: Dr **1100 Trade Receivables 483.21**, Cr **4000 Sales 409.50**, Cr **2220 Output CGST 36.86**, Cr **2230 Output SGST 36.85**. Vijaya's Outstanding **483.21**.
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
- **Expect:** 9 is refused: "Only 5.0 went out on this line." (server: "Return quantity exceeds what was dispatched on the source document (5 sent, 0 already returned)."; where the line names a unit, "(5 PIECE sent, 0 PIECE already returned)"). With 2: "SR-… created as a draft…", "SR-… approved. Nothing has moved yet…", "SR-… completed: 2 back on the shelf and 193.28 credited to the customer." Ledger `SALES_RETURN` +2; Outstanding down **193.28** (2 × 84 less 2.5% plus 18%). A return against a delivery note nobody was billed for moves stock and cost only: no `SR-…` credit journal, no receivable row, `unbilled_quantity` on the line, and the note's left-to-bill reduced. On a part-billed note the unbilled part is taken first (4 delivered, 3 billed, 2 back: 1 credited). TC-SELL-094 walks both.
- **Reports:** Reports > Operational → **Sales return register** values a return at what was credited: it shows the credited amount (`credited_amount`) and the unbilled quantity (`unbilled_quantity`) beside the document total, and by customer, by product and the summary add up the credited figure. The summary's **total return value** counts only completed returns and equals the register's credited total; a draft or approved return adds its stated total to **pending return value** and nothing to the total, and completing it moves what it credited across (nothing, for a return never billed). The summary counts no header charge or rounding of a return that credited nothing. A return raised against a delivery note of a billed supply names that bill under *Against invoice* in the GST sales register and in GSTR-1 CDNR.
- **Loyalty (D-SELL-47, 2026-10-05):** the return takes back the points the bill earned on the value returned — about **3.87** of the bill's 9.66 (193.28 of 483.21) — a `REVERSED` row in `loyalty_entries` naming the return, with a journal Dr 2600 / Cr 5700. Cancelling the return gives them back.
### TC-SELL-016 — A credit note reverses the tax the line was charged, and no more than the line

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Steps**
  1. Sell > Returns & notes > Credit Notes → **Raise credit note**: the invoice, Line 1, Reason Rate difference, **Credit, before tax** **50** → Raise → row's **Approve**.
  2. Raise again on the same line with **400**.
- **Expect**
  - Step 1: the row reads `59.00 (tax 9.00)` — 18%, the rate that line was charged. "CN-… — approved. The credit and the tax are on the ledger." Outstanding down **59**.
  - Step 2: refused: "A credit note cannot credit more than the line was charged: 409.50 charged, 50.00 already credited."
- **Loyalty (D-SELL-47, 2026-10-05):** approving takes back about **1.18** of the bill's 9.66 points (59.00 of 483.21); cancelling the note gives them back.
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

- **Preconditions:** A firm on the **Pharmacy** profile, with a batch-tracked product in two batches with different expiry dates, and two orders for it.
- **Also needs:** the product `QA-AMX` in three batches of 10 as in TC-STOCK-005 (one expired, one within 30 days, one later); an approved sales order for 8 of it, and a second one.
- **Steps:** Sell > Delivery Notes → **New** off the order. Look at the side panel's batch list. (a) Change nothing → Save → Approve → **Dispatch**. On a second order: (b) type 8 against the *later* batch and clear the earlier → Save → Approve → Dispatch. (c) Split 5 + 3 across the two in-date batches → dispatch → **Print** the challan. (d) Type only 6 in total → Save → Approve → Dispatch. (e) Edit a box, then **Use earliest expiry**.
- **Expect:** every batch is listed nearest expiry first with expiry, days left and *can take*; the expired one is greyed and cannot be typed into; the next one is marked near expiry; the boxes start at the earliest-expiry split. (a) ships the nearest in-date batch, as before. (b) ships the later batch, the earlier one's stock is free again, and the audit trail shows **delivery_note.fefo_skipped** with both splits. (c) the challan prints **two rows** for the line, quantities 5 and 3, values adding up to the line. (d) the panel flags that 6 of 8 are chosen, Save works, and Dispatch is refused. (e) the boxes return to the earliest-expiry split. Approving the order reserves by batch: first expiry first, or the batch a customer's minimum shelf life allows. A batch picked by hand that other orders hold in full is refused at dispatch: "Line 1: Batch … holds 0.0000 available here, and 5.0000 is chosen from it. Choose less from it, or another batch." A batch is expired **on** its expiry date, not the day after.
### TC-SELL-020 — Charging a customer more after the invoice

*Added 2026-10-02 from the code. **Server side driven in full 2026-10-05** on a `compliance-firm`, the GST returns included; results in `docs/qa/SELLING_API_CHECK_ROUND_3_2026-10-05.md`. **The screens are not yet driven.***

- **Preconditions:** The GST-registered firm described in this section's preparation table, with its three invoices.
- **Also needs:** an approved invoice to a **registered** customer for 10 at 100 + 18% GST (1,180.00), nothing received on it.
- **Steps:** as a **Sales manager** (hire one if the preparation has none): Sell > Returns & notes > **Debit Notes** → **New** → pick the invoice → reason *Price increase* → 100 on its line → watch the tax → **Save**. Try **Approve**. As the **Firm admin**: approve it. Then Sell > Receipts → New for the customer. Then GST Returns → GSTR-1 and GSTR-3B for the month. Then try to cancel the **invoice**. Then record a receipt of 1,250.00 against the invoice and try to cancel the **debit note**.
- **Expect:** the preview shows tax **18.00**, total **118.00** (the invoice line's rate). The sales manager can raise but is not offered **Approve**. After approval the customer's balance is **118.00** higher, and Record Receipt lists the invoice at **1,298.00** owing, one row not two. GSTR-1 CDNR shows the note as type **D** against the invoice, taxable 100, CGST 9 + SGST 9; GSTR-3B 3.1(a) is 100 higher. Cancelling the invoice is refused naming the debit note. With 1,250.00 received, cancelling the debit note is refused ("Money received on invoice SI-… has already met 70.00 of this debit note. Reverse that receipt first, then cancel the note."); after reversing the receipt it cancels and the balance drops back. A customer debit note prints (A4, its own **Print**).
### TC-SELL-021 — Rate includes GST on an order and a quotation

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**, Sell > Quotations → **New** for `QA-C01`. Switch **Rate includes GST** on, type a rate of **118** on a line taxed at 18%, with quantity 10 → Save. Reopen it, then **Print**. Convert it to a sales order and open the order. Then Settings > Selling > **Sales Stages** → *Rates typed on a bill include GST* on → Save, and start another new sales order.
- **Expect:** while the switch is on the Rate column is labelled as the shelf price and the totals show a taxable value of 1,000.00 with 180.00 tax, total 1,180.00. Reopening shows 118 as typed; the print shows both rates. The order opens with the switch **on** and the same typed rate, and the customer is billed what was quoted. A bill raised from the order prints only the pre-tax rate. A new order starts with the switch on only after the setting is saved; an order made by converting a quotation never reads the setting a second time.
### TC-SELL-022 — Batch rules: near expiry, a reason, and the price floor

*Added 2026-10-02 (backlog 79 row 6, A2).*

- **Preconditions:** the shop from TC-SELL-019 (a batch expiring within 30 days and a later one, 10 each). The product's **minimum selling price** 150. Settings > Selling > **Price Floor**: *Block*.
- **Steps:** Settings > Stock > **Batch Rules**: note the defaults, then set *A near-expiry batch leaving* to **Need a reason** → Save. (a) A sales order for 2 at **100** → Approve. (b) A sales order for 15 at 100 → Approve. (c) A delivery note off order (a), batches untouched → Save → Approve → **Dispatch**; cancel the reason prompt; Dispatch again and give *Short-dated stock cleared*. (d) Set *FEFO skip* to **Need a reason**; a note choosing the *later* batch → Dispatch. (e) Untick *may be sold below the price floor* → repeat (a).
- **Expect:** the defaults read 30 days, Warn, Record, ticked. (a) approves although 100 is below 150; its timeline names the near-expiry batch. (b) is refused below the minimum price when the order is **approved**, not when it is saved, and the message quotes the rate after any standing discount -- 15 takes the later batch too, which is fresh stock. (c) the prompt names the line and the near-expiry batch; cancelling dispatches nothing; with the reason it dispatches and Settings > Platform > System > Audit Logs shows **delivery_note.near_expiry_dispatched** with the reason. (d) asks for a reason before dispatching; **delivery_note.fefo_skipped** keeps it. (e) is refused like (b). A batch is expired **on** its expiry date, not the day after.

### TC-SELL-023 — Choosing batches on a counter bill

*Added 2026-10-02 (backlog 79 row 2).*

- **Preconditions:** a firm with the delivery note stage **off** (Settings > Selling > Sales Stages). A batch-tracked product with two in-date batches, an earlier and a later expiry, 10 each, in the default warehouse.
- **Steps:** Sell > Sales Invoices > **+ New by product** (the counter bill): the product, quantity 4. Open the line's batches: note the pre-fill. Put 4 on the **later** batch → Save → reopen the draft and look at the batches → change to 1 earlier + 3 later → Save → **Approve**. Then a second bill of 4 with the batches untouched → Approve.
- **Expect:** the picker lists both batches with expiry and days left, the earlier one pre-filled with 4. The saved draft shows 4 on the later batch, and Stock > Batches shows the 4 reserved on it. After the change to 1 earlier + 3 later, Stock > Batches reads 1 reserved on the earlier batch and 3 on the later: a line split across batches holds each batch for what was chosen from it. Picks that do not add up to the line are held first expiry first and refused at approval ("Line 1: the batches chosen add up to 5.0000, and the line delivers 6.0000."). A counter bill that picks an expired batch is refused when it is saved: "Line 1: the batch the customer asked for, … has expired." **(HTTP)** the picks of a saved counter bill are edited either way, the line sent back by its source fields (no `product_id`) or as a product line; changing the quantity without sending the picks again clears them. After approval, stock of the earlier batch is down by 1 and the later by 3 (Stock > Batches), and Settings > Platform > System > Audit Logs shows **delivery_note.fefo_skipped**. The untouched bill draws 4 from the earlier batch, as before.

### TC-SELL-024 — A customer's minimum shelf life

*Added 2026-10-02 (backlog 79 row 6).*

- **Preconditions:** a firm whose business profile has expiry tracking. A batch-tracked product with a batch expiring in about 4 months and one in about 9 months, 10 each. A customer with **Minimum shelf life** 180 days (Masters > Customers → edit). An approved sales order of 8 for that customer.
- **Steps:** (a) Sell > Delivery Notes → New off the order, batches untouched → Save → Approve → **Dispatch**. (b) A second order and note: open the batch picker. (c) Put 8 on the 4-month batch → Save → Approve → Dispatch. (d) Settings > Stock > **Batch Rules**: *short of the customer's minimum shelf life* → **Warn** → Save, and dispatch (c) again. (e) Raise and approve an order for the same customer (it holds the 9-month batch), then an ordinary order for another customer that holds the 4-month batch; dispatch the first order's note with its batches untouched. (f) Cancel the second order and read Stock > Batches.
- **Expect:** (a) ships the **9-month** batch -- the 4-month one is passed over without anybody choosing; Stock > Batches shows the order's 8 reserved on the 9-month batch from approval. (b) the 4-month batch carries **Too short for customer** and the pre-fill is on the 9-month one. (c) Dispatch is refused with a message naming the batch and the customer's minimum; no reason prompt is offered. (d) it dispatches, and Settings > Platform > System > Audit Logs shows **delivery_note.short_shelf_life_dispatched**. (e) the first order's note still ships the 9-month batch and the other order's reservation on the 4-month batch stays. (f) cancelling or closing an order lets go of that order's own hold and no other: the 4-month batch is free again and nothing else moves.

### TC-SELL-025 — Pinning the batch a customer asked for

*Added 2026-10-02 (backlog 79 row 4).*

- **Preconditions:** a batch-tracked product with an earlier and a later in-date batch, 10 each, and one expired batch with stock.
- **Steps:** Sell > Sales Orders → New: 5 of the product, **Batch** = the later batch → Save → Approve. Stock > Batches. Sell > Delivery Notes → New off the order → look at the batch picker → Approve → Dispatch. Then an order for 12 pinning the later batch → Approve. Then an order pinning the expired batch → Approve.
- **Expect:** approval holds 5 of the **later** batch and nothing of the earlier. The note opens with 5 on the later batch, and dispatch ships it (audit trail: **delivery_note.fefo_skipped**). The order for 12 holds 10 of the later batch and leaves 2 as a back order -- the earlier batch stays free -- and Reports > Back orders lists the order with 2. Cancelling or closing an order, or cancelling a draft counter bill, lets go of that order's own hold: an order on the later batch that is cancelled frees the later batch and leaves another order's hold on the earlier batch alone. Pinning the expired batch is refused at approval naming it. A batch is expired **on** its expiry date, not the day after.

### TC-SELL-026 — A batch's own MRP

*Added 2026-10-02 (backlog 79 row 7, A41).*

- **Preconditions:** a batch-tracked product; the delivery note stage off (counter bills).
- **Steps:** Goods Receipt for the product: batch `B1`, **MRP** 120, **Selling price** 95; a second line batch `B2`, MRP 100. Complete it. Settings > Stock > Batch Rules: tick *Take a line's rate from its batch's selling price*. Counter bill: the product, 4, choose `B1` → look at the rate → Save → Approve → **Print**. Then a counter bill of 4 from `B2` at rate **110** (no tax) → Approve.
- **Expect:** the batch screen shows B1 at MRP 120 / 95 and B2 at 100. The picker lists each batch's MRP. Choosing B1 fills the rate **95** on the screen; the server does not fill a blank rate from the batch. The printed bill has an **MRP** column, 120 on the B1 row. The B2 bill at 110 is refused, quoting the rate **with tax**: on a product taxed at 18%, "charges 129.80 a unit with tax, above the MRP of 100.00 printed on the batch it ships" (110.00 only where the product carries no tax).
---

### TC-SELL-027 — Several delivery notes on one bill: customer first

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Also needs:** a second customer with one dispatched, unbilled delivery note; for the clash, a third dispatched note for Vijaya that names a **different salesman** from the notes of 5 and 7 (set the salesman on the order it came from). For the supplier half, `po-received` (receipts of 4 and 6).
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → New → bill from delivery notes. (a) Look at the first question asked. Pick Vijaya. (b) Tick the notes of 5 and 7 → create the draft. (c) Start again and also try to tick the third note. (d) Start again and pick the second customer. Then Buy > **Purchase Invoices** → New → from receipts: pick the supplier and tick the receipts of 4 and 6.
- **Expect:** (a) the editor asks for the **customer** first and lists only customers that have notes left to bill. Vijaya opens a tick list: number, date, order and the amount left to bill before tax. (b) the two notes can be ticked together and make one draft bill. (c) the third note cannot be ticked beside notes of another salesman, and says which field it clashes on (the server names the field -- "All source documents must belong to the same salesman." -- and not the note; a note that names nobody never clashes); the same holds for branch, territory or route. (d) a customer with a single note has it ticked already, without being asked. The supplier bill asks for the **supplier** first and lists that supplier's receipts; the only field a receipt can clash on is the branch.
### TC-SELL-028 — An enquiry becomes a customer and a quotation

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the product `QA-DET`; a role holding SALES_VIEW, SALES_QUOTATION_CREATE and SALES_UPDATE (the firm administrator does).
- **Steps:** as the prepared **Firm admin**: Sell > All Sell screens > Documents > **Enquiries** → New. Type a **prospect** (name, company, phone in the form +91…, email, city) instead of picking a customer; source, salesman, expected value, expected close date, next follow-up date; one line for `QA-DET` × 10 and a second line with a description only. Save. (a) Try **Convert to quotation**. (b) Give the second line a product and convert again. (c) Open the new quotation and convert it to a sales order. (d) Raise a second enquiry for a prospect, add a follow-up note with a new next date, then mark it **Lost** with a reason from the list. (e) Open the **Follow-ups due** view; then Reports > Operational → **Enquiries lost**.
- **Expect:** the enquiry is numbered **ENQ-…** and opens as new. (a) conversion is refused while a line has no product. (b) a customer is created from the prospect (code from the customer series, the firm's currency) and a draft quotation with the lines; the enquiry shows the quotation and the customer. (c) once the order is made the enquiry reads **WON**. (d) the follow-up is kept with its date and the enquiry's next follow-up moves; Lost needs a reason chosen from a fixed list. (e) the due view lists enquiries whose next follow-up is today or earlier and not closed; the lost report counts the lost enquiries and totals their expected value by reason. The due view is paged like the enquiry list (**(HTTP)** `GET /api/v1/enquiries/follow-ups-due` with `page_size` above 100 is 422). There is no Home gadget and no reminder yet.
### TC-SELL-029 — Counter billing with a barcode scanner and a split of tenders

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** `QA-DET` given a barcode (Masters > Products → the product → barcode); a USB scanner in keyboard mode, or type the barcode and press Enter; a thermal printer or the PDF preview.
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → New by product for Vijaya. Click the **scan field**, scan `QA-DET`, scan it again. Add a split of tenders: part **Cash**, the rest **UPI**; then give more cash than the balance. Press **Save & print (F9)**. Then try a tender total above the bill by editing it and saving.
- **Expect:** the first scan adds a line, the second raises its quantity by 1. The tender panel shows the balance and, for cash over the balance, the change to give back. F9 saves, approves, prints the thermal bill and opens the next blank bill. The bill shows as paid: one receipt per tender is recorded, cash into the cash book, UPI through the bank with mode UPI, each allocated to the bill. A tender total above the bill saves as a draft and is refused when the bill is **approved**: "600.00 was received against a bill of 472.00. Enter what the bill is paid with; change is handed back." Receipts appear under Sell > **Receipts**.
### TC-SELL-030 — Picking list and loading sheet

- **Preconditions:** As *selling-ordered*, plus the two delivery notes in the preparation table, dispatched.
- **Steps:** as the prepared **Firm admin**: Sell > **Delivery Notes**; tick both notes (5 and 7) → **Pick list**. Then with the same ticks → **Loading sheet**. Try the buttons with nothing ticked, and as a role without SALES_VIEW.
- **Expect:** each button gives an A4 PDF. The pick list sums the ticked notes **by product** (12 of `QA-DET`, free goods included, in stock units), by batch where a note chose one and "earliest expiry first" where it left the batch to dispatch. The loading sheet has one drop per note in the order the round visits the customers, with the note's value and what its bills still owe. Nothing is written: the notes are unchanged. With nothing ticked the buttons are disabled or the request is refused by name.
### TC-SELL-031 — Cash discount for early payment, and interest on overdue bills

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** the invoice of 483.21 nothing has been received on; an invoice that is already past its due date (back-date one, or use the due date on the bill).
- **Steps:** as the prepared **Firm admin**: Masters > **Customers** → Vijaya → terms → cash discount **2% within 10 days**. Settings > Selling > **Credit Control** → set an overdue interest rate (say 18% a year) and a grace of 5 days → Save. Sell > **Receipts** → Record Receipt for Vijaya on the day of the invoice. Then open **Customer Statements** for a customer with an overdue bill and press **Raise interest debit note**. Then clear the customer's own discount days and look again.
- **Expect:** Record Receipt prefills the discount allowed (2% of what the bill still owes) while the bill is inside its 10 days, and not after; accepting it posts the discount as *Discount Allowed* and leaves the bill's tax alone. A customer with no days of their own takes the firm's terms; zero days refuses a discount. The statement shows the interest accrued on each overdue bill at the yearly rate (365-day year) for the days past due once the grace days have run. *Raise interest debit note* makes a **draft** customer debit note with the reason *Late payment interest*, taxed at the bill's own rates; interest is only charged when somebody raises it. A receipt, credit note or return changes the figures at once. Raising the note needs CUSTOMER_DEBIT_NOTE_MANAGE.
### TC-SELL-032 — A new outlet waits for office approval

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a **Field Sales** user (SALES_EXECUTIVE) beside the firm administrator.
- **Steps:** as the **Firm admin**: Settings > Selling > **Sales Stages** → switch on *New outlets need approval* → Save. As the **Field Sales** user: Masters > **Customers** → New, save. Try to raise a quotation, an order, and a bill for it; try to change its status. Sign in as the **Firm admin**: filter the list by **Pending approval**, tick the new customer → **Approve**; also tick two more pending ones → **Approve** (bulk). Switch the setting off and create another customer as the field user.
- **Expect:** the field user's new customer is saved with status **Pending approval** (badge in the list; a filter finds it) and a bill for it is refused when it is raised, naming the reason ("… is a new outlet waiting for approval, so it cannot be billed yet. Its orders are kept; approve the customer to bill them."); quotations and orders for it are still accepted and kept; the field user cannot move it on. The administrator's Approve (single and bulk) activates it, after which it can be billed. With the setting off a non-approver's new customer starts active. Approving needs CUSTOMER_APPROVE. The Field Sales user's new customer carries no money terms: on the form the **Credit limit**, **Default discount %**, **Opening balance**, **Payment terms (days)**, **Cash discount (days)** and **Cash discount %** boxes are locked ("Set by somebody with the manage customer settings permission."), and **(HTTP)** a credit limit, an opening balance, credit days, cash-discount terms or a standing discount sent with the new customer is refused (403) naming CUSTOMER_MANAGE_SETTINGS. Zero or blank is not refused. A customer that needs such terms is created, or given them, by the firm administrator or a Firm Manager (TC-CUST-007).
### TC-SELL-033 — Named price levels, and a customer's own level

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Pricing > **Price Levels** → New *Dealer* and *Retail*. Masters > Products → `QA-DET` → price levels → Dealer 70, Retail 90. Masters > Customers → Anand → Price level *Dealer* (and, separately, a customer **group** with level *Retail*, Vijaya in it). Sell > **Quotations** → New for Anand: add DET and leave **Unit price** blank. Repeat for Vijaya. Then add a price list that has a **Rate** for DET and repeat for Anand.
- **Expect:** the blank price is filled with the customer's level rate (Dealer 70 for Anand, the group's Retail 90 for Vijaya — the customer's own level wins over the group's) before the GST-inclusive conversion; lines the server filled are not converted again. A price list **Rate** wins over the level, and the level wins over the product's own price. The same holds on a sales order. A typed unit price is kept as typed.
### TC-SELL-034 — A UPI QR on the invoice, and sharing it on WhatsApp by hand

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** the approved invoice of 483.21 for Vijaya, given a phone number for this case; a browser or WhatsApp installed for the wa.me link. No messaging account is needed.
- **Steps:** as the prepared **Firm admin**: Sell > **Sales Invoices** → Print settings → UPI ID `shop@upi` → Save; try `shop` alone. Print the approved invoice (A4, then the 80 mm roll). Receive part of the bill, print again; receive the rest, print again. Select the approved invoice → **WhatsApp**. Look at Vijaya's timeline.
- **Expect:** the UPI ID must look like `name@handle`. A bill that stands and still owes money prints *Scan to pay by UPI*: a QR with the payee, the amount still owing, INR and the bill number, plus the amount and the UPI ID beside it, in the A4 footer and under the total on the roll. A part-paid bill asks only for the rest; a paid one prints none; a draft or cancelled bill prints none. *WhatsApp* saves the PDF in Downloads, opens the folder with the file selected and opens WhatsApp web (wa.me) with the covering note (and the UPI line); the bill's timeline reads *WhatsApp shared by hand to …* and never "sent".
### TC-SELL-035 — Payment reminders and other documents sent by hand

- **Preconditions:** As *selling-delivered*, plus the first note billed and approved, as in the preparation table.
- **Also needs:** Settings > Firm > **Messaging** switched on with an email account for the firm (see the messaging setup guide) for the email halves; a customer who owes nothing; a customer set to *No reminders*; a quotation, a sales order, a receipt and a purchase order.
- **Steps:** as the prepared **Firm admin**: Sell > **Customer Statements** → Vijaya → **Remind**; choose email. Then select the approved invoice → **Remind** → WhatsApp. Try Remind for the customer who owes nothing and for the *No reminders* customer. Then use **Send** (email) on a quotation, a sales order, a receipt and a purchase order; print the order and the receipt.
- **Expect:** the reminder sends the customer's **statement of account** as a PDF: the movement from the oldest unpaid bill to today, the closing balance, the unpaid bills with days overdue, and the UPI line where it applies. Email queues an outbox row and the worker sends it; WhatsApp opens WhatsApp web (wa.me) as in TC-SELL-034 and is recorded in the customer's audit trail. A customer who owes nothing and one marked *No reminders* are refused by name on both roads. The five documents send by email with a covering note and the PDF rendered at send time; a cancelled document or a reversed receipt is refused. The order and the receipt each have a Print (the receipt on A5).
---

**The nine selling features of backlog 87 (SG-1 to SG-9).** Cases TC-SELL-036 onward were written from the code and its automated tests on 2026-10-05 and have not yet been run by hand; treat a failure as possibly the case's mistake until it is settled. Each case stands alone: it names everything it needs and uses no other case's documents. They share these masters, which no earlier case touches:

| Record | Values |
| --- | --- |
| Product `QA-CTR` *Counter Item* | Selling price 100, GST 18% Local, HSN / SAC `3402`, 500 in MAIN bought at 60 |
| Product `QA-SVC` *Installation* | Product type *SERVICE*, selling price 500, GST 18% Local, HSN / SAC `998739`, no stock |
| Customer `QA-C03` *Registered Buyer* | a GSTIN in the firm's own state, credit limit 0, no standing discount |
| Counter billing | Settings > Selling > **Sales Stages**: *Sales order* and *Delivery note* both **off**. Sell > Sales Invoices → **New Invoice** then opens the counter bill. Switch both back **on** after the counter cases |
| Figures | 10 of `QA-CTR` at 100 is 1,000.00 before tax, 90.00 CGST + 90.00 SGST, 1,180.00 in all. Where a case says *the bill of 1,180.00* it means that bill to the customer the case names |

Counter Shifts and Customer Rebates are under Sell > All Sell screens > Documents; Collection Sheet and Payment Promises under Sell > All Sell screens > Money; Transporters under Settings > Set up > Territories & routes; Party Adjustments under Accounts > All Accounts screens > Books. The journal of any step is read under Accounts > **Journal Entries**.

**GST sales register and HSN summary of sales (SG-1)**

### TC-SELL-036 — The GST sales register reads a bill by tax head

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters in the table above; the Sales order and Delivery note stages **on**. One sale of 10 `QA-CTR` at 100 to `QA-C03`, Discount % `0`: order approved, delivery note dispatched, invoice approved today (1,180.00). One more invoice left as a **draft**.
- **Steps:** as the prepared **Firm admin**: Reports > Financial → **GST sales register**, period this month → run. Then **Export**.
- **Expect:** one row for the approved bill: Type **Invoice**, its number, Customer *Registered Buyer*, GSTIN the customer's, Place of supply the firm's state code, Taxable **1,000.00**, IGST 0.00, CGST **90.00**, SGST **90.00**, Cess 0.00, Total tax **180.00**, Total **1,180.00**; *Against invoice* blank. The draft is not listed. The figures equal the bill's journal: Dr 1100 Trade Receivables 1,180.00, Cr 4000 Sales 1,000.00, Cr Output CGST 90.00, Cr Output SGST 90.00. The export matches the grid.
### TC-SELL-037 — Credit notes and returns are rows in minus, a debit note a row in plus

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above, stages **on**; an approved bill of 1,180.00 to `QA-C03` as in TC-SELL-036, nothing received on it.
- **Steps:** as the prepared **Firm admin**: (a) Sell > Returns & notes > Credit Notes → **Raise credit note**: the bill, Line 1, Reason Rate difference, Credit, before tax **100** → Raise; run the register before approving it. (b) **Approve** it and run the register again. (c) Sell > Returns & notes > Debit Notes → New → the bill → **50** on its line → Save → Approve. (d) Sell > Returns & notes > Sales Returns → New Return against the bill, Quantity returned **2**, taken back into MAIN → Create draft → Approve → Complete. Run Reports > Financial → **GST sales register** for the month.
- **Expect:** (a) a draft credit note is not in the register. (b) a row Type **Credit note**, *Against invoice* the bill's number, Taxable **-100.00**, CGST **-9.00**, SGST **-9.00**, Total **-118.00**, on the note's own date. (c) a row Type **Debit note**, Taxable **50.00**, CGST **4.50**, SGST **4.50**, Total **59.00**. (d) a row Type **Sales return**, Taxable **-200.00**, CGST **-18.00**, SGST **-18.00**, Total **-236.00**; an approved return that is not yet completed is not listed. The four rows' Taxable adds to **750.00**, the same net figure the HSN table (Table 12) of GSTR-1 states for the month under Accounts > All Accounts screens > Tax filing > GST Returns. (GSTR-1 answers only for a firm with a GST number: put one on the preparation firm, or use `compliance-firm`.)
### TC-SELL-038 — The HSN summary of sales adds up to the register

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above, stages **on**; an approved bill of 10 `QA-CTR` at 100 to `QA-C03` dated today, and an approved bill of 5 `QA-DET` at 84, Discount % `0`, to the same customer (`QA-DET` carries no HSN).
- **Steps:** as the prepared **Firm admin**: Reports > Financial → **HSN summary of sales**, period this month → run. Then set the period to the whole financial year and run again.
- **Expect:** a row HSN **3402**, Rate % **18**, Quantity **10**, Taxable **1,000.00**, CGST **90.00**, SGST **90.00**, Total tax **180.00**. A second row with a **blank** HSN for the detergent: Quantity 5, Taxable 420.00, CGST 37.80, SGST 37.80. The Taxable and Total tax columns add to the GST sales register's for the same days. A year is accepted here, though GSTR-1 itself is refused for more than three months. (GSTR-1 answers only for a firm with a GST number: put one on the preparation firm, or use `compliance-firm`.)
### TC-SELL-039 — Who may open the two GST reports

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a **Read Only** user and a **Warehouse** user in the firm.
- **Steps:** as the **Read Only** user: Reports > Financial → GST sales register and HSN summary of sales. As the **Warehouse** user: look for them. **(HTTP)** as the Warehouse user, `GET /api/v1/sales-invoices/reports/gst-register`.
- **Expect:** Read Only (who holds `SALES_VIEW` and `REPORT_VIEW`) opens both. The Warehouse user, who holds neither, is not offered them and the request is refused with **403**, "You do not have permission to perform this action."
---

**Walk-in cash sale (SG-2)**

### TC-SELL-040 — A walk-in bill names the Cash sale customer and is paid at the counter

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing (both stages **off**).
- **Steps:** as the prepared **Firm admin**: Sell > Sales Invoices → **New Invoice**. Under *Counter sale* press **Walk-in**. In *Buyer (optional)* type Buyer name `Ramesh` and Buyer phone `+919800000555`. Add `QA-CTR` quantity **10**. Read *Received now*. Press **Save & print (F9)**. Then Masters > Customers; Sell > Receipts; Accounts > Journal Entries. Start another bill and press **Walk-in** again.
- **Expect:** Walk-in selects the customer **Cash sale** (code `CASH`) and shows the two buyer boxes. *Received now* is pre-filled with the bill's amount payable (its total rounded to the paisa, 1,180.00 here), with the note "A walk-in bill is paid in full at the counter." F9 saves, approves and prints; the print names **Ramesh** and his phone in place of *Cash sale*. Masters > Customers lists one *Cash sale*, Outstanding 0.00; the second Walk-in reuses it and makes no second customer. Receipts shows one receipt of 1,180.00, Cash, applied to the bill. Journals: the bill Dr 1100 Trade Receivables 1,180.00 / Cr 4000 Sales 1,000.00 / Cr Output CGST 90.00 / Cr Output SGST 90.00; the receipt **Dr 1000 Cash 1,180.00 / Cr 1100 Trade Receivables 1,180.00**; and the delivery note's cost entry Dr 5200 Cost of Goods Sold 600.00 / Cr 1200 Inventory 600.00. Stock of `QA-CTR` is down 10.
### TC-SELL-041 — A walk-in bill that is not paid in full is refused at approval

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → **Walk-in** → `QA-CTR` quantity **10** → change *Received now* to **500** → **Save & print (F9)**. Then set *Received now* to **0** and try again. Then set it to **1180** and press F9.
- **Expect:** with 500 the bill is kept as a draft and approval is refused, the screen staying open with the server's message: "A walk-in bill is paid in full at the counter: SI-… comes to 1180.00 and 500.00 was received. Take the rest, or bill a customer with a record to sell on credit." The amount to take is the bill's **amount payable**, its total rounded to the paisa; TC-SELL-093 covers a bill whose total is not a whole paisa. The same with 0. Nothing is posted and no receipt is made: Journal Entries has no entry for the bill. With 1180 it approves as in TC-SELL-040.
### TC-SELL-042 — A walk-in bill paid with two tenders

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → **Walk-in** → `QA-CTR` quantity **10** → **Split payment**: Cash **680**; **Add payment** UPI **500**, Reference `UPI-QA-500` → **Save & print (F9)**. Then repeat with Cash 680 and UPI **400**, and once more with Cash 700 and UPI **500**.
- **Expect:** 680 + 500 equals the bill, so it approves. Sell > Receipts shows **two** receipts, each applied to the bill: 680.00 Cash (**Dr 1000 Cash / Cr 1100 Trade Receivables**) and 500.00 with mode UPI (**Dr 1010 Bank / Cr 1100 Trade Receivables**). With 680 + 400 approval is refused with the paid-in-full message of TC-SELL-041, naming 1080.00 as received. With Cash 700 and UPI 500 it is refused the other way: "1200.00 was received against a bill of 1180.00. Enter what the bill is paid with; change is handed back." Split tenders approve only when they add up to the amount payable.
### TC-SELL-043 — A buyer's name belongs only on a walk-in bill

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → choose `QA-C03` and look for the buyer boxes. Press **Walk-in**, then choose `QA-C03` again. **(HTTP)** `POST /api/v1/sales-invoices` for `QA-C03` with `"buyer_name": "Ramesh"`.
- **Expect:** *Buyer (optional)* shows only while the customer is *Cash sale*, and goes when another customer is chosen. The request is refused: "A buyer's name and phone are typed only on a walk-in bill. This bill names a customer with a record; correct the customer instead."
### TC-SELL-044 — The Cash sale customer cannot be deleted, given credit, registered or made inactive

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the Cash sale customer (press **Walk-in** once on a counter bill, as in TC-SELL-040).
- **Steps:** as the prepared **Firm admin**: Masters > Customers → *Cash sale*. (a) **Delete**. (b) Edit: Credit limit `5000` → Save. (c) Edit: a GST number → Save. (d) Edit: change the status to anything but Active → Save.
- **Expect:** each is refused and the customer is unchanged: (a) "Cash sale is the walk-in customer every counter bill without a customer record names; it cannot be deleted." (b) "Cash sale is the walk-in customer and takes no credit: its bills are paid in full at the counter." (c) "Cash sale is the walk-in customer and is unregistered. Bill a registered buyer to a customer record of its own." (d) "Cash sale is the walk-in customer and stays active."
### TC-SELL-045 — A walk-in bill earns no loyalty points and files as B2C

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there. ((its loyalty scheme gives 2 points per 100))
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: a walk-in bill of 10 `QA-CTR`, paid in full, F9. Then a counter bill of the same to `QA-C01` (Vijaya), Discount % `0`, *Received now* 1180, F9. Settings > Set up > Pricing > **Loyalty**. Reports > Financial → **GST sales register** for today.
- **Expect:** Loyalty lists Vijaya with about **23.6** points from her bill (2 per 100 of 1,180.00) and has **no** row for *Cash sale*. In the register both bills show a blank GSTIN; the walk-in bill's Customer is *Cash sale*.
---

**Service invoices (SG-3)**

### TC-SELL-046 — A bill of a service moves no stock and posts no cost

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → add `QA-SVC` quantity **1** → Save, then **Approve** the draft from the list. Stock > All Stock screens > Stock > Inventory and Stock > Stock Ledger for `QA-SVC`. Sell > Delivery Notes. Accounts > Journal Entries. Then a second bill of quantity **5000**.
- **Expect:** the bill totals **590.00** (500.00 + 45.00 CGST + 45.00 SGST) and approves although the product has no stock. Its own delivery note reads **DISPATCHED**. The stock ledger has **no** row for the service and Inventory shows nothing reserved for it (or no row at all). Journals: only the bill's, Dr 1100 Trade Receivables 590.00 / Cr 4000 Sales 500.00 / Cr Output CGST 45.00 / Cr Output SGST 45.00; there is **no** Cost of Goods Sold entry for the note. 5000 units approve the same way.
### TC-SELL-047 — Goods and a service on one bill

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **2** and `QA-SVC` quantity **1** → Save → Approve → **Print**. Stock Ledger for both products. Journal Entries. Reports > Financial → HSN summary of sales for today.
- **Expect:** taxable 700.00, tax 126.00 (63.00 + 63.00), total **826.00**. The stock ledger shows `DISPATCH` −2 for the goods and nothing for the service. The note's cost entry is for the goods alone: Dr 5200 Cost of Goods Sold 120.00 / Cr 1200 Inventory 120.00. The print and the HSN summary carry the service under **998739** and the goods under 3402.
### TC-SELL-048 — A service on a typed order and delivery note

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; the Sales order and Delivery note stages **on**.
- **Steps:** as the prepared **Firm admin**: Sell > Sales Orders → New Order: `QA-C03`, MAIN, `QA-SVC` quantity **3** → Create draft → **Approve**. Inventory for the service. Reports → **Back orders**. Sell > Delivery Notes → New off the order → Save → Approve → **Dispatch**. Stock Ledger. Bill the note and approve. Then cancel a second, approved order for the service.
- **Expect:** the order approves with nothing on hand; Inventory shows no reservation and the order is **not** on the back-order report. The note dispatches, the order reads DELIVERED, and the stock ledger has no row and Journal Entries no cost entry. The bill is 1,770.00 (1,500.00 + 135.00 + 135.00). Cancelling an approved service order writes no stock movement either.
### TC-SELL-049 — Returning a service credits the customer and puts nothing on a shelf

*The server has no automated test of its own for this path (it rides the return's zero-movement path), so check it with extra care.*

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the approved bill of 1 `QA-SVC` (590.00) to `QA-C03` from the steps of TC-SELL-046, built for this case.
- **Steps:** as the prepared **Firm admin**: Sell > Returns & notes > Sales Returns → New Return against the bill, Quantity returned **1** → Create draft → Approve → **Complete**. Stock Ledger for the service. Masters > Customers → `QA-C03`.
- **Expect:** the return completes and the customer's Outstanding falls by **590.00**. The stock ledger has **no** `SALES_RETURN` row for the service and no stock is added.
---

**Charges on the bill with their own GST (SG-4)**

### TC-SELL-050 — A charge is taxed at its own rate and credited to Other Charges Recovered

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **10**. Under **Other charges** press **Add charge**: Name `Packing`, Amount `100`, tax **GST 18% Local**, SAC `998540`. Read the totals. Save → Approve. Accounts > Journal Entries → the bill's entry.
- **Expect:** the charge adds 100.00 and 18.00 of tax (9.00 CGST + 9.00 SGST): taxable 1,100.00, tax 198.00, total **1,298.00**. Journal: Dr 1100 Trade Receivables 1,298.00 / Cr 4000 Sales **1,000.00** / Cr **4050 Other Charges Recovered 100.00** / Cr Output CGST 99.00 / Cr Output SGST 99.00. The customer's Outstanding rises by 1,298.00.
### TC-SELL-051 — A charge that names no tax carries none

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **10** → **Add charge**: Name `Handling`, Amount `50`, tax left at **(no tax)**, SAC blank. Also type **20** in *Delivery charge*. Save → Approve → the journal.
- **Expect:** *Handling* adds 50.00 and no tax. The delivery charge is still taxed with the goods (20.00 + 3.60). Total 1,180.00 + 50.00 + 23.60 = **1,253.60**. Journal: Cr 4050 Other Charges Recovered **50.00**; Cr 4000 Sales 1,020.00 (goods and delivery charge); Output CGST 91.80, Output SGST 91.80; Dr 1100 Trade Receivables 1,253.60.
### TC-SELL-052 — Charges on a draft are replaced by what the editor holds

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **10** → two charges: `Packing` 100 at GST 18% Local, and `Insurance` 40 at (no tax) → Save. Reopen the draft with **Edit**: both rows are there. Change Packing to **200**, remove Insurance with **Remove charge**, add a third row with an amount and **no name** → Save. Reopen. **(HTTP)** `PUT` the draft with eleven charges; and with a charge whose name is spaces. Then on a draft that carries a **Reference**, a bill discount and a delivery charge: **Edit**, change only the quantity → Save; **Edit** again, empty the Reference box and the bill discount box → Save.
- **Expect:** the first save totals 1,180.00 + 118.00 + 40.00 = **1,338.00**. After the edit only *Packing* 200.00 remains (the unnamed row is not a charge) and the total is 1,180.00 + 236.00 = **1,416.00**. Eleven charges are refused (at most ten), and a blank name is refused: "A charge needs a name." An edit keeps what it does not mention: after the quantity-only save the reference, the bill discount and the delivery charge are as they were; emptying the Reference or the bill discount box on a saved bill and saving clears it. **(HTTP)** a header field a `PUT` does not send is left as it is (freight, the bill discount, the reference, remarks, additional charges, round off, notes and charges). Null clears a reference, remarks, freight, a bill discount or a coupon; 0 clears additional charges and round off; an empty list clears notes and charges. A flat bill discount amount is carried as its rate when the quantity changes, so send the amount again to keep it flat.
### TC-SELL-053 — The charge on the print, in the register and in the HSN summary

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the approved bill of TC-SELL-050 (10 `QA-CTR` and *Packing* 100 at 18%, SAC `998540`: 1,298.00), built for this case.
- **Steps:** as the prepared **Firm admin**: select the bill → **Print**. Reports > Financial → GST sales register, then HSN summary of sales, for today. Accounts > All Accounts screens > Tax filing > GST Returns → GSTR-1 for the month.
- **Expect:** the print lists **Packing** by name between the taxable value and the tax rows, and its HSN summary has a row for 998540. The register's row for the bill reads Taxable **1,100.00**, CGST 99.00, SGST 99.00, Total 1,298.00. The HSN summary has a row **998540**, Rate % 18, Quantity **0**, Taxable 100.00, beside the goods' row. GSTR-1 states the same 1,100.00. (GSTR-1 answers only for a firm with a GST number: put one on the preparation firm, or use `compliance-firm`.)
### TC-SELL-054 — What a charge does not do yet

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the approved bill of TC-SELL-050, built for this case, nothing received on it; the Sales order and Delivery note stages **on** for the second half.
- **Steps:** as the prepared **Firm admin**: Sell > Returns & notes > Credit Notes → **Raise credit note** on the bill: look at what can be credited; credit Line 1 by **1000** before tax → Raise → Approve. Then Sell > Sales Orders → New Order and look for charges.
- **Expect:** a credit note offers the bill's **lines** only; the charge cannot be credited. After crediting the whole line (1,180.00) the customer still owes **118.00**, the charge and its tax. A sales order has no *Other charges*: charges are typed on the bill and are not carried from the order.
---

**Transporter master and freight terms (SG-5)**

### TC-SELL-055 — A transporter is kept once by name

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** as the prepared **Firm admin**: Settings > Set up > Territories & routes > **Transporters** → New: Name `Speedy Carriers`, GSTIN `33AAAPL1234C1ZV`, Phone `+919800000777`, Usual mode **Rail**, Active ticked → Save. New again with the same name. New: Name `Hill Cargo`, GSTIN `12345` → Save. New: Name `Hill Cargo`, GSTIN blank, Transporter ID (TRANSIN) `33AABCH5678K1Z2` → Save.
- **Expect:** *Speedy Carriers* is listed with Mode **Rail** and Active **Yes**. The second is refused: "There is already a transporter Speedy Carriers." The same name in other letters (`speedy carriers`) or with a trailing space is refused the same way. A GSTIN that is not the shape of a GSTIN is refused and nothing is saved. *Hill Cargo* saves with only a Transporter ID.
### TC-SELL-056 — Choosing a carrier fills the delivery note

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; stages **on**; the transporter *Speedy Carriers* of TC-SELL-055 (GSTIN `33AAAPL1234C1ZV`, usual mode Rail); an approved order of 10 `QA-CTR` for `QA-C03`.
- **Steps:** as the prepared **Firm admin**: Sell > Delivery Notes → **New** → the order. In **Carrier (master)** choose *Speedy Carriers*. In **Freight** choose **To pay**. **Save delivery note** → Approve → Dispatch → **Print** the challan.
- **Expect:** choosing the carrier fills *Transporter* `Speedy Carriers`, *Transporter GSTIN* `33AAAPL1234C1ZV` and *Moving by* **Rail**. The saved note keeps them, and the challan prints the transporter and **Freight: To pay**. Freight terms move no money: no journal names them, and the bill's *Delivery charge* is still what charges the customer.
### TC-SELL-057 — What is typed on the note wins, and the master never rewrites a note

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** as TC-SELL-056, with two approved orders.
- **Steps:** as the prepared **Firm admin**: (a) New delivery note on the first order: choose *Speedy Carriers*, then overtype *Transporter* with `Speedy Carriers (Salem depot)` and set *Moving by* to **Road** → Save delivery note. (b) Settings > Set up > Territories & routes > Transporters → edit *Speedy Carriers*: Usual mode **Air** → Save. Print the note's challan. (c) **Delete** *Speedy Carriers*. Print the challan again.
- **Expect:** (a) the note keeps what was typed: `Speedy Carriers (Salem depot)`, Road. (b) the challan still prints what the note held; the edit rewrote nothing. (c) deleting the transporter is not refused, and the note still prints its carrier. The name is free again for a new transporter.
### TC-SELL-058 — An inactive carrier is not offered and is refused

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** stages **on**; a transporter `Slow Lines` with **Active** unticked; an approved order.
- **Steps:** as the prepared **Firm admin**: Sell > Delivery Notes → New → the order → open **Carrier (master)**. **(HTTP)** `POST /api/v1/delivery-notes` for the order with `transporter_id` of *Slow Lines*; and with `"freight_terms": "COLLECT"`.
- **Expect:** the picker lists active carriers only, and `(none)`. The request naming the inactive one is refused: "Slow Lines is marked inactive. Choose another transporter or make it active again." A freight term other than PAID, TO_PAY or TO_BE_BILLED is refused.
### TC-SELL-059 — Who keeps transporters, and what the note editor cannot do yet

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a **Field Sales** user; one dispatched delivery note with a carrier.
- **Steps:** as the **Field Sales** user: Settings > Set up > Territories & routes > Transporters. As the **Firm admin**: Sell > Delivery Notes → select the note and look for a way to change its carrier.
- **Expect:** Field Sales (who holds `SALES_VIEW` and not `SALES_UPDATE`) sees the list and is offered no New, Edit or Delete. The delivery note editor only **creates** notes: the carrier and freight of a note already raised cannot be changed on screen.
---

**Files on the five sales documents (SG-6)**

### TC-SELL-060 — Attaching a file to a sales invoice

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** any saved sales invoice; a PDF and a JPG or PNG photo under 10 MB.
- **Steps:** as the prepared **Firm admin**: Sell > Sales Invoices → select the invoice → **Attachments** → **Add file** → the PDF. Add the photo. Close. Read the **Files** column. Open Attachments again → **Open** the PDF, then **Save as**.
- **Expect:** the panel is titled "Attachments · SI-…" and lists both files. The list's Files cell reads a paper clip and **2**; an invoice with nothing attached shows a blank cell. The file opens and saves byte for byte as it was added.
### TC-SELL-061 — Only a PDF, JPG or PNG of up to 10 MB

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** any saved sales invoice; a file over 10 MB; a `notes.docx`; a text file renamed `fake.pdf`.
- **Steps:** as the prepared **Firm admin**: Sell > Sales Invoices → the invoice → Attachments → Add file, each of the three in turn.
- **Expect:** each is refused and nothing is added (if the file picker does not offer a file, that is the refusal; otherwise the server's message shows): "The file is larger than 10 MB, the most it may be."; "Only PDF, JPG and PNG files may be attached; 'notes.docx' is not one by its name."; "'fake.pdf' is not a PDF, JPG or PNG file by its contents."
### TC-SELL-062 — Each of the five documents keeps its own files

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above, stages **on**; one sale taken from a quotation to an order, a delivery note, an invoice and a sales return; a PDF.
- **Steps:** as the prepared **Firm admin**: on each of Sell > Quotations, Sales Orders, Delivery Notes, Sales Invoices and Sell > Returns & notes > Sales Returns, select the document → **Attachments** → Add file. Then open Attachments on the invoice.
- **Expect:** every one of the five lists has **Attachments** and a **Files** column. A file added to the order shows on the order only: the invoice of the same sale lists just its own.
### TC-SELL-063 — Deleting a file, and who may add one

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a sales invoice with one file attached; a **Read Only** user.
- **Steps:** as the **Read Only** user: Sell > Sales Invoices → the invoice → Attachments. As the **Firm admin**: Attachments → **Delete** the file → confirm. Settings > Platform > System > Audit Logs.
- **Expect:** Read Only sees the file and can open it, with no **Add file** and no **Delete**. After the administrator deletes it the panel reads "Nothing is attached yet.", the Files cell is blank, and the audit trail keeps that the file was removed.
---

**Hold and recall a counter bill; shift closing (SG-7)**

### TC-SELL-064 — Holding a counter bill and recalling it

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **3** → **Hold (F8)** → in *Hold this bill* type the note `blue shirt, back in 5 min` → **Hold**. Read Inventory for the product. Type a line on the fresh bill and press **Recall**. Clear the line, press **Recall (1)**, pick the bill. Change the quantity to **4** → **Save & print (F9)** with *Received now* 472.
- **Expect:** "SI-… is held. Recall it from the Recall button." and a blank bill opens; the button reads **Recall (1)**. The held bill keeps the stock its saved draft reserved (Reserved 3) and ships nothing. Recall with a line typed is refused: "Hold this bill, or finish it, before recalling another." *Recall a held bill* lists the bill with its note, when it was held and its total; picking it reopens the draft and the button reads **Recall**. The bill then approves for 4 (472.00) like any other, and 4 leave the stock. The delivery note and order the first save raised read CANCELLED, "Bill … was changed before approval.", and a new pair carries the 4; their numbers are spent. Any change to a saved or recalled counter bill's lines (a quantity, a price, a discount, another product) withdraws the pair the save raised and raises a new one, so the bill, the note and the order agree after each save; a save that changes nothing on the lines raises nothing. TC-SELL-088 and TC-SELL-089 have the whole of it.
### TC-SELL-065 — A held bill is never approved

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; one bill held as in TC-SELL-064 and one ordinary draft bill.
- **Steps:** as the prepared **Firm admin**: Sell > Sales Invoices → select the held draft → **Approve**. Tick both drafts → bulk **Approve**. Select the held draft → **Edit**, change the quantity → save. Then **Cancel** the held draft.
- **Expect:** approval is refused: "SI-… is held. Recall it first, then approve it." Bulk approve approves the ordinary draft and reports the held one with the same message. The edit saves and the bill is still held. Cancelling the held draft clears the hold and gives back the stock it reserved (its order is cancelled with it): it no longer counts in **Recall**.
### TC-SELL-066 — Only a draft can be held

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an approved sales invoice and a draft one that is not held.
- **Steps:** **(HTTP)** as the prepared **Firm admin**: `POST /api/v1/sales-invoices/{id}/hold` with `{"note": "x"}` on the approved bill; `POST /api/v1/sales-invoices/{id}/recall` on the draft that is not held; `GET /api/v1/sales-invoices?is_held=true`.
- **Expect:** "Only a draft bill can be held; SI-… is approved." and "SI-… is not held." The list returns only held bills, each with `is_held`, `held_at` and `held_note`.
### TC-SELL-067 — Opening a shift, and one open shift per cashier

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** counter billing; a **Counter Sales** user and a **Sales Manager** user in the firm; neither has a shift open.
- **Steps:** as the **Counter Sales** user: New Invoice. The strip above the scan field reads **No shift open** → **Open shift** → Opening float `500` → Open shift. **(HTTP)** `POST /api/v1/counter-shifts/open` with `{"opening_float": "100"}` again as the same user. Sign in as the **Sales Manager**: New Invoice → Open shift, float `200`. Sell > All Sell screens > Documents > **Counter Shifts**.
- **Expect:** the strip reads "Shift SHIFT-…" (the firm's next number), when it was opened, **0 bills** and **cash expected 500.00**, with **Close shift**. The second request is refused (409): "You already have SHIFT-… open. Close it before opening another." The Sales Manager opens a shift of their own with the next number. Counter Shifts lists both: Cashier, Opened, Float, Expected, Status **Open**. Opening a shift posts nothing. A Counter Sales user may open a shift: it takes the right to raise sales invoices, not the right to approve them.
### TC-SELL-068 — Expected cash is the float and the cash tenders, in the shift of the cashier who made the bill

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; a **Counter Sales** user and a **Sales Manager** user in the firm; the Sales Manager has a shift of their own open with float `200`; no shift open for the Counter Sales user.
- **Steps:** as the **Counter Sales** user: New Invoice → **Open shift**, float `500`. Bill 1: **Walk-in**, 10 `QA-CTR`, *Received now* 1180 Cash, F9. Bill 2: Walk-in, 10 `QA-CTR`, **Split payment** Cash 680 + UPI 500, F9. Bill 3: `QA-C03`, 10 `QA-CTR`, *Received now* blank, Save. Sign in as the **Sales Manager**: Sell > Sales Invoices → **Approve** the three drafts. Sign in as the Counter Sales user again and read the strip; then Counter Shifts → each of the two shifts → **View**.
- **Expect:** Counter Sales cannot approve, so F9 leaves each bill a **draft** for somebody who may; while they are drafts the strip still reads 0 bills. Once the Sales Manager has approved them the **cashier's** strip reads **2 bills** and **cash expected 2,360.00** (500 + 1,180 + 680): a bill paid at the counter is counted in the open shift of the cashier who **made** it, whoever approves it. View on the cashier's shift shows Bills 2, Total billed 2,360.00, CASH 1,860.00, UPI 500.00, CARD 0.00, BANK_TRANSFER 0.00, Opening float 500.00, Cash expected 2,360.00. The Sales Manager's own shift still reads **0 bills** and cash expected **200.00**. The credit bill took no money at the counter and is in neither shift.
### TC-SELL-069 — Closing a shift short posts to Cash Short and Over

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; a shift of the Firm admin's own with float `500` and one walk-in bill of 1,180.00 paid in cash (expected 1,680.00).
- **Steps:** as the prepared **Firm admin**: on the counter bill press **Close shift**. Type *Counted cash* `1670`, Note `End of day` → **Close shift** → **Print report** → Done. Accounts > Journal Entries. Counter Shifts.
- **Expect:** the dialog shows the tenders, Opening float 500.00 and **Cash expected 1,680.00**; typing 1670 reads **Short by 10.00**. After closing: "Shift SHIFT-… is closed.", Cash counted 1,670.00. One journal, reference the shift's number, "Cash short at the close of SHIFT-…": **Dr 6960 Cash Short and Over 10.00 / Cr 1000 Cash 10.00**. The report is a PDF of the takings by mode, the count and the difference. Counter Shifts shows the shift **Closed**, Expected 1,680.00, Counted 1,670.00, Difference −10.00. Closing it again is refused: "SHIFT-… is already closed." The strip reads No shift open. A shift opened after midnight is listed under that day and its report says it was printed on it.
### TC-SELL-070 — Closing over, and closing exact

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; no shift open for the Firm admin.
- **Steps:** as the prepared **Firm admin**: (a) Open shift, float `500`; one walk-in bill of 1,180.00 in cash; Close shift with *Counted cash* `1685`. (b) Open shift again, float `500`; no bill; Close shift with `500`.
- **Expect:** (a) reads **Over by 5.00**; the journal is the other way round: **Dr 1000 Cash 5.00 / Cr 6960 Cash Short and Over 5.00**, its reference this shift's own number. (b) reads **Cash is exact** and posts **no** journal. Both shifts read Closed, with Difference 5.00 and 0.00.
### TC-SELL-071 — Who may close a shift

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** counter billing; a **Sales Manager** and a **Field Sales** user in the firm; an open shift of the **Sales Manager's**.
- **Steps:** **(HTTP)** as the **Field Sales** user (who holds `SALES_INVOICE_CREATE` and not `SALES_APPROVE`): `POST /api/v1/counter-shifts/{id}/close` with `{"counted_cash": "200"}` on the Sales Manager's shift. Then the same as the **Firm admin**. On screen, as Field Sales: Sell > All Sell screens > Documents > Counter Shifts.
- **Expect:** Field Sales is refused (403): "Only the cashier who opened this shift, or somebody who may approve sales, can close it." The Firm admin, who may approve sales, closes it: "Shift closed." Field Sales can see the Counter Shifts list and print a shift report.
### TC-SELL-072 — Shifts are optional, and a held bill does not stop the close

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; no shift open for the Firm admin.
- **Steps:** as the prepared **Firm admin**: (a) with **No shift open**, a walk-in bill of 1,180.00 in cash, F9. (b) Open shift, float `0`; raise a bill and **Hold (F8)** it; press **Close shift**, Counted cash `0`.
- **Expect:** (a) the bill approves and its receipt posts as always; it belongs to no shift. (b) the close dialog warns "1 bill is still held. Recall and finish it, or close the shift and leave it for the next one." and still closes; the held bill stays a held draft. Known limits: a cash receipt is booked to the firm's Cash account whatever account a shift names, and there is no counter refund against a bill, no count by denomination and no handing a shift to another cashier.
---

**Collection follow-up (SG-8)**

### TC-SELL-073 — The collection sheet, by collector

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; an approved bill of 1,180.00 to `QA-C03` with nothing received; a second member of the firm (a **Counter Sales** user).
- **Steps:** as the prepared **Firm admin**: Masters > Customers → `QA-C03` → Edit → set **Collector** (its helper reads "Who chases the dues of this customer; the collection sheet groups by them") to the Counter Sales user → Save. Sell > All Sell screens > Money > **Collection Sheet**. Filter **Collector** to that user; tick **Overdue only**; untick it. **Print sheet**.
- **Expect:** the sheet lists every bill still owing: Collector, Customer, Phone, Bill, Bill date, Due, Days overdue, Outstanding **1,180.00**, and the promise columns blank. The bill is under the chosen collector; a customer with no collector is under its account manager, or nobody. *Overdue only* hides a bill not yet due. Print sheet saves a PDF: "The collection sheet was saved."
### TC-SELL-074 — Recording a promise posts nothing

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an approved bill of 1,180.00 to `QA-C03` with nothing received.
- **Steps:** as the prepared **Firm admin**: Collection Sheet → select the bill → **Record promise**. *Promised on* three days from today, Amount `1180` (offered), Note `will pay by NEFT` → **Save promise**. Sell > All Sell screens > Money > **Payment Promises**. Accounts > Journal Entries. Masters > Customers → the customer.
- **Expect:** "Promise recorded." The sheet's row now shows Promised on, Promised amount 1,180.00 and Promise status **Pending**. Payment Promises lists it: Customer, Bill, Promised on, Amount 1,180.00, Received 0.00, Status Pending, Recorded on today, Recorded by. **No journal** is written and the customer's Outstanding is still 1,180.00.
### TC-SELL-075 — A promise is kept by the money, and un-kept by a reversal

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an approved bill of 1,180.00 to `QA-C03` and a promise for the whole of it, promised for three days from today, both made for this case.
- **Steps:** as the prepared **Firm admin**: Sell > Receipts → Record Receipt: the customer, Amount `500`, Bank, Apply 500 to the bill. Payment Promises. Record a second receipt of `680`, applied to the bill. Payment Promises. Then **Reverse** the second receipt with a reason. Payment Promises.
- **Expect:** after 500: Received 500.00, Status still **Pending** (part of the money does not keep a promise). After 680: Received 1,180.00, Status **Kept**. After the reversal: Received 500.00 and Status back to **Pending**. The receipts post as ever (Dr 1010 Bank / Cr 1100 Trade Receivables); the promise itself posts nothing at any point.
### TC-SELL-076 — Due today, the chase list, and broken

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an approved bill of 1,180.00 to `QA-C03` with nothing received.
- **Steps:** as the prepared **Firm admin**: Collection Sheet → the bill → Record promise, *Promised on* **today**, Amount `1180` → Save promise. Payment Promises → tick **To chase today**; set **Status** to *Due today*. The **next day**, with nothing received, open Payment Promises and the chase list again; then record a new promise on the bill and look once more.
- **Expect:** today the promise reads **Due today** and is on the chase list. The next day it reads **Broken** and is still on the chase list. Once a newer promise is taken on the bill, the broken one leaves the chase list but still reads Broken in the full list. **(HTTP)** `GET /api/v1/collections/sheet?as_of=<tomorrow>` shows the promise **Broken** without waiting.
### TC-SELL-077 — Promises that are refused

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an approved bill of 1,180.00 to `QA-C03` with nothing received; a fully paid bill and a draft bill of the same customer; an approved bill of `QA-C01`.
- **Steps:** as the prepared **Firm admin**: Collection Sheet → the unpaid bill → Record promise with Amount `2000` → Save promise. **(HTTP)** `POST /api/v1/collections/promises` for `QA-C03`: (a) `promised_on` yesterday; (b) `sales_invoice_id` the paid bill; (c) the draft bill; (d) the bill of `QA-C01`.
- **Expect:** 2000 is refused with the dialog still open: "Bill SI-… owes 1,180.00; a promise cannot be for more than that." (a) "A promise is for today or a later day." (the dialog's date picker offers no earlier day). (b) "Bill SI-… owes nothing." (c) "Bill SI-… is not approved, so nothing is owed on it yet." (d) "Bill SI-… belongs to another customer." Nothing is recorded by any of them. A promise dated today is accepted at any hour: today is the firm's own day. A receipt entered after the promise counts toward it whatever date it carries, up to the promised day: yesterday's cash keyed in today keeps the promise. A receipt dated after the promised day does not.
### TC-SELL-078 — A promise is withdrawn, never edited

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a pending promise on an unpaid bill, made for this case.
- **Steps:** as the prepared **Firm admin**: Payment Promises → select the promise → **Withdraw** → leave the reason empty; then give `Customer asked for a week more` → Withdraw. Look for a way to edit or delete a promise. **(HTTP)** withdraw the same promise again.
- **Expect:** an empty reason withdraws nothing. With a reason: "The promise was withdrawn.", Status **Withdrawn**, and the row stays in the list. Withdraw is no longer offered for it, nor for a Kept promise. There is no Edit and no Delete: a changed promise is a withdrawn one and a new one. The repeated request is refused (409): "That promise was already withdrawn." **(HTTP)** withdrawing a Kept promise is refused (422): "That promise was kept: the money promised was received, so there is nothing to withdraw."
### TC-SELL-079 — Who may read the sheet and who may record a promise

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an unpaid approved bill; a **Counter Sales**, a **Read Only** and a **Field Sales** user in the firm.
- **Steps:** as each user in turn: Sell > All Sell screens > Money → Collection Sheet and Payment Promises. **(HTTP)** as Read Only, `POST /api/v1/collections/promises`.
- **Expect:** Counter Sales (who holds `RECEIPT_VIEW` and `RECEIPT_CREATE`) reads both and is offered **Record promise** and **Withdraw**. Read Only (`RECEIPT_VIEW` alone) reads both and is offered neither; the request is refused with 403. Field Sales, who holds neither code, is not offered the two screens.
---

**Turnover rebate to a customer (SG-9)**

For these cases the agreement covers **last calendar month**, and its bills carry an invoice date in that month, so the accounting period of last month must be open. Slabs: from turnover of 1,000 → 1%, from 5,000 → 2%. The rate of the slab reached applies to the whole turnover, before tax.

### TC-SELL-080 — The slab reached sets the rate on the whole turnover

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; a customer `QA-C05` *Rebate Buyer* with no other bills; one approved bill to it of 10 `QA-CTR` at 100 (1,000.00 before tax) dated in last month.
- **Steps:** as the prepared **Firm admin**: Sell > All Sell screens > Documents > **Customer Rebates** → New: **Customer** `QA-C05`, Code `TR-1`, Name `Turnover rebate`, period the first to the last day of last month, **Add slab** From turnover of `1000` Rebate % `1`, Add slab `5000` and `2` → save. Read the row. Approve a second bill to the customer, 40 `QA-CTR` at 100 dated in last month, and Refresh. Open **Statement**.
- **Expect:** "Rebate TR-1 saved." Status ACTIVE, Turnover **1,000.00**, Rate % **1**, Earned **10.00**, Next slab / To next 5,000 and **4,000.00**. After the second bill: Turnover **5,000.00**, Rate % **2**, Earned **100.00**, no next slab. The statement shows the turnover by kind of document (invoiced, returned, credit notes, debit notes) and "Nothing has been settled yet." A bill dated outside the period, a draft, and another customer's bill do not count. Nothing is posted by the agreement.
### TC-SELL-081 — A rebate is accrued once, after its period ends

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the agreement `TR-1` and the two bills of TC-SELL-080, built for this case (turnover 5,000.00, earned 100.00); a second agreement `TR-NOW` for another customer whose period is the **current** month.
- **Steps:** as the prepared **Firm admin**: Customer Rebates → select `TR-NOW` and look at **Accrue**. **(HTTP)** `POST /api/v1/customer-rebates/{id}/accrue` for it. Select `TR-1` → **Accrue** → leave *Accrual date (optional)* blank → Accrue. Accounts > Journal Entries. Approve one more bill dated in last month and Refresh. Try **Edit** and **Cancel** on `TR-1`.
- **Expect:** **Accrue** is disabled while the period is running; the request is refused: "The period runs to … ; accrue it after that, once every bill of the period is in." For `TR-1`: "Rebate TR-1 accrued.", Status **ACCRUED**, Accrued 100.00, To settle 100.00. Journal dated the **last day of the period**, reference `CREBATE-TR-1`: **Dr 5310 Rebates Allowed 100.00 / Cr 2900 Customer Rebates Payable 100.00**; no tax leg. The late bill does not move what was booked, though the statement's *Turnover today* shows it. **Edit** and **Cancel** are disabled on an accrued agreement; the server's words for the same refusals are "A rebate agreement that is accrued cannot be changed." and "… cannot be cancelled."
### TC-SELL-082 — Settling a rebate against the customer's bills

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the accrued agreement `TR-1` of TC-SELL-081, built for this case (100.00 to settle; the customer owes 5,900.00 on two bills).
- **Steps:** as the prepared **Firm admin**: Customer Rebates → `TR-1` → **Settle against bills**: Amount to settle `60`, Reason `September turnover rebate`, type 60 against the first open bill → save. Accounts > All Accounts screens > Books > **Party Adjustments** → the new draft → **Approve**. Journal Entries; Masters > Customers; Customer Rebates → Statement. Then settle `50` more.
- **Expect:** **Settle against bills** is on the toolbar because the Firm admin may manage party adjustments (`PARTY_ADJUSTMENT_MANAGE`); it is shown on that right alone, and is live only for an accrued agreement with something left to settle. The dialog says "… 100.00 left to settle. This drafts a party adjustment that credits the customer's account; it is approved in Party Adjustments." A draft posts nothing. Approving posts **Dr 2900 Customer Rebates Payable 60.00 / Cr 1100 Trade Receivables 60.00**, no tax; the customer's Outstanding falls by 60.00 and the first bill owes 60.00 less in Record Receipt. The agreement reads Settled 60.00, To settle **40.00**, and its statement lists the adjustment. 50 more is refused: "No more than 40.00 is left to settle." on the screen (the server says "The rebate has 40.00 still to settle, so … cannot be set against the customer's account."). A rebate is settled only this way: no credit note is raised and nothing reaches GSTR-1.
### TC-SELL-083 — Reversing an accrual

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the agreement `TR-1` accrued (100.00) and settled by an approved adjustment of 60.00, as in TC-SELL-082, built for this case.
- **Steps:** as the prepared **Firm admin**: Customer Rebates → `TR-1` → **Reverse accrual**. Then Party Adjustments → the adjustment → **Cancel** with a reason. Reverse accrual again. Journal Entries. Then **Accrue** once more.
- **Expect:** the first reversal is refused: "Part of this rebate is already set against the customer's account; cancel those settlements first." Cancelling the adjustment puts the 60.00 back on the customer's account and the agreement reads To settle 100.00. The reversal then works: "Accrual of TR-1 reversed.", Status ACTIVE, and a mirror journal `CREBATE-TR-1-REV`. Accruing again posts a new journal under `CREBATE-TR-1-2`.
### TC-SELL-084 — Two agreements cannot cover the same sales

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** a customer `QA-C05` in the customer group *Wholesaler*; an ACTIVE agreement `TR-1` for the customer covering last month.
- **Steps:** as the prepared **Firm admin**: Customer Rebates → New for the same customer, Code `TR-2`, a period overlapping `TR-1` by one day → save. New for **Customer group** *Wholesaler*, Code `TR-G`, the same month → save. New for the same customer, Code `TR-1`, a month that does not overlap → save. New `TR-3` with two slabs both from `1000`. New `TR-4` whose period ends before it starts.
- **Expect:** `TR-2` is refused: "… already has rebate agreement TR-1 from … to …; two cannot cover the same sales." `TR-G` is refused because a member already has an agreement of its own over those dates: "… is in the customer group Wholesaler and already has rebate agreement TR-1 of its own over these dates; cancel that one or leave the customer out of the group." A repeated code is refused: "A rebate agreement TR-1 already exists." Two slabs at one turnover and a backwards period are refused before anything is saved ("Two slabs cannot start at the same turnover."; "The period must not end before it starts.").
### TC-SELL-085 — An agreement for a customer group

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; a customer group `REBATE-GRP` *Rebate Group* holding two customers, `QA-C06` and `QA-C07`, neither with an agreement; an approved bill of 3,000.00 before tax to the first and 2,000.00 before tax to the second, dated last month; `QA-C03` outside the group.
- **Steps:** as the prepared **Firm admin**: Customer Rebates → New: **Customer group** *Rebate Group*, Code `TR-GRP`, last month, slabs 1,000 → 1% and 5,000 → 2% → save. Statement. **Accrue**. **Settle against bills**: choose *Customer in the group* `QA-C06`, Amount `70`, a reason → save, and approve it in Party Adjustments. **(HTTP)** create a `CUSTOMER_REBATE` party adjustment naming `TR-GRP` for `QA-C03`.
- **Expect:** Turnover **5,000.00** (the two customers together), Rate % 2, Earned **100.00**; the statement has one row per customer, 3,000.00 and 2,000.00. Accrual posts Dr 5310 Rebates Allowed 100.00 / Cr 2900 Customer Rebates Payable 100.00. The settlement comes off `QA-C06`'s account alone; To settle 30.00. For a customer outside the group it is refused: "That rebate agreement is for a customer group this customer is not in."
### TC-SELL-086 — Who agrees a rebate, who settles it, and what it does not do

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** an accrued agreement with something left to settle whose customer still owes money; an ACTIVE agreement, period over, whose customer sold less than the first slab; a **Sales Manager**, an **Accounts** and a **Read Only** user.
- **Steps:** as **Read Only**: Customer Rebates. As the **Sales Manager**: create an agreement, select the accrued one and look for **Settle against bills**. **(HTTP)** as the Sales Manager, create a `CUSTOMER_REBATE` party adjustment naming the accrued agreement. As **Accounts**: look for Customer Rebates in the menu, then Accounts > All Accounts screens > Books > Party Adjustments. As the **Firm admin**: select the accrued agreement and look for **Settle against bills**; **Accrue** the agreement that reached no slab; Reports > Financial → **Customer rebate statement**.
- **Expect:** Read Only sees the list and the Statement and no New. The Sales Manager (who holds `SALES_APPROVE`) may agree, edit, accrue, reverse and cancel, and is **not offered Settle against bills**: the button is shown on `PARTY_ADJUSTMENT_MANAGE` alone, which is not in that role -- whoever promises a rebate does not move the customer's account. The HTTP request is refused all the same: "You do not have permission to perform this action." The Firm admin is offered the button; of the jobs a firm starts with, Firm Administrator and Firm Manager can settle from the screen. The Accounts job holds the code but cannot open Customer Rebates (it holds no right to view sales), so it settles nothing from that screen; it sees the drafted adjustments under Party Adjustments. Nothing earned is not accrued: "Sales of … reached no slab, so there is nothing to accrue. Cancel the agreement instead." The report lists each agreement with Turnover, Rate %, Earned, Accrued, Settled and Balance. Known limits: a rebate carries no GST and raises no credit note (the *Agreed before the sale* tick is kept for the firm's CA); it accrues once, after the period ends, and is settled only by party adjustment.
---

**Added after the fixes of 2026-10-05 (D-SELL-51)**

### TC-SELL-087 — A bill whose maker has no shift open goes to the approver's shift

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; a **Counter Sales** user with **no** shift open; a **Sales Manager** with a shift of their own open, float `200`, and no bill in it.
- **Steps:** as the **Counter Sales** user, with **No shift open**: Walk-in, 10 `QA-CTR`, *Received now* 1180 Cash, F9. As the **Sales Manager**: Sell > Sales Invoices → **Approve** the draft; read the strip on New Invoice. Then as the Counter Sales user **Open shift**, float `500`, and raise a second walk-in bill of 1,180.00 in cash; the Sales Manager approves it. Read both strips and Counter Shifts.
- **Expect:** the first bill's maker has no shift, so it lands in the approver's: the Sales Manager's strip reads **1 bill** and **cash expected 1,380.00** (200 + 1,180). The second bill lands in the cashier's shift: **1 bill**, cash expected **1,680.00**; the Sales Manager's shift stays at 1 bill and 1,380.00. Had neither of them a shift open, the bill would approve as always and belong to no shift (TC-SELL-072).
---

**Counter bills, coupons, paise and returns after the fixes of 2026-10-05 and 06.** Cases TC-SELL-088 to TC-SELL-095 were added on 2026-10-06. Their expectations were driven over HTTP against a running server; the screens have not been walked. Each stands alone and uses the masters above. A **saved** (draft) or **recalled** (held) counter bill opens with its saved lines and, under them, a table for the products added since, with the same **+ add a product (Ctrl+Enter)** row, scan field and pickers as a new bill. A firm that bills at the counter still has an order and a delivery note behind every bill; they are listed under Sell > Sales Orders and Sell > Delivery Notes.

### TC-SELL-088 — A saved counter bill is cut down, grown and given another product before approval

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing (both stages **off**).
- **Steps:** as the prepared **Firm admin**: (1) New Invoice → `QA-C03` → `QA-CTR` quantity **3** → **Save**. Read Inventory for the product, and the newest row of Sell > Sales Orders and Sell > Delivery Notes. (2) **Edit** the draft: quantity **2** → Save; read the same three. (3) Edit: quantity **4** → Save. (4) Edit: on **+ add a product (Ctrl+Enter)** add `QA-DET` quantity **2** → Save. (5) Edit: type a Discount % of **150** on a line → Save. (6) Edit: set the quantity of the `QA-DET` line to **0** → Save. (7) **Approve**. Inventory, Stock Ledger and Journal Entries.
- **Expect:** (1) 354.00, Reserved **3**; an order and a note for 3 stand behind the bill. (2) 236.00, Reserved **2**; the first note and order read **CANCELLED**, "Bill SI-… was changed before approval.", and a new pair carries the 2 (their numbers are spent). (3) 472.00, Reserved 4, a new pair again. (4) the new product is priced as on a new bill (84 less the price list's 2%): total **666.28** (472.00 + 194.28), Reserved 4 of the counter item and 2 of the detergent, and one new note and order hold both lines. (5) refused, and a refused save changes nothing: the bill, its version, the note, the order and the reserved stock are as they were. (6) quantity 0 takes the line off the bill: 472.00 again, the detergent's 2 released. (7) the bill approves for **4**: billed, shipped and out of stock agree. Four leave (`DISPATCH` 4 on the last note); Dr 1100 Trade Receivables 472.00 / Cr 4000 Sales 400.00 / Cr 2220 Output CGST 36.00 / Cr 2230 Output SGST 36.00; cost Dr 5200 Cost of Goods Sold 240.00 / Cr 1200 Inventory 240.00; nothing left reserved. The same edits are taken on a **recalled** held bill, which stays held until it is recalled.
### TC-SELL-089 — A price or a discount changed in a save of its own holds through later edits

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: (a) New Invoice → `QA-C03` → `QA-CTR` quantity **3**, Discount % **5** → Save. Edit: Discount % **0** → Save. Edit: quantity **4**, nothing else → Save → Approve. (b) New Invoice → the same, quantity **3** at **100** → Save. Edit: rate **90** → Save. Edit: quantity **4**, nothing else → Save → Approve. (c) Edit a draft and press Save without changing anything.
- **Expect:** (a) 336.30, then 354.00, then **472.00**: the 0% typed in its own save holds when the quantity changes (it does not fall back to 5%, which would be 448.40). (b) 354.00, then 318.60, then **424.80**: 4 at the 90 typed earlier, not at 100. After every save the bill line, the note line and the order line agree on quantity, price and discount; each price-only or discount-only save withdraws the pair behind the bill and raises a new one, the old pair reading CANCELLED, "Bill SI-… was changed before approval." (c) a save that changes nothing on the lines raises nothing. The same holds on a bill whose rates include GST (3 at 118 inclusive less 5% is 336.30, at 0% 354.00, then 4 is 472.00, still inclusive).
### TC-SELL-090 — Quantity 0 on a line, and a bill that comes to 0.00

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing for (a) to (c); the Sales order and Delivery note stages **on** for (d).
- **Steps:** as the prepared **Firm admin**: (a) New Invoice → `QA-C03` → `QA-CTR` **3** and `QA-SVC` **1** → Save. Edit: quantity of the service line **0** → Save. (b) **(HTTP)** `PUT` a draft counter bill of one line with that line sent back at `current_invoice_quantity` "0"; then with `free_quantity` 1 beside the 0. (c) New Invoice → `QA-C03` → `QA-CTR` **3**, Discount % **100** → Save → Approve. Journal Entries; Inventory; Masters > Customers. (d) **(HTTP)** a sales order line, a delivery note line and an invoice line of quantity 0 with nothing free.
- **Expect:** (a) on screen, quantity 0 on a saved line removes it from the bill: 354.00 remains. (b) refused (422) and nothing is written: "Line 1 bills a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the bill." The bill's version, total, note, order and reserved stock are unchanged. Quantity 0 with 1 free is accepted: nothing billed, one given. (c) a bill that comes to **0.00** approves: it posts no receivable and no journal of its own, the customer's Outstanding does not move, and the goods still leave and are costed (Dr 5200 Cost of Goods Sold 180.00 / Cr 1200 Inventory 180.00). (d) each is refused in the same pattern, naming the line. With the stages on, a delivery note billed at 0.00 leaves the list of notes still to bill.
### TC-SELL-091 — Cancelling a draft counter bill withdraws its order and note and frees its stock

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: New Invoice → `QA-C03` → `QA-CTR` quantity **7** → Save. Inventory. Sell > Sales Invoices → select the draft → **Cancel** with a reason. Inventory, Stock Ledger, Sales Orders, Delivery Notes. Then raise another bill of 7, **Hold (F8)** it, and cancel it while held.
- **Expect:** the draft reserves 7. After the cancel the bill, its delivery note and its order all read **CANCELLED** and nothing is reserved; the Stock Ledger shows `RESERVE` 7 then `UNRESERVE` 7 against the bill's order. A held bill cancelled while held frees its 7 the same way and leaves **Recall**. Cancelling releases only the bill's own reservation: another draft's or another order's stock stays reserved.
### TC-SELL-092 — An offer that may be used once, on two draft counter bills

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing; a promotion of the case's own (Settings > Set up > Pricing > **Promotions** → New): **4%** off, coupon only, code `QAONE`, dated today, **limited to 1 use**. For step (6), the stages **on** and a dispatched delivery note of `QA-C03`.
- **Steps:** as the prepared **Firm admin**: (1) New Invoice → `QA-C03` → `QA-CTR` **3**, **Coupon** `QAONE` → Save. A second bill the same → Save. **Print** the second draft. (2) **Approve** the first. (3) **Approve** the second. (4) **Edit** the second → Save without changing anything → **Approve**. (5) **Cancel** the first, approved, bill with a reason; raise a third bill with the coupon → Save. (6) With the stages on: New Invoice → *Bill this delivery note* → type the coupon → Create draft.
- **Expect:** (1) both drafts save priced with the offer: **339.84** each (354.00 less 4%). A saved counter bill holds **no** claim on the offer: the claim is made when the bill is approved. The printed draft names the offer under **Offers**. (2) the first approves and claims the one use. (3) the second is refused at approval: "Promotion … has been claimed as often as it allows. Re-save the document to price it without." (where the limit is on the code itself, "Coupon … has been used as often as it allows. …"). (4) saved again it is priced without the offer, **354.00**, and approves. (5) cancelling an **approved** bill does not give the use back, because the goods were delivered: the third draft is priced without the offer, 354.00. (6) refused: "A coupon is applied where the price is set: on the order, or on a bill typed straight in. This bill continues documents already priced, so it cannot take one." A coupon is taken on a counter bill when it is typed and on any later edit, and stays when an edit does not mention it.
### TC-SELL-093 — A walk-in bill whose total is not a whole paisa

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; counter billing.
- **Steps:** as the prepared **Firm admin**: (1) New Invoice → **Walk-in** → `QA-DET` quantity **1** (84 less the price list's 2%, plus 18%: 97.1376). Read *Received now*. (2) Change it to **97.13** → **Save & print (F9)**. (3) Change it to **97.15** → F9. (4) Put **97.14** back → F9. Journal Entries; Sell > Receipts. (5) A second walk-in bill of 1 with **Split payment**: Cash **50.00**, UPI **47.14** → F9. (6) A bill of 1 to `QA-C03` with *Received now* blank → Save → Approve; Sell > Receipts → Record Receipt for 97.15 applied to it, then 97.14.
- **Expect:** (1) *Received now* is pre-filled with the **amount payable**, the total rounded to the paisa: **97.14**. (2) refused, and the bill stays a draft: "A walk-in bill is paid in full at the counter: SI-… comes to 97.14 and 97.13 was received. Take the rest, or bill a customer with a record to sell on credit." (3) refused: "97.15 was received against a bill of 97.14. Enter what the bill is paid with; change is handed back." (4) approves: Dr 1100 Trade Receivables 97.14, and the receipt Dr 1000 Cash 97.14 / Cr 1100 Trade Receivables 97.14; nothing is owed. (5) approves with two receipts; 50.00 + 47.13 and 50.00 + 47.15 are refused in the two wordings above. (6) the customer owes **97.14**; a receipt of 97.15 against the bill is refused, "Invoice … has 97.14 outstanding, so 97.15 cannot be allocated to it."; 97.14 clears it to 0.00.
### TC-SELL-094 — A return of goods never billed credits nothing, and the reports say so

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Also needs:** the masters above; the Sales order and Delivery note stages **on**; a GST number on the firm for the GSTR-1 step. For `QA-C03`, all of `QA-CTR` at 100, Discount % `0`: (A) an order of 10, delivered and **billed** (1,180.00, approved); (B) an order of 4, delivered, with **3** billed (354.00, approved); (C) an order of 5, delivered and **never billed**.
- **Steps:** as the prepared **Firm admin**: Sell > Returns & notes > Sales Returns → New Return: (1) against bill A, quantity **2** → Create draft → Approve → Complete. (2) against **delivery note** B, quantity **2** → Create draft → Approve → Complete. (3) against delivery note C, quantity **5** → Create draft; read Reports > Operational → **Sales return register** and the returns summary; then Approve → Complete and read them again. Then Reports > Financial → **GST sales register**; Masters > Customers; Sell > Sales Invoices → New Invoice → *Bill this delivery note*; GST Returns → GSTR-1.
- **Expect:** (1) credited **236.00**: Dr 4100 Sales Returns 200.00 / Dr 2220 Output CGST 18.00 / Dr 2230 Output SGST 18.00 / Cr 1100 Trade Receivables 236.00, and the cost entry. (2) the unbilled unit is taken first: unbilled quantity **1**, credited **118.00** for the one billed unit, cost entered for both; the return names bill B under *Against invoice*. (3) cost entry only: unbilled quantity **5**, credited **0.00**, no `SR-…` credit journal, and the customer's Outstanding does not move. While return C is a draft it adds its stated total, 590.00, to **pending return value** and nothing to **total return value**; completed, it leaves pending and adds nothing. With all three completed, total return value is **354.00**, equal to the register's credited total. The GST sales register has rows of -200.00 and -100.00 taxable and **no** row for C; GSTR-1 CDNR lists the same two, each against its bill. Delivery note C has nothing left to bill, and note B's left-to-bill is down by the unbilled unit returned. Header charges or rounding on a return that credited nothing add 0 to the summary.
### TC-SELL-095 — Reservations are held batch by batch, and a cancel frees only its own

*Added 2026-10-06 after the fixes of 2026-10-05 and 06. **Server side driven** over HTTP; results in `docs/qa/SELLING_API_CHECK_ROUND_4_2026-10-05.md`, `docs/qa/SELLING_API_CHECK_ROUND_5_2026-10-06.md` and `docs/qa/BUYING_SELLING_API_CHECK_ROUND_6_2026-10-06.md`. **The screens are not yet driven.***

- **Preconditions:** a `pharma-firm`, with the delivery note stage **off** for (a) and (b) and **on** for (c). A batch-tracked product with two in-date batches, an **earlier** and a **later** expiry, 10 each, in the default warehouse, and nothing reserved. A customer.
- **Steps:** (a) Counter bill **A**: the product, quantity **4**, batches untouched → Save. Counter bill **B**: quantity **4**, all 4 on the **later** batch → Save. Stock > Batches. **Cancel** B. Stock > Batches. **Approve** A. (b) Counter bill **C**: quantity **4**, picked **1** earlier + **3** later → Save; Stock > Batches. Raise and approve an ordinary bill or order for the **16** that are left. Approve C. (c) With the delivery note stage on: order **X** for 4 (it holds the earlier batch); order **Y** for 4 with **Batch** = the later batch; approve both. Cancel Y. Stock > Batches. Dispatch X.
- **Expect:** (a) A holds 4 of the earlier batch and B 4 of the later. Cancelling B frees the later batch and leaves A's 4 alone (Stock Ledger: `UNRESERVE` 4 on the later batch against B's order); A approves and ships 4 of the earlier batch. (b) C holds **1** on the earlier batch and **3** on the later, exactly as picked; the other document takes only the rest, and C approves and ships 1 + 3. (c) cancelling Y frees the later batch and nothing else; X dispatches from the earlier batch. An order whose stock is reserved on the batch its customer's minimum shelf life allows dispatches from that batch even while another order holds the earlier one. Cancelling an order while a dispatched note stands against it is refused, as before.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 08-S01 | **Sell > Quotations** | Offered to any role holding `SALES_VIEW` or `SALES_QUOTATION_CREATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S02 | **Sell > Sales Orders** | Offered to any role holding `SALES_VIEW` or `SALES_ORDER_CREATE` or `SALES_UPDATE` or `SALES_IMPORT` or `SALES_EXPORT` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S03 | **Sell > Delivery Notes** | Offered to any role holding `SALES_VIEW` or `DELIVERY_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S04 | **Sell > Sales Invoices** | Offered to any role holding `SALES_VIEW` or `RECEIPT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S05 | **Sell > Returns & notes > Sales Returns** | Offered to any role holding `SALES_VIEW` or `SALES_RETURN` or `SALES_UPDATE` or `SALES_APPROVE` or `SALES_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S06 | **Sell > All Sell screens > Documents > Counter Shifts** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S07 | **Sell > All Sell screens > Documents > Customer Rebates** | Offered to any role holding `SALES_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S08 | **Sell > All Sell screens > Documents > Proforma** | Offered to any role holding `PROFORMA_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 08-S09 | **Sell > Returns & notes > Credit Notes** | Offered to any role holding `CREDIT_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
