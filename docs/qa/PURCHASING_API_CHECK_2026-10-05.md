# Purchasing: checked through the API, 2026-10-05

Kept apart from `06_PURCHASING.md`, which is regenerated from
`docs/INDEPENDENT_TEST_CASES.md` and would drop a hand-written table.

All 92 buying cases (TC-BUY-001 to 092) driven against the running backend
(`main` at `c87fb6c6`, release 1.3.0) over HTTP, each on the fixture it names,
built by `scripts/test_fixture.py`. Books were read back through the API
(document GETs, `/finance/journal-entries`, the stock ledger, reports), never
from the database. **This covers the server.** Labels, dialogs, toasts and
anything else that exists only on screen were not seen and are marked
"screen, not driven".

Results: **Pass**; **Fail** (a defect, listed below); **Differs** (the case
text is wrong, the application is right); **Partly** (part not driven);
**Not driven**.

| Result | Cases | Which |
| --- | --- | --- |
| Pass | 74 | the rest; 041, 063, 070, 086 and 087 pass with a wording correction |
| Fail | 2 | 021 (BUYQ-1), 075 (BUYQ-8) |
| Differs | 7 | 006, 009, 022, 023, 025, 030, 035 |
| Partly | 8 | 019, 020, 024, 032, 054, 062, 068, 084 |
| Not driven | 1 | 055 |

Fifteen defects are listed under **Defects found by this check**: three High
(BUYQ-1, BUYQ-5, BUYQ-8), four Medium, eight Low. Nothing was fixed and no
application code was changed. Every script that drove a case is in the
session scratchpad (`scratchpad/buying/`, `b01.py` to `b10c.py`, `g01.py`,
`r01.py`) with its log beside it; `fixtures.log` there lists every fixture
run and its suffix.

**Where the data went.** `TEST01` (schema `test_fixtures`) for the cases on the
buying fixtures; firms of this run's own for anything firm-wide:
`T100509T7-G` (`compliance-firm`), `T1005RAR6-R` (`ready-firm`, the generic
checks), `T1005AWVW-E` and `T1005WGOM-E` (`electronics-firm`), `T1005A76G-P`
(`pharma-firm`). No demo or QA firm was written to.

## Cases 001 to 028

