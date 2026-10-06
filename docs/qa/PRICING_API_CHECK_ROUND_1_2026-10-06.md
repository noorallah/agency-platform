# Pricing, promotions, loyalty, commission and targets: checked through the API, round 1, 2026-10-06

The first pass over this module, driven the way the eight buying and selling
rounds were: the real server over HTTP at http://127.0.0.1:8000 (version
1.3.0, checkout at `4d3b9082`, one test-only commit past `76329d19`), fixture
firms only, books read back through the API, nothing read from the database,
no source file changed and nothing fixed.

**All twelve cases were driven. Ten pass (four of them with a line of case
text to correct), 006 has the wrong figures in its text while the product is
right, and 007 cannot be run as written on any day.**
The probes beyond the book found **three High, six Medium and twelve Low**
things. The worst: a discount on the whole order, typed or given by an offer,
never reaches the delivery note or the bill, so the customer is billed more
than the order that was approved (PRCQ-1).

## When, and on which firms

Fixtures were built between 04:00 and 04:07 IST and everything was driven
between **04:03 and 04:37 IST on 6 October 2026, which is 22:33 to 23:07 UTC
on 5 October**: the whole round ran while the server's UTC day was one behind
the firm's day. Every date rule seen (coupon and price-list windows, weekday
offers, commission periods, loyalty expiry) was judged on the firm's day. The
server was not restarted and `/health` answered before and after. Six
requests answered 500, all from PRCQ-5. No request failed in transit.

Ten fixture firms, all built by `backend/scripts/test_fixture.py` in this
round, about 40 seconds each:

| Key | Fixture | Firm | Used for |
| --- | --- | --- | --- |
| SA | `selling-firm` | `T1006QPAE-S` | cases 004, 001, 002; probes 1, 2, 3, 11 |
| SB | `selling-firm` | `T1006XXHY-S` | cases 004, 001, 002 again; probes 3 (the bill discount), 4 |
| S9 | `selling-firm` | `T1006M9E2-S` | cases 011, 009; probes 5, 6, 10 |
| O3 | `selling-ordered` | `T1006RI22-S` | case 003 |
| L5 | `loyalty-points` | `T1006I5SE-S` | cases 005, 010; probe 7 |
| L10 | `loyalty-points` | `T1006M0WN-S` | case 010 first, 012 again; probe 7 second runs |
| D12 | `selling-invoiced` | `T10068FJ1-S` | case 012 |
| CA | `commission-firm` | `T1006OYSK-T` | cases 006, 008; probe 8 |
| CB | `commission-firm` | `T1006EVTD-T` | cases 006, 008 again, 007 |
| PH | `pharma-firm` | `T1006PQDI-P` | probe 6 (MRP, PTR, PTS) |

Scripts and logs are in the scratchpad folder `pricing1`, beside `round8`;
the helpers were copied, not changed. Every script and edit went through the
file tool.

## The twelve cases

