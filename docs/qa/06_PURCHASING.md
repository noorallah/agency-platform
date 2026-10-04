# Purchasing: order to payment

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

## Buying — order to payment

Four documents: a purchase order, goods receipts against it, a supplier
invoice against a receipt, and a purchase return. **Completing a receipt
posts stock; cancelling a completed one reverses the stock and the journal;
approving an invoice posts the payable; completing a return takes stock back
off.** Everything else is paperwork.

| Preparation | Starts you with |
| --- | --- |
| `buy-ready` | a vendor `QA-V` and a product `QA-B`, 0 on hand |
| `po-approved` | … and an **approved** purchase order for 10 at 100 |
| `po-received` | … and receipts of **4** and **6**, both completed — 10 on hand |
| `po-invoiced` | … and an **approved** supplier invoice for the receipt of 6 (708.00 with GST) |

Purchase orders are Buy > **Purchase Orders**; Goods Receipts and Purchase Invoices
are on the Buy menu and Purchase Returns under Buy > **Returns & notes**;
payments are Buy > **Payments**;
stock is Stock > All Stock screens > Stock > **Inventory** and Stock > **Stock Ledger**. Every
screen reads once when opened: **Refresh** after acting elsewhere.

### TC-BUY-001 — Raising a purchase order, and the approval that cannot be skipped

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Steps**
  1. As the prepared **Firm admin**, Buy > Purchase Orders → **New**: vendor `QA-V`, branch `HO`, warehouse `MAIN`, today; **Add Line**: product `QA-B`, quantity **10**, unit price **100** (the units fill from the product, PIECE) → **Save**. Open it.
  2. Select the draft: look at the toolbar and inside the view.
  3. **Submit**, then **Approve**.
- **Expect**
  - Step 1: status **DRAFT**, number `PO-QA01-HO-2026-2027-…`; the Line Items table names the product as `QA-B — Bought Item qa` and the unit `PIECE`; the Approval banner reads "Submit this draft to send it for approval."
  - Step 2: **Approve is not offered** on a draft — only Submit. **(HTTP)** `POST /api/v1/purchases/{id}/approve` on a draft → **422**, "Only submitted purchase orders can be approved. Submit the order first."
  - Step 3: toasts "… submitted for approval." and "… approved."; status **APPROVED**, the grid updating without the dialog closing.
### TC-BUY-002 — Editing an approved order withdraws the approval

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps:** as the prepared **Firm admin**, select the prepared order → **Edit** → dialog **Editing withdraws the approval** → **Edit anyway**. Type a line remark and change the order remarks → **Save**. Then **Submit** and **Approve** again.
- **Expect:** saved as **DRAFT**; the remark survives reopening; the view's **History** shows the approval withdrawn (audit `purchase.approval_withdrawn`). An edit no longer decides the status — the update body cannot write one. After Submit and Approve: APPROVED again.
### TC-BUY-003 — Receiving part of an order, then the rest

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps**
  1. As the prepared **Firm admin**, Buy > Goods Receipts → **New** → **Purchase Order** picker (approved orders only) → the prepared order. Set Accepted to **4**, warehouse `MAIN` → **Save Receipt** → select the draft → **Complete**.
  2. Buy > Purchase Orders → the order. Stock > All Stock screens > Stock > Inventory and Stock Ledger, filtered to `QA-B`.
  3. Buy > Goods Receipts → New against the same order → Accepted defaults to **6** → Save, Complete.
- **Expect**
  - Step 1: the line arrives with Accepted 10 and "Ordered 10 · already received 0"; after save, "Goods receipt GRN-… created as a draft. Complete it to post the stock."; after Complete, status **COMPLETED**.
  - Step 2: the order reads **PARTIALLY_RECEIVED**; `QA-B` in MAIN holds **4**; the Stock Ledger shows `GOODS_RECEIPT` +4 referencing the GRN.
  - Step 3: the line says "already received 4"; after Complete the order reads **RECEIVED**, MAIN holds **10**, and a second `GOODS_RECEIPT` entry appears.