| Case | What was driven, with the data used | Result |
| --- | --- | --- |
| TC-BUY-001 | `buy-ready` t1005dk3k. PO-TEST01-HO-2026-2027-000020 for 10 at 100 saved DRAFT, 1,180.00. Approve on the draft answered 422 "Only submitted purchase orders can be approved. Submit the order first."; submit then approve gave APPROVED; history `purchase.created/submitted/approved`; no journal, no stock row | Pass (banner, toasts: screen, not driven) |
| TC-BUY-002 | `po-approved` t1005wc59, PO-…-000022. PUT with a line remark and order remarks answered 200 and DRAFT; a `status: APPROVED` sent in the same body was ignored; the line kept its id; history gained `purchase.updated` and `purchase.approval_withdrawn` (same instant); submit and approve gave APPROVED again | Pass (the "Edit anyway" dialog: screen) |
| TC-BUY-003 | `po-approved` t1005reu8, PO-…-000023. GRN-…-000036 for 4: draft moved no stock; completed, stock 4, order PARTIALLY_RECEIVED, ledger `GOODS_RECEIPT` +4, journal Dr 1200 400.00 / Cr 2300 400.00. GRN-…-000037 for 6: stock 10, order RECEIVED, Dr 1200 600.00 / Cr 2300 600.00. One more unit refused 422 "Goods receipt exceeds allowed quantity for PO line 1." | Pass |
| TC-BUY-004 | `po-received` t10053ubp. GRN-…-000038 (the 4) cancelled: CANCELLED, ledger `GOODS_RECEIPT_REVERSAL` -4, stock 6, order PARTIALLY_RECEIVED, original journal REVERSED and `GRN-…-000038-REV` Dr 2300 400.00 / Cr 1200 400.00, line's `inventory_transaction_id` cleared | Pass |
| TC-BUY-005 | `po-invoiced` t1005fzct. Cancel of GRN-…-000041 (billed on PI-2026-2027-000015) refused 422 with the case's exact words; `version` 4 before and after; stock still 10 | Pass |
| TC-BUY-006 | `po-received` t10053ubp. PR-2026-2027-000010, 2 off GRN-…-000039, `is_damaged`, approved and completed: stock down by 2, ledger `RETURN` 2, `grand_total` 236.00, the damaged report lists the line. **Journal is Dr 2300 Goods Received Not Invoiced 200.00 / Cr 1200 Inventory 200.00**, not the case's Dr 2100 236.00 / Cr 1200 200.00 / Cr 1300 36.00 | Differs: the receipt was never billed, and since D-BUY-26 a return before billing moves only GRNI and stock at cost (D-BUY-31 keeps the 236.00 on the document). The case's Data line is the pre-D-BUY-26 posting |
| TC-BUY-007 | `po-approved` t1005bngn, PO-…-000021. `/purchases/reports/register`, `pending`, `by-vendor`, `by-product` all list the fixture's order, supplier and product; `overdue` and `by-buyer` answer 200 with no rows | Pass ("Nothing to report" wording: screen) |
| TC-BUY-008 | `po-invoiced` t1005fzct. `/payments/parties?search=` lists T1005FZCT-V; PY-2026-2027-000004 of 708.00 by bank allocated to PI-2026-2027-000015: outstanding list empty afterwards, bill still APPROVED, journal Dr 2100 708.00 / Cr 1010 708.00 | Pass |
| TC-BUY-009 | (a) As written, `po-received` t1005odt3: PR-2026-2027-000011, 2 off the unbilled receipt, outcome REFUND, posts Dr 2300 200.00 / Cr 1200 200.00 and leaves **no supplier credit**; a refund is refused 422 "…leaves no credit on the supplier's account…". (b) `po-invoiced` t1005bj4j with the bill paid 708.00 first: PR-2026-2027-000012 posts Dr 2100 236.00 / Cr 1200 200.00 / Cr 1320 18.00 / Cr 1330 18.00; credit 236.00; refund 100 posts Dr 1010 100.00 / Cr 2100 100.00 (`PR-…-000012-RF1`), available 136.00; 500 more refused "has only 136.00 of credit left to be paid back."; cancelling the return refused "…Reverse the refund first."; reversing restores 236.00 and posts the mirror | Differs: the fixture must be `po-invoiced` with the bill paid. Off `po-received` nothing was billed, so nothing is owed back (D-BUY-26). Everything else passes on (b) |
| TC-BUY-010 | `po-received` t1005ny32. PR-2026-2027-000013, 2 off the 6, REPLACEMENT: order PARTIALLY_RECEIVED. Outcome to CREDIT: RECEIVED, and a receipt of 2 refused. Back to REPLACEMENT, GRN of 2 completed: RECEIVED, 10 on hand; one more refused | Pass |
| TC-BUY-011 | `po-invoiced` t1005cvcx. Bill PI-…-000017 paid 708.00; PR-2026-2027-000014, 2 off the bill: Dr 2100 236.00 / Cr 1200 200.00 / Cr 1320 18.00 / Cr 1330 18.00; nothing outstanding; supplier credit 236.00. New bill PI-…-000018 590.00; credit applied: owes 354.00, credit used up. Deleting the vendor refused ("is owed 354.00, has 1 open bill…") | Pass, with a note: the vendor delete was refused for the open bill; the credit had been used up by then, so "refused while the credit stands" on its own was not isolated |
| TC-BUY-012 | `buy-ready` t1005af45. Product T1005AF45-CAR `itc_eligibility` BLOCKED; bill PI-…-000019 of 1 at 1,000: Dr 2300 1,000.00, Dr 5450 Input Tax Not Claimable 180.00 / Cr 2100 1,180.00, no input CGST/SGST. Bill PI-…-000020 with the line set ELIGIBLE: Dr 1320 90.00, Dr 1330 90.00. GSTR-3B cannot be read on TEST01 ("This firm has no GST number, so it has no return to file."), so the same bill was raised on the GST-registered firm T100509T7-G (PI-T100509T7-G-HO-2026-2027-000001): `eligible_itc` 90.00 + 90.00, `itc_reversed_blocked` 90.00 + 90.00, `net_itc` 0.00 | Pass (the badge, and the read-only field for a user without PRODUCT_TAX_MANAGE: screen). The case needs a firm with a GSTIN for its 3B step |
| TC-BUY-013 | `buy-ready` t1005if0d. Vendor T1005IF0D-COMP with a GSTIN, COMPOSITION. UNREGISTERED with the GSTIN kept refused 422 "An unregistered supplier cannot have a GST number; clear it or choose the registered type." Order, receipt and bill PI-…-000021 for 3 at 100 carry tax 0.00, total 300.00, Dr 2300 300.00 / Cr 2100 300.00. The fixture's own (not set) supplier is taxed: 354.00 | Pass (the editor's note: screen) |
| TC-BUY-016 | `po-invoiced` t1005rluq. Order line after the bill of 6: received 10, `invoiced_quantity` 6, `to_invoice_quantity` 4, `billing_status` PARTIALLY_INVOICED, `is_complete` false. A draft bill for the 4 changes nothing; approved: INVOICED, complete, to bill 0. PR-…-000015 returns 2: returned 2, to bill 0, still complete. A draft order reads NOT_INVOICED. Sending `received_quantity` on the update is refused 422 (extra field) | Pass |
| TC-BUY-017 | `buy-ready` t10058vny. Bills PI-…-000027 1,180.00 (paid) and PI-…-000028 590.00 (the case says 500.00). DBN-TEST01-HO-2026-2027-000003 for 100 approved on the paid bill: Dr 2100 118.00 / Cr 5400 100.00 / Cr 1320 9.00 / Cr 1330 9.00; credit 118.00 marked DEBIT_NOTE; applied, the second bill owes 472.00 (590 - 118); cancelled, it owes 590.00 again and the credit is gone, journal mirrored. Second note with a refund of 50: cancel refused "The supplier paid back 50.00 against …'s credit. Reverse that refund before cancelling the debit note." | Pass |
| TC-BUY-014 | Own firm `compliance-firm` T100509T7-G (GSTIN 33FXGST6418A1Z5), supplier V14-FABC (33AAACV1414A1Z5). Bills PI-…-000002 and 000003 (708.00 each) and 000004 (236.00). 2B file with the two bills (the second with CGST 59) and `NOT-IN-BOOKS-1`, imported for `2026-10`: rows MATCHED, DIFFERENT, NOT_IN_BOOKS; `in_books_only` lists bill 000004. Imported again: still 3 documents. Match the not-in-books row to bill 000004: MANUAL; undo: NOT_IN_BOOKS. `itc_claim_basis` MATCHED_ONLY: 3B `itc_awaiting_2b` 72.00 + 72.00, net 54.00 + 54.00; set back to ALL | Pass. Note: the API takes the period as `2026-10`; the file's own `rtnprd` stays `102026` |
| TC-BUY-015 | Same firm. Product RS-3E8E: 100 opening, 90 sold and dispatched, no level typed; product RL-F498 with reorder level 10, maximum 25, 5 on hand. On LEVELS only RL-F498 is listed. On SALES (90/7/7/30): RS-3E8E basis SALES, avg/day 1, reorder level 14, maximum 44, suggested 34; RL-F498 keeps basis LEVEL. Cover 0 refused 422 (>= 1). Draft raised for 34 (PO-…-000005) once a supplier was named; the row then shows 34 on order, suggested 0. Audit `purchase.reorder_planning_updated` | Pass (read-only dialog for a role without the permission: screen) |
| TC-BUY-018 | Same firm. QV1-10A0 billed P18-D47A at 100; QV2-B30F never; purchase price 90; reorder level 10. No preferred: QV1 at 100. Preferred QV2: QV2 at 90.00, draft raised to QV2. QV2 inactive: falls back to QV1 at 100. Saving the product with QV2 inactive and the supplier untouched: 200. Choosing the inactive supplier on another product: 422 "Preferred supplier not found, or not active." | Pass |
| TC-BUY-019 | Same firm, suppliers V19-…/V19B-…. Blank price and discount on an order line: product price 100 with the standing 5% (PO-…-000011); with a catalogue row at 80 (code SK-1, lead 7 days): 80, SK-1, 5%, expected date order date + 7 (PO-…-000015); with a supplier price list at 90: 90, and the discount is the list's 0% (PO-…-000016). Typed discount 0 kept (PO-…-000013); typed price 0 kept (PO-…-000014). Quantity 25 against minimum 20, multiple 10: preview hint "…30 would do"; WARN saves, REFUSE answers 422 "The supplier's order terms are not met -- line 1: 25 is off the supplier's terms (minimum 20, in multiples of 10); 30 would do."; 30 is accepted. Lead-time summary: quoted 7, receipts 1, on-time 100%; after cancelling the receipt, receipts 0 | Partly. Not driven: the catalogue file import (its template answers), the reorder planner rounding to the multiple, and a sales line ignoring the supplier list. **Case text:** with a supplier price list in force the standing discount does not fill the blank -- the list's own discount (0) does, because a price list outranks a standing rate |
| TC-BUY-020 | `po-approved` t10056geb, a *Purchasing* user hired from the job template. Requisition PR-2026-2027-000017 with a line naming T10056GEB-V and a line whose product prefers T10056GEB-V2: submitted by the Purchasing user, whose Approve answered 403; approved by the admin; convert raised PO-…-000042 (V, 5 at 100) and 000043 (V2, 3 at 100), both DRAFT with the requisition number as reference; requisition ORDERED. A requisition with a third line naming no supplier (PR-2026-2027-000016) **saves, submits and approves**, and is refused at convert: "Name a supplier for T10056GEB-B3 -- neither the line nor the product names one." Amend of the approved PO-…-000041 (10 to 12, with a reason): still APPROVED, revision 1, 1,416.00; revision 0 kept at 1,180.00; amend with no reason 422; print answers 200 | Partly. What was driven passes, with BUYQ-3 (the number). Not driven: *Raise requisition* from the reorder screen (the product was not below its level), and the amendment title on the print |
| TC-BUY-021 | `po-approved` t1005iu0l, product set `inspection_required`. GRN-…-000085 of 10: sellable 0, quarantine 10, journal Dr 1200 1,000.00 / Cr 2300 1,000.00. A Read Only user's decision: 403. Passed + rejected must equal the 10 held (6 + 2 refused). Pass 6, reject 4 WRITE_OFF: sellable 6, quarantine 0, Dr 5500 Inventory Adjustment 400.00 / Cr 1200 400.00. Second receipt GRN-…-000086: pass 6, reject 4 RETURN: sellable 12, quarantine 4. Purchase return PR-2026-2027-000018 of those 4 (condition QUARANTINE, rejected 4): **sellable 8, quarantine still 4**. Third receipt GRN-…-000087 of 5 cancelled while on hold: quarantine back to 4, nothing pending | **Fail: BUYQ-1.** The rest passes |
| TC-BUY-022 | Own firm T100509T7-G (the settings are firm-wide), tolerance 2% and 50.00. Bill PI-…-000009 at 110 against an order at 100 (60.00 over). A user on a custom role holding PURCHASE_APPROVE without the over-rights: single approve 403 and bulk approve REFUSED, both "…is priced past the firm's tolerance over its order -- line 1: billed at 110.00 against 100.00 ordered (10.0% over, tolerance 2.0%); the bill runs 60.00 over its order's prices (tolerance 50.00). Approving it needs … (PURCHASE_APPROVE_OVER_TOLERANCE), or correct the bill."; the bill stays DRAFT; the admin approves. A bill at 101 passes. Budget 500 for October and the product's category: used is approved orders before tax (1,200.00), derived on each read; WARN approves; NEEDS_APPROVAL refuses the same user 403 "…takes a purchase budget past its amount (… 3200.00 of 500.00). Approving it needs … (PURCHASE_APPROVE_OVER_BUDGET)."; bulk the same; the admin approves; the panel shows amount, used, this order, available | Differs on who: **a user hired as *Purchase Manager* approved both** (bill PI-…-000006 and the over-budget orders), because the seeded PURCHASE_MANAGER role holds both over-rights. The refusal needs a custom role. The policy is called NEEDS_APPROVAL on the server, not Block |
| TC-BUY-023 | `po-invoiced` t1005zrwd plus supplier T1005ZRWD-VB with a bank account and bills PI-…-000030 (590.00) and 000031 (236.00). Proposal to today + 30 lists all three. A line of 9,999 refused "PI-2026-2027-000030 owes 590.00, not 9999." Run PRN-2026-2027-000001: 708.00 + 400.00 + 236.00. Cashier approve: 403. Admin approve: PY-…-000009 708.00 to V and PY-…-000010 636.00 to VB, both bank transfer, Dr 2100 / Cr 1010; VB's bill then owes 190.00. A cancelled draft pays nothing. Bank file of that run: **422 "These suppliers have no bank account to pay into: Fixture Supplier t1005zrwd."** A run of VB alone (`buy-ready` t1005r4hz, PRN-…-000003, 826.00): CSV, one row, `T1005R4HZ-VB,Supplier VB,50100123456789,HDFC0001234,826.00,05/10/2026,NEFT,…` | Differs: the fixture's own supplier has no bank account, so the run as the case builds it has no bank file at all; give `<SUFFIX>-V` a bank account first or untick its bill. Everything else passes |
| TC-BUY-024 | `po-received` t10050g38. Supplier performance row: receipts 2, on-time % blank (no expected date), rejected 0.0, returned 0.0, short 0.0. Price trend (`po-invoiced` t10058bb6, needs `vendor_id`): 2026-10, quantity 6, average rate 100.00. Rating 4/3/5/4/2 saved, changed to 5/…; 0 and 6 refused 422; a second user's rating: count 2, averages and overall 2.9, `mine` is the reader's; the second user deletes only their own (count 1). Audit `vendor.rated` x3, `vendor.rating_withdrawn` | Pass. Not driven: a late receipt (every fixture receipt is dated today, the order has no expected date) |
| TC-BUY-025 | (a) As written, `po-invoiced` t10051bb0, period 1 to 31 Oct 2026: volume 600.00, rate 2%, earned 12.00 read correctly, but **Accrue is refused** "The period runs to 31 Oct 2026; accrue it after that, once every bill of the period is in." (b) `buy-ready` t1005esss, bill PI-…-000037 dated 2026-10-04, period 1 to 4 Oct, agreement RB-83FB: accrue posts `REBATE-RB-83FB` Dr 1410 Supplier Rebates Receivable 12.00 / Cr 4320 Supplier Incentives Received 12.00; second accrual refused; reverse mirrors it; accrue again posts `REBATE-RB-83FB-2`; party adjustment PA-2026-2027-000001 of kind SUPPLIER_REBATE approved: Dr 2100 12.00 / Cr 1410 12.00, settled 12.00, the bill owes 696.00; 5.00 more refused. A second agreement cancelled. Control account 1410 mapped | Differs: an agreement is accrued only after its period has ended, so the case needs a period already over (and a bill dated inside it). All else passes on (b) |
| TC-BUY-026 | `po-received` t1005r9gq and t1005ucjx, 4 of the 10 sold. Voucher LCV-2026-2027-000001, freight 1,000 by VALUE over both receipts: shares 400.00 and 600.00; to stock 600.00, to COGS 400.00; journal Dr 1200 600.00, Dr 5200 400.00 / Cr 5210 Expenses Included in Valuation 1,000.00; two zero-quantity `LANDED_COST` movements; valuation 6 at 100 = 600.00 becomes 6 at 200 = 1,200.00. Cancel: journal mirrored, valuation 600.00 again. QUANTITY posts; WEIGHT refused (no product has a weight). Read Only lists (200) and cannot post (403); Purchasing (no PURCHASE_APPROVE) 403 | Pass. Low: the journal reference reads `LCV-LCV-2026-2027-000001` (BUYQ-4) |
| TC-BUY-027 | `buy-ready` t1005gzxg. Opening bill OB-65BC of 500.00; a bill of 1,180.00 paid and 2 returned off it (credit 236.00). 200 applied to the opening bill: Record Payment shows "OB-65BC (opening)" owing 300.00; the opening bill list reads paid 200.00; deleting the supplier refused; cancelling the opening bill gives the 236.00 back whole | Pass |
| TC-BUY-028 | `po-approved` t1005cfqc and t1005r4xf, product set `free_issue_only`. A priced sales order line and a priced quotation line: 422 "Free-issue goods are given away, never sold at a price: …". Receipt of 5 keeps `scheme_name`. Write-off FREE_TO_CUSTOMER with no customer refused; with one, WO-2026-2027-000001 of 2: Dr 6940 Promotional Expenses 200.00 / Cr 1200; SAMPLE of 1: 100.00 the same way. Free goods report: RECEIVED 5 (scheme named), GIVEN 2 to the customer and 1 sample, ON_HAND 2. Gifts GIFT-2026-2027-000001 (20,000, ASSET): Dr 1500 / Cr 4320 Supplier Incentives Received; 000002 (30,000, OWNER): Dr 3100 Drawings / Cr 4320; 194R summary 2 gifts, 50,000.00, over threshold; cancel reverses the journal; a Purchasing user is refused 403 | Pass |

