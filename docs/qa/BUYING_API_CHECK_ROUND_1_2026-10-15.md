# Buying API check, round 1 (2026-10-15)

Driven over HTTP against the running backend (http://127.0.0.1:8000) on two
finished Wholesale fixture firms made by `docs/qa/checks/buying/setup.py`
(firm one: Firm admin, Viewer, Purchase Executive and a custom approver role;
firm two: a second Firm admin). Kept scripts: `docs/qa/checks/buying/`
(`_buy.py` helpers, one `tc_buy_NNN.py` per case, six `p_buy_*.py` probes).
Run: `python docs/qa/checks/run.py buying` (about 100 seconds).

Result: **31 of 32 scripts clean, 1 failing** (the failing one is a product
defect, B-1 below). No backend code was changed.

## Cases

| Case | Result | Notes |
| --- | --- | --- |
| TC-BUY-001 order, approval cannot be skipped | PASS | approve on a draft is 422 with the stated message |
| TC-BUY-002 edit withdraws approval | PASS | a `status` in the body is ignored; history carries `approval_withdrawn` |
| TC-BUY-003 part receipt, then rest; zero line | PASS | order, receipt, bill and return lines of 0 are all refused |
| TC-BUY-004 cancel completed receipt | PASS | ledger `GOODS_RECEIPT_REVERSAL` is **-4**; inventory credited 400.00 |
| TC-BUY-005 invoiced receipt cannot be cancelled | PASS | |
| TC-BUY-006 damaged return | partial | everything but the last sentence (a return for more than the location holds, refused at Complete) which needs stock to leave by a sale or issue; skipped with a note |
| TC-BUY-008 pay the supplier | PASS | |
| TC-BUY-009 refund | PASS | refund POST answers 200 (not 201); over-refund names the 136.00 left |
| TC-BUY-010 replacement reopens the order | PASS | outcome change to Credit puts the order back to Received |
| TC-BUY-011 return off a paid bill | PASS | credit 236.00 applied; the new bill owes 944.00; vendor delete refused both times |
| TC-BUY-016 quantity picture, billing status | PASS | header status words matched loosely ("PART...", then a billed word) |
| TC-BUY-017 debit note on a paid bill | PASS | see case-text note 2 |
| TC-BUY-022 tolerance and budget | PASS | custom role approver refused with 403 naming the right; bulk approve refuses too; Warn / Needs approval both behave |
| TC-BUY-026 landed cost | PASS (proxy) | no sale driven: 4 sent back instead, giving 6 on hand of 10; inventory 600.00 / cost of goods sold 400.00 |
| TC-BUY-036 approve and pay | PASS | both journals as stated |
| TC-BUY-037 part now, more refused | PASS | |
| TC-BUY-038 reverse the payment | PASS | |
| TC-BUY-066 10+2 scheme | PASS | see case-text note 1 |
| TC-BUY-067 typed free kept, 0 refuses | PASS | |
| TC-BUY-093 free goods back off the receipt | PASS | reconciliation row received 12 / returning 12 / pending 0 |
| TC-BUY-094 same goods go back once | PASS | statement shows the bill and one return (708.00) |
| TC-BUY-095 free units after the bill's return | PASS | reconciliation rows as stated |
| TC-BUY-096 return takes its batch | PASS (on Wholesale) | the case names a Pharmacy firm; the batch rules are the same and a batch-tracked product was made on the Wholesale fixture |
| TC-BUY-099 free cap on a receipt | PASS | |
| TC-BUY-101 approval switched off | partial | steps 1-6 and 8-11 driven; step 7's "one Save also completes the receipt" is a screen behaviour and was skipped (see note 3) |
| TC-BUY-102 branch of a main office | partial | all server steps pass; the GST-state tax for the branch (step 7) is not driven (check vendors have no GST number), and the screens are not clicked |

Probes: `p_buy_bill_over_received`, `p_buy_return_over_received`,
`p_buy_other_firm_and_viewer` (Viewer and other-firm refusals, 401),
`p_buy_cancel_bill_after_payment`, `p_buy_payment_edges` all PASS.
`p_buy_receipt_over_order` FAILS on defect B-1.

## Script faults fixed (not product defects)

- `amount_owed` on a bill is the payable, not what is still outstanding; the
  helper `owing()` reads the payments `outstanding` list instead.
- `GET /payments` filters on `vendor_id`; `party_id` is silently ignored and
  returned every payment in the firm.
- A supplier refund answers 200, not 201.
- The ledger shows a receipt reversal as -4 (the case says "-4"; script wanted +4).
- Role codes must be lower-case; a role made by the platform admin is a platform
  role and cannot be assigned to a firm user, so the approver role is made by the
  Firm admin.
- Bill and return refusals now print the unit ("25 PIECE bought"); scripts match
  the words around it.
- Billing after a return must be for the quantity left (8, not 10).
- The statement lists one row per document; counted by row, not by text.

## Product defects

### B-1 (Low): a draft goods receipt does not hold the order line's quantity

Request: order of 10, approved. `POST /api/v1/goods-receipts` for 6 (draft),
then another `POST /api/v1/goods-receipts` for 5 on the same line.

Expected: refused at Save, as a draft supplier bill (4 then 3 on a receipt of 6)
and a draft purchase return (4 then 1) already are, and as TC-BUY-099 says a
draft receipt counts for free goods. Actual: **201**, a second draft; only
Complete of the second refuses it (422 "Receipt exceeds allowed quantity for
purchase order line 1."). Stock is safe; two drafts can stand that together
exceed the order. Cause: `goods_receipt_service.py:1913` compares
`prev_received` (completed receipts only) plus this line to the order, so
drafts are not counted for the bought quantity.

### B-2 (Low, may be by design): an order that is partly received can be cancelled

Request: order of 10, receipt of 6 completed, then
`POST /api/v1/purchases/{id}/cancel`.

Expected (as the probe first assumed): refused while goods stand against it.
Actual: **200**; the order reads CANCELLED while the completed receipt and any
bill stay in force (stock stays 6 on hand); a further receipt is refused
("goods can only be received against an approved order"). Only a fully RECEIVED
order is refused, "Received purchase orders cannot be cancelled."
(`purchase_service.py:1555`). If cancelling a part-received order is meant as a
short-close, it is what `close` is for; decide which. No script asserts it.

## Case text that is wrong

1. TC-BUY-066, 093, 094, 095: the refusals now read "can still send back 25
   PIECE bought and 4 free" and "10 PIECE of these goods have already gone back"
   (the unit name is inserted); the case text omits the unit.
2. TC-BUY-017: a second bill of exactly 500.00 cannot be made at 18% GST from whole
   units at 100; with 5 x 100 the bill is 590.00 and the balances are 472.00
   (not 382.00) after the credit and 590.00 after the cancel.
3. TC-BUY-101 step 7: the server does not refuse a Purchase Executive completing
   a receipt when "Goods receipts are completed as a step of their own" is on;
   the setting only shapes the screen. The wording "a receipt has no approver"
   is right, but a reader may expect a refusal.

## Skipped (printed notes, not failures)

- TC-BUY-006, 009, 010, 011: the "more than the location holds" refusal at
  Complete needs stock removed by a sale or issue, not driven here.
- TC-BUY-026: the sale of 4 of 10 was replaced by a return of 4 (same on-hand gap).
- TC-BUY-096: Pharmacy profile not used.
- TC-BUY-101 step 7 and the screen wording/toolbar parts of 001, 006, 036, 037,
  101 and 102: screens are not driven.
- TC-BUY-102 step 7: tax by the branch's state (no GST numbers on check vendors).

## Triage (2026-10-15, the loop)

- **B-1 -> D-BUY-78, not a defect.** A draft receipt brings nothing in and holds
  nothing; the order's remainder is checked at Complete (ERPNext / Zoho).
  `p_buy_receipt_over_order.py` now expects the second draft to save and its
  Complete to be refused.
- **B-2 -> D-BUY-77, Medium, fixed on this branch.** Cancel refuses an order a
  live receipt or bill continues, naming each, and says to close it instead
  (the D-SELL-11 rule). New probe `p_buy_cancel_part_received.py`.
- Case text corrected: TC-BUY-017 (second bill 590.00; owes 472.00, then
  590.00), and TC-BUY-066/093/094/095 refusals now name the unit (PIECE).
- TC-BUY-101 step 7: no change. The case expects one Save to complete the
  receipt, which is what the switch does; it does not claim a refusal.
