# Pricing, promotions, loyalty, commission, claims and lines in another unit: checked through the API, round 4, 2026-10-06

The fourth pass over this module, driven the way rounds 1 to 3 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `b714851f`), fresh
fixture firms only, books read back through the API, nothing read from the
database, no source file changed and nothing fixed.

**The round found new things: two High, six Medium and three Low (PRCQ-47 to
PRCQ-57).** The two High ones are not in what the fixes were asked to change;
they are in what the fixers said they could not verify:

- **A delivery note line naming another unit than its order line is not
  refused** (it was said to be). An order of 2 BOX at 1,200.00 delivered on a
  note typed "24 PIECE" is billed and approved at **33,984.00 where the order
  is 2,832.00**; an order of 24 PIECE delivered on a note typed "2 BOX" ships
  **24 pieces, bills 2 and leaves 22 still to deliver** (PRCQ-47).
- **A draft order saved again loses its offer.** Sent back the way the desktop
  sends it (the offer's free line left out), a box order under "buy 10 get 1"
  comes back with no free line and ships 24 where it should ship 26. Sent
  back as read, the goods stay free and the offer is no longer named: no
  claim, and an offer with a budget of 2 free units gave 4 (PRCQ-48).

**Every round 3 finding is fixed**, each by its original reproduction, on two
firms except where said. **Purchase by the box and the rate difference claim
give what they gave in round 3** apart from what the fixes changed, and **the
twelve cases give what they gave**; 007 still cannot be run as written. The
answer to B1, the question that mattered most: **16 cannot be shipped against
10**. Both notes of 6 save and both are approved, and the second is refused
at dispatch, so the stock is safe and the paper is not (PRCQ-49).

## When, and on which firms

Ten fixtures were built between 12:02 and 12:07 IST, one at a time, and
everything was driven between **12:09 and 12:44 IST on 6 October 2026, which
is 06:39 to 07:14 UTC on the same day**. The server was not restarted;
`/health` answered 200 before every script and at the end. **No request
answered 500 or 503, and the server's log holds no error for the window.**

**Memory.** Ten firms, the limit set for the round. Free memory was read
before each build and between scripts: it stood between 1.9 and 3.5 GB before
every build, and the lowest reading of the round was **941,384 KB, straight
after the seventh build (L1, 12:05)**; the builder waited about a minute, until
it read 2.1 GB, before the eighth. The lowest reading while driving was
1,202,076 KB (12:18). PostgreSQL did not fall over.

| Key | Fixture | Firm | Used for |
| --- | --- | --- | --- |
| S1 | `selling-firm` | `T100667G6-S` | cases 004, 001, 002; PRCQ-37, 38, 39, 40, 43; D-PRC-44, 45, 46; B1, B3, B4, B6, B7, B8; the e-invoice and GSTR-1; generic checks |
| S2 | `selling-firm` | `T10064CYP-S` | the same again; PRCQ-41; the second pass on PRCQ-39, B1, B4, B8 |
| S3 | `selling-firm` | `T100659Z3-S` | cases 011, 009; PRCQ-41, 42; D-PRC-45; section C; buying by the box (second firm); the re-save probe; claim receipt checks |
| R1 | `ready-firm` | `T10067V0N-R` | section B, buying; PRCQ-37, 38, 39 on purchase; B2, B7, B8 |
| P1 | `pharma-firm` | `T1006THK2-P` | PRCQ-36; the rate difference by batch |
| P2 | `pharma-firm` | `T1006EJV8-P` | the same again |
| L1 | `loyalty-points` | `T100617FE-S` | cases 005, 010; round 3's PRCQ-30 script; PRCQ-42; B5 |
| C1 | `commission-firm` | `T1006MWGX-T` | cases 006, 007, 008; the per-unit commission |
| D1 | `selling-invoiced` | `T1006XRBS-S` | case 012 |
| O1 | `selling-ordered` | `T1006F0SC-S` | case 003 |

Scripts and logs are in the scratchpad folder `pricing4`, beside `pricing3`.
Round 3's scripts were copied and run unchanged; the new ones are `n4*.py`.
Round 3's logs were compared with this round's by `cmp4.py`, which masks firm
tags, ids, times and document numbers and compares the two logs as bags of
lines (two journals read back in the other order are not a difference). "The
same on both" means that comparison showed nothing.

What went wrong on my side, so the record is straight:

- **Answers dropped in transit, on reads only.** From 12:29 a page of 25
  whole bills or orders (about 135 KB) was reset on the way back ("An
  existing connection was forcibly closed") 19 times, in five runs of three scripts. The
  server's log shows each of those requests completed with 200 in under 0.3
  s; the same pages read whole a moment later through another client. No
  write was affected. It stopped round 2's generic script twice at one read.
  My copies of two helpers were changed for it, through the file tool: a GET
  is read again up to nine times and a write is never sent twice blind
  (`h.py`), and lists are read 10 a page (`pl.py`). The API description
  could not be fetched by the script at 12:04 for the same reason and was
  fetched with `curl`.
- **`n4m.py` ran batch BM out on P1 and P2** and left seven approved orders
  and notes that could not ship, holding 96 pieces, for four minutes.
  `n4m2.py` cancelled them, received a fresh batch and drove what was left.
- **Two parts of `n4s.py` had to be run again**: one sent a field the
  product has no such name for (`hsn_code` for `hsn_sac`), and one spoilt its
  own next step by saving the order again (which is how PRCQ-48 was found).
- **Showing PRCQ-47 meant approving a bill of 33,984.00** on S1 and S2. Both
  bills were cancelled at once; the notes behind them stay dispatched.
- **S1 was given a GST number** (and its customer PC one) so that the
  e-invoice payload and GSTR-1 could be read; a fixture firm has none.
- Every script was written and changed with the file tool. No heredoc, no
  inline patch.

## A. The findings of round 3

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| PRCQ-36 | **Fixed** | P1, P2 | 1 BOX at 1,200.00, GST 12%, batch MRP 120.00, pinned: order 1,344.00, note approved and dispatched (12 leave), bill approved at **1,344.00**. The same note billed as 12 PIECE, with no price and at a typed 100.00: approved at 1,344.00 (`entered_quantity` 12). 1 BOX at 1,320.00 refused at the order's save, "Line 1: charges 123.20 a unit with tax, above the MRP of 120.00 printed on the batch it ships."; the same sentence at the bill's approval for 12 PIECE at a typed 110.00 and for 1 BOX at a typed 1,320.00; 7 PIECE at a typed 108.00 refused at "120.96 a unit". 1 BOX at 1,285.00 (119.93 a piece) approved; 7 PIECE with no price approved at 784.00. A counter bill of 1 BOX at 1,200.00, batch named or not: approved, 12 leave; at 1,320.00 refused. A box line not pinned: 1 BOX and 2 BOX shipped and billed |
| PRCQ-37 | **Fixed** | S1, S2 (sales); R1, S3 (purchase) | Note of 2 BOX at 1,200.00, GST 18%. 7 PIECE with no price: `entered_quantity` 7.0000, gross **700.00**, total **826.00**, Cr 4000 700.00, 63.00 + 63.00. The other 17 at a typed 100.00: 1,700.00, `unit_price` 1200.0000. Together **2,832.00**. A 25th piece: 422 "Invoice quantity exceeds the available source quantity." 5 + 5 + 14: 590.00 + 590.00 + 1,652.00 = 2,832.00 (the third stored as 1.1666). Purchase, receipt of 2 BOX at 720.00: 7 PIECE at a typed 60.00 is **420.00** (`unit_price` 720.0000, Dr 2300 420.00); 17 with no price **1,020.00**; goods received not invoiced ends 0.00, variance 0, the price-variance report empty; 5 + 5 + 14 clear 1,440.00 exactly |
| PRCQ-38 | **Fixed** | R1, S3 (purchase); S1, S2 (sales) | A purchase return of 7 PIECE against a BOX line: saved, approved, **COMPLETED**; the movement reads `quantity` 7.0000, `entered_quantity` 7.0000. 0.5 with no unit and 0.5 naming BOX: 422 at save, "BOX is counted in whole numbers, so 0.5 BOX cannot be entered." Off a supplier's bill: Dr 2100 495.60 / Cr 1200 420.00 / 37.80 + 37.80. A sales return of 7 PIECE off a bill of 2 BOX: completed, 826.00, Dr 4100 700.00, 7 back on the shelf, cost 420.00; 0.5 BOX refused in the same words; 18 more refused, 17 more taken; the same off a bill typed 24 PIECE. One thing is left on the purchase side: PRCQ-54 |
| PRCQ-39 | **Fixed, for an order left as it was first saved** | S1, S2, S3 (sales); R1, S3 (purchase) | "Buy 10 get 1": 2 BOX reads a second line "0 + 2 PIECE free, Free with B10X" with `free_promotion_id`; approval reserves 26; the note ships 26 (cost of goods 1,560.00); the offer counts 2 free units; the bill prints "Free with B10X, 0 + 2 free, PIECE". 24 PIECE: 2 free on the line. 12 BOX: 14 PIECE. A free-unit budget counts pieces (budget 3: 2 claimed, 1 left). Purchase: the preview's `scheme_suggestions` offers 2 PIECE of the same product, `free_uom_id` PIECE (14 for 12 BOX, 1 for 1 BOX, none for 24 PIECE, which carries 2 on its line); the line added (ordered 0, free 2, `scheme_id`) stays in PIECE even when sent naming BOX; received and billed, **26 pieces at 55.384615 = 1,440.00**: the free two at nil cost, averaged in. **Not fixed for an order saved again**: PRCQ-48 |
| PRCQ-40 | **Fixed** for bills | S1, S2; e-invoice and GSTR-1 on S1 only | The bill typed 24 PIECE prints "24, PIECE, 100.00"; 7 PIECE prints "7, PIECE, 100.00"; a box line prints "2, BOX, 1,200.00"; the quotation, order and challan print BOX. Offline e-invoice export: `Qty` 24.0 `UnitPrice` 100.0 for the first, 2.0 and 1200.0 for the box bill, no unit named. GSTR-1 HSN row: 24 + 2 + 7 = 33.0, taxable 5,500.00. The **credit note** of a return prints right; what the return sends to the portal and to GSTR-1 does not: PRCQ-50 |
| PRCQ-41 | **Fixed** | S3, S2 | Six pairs of 1.00 sent at the same instant from two connections: both 201 every time; journals `-PAY-1` to `-PAY-18` with no gap or repeat. Six pairs of 60% of what was owed: exactly one 201 and one 422 every time, "The claim has 13.20 still to settle, so 19.80 cannot be received against it." 1420 equals open claims afterwards |
| PRCQ-42 | **Fixed** | S3, S2 (round 3's sequence); L1 step by step | Round 3's sequence, which ended 79.17 against 79.18, ends with 2600 equal to the report on both firms (155.23 on S3 after later work). On L1 the two were read after each of: a bill of 424.80 (8.4960 points, 8.50), a quarter returned (6.37), an adjustment, a part redemption of 55.5, two more part returns, a cancelled bill, a batch born lapsed (5.51 lapsed), a return of lapsed points, the sweep: **difference 0.00 at all twelve readings** |
| PRCQ-43 | **Fixed** | S1, S2 | Drafts of 6 and 4: the draft of 4 reads `previously_delivered_quantity` 6.0000 and `remaining_quantity` 0 once the other is approved, on the read and on the list. Drafts of 3, 3 and 4: after A is approved B reads 3 and 4, C reads 3 and 3; after B is dispatched C reads 6 and 0; A, approved before any of it, goes on reading 0 and 7 |
| D-PRC-44 | **Fixed** | S1, S2 | A counter bill line of 2 naming `order_uom_id` BOX alone: 2 at 1,200.00, 2,832.00, 24 reserved at the save, 24 leave. BOX with PIECE, either way round: 422 "Line 1 names two units: BOX as the unit it is ordered in and PIECE as the unit it is billed in. A line typed straight onto a bill is sold in one unit; name that unit once." |
| D-PRC-45 | **Fixed** | S3 (round 3's script); S1, S2 (with a principal) | 10% on a line of 6, budget 100.00, the principal pays half. Billed: 60.00 given, claim preview 30.00. A return saved, then approved: still 60.00. Completed: the offer, performance, redemptions (`benefit_amount` 0 beside `claimed_benefit_amount` 60.0000) and discount-by-promotion read **0.00**, 100.00 left, and the preview is empty. A second order, 2 of 6 returned: 40.00 everywhere, preview 20.00. A third order takes the 60.00 left; a fourth gets nothing |
| D-PRC-46 | **Fixed** | S1, S2 | Note stage off, order of 1,180.00. 10% typed on the bill's line, and 100.00 typed: **1,062.00**; the manager limited to 5%: 422 "Line 1 carries a discount of 10.00%, above your limit of 5.00%. It needs approval by someone allowed at least 10.00%." 5% typed: approved by him. A price of 90.00: refused, "priced at 90.00 where the customer's price is 100.00". A typed 0 on an order that gave 10%: 1,180.00. A counter bill with 100.00 or 10% typed on the bill reads `bill_discount_source` **`typed`** |

## B. What the fixers could not verify

**1. Two draft notes of 6 and 6 against a line of 10 (S1, S2).** Both save.
The first is approved and dispatched; the second is **approved too (200)**
and refused where it is dispatched: 422 "Reservation is insufficient for
dispatch quantity." The same with both approved before either is dispatched,
and with a draft of 4 edited up to 6 beside a draft of 6. Six leave, the
order reads PARTIALLY_DELIVERED with 4 reserved; nothing is over-shipped or
over-reserved. The approved note of 6 prints a delivery challan for 6, cannot
be billed ("only a dispatched delivery note can"), cannot be edited ("Only
draft delivery notes can be updated.") and has to be cancelled; a fresh note
of 4 then finishes the order. A single draft of 11 is refused at save. The
fixer's reading is right: the cap is judged at save against approved notes
and not again at approval. PRCQ-49.

**2. A free-only purchase line (R1, S3).** Order of 2 BOX and a line of 0
ordered, 2 free under the scheme: kept as 2 PIECE. A receipt line that sends
0 and no free quantity is refused, "Line 2 receives a quantity of 0 and
nothing free. Type a quantity, or leave the line off the receipt."; with
`free_quantity` 2 it saves and completes: Dr 1200 1,440.00 / Cr 2300
1,440.00, 26 on the shelf at 55.384615. The bill carries the free line at
nothing and clears 1,440.00. The order reads RECEIVED. **Sending the free
units back as free is refused**: a return of quantity 0 and `free_quantity`
1 is 422 "Line 1 returns a quantity of 0. Type a quantity, or leave the line
off the return." Typed as a quantity of 1 on the free line it completes,
reads `current_return_quantity` 1 and `free_quantity` 1, one piece leaves,
and it posts **Cr 1200 55.38 / Dr 5400 Purchase Price Variance 55.38**; a
second the same; a third is refused, "can still send back 0 bought and 0
free." PRCQ-51.

**3. BEST_OFFER against "buy 10 get 1" on a box line (S1, S2).** Works. With
a 5% offer beside it, 2 BOX takes the free goods (the trace: "Best offer
only: BOF was worth more (200.00 against 120.00)"): 2 PIECE free, no
discount, 2,832.00, the same as 24 PIECE. 1 BOX takes 1 free piece over
60.00. 5 PIECE, which earn nothing free, take the 5%. In COMBINE both apply
(2,690.40). `POST /promotions/simulate` gives the right answer only when
`stock_factor` 12 is sent with the line; without it it counts 2.

**4. A product kept in BOX and sold in PIECE (S1, S2).** With only the rule
"1 BOX = 12 PIECE" every line in PIECE is refused, "no active conversion
rule converts PIECE to BOX. Add one under Units -> Conversion Rules, or
enter the quantity in BOX." With a second rule, 1 PIECE = 0.0833333333 BOX
(S2): 24 PIECE with no price fills **100.00 a piece**, 2,400.00, reserves 2
boxes, ships 2, bills and prints "24, PIECE, 100.00"; the limit works (50.00
a piece refused for the manager, "50.00% off in all", 95.00 approved); the
offer counts boxes (24 PIECE nothing, 120 PIECE earn 12 PIECE free on the
line). Two things are wrong. **The price list's break "5% from 2 boxes" is
missed by 24 PIECE**, which take the 2% step (48.00 off where 120.00);
2 BOX on the same list take 5%. And 7 PIECE leave 0.5833 of a box: cost of
goods 419.98 for 420.00 and 97.4167 boxes on the shelf. PRCQ-52. A line that
names no unit at all is taken as boxes: PRCQ-53.

**5. A redemption put back out of order (L1).** Works. 347.20 points; redeem
A 120 against one bill and B 150 against another; reverse A while B stands:
197.20 points, Cr 2600 120.00 / Dr 1100 120.00, the customer owes 2,210.00.
A second reversal of A: 422 "Those points were already put back, on
2026-10-06." Redeeming 200 then: 422 "That customer holds 197.2000 points,
not 200.0000." Reverse B: 347.20. A return of 5 of 10 on B's bill
afterwards: 335.40. Loyalty Payable equalled the report after every step.

**6. Free goods under an offer returned in another unit (S2, S1).** The bill of
2 BOX carries the free line of 2 PIECE. A return of quantity 0 and
`free_quantity` 1 on it is refused by the schema, "Input should be greater
than 0", with or without `return_uom_id`. Typed as a quantity of 1 on the
free line it completes at 0.00: one piece back, Dr 1200 60.00 / Cr 5200
60.00, and the offer, the performance report and the redemptions report read
1 free unit given (beside 2 claimed). 1 BOX of the charged line comes back
as 12 pieces and 1,416.00. PRCQ-51.

**7. A draft bill typed in pieces, saved again (S1, S2; R1, S3).** The
quantity is never changed, and it survives only if the client sends the
typed figure. The read gives `current_invoice_quantity` 0.5833,
`entered_quantity` 7.0000, `invoice_uom_id` PIECE. Sent back as read: 422
"PIECE is counted in whole numbers, so 0.5833 PIECE cannot be entered." Sent
with no unit, or in the shape the desktop's purchase editor uses (the stored
quantity with the line's own unit): 422 "BOX is counted in whole numbers, so
0.5833 BOX cannot be entered." Sent as 7 with `invoice_uom_id` PIECE: saved,
7 stays 7, 826.00 (495.60 on the purchase bill). PRCQ-55.

**8. A receipt line and a note line in another unit than the order's.** The
**goods receipt is refused by name** (R1, S3): "Line 1 is received in PIECE
where PO-…-000022 orders it in BOX. Receive it in the order's unit.", and the
same sentence the other way round. (7 or 24 typed in PIECE against 2 BOX are
refused sooner, as "Goods receipt exceeds allowed quantity for PO line 1.")
**The delivery note is not refused** (S1, S2): PRCQ-47.

## C. Regression

**Buying by the box (R1; round 3's `bx.py` unchanged, against R2's log).**
Every difference is a fix: `conversion_factor` now reads 0.0833333333 where
it read 0.0833000000; a draft bill of 7 PIECE at 60.00 stores 720.0000 where
it stored 720.0411; the bills of 7 and 17 PIECE clear 420.00 and 1,020.00
with nothing to variance (419.98 + 0.02 and 1,020.02 + 0.01 before); the
return of 7 PIECE completes where it stuck. Everything else is line for line
round 3's: 2 BOX at 720.00 as 24 pieces at 60.00, six orders three ways of
naming the unit, Inventory 8,640.00 for 144 pieces, the returns, the
refusals, a bill with no order, cost of goods sold 300.00 for 5 pieces.

**The rate difference claim (S3; by batch on P1, P2).** Line for line round
3's (against S4's log): 100 at 60.00 to 55.00 is 500.00, untouched by a
receipt and a sale of the day, the refusals by name, Dr 1420 500.00 / Cr 5400
500.00, once only, cancelled and raised again, receipts of 200.00 and 300.00.
By batch: two lines, 105.00 and 135.00, 240.00.

**Lines sold by the box (S1, S2; `a24.py` unchanged).** Differences from
round 3, all expected: the bills in pieces (PRCQ-37), the prints (PRCQ-40),
`order_uom_id` alone (D-PRC-44), the free line (PRCQ-39). **One difference
needs saying**: an order of 12 BOX read 16,756.00 in round 3 and reads
**15,481.60** now, because the fixture's own offer BULK5, 7.5% on a line of
25 or more, now counts 144 pieces where it counted 12. That is D-PRC-39
doing what its doc says of a `line_quantity` condition; a firm with such an
offer will see box orders start to qualify.

**Round 3's own scripts for PRCQ-22, 23, 27, 28, 29, 31, 32, 34, 35 and D7**
(S1, S2, S3) give round 3's figures; the only changed lines are the fixes
(D-PRC-45, D-PRC-46, PRCQ-41, PRCQ-43). D4 still shows 376.0830 against
376.0831 for drafts of 3 and 7.

| Case | Firm | Verdict | Difference from round 3 |
| --- | --- | --- | --- |
| 001, 002, 004 | S1 | **Pass** | None; two audit rows and two pending claims listed in the other order |
| 003 | O1 | **Pass** | None |
| 005 | L1 | **Pass**, text wrong in one figure as before | None |
| 006 | C1 | **Case text wrong, product right**, as before | None: Asha 420.00, Bala 80.00 |
| 007 | C1 | **Not runnable as written**, as before; the flow passes | None |
| 008 | C1 | **Pass** | None |
| 009, 011 | S3 | **Pass** | None; the lists hold more rows because the firm had been used |
| 010 | L1 | **Pass** | The balances are 140 points lower: case 005 ran first on this firm |
| 012 | D1 | **Pass** | None in the claim flow, the settlement or the two receipts a second apart. The second-run script (raise, cancel, raise again) ran after the claim here and stopped at "Nothing is left to claim"; its previews agree with round 3 |

The per-unit commission (C1): 60.00 on 2 BOX, on 24 PIECE and on a note of 2
BOX billed as 24 PIECE, as before.

**Generic checks.** Round 2's script (S1, S2, L1): the same answers; row
counts differ. New checks on the routes changed since round 3 (S1, S3, R1,
about seventy requests each time): a quantity of 0, a negative one, text, five decimal places, 0.5
of a whole-number unit, a unit id that does not exist or is not a UUID,
`entered_quantity` sent on a write (forbidden), another firm's note, bill,
claim and product (404, or "not available in this firm"), a read-only user
on every write (403), claim receipts of 0, less than 0, three decimal
places, no account, an unknown account, `stock_factor` 0 and negative, a
scheme of "buy 0", a free-only line naming an unknown scheme: all refused
cleanly, **nothing at 500**. One answer to note: a claim receipt dated
tomorrow is taken (Gaps).

**The books at the end, all ten firms.**

| Firm | Trial balance | 1100 = customers | 2100 = suppliers' reports | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation | 5400 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 2,577,676.69 balanced | 123,173.23 | 28,320.00 | 2,463.46 | 0 | 0 | 2,364,600.00 | 0 |
| S2 | 2,405,588.74 balanced | 83,876.23 | 28,320.00 | 1,677.51 | 0 | 64.54 | 2,253,480.02 | 0 |
| S3 | 469,927.34 balanced | 7,761.85 | 37,972.40 | 155.23 | 0 | 63.54 | 447,936.13 against **447,936.12** | -333.86 |
| R1 | 29,500.80 balanced | 1,270.00 | 24,850.80 | 0 | 0 | 0 | 22,873.86 against **22,873.85** | 166.14 |
| P1 | 32,191.20 balanced | 18,911.20 | 0 | 0 | 0 | 240.00 | 3,136.27 against **3,136.28** | -240.00 |
| P2 | 32,191.20 balanced | 18,911.20 | 0 | 0 | 0 | 240.00 | 3,136.27 against **3,136.28** | -240.00 |
| L1 | 54,260.67 balanced | 16,333.02 | 28,320.00 | 588.84 | 0 | 0 | 19,860.00 | 0 |
| C1 | 128,876.00 balanced | 8,496.00 | 0 | 0 | 0.00 (both paid) | 0 | 92,880.00 | 0 |
| D1 | 7,881.10 balanced | 1,231.57 | 354.00 | 24.63 | 0 | 227.10 | 4,980.00 | 0 |
| O1 | 6,000.00 balanced | 0 | 0 | 0 | 0 | 0 | 6,000.00 | 0 |

No journal is unbalanced on any firm. Receivables equal customers less
advances, payables equal the suppliers' outstanding less credits (R1:
27,045.60 less 2,194.80), Loyalty Payable equals the report **on every firm
this time**, commission and claims agree. Two columns do not come out clean:

- **Purchase Price Variance.** The -500.00 on S3 and -240.00 on P1 and P2
  are the rate difference claims, as designed. The **166.14 on R1 and on S3
  is three free pieces sent back at 55.38 each** (PRCQ-51). No variance is
  left by a unit conversion at the end, though one of 0.02 comes and goes on
  the way (PRCQ-54).
- **Stock.** On R1, S3, P1 and P2 the valuation report and the stock account
  part by **a paisa**; the report says so itself (PRCQ-56). GRNI of 2,880.00
  on R1 and S3 is two receipts left unbilled by the probes.

## Findings

Ids continue from round 3 (44, 45 and 46 are taken by the fixers' own). High
= wrong money, stock or tax, or a rule that can be bypassed; Medium = a wrong
record or a broken flow with a workaround; Low = wording or convenience.
Causes are from reading the code named, not from a debugger.

| Id | Severity | What | Firms | Where from |
| --- | --- | --- | --- | --- |
| PRCQ-47 | **High** | A delivery note line naming another unit than its order line is accepted: 12 times the order's value billed, or 24 pieces shipped for 2 billed | S1, S2 | B8 |
| PRCQ-48 | **High** | A draft order saved again loses its offer: the free goods vanish, or stay with no claim and get round the offer's budget | S1, S2, S3 | PRCQ-39 |
| PRCQ-49 | Medium | A delivery note for more than its order line has left can be approved; it is caught only at dispatch | S1, S2 | B1 |
| PRCQ-50 | Medium | GSTR-1's HSN quantity and the e-invoice of a sales return typed in pieces state the stored box figure | S1 | PRCQ-40 |
| PRCQ-51 | Medium | The free units of a free-only line cannot be returned as free; typed as a quantity, a purchase return books their cost to Purchase Price Variance | R1, S3 (purchase); S2, S1 (sales) | B2, B6 |
| PRCQ-52 | Medium | A product kept in BOX and sold in PIECE misses its price-list break at exact boxes, and loose pieces leave a rounded part of a box | S2 | B4 |
| PRCQ-53 | Medium | A sales line that names no unit is taken in the stock unit whatever the product's selling unit is | S1, S2 | B4 |
| PRCQ-55 | Medium | A draft bill typed in pieces cannot be saved again from what its own read returns | S1, S2 (sales); R1, S3 (purchase) | B7 |
| PRCQ-54 | Low | Loose pieces returned before the supplier's bill post 0.02 to Purchase Price Variance, taken back when the rest is billed | R1, S3 | PRCQ-38 |
| PRCQ-56 | Low | The stock valuation report and the stock account part by a paisa where the average cost is not a round figure | R1, S3, P1, P2 | books |
| PRCQ-57 | Low | Wording and figures: refusals that count in boxes without saying so, a zero printed three ways | all | several |

### PRCQ-47: a delivery note line in another unit than its order line (High)

S2 12:25:15 IST, S1 12:28:12 (`n4x.py`, part q); read back at 12:34 and 12:37
(`n4e.py`). The same on both.

The order by the box:

1. Product X08, kept and sold in PIECE at 100.00, GST 18%, rule 1 BOX = 12
   PIECE, 3,000 on hand.
2. `POST /sales-orders`: 2 with `sales_uom_id` BOX. 2,832.00. Approve.
3. `POST /delivery-notes` for that line with `current_delivery_quantity` 24
   and `sales_uom_id` PIECE: **201**. The line reads 24, PIECE, factor 1,
   `unit_price` **1200.0000**, gross 28,800.00, total **33,984.00**.
4. Approve 200, dispatch 200. 24 pieces leave (cost 1,440.00): right.
5. `POST /sales-invoices` for the note: 24 at 1,200.00, 33,984.00. Approve
   **200**: Dr 1100 33,984.00 / Cr 4000 28,800.00 / 2,592.00 + 2,592.00. The
   tax invoice prints "24, PIECE, 1,200.00". The order reads DELIVERED.

The order by the piece, raised and approved by the sales manager limited to
5%:

1. `POST /sales-orders`: 24 (PIECE) at 100.00. 2,832.00. Approve.
2. `POST /delivery-notes` with `current_delivery_quantity` 2 and
   `sales_uom_id` BOX: **201**. The line reads 2, BOX, **factor 1**, 100.00,
   236.00, `remaining_quantity` 22.
3. Approve 200, dispatch 200. The movement reads `quantity` **24.0000**,
   `entered_quantity` 2.0000; cost of goods 1,440.00. The challan prints "2,
   BOX, 100.00".
4. The bill of the note: 2 at 100.00, **236.00**, approved.
5. The order reads PARTIALLY_DELIVERED with 22 reserved, and a further note
   of 22 saves (2,596.00; cancelled).

**Expected** (`docs/UOM_FRAMEWORK.md`, "What is not typed in pieces"): "A
goods receipt line and a delivery note line are counted in their order
line's unit and one naming another is refused where it is saved." The
receipt is. **Actual:** the note takes the unit as a label and keeps the
order line's price for it. One way round the customer is billed twelve times
the order with the limit silent, since nothing was discounted; the other way
24 pieces are gone, 2 are billed, and the order will ship 22 more. Nothing
in the desktop's note editor was seen to send a unit, so this is reached
today through the API or an import; the rule is still one the server says it
enforces. Workaround: none once dispatched except a return.

**Suspected:** `app/delivery_note/services/delivery_note_service.py:2431`
(the conversion takes `item.sales_uom_id or source_line.sales_uom_id` and no
check that the two agree, as the goods receipt has); `:3405` passes the
line's unit to the stock ledger, which converts it, while `:2440` counts the
typed figure against the order line.

### PRCQ-48: a draft order saved again loses its offer (High)

S2 12:24:42 IST, S1 12:28 (`n4x.py`, part p); S3 12:34:10 (`n4z.py`). First
seen on S1 at 12:19 (`n4s.py`, part a).

Offer "buy 10 get 1" on a product with 1 BOX = 12 PIECE. `POST
/sales-orders` of 2 BOX reads two lines: 2 BOX, and 0 + 2 PIECE free with
`free_promotion_id` set. Then, a fresh order each time:

| What is done to the draft | Lines before approval | Reserved at approval | Claim on the offer |
| --- | --- | --- | --- |
| Nothing | 2 BOX; 0 + 2 PIECE free, offer named | 26 | CLAIMED, 2 |
| `PUT` with only the box line (the desktop's way) | **2 BOX only** | **24** | **none** |
| The same `PUT` twice | 2 BOX only | 24 | none |
| `PUT` with only the box line, its quantity 3 | 3 BOX only | 36 | none |
| `PUT` with both lines as the read returned them | 2 BOX; 0 + 2 PIECE free, **no offer named** | 26 | **none** |
| `PUT` with both lines, the box quantity 3 | 3 BOX; 0 + **2** PIECE free, no offer named | 38 | none |

And on S3, an offer limited to **2 free units in all**, three drafts of 2 BOX:

1. Approve the first: 2 claimed, 0 left.
2. Approve the second, untouched: 422 "Promotion BZ has 0 left of its budget
   of 2 free units, and this document would take 2. Re-save the document to
   price it without." Right.
3. `PUT` the third with both lines as read; approve: **200**. Its note ships
   26. The offer still reads 2 given: **4 given against a budget of 2.**

The same on S3 for free goods on the line itself (24 PIECE, 2 free): sent
back as read, the 2 stay and the claim is gone; sent back with no
`free_quantity`, the offer is applied again and claimed. A gift of
**another** product keeps its claim both ways.

**Expected:** `docs/PRICING_AND_PROMOTIONS.md`: "an editor should drop it
and let the engine add it again", and the desktop's order editor does
exactly that, on the stated ground that "The server adds them again from the
offer on every save"
(`desktop/lib/ui/sales/sales_order_editor_dialog.dart:216`). **Actual:** the
server does not add the box line's free line again on a save. So an order by
the box opened and saved once in the desktop gives the customer 24 where the
offer says 26, with nothing said; and any client that echoes the free
figure gives the goods away outside the offer's budget, its once-a-customer
limit, its reports and the principal's scheme claim. The second half is the
documented rule for a typed free quantity ("it then stands as typed"); what
makes it a way round is that the figure being echoed is the offer's own.
Workaround: cancel the draft and raise the order again.

**Suspected:** `app/sales_order/services/sales_order_service.py:2227`
(`_gift_lines`) and the call at `:2557` on the update path: the free line of
the line's own product is not offered again there, though a gift of another
product is.

### PRCQ-49: a note for more than the order has left can be approved (Medium)

S1 12:20:15 IST, S2 12:27 (`n4s.py`, part f); S2 12:25:38 (`n4x.py`, part t).
Steps in B1. **Expected:** the second note refused at save or at approval,
in the order line's words. **Actual:** approved, printable as a challan,
then refused at dispatch for its reservation; it cannot be edited and must
be cancelled. No goods move wrongly.

**Suspected:** `app/delivery_note/services/delivery_note_service.py:2441` to
`:2459` (the cap counts APPROVED, DISPATCHED, COMPLETED and CLOSED notes and
is asked only where the lines are built), against `approve_note` at `:686`,
which does not ask it again.

### PRCQ-50: a return typed in pieces, in GSTR-1 and on the e-invoice (Medium)

S1 12:42:17 IST (`n4f.py`). One firm: the others have no GST number.

1. A product with HSN 96081019, 1 BOX = 12 PIECE. A note of 2 BOX billed as
   24 PIECE and approved. `GET /gst-returns/gstr1` for the day: the HSN row
   reads quantity 24.0, taxable 2,400.00.
2. A sales return of 7 PIECE off that bill, completed (826.00).
3. The HSN row reads quantity **23.4167**, taxable 1,700.00.
4. `POST /einvoice/offline/export` with the return: `Qty` **0.5833**,
   `UnitPrice` **1200.069**.
5. The printed credit note is right: "7, PIECE, 100.00, 700.00".

**Expected:** 17, and 7 at 100.00: `docs/UOM_FRAMEWORK.md` says the e-invoice
and GSTR-1 "say what the bill says". **Actual:** that was done for the bill
and not for the return; the values and the tax are right, the quantities are
the stored part of a box.

**Suspected:** `app/gst_returns/services/gstr_service.py:2302`
(`current_return_quantity` times a share, where `:1730` reads
`entered_quantity` for a bill); the credit note's items in
`app/einvoice/services/payload.py`, which reads `stated_invoice_lines` for a
bill only.

### PRCQ-51: free units cannot be sent back as free (Medium)

R1 12:19:05 and 12:33:55 IST, S3 12:29 and 12:34 (`n4p.py` part b,
`n4y.py`); S2 12:25, S1 12:28 (`n4x.py`, part p). Steps in B2 and B6.

**Expected:** a return of 0 charged and 1 free against a line that was all
free. **Actual:** refused on both sides (a sentence on purchase, a bare
schema message on sales). Typed as a quantity it works, and the line then
reads 1 returned and 1 free of it. On the purchase side each such piece
posts its average cost, 55.38, to Purchase Price Variance, which is why R1
and S3 end with 166.14 there; whether a free unit sent back is a variance,
a loss or nothing at all is the owner's to decide, and the doc is silent. On
the sales side the cost goes back to stock at 60.00 and the offer's count
comes down, which is right.

**Suspected:** `app/sales_return/schemas/sales_return.py:75`
(`current_return_quantity` must be greater than 0);
`app/purchase_return/services/purchase_return_service.py` (the zero-quantity
refusal, and the journal of a line with no value).

### PRCQ-52: a product kept in BOX and sold in PIECE (Medium)

S2 12:25:24 IST (`n4x.py`, part r); S1 12:20:40 without the second rule
(`n4s.py`, part h). Steps in B4.

**Expected:** 24 PIECE are 2 boxes and take "5% from 2". **Actual:** 2%,
because the break is asked at 24 times 0.0833333333, which is 1.9999999992;
the line itself shows `base_quantity` 2.0000 and the offer counts it as 2.
The factor cannot be written more exactly: the column holds ten places. And
a firm has to write the rule the other way round at all, where a bill or a
return typed in pieces against boxes needs no such rule.

**Suspected:** `app/sales_order/services/sales_order_service.py:2589`
(`prices.rate_for(item.product_id, item.quantity * factors[index])`,
unrounded).

### PRCQ-53: a sales line that names no unit (Medium)

S2 12:25:36 IST (`n4x.py`, part s); S1 and S2 (`n4s.py` part h, `n4x.py`
part r).

1. A product kept in PIECE whose **selling unit is BOX**. A sales order, a
   quotation and a counter bill of 2 naming no unit: each 2 at 100.00,
   **236.00**, 2 pieces.
2. A product kept in BOX whose **selling unit is PIECE**. An order of 24
   naming no unit: 24 at 1,200.00, **32,048.80**, 24 boxes reserved.

**Expected:** the product's selling unit, as a purchase line naming no unit
takes the product's buying unit (2 naming nothing is 2 BOX at 720.00).
**Actual:** the stock unit. Nothing is wrong in what is stored; whether it
matters depends on whether every client always names the unit, which was not
checked on screen.

### PRCQ-55: a draft bill typed in pieces, saved again (Medium)

S1 12:19:35 IST, S2 12:26; R1 12:18:58, S3 12:29 (`n4s.py` part b, `n4p.py`
part a). Steps in B7. **Expected:** a write that takes back what the read
gave, or a read that gives what the write wants. **Actual:** the read gives
the stored 0.5833 beside the unit PIECE, and that pair is refused as "0.5833
PIECE"; the typed 7 is in `entered_quantity`, which the write forbids as a
field. No client can type pieces yet (the desktop's purchase editor sends
the line's own unit, the sales editor none), so today this stops an editor
from saving a draft that came in through the API or an import. Nothing is
corrupted.

### The Low findings

- **PRCQ-54.** R1 12:33:50 IST, S3 12:34 (`n4y.py`). A receipt of 2 BOX at
  720.00, not billed; a return of 7 PIECE: Dr 2300 419.98 / Cr 1200 420.00 /
  **Dr 5400 0.02**. The other 17 billed: Dr 2300 1,020.02, **Cr 5400 0.02**.
  Net nothing once the line is finished; with whole boxes there is no such
  entry. The accrual's share is worked from 0.5833 of 2
  (`app/purchase_return/services/purchase_return_service.py:942`).
- **PRCQ-56.** R1 22,873.86 against 22,873.85; S3 447,936.13 against
  447,936.12; P1 and P2 3,136.27 against 3,136.28. Each appeared once a
  product's average cost stopped being a round figure (55.384615 after free
  goods on R1 and S3; batches at 60.00, 50.00 and 45.00 on P1 and P2). Not
  placed further.
- **PRCQ-57.** "Return quantity exceeds what was dispatched on the source
  document (2.0000 sent, 0.5833 already returned)" and "can still send back
  1.4167 bought" to somebody typing pieces; 7 loose pieces received against
  an order of 2 BOX are refused as "exceeds allowed quantity" and not in the
  unit's sentence; a nothing reads `0`, `0.0000` and, for an offer's free
  units after a return, `1.00000000000000`.

## Case text to correct

Round 3's table still stands; nothing in it was applied. Changes, for
`docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 3's held-back cases | Can be written as passing: a box line from a batch with an MRP (order, note, bill at 1,344.00; 1,320.00 refused at 123.20); loose pieces of a box on a bill (700.00 + 1,700.00 = 2,832.00; 5 + 5 + 14) and on a return (7 pieces leave; 0.5 BOX refused) |
| New cases wanted | (1) "buy 10 get 1" on 2 BOX: a second line of 2 PIECE free, 26 ship. **Hold back** "saved again" until PRCQ-48 is fixed; (2) a supplier's "10 + 1" on 2 BOX: the suggestion, the free line, 26 at 55.384615; (3) what each document prints for a bill typed in pieces; (4) two receipts on one claim at once; (5) a return under an offer with a value budget (60.00 to 0.00; the preview); (6) a discount typed on a bill straight off an order (1,062.00; the 5% approver refused); (7) a counter bill naming one unit, and two |
| Any case that orders by the box on a `selling-firm` | The fixture's BULK5 (7.5% on a line of 25 or more) now applies from 25 **pieces**: 12 BOX is 15,481.60, not 16,756.00 |
| Hold back until fixed | A delivery note in another unit (PRCQ-47); a re-saved order under an offer (PRCQ-48); two notes over the order (PRCQ-49); free units returned (PRCQ-51) |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.
Round 3's list was not driven again except where A or B covers it.

- **A claim receipt dated tomorrow is taken** (201, S3).
- **An offer with 1 free unit left of 3 gives an order that earns 2
  nothing at all**, and says nothing: the order simply has no free line.
- **GSTR-1's HSN row adds pieces and boxes**: 24 PIECE, 2 BOX and 7 PIECE of
  one HSN code read 33. Neither the return nor the e-invoice names a unit.
- **`POST /promotions/simulate` counts the line as typed unless
  `stock_factor` is sent**; for 2 BOX it says the offer gave nothing where
  the order gives 2 free.
- **A free-only line must be received with its free quantity sent**; a
  receipt that sends 0 and nothing is refused, not filled from the order.
- **A box order now meets an offer's quantity condition in pieces** (BULK5
  above). Designed; a firm whose offers were written in boxes will want to
  read them again.
- **A line that names no unit prints no unit on the challan** (a product
  sold in its stock unit: "6, , 100.00"); the tax invoice falls back to the
  stock unit.
- **A bill of an approved note is refused well**: "DN-… is approved, so it
  cannot be billed: only a dispatched delivery note can. Dispatch it first."
  The dispatch refusal beside it says only "Reservation is insufficient".
- **An order pinned to a batch for more than the batch holds is approved**
  (round 3's gap, met again: it is how `n4m.py` left 96 pieces held).
- **The print's `format=thermal` was not recognised**; the A4 invoice came
  back.

## Left on the firms

On S1 and S2: one delivery note each DISPATCHED at 33,984.00 with its bill
cancelled (PRCQ-47), and one note of "2 BOX" billed at 236.00 with its order
part delivered and 22 reserved; approved notes that cannot be dispatched (5
on S1, 4 on S2) and 21 to 25 orders approved, draft or part delivered;
products N01 to N4K, X01 to XSB, HF, NGG with BOX rules; price lists
`K…`, `X…`; offers B10N, B10B, B10X, V45, BOF, BOD, K10, K10X retired;
limits off, stages on, promotion mode back to COMBINE; principal PR4. **S1
has GSTIN 29AAGCB7383J1Z4 and its customer PC 29AAPFU0939F1ZV.** On S3:
principals PRA, PRB, PRD; claims open for 63.54; offers GZ, QZ, BZ retired;
one order approved outside its offer's budget and shipped (PRCQ-48);
purchase stages as found. On R1 and S3: products NPA, NPS, NPC, NPY, NGP;
a supplier scheme "10 + 1" on NPS still active; two receipts unbilled
(2,880.00); 166.14 in Purchase Price Variance. On P1 and P2: batch BN (120
received), a BOX rule on AMX, a claim of 240.00 RAISED, seven
cancelled orders and notes from `n4m.py`. On L1: seven extra customers; the
scheme as the fixture set it. On C1: three per-unit rules; both payouts
PAID. On D1: claims RAISED for 227.10, an open supplier bill of 354.00.

## Not verified

- **Nothing on screen.** The desktop was not opened. What its editors send
  was read from the source in three places only (the sales order editor's
  free lines, the purchase bill editor's line, the absence of
  `invoice_uom_id` in the sales bill editor); nothing was clicked.
- **Nothing was read from the database.** That every store is at
  `20261006_0343` was taken from the hand-over.
- **Everything ran once, in one window** (12:09 to 12:44 IST).
- **One firm where two were asked**, to stay inside ten: section B's buying
  regression (R1; the new buying probes ran on S3 too); cases 003, 005 to
  008, 010 and 012 (one firm each); PRCQ-50, the e-invoice payload and
  GSTR-1 (S1 only); PRCQ-52 with the second rule (S2 only); B5 and the
  step-by-step PRCQ-42 (L1 only); the budget half of PRCQ-48 (S3 only).
- **Round 3's second firm for the regression** (R2, S4, L2, C2, D2) was not
  rebuilt; case 012's second-run script was not repeated as written.
- **PRCQ-36:** the product's own MRP standing in for a batch with none; a
  box split across two batches was not forced (the unpinned boxes each came
  from one batch).
- **PRCQ-39:** a short close and a principal's free-goods claim on the free
  PIECE line; a quotation's free line; the free line on a counter bill.
- **PRCQ-40:** the thermal print; the e-invoice was read from the offline
  export, not from a registration in the sandbox; GSTR-3B was not read.
- **PRCQ-41:** six pairs each way on two firms, not a load test; three at
  once, and simultaneous reversals, were not tried.
- **PRCQ-47:** a note in another unit beside free goods, a batch or a part
  delivery; the 33,984.00 bill was cancelled, not left to be settled or
  returned.
- **PRCQ-48:** which request the desktop really sends was read, not watched;
  a quotation saved again; an order by the box converted from a quotation.
- **PRCQ-49:** whether a tolerance setting changes it; a note approved in
  bulk.
- **B4:** a product kept in BOX on a purchase, a return, a batch.
- **B5:** a reversal after the points it gives back have passed their
  expiry.
- **The generic checks** did not sweep the access matrix of round 1 again
  beyond a read-only user and the sales manager's limit.
- **The dropped reads** were not traced beyond the server's log: whether the
  cause is this PC's security software or something in how a large answer
  is closed was not established.