## Cases 029 to 053

TC-BUY-029 onward had never been run. On `TEST01` the unfiltered payables
books check reads a difference of **-708.00** that is not from this run: bill
PI-2026-2027-000003 of supplier T09187AT1-V was cancelled on 2026-09-18 and
its journal still stands (data from before a fix; see "Not verified").

| Case | What was driven, with the data used | Result |
| --- | --- | --- |
| TC-BUY-029 | `po-invoiced` t10057evo, PI-2026-2027-000038. `GET /purchase-invoices/reports/gst-register` for the month: type Bill, GSTIN blank, taxable 600.00, CGST 54.00, SGST 54.00, IGST 0.00, total tax 108.00, not claimable 0.00, reverse charge 0.00, capital goods tax 0.00, total 708.00. Draft bill PI-…-000039 not listed; approved, listed; cancelled, gone | Pass |
| TC-BUY-030 | Same fixture. **The fixture's product carries no HSN**, so the bill of 6 sits in the blank-HSN row with every other fixture product (118 units, 25 bills that day). A product of its own with HSN 84394962, 6 at 100: row quantity 6, taxable 600.00, CGST 54.00, SGST 54.00, total tax 108.00, bills 1. A product with no HSN goes to the blank row. **Unit is blank on every row** | Differs (the fixture product has no HSN) and BUYQ-6 (the unit) |
| TC-BUY-031 | `po-received` t1005hl11. PI-2026-2027-000042 with the line BLOCKED: register CGST 54.00, SGST 54.00, total tax 108.00, **not claimable 108.00**; journal Dr 2300 600.00, Dr 5450 108.00 / Cr 2100 708.00 | Pass |
| TC-BUY-032 | `po-invoiced` t10057fqj. DBN-TEST01-HO-2026-2027-000005 (100) and PR-2026-2027-000020 (2 off the billed receipt): register rows Debit note -100.00 / -9.00 / -9.00 and Purchase return -200.00 / -18.00 / -18.00, both "against" PI-2026-2027-000043 and dated today. PR-2026-2027-000021 off the unbilled receipt of 4 is not listed | Pass. Not checked: the HSN row falling by the same amounts (the fixture product shares the blank-HSN row) |
| TC-BUY-033 | `po-invoiced` t10059y6f. `GET /purchase-invoices/reports/payables`: the supplier's row 708.00 in 2026-10 and 708.00 total; columns older, six months, later, credits, total; narrowed to the supplier the total is 708.00 and the books check reads 708.00, difference 0.00. By due date the 708.00 stays in October (the fixture's bill has no terms) | Pass for the supplier. The firm-wide check differs by the pre-existing 708.00 above |
| TC-BUY-034 | Same fixture. PY-2026-2027-000013 of 200.00: Owed 508.00; Paid 200.00 in October, its books check 0.00; Owed with a branch: note "Narrowed to a branch: advances and refunds name no branch, so there is no books check."; Paid with a branch refused 422 "A payment names no branch, so the Paid view cannot be narrowed to one. Clear the branch filter." | Pass |
| TC-BUY-035 | `po-received` t1005t7de. PR-2026-2027-000022, 1 off the unbilled receipt of 4: Dr 2300 100.00 / Cr 1200 100.00, **no payable**; bill PI-…-000045 708.00. Payables row: 708.00, **Credits 0**, total 708.00; no supplier credit. Then the bill paid and PR-…-000023 returns 1 off it: Credits -118.00, total -118.00 | Differs: a return off a receipt no bill names posts nothing to 2100 (D-BUY-26), so it is not a credit. Credits fill from a return off a bill already paid, or a debit note |
| TC-BUY-036 | `po-received` t1005bmbs. Bill PI-2026-2027-000046 approved with `{"payment": {"method": "CASH"}}`: "Bill approved and payment PY-2026-2027-000015 of 708.00 recorded.", dated the bill's date, allocated in full, nothing outstanding. Journals: Dr 2300 600.00, Dr 1320 54.00, Dr 1330 54.00 / Cr 2100 708.00; Dr 2100 708.00 / Cr 1000 708.00 | Pass |
| TC-BUY-037 | `po-received` t1005zd0o. PI-2026-2027-000047: 800 refused 422 "Bill PI-2026-2027-000047 owes 708.00, so 800 cannot be paid against it now. Record an advance through Payments."; the bill is still DRAFT with no journal. 300 by bank, reference NEFT-QA-0300: APPROVED, PY-…-000016, owes 408.00, Dr 2100 300.00 / Cr 1010 300.00 | Pass |
| TC-BUY-038 | `po-received` t1005bmbs. PY-2026-2027-000015 reversed: bill still APPROVED, owes 708.00, `PY-…-000015-REV` Dr 1000 708.00 / Cr 2100 708.00 | Pass |
| TC-BUY-039 | `po-received` t100579ea, a user hired as *Purchase Manager*. Approve with a payment: 403 with the case's exact words, the bill stays DRAFT. Plain approve: APPROVED, owes 708.00. `POST /payments` by the same user: 403 | Pass |
| TC-BUY-040 | `po-invoiced` t1005lqpx, approved bill PI-2026-2027-000050. List empty; a PDF with a caption and a PNG attached (201); content comes back byte for byte; the list row's `attached_file_count` 2, then 1 after the delete (204); audit `document_file.attached` x2, `document_file.removed` | Pass |
| TC-BUY-041 | Same bill. `notes.txt`: 422 "Only PDF, JPG and PNG files may be attached; 'notes.txt' is not one by its name." Text renamed `.pdf`: 422 "'renamed.pdf' is not a PDF, JPG or PNG file by its contents." 10 MB + 87 bytes: 422 **"The file is larger than 10 MB, the most it may be."** Nothing added | Pass; the size wording is the server's (see corrections) |
| TC-BUY-042 | `po-received` t1005fe6y, completed GRN-…-000113. PNG attached, `attached_file_count` 1. Read Only lists and opens it; add and delete answer 403. A *Warehouse* user adds one (201) | Pass ("Save first to attach files": screen) |
| TC-BUY-043 | `buy-ready` t10051ztq, supplier T10051ZTQ-T0E0B (PAN AAACF7485G, 194C). Bill PI-2026-2027-000051, 400 at 100 = 47,200.00. `tds-proposal`: 194C, 2%, basis OTHER, crossed SINGLE, due 800.00, deducted 0.00, proposed 800.00. Approved blank: owes 46,400.00; Dr 2300 40,000.00, Dr 1320 3,600.00, Dr 1330 3,600.00 / Cr 2100 46,400.00, Cr 2700 800.00. A bill of 28,000 with 5,000 of charges proposes 660.00 | Pass |
| TC-BUY-044 | `buy-ready` t1005l55x, supplier T1005L55X-T3D2A. Bills PI-…-000053 (20,000): nothing; 000054 (40,000): 800.00, SINGLE; 000055 (50,000): 1,400.00, ANNUAL. TDS deducted report: 800.00 + 1,400.00 = 2,200.00 | Pass |
| TC-BUY-045 | `buy-ready` t1005kh77. No PAN: 20%, 8,000.00, owes 39,200.00. Individual / HUF yes: 1%, 400.00. Unset with PAN AAAPN6665F (fourth letter P) and AAAHL3613G (H): 1%, 400.00 each | Pass |
| TC-BUY-046 | `buy-ready` t10055e0r. 194J supplier: 25,000 proposes nothing; 10,000 takes the year to 35,000: 10%, 3,500.00, bill 11,800.00 owes 8,300.00, Cr 2700 3,500.00. Technical-services supplier, 40,000: 2%, 800.00 | Pass |
| TC-BUY-047 | `buy-ready` t1005h05h and t1005ve4k. Hint for 50,000 paid ahead: 194C, 1,000.00; for 20,000: nothing. Advance PY-2026-2027-000017 with TDS 1,000: Dr 2100 50,000.00 / Cr 1010 49,000.00, Cr 2700 1,000.00. Bill of 50,000 (59,000.00) proposes 0.00, approves with no TDS, owes 59,000.00; the advance set against it leaves 9,000.00 | Pass (the half-second hint: screen) |
| TC-BUY-048 | `po-received` t10057fg6, supplier T10057FG6-TAA98. (1) `tds_amount` 0: owes 47,200.00. (2) proposal by then 1,600.00; 500 typed: owes 46,700.00, Cr 2700 500.00. (3) the bill's total: 422 "TDS deducted must be less than what the bill owes." (4) the fixture's supplier, no section: 422 with the case's words. Audit `purchase_invoice.approved`: proposed 1,600.00, deducted 500.00, `tds_overridden` true | Pass |
| TC-BUY-049 | Own firm T100509T7-G. Defaults as the case lists them (194J has no per-payment limit). 194C annual 150,000 saved; rate 35, rate 0 and threshold -1 refused 422. **An explicit `null` rate answers 500.** 194J off: a 194J supplier's bill of 40,000 proposes 0.00; on again, 4,000.00. Read Only reads, and is refused 403 on save. Audit `tds_section.settings_saved` | Pass on what the screen sends; BUYQ-7 for the 500. "Nothing has changed." is the screen's: the server answers "194C settings saved." both times |
| TC-BUY-050 | `po-received` t1005dwir. Bill PI-2026-2027-000068 with `tcs_rate_percent` 0.1: total 708.00, tax 108.00, TCS 0.71; approved, owes 708.71; Dr 2300 600.00, Dr 1320 54.00, Dr 1330 54.00, Dr 1430 0.71 / Cr 2100 708.71 | Pass |
| TC-BUY-051 | `po-received` t10054blv, draft PI-2026-2027-000070. Rate 0.1 and amount 1.00: TCS 1.00. Both cleared: 0. Rate alone: 0.71. A save naming neither field leaves it at 0.71 | Pass |
| TC-BUY-052 | `po-received` t1005e1q1. Bill with TCS 1.00 approved with payment: PY-2026-2027-000018 of 709.00, nothing owed. Bill PI-…-000072 (the 4, TCS 1.00) approved and cancelled: `-REV` mirrors every leg, Cr 1430 1.00 and Dr 2100 473.00 | Pass |
| TC-BUY-053 | `po-received` t1005dwir. `GET /purchase-invoices/reports/tcs-paid`: row Q3 2026-27, base 708.00, rate 0.1, TCS 0.71, and a row "Total Q3 2026-27" 708.00 / 0.71. A draft bill with TCS is not listed | Pass |