### TC-BUY-004 — Cancelling a completed receipt undoes its stock and its journal

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Goods Receipts → select the **receipt of 4** → **Cancel**. Then the order, the Inventory row and the Stock Ledger for `QA-B`; Accounts > Journal Entries.
- **Expect:** status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` **−4** against that GRN; MAIN holds **6**; the order drops back to **PARTIALLY_RECEIVED**; the journal shows the reversal, crediting inventory with what the movement removed.
### TC-BUY-005 — A receipt that has been invoiced cannot be cancelled

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Goods Receipts → select the **receipt of 6** (the one the preparation invoiced) → **Cancel**.
- **Expect:** refused — "Goods receipt GRN-… has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes.
### TC-BUY-006 — Returning damaged goods to the supplier

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** → **Goods Receipt** picker (completed receipts only) → the **receipt of 6**. On its line set **Returning** **2**, click the **Damaged** chip → **Save Return** → select the draft → **Approve** → **Complete**. Then Inventory, Stock Ledger, Journal Entries, and Reports > Operational → **Damaged goods returned**.
- **Expect:** after save, "Purchase return PR-2026-2027-… created as a draft. Approving and completing it is what takes the stock off."; after Complete, **COMPLETED**. MAIN holds **8**. The Stock Ledger shows the return of 2 referencing the PR (the API reads `transaction_type: RETURN`). The journal shows the return's entry; the damaged-goods report lists the line. Open the return: product and unit read as code and name, not ids.
### TC-BUY-007 — The purchasing reports have rows

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps:** as the prepared **Firm admin**, Reports > **Operational**: Purchase order register, Orders not yet received, Overdue purchase orders, Orders by supplier, Orders by buyer, Purchases by product.
- **Expect:** each opens with a row count in the header. The register and "not yet received" include the prepared order; by supplier names `Fixture Supplier qa`; by product names `Bought Item qa`. Overdue and by buyer may be empty in QA01 — an empty report reads "Nothing to report", never a blank grid.
### TC-BUY-008 — Paying the supplier

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Buy > Payments → **Record Payment**: **Paid to** `QA-V`; **Amount** the bill's Outstanding (708.00); **Method** Bank; **Oldest first** → **Record payment**. Open Record Payment again for the same vendor.
- **Expect:** toast "PY-… recorded and posted to the ledger." *(The plan said `PAY-`; the series prefix is `PY`.)* The second time, the bill is gone from the list. Journal Entries shows the payment: Dr Accounts Payable / Cr Bank.
---

### TC-BUY-009 — A return the supplier pays back (refund)

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** As *po-received*: a completed receipt of 6 from `QA-V`.
- **Steps:** as the prepared **Firm admin**, Buy > Returns & notes > Purchase Returns → **New** off the **receipt of 6**, return **2**, **Outcome** *Refund* → Save → Approve → Complete. Buy > Payments → **Supplier refunds** → `QA-V` → on the return, **Record refund**: amount **100**, today, Bank → Save. Then **Record refund** again for more than is left. Then **Refunds** → **Reverse** with a reason. Then try **Cancel** on the return while a refund stands (record one again first).
- **Expect:** the credit shows Outcome *Refund*, Refunded 100, Available reduced by 100; Journal Entries has Dr Bank / Cr Accounts Payable. Over-refund is refused naming what is left. After Reverse the credit is whole again and the mirror journal posts. Cancelling the return while a refund stands is refused: "…Reverse the refund first."
### TC-BUY-010 — A return to be replaced reopens the order

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** As *po-received* with the order fully received (receipts of 4 and 6).
- **Steps:** return **2** off the receipt of 6 with **Outcome** *Replacement* → Approve → Complete. Open the purchase order. Then receive 2 more against the order.
- **Expect:** the order reads **Partially received** with 2 pending; the new receipt of 2 is accepted (no over-receipt refusal) and the order reads **Received** again. Change the return's outcome to *Credit* (list → **Change outcome**) before receiving: the order goes back to **Received**.
### TC-BUY-011 — A return off a bill already paid leaves a supplier credit

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** As TC-BUY-008 (the bill paid in full).
- **Steps:** Buy > Returns & notes > Purchase Returns → **New** off the **paid bill**, return 2 → Approve → Complete. Buy > Payments → **Supplier credits** → `QA-V`. Raise another bill and **Apply** the credit to it.
- **Expect:** the paid bill does not reappear in Record Payment; the return appears as a supplier credit for its value; applying it lowers the new bill's outstanding by that much. Deleting `QA-V` is refused while the credit stands.
### TC-BUY-012 — Input credit blocked on a purchase (a car, catering)

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** *buy-ready* with the GST template; a product `QA-CAR`.
- **Steps:** Masters > Products → `QA-CAR` → **Input credit** *Blocked (s.17(5))* → Save. Bill it from a receipt at 18% GST and approve. Open Journal Entries for the bill, and Accounts > GST Returns → GSTR-3B for the month. Then on another bill line set **Input credit** *Eligible* explicitly.
- **Expect:** the bill line shows a **Credit blocked** badge. The journal debits **5450 Input Tax Not Claimable** with the whole tax and **no** input CGST/SGST. GSTR-3B shows the tax in 4(A)(5) and again in **4(B)(1)**, net 4(C) without it. The line set to *Eligible* claims as usual. A user without `PRODUCT_TAX_MANAGE` sees the product's Input credit read-only.
### TC-BUY-013 — A composition supplier charges no GST

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** *buy-ready*; a supplier `QA-COMP` with a GSTIN.
- **Steps:** Masters > Vendors → `QA-COMP` → **GST type** *Composition* → Save. Then set *Unregistered* while the GSTIN is still filled → Save. Order, receive and bill from `QA-COMP` (as Composition).
- **Expect:** *Unregistered with a GSTIN* is refused with the server's message and the form stays open with what was typed. The bill editor shows "This supplier charges no GST; the bill will carry no tax."; the approved bill has tax 0 and claims no credit. A supplier with GST type *Not set* is taxed as before.
### TC-BUY-014 — GSTR-2B reconciliation

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** two approved bills in a month from a supplier with a GSTIN; the sample `docs/qa/tools/gstr2b_sample.json`, edited: `rtnprd` to the month as MMYYYY, `ctin` to the supplier's GSTIN, the two bill numbers, dates and amounts to the two bills' (the sample's second bill carries CGST 5 more than the books on purpose), and one invoice not in the books.
- **Steps:** Accounts > All Accounts screens > Tax filing > **GSTR-2B Reconciliation** → month → **Import 2B file**. Then **Match to bill…** on the *Not in books* row, then **Undo match**. Then Settings > Tax > GST Documents → **Claim input credit** *Only bills matched to GSTR-2B* → GSTR-3B for the month.
- **Expect:** rows read **Matched**, **Different** ("CGST … in 2B, … in the books"), **Not in books**; the "In books, not in 2B" section lists any bill 2B lacks. Importing the month again replaces it. Under *matched only*, 3B claims only matched bills and shows the rest as *Held back — not yet in GSTR-2B*.
### TC-BUY-015 — Reorder from what sold (planning formula)

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** a product with **no** reorder or minimum level typed, 100 received in one warehouse long ago and 90 delivered to customers within the last 90 days (10 left); a second product with a reorder level typed.
- **Steps:** as the prepared **Firm admin**: Settings > Buying > **Purchase Settings** → **Reorder planning** → Open. Note it says the firm plans on typed levels. Reports > Operational → **Below reorder level**. Then choose **From sales**, leave 90 / 7 / 7 / 30 → Save. Open the report again, and Buy > Purchase Orders → "..." → **Below reorder level...**. Try Cover 0 → Save. Open the dialog as a role without *Manage purchase settings*.
- **Expect:** on typed levels the first product is **not** listed. On sales it is listed with **Basis Sales**, **Avg/day 1**, reorder level 14, maximum 44 and **suggested 34** (44 - 10), whole units; the second product keeps **Basis Level** with its typed figures. The dialog names the basis above the grid, and **Raise draft orders** raises a draft for 34. Cover 0 is refused with the range. Without the permission the dialog is read-only. Settings > Platform > System > Audit Logs shows **purchase.reorder_planning_updated**.
### TC-BUY-016 — One quantity picture per order line, and the billing status

*Added 2026-10-02 from the code and the QA suite; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** as *po-invoiced*: an order for 10, receipts of 4 and 6 completed, a bill for the receipt of 6 **approved**.
- **Steps:** as the prepared **Firm admin**, Buy > Purchase Orders → open the order and select its line. Then Purchase Invoices → raise a second bill for the receipt of 4 but leave it in **Draft**; reopen the order. Approve that bill; reopen. Then Purchase Returns → return 2 off the receipt of 6 → Approve → Complete; reopen. Open a **Draft** order beside it.
- **Expect:** after the first bill the header reads *Part billed*, and the side panel's *Received and billed* block says Received 10, Billed 6, Pending 0, **To bill 4**. The draft bill changes nothing (only approved bills count). After approving it: *Billed*, **Complete**, To bill 0. After the return of 2: Returned 2, **To bill 0** still (the return is set against what was kept), and Complete stays. A draft order shows none of the block and no billing chip. Nothing in the editor lets the figures be typed, and saving the order does not send them.
### TC-BUY-017 — A debit note on a bill already paid

*Added 2026-10-02 (decision A4).*

- **Preconditions:** an approved supplier bill of 1,180.00 (1,000 + 18% GST), **paid in full**, and a second approved bill of the same supplier for 500.00.
- **Steps:** Buy > Returns & notes > **Debit Notes** → New against the paid bill: 100 on its line, reason *Price difference* → Save → **Approve**. Pay → New payment for the supplier: look at the supplier credits. Set the debit note's credit against the second bill. Then cancel the debit note. Then raise and approve it again, record a supplier **refund** of 50 against its credit, and try to cancel it.
- **Expect:** approval succeeds (it used to refuse "still owes only 0"). The payment screen lists a credit of **118.00** marked as a debit note; set against the second bill, that bill owes **382.00**. Cancelling the debit note withdraws it -- the second bill owes 500.00 again and the credit is gone. With the refund standing, the cancel is refused ("Reverse that refund…").

### TC-BUY-018 — Reorder orders from the preferred supplier

*Added 2026-10-02 (decision A18).*

- **Preconditions:** two active suppliers, `QA-V1` (who billed the product last, at 100) and `QA-V2` (never billed it); the product below its reorder level; its purchase price 90.
- **Steps:** Masters > Products → open the product → **Preferred supplier** `QA-V2` → Save. Buy > Purchase Orders → "..." → **Below reorder level...**. Then mark `QA-V2` inactive and open the dialog again. Then open the product as a role that cannot see suppliers.
- **Expect:** with `QA-V2` preferred the row names **QA-V2** at **90.00** (the last bill's 100 was QA-V1's, so it does not carry over); **Raise draft orders** raises a draft to QA-V2. With QA-V2 inactive the row falls back to **QA-V1** at 100. Saving the product with QA-V2 inactive and the supplier untouched still works. Choosing an inactive supplier is refused ("Preferred supplier not found, or not active.").
---

### TC-BUY-019 — Supplier rates, catalogue, order multiples and lead times

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a price list scoped to the vendor `QA-V` with a rate for `QA-B`; one completed receipt of the order of 10 (the preparation has two).
- **Steps:** as the prepared **Firm admin**: Masters > **Vendors** → `QA-V` → **Standing discount %** 5 → Save. Settings > Set up > Pricing > **Price Lists** → New, scope *Supplier* `QA-V`, rate 90 for `-B`. Masters > Vendors → `QA-V` → **Catalogue** tab → add `-B`: supplier code `SK-1`, price 80, minimum order 20, **order multiple 10**, pack size, lead time 7 days; also import a catalogue file (Import → *supplier catalogue*). Settings > Buying > **Purchase Settings** → order quantity policy **Warn**, then **Refuse**. Buy > **Purchase Orders** → New for `QA-V`: add `-B` with the price and discount boxes blank, quantity 25; use the hint's **Use N**; save. Look at the expected date, then the vendor's lead-time summary. Reports > Operational → Below reorder level (From sales).
- **Expect:** a blank price and discount are filled from the supplier's terms: the catalogue price ranks between the supplier price list and the product's purchase price, and the supplier code is filled; the standing discount fills a blank discount. Quantity 25 against minimum 20 and multiple 10 shows a hint "use 30"; under Warn the order saves, under Refuse it is refused naming the multiple. The expected date is the order date plus the catalogue lead time. The vendor shows quoted lead time and what the deliveries actually took (average days, late receipts, on-time share), derived from completed receipts; a cancelled receipt stops counting. The reorder planner rounds its suggestion to the multiple and uses the lead time for the sales-based reorder point. Sales price lists ignore supplier-scoped lists. An explicit price or discount of 0 typed on the line is kept.
### TC-BUY-020 — A requisition becomes orders, and an approved order is amended

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a second vendor and a second product with a preferred supplier; a role holding PURCHASE_REQUISITION_CREATE but not PURCHASE_APPROVE.
- **Steps:** as the **Purchasing** user: Buy > All Buy screens > Documents > **Requisitions** → New with two lines (one naming a supplier, one with only a product that has a preferred supplier, then one with neither) → Save → Submit. Try Approve. As the **Firm admin**: Approve → **Convert to orders**. Separately Reports > Operational > Below reorder level → **Raise requisition**. Then open the approved purchase order → **Amend**: change a quantity → Save; open **Revisions**; print.
- **Expect:** a requisition is numbered in its own **PR** series; a line with neither a supplier nor a preferred supplier is refused by name; only an approver sees Approve. Converting raises **one draft purchase order per supplier** priced from the supplier's terms; the requisition becomes ORDERED and is history. Raise requisition from the reorder screen makes a requisition rather than orders. Amend on the approved order keeps it approved, bumps the **revision number**, and keeps the earlier version listed under Revisions; the print titles it as an amendment.
### TC-BUY-021 — Goods held for inspection on receipt

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a user holding PURCHASE_INSPECT.
- **Steps:** as the prepared **Firm admin**: Masters > Products → `QA-B` → switch on **Inspect on receipt** → Save (or the same on its category). Buy > Goods Receipts → receive 10 and complete. Open Stock > All Stock screens > Stock > **Inventory**. Then Buy > All Buy screens > Documents > **Quality Inspection**: pass 6, reject 4 (once written off, once left in quarantine for a return). Cancel a second receipt that is still on hold.
- **Expect:** completing the receipt puts the goods in **quarantine** — owned and valued as received but not sellable or issuable. The Quality Inspection screen lists the held lines; passing releases that quantity to stock; rejecting either writes it off at once or leaves it in quarantine for a purchase return (condition Quarantine). Cancelling a receipt whose lines are still held releases the holds with it. Without PURCHASE_INSPECT the decision is refused.
### TC-BUY-022 — A supplier bill outside tolerance, and an order over budget

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a user with the approval right on purchases and a firm administrator; PURCHASE_APPROVE_OVER_TOLERANCE and PURCHASE_APPROVE_OVER_BUDGET held by the administrator only.
- **Steps:** as the **Firm admin**: Settings > Buying > **Purchase Settings** → **Bill matching**: price tolerance 2% and amount tolerance 50 → Save. Buy > Purchase Invoices → New for the receipt of 6 with the rate 10% above the order → Save → Approve as the **Purchasing manager**, then as the administrator. Next Settings > Buying > **Purchase Budgets** → New for this month, category of `-B`, amount 500; set the policy on Purchase Settings to **Warn**, then **Block**. Raise and approve a purchase order of 10 × 100 as the manager, then as the administrator; open the order's budget panel.
- **Expect:** the bill is **held** at approval and refused naming the breach (price over tolerance) for a user without the over-tolerance right — single and bulk approve alike; the administrator may approve it. The budget is a month, optionally one branch and one category; what it has used is the value before tax of approved orders in that month, derived on every read. Under Warn the approval proceeds with a warning; under Block it is refused for a user without PURCHASE_APPROVE_OVER_BUDGET. The order's budget panel shows budget, used and what the order adds.
### TC-BUY-023 — A payment run and its bank file

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Also needs:** a second approved supplier bill for another vendor with a bank account saved; a cashier user (CASHIER cannot approve a run).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Payment Runs** → New → *Propose* bills falling due by today plus 30 days. Untick one bill; lower another amount; try an amount above what the bill owes. Save the draft. As the **cashier** try Approve. As the administrator: Approve. Download the **bank file**. Cancel a second draft run.
- **Expect:** the proposal lists every supplier bill still owing that falls due by the date. A draft holds the chosen bills and amounts, never more than a bill still owes. Approving needs PAYMENT_RUN_APPROVE (the cashier is refused), records **one payment per supplier** by bank transfer allocated to that supplier's bills, all in one commit: a run that cannot pay every supplier pays none. The bank file is a generic NEFT CSV with one row per supplier from its primary bank account (no bank-specific layout yet). A cancelled draft pays nothing.
### TC-BUY-024 — Supplier performance, price trend and ratings

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** the receipts made on different days from the order's expected date (one late); two users with PURCHASE_VIEW or VENDOR_VIEW.
- **Steps:** as the prepared **Firm admin**: Reports > Operational → **Supplier performance**, then **Supplier price trend**. Masters > Vendors → `QA-V` → **Ratings** → rate each criterion 1-5 → Save; change it and save again; try 0 and 6. Sign in as a second user and rate; open the tab again; **Delete** your own rating.
- **Expect:** the performance report has a row per supplier with receipts, **On time %**, **Rejected %**, **Returned %** and **Short %**; the trend shows month, quantity and **Average rate**. A rating criterion outside 1-5 is refused. The tab shows the averages per criterion, the overall figure, every rating and the reader's own; one live rating per person per supplier — the earlier ones stay as history and the audit row keeps the earlier scores. Deleting removes only your own.
### TC-BUY-025 — Supplier volume rebates

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Supplier Rebates** → New for `QA-V`: a period covering the bill of 708.00 (600 before tax) and two slabs (for example from 0 at 1%, from 500 at 2%). Save. Open it and read the volume, the slab reached and the amount. **Accrue**. Accrue again. **Reverse accrual**. Accrue once more, then Accounts > All Accounts screens > Books > **Party Adjustments** → New of kind *Supplier rebate* naming the agreement. Cancel a second agreement.
- **Expect:** the volume is derived on every read: the supplier's approved bills dated in the period at taxable value, less its completed purchase returns in the period; the **highest slab reached** sets the rate on the **whole** volume (600 at 2% = 12.00). Accrual snapshots the volume, rate and amount with the journal that booked them (Dr *Supplier Rebate Receivable*), and a second accrual of the same period is refused; nothing re-reads the bills afterwards. Reversing the accrual takes the journal off. The rebate is settled by an approved **party adjustment of kind Supplier rebate** that names the agreement (not a debit note, which has to name one bill); what has been settled is the sum of those. The control account exists for new and existing firms.
### TC-BUY-026 — Landed cost spread over received goods

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Also needs:** a freight bill from a transporter (a second vendor) of 1,000; part of the goods already sold so that on hand is less than received (deliver 4 of the 10).
- **Steps:** as the prepared **Firm admin**: Buy > All Buy screens > Money > **Landed Costs** → New: pick the two completed receipts, add a charge (freight, the transporter as billing party, its bill number, 1,000), apportion **by value**. Preview and post. Open the voucher and read each product's split. Then try **by quantity**, **by weight**, and cancel a voucher. Check Accounts > Balance Sheet and the stock valuation.
- **Expect:** the charge's own bill is booked to *Expenses Included in Valuation*; the voucher spreads the total over the receipts' lines by taxable value (or quantity, or weight; the rounding residual goes to the largest line) and splits each share by the product's quantity still on hand: that part **revalues the stock** through a zero-quantity *Landed cost* movement (new average cost), and the rest goes to **cost of goods sold**. Journal: Dr Inventory, Dr Cost of Goods Sold, Cr Expenses Included in Valuation. Cancelling reverses the journal and takes the on-hand value back off at today's quantity. Reading needs PURCHASE_VIEW, posting PURCHASE_APPROVE.
### TC-BUY-027 — Supplier credit set against an opening bill

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Also needs:** an opening supplier bill for `QA-V` (Accounts > All Accounts screens > Books > Opening Balances) of 500, and a supplier credit of 200 (a purchase return refunded as credit, as in TC-BUY-011).
- **Steps:** as the prepared **Firm admin**: apply the supplier credit — the apply dialog lists bills and opening bills (marked "(opening)") — to the opening bill for 200. Open Buy > **Payments** → Record Payment for the supplier. Open the opening bill list. Try to delete the supplier. Then cancel the opening bill.
- **Expect:** the credit is accepted against the opening bill (it used to refuse it). Record Payment shows the opening bill owing **300**; the opening bill list shows the credit counted; the supplier cannot be deleted while it holds an application. Cancelling the opening bill withdraws the credit set against it and the 200 is available again.
### TC-BUY-028 — Free goods to customers, and gifts from a supplier

*Added 2026-10-03 from the code and the build notes; **not yet driven through a preparation** -- drive it and correct the expectation before relying on it.*

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Also needs:** a customer; a user holding SUPPLIER_GIFT_MANAGE; the firm's TDS 194R rules are described in the compliance notes.
- **Steps:** as the prepared **Firm admin**: Masters > Products → `QA-B` → switch **Free issue only** on; try to put it on a quotation or an invoice line with a price. Receive 5 units on a goods receipt with a **Scheme** name on the line. Stock > All Stock screens > Stock > Inventory → Write off 2 with reason *Free to customer* and the customer, and 1 with reason *Sample*. Reports > Operational → **Free goods**. Then Buy > All Buy screens > Money > **Supplier Gifts** → record a gift from the supplier (a fridge, value 20,000, to the firm, then one taken for personal use). Open the **194R summary**. Cancel one.
- **Expect:** a free-issue-only product is refused on a priced sales line by name. The receipt line keeps the scheme; the write-offs post to *Promotional Expense* (not Inventory Adjustment) and carry the customer; the Free goods report shows what came in free, what went out free and what is left. A supplier gift posts Dr the asset or expense account named (or *Drawings* when the owner kept it) and Cr *Supplier Incentives Received*, with no input tax; the gift register links to the receipt line marked "gift, not stock"; the 194R summary totals gifts per supplier; cancelling reverses the journal. Managing gifts needs SUPPLIER_GIFT_MANAGE.

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 06-S01 | **Buy > All Buy screens > Insight > Purchase Dashboard** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S02 | **Buy > All Buy screens > Insight > Purchase Analysis** | Offered to any role holding `PURCHASE_VIEW` or `REPORT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S03 | **Buy > All Buy screens > Insight > Rate Trend** | Offered to any role holding `PURCHASE_VIEW` or `REPORT_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S04 | **Buy > Purchase Orders** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S05 | **Buy > Returns & notes > Debit Notes** | Offered to any role holding `DEBIT_NOTE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S06 | **Buy > All Buy screens > Documents > Requisitions** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_REQUISITION_CREATE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S07 | **Buy > All Buy screens > Documents > Quality Inspection** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_INSPECT`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S08 | **Buy > All Buy screens > Money > Supplier Rebates** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S09 | **Buy > All Buy screens > Money > Principal Claims** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S10 | **Buy > All Buy screens > Documents > Approvals** | Offered to any role holding `SALES_APPROVE` or `PURCHASE_APPROVE`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S11 | **Buy > All Buy screens > Money > Landed Costs** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S12 | **Settings > Buying > Purchase Settings** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S13 | **Buy > Purchase Invoices** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S14 | **Buy > Returns & notes > Purchase Returns** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S15 | **Buy > Goods Receipts** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
