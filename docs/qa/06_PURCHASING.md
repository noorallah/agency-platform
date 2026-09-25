# Purchasing: order to payment

Part of the QA test suite in `docs/qa/`. Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Generated
on 2026-09-25 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
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

Purchase orders are **Purchases → Purchase Orders**; receipts, invoices and
returns have their own sidebar modules; payments are **Finance → Payments**;
stock is **Inventory → Inventory** and **Inventory → Stock Ledger**. Every
screen reads once when opened: **Refresh** after acting elsewhere.

### TC-BUY-001 — Raising a purchase order, and the approval that cannot be skipped

- **Preconditions:** A firm administrator of QA01, a vendor `QA-V`, and a product `QA-B` *Bought Item* with nothing on hand.
- **Steps**
  1. As the prepared **Firm admin**, Purchases → Purchase Orders → **New**: vendor `QA-V`, branch `HO`, warehouse `MAIN`, today; **Add Line**: product `QA-B`, quantity **10**, unit price **100** (the units fill from the product, PIECE) → **Save**. Open it.
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
  1. As the prepared **Firm admin**, Goods Receipts → **New** → **Purchase Order** picker (approved orders only) → the prepared order. Set Accepted to **4**, warehouse `MAIN` → **Save Receipt** → select the draft → **Complete**.
  2. Purchases → the order. Inventory → Inventory and Stock Ledger, filtered to `QA-B`.
  3. Goods Receipts → New against the same order → Accepted defaults to **6** → Save, Complete.
- **Expect**
  - Step 1: the line arrives with Accepted 10 and "Ordered 10 · already received 0"; after save, "Goods receipt GRN-… created as a draft. Complete it to post the stock."; after Complete, status **COMPLETED**.
  - Step 2: the order reads **PARTIALLY_RECEIVED**; `QA-B` in MAIN holds **4**; the Stock Ledger shows `GOODS_RECEIPT` +4 referencing the GRN.
  - Step 3: the line says "already received 4"; after Complete the order reads **RECEIVED**, MAIN holds **10**, and a second `GOODS_RECEIPT` entry appears.
### TC-BUY-004 — Cancelling a completed receipt undoes its stock and its journal

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Goods Receipts → select the **receipt of 4** → **Cancel**. Then the order, the Inventory row and the Stock Ledger for `QA-B`; Finance → Journal Entries.
- **Expect:** status **CANCELLED**; the ledger shows `GOODS_RECEIPT_REVERSAL` **−4** against that GRN; MAIN holds **6**; the order drops back to **PARTIALLY_RECEIVED**; the journal shows the reversal, crediting inventory with what the movement removed.
### TC-BUY-005 — A receipt that has been invoiced cannot be cancelled

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Goods Receipts → select the **receipt of 6** (the one the preparation invoiced) → **Cancel**.
- **Expect:** refused — "Goods receipt GRN-… has been invoiced, so cancelling it would leave the accrual and the payable disagreeing. Cancel the purchase invoice first, or raise a purchase return." Nothing changes.
### TC-BUY-006 — Returning damaged goods to the supplier

- **Preconditions:** As *po-approved*, plus goods receipts of **4** and **6** against it, both completed: 10 on hand in MAIN.
- **Steps:** as the prepared **Firm admin**, Purchase Returns → **New** → **Goods Receipt** picker (completed receipts only) → the **receipt of 6**. On its line set **Returning** **2**, click the **Damaged** chip → **Save Return** → select the draft → **Approve** → **Complete**. Then Inventory, Stock Ledger, Journal Entries, and Reports → Operational Reports → **Damaged goods returned**.
- **Expect:** after save, "Purchase return PR-2026-2027-… created as a draft. Approving and completing it is what takes the stock off."; after Complete, **COMPLETED**. MAIN holds **8**. The Stock Ledger shows the return of 2 referencing the PR (the API reads `transaction_type: RETURN`). The journal shows the return's entry; the damaged-goods report lists the line. Open the return: product and unit read as code and name, not ids.
### TC-BUY-007 — The purchasing reports have rows

- **Preconditions:** As *buy-ready*, plus an **approved** purchase order for 10 of `QA-B` at 100.
- **Steps:** as the prepared **Firm admin**, Reports → **Operational Reports**: Purchase order register, Orders not yet received, Overdue purchase orders, Orders by supplier, Orders by buyer, Purchases by product.
- **Expect:** each opens with a row count in the header. The register and "not yet received" include the prepared order; by supplier names `Fixture Supplier qa`; by product names `Bought Item qa`. Overdue and by buyer may be empty in QA01 — an empty report reads "Nothing to report", never a blank grid.
### TC-BUY-008 — Paying the supplier

- **Preconditions:** As *po-received*, plus an **approved** supplier invoice for the receipt of 6 (708.00 with GST).
- **Steps:** as the prepared **Firm admin**, Finance → **Payments → Record Payment**: **Paid to** `QA-V`; **Amount** the bill's Outstanding (708.00); **Method** Bank; **Oldest first** → **Record payment**. Open Record Payment again for the same vendor.
- **Expect:** toast "PY-… recorded and posted to the ledger." *(The plan said `PAY-`; the series prefix is `PY`.)* The second time, the bill is gone from the list. Journal Entries shows the payment: Dr Accounts Payable / Cr Bank.
---

## Screen checks

One standard check for every screen in this area. Run it once per screen as the firm administrator, then confirm the access line with a role that lacks the code. Where a detailed case above already covers an action, the check only asks that the screen behaves consistently with it.

| ID | Screen | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| 06-S01 | **Purchases → Dashboard** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S02 | **Purchases → Purchase Orders** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S03 | **Purchases → Analytics** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S04 | **Purchases → Settings** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S05 | **Purchase Invoices** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S06 | **Purchase Returns** | Offered to any role holding `PURCHASE_VIEW` or `PURCHASE_CREATE` or `PURCHASE_UPDATE` or `PURCHASE_IMPORT` or `PURCHASE_EXPORT` or `PURCHASE_APPROVE` or `PURCHASE_CANCEL`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |
| 06-S07 | **Goods Receipts → Receipts** | Offered to any role holding `PURCHASE_VIEW`. Opens without an error; shows its records, or an empty-state message rather than a blank grid. **Refresh** re-reads. Search, filters and column sorting narrow and order the list. Where the screen offers them: **New** refuses a save with a required field empty and names the field, and a complete save appears in the list; **Edit** changes only what was changed; **Delete** is refused while something uses the record, and a deleted record can be restored where **Restore** is offered; **Export** gives a file matching the grid; **Import** with one bad row imports nothing. A role without the code is not offered the screen (see `01_ROLES_AND_ACCESS.md`) | Not run | |

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