## Cases 054 to 092

Own firms used here: `compliance-firm` T100509T7-G (GST-registered; imports,
depreciation, firm-wide settings), `electronics-firm` T1005AWVW-E and
T1005WGOM-E, `pharma-firm` T1005A76G-P.

| Case | What was driven, with the data used | Result |
| --- | --- | --- |
| TC-BUY-054 | Own firm T100509T7-G, messaging never switched on. `POST /messaging/send` for an approved order by WhatsApp: 422 "Messaging is off for this firm. Switch it on under Settings > Messaging first." Messaging on, no account: "WhatsApp cannot send: no account is set up." A dummy account saves, but the channel cannot be switched on until its Test passes | Partly. The "name the WhatsApp template" refusal was not reached: it needs a WhatsApp account that passes Test. Channel choices in the dialog: screen |
| TC-BUY-055 | Same firm | Not driven (Blocked, as the case allows): no WhatsApp Business account, and a channel cannot be enabled without a passed Test |
| TC-BUY-056 | `buy-ready` t1005qztj. RFQ-2026-2027-000001, two suppliers, 10 of the product: DRAFT; a quote on a draft refused "A draft RFQ takes no quotations; quotes are entered while it is sent."; SENT. Quotes 100 less 5% (lead 7) and 96 (lead 3). Comparison: `landed_rate` 95.00 marked lowest, 96.00 | Pass ("No supplier has quoted yet": screen; the API answers the lines with no quotes) |
| TC-BUY-057 | Same RFQ. The 96.00 quote with no reason: 422 "Line 1: say why Supplier T1005QZTJ-V2 is chosen over the lowest quote." With a reason, then raise orders: PO-TEST01-HO-2026-2027-000099, DRAFT, 10 at 96.00, reference RFQ-2026-2027-000001; RFQ CLOSED; a quote then refused "A closed RFQ takes no quotations; quotes are entered while it is sent." | Pass |
| TC-BUY-058 | `buy-ready` t1005jaax. Approved requisition PR-2026-2027-000024 (one line naming V, one product preferring V2): RFQ-2026-2027-000002 DRAFT with both lines and both suppliers. Again: 422 "RFQ RFQ-2026-2027-000002 was already started from requisition PR-2026-2027-000024." From a draft requisition: "An RFQ is started only from an approved requisition." Send with no supplier: "Invite at least one supplier before sending." Cancel needs a reason (422), then CANCELLED. Orders raised from the requisition's RFQ: requisition ORDERED | Pass |
| TC-BUY-059 | `buy-ready` t1005chn4. Read Only: list and comparison 200; new, send, quote, selections, raise orders all 403. Warehouse: list 403. Purchasing: saves selections and raises the order (201) | Pass |
| TC-BUY-060 | `buy-ready` t1005vzyi. RC-2026-2027-000005, 90 for 20 units: DRAFT; a Purchasing user can type one (201) and is refused Approve (403); ACTIVE. Order line with no price: 90.00 with `rate_contract_line_id` set (PO-…-000102); a typed 95 is kept and names no contract | Pass (the tooltip: screen) |
| TC-BUY-061 | Same contract. Drafts draw nothing; 15 approved: drawn 15, remaining 5; releases list PO-…-000102 line 1, 15 at 90. Order of 10: warning on the draft and after approval "Over rate contract: RC-2026-2027-000005 T1005VZYI-B: 25 drawn of 20 contracted."; drawn 25, remaining 0. First order cancelled: drawn 10, remaining 10 | Pass |
| TC-BUY-062 | Same contract. (1) overlapping contract refused at approval "Another active rate contract with this supplier covers the same product for an overlapping period: T1005VZYI-B on RC-2026-2027-000005 (2026-10-05 to 2026-11-04). Close it, or change the period." (2) "RC-2026-2027-000008 ended on 2026-10-04; change its period before approving it." (3) "Only a draft rate contract can be changed." (4) CLOSED; a blank price then takes the product's 100. (5) a draft deletes (then 404); cancel with no reason 422; with one, CANCELLED and the reason kept | Partly: an active contract past its last day reading Expired in the list, and pricing nothing, was not driven (it needs a contract approved before its last day and read after it) |
| TC-BUY-063 | `electronics-firm` T1005AWVW-E. Range QA-SN, start 1, count 2, width 4 expands to QA-SN0001, QA-SN0002. Draft receipt of 3 with two serials saves; complete refused 422 "Line 1 (T1005AWVW-MIX) receives 3 serial-tracked units but 2 serial numbers are entered: enter 1 more on the goods receipt." With three: COMPLETED, three units AVAILABLE in MAIN, trail answers. 1 accepted + 1 free with one serial: refused (2 needed) | Pass (the wording has "serial numbers", see corrections) |
| TC-BUY-064 | Same firm. (1) `qa-sn0001`: 422 "Line 1 (T1005AWVW-MIX): serial qa-sn0001 already belongs to a unit in this firm (AVAILABLE)." (2) "Serial QA-TWICE-… is entered on line 1 and on line 2 of GRN-T1005AWVW-E-HO-2026-2027-000003." (3) the server also refuses one number twice on a line: "…serial QA-DUP is entered twice." (4) "Line 1 (T1005AWVW-PLAIN): this product is not serial-tracked, so its lines take no serial numbers." | Pass |
| TC-BUY-065 | T1005AWVW-E and T1005WGOM-E. (1) receipt of QA-A1, QA-A2 cancelled: the units are gone and are received again on a new receipt. (2) QA-B1 sold and dispatched: cancel refused "GRN-T1005WGOM-E-HO-2026-2027-000001 cannot be cancelled: serial QA-B1 has left stock since it was received (SOLD)." (3) a return naming no unit is refused at completion; the sold unit, a unit not from this supplier, another product's unit ("…serial QA-OTHER-1 is not a unit of this product in this firm.") and an unknown serial are refused at save; naming QA-B2 completes and the unit reads RETURNED. (4) cancelling the completed return: QA-B2 AVAILABLE, stock back | Pass |
| TC-BUY-066 | `buy-ready` t1005zgmv. Scheme 10+2 for the supplier. Order PO-…-000106 of 25 at 100 with Free blank: free 4, `scheme_name` 10+2, subtotal 2,500.00. Received with 25 and 4 free: 29 on hand; Dr 1200 2,500.00 / Cr 2300 2,500.00 | Pass. Note: a receipt created over the API starts its free quantity at 0; the screen fills the 4 (D-BUY-33) and that is what was sent |
| TC-BUY-067 | Same scheme. Free typed 0: 0 and no scheme named (PO-…-000107). Typed 1: 1. Nine units: 0. Order dated 2026-10-04, before the scheme: 0 | Pass |
| TC-BUY-068 | `buy-ready` t1005x0tu. Scheme "10 + 1 Item T1005X0TU-GIFT". Preview of 25 suggests the gift product, free 2. Saved with a free-only gift line (ordered 0, free 2, price 0): PO-…-000113, subtotal 2,500.00, tax 450.00, total 2,950.00 | Partly. The editor adding the line once and not twice is the screen's (the server marks an existing gift line only when it carries the scheme's id) |
| TC-BUY-069 | `buy-ready` t1005zgmv. Overlapping scheme from next week: 422 "An active scheme for this supplier on this product already runs 2026-10-05 to open-ended. End or switch it off first." Ends before it starts: "A scheme cannot end before it starts." All-suppliers 10+1 stands beside it; the supplier's own wins (20 earns 4); own switched off, the all-suppliers one applies (20 earns 2). Read Only: list 200, new and delete 403 | Pass |
| TC-BUY-070 | Own firm T100509T7-G, supplier USD-FC74, product IMP-6112 on GST_0. Currency `US` refused. USD order with no rate: 422. PO-…-000029 at 83: 1,000.00. GRN-…-000012: 10 units at 8,300 = 83,000.00, Dr 1200 83,000.00 / Cr 2300 83,000.00. Bill PI-…-000011: 1,000.00 USD, `base_grand_total` 83,000.00; Paid now refused "Bill … is in USD. Approve it, then pay it through Payments in USD at the day's rate."; TDS refused; approved: Dr 2300 83,000.00 / Cr 2100 83,000.00 | Pass on the server; wording differs in three places (see corrections). An order sent with no currency for a USD supplier is saved in rupees: starting in USD is the screen's |
| TC-BUY-071 | Same firm. Bills PI-…-000012 and 000013. Paid 1,000 USD at 84: `exchange_difference` 1,000.00, Dr 2100 83,000.00, Dr 4950 1,000.00 / Cr 1010 84,000.00. At 82: -1,000.00, Dr 2100 83,000.00 / Cr 1010 82,000.00, Cr 4950 1,000.00. Nothing owed | Pass |
| TC-BUY-072 | Bill PI-…-000014. 400 USD at 84: Dr 2100 33,200.00, Dr 4950 400.00 / Cr 1010 33,600.00; owes 600.00 USD and 49,800.00. Reversed: all three legs mirrored; owes 1,000.00 USD and 83,000.00 | Pass |
| TC-BUY-073 | Same bill. Rupees against it: "Bill … is in USD. Pay it with a payment in USD at the day's rate." 1,200 USD applying 1,000, and a USD advance: "A payment in USD is applied in full to the supplier's bills in USD; an advance in another currency is not carried." No rate: "A payment in USD needs its exchange rate…". With TDS: "A payment in USD takes no TDS, rounding, bank charges or discount; record it for the amount that was sent." A USD bill with TCS: "TCS under 206C(1H) is charged by a seller in India; a bill in another currency carries none." | Pass (what the rupee dialog offers: screen) |
| TC-BUY-074 | Bill PI-…-000015, product IMP-3565, 10 on hand at 8,300. BOE-2026-2027-000001 (number 3523996, INMAA1), assessable 85,000, BCD 10%, IGST 18%: BCD 8,500.00, SWS 850.00, IGST base 94,350.00, IGST 16,983.00. Posted: customs duty 9,350.00, to stock 9,350.00, COGS 0; valuation 92,350.00 (9,235.00 each); Dr 1200 9,350.00, Dr 1310 16,983.00 / Cr 2800 26,333.00; 3B `itc_import_goods` 16,983.00 | Pass |
| TC-BUY-075 | (1) BOE-…-000002, BCD typed 9,000: SWS 900.00, duty 9,900.00; 6 of 10 on hand: to stock 5,940.00, to COGS 3,960.00. (2) the first cancelled: valuation 8,300.00 again, journal mirrored, 3B drops its 16,983.00. (3) **a second draft with the same number, port and date saves, and then posts** (BOE-…-000003, and two more typed in lower case), each booking the duty and the IGST again. (4) a Bill of Entry with no line is refused at save (validation). (5) Purchasing saves a draft; Post and Cancel 403 | **Fail: BUYQ-8.** The three duplicates were cancelled afterwards to keep the firm's books |
| TC-BUY-076 | The firm's one USD bill then, PI-…-000011. Revalue at 85 as of 2026-10-05: loss 2,000.00, `FXREV-20261005` Dr 4950 2,000.00 / Cr 2100 2,000.00 and its mirror `FXREV-20261005-REV`. Again: "Payables in other currencies were already revalued on 2026-10-05 (FXREV-20261005)." The bill still reads 83,000.00; paid at 84 it posts the whole 1,000.00 loss. No rate: 422 | Pass |
| TC-BUY-077 | `buy-ready` t1005wdov. Classes PLANT, FURNITURE, COMPUTERS, VEHICLES, OFFICE_EQUIPMENT, all SLM, residual 5. Order PO-…-000122 with the line capital goods; receipt GRN-…-000147 starts ticked, completes with no stock row, no movement and no journal; order RECEIVED. Bill with no class: 422 "Line 1 is capital goods: choose its asset class." (at save); unticked: refused; with FURNITURE: PI-2026-2027-000077, 43,070.00. Approved: FA-00002, FURNITURE, cost 36,500.00, NBV 36,500.00, ACTIVE, names the bill; stock nothing; Dr 1500 36,500.00, Dr 1320 3,285.00, Dr 1330 3,285.00 / Cr 2100 43,070.00; register `capital_goods_tax` 6,570.00 | Pass. Low: the journal also carries a 0.00 line on 2300 (BUYQ-10) |
| TC-BUY-078 | (1) `po-received` t1005ulz6: a capital-goods bill for the stocked receipt saves and is refused at approval with the case's words. (2) t1005wdov: the capital-goods bill cancelled, journal mirrored, the asset gone from the register. (3) delete: "Asset FA-00002 was raised by a bill; cancelling the bill takes it off the register."; cost: "Asset FA-00002 costs what its bill charged; change the bill, not the asset." | Pass |
| TC-BUY-079 | Own firm T100509T7-G (runs are firm-wide). Class QAWDV6E6A (WDV 40%), assets FA-00001 (FURNITURE) and FA-00002, both 2026-10-01 at 36,500. Run DEP-00001 for October: 31 days each, 294.50 and 1,240.00, one journal Dr 6950 1,534.50 / Cr 1590 1,534.50; NBV 36,205.50 and 35,260.00; schedules show the charge. Same period: "Depreciation run DEP-00001 already charged 2026-10-01 to 2026-10-31. Cancel it, or run a period after it." Earlier: "Runs go forward: DEP-00001 charged up to 2026-10-31. Cancel it to run an earlier period." | Pass |
| TC-BUY-080 | Same assets. FA-00001 for 35,000 by bank: Dr 1590 294.50, Dr 1010 35,000.00, Dr 4960 1,205.50 / Cr 1500 36,500.00, gain/loss -1,205.50. FA-00002 for 36,000 cash: Dr 1590 1,240.00, Dr 1000 36,000.00 / Cr 1500 36,500.00, Cr 4960 740.00. An asset not yet charged disposed on 10-15: a DISPOSAL run DEP-00002 charges 10-01 to 10-15 first. An asset charged to 2026-11-30 disposed on 11-15: 422 "Depreciation on FA-00004 is charged to 2026-11-30. Dispose of it on or after that day, or cancel the runs that charged past it." Cancel October: "FA-00001, FA-00002 has since been disposed at the book value DEP-00001 left, so the run stands." | Pass |
| TC-BUY-081 | Same firm. Class QAIT6135, IT rate 25, assets of 40,000 on 2026-06-01 and 2026-12-01. Run DEP-00003 (Nov-Dec) cancelled with a reason: CANCELLED, `DEP-00003-REV`, and the period runs again. Block 25% for 2026-27: opening 0.00, additions full 40,000.00, half 40,000.00, depreciation 15,000.00, closing 65,000.00 (read before a third asset of 10.00 was typed). Delete class: "Asset class QAIT6135 has assets on the register. Move them to another class, or mark this one inactive." Read Only: four reads 200; new, dispose, run 403. FIXED_ASSET_MANAGE without JOURNAL_POST: 403 "This posts a journal, which needs JOURNAL_POST as well." | Pass |
| TC-BUY-082 | `pharma-firm` T1005A76G-P. Receipt of 20 into new batch QA-PTR-1, MRP 120, PTR 90, PTS 80: the batch reads 120 / 90 / 80. Second receipt into it, PTR 92, PTS blank: 92 / 80. Audit `batch.rates_updated` with the old pair 90 / 80 | Pass |
| TC-BUY-083 | Same firm. PTR 120 over MRP 100: 422 "PTR 120.00 cannot exceed the MRP 100.00." No batch: "Line 1: PTR and PTS are kept on the batch, so the line needs a batch number." Batch update with PTS 130 or PTR 125 over MRP 120: refused the same way | Pass |
| TC-BUY-084 | Same batch (PTR 92 by then). Sales order line with the batch pinned and no price: Retailer 92.00, Stockist 80.00, Other 100.00, not set 100.00; typed 95 stays; Retailer with no batch 100.00. The batch availability list carries MRP, PTR, PTS | Partly: a customer price list ranking above the batch's rate, and the price level below it, were not driven; the delivery-note picker is screen |
| TC-BUY-085 | `electronics-firm` T1005WGOM-E. A receipt line with `ptr`: 403 "This firm's business profile does not enable BATCH_PTR_PTS, so ptr cannot be set." The same line without it saves | Pass. Observation: a customer's `trade_class` is accepted by the server in this firm; hiding it is the screen's |
| TC-BUY-086 | Firm of its own T1005WGOM-E, both buying stages off (order off with receipt on is refused). USD supplier, GST_0 product. Bill with no rate: 422. PI-T1005WGOM-E-HO-2026-2027-000001 at 83: 1,000.00 USD, 83,000.00; approved: 10 units at 8,300; Dr 1200 83,000.00 / Cr 2300 83,000.00 (GRN-…-000004) then Dr 2300 83,000.00 / Cr 2100 83,000.00; owes 1,000.00 USD. Stages switched back on | Pass; the refusal's words name a purchase order (BUYQ-9) |
| TC-BUY-087 | Own firm T100509T7-G. (1) PI-…-000017 at 84.50: 84,500.00; Dr 2300 83,000.00, Dr 5400 1,500.00 / Cr 2100 84,500.00. (2), (3) refused with the case's words both ways. (4) "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." (5) refused with the case's words. (6) saved USD at 83 | Pass; (4) quotes the wrong words (see corrections) |
| TC-BUY-088 | T1005WGOM-E, stages off, bill dated 2026-10-01. No class: 422 at save. FURNITURE: PI-…-000002 approved; FA-00001 FURNITURE 36,500.00 ACTIVE naming the bill; no stock; Dr 1500 36,500.00, Dr 1320 3,285.00, Dr 1330 3,285.00 / Cr 2100 43,070.00 (plus the 0.00 line on 2300) | Pass |
| TC-BUY-089 | T100509T7-G, bill PI-…-000017 (1,000 USD at 84.50, HSN 90765242). GST register: taxable 84,500.00, total 84,500.00, heads 0.00. HSN summary: quantity 10, taxable 84,500.00. Purchase invoice register: 84,500.00 | Pass (figures at the bill's 84.50, not the case's 83) |
| TC-BUY-090 | `buy-ready` t1005wayo. (1) order line not marked; receipt line ticked: completes with no stock, no movement, no journal; order RECEIVED. (2) the bill line starts capital goods and needs a class; `is_capital_goods: false` refused with the case's words. (3) second receipt cancelled: CANCELLED, nothing reversed, order back to APPROVED | Pass |
| TC-BUY-091 | T100509T7-G, bill PI-…-000019. Debit note DBN-…-000001 for 100.00: Dr 2100 8,300.00 / Cr 5400 8,300.00; owes 900.00 USD and 74,700.00; 950 USD refused; payables for the supplier agree with the books (difference 0.00); statement carries 8,300.00. Cancelled: mirrored, 1,000.00 USD and 83,000.00 again | Pass |
| TC-BUY-092 | Same bill. (1) return PR-…-000001 of 2, sent as INR at 1: stamped USD at 83, 200.00; Dr 2100 16,600.00 / Cr 1200 16,600.00; 8 on hand; owes 800.00 USD and 66,400.00. (2) 800 USD at 83: no exchange difference, nothing owed. (3) t1005wdov: a return of the capital-goods line, off the bill and off the receipt: 422 with the case's words | Pass |

