# Purchasing, round 2 -- verifying the walkthrough fixes on QA01

Round 1 (2026-10-04) found D-ROLE-2/3, D-BUY-21..28 and D-UI-4; all were fixed
by #1080-#1096. This round proves each fix on the running app, then carries on
with BUY-012..014 and the 017 GST cases.

**Setup.** Local backend on port 8000 (migrated to `20261004_0304`), phase 2
app (`flutter run -d windows -t lib/main_phase2.dart`). Firm **QA01 "QA
Traders"**. Every user's password is `DemoAdmin@12345`: `admin@`,
`purchasing@`, `purchmgr@`, `warehouse@`, `accounts@`, `readonly@` (all
`@qa01.test`). Supplier `QA-V`, products `QA-B` (cost 100, GST 18%) and `QA-B2`.

Write down every document number as you go -- later steps refer back to them.

## R2-1 Order with a line remark (D-BUY-21) -- `purchasing@`

1. Purchase > Orders > New. Supplier QA-V, branch HO, product QA-B, quantity 10, rate 100.
2. In the line's **Line remark** box type `Deliver to back gate`. Save.
3. Close and reopen the order.

**Expect:** the remark is still on the line. Send for approval.

## R2-2 Approval and history in words (D-BUY-25) -- `purchmgr@`

1. Open the order from R2-1, Approve.
2. Open its **History** tab.

**Expect:** rows read like *Approved · Submitted → Approved · (person's name) ·
04-10-2026 17:38* -- no `purchase.approved`, no capitals, no long id, no ISO
time.

## R2-3 Warehouse receives and completes (D-ROLE-3, D-BUY-22, D-BUY-24) -- `warehouse@`

1. Sign in as `warehouse@`. Home shows **POs to receive** with a figure (not blank).
2. Global search for the order number: the order and (later) receipts are found.
3. Goods Receipts > New on the order: receive **6**. Use **Save & complete**.

**Expect:** no 403; the window closes, the list shows the receipt
**Completed**. Purchase > Orders: the order is *Partially received*; the line
status (if shown in the API/grid) is *Partially received*, received 6, pending 4.
Warehouse still has **no** New on purchase orders and cannot open bills.

## R2-4 Draft receipts named on a new receipt (D-BUY-23) -- `purchasing@`

1. New goods receipt on the same order, quantity 2, **Save** (draft only).
2. Start another new receipt on the same order.

**Expect:** the line says *other draft receipts hold 2 of this line (GRN-…)*;
the quantity starts at 2 (4 due less the 2 drafted), and goes red if you type
more than 2. Delete or cancel the draft afterwards.

## R2-5 Complete from the receipt's own window (D-BUY-22) -- `purchasing@`

1. New receipt for the remaining 4, **Save** only (draft).
2. Open it from the list (view or edit).

**Expect:** the window itself offers **Complete** (and Cancel under More). Complete it there; the order is now *Received*.

## R2-6 Return before billing (D-BUY-26) -- `purchasing@`, then `purchmgr@`

1. Purchase Returns > New off the **first** receipt (6), return **2** of QA-B. Save.
2. As `purchmgr@`, open it and **Complete** from its window.
3. Finance > journal / ledger for the return.

**Expect:** journal **Dr GRNI 200 / Cr Inventory 200** -- no input tax line, no
Trade Payables line. Supplier balance unchanged. Stock of QA-B down by 2.
Try cancelling the first receipt: refused (a return stands against it).

## R2-7 The bill offers only what is left (D-BUY-27, D-UI-7) -- `purchasing@`

1. Purchase Bills > New, supplier QA-V. Press **Choose receipts (n waiting)**.

**Expect:** only receipts with something left to bill. Receipts billed in full
in round 1 (PO-1's, PO-2's) are **not** listed. The first receipt shows **4
left, 472.00** (not 708); the second **4, 472.00**. Document numbers read in full.

2. Tick both. Lines offer 4 and 4. Change the first line to **6** and save.

**Expect:** refused, naming the receipt and line (only 4 left to bill). Put it back to 4, save; supplier invoice number `R2-INV-1`.

3. As `purchmgr@`, open the bill and **Approve** from its window (or Save & approve).

**Expect:** payables 944 (800 + 144 GST), GRNI for this order back to 0.

## R2-8 Return after billing reverses CGST and SGST (D-BUY-28) -- `purchasing@`, `purchmgr@`

1. Return **1** of QA-B off the second receipt (now billed). Complete as `purchmgr@`.
2. Look at the journal.

**Expect:** Dr Trade Payables 118 / Cr Inventory 100 / **Cr Input CGST 9 / Cr
Input SGST 9**. Nothing on `1300 Input Tax`.

## R2-9 Steps in every window -- `purchmgr@`

Open one each: purchase bill (draft), purchase return (draft), and on the sales
side a sales order and a sales invoice.

**Expect:** each window shows its next steps (Approve / Complete / Cancel /
Close as the list offers); a refused step keeps the window open with the
server's message.

## R2-10 Roles that could not work before (D-ROLE-2)

Needs a Field Sales (`SALES_EXECUTIVE`) and a Counter Sales
(`BILLING_EXECUTIVE`) user on QA01 -- add them under Users if missing.

1. Field Sales: New sales order, save, edit it again. **Expect:** allowed; Approve not offered.
2. Counter Sales: New sales invoice, save. **Expect:** allowed; a colleague's draft is not editable.

## R2-11 Small fixes

| # | Check | Expect |
| --- | --- | --- |
| a | Platform admin: create a firm, then open the firm switcher (D-UI-4) | New firm is listed without signing out |
| b | Select text in a document window or an error message; Ctrl+C on a grid row (backlog 83) | Text selects; pasted rows are tab-separated with a header |
| c | Copy icon beside a document number | Number on the clipboard |
| d | Products: **Copy as new product** on QA-B (backlog 82) | Unsaved form, name `QA-B (copy)`, code blank, banner lists what is not copied |
| e | Firms > edit QA01: State (backlog 81) | A dropdown; typing a GSTIN starting `33` proposes Tamil Nadu |
| f | Window at 800x600: goods receipt editor and a sales invoice from a delivery note | Nothing runs off; the buttons scroll sideways |

Bill/return numbering per branch (backlog 84) applies to **new** firms only; QA01 keeps `PI-2026-2027-…`.

## Then -- round 1 cases not yet run

BUY-012, BUY-013, BUY-014 and the BUY-017 GST cases (interstate IGST, blocked
credit, reverse charge), from the QA test book.

Record each result as Pass / Fail with the document number; a fail goes in
`docs/DEFECTS.md` under a new *round 2* heading.