| Case | Firms | Verdict | Evidence |
| --- | --- | --- | --- |
| 001 A price list is a ladder, and a promotion outranks it | SA, SB | **Pass** | STANDING read 0 → 2%, 15 → 4.25%, 18 → 6.75%. `PUT` with a fourth row 25 → 8%: 200, four rows. Quotation of 30 DET for C01: 7.5% `promotion` (189.00 off 2,520.00, total 2,750.58), the same after a revise. A quotation of 24: 6.75% `price_list` |
| 002 Editing an active promotion makes a new revision | SA, SB | **Pass** | `PUT` BULK5 with only the description changed: 200, a new row `version_number` 2 ACTIVE with the same `version_group_id` and `supersedes_promotion_id` naming the old row; the old row INACTIVE; the ACTIVE list holds one BULK5; a quotation of 30 takes 7.5% once. Audit `promotion.superseded` |
| 003 Promotion reports count a claim once | O3 | **Pass** | Performance: WELCOME 1 claim 25.20, the other three 0. Coupons: WELCOME10 1 claim, WELCOME10B 0. Claims: one row, SO-2026-2027-000001, 25.20, CLAIMED. Performance was also set against the claims list on SA, row by row: agrees |
| 004 An offer that does not stack ends the stack | SA, SB | **Pass, as far as the order** | 60 DET at 84: line 7.5% `promotion` (378.00), `bill_discount_amount` 200.00 `promotion`, total 5,265.16; CLEARANCE not applied; trace "This promotion does not stack, so evaluation stopped."; both survive an unchanged save. **The 200 never reaches the bill: see PRCQ-1** |
| 005 Loyalty: the scheme, a balance, spending points settles a bill | L5 | **Pass**, text wrong in one figure | Balance 209.6642 (200 given, 9.6642 earned by the bill of 483.21). 100 points on SI-26-27-000001: `LOY-RED-SI-26-27-000001` Dr 2600 100.00 / Cr 1100 100.00; customer owes 383.21; bill total unchanged. 5,000 points: 422 "That customer holds **109.6642** points, not 5000.0000." (the case says 100.0000). Expiring report empty |
| 006 Commission blends rates per line | CA, CB | **Case text wrong, product right** | Asha: collected 5,900.00, commission **420.00** (the case says 495.60). Bala: 4,720.00, **80.00** (the case says 94.40). Commission has been on net sales since 2026-09-24: 15% of 2,000 + 4% of 3,000, and 2% of 4,000. Achievement as the case says: Asha 5,900 of 1,000; Bala 4,720 of 100,000, 95,280 short |
| 007 Payouts: accrue, approve, pay, cancel | CB (CA in probe 8) | **Not runnable as written**; the flow passes when driven another way | "Accrue this month": 422 "That period has not ended…accrue it from 2026-11-01." To yesterday: 201 "Nobody earned anything in that period." (the fixture's sales are all dated today, and a period must end before today, so no day exists on which the case runs). Driven with three sales dated yesterday: 2 payouts accrued (Asha 190.00, Bala 40.00). Pay a draft: 422, the case's words. **Approve by the firm admin who accrued: 403** "The person who accrued a payout cannot approve it." Approve by a firm manager: `COMM-202610-365adf1a` Dr 5600 40.00 / Cr 2400 40.00. **Pay by the approver: 403.** Pay by the accountant: `…-PAY` Dr 2400 40.00 / Cr 1000 40.00. Cancel Asha's draft: nothing posted. Accrue again: 409, the case's words |
| 008 Whoever states a debt must not move the cash | CA, CB | **Pass** | Asha and Bala (SALES_EXECUTIVE): 403 on payouts list, approve, pay, rules, report, targets, achievement, price lists, promotions, loyalty settings |
| 009 Buy X get Y at a discount, and a combo price | S9 | **Pass** | Buy 2 get 1 at 50%: 3 units 42.00 off, 6 units 84.00, 1 unit nothing (falls to the list's 2%), 5 units 42.00. A cap of 50 on 84 + 42: 33.3333 and 16.6667. Combo DET + QQ for 150: two sets save 36.00 (18.00 a line); DET × 2 with QQ × 1 saves 18.00 (9.00 a line); DET alone nothing. A combo of one product: 422 |
| 010 Bonus points, customer history, day and time | L10, L5 | **Pass**, text loose in three places | ×3 offer: a bill of 485.688 earns 29.1413 (three times 9.7138), `LOY-SI-…` Dr 5700 29.14. ×3 and ×2 both live: 29.1413 (the larger, not 6). Multiplier 11, 0 and **1**: 422. Beside a discount: 422. Order count = 0: applies to C02 until its first **approved bill** (an approved order alone does not count). Days since ≥ 30: no at 29, yes at 30 and 35. Weekend offer: no on Tuesday, yes dated Saturday and Sunday. A window around now (04:10 IST): applies; 16:00 to 18:00: not now, and the trace says yes at 16:00 and 18:00, no at 15:59 and 18:01. Across midnight, weekday 8 and 0, minute 1440: 422 |
| 011 Bulk coupon codes, copying an offer | S9 | **Pass** | 50 codes `DIWALI-XXXXXXXX`, no 0/O/1/I/L, each 1 use and 1 a customer; 6,000 and 5,001: 422; CSV of 53 lines with uses. A code on an order for C01, approved: 2.5%. The same code again for C01 and for C02: not quoted (2% and 9.25% from the lists), trace "This coupon has been used as often as it allows." Copy `-NOV`: a DRAFT WELCOME-NOV, version 1, the new window, no coupons; again: 409; 101 ids: 422. Audit `promotion.copied` |
| 012 Claims to the principal | D12, L10 | **Pass**, text misses a precondition | Preview: scheme 25.20 (60% of 42.00), expiry 120.00, breakage 81.90, total 227.10. Raise: `CLAIM-CLM-2026-2027-000001` Dr 1420 227.10 / Cr 6940 25.20 / Cr 5500 201.90. Again: 422 "Nothing is left to claim…". **Credit note with no open supplier bill: 422** "…open bills add up to 0…". With a supplier bill of 354.00: adjustment 113.55 Dr 2100 / Cr 1420, PART_SETTLED; the rest by bank: SETTLED; one more rupee: 422; reverse a receipt: PART_SETTLED; cancel the credit note: back again. Cancel while part settled: 422. On L10: raise schemes only (25.20), then the rest (201.90), cancel (`…-REV`), raise again. Print: PDF with the three sections. PURCHASE_MANAGER may raise and receive; PURCHASE_EXECUTIVE and VIEWER read only; ACCOUNTANT and SALES_MANAGER 403 on everything |

No case names a risk in the book. 001, 002, 004, 006, 008, 010 and 012 were
run on two firms; 005's second run redeemed on another customer's bill by my
slip (probe 7 repeats it properly on L10); 003, 009 and 011 were run on one.

## Probe 1: discount precedence on one line

Rule: explicit amount > explicit percent > promotion > price list > the
customer's own rate > the customer group's; silence takes the arrangement,
zero refuses it; the recorded rate comes from the branch taken.

**Holds, on quotations and on orders (SA).** C01 buying 2 DET (group 1.75%,
own 7.5%, list 2%, an offer of 3%):

| Sent | Recorded | Source |
| --- | --- | --- |
| amount 10 and percent 5 | 10.00, 5.9524% | `amount` |
| percent 5 | 8.40, 5% | `percent` |
| nothing, or both null | 5.04, 3% | `promotion` |
| percent 0 | 0, 0% | `percent` |
| amount 0 | 0, 0% | `amount` |
| percent 0 and amount 5 | 5.00, 2.9762% | `amount` |
| offer retired, nothing | 3.36, 2% | `price_list` |
| a product with no list | 15.00, 7.5% | `customer` |
| C02, that product | 6.50, 3.25% | `customer_group` |
| a customer with nothing | 0 | `none` |

101%, a negative rate and an amount above the line are refused (422); an
amount equal to the line is taken (100%). A customer's own list (9.25%)
replaces the firm-wide ladder whole, at 2 and at 20.

## Probe 2: a downstream document inherits

Rule: a note ships at the order line's price and discount, a bill at the
note's, a rate as itself and an amount pro-rated; free goods follow.

SA, quotation QT-…-000020 → SO-…-000017 for C01: 30 DET (7.5% by BULK5), 10
NOL with 50.00 typed, 10 FRE with 2 free typed. After approval the price
list (to 10% and 20%), BULK5 (to 15%), all three selling prices and C01's own
rate (to 12%) were changed; a new quotation takes the new terms (2,700.00 at
15%, 12% on the others).

**Price and discount hold.** Note 1 (12, 4, 5): 84.00 at 7.5% (75.60),
100.00 with 20.00, 50.00 at 7.5%. Bill 1 (6, 2, 5): 37.80, 10.00, 18.75;
journal Dr 1100 1,047.19 / Cr 4000 887.45 / tax 79.87 + 79.87. Bill 2, note
2 and bill 3 the same way. Billed in all: 2,520.00 with 189.00, 1,000.00
with exactly 50.00, 500.00 with 37.50, as the order said. The return of 2
DET and 5 FRE credits at 84.00 less 7.5% and 50.00 less 7.5% (456.25).
BULK5's claim stays one row, CLAIMED 189.00.

**Free goods do not follow: PRCQ-4.** The notes shipped 5 + 5 of FRE and no
free unit; the order reads PARTIALLY_DELIVERED with 2 reserved for good.

## Probe 3: a bill discount and freight on the lines

Rule: both are split across the lines by what each is worth after its own
discount, stored on the line, taxed, the residual on the largest line.

**The split holds on the order (SA).** Lines worth 588.00, 270.00, 33.33
(18%) and 200.00 (5%) with 100.00 off and freight 50.01: shares 53.8791,
24.7405, 3.0541, 18.3263 (sum 100.0000) and 26.9450, 12.3727, 1.5273,
9.1650 (sum 50.0100); each line's tax is its rate on gross less discount
less share plus freight; lines' net 1,203.9722 = the total. Three equal
lines: 33.3334, 33.3333, 33.3333, the extra on the first. A line discounted
to nothing carries neither. Rate and amount together: the amount wins. Above
what the lines come to: 422. Negative freight: 422.

**Freight carries down; the bill discount does not: PRCQ-1.** Note 1 and
note 2 of that order carry freight 32.9631 + 17.0469 = 50.01 and a bill
discount of 0. The two bills come to 1,319.59 against an order of 1,203.97.

Journals agree with the bills as raised: SI-26-27-000004 Dr 1100 876.83 /
Cr 4000 752.29 / 62.27 + 62.27; the HSN summary gives the 5% product 209.17
taxable, 5.23 + 5.22.

## Probe 4: promotions

All on SB unless said. Every row behaved as the rule says except the last
three.

| Check | Result |
| --- | --- |
| An offer edited under a draft | BULK5 7.5% → 10% while SO-…-000001 was a draft at 7.5%: approval keeps 7.5% (378.00) and claims it under the group; a new order takes 10% |
| An offer retired under a draft | the draft approves at the retired offer's 10% and claims it |
| Stacking | 40 DET: 10% then 1% of what is left = 10.9% (336.00 + 30.24). 60 DET: 10% and 200 off; BIGORDER ends the stack |
| Best offer | 60 DET: BULK5B alone, trace "BULK5B was worth more (504.00 against 200.00)"; a 20% offer capped at 100 loses to it |
| A cap of 10.5% on a line | 10.9% held at 352.80, "trimmed from CLEARANCE", whose benefit falls to 16.80 |
| A total limit of 1 | two orders quoted at 5%; first approval claims; the second: 422 "Promotion LIM1 has been claimed as often as it allows. Re-save the document to price it without."; a third order is not quoted; the re-saved one takes its list and approves |
| Cancel gives the claim back | cancel the approved order: REVERSED, 1 left; the next order is quoted and claims |
| An edit does not reset the count | revision 2 still shows 0 left |
| The race | two approvals at once for one slot: one 200, one 422 by name; one APPROVED, one DRAFT |
| Once a customer | C01's second order not quoted; C02's first is; a quotation for C01 not quoted |
| Limits of 0 or less | 422 |
| Reports | performance equals the claims list for every offer (SA) |
| Free goods from an offer | FREE11 (buy 10 get 1): the order line reads 12 + 1 free and reserves 13. **A note of 12 ships 12: PRCQ-4.** With 1 free typed on the note it ships 13 and the bill reads 12 + 1 free; 3 free typed: 422 |
| A free product | GIFT7: the quotation and the order carry a second line, 0 charged, 1 free; the note needs that line sent with `free_quantity` 1 (quantity 0 alone is refused by name); the bill carries it; Cr 4000 533.61 |
| A return under an offer | all 12 charged units come back at 84.00 less 9.25% (1,079.42). **The free unit cannot: PRCQ-8.** The offer's claim stays CLAIMED |

Both free-goods offers show a claim with `benefit_amount` 0.0000 (PRCQ-10).

## Probe 5: coupons

S9. **Holds.** A code with 2 uses in all and 1 a customer: two customers
claim, the same customer again and a third are not quoted; report 2 claimed,
0 left. Windows are judged on the document's date on the firm's day: a code
from today applies today and tomorrow, not dated yesterday; ending today
applies today; ending yesterday does not; from tomorrow only dated tomorrow.
A code is matched whatever its case. A code ending before it starts: 422.
The code still reaches its offer after the offer is edited. Deleting an
offer deletes its codes. Switching an offer INACTIVE leaves its code reading
ACTIVE (PRCQ-16), though it gives nothing.

## Probe 6: price lists, levels, revisions, the floor and the limit

S9 and PH.

- **Ladder with fixed rates.** QQ (84): 0 → 80.00, 10 → 75.00 less 2%, 50 →
  10% with no rate. 1 unit 80.00; 10 units 75.00 at 2%; 49 units 75.00 with
  the offers' 8.425% in place of the list's 2%; 50 units **84.00** (the row
  at 50 has no rate, so the price falls back to the product's). A typed
  price beats the list; a typed 0 gives the goods away.
- **Windows.** A list from today applies today; one that ended yesterday
  does not; one ending today does; one from tomorrow only on a document
  dated tomorrow.
- **Levels.** A customer on a level with DET at 70.00 is quoted 70.00, less
  the list's 2%; a typed price wins; a product with no level rate falls to
  the list. Deleting a level in use: 409 by name.
- **Dated revisions.** DET revised to 91.00 from the 8th (by file) and 86.00
  from today: a document dated today takes 86.00, yesterday 84.00, the 8th
  91.00. The file import: a bad row reports "Row 3 (NOSUCH): Code: is not a
  product of this firm." and imports nothing, checked or applied; a good
  file imports. Three things under PRCQ-15.
- **MRP, PTR, PTS (PH).** A batch with MRP 120, PTR 90, PTS 80: a line
  pinned to it is priced 90.00 for a RETAILER, 80.00 for a STOCKIST, the
  product's 100.00 for OTHER or unclassed or with no batch named; a batch
  with no PTR falls through; a typed price wins; the customer's own list at
  85.00 outranks the batch. A counter bill from that batch: 90.00, and the
  print carries MRP 120.00. PTR above MRP: 422. PTS above PTR is taken
  (PRCQ-18). A price above the MRP: PRCQ-7.
- **The floor.** WARN: `price-check` names the line, approval goes through.
  BLOCK: a sales manager 422, with a reason 403 "…needs the price override
  permission"; the firm admin 422 without a reason and 200 with one, kept on
  the APPROVED event as "Price floor overridden: clearing old stock". The
  bill discount's share counts (72.00 with 10.00 off the bill is judged at
  67.00). Below cost reads "below its minimum price" or "below what it
  cost", never the figure. A sales manager cannot change the setting (403).
- **The discount limit.** SALES_MANAGER 5%: a typed 10%: 422 "Line 1 carries
  a discount of 10.00%, above your limit of 5.00%. It needs approval by
  someone allowed at least 10.00%."; a typed 5% approves; 20.00 off 168.00
  is judged at 11.90%; 4% on the line with 4% on the bill at 7.84%; the
  customer's own list at 9.25% is not judged; a firm manager with no row
  approves. A sales manager cannot raise his own limit (403). **A typed
  price is not judged: PRCQ-2.**

## Probe 7: loyalty

L5, second runs on L10.

| Check | Result |
| --- | --- |
| Earned at approval, and its cost | each approved bill: `LOY-SI-…` Dr 5700 / Cr 2600 for 2% of the bill's **total, tax included**, at the scheme's value. A draft earns nothing |
| Redemption settles | Dr 2600 / Cr 1100; the bill's total and tax unmoved; the customer's balance falls |
| Beyond the balance, beyond the bill | 422 "holds 109.6642 points, not 5000.0000"; 500 points on a bill owing 188.33: 422 "…owes only 188.33, and those points are worth 500.00."; exactly 188.33 settles it; one more: 422 |
| The minimum | it is a balance to reach, not a size: 40 points are spent from a balance of 109.66; a balance of 33.44 reads `redeemable` false |
| Draft bill, order id, 0, negative | 422, 404, 422, 422 |
| Goodwill | +1,000: `LOY-ADJ-…` Dr 5700 1,000.00 / Cr 2600; −10: the other way; 0, no reason, below zero: 422 |
| A cancelled bill | bill X earned 59.4720, 30 points were spent elsewhere; cancel X: REVERSED −33.4368 (what the customer had left), `LOY-SI-…-REV` Dr 2600 33.44 / Cr 5700 33.44 |
| A return | points taken back in proportion: `LOY-SR-…` Dr 2600 / Cr 5700 (9.12 on SA, 21.59 on SB, 3.86 on D12) |
| Expiry | a batch of 79.2960 lapsed, 20 already spent from it: the sweep takes 59.2960, `LOY-EXP-…` Dr 2600 59.30 / Cr 5700 59.30; a second sweep takes nothing |
| A point keeps its value | value raised from 1.00 to 2.00: the old batch still reads 59.47, the new bill's 59.4720 points are worth 118.94 |
| Scheme off | a bill earns nothing; a redemption is refused; a goodwill adjustment is still taken |
| A walk-in bill | earns nothing: no entry, no `LOY-` journal (L10) |
| Balance is a sum | the balances report equals the sum of each customer's entries (SA) |
| Liability against points | 2600 equals the report's worth on SA, SB, S9, L10, D12; on L5 it is one paisa under (PRCQ-17) |

Three things fail: **lapsed points can be spent (PRCQ-3)**, a redemption
cannot be undone (PRCQ-6), and two batches of one day are not spent oldest
first (PRCQ-21).

## Probe 8: commission and targets

CA; case 007's flow on CB.

| Check | Result |
| --- | --- |
| What a rule may say | a second live rule over one person's days in the same scope: 409, whatever its basis; per unit on COLLECTED, and with no product: 422 with the reason; a ladder not starting at 0, with a gap, or open below the top: 422; 101%: 422 |
| The rule of each row's own date | Asha's 15% on P ended three days ago and 10% began two days ago: 1,000 net sold four days ago earns 150.00 and yesterday 100.00; the report over both: 250.00 |
| A ladder ignores its flat rate | Bala's ladder given a flat 50% as well: 2,000 net still earns 40.00 |
| Margin | 10 P at 100 on a 50% margin rule: 200.00, which is half of 1,000 less a cost of 60 a unit (the line's cost is not in the API answer, so the cost was not read). A sale below cost: 0.00, not a negative. The line with no cost could not be made (see Not verified) |
| The base | 10 at 100 with 100 off the bill and freight 50 (bill 1,121.00): 45.00 = 5% of 900. Half of a bill of 1,180.00 collected: 25.00 |
| A payout is a snapshot | accrue, adjust +25 (a reason is required; above what was earned: 422; negative past zero: 422; a stale `If-Match`: 409); approve posts earned + adjustment; an approved payout cannot be adjusted |
| Cancel an approved payout | `…-REV` mirrors the accrual; the period is free and accrues again |
| One live payout a person a period | the same period, a day inside it, and four days overlapping it: 409 by name. Two accruals at once: one 201, one 409 |
| The period and the dates | not ended: 422; `accrued_on` before the period's end or in the future: 422; paid before it was accrued: 422. **Paid in the future is taken: PRCQ-9** |
| Who | accrue, approve, pay: firm manager and accountant; the sales manager reads only; nobody approves what they accrued or pays what they approved (403 by name); Asha and Bala 403 on all of it |
| Money going back after a payout | Bala paid 240.00; a receipt of 2,360.00 in the period reversed: the report now reads 200.00; the next accrual for him (an earlier stretch earning 20.00) carries `clawback_amount` 20.00 and pays 0.00 |
| The ledger | 2400 equals approved and unpaid (560.00, then 320.00, then 0); 5600 equals approved and paid (560.00) |
| Targets | a second target over the same month and basis: 409; backwards or negative: 422; the sales manager cannot set or lower one (403). With Bala's target lowered to 4,000 the report adds his 2% bonus (280.00 → 360.00); with it deleted, `target_met` reads null and the bonus goes |

## Probe 9: claims to the principal

Case 012 above, on two firms. 1420 equals the claims outstanding on both
(226.09 on D12, 227.10 on L10).

## Probe 10: access

S9, ten seeded jobs, a body of `{}` sent to every write so that an allowed
caller is answered 422 or 404 and nothing is written.

| Write | Allowed besides the firm admin |
| --- | --- |
| price lists, levels, revisions; price floor; discount limits; sales workflow | Firm Manager |
| promotions, coupons, copy | Firm Manager |
| loyalty settings and goodwill | Firm Manager |
| loyalty redemption | Firm Manager, Sales Manager |
| commission rules, accrue, adjust, approve, cancel, pay | Firm Manager, Accountant |
| targets | Firm Manager |
| customer groups | Firm Manager, Accountant |
| principal claims | Firm Manager, Purchase Manager |

Sales Executive, Counter Sales, Purchasing, Warehouse, Customer Support and
Viewer are refused every write in the module. The Sales Manager reads
offers, coupons, loyalty, commission and targets and writes none of them. A
standing discount on a customer needs `CUSTOMER_MANAGE_SETTINGS` and both
selling roles are refused it by name (create with 40%, edit to 35%: 403).

What a selling role can still do: type a price (PRCQ-2). The Sales Manager's
`PUT` of a customer's `price_level_id` and `customer_group_id` is also
taken (200); its effect on a price was not isolated.

## Probe 11: generic checks

SA, with SB as the other firm.

- **Paging.** Seventeen paged lists and reports: `page_size` 101, 1000, 0
  and −1 are 422, `page` 0 is 422, a page past the end is an empty 200.
- **Unknown ids.** Eighteen reads, deletes and actions: 404 by name; two
  malformed ids: 422. No 500.
- **Another firm's ids.** Sixteen calls with SB's price list, offer, coupon,
  customer and product: 404, or 422 / 409 on a create; SB's rows untouched.
- **A stale `If-Match`.** 409 on price lists, promotions, commission rules,
  targets and payouts. Price levels: PRCQ-13.
- **Deleted rows.** Gone from the list and 404 on read, for all six kinds.
- **Totals.** Promotion performance equals the claims list; loyalty balances
  equal the entries; the commission report's total equals its rows (500.00,
  560.00); the three discount reports agree on 306.50 with the approved
  bills' own lines. Gross differs by one product: PRCQ-14.

Two things fail: an offer naming a product that is not the firm's (PRCQ-5)
and the wording of four 409s (PRCQ-12).

## Probe 12: the books at the end

| Firm | Trial balance | 1100 = customers | 2600 = points' worth | 2400 = approved unpaid | 1420 = claims | 1200 = valuation |
| --- | --- | --- | --- | --- | --- | --- |
| SA | 55,772.95 balanced | 5,280.67 | 105.63 | 0 | 0 | 47,040.00 |
| SB | 45,764.46 balanced | 16,676.20 | 333.50 | 0 | 0 | 13,788.00 |
| S9 | 17,611.18 balanced | 5,501.16 | 110.02 | 0 | 0 | 8,400.00 |
| O3 | 6,000.00 balanced | 0 | 0 | 0 | 0 | 6,000.00 |
| L5 | 49,157.60 balanced | 13,309.98 | **1,012.83 against 1,012.84** | 0 | 0 | 19,380.00 |
| L10 | 13,506.12 balanced | 6,644.87 | 402.35 | 0 | 227.10 | 1,620.00 |
| D12 | 7,881.10 balanced | 1,231.57 | 24.63 | 0 | 226.09 | 4,980.00 |
| CA | 42,578.00 balanced | 2,950.00 | 0 | 0 | 0 | 10,500.00 |
| CB | 30,380.00 balanced | 0 | 0 | 0 | 0 | 7,200.00 |
| PH | 2,080.80 balanced | 100.80 | 0 | 0 | 0 | 1,860.00 |

Every figure in a row agrees with its sub-ledger except the one in bold. No
journal on any firm is unbalanced (read 25 a page).

## Findings

Provisional ids. High = wrong money, stock or tax, or a rule that can be
bypassed; Medium = a wrong record or a broken flow with a workaround; Low =
wording or convenience. Causes are from reading the code named.

| Id | Severity | What | Firms |
| --- | --- | --- | --- |
| PRCQ-1 | **High** | An order's discount on the whole bill, typed or an offer's, never reaches the delivery note or the bill | SA, SB, S9 |
| PRCQ-2 | **High** | The discount limit is passed by typing the price | S9, SB |
| PRCQ-3 | **High** | Points past their expiry date are spent like any others until somebody runs the sweep, and nothing runs it | L5, L10 |
| PRCQ-4 | Medium | Free goods on an order are not shipped unless the note states them again | SA, SB |
| PRCQ-5 | Medium | An active offer whose free product is not the firm's makes every matching quotation and order answer 500 | SA, SB |
| PRCQ-6 | Medium | A redemption cannot be undone, so a bill with points spent on it can never be cancelled | L5, L10 |
| PRCQ-7 | Medium | A price above the batch's MRP is refused only at the bill, after the goods have left | PH |
| PRCQ-8 | Medium | Free goods cannot come back on a sales return | SB |
| PRCQ-9 | Medium | A payout can be paid on a day that has not come | CA |
| PRCQ-10 | Low | A free-goods offer claims a benefit of nothing | SB |
| PRCQ-11 | Low | The promotions list searches the name and not the code | S9 |
| PRCQ-12 | Low | Four refusals say only "The request conflicts with existing data. Please retry." | SA, SB, S9 |
| PRCQ-13 | Low | A price level has no `ETag` and its edit ignores `If-Match` | SA |
| PRCQ-14 | Low | The discount-by-product report leaves out a product sold with no discount | SA |
| PRCQ-15 | Low | Price revisions: MRP below the selling price is taken; a revision dated in the past is taken in silence; the product read keeps the old price | S9 |
| PRCQ-16 | Low | A coupon reads ACTIVE after its offer is switched INACTIVE | S9 |
| PRCQ-17 | Low | Loyalty Payable is a paisa off the balances report after a redemption; `expiring_soon` counts a batch already lapsed | L5, L10 |
| PRCQ-18 | Low | A batch takes a PTS above its PTR | PH |
| PRCQ-19 | Low | Paying a paid payout answers "Only an approved payout can be paid. Approve it first…" | CB |
| PRCQ-20 | Low | A target of 0 is taken | CA |
| PRCQ-21 | Low | Two batches of points credited the same day are not spent oldest first | L5 |

### PRCQ-1: an order's bill discount never reaches the bill (High)

SB, 04:18:55 to 04:19:09 IST (`p3b.py`); S9 04:19:37 (`p3c.py`); SA 04:17:52
(`p3.py`).

1. **An offer's.** `POST /sales-orders` for C01, 60 DET at 84 → BULK5 7.5%
   (378.00) and BIGORDER `bill_discount_amount` 200.00, source `promotion`,
   **total 5,265.16**. Approve. Both claims read CLAIMED.
2. `POST /delivery-notes` for all 60, approve, dispatch → DN-26-27-000001:
   line 7.5%, `bill_discount_amount` **0**, total 5,501.16.
3. `POST /sales-invoices` from the note, approve → SI-26-27-000001 **total
   5,501.16**; Dr 1100 5,501.16 / Cr 4000 4,662.00 / Cr 2220 419.58 / Cr
   2230 419.58.
4. **A typed one.** C02, 10 DET at 84, `bill_discount_amount` 100 → order
   873.20; note and bill **991.20**. With `bill_discount_percent` 10 and
   freight 50: order 951.08; note and bill **1,050.20** (freight 50.00
   carried, the discount not).
5. **The note told the 10% again by its caller** → note 951.08; the bill
   raised from that note is still **1,050.20**.
6. **Part delivery (SA).** Order A of four lines with 100.00 off and freight
   50.01, total 1,203.97: two notes and two bills carry the freight in full
   and no discount, and come to **1,319.59**.
7. **Stages off (SB).** A counter bill of 60 DET for C01: bill SI-26-27-000005
   total **5,501.16** with no bill discount, while the order raised behind
   it (SO-…-000006) reads 5,265.16 with 200.00 `promotion`, CLAIMED.

**Expected:** the bill charges what the order was approved at (5,265.16,
873.20, 951.08, 1,203.97); freight already does this. **Actual:** the
customer is billed 236.00, 118.00, 99.12 and 115.62 more, with GST on the
difference. A typed bill discount on a counter bill works (873.20); a bill
discount typed on the bill itself works (probe 8). The performance report
and discount-by-promotion still count BIGORDER as claimed and worth 200.00
each time, while discount-by-customer reads `bill_discount` 0.00 for the
same bills.

**Suspected:** `app/delivery_note/services/delivery_note_service.py:488`
and `:609` (the note's discount is `data.bill_discount_percent` /
`_amount` and nothing reads the order's; for freight, `_inherited_freight`
at `:1779` is called at `:1941` when none is sent, and the discount has no
twin) and `app/sales_invoice/services/sales_invoice_service.py:717` and
`:996` (the same for a bill of documents, and for a counter bill whose
hidden order was given one by an offer). The desktop's note editor has no
field for it.

### PRCQ-2: the discount limit is passed by typing the price (High)

SB, 04:37:00 IST (`x7.py`); S9, 04:24:19 (`p56.py`).

1. `PUT /sales-orders/discount-limits` → SALES_MANAGER 5%, SALES_EXECUTIVE
   2%. Price floor as it comes: WARN. DET sells at 84.00 and cost 60.00.
2. As a sales executive: order of 2 DET with `discount_percent` 50 → 99.12.
   Approve as the sales manager → **422** "Line 1 carries a discount of
   50.00%, above your limit of 5.00%…".
3. As the executive: order of 2 DET with `unit_price` 42, `discount_percent`
   0 → the same 99.12. `GET …/price-check` names the line "below what it
   cost". Approve as the sales manager → **200**. Delivered and billed:
   SI-26-27-000010, Dr 1100 99.12 / Cr 4000 84.00.

**Expected:** a control over what a selling role may give away judges what
the line was sold at against what it should have sold at. **Actual:** only
the discount boxes are judged, so half price goes through as a typed rate.
The floor stops it only where the firm has switched it to BLOCK, and then
only below the minimum price or cost. `docs/PRICING_AND_PROMOTIONS.md` says
only a typed discount is judged, so this is the rule as written; the rule
does not hold what it is for.

**Suspected:** `app/sales_order/services/discount_limit.py:44`
(`TYPED_SOURCES`) and `:66`: nothing compares `unit_price` with the price
the ranking would have given. Related and not isolated: a sales manager's
`PUT /customers/{id}` with `price_level_id` or `customer_group_id` is taken
(200), where the standing discount needs `CUSTOMER_MANAGE_SETTINGS`.

### PRCQ-3: lapsed points are spent (High)

L10, 04:28:52 IST (`x3.py`); L5, 04:27:42 (`p7.py`).

1. Scheme expiry set to 1 month. A bill dated 2026-08-27 for a new customer,
   3,540.00, approved → EARNED 70.8000, `expires_on` **2026-09-27**. Expiry
   set back to 24 months.
2. A bill today, 118.00. `GET /loyalty/reports/expiring` → the batch, 70.8000,
   `days_remaining` **−9**, `awaiting_sweep` true. `GET /loyalty/{customer}`
   → 73.1600 points.
3. `POST /loyalty/redeem` 70 points on today's bill → **200**, 70.00;
   `LOY-RED-SI-26-27-000010` Dr 2600 70.00 / Cr 1100 70.00.
4. `POST /loyalty/expire` afterwards → 1 entry lapsed; 0.80 of the batch was
   left to take.

On L5 the same with 20 of a lapsed 79.2960.

**Expected:** points nine days past their date are worth nothing at the
counter. **Actual:** the balance a redemption is checked against is the sum
of the ledger, and a batch leaves it only when `POST /loyalty/expire` is
called. Nothing calls it: the route is the only caller in `app/`. A firm
that never presses it never expires a point.

**Suspected:** `app/loyalty/services/loyalty_service.py:1341` (`_points_of`
sums every entry) used at `:793`; `app/loyalty/api/router.py:165` is the
only call of `expire`.

### PRCQ-4: an order's free goods are not shipped unless typed again (Medium)

SB, 04:21:43 IST (`p4e.py`); SA, 04:16:11 (`p2.py`).

1. Offer FREE11 (buy 10 get 1). Order of 12 DET for C02 → line `quantity`
   12, `free_quantity` 1, `reservable_quantity` 13. Approve: 13 reserved.
2. `POST /delivery-notes` with `current_delivery_quantity` 12 and nothing
   else, approve, dispatch → `ordered_quantity` 13, `delivered_quantity`
   **12**, `remaining_quantity` 1. Stock 240 → 228. The order reads
   **PARTIALLY_DELIVERED**; 1 stays reserved.
3. Bill of the note → 12 charged, no free quantity.
4. The same with `free_quantity` 1 sent on the note line → 13 leave, the
   order reads DELIVERED, the bill reads 12 + 1 free.

On SA the same with 2 free units typed on the order (10 + 2 of FRE): two
notes of 5 shipped 10, 2 stay reserved.

**Expected:** silence takes what the order gave, as it does for the price
and the discount; a typed 0 refuses it. **Actual:** `free_quantity` on a
note line defaults to 0, and the desktop's note editor starts the box at 0
too. The customer is short of the goods the offer promised, the order never
completes, and the units stay reserved. Workaround: type the free quantity
on the note.

**Suspected:** `app/delivery_note/schemas/delivery_note.py:80`
(`default=Decimal("0")`, where the order line's is `Decimal | None`);
`delivery_note_service.py:1969`;
`desktop/lib/ui/delivery_notes/delivery_note_editor_dialog.dart:99`.

### PRCQ-5: an offer naming a product that is not the firm's breaks every matching sale (Medium)

SA, 04:35:20 IST (`x6.py gift`); SB, 04:37:04 (`x7.py`).

1. `POST /promotions`, ACTIVE, condition `line_quantity` EQUALS 9, action
   FREE_PRODUCT, `free_quantity` 1, `free_product_id`
   `00000000-0000-0000-0000-000000000001` → **201**. The same with another
   firm's product id → 201.
2. `POST /quotations` for 9 DET → **500** "An unexpected error occurred."
   `POST /sales-orders` → **500**.
3. A quotation of 8 → 201. Retire the offer; 9 → 201.

**Expected:** the offer is refused when written ("Say which product is
given away" is checked; that it is the firm's is not). **Actual:** six 500s
in this round. A product id in a `product_id` condition is not checked
either; that one only never matches.

**Suspected:** `app/promotions/services/promotion_crud.py` (no lookup of
`free_product_id`; `:419` only reads it back);
`app/sales_order/services/sales_order_service.py:2098` (`_gift_lines`).

### PRCQ-6: a redemption cannot be undone (Medium)

L5, 04:27:42 IST; L10, 04:37:05.

1. A bill of 118.00 approved; `POST /loyalty/redeem` 10 points on it → 200.
2. `POST /sales-invoices/{id}/cancel` → **422** "SI-26-27-000011 cannot be
   cancelled while it has loyalty points spent on it. Reverse or cancel
   those first."
3. The loyalty routes are settings, entries, adjust, redeem, expire and
   three reports. None reverses a redemption.
4. Giving the 10 points back by `POST /loyalty/adjust` (Dr 5700 10.00 / Cr
   2600 10.00) and cancelling again → the same 422.

**Expected:** the action the refusal names exists. **Actual:** a bill with
points on it cannot be cancelled by anybody; the way left is a sales return
or a credit note.

**Suspected:** `app/sales_invoice/services/sales_invoice_service.py:2848`;
no reversal in `app/loyalty/api/router.py`.

### PRCQ-7: a price above the MRP is refused only at the bill (Medium)

PH, 04:35:21 IST (`x6.py mrp`). One firm.

1. Batch B3 of AMX: MRP 120.00. Order of 1 pinned to it at `unit_price` 130
   (145.60 with tax) → 201. `GET …/price-check` → no finding. Approve → 200.
2. Delivery note, approve, dispatch → DISPATCHED.
3. Bill of the note → **422** "Line 1: charges 145.60 a unit with tax, above
   the MRP of 120.00 printed on the batch it ships."

**Expected:** the order, or at the latest the note, is refused. **Actual:**
the goods are out and the bill cannot be raised at the price the order was
approved at; it has to be typed lower on the bill.

**Suspected:** the check lives only at
`app/sales_invoice/services/sales_invoice_service.py:1985`.

### PRCQ-8: free goods cannot come back on a sales return (Medium)

SB, 04:21:55 IST (`p4e.py`). One firm.

1. A bill of 12 DET + 1 free (FREE11). `POST /sales-returns` for 12 against
   it, approve, complete → credited 1,079.42, stock +12.
2. A second return of 1 for the same line → **422** "Return quantity exceeds
   what was dispatched on the source document (12.0000 sent, 12.0000 already
   returned)."

**Expected:** the thirteenth unit can be taken back at nothing, as a
purchase return has done since D-BUY-56. **Actual:** the customer returns
everything charged and the free unit has nowhere to go but a stock
adjustment. The offer's claim also stays CLAIMED after the whole sale came
back.

**Suspected:** `app/sales_return/services/sales_return_service.py:1498`
(the cap is the charged quantity).

### PRCQ-9: a payout paid on a day that has not come (Medium)

CA, 04:31:20 IST (`p8.py`). One firm.

1. An APPROVED payout of 240.00, accrued on 2026-10-05.
2. `POST …/pay` with `paid_on` 2026-10-09 (three days ahead) → **200**
   "Payout paid."
3. The payout reads PAID, `paid_on` 2026-10-09;
   `COMM-202609-223f93d4-PAY` is POSTED and dated 2026-10-09.

**Expected:** refused like `accrued_on` in the future ("…a day that has not
happened yet."). **Actual:** only a date before the accrual is refused.

**Suspected:** `app/commission/services/payout_service.py:716`.

### The Low findings

- **PRCQ-10.** FREE11 and GIFT7 on SB: every claim row reads
  `benefit_amount` 0.0000, so the performance report costs a free-goods
  campaign at nothing. Best-offer mode values free units at the line's rate;
  the claim does not.
- **PRCQ-11.** S9: `GET /promotions?search=WELCOME-NOV` and `search=NOV`
  return nothing; `search=WELCOME` returns both offers (both are named
  "Welcome"). `app/promotions/services/promotion_crud.py:85` matches
  `Promotion.name` alone.
- **PRCQ-12.** "The request conflicts with existing data. Please retry."
  (409) is the whole answer to: a price list naming a product or a customer
  that is not the firm's; a price list with two rows at one break; an edit
  sent to a superseded offer row. Each has a plain cause to name.
- **PRCQ-13.** SA: `PUT /price-levels/{id}` with `If-Match: "99"` → 200;
  the row carries `version` and no route publishes it as an `ETag`.
- **PRCQ-14.** SA: discount-by-customer and by-salesman total gross
  5,141.33; by-product totals 4,941.33. The 200.00 is the 5% product, sold
  at no discount and missing from the by-product rows. The discount columns
  agree (306.50).
- **PRCQ-15.** S9. (a) `POST /products/{id}/price-revisions` with
  `selling_price` 50 and `mrp` 40 → 201; the product form refuses an MRP
  below the selling price. (b) A revision dated three days back at 70.00 →
  201 with no word; once today's revision was deleted it became the price
  in force, and a blank-price quotation today took **70.00** against a
  product that reads 84.00. (c) `GET /products/{id}` shows `selling_price` 84.00
  throughout; the price in force is on `GET …/price-revisions`
  (`is_current`) only.
- **PRCQ-16.** S9: offer ONEOFF switched to INACTIVE by an edit; its code
  ONE1 still reads ACTIVE on `GET /promotions/coupons/{id}`. Presented, it
  gives nothing. Deleting an offer removes its codes.
- **PRCQ-17.** L5: after the first redemption (140 points for 140.00) and
  the next earning, the customer's balance reads 98.8055 points worth 98.81
  while 2600 holds 98.80; the paisa stays to the end (1,012.83 against
  1,012.84). L10, with redemptions too, agrees. Not traced. Separately,
  `expiring_soon` on `GET /loyalty/{customer}` reads 99.1200 for a customer
  holding 19.8240 after the sweep (L5), and 70.8000 for one holding 2.36
  (L10).
- **PRCQ-18.** PH: `PUT` batch with PTR 90, PTS 95 → 200. PTR above MRP is
  refused by name.
- **PRCQ-19.** CB: `POST …/pay` on a PAID payout → 422 "Only an approved
  payout can be paid. Approve it first, which is what recognises the debt."
- **PRCQ-20.** CA: `POST /sales-targets` with `target_amount` 0 → 201; such
  a target is always met, which pays a rule's bonus.
- **PRCQ-21.** L5: one customer, two bills the same day, the first earning
  59.4720 points at 1.00 and the second 59.4720 at 2.00. 70 points spent →
  **129.47** (all of the second batch, then 10.528 of the first); oldest
  first would be 80.53. In probe 7's cancel check the later bill's batch was
  also the one spent first. It matters only when the value of a point
  changes within a day.

## Case text to correct

Changes for `docs/INDEPENDENT_TEST_CASES.md` (the book in `docs/qa/` is
generated from it).

| Case | What the text must say |
| --- | --- |
| TC-INCENT-004 | Add: "The case ends at the order. Until PRCQ-1 is settled the 200 off does not reach the delivery note or the bill." |
| TC-INCENT-005 | Step 4: "That customer holds **109.6642** points, not 5000.0000." (200 given, 9.6642 earned, 100 spent). Step 1's banner: the 50 is a balance to reach before any can be spent, not the smallest redemption: 40 points can be spent from 109.66 |
| TC-INCENT-006 | Asha: commission **420.00**, 15% of 2,000.00 on `-P` plus 4% of 3,000.00 on the rest: **8.4% of her net sales of 5,000.00**. Bala: **80.00**, exactly 2% of net 4,000.00. Add: "Commission is on net sales; tax and freight earn nothing. Collected and invoiced stay the money itself (5,900.00, 4,720.00)." |
| TC-INCENT-007 | Rewrite. Preparation: the three sales must be dated and collected **before today** (the fixture dates them today, so `commission-firm` needs sales dated yesterday, or the case is run the day after the fixture). Step 1: "Accrue a period that has ended (the 1st to yesterday). This month is refused: 'That period has not ended…'." Step 2: "Three people: the one who accrued cannot approve (403 'The person who accrued a payout cannot approve it…'), the one who approved cannot pay (403). Approve as a Firm Manager, pay as the Accountant." The journal reference is `COMM-YYYYMM-<first 8 of the id>`, dated the accrual day. Step 4's refusal is a 409 |
| TC-INCENT-009 | Add the figures driven: 3 units 42.00 off, 6 units 84.00, 1 unit none (the price list's 2% applies instead), 5 units 42.00; a cap of 50 on 126.00 splits 33.33 / 16.67; combo two sets 18.00 a line, one set 9.00 a line |
| TC-INCENT-010 | "A multiplier is above 1 and at most 10: 0, 1 and 11 are refused." "Customer order count counts **approved bills**; an approved order with no bill is still a first order." "Days since last order: use *at least* 30; *equals* 30 applies on the thirtieth day only." "A weekend or dated offer is tested with the quotation's date; the time of day is the moment it is raised" |
| TC-INCENT-011 | "A quotation takes a coupon and claims nothing, so one code can be quoted any number of times; it is used up when an **order** carrying it is approved. After that the same code on an order for the same or another customer gives nothing (the line takes its price list), with no refusal." |
| TC-INCENT-012 | Also needs: "an approved supplier bill from the principal's vendor, open for at least the credit note's amount: a credit note is set against what the firm owes that supplier, and is refused ('…open bills add up to 0…') without one." And: "Cancelling is refused while any part is settled; reverse the receipts and cancel the credit note first." And: "The Accountant cannot read or settle a claim; receipts are recorded by whoever holds PURCHASE_APPROVE." |
| TC-INCENT-001 | Step 3 at the API: the quotation line reads `discount_percent` 7.5, `discount_source` `promotion`. Nothing to change on screen |
| New cases wanted | (1) An order with a discount on the whole bill, down to the bill (PRCQ-1). (2) An order with free goods, a note raised with and without them (PRCQ-4). (3) Points past their date at the counter (PRCQ-3). (4) A typed price against the discount limit (PRCQ-2) |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **The ranking takes the higher tier even when it is worth less.** A
  first-order offer of 5% replaced C02's negotiated 9.25% (bill
  SI-26-27-000005 on L5 went out at 5%); the firm-wide list's 2% replaces
  C01's own 7.5% on the same product; a 2.5% coupon replaces either. The
  offer then reports a "benefit" for charging the customer more.
- **Loyalty points are earned on the bill's total, tax and freight
  included; commission is on net sales; targets are measured on the money,
  tax included.** Three bases for three incentives on the same bill.
- **Nothing runs the loyalty expiry sweep** (PRCQ-3), and nothing reverses a
  redemption (PRCQ-6).
- **A full return does not give an offer's claim back**; only cancelling the
  order does.
- **A price-list break with a discount and no rate drops the lower break's
  rate**: 49 units at 75.00, 50 units at 84.00.
- **The product read does not show the price in force** once revisions
  exist.
- **The Accountant has no access to principal claims**, and the Purchase
  Manager both raises a claim and records its money.
- **A payout paid from Cash takes Cash below zero** with no word (−40.00 on
  CB, −320.00 on CA).
- **Goodwill points can be given to the walk-in customer**, and adjustments
  are taken while the scheme is switched off.
- **A promotion reads back differently from how it is written**: an action's
  figures come back under `parameters`, and a combo's as `price` and `items`
  where the write takes `amount` and `combo_items`.
- **A breakage claim is raised at the selling value credited (81.90) while
  the damaged unit went back into stock at cost (60.00)**; the claim credits
  Inventory Adjustment, which the return never debited.
- **Free quantity on a bill line is not claimed from the principal**, as the
  case says.

## Left on the firms

Offers made and retired (INACTIVE) on SA, SB, S9, L5, L10; draft offers M10,
M2_5 on L5 and L10, WELCOME-NOV on S9. On SA: products NOL, FRE, G5, a third
customer, STANDING at 10% / 20%, BULK5 at 15%, C01's own rate at 12%, DET at
90. On SB: a supplier with a bill of 21,240.00, product GFT, BULK5B, stages
and limits back as they were, one order PARTIALLY_DELIVERED with 1 reserved.
On S9: product QQ with a minimum price of 70, four plain customers, lists
QLAD, WTODAY, WENDED, WFUTURE, WLAST, level WSALE, DET revisions dated the
3rd (70.00), the 8th (91.00) and the 9th (50.00, MRP 40.00), **so DET sells
at 70.00 there**, the floor at WARN, no limits. On L5 and L10: three and one
extra customers, a supplier bill each, 100 goodwill points on L10's Cash
sale customer, the scheme on at 2 per 100, 1.00, 24 months. On D12: a claim
PART_SETTLED with 226.09 due and an open supplier bill of 354.00. On L10:
claims of 25.20 and 201.90 RAISED. On CA and CB: extra rules, payouts PAID
and CANCELLED, one payout dated the 9th, a reversed receipt, Bala's target
deleted, three targets for November. On PH: batch rates on B2 and B3, an
order dispatched and not billed (PRCQ-7).

## Not verified

- **Nothing on screen.** The desktop was not opened; the screen checks
  09-S01 to 09-S05 were not run. Menu paths and messages in the cases were
  checked as API answers only.
- **Nothing was read from the database.** That every store is at
  `20261005_0333` was taken from the hand-over.
- **Everything ran once, in one window** (04:03 to 04:37 IST), all of it
  before 05:30 IST, when the UTC day catches up. No date rule was re-run
  with the two days agreeing.
- **Second firms.** Cases 003, 009 and 011, and PRCQ-7, 8, 9 and every Low
  but PRCQ-12 and 17, were seen on one firm.
- **Probe 2:** a credit note (the price-difference kind) and a debit note
  down the chain; a return against a delivery note not yet billed.
- **Probe 3:** GSTR-1 and GSTR-3B (the firms have no GSTIN); an inter-state
  sale; `additional_charges`; the printed bill's three rows.
- **Probe 4:** free shipping; a bill-discount percentage offer with a cap;
  conditions on territory, route, salesman, branch and category; the race
  was run once per firm, two requests.
- **Probe 6:** `rate_includes_tax` with a price list or an offer (the
  selling rounds covered the switch itself); a list for a territory; a list
  and a level together on a group; supplier-side lists, rate contracts and
  schemes; the near-expiry exemption from the floor; a scheduled revision
  taking effect as the date arrives.
- **Probe 7:** expiry of a batch aged by time; here the batches were born
  lapsed, by a bill dated 40 days back under a one-month expiry. Two
  redemptions racing for one balance. Points on a credit note. The paisa on
  L5 (PRCQ-17) was not traced to its line.
- **Probe 8:** margin with no cost on the line: a bill straight off an
  order is refused while the delivery-note stage is on ("This firm ships on
  a delivery note before it bills."), and with the stage off the chain
  dispatches, so the case could not be made through the API. A sales
  **return** after accrual (a reversed receipt was driven instead). INVOICED
  basis, WHOLE_AMOUNT ladders, per-unit rules, category rules,
  `max_commission_amount`, and the floor at exactly 1,000 were not driven.
  A salesman approving his own payout needs a salesman holding
  COMMISSION_MANAGE; none was made.
- **Probe 10:** the matrix says who is refused, by sending an empty body;
  that each allowed role's real write succeeds was seen only for the firm
  admin, the firm manager, the accountant (commission) and the purchase
  manager (claims). Custom roles were not tried.
- **Probe 12:** 2100 was not set against the suppliers on the four firms
  that bought.
- **The causes** given for every finding are from reading the code named,
  not from a debugger or a failing test.