## Generic checks

149 requests in a firm of its own, `ready-firm` T1005RAR6-R, as its firm
administrator, its VIEWER and a user hired as *Purchasing* (`g01.py`,
`g01.log`). The other firm's product and vendor were TEST01's. A cell is the
HTTP status; **bold** is not what was expected and is explained under the
table. "-" means the document has no such field or action.

| Check | Order | Receipt | Bill | Return | Debit note | Payment | Requisition | RFQ | Rate contract |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A mandatory field left out | 422 | 422 | 422 | 422 | 422 | 422 | 422 | 422 | 422 |
| No lines | 422 | - | 422 | - | - | - | 422 | 422 | 422 |
| Quantity (or amount) 0 | **201** | **201** | **201** | **201** | 422 | 422 | 422 | 422 | - |
| Rate 0 | - | - | - | - | - | - | - | **200** (a quote) | **201** |
| Negative quantity or amount | 422 | 422 | 422 | 422 | 422 | 422 | 422 | 422 | 422 |
| Negative rate | 422 | - | 422 | 422 | - | - | - | 422 | 422 |
| More than the source allows | - | 422 (11 of 10) | 422 (5 of 4) | 422 (5 of 4) | 422 (9,999 on a line of 400) | 422 (applied above the amount; above what the bill owes) | - | 422 (discount 120%) | - |
| An id that does not exist | 422 vendor, 422 product, 404 GET | 404 order, 422 line | 422 line, 422 vendor | 422 line | 404 bill, 422 line | 404 supplier, 422 bill | 422 product | 422 product | 422 vendor |
| A product or supplier of another firm | 422, 422 | - | 422 (a bill typed alone is refused while the stages are on) | - | - | 404 | 422 product, **409** supplier | 422, 422 | 422 product |
| A user without the permission | 403 create, submit, delete (VIEWER); 403 approve (Purchasing) | 403 create, complete | 403 create; 403 approve (Purchasing) | 403 create; 403 approve (Purchasing) | 403 create; 403 approve (Purchasing) | 403 record, reverse (VIEWER); 403 record (Purchasing) | 403 create; 403 approve (Purchasing) | 403 create | 403 create; 403 approve (Purchasing) |
| `page_size=100000` | 422 (cap 100) | 422 | 422 | 422 | 422 | 422 | **200** | 422 | 422 |
| A stale `If-Match` on update | 409 | 409 | **200** | **200** | 409 | 405 (a payment is not edited) | **200** | 409 | 409 |
| `status` sent in the update body | 200, ignored: still DRAFT | 422 | 422 | 422 | 422 | - | 422 | 422 | 422 |
| A step skipped or repeated | 422 approve a draft | 422 edit after completion | 422 edit after approval; 422 approve twice | 422 complete before approval | 422 cancel with no reason | 422 reverse twice | 422 approve or convert a draft | 422 raise orders from a draft, or with nothing chosen | - |
| Cancel or reverse puts it back | - | 200: a completed receipt of 6 cancelled, stock 4 before and after, net on 1200 0.00 | 200: an approved bill of 354.00 cancelled, owed 826.00 to 472.00, net on 2100 0.00 | 200: a completed return of 1 cancelled, stock 7, 6, 7 | 200: an approved note of 59.00 cancelled, owed 472.00, 413.00, 472.00 | 200: a payment of 100.00 reversed, owed 472.00, 372.00, 472.00 | - | - | - |

What the bold cells are:

- **Quantity 0** is accepted on an order line, a receipt line, a bill line and
  a return line, and **rate 0** on a supplier's quote and a rate contract:
  BUYQ-11. An order line may lawfully carry 0 ordered with free goods; these
  carried nothing at all.
- **A stale `If-Match`** is ignored on a purchase bill, a purchase return and
  a requisition, which publish no `ETag`: BUYQ-12. Bulk approval of bills does
  refuse a stale row ("…was changed after the list was read; open it, check it
  and try again.").
- **Requisition list**: the route takes no `page` or `page_size` at all and
  returns every requisition, so the parameter is ignored rather than refused.
  Not a 500; noted with BUYQ-12.
- **Requisition, another firm's supplier**: 409 "The request conflicts with
  existing data. Please retry." -- the foreign key, not a check: BUYQ-15.
- Deleting an approved order that nothing was received against answers 204 and
  `POST /purchases/{id}/restore` brings it back: by design
  (`PurchaseService.delete_order`), listed so nobody takes it for a finding.

No request in this table answered 500. The two 500s of the whole run are
BUYQ-7.

### The books at the end

Read through `GET /finance/trial-balance` (first period to the current one)
and `GET /purchase-invoices/reports/payables` (`r01.py`, `r02.log`).

| Firm | Trial balance | 2100 Trade Payables | Payables report | Agrees |
| --- | --- | --- | --- | --- |
| T1005RAR6-R (generic checks) | balanced, 4,870.00 each side | 472.00 Cr | 472.00 | Yes |
| T100509T7-G (imports, assets, settings) | balanced, 899,999.76 | 339,673.76 Cr | 339,673.76 | **As of 2026-10-05 the check reads a difference of -2,000.00** (books 341,673.76): BUYQ-13. Read a day later it agrees |
| T1005WGOM-E | balanced, 140,570.00 | 126,070.00 Cr | 126,070.00 | Yes |
| T1005AWVW-E, T1005A76G-P | balanced | nothing owed | 0 | Yes |
| TEST01 | balanced, 934,661.71 | 609,872.71 Cr | 609,164.71 | Differs by 708.00, all of it PI-2026-2027-000003 of 2026-09-18 (see "Not verified"). Supplier by supplier, the only other difference is BUYQ-5 |

## Defects found by this check

Provisional ids. None is in `docs/DEFECTS.md` under Open, Fixed or Not a
defect. Each was reproduced at least twice, the second time on a fresh
fixture.

| Id | Severity | What | Where |
| --- | --- | --- | --- |
| BUYQ-1 | High | Goods rejected at inspection and kept "for a return" stay in quarantine for ever: the purchase return takes them out of sellable stock instead | `app/inventory/services/inventory_service.py:2769-2772` |
| BUYQ-2 | Medium | A purchase return completes for goods no longer on hand and takes stock below zero | `app/inventory/services/inventory_service.py:2698-2788` (no check; compare `:1938-1946`) |
| BUYQ-3 | Low | A purchase requisition and a purchase return are both numbered `PR-…`; on TEST01 four numbers belong to one of each | `app/purchase/services/requisitions.py:53`, `app/purchase_return/services/purchase_return_service.py:144` |
| BUYQ-4 | Low | Journal references double the prefix (`LCV-LCV-…`, `BOE-BOE-…`); a supplier refund's reversal is referenced by a bare id (`ED77F6AD-REV`) | `app/finance/services/document_posting.py:2167`, `:2245`; `app/settlements/services/supplier_credits.py:962` |
| BUYQ-5 | High | A supplier refund is missing from the supplier's statement, so its closing balance is wrong by every refund, and Payables by Month narrowed to that supplier says it does not agree with the books | `app/vendors/services/statement_service.py:71-78`; `app/finance/services/document_posting.py:1549`; `app/purchase_invoice/services/payables_report.py:817-832` |
| BUYQ-6 | Low | A bill line that names no unit is stored with none, though it bills a receipt line that has one; the HSN summary of purchases then shows a blank unit | `app/purchase_invoice/services/purchase_invoice_service.py:2566-2567` |
| BUYQ-7 | Low | `PUT /finance/tds-sections/settings/{section}` with an explicit `null` rate or threshold answers 500 | `app/finance/services/tds_sections.py:191-206` |
| BUYQ-8 | High | A second Bill of Entry with the same number, port and date posts, booking the customs duty and claiming the IGST again | `app/bill_of_entry/repositories/__init__.py:86-99`; `app/bill_of_entry/services/bill_of_entry_service.py:288-298` |
| BUYQ-9 | Low | A bill typed alone in another currency with no rate is refused in a purchase order's words | `app/finance/currency.py:64` (called for the order the bill raises) |
| BUYQ-10 | Low | A capital-goods bill's journal carries a 0.00 line on 2300 Goods Received Not Invoiced | `app/finance/services/document_posting.py:3774` (`post_purchase_invoice`) |
| BUYQ-11 | Low | Documents that carry nothing are accepted: an order line of 0 (and the order approves at 0.00), a receipt of 0 (completes), a return of 0 (completes), a bill of 0 (saves), a rate contract at rate 0 (approves, and prices order lines at 0.00) | `app/purchase/schemas/purchase.py:65`; `app/goods_receipt/schemas/goods_receipt.py:77`; `app/purchase_invoice/schemas/purchase_invoice.py:108`; `app/purchase_return/schemas/purchase_return.py:88`; `app/rate_contracts/schemas/__init__.py:20`; `app/rfq/schemas/__init__.py:108` |
| BUYQ-12 | Medium | A purchase bill, a purchase return and a requisition publish no `ETag` and ignore `If-Match`: a save over somebody else's newer save is accepted. The requisition list is also unpaged | `app/purchase_invoice/api/router.py`, `app/purchase_return/api/router.py` (no `set_etag`), `app/purchase/api/router.py:552-565` |
| BUYQ-13 | Medium | On the day payables in another currency are revalued, Payables by Month reads "does not agree with the books" by the revaluation | `app/purchase_invoice/services/payables_report.py:833-849`; `app/finance/services/fx_revaluation.py:54` |
| BUYQ-14 | Medium | After a firm is provisioned from the running server, the server writes no more request or error log until it is restarted (not a buying defect; it is why BUYQ-7 has no traceback) | `backend/alembic/env.py:21` |
| BUYQ-15 | Low | A requisition line's supplier is not checked against the firm: an unknown or foreign supplier answers 409 "The request conflicts with existing data." | `app/purchase/services/requisitions.py:326`, `:369` |

### BUYQ-1 -- goods rejected for return never leave quarantine (High)

Reproduced four times: `po-approved` t1005iu0l, t1005i48t, t10051hjb, t10050fyz.

1. `PUT /products/{id}` with `inspection_required: true`.
2. Receive 10 and complete (GRN-TEST01-HO-2026-2027-000148): sellable 0,
   quarantine 10.
3. `POST /goods-receipts/{id}/lines/{line}/inspection`
   `{"passed_quantity": "6", "rejected_quantity": "4", "rejected_action": "RETURN"}`
   -> 200 "Inspection saved."; sellable 6, quarantine 4.
4. `POST /purchase-returns` off that receipt line with
   `{"current_return_quantity": "4", "rejected_quantity": "4", "item_condition": "QUARANTINE"}`,
   approve, complete (PR-2026-2027-000024) -> 200.

**Expected:** sellable 6, quarantine 0. **Actual:** sellable **2**, quarantine
**4**. The movement reads `current_quantity_delta` -4.0000,
`quarantine_quantity_delta` 0.0000, and its remarks say
"…quarantine=4.0000". Four good units have gone from what can be sold and four
rejected units that left the building are still held.

**Cause:** `InventoryService.record_purchase_return` always writes
`current_delta=-base_quantity` and `quarantine_delta=ZERO`
(`inventory_service.py:2769-2772`); `quarantine_quantity`, which
`purchase_return_service.py:653-655` passes for exactly this case, reaches
only the remarks string.

### BUYQ-2 -- a purchase return takes stock below zero (Medium)

Reproduced twice: `po-received` t10055hm0 (10 received, 9 sold, 3 returned:
-2) and t10051yt1.

1. `po-received`: 10 on hand. Sell and dispatch 10 to a customer: 0 on hand.
2. `POST /purchase-returns` for 2 off the receipt of 6, approve, complete
   (PR-2026-2027-000026) -> 200, 200, 200.

**Expected:** refused, as a transfer is ("The source holds … available, so …
cannot be transferred out of it.") and a write-off is ("This location holds
-2.0000, so 1 cannot be written off from it."). **Actual:** completed;
inventory `current_quantity` -2.0000, `available_quantity` -2.0000. The
product has `allow_negative_stock` false. Journal Dr 2300 300.00 / Cr 1200
300.00 on the first run, for goods that were not there.

Not the same as D-STK-12 (a hand adjustment may go negative, decided) or
D-BUY-14 (a return with no receipt behind it, fixed): here the receipt exists
and the goods have been sold.

**Cause:** `record_purchase_return` stages the movement with no check of what
the location holds.

### BUYQ-3 -- two documents, one number (Low)

`GET /purchases/requisitions` and `GET /purchase-returns` on TEST01 both list
`PR-2026-2027-000016`, `-000017`, `-000024` and `-000025`: a requisition
(APPROVED or ORDERED) and a completed purchase return each. Journals, the
stock ledger and an order's reference quote the number alone, so
"PR-2026-2027-000017" on PO-TEST01-HO-2026-2027-000042 cannot be told from
the return. In a firm created today the two differ in form
(`PR-2026-2027-000001` against `PR-T1005RAR6-R-HO-2026-2027-000001`) but still
share the prefix. **Expected:** a prefix of its own for the requisition.

### BUYQ-4 -- journal references (Low)

`LCV-LCV-2026-2027-000001` (voucher LCV-2026-2027-000001),
`BOE-BOE-2026-2027-000002`: the posting adds a prefix the document number
already has. The reversal of refund `PR-2026-2027-000012-RF1` is referenced
`ED77F6AD-REV`, where every other reversal is its original's reference with
`-REV`.

### BUYQ-5 -- a supplier refund is missing from the statement (High)

Reproduced three times: `buy-ready` t10058vny (a debit note's refund of 50),
`po-invoiced` t1005dezg and t1005op4h.

1. `po-invoiced`: bill PI-2026-2027-000080, 708.00. Pay it in full
   (PY-2026-2027-000022).
2. Return 2 off the billed receipt with `outcome: REFUND`
   (PR-2026-2027-000029): Dr 2100 236.00.
3. `POST /payments/supplier-credits/{return_id}/refunds`
   `{"amount": "100", "refunded_on": "2026-10-05", "method": "BANK"}` -> 200;
   journal `PR-2026-2027-000029-RF1` Dr 1010 100.00 / Cr 2100 100.00.
4. `GET /vendors/{id}/statement?from_date=2026-10-01&to_date=2026-10-05`.
5. `GET /purchase-invoices/reports/payables?as_of=2026-10-05&vendor_id=…`.

**Expected:** the statement lists the refund and closes at -136.00, what 2100
holds for this supplier; the report's books check reads no difference.
**Actual:** the statement has three lines (bill, payment, return), no refund,
closing **-236.00**. The report's total is -136.00 and its books check
`{"ledger_balance": "-236.00", "difference": "100.00"}`. The same statement
feeds `GET /vendors/{id}/balance-confirmation`.

**Cause:** the refund's journal carries
`source_module="supplier_credit_refund"` (`document_posting.py:1549`), which
`SUPPLIER_SOURCES` (`statement_service.py:71-78`) does not list, so
`_movements` never reads it. `PayablesReportService._ledger_balance` uses
those movements for one supplier (`payables_report.py:817-832`) while the
report itself counts refunds (`_refunds`, `:698`). The firm-wide check, which
sums the account, is unaffected.

### BUYQ-6 -- no unit on a bill line, blank unit in the HSN summary (Low)

`POST /purchase-invoices` billing a receipt line without `invoice_uom_id`
(as `scripts/test_fixture.py` does): the bill line's `purchase_uom_id` and
`invoice_uom_id` are null although the receipt line's are PIECE.
`GET /purchase-invoices/reports/hsn-summary` then shows `"unit": ""` for it.
The desktop editor sends the unit, so bills typed on screen are not affected;
an import or any other client is. **Cause:** `purchase_invoice_service.py:2566-2567`
stores what the request sent, though `:2427` already falls back to the source
line's unit for the quantity check.

### BUYQ-7 -- 500 on an explicit null (Low)

`PUT /api/v1/finance/tds-sections/settings/194C` with `{"rate_percent": null}`,
`{"annual_threshold_amount": null}` or `{"lower_rate_percent": null}` ->
**500** "An unexpected error occurred." (request ids de1bda9f-…, 9a1558a2-…,
9b5f058a-… in T1005RAR6-R; also in T100509T7-G). `{"is_enabled": null}` and
`{}` answer 200. **Expected:** 422. The desktop refuses a blank rate before
sending, so this is the API only. **No traceback could be read** (BUYQ-14).
**Cause, from the code:** the schema allows `None` and the router dumps with
`exclude_unset=True`, so an explicit null reaches `save_settings`, where
`merged.annual_threshold_amount < ZERO` (`tds_sections.py:196`) and
`ZERO < rate <= _MAX_RATE` (`:206`) compare a Decimal with None.

### BUYQ-8 -- a duplicate Bill of Entry posts (High)

Reproduced five times in three firms (T100509T7-G three times, TEST01
`buy-ready` t1005o2az, T1005RAR6-R).

1. `POST /bills-of-entry`
   `{"boe_number": "1444033", "boe_date": "2026-10-05", "port_code": "INMAA1", "vendor_id": …, "lines": [{"product_id": …, "quantity": "1", "assessable_value": "10000", "bcd_rate": "10", "igst_rate": "18"}]}`
   -> 201 BOE-2026-2027-000001; `POST …/post` -> 200.
2. The same body again -> **201** BOE-2026-2027-000002; `POST …/post` ->
   **200 "Posted."**

**Expected:** "Bill of Entry 1444033 at INMAA1 on 2026-10-05 is already
BOE-2026-2027-000001." **Actual:** both POSTED, each with its journal Dr 5220
Customs Duty 1,100.00, Dr 1310 Input IGST 1,998.00 / Cr 2800 Customs Duty
Payable 3,098.00. On T100509T7-G the duplicate of a Bill of Entry linked to a
bill also revalued the stock a second time (Dr 1200 5,940.00, Dr 5200
3,960.00, Dr 1310 17,082.00 again) and GSTR-3B 4(A)(1) would have claimed the
IGST twice. Number and port typed in lower case posted too. The duplicates
were cancelled afterwards.

**Cause:** `BillOfEntryRepository.duplicate` selects any live, uncancelled
row with that number, port and date and returns one with `session.scalar`
-- and the draft being posted is itself such a row. `stage_post` then tests
`clash.id != row.id` (`bill_of_entry_service.py:288-298`); when the row that
came back is the draft itself the test passes. The query needs to leave the
row itself out. (Nothing checks at save either; the case expected the refusal
there.)

### BUYQ-9 -- the wrong document in the refusal (Low)

Stages off, `POST /purchase-invoices` for a USD supplier with no
`exchange_rate` -> 422 "A purchase order in USD needs its exchange rate: the
rupees one USD was worth on the purchase order's date." The person typed a
bill and no order.

### BUYQ-10 -- a zero line in the journal (Low)

PI-2026-2027-000077 (TEST01) and PI-T1005WGOM-E-HO-2026-2027-000002: Dr 1500
36,500.00, Dr 1320 3,285.00, Dr 1330 3,285.00 / Cr 2100 43,070.00 **and Cr
2300 Goods Received Not Invoiced 0.00**. The mirror on cancel carries it too.

### BUYQ-11 -- documents for nothing (Low)

In T1005RAR6-R: PO-T1005RAR6-R-HO-2026-2027-000003, one line with
`ordered_quantity` 0 and nothing free, saved, submitted and **approved** at
0.00. A goods receipt of 0 saves and **completes** (no stock, no journal). A
purchase return of 0 saves, approves and **completes**. A bill of 0 saves and
is refused only at approval, in the ledger's words: "A journal entry must
carry a non-zero amount." A rate contract at rate 0 approves, and an order
line with no price then takes **0.0000** from it. A supplier's quote at rate 0
is accepted. **Expected:** a line needs a quantity or free goods; a contract
or a quote needs a rate above 0.

### BUYQ-12 -- no optimistic lock on a bill, a return or a requisition (Medium)

`GET /purchase-invoices/{id}`, `/purchase-returns/{id}` and
`/purchases/requisitions/{id}` return no `ETag`; a `PUT` with
`If-Match: "1"` after the record has moved on answers 200. The same request on
an order, a receipt, a debit note, an RFQ and a rate contract answers 409
"This record changed since you loaded it. Reload and try again."
`GET /purchases/requisitions` also takes no `page` / `page_size` and returns
every row.

### BUYQ-13 -- the books check on a revaluation day (Medium)

T100509T7-G: `POST /finance/fx-revaluation {"as_of": "2026-10-05", "rates": {"USD": "85"}}`
posts `FXREV-20261005` (Cr 2100 2,000.00, dated 2026-10-05) and its mirror
dated 2026-10-06. `GET /purchase-invoices/reports/payables?as_of=2026-10-05`
then reads `{"ledger_balance": "341673.76", "difference": "-2000.00"}` against
a total of 339,673.76; as of any later day it agrees. A revaluation is run for
a period end, which is the day the payables are read against the books.
**Expected:** the check allows for the unrealised revaluation (or the report
shows it as a row).

### BUYQ-14 -- the server stops logging after a provision (Medium, platform)

`backend/logs/server/server-2026-10-05.log` ends at 18:30:27 with "Request
received method=POST path=/api/v1/firms/…/provision"; nothing was written
after it though the server answered several thousand requests. The same file
shows the same silence from 08:29:59 (another provision) until the restart at
09:56. `uvicorn-run.log` received only alembic's lines. **Cause, from the
code:** `alembic/env.py:21` calls `fileConfig(config.config_file_name)`, whose
default `disable_existing_loggers=True` switches off the application's
loggers when `upgrade_store` runs alembic inside the server process. Not
reproduced a second time by me on purpose (it needs a restart to undo).

### BUYQ-15 -- a requisition's supplier is not checked (Low)

`POST /purchases/requisitions` with a line `vendor_id` that is no supplier of
this firm (TEST01's, or a random id) -> 409 "The request conflicts with
existing data. Please retry." The product on the same line is checked
("Unknown product(s): …"). Only the foreign key refuses it, and two firms in
the shared store share that table: **whether a requisition there can name
another firm's supplier was not driven.**

## Case text to correct

Exact wording to change in `docs/INDEPENDENT_TEST_CASES.md` (then regenerate
`06_PURCHASING.md`).

| Case | Change |
| --- | --- |
| TC-BUY-006 | **Data:** replace "The return should read `grand_total` **236.00** and post Dr 2100 236.00 / Cr 1200 200.00 / Cr 1300 36.00; a return at **0.00** with the 200.00 charged to 5400 means no price reached the line." with "The return reads `grand_total` **236.00** (D-BUY-31) and, because the receipt has not been billed, posts **Dr 2300 Goods Received Not Invoiced 200.00 / Cr 1200 Inventory 200.00** with no tax and no payable (D-BUY-26)." |
| TC-BUY-009 | **Fixture:** `po-invoiced`, not `po-received`. **Also needs:** "As *po-invoiced*, with the bill for the receipt of 6 paid in full (TC-BUY-008)." A return off a receipt nobody has billed leaves no supplier credit, and Record refund answers "…leaves no credit on the supplier's account…". |
| TC-BUY-011 | Add: "Delete the supplier before applying the credit to see the refusal for the credit alone; afterwards it is refused for the open bill." |
| TC-BUY-012 | **Also needs:** add "a firm with a GST number (TEST01 has none: GSTR-3B answers 'This firm has no GST number, so it has no return to file.')". |
| TC-BUY-014 | Add after **(HTTP)** wording, if any is wanted: "`POST /gst-returns/gstr2b/imports` takes `return_period` as `YYYY-MM`; the file's own `rtnprd` stays MMYYYY." |
| TC-BUY-019 | Replace "the standing discount fills a blank discount" with "the standing discount fills a blank discount **unless a supplier price list prices the line, whose own discount (0 where none is typed) then applies**". |
| TC-BUY-020 | Replace "a line with neither a supplier nor a preferred supplier is refused by name" with "a requisition with such a line saves and can be approved; **Convert to orders** refuses it by name: 'Name a supplier for … -- neither the line nor the product names one.'" |
| TC-BUY-021 | Replace "pass 6, reject 4 (once written off, once left in quarantine for a return)" with "pass 6 and reject 4 written off on one receipt; on a second receipt pass 6 and reject 4 left for a return. Passed and rejected must add up to everything the line holds." (The return of those four is BUYQ-1.) |
| TC-BUY-022 | Replace "PURCHASE_APPROVE_OVER_TOLERANCE and PURCHASE_APPROVE_OVER_BUDGET held by the administrator only" and "as the **Purchasing manager**" with "a user on a **custom role** that holds PURCHASE_APPROVE without PURCHASE_APPROVE_OVER_TOLERANCE or PURCHASE_APPROVE_OVER_BUDGET; the seeded *Purchase Manager* holds both and approves". Replace "**Block**" with "**Needs approval**" if that is what the screen calls `NEEDS_APPROVAL`. |
| TC-BUY-023 | **Also needs:** add "a bank account on `<SUFFIX>-V` too, or untick its bill: a run that pays a supplier with no bank account has no bank file ('These suppliers have no bank account to pay into: …')." |
| TC-BUY-025 | Replace "a period covering the bill of 708.00" with "a period **that has already ended** and covers a bill dated inside it (date the bill before today): an agreement is accrued only after its last day ('The period runs to …; accrue it after that, once every bill of the period is in.')". The fixture's bill is dated today, so the case needs a bill of its own. |
| TC-BUY-030 | **Also needs:** add "an HSN code on `<SUFFIX>-B` (the fixture creates it with none), or a product of the case's own with one". As written the fixture's bill is in the blank-HSN row. Drop "with its unit" until BUYQ-6 is decided. |
| TC-BUY-035 | Replace the steps' return "off the **receipt of 4** (which no bill names)" with "off the **receipt of 6 after its bill has been approved and paid**", and the expectation with "the supplier's row shows the return's value as a minus figure under **Credits**". A return off an unbilled receipt posts Dr 2300 / Cr 1200 and is no credit. |
| TC-BUY-041 | Replace "The file is … MB; the most a file may be is 10 MB." with "The file is larger than 10 MB, the most it may be." |
| TC-BUY-049 | Add: "'Nothing has changed.' is the screen's; the server saves again and answers '194C settings saved.'" |
| TC-BUY-063 | Replace "receives 3 serial-tracked units but 2 are entered: enter 1 more on the goods receipt." with "receives 3 serial-tracked units but 2 serial numbers are entered: enter 1 more on the goods receipt." |
| TC-BUY-070 | The server's words differ from the quoted ones: currency `US` is "A currency is its three-letter ISO code, such as USD or EUR."; no rate is "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." Keep the quoted ones only if they are the screen's. Add: "the order starts in USD on screen; the server saves an order that names no currency in rupees." |
| TC-BUY-075 | Step (3): replace "→ Save" with "→ Save → **Post**" and the expectation with "refused at Post" -- once BUYQ-8 is fixed; today it posts. Step (4): "A Bill of Entry with no item" cannot be saved at all (validation), so "Add at least one line before posting." is not reachable over the API. |
| TC-BUY-086 | Replace "(the server's own words for the same refusal: 'A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date.')" with the words the server uses today, "A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date." (BUYQ-9). |
| TC-BUY-087 | Step (4): replace "'A bill in USD needs its exchange rate: the rupees one USD was worth on the bill's date.' (the server uses the bill's wording for an order too)" with "'A purchase order in USD needs its exchange rate: the rupees one USD was worth on the purchase order's date.'" |

## Still to walk on screen

- Every label, banner, toast, dialog and tooltip the cases quote: 001 to 003,
  012 (badge), 013, 036 to 039 (the Approve dialog and Paid now), 040 to 042
  (the Attachments dialog and the Files column), 043 to 049 (the TDS lines in
  the Approve dialog, the payment hint's half-second, the settings cards),
  050 and 051 (TCS boxes and Net payable), 054 (channel choices), 056 to 062,
  063 and 064 (the Serials dialog), 066 to 069 (the scheme note, the gift
  line added once), 070 to 076 (Currency, the notes, the toasts), 077, 088,
  090 (the Capital goods tick and what stands under it), 082 to 085.
- TC-BUY-055 whole, and the template refusal of 054: they need a WhatsApp
  Business account that passes Test.
- TC-BUY-015, 049, 059, 069, 081: the read-only state of a screen for a role
  without the permission (the server's 403 was driven).
- TC-BUY-020: the amendment title on the print; 023: the bank file download
  from the screen; 024: a late receipt.

## Not verified

- **Nothing was read from the database.** Every figure above is what the API
  returned.
- **No traceback** for BUYQ-7: the running server's log has been silent since
  18:30:27 (BUYQ-14). Its cause is from reading the code.
- **TEST01's 708.00.** `GET /vendors/{id}/statement` for T09187AT1-V shows
  PI-2026-2027-000003 (2026-09-18) crediting 708.00 while the bill reads
  CANCELLED and nothing is outstanding. It predates this run and was not
  chased; it makes the unfiltered books check on TEST01 read -708.00.
- **Three connection resets** (WinError 10054) on list reads --
  `GET /vendors?page_size=100` once and `GET /finance/journal-entries?page_size=100`
  twice -- each answered normally on the next try. The server process did not
  restart. Not explained.
- Not driven at all, and server-side: the supplier catalogue file import
  (019), the reorder planner rounding to an order multiple (019), a sales line
  ignoring a supplier price list (019), *Raise requisition* from the reorder
  report (020), a late receipt in supplier performance (024), the HSN row
  falling by a debit note and a return (032), an expired rate contract (062),
  a price list or price level against a batch's PTR (084), a requisition
  naming another firm's supplier in the shared store (BUYQ-15).
- TC-BUY-066: the receipt "offers 4 free" on screen; over the API a receipt
  line starts at free 0 and the 4 were sent.
- The second half of TC-BUY-011 ("refused while the credit stands") was seen
  only together with an open bill.
- GSTR-3B after BUYQ-8: the double IGST claim was inferred from the journal,
  then the duplicates were cancelled; the return itself was not read while
  they stood.
