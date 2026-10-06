# Pricing, promotions, loyalty, commission, claims and lines in another unit: checked through the API, round 6, 2026-10-06

The sixth pass over this module, driven the way rounds 1 to 5 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `d19b3f66`, PR #1295,
migration head `20261006_0344`), books read back through the API, nothing
read from the database, no source file changed, nothing fixed, no test suite
run and no git write.

**The round found new things, so it does not close the module: five High and
three Low (PRCQ-63 to PRCQ-70).** One of the five High is in pricing proper
(offers); one is commission reading a selling document; three belong to
selling and buying and were reached from the suspicions the fixers left.

- **Every round 5 finding is fixed by its original reproduction**, on two
  firms each: PRCQ-58, 59, 60, 61, 62 and the return after a credit note
  (D-SELL-88). The clawback round 5 never ran was run: the next accrual for
  the person carries the 17.50.
- **What is left of PRCQ-58 is one shape**: two lines of the same product,
  both carrying an offer's free goods, sent back in the other order. Each is
  taken for the other, the figures differ, and both stand as typed: 5 free
  units shipped unclaimed beside a budget of 5 that another order then spent
  in full (PRCQ-63).
- **A customer can still be credited more than they were billed, three other
  ways**: a return with a typed price or charge above the bill's (3,540.00
  against 2,832.00, PRCQ-64); a note billed in two parts with the credit
  note on the second bill (3,304.00 against 2,832.00, and 472.00 *short*
  when the credit note is on the first, PRCQ-65). **The purchase twin is
  open too**: 2,171.20 claimed from a supplier against a bill of 1,699.20
  (PRCQ-67).
- **A return raised off the delivery note after the bill exists takes
  nothing off commission, targets or the bill's outstanding** (PRCQ-66): the
  same goods returned off the bill take 35.00 and 17.50 off; off the note,
  0.00 and 0.00.

**The regression is unchanged**: purchase by the box, the rate difference
claim, promotion budgets, principal claims and the twelve cases give what
they gave in round 5; the differing lines are the fixes' own wordings and my
running order.

## When, and on which firms

Everything was driven between **15:05 and 15:38 IST on 6 October 2026, which
is 09:35 to 10:08 UTC on the same day**. Six fixtures were built between
15:24 and 15:27 IST, one at a time; round 4's and round 5's sixteen firms
were used again wherever a clean firm was not needed. The server was not
restarted; `/health` answered 200 before each of the 59 script runs and at
the end. **No request answered 500 or 503.** The server's error log for the
window holds two warnings, both from the background loops (messaging,
reservation lapse) touching firm `T10061BYP-R` in the seconds between its
creation and its provisioning, and no error.

**Memory.** Free memory was read before each build and before each script.
The lowest reading of the round was **1,767,832 KB at 15:29:18 (before
`a24.py` on N2, two minutes after the sixth build)**; the lowest before a
build was 2,469,736 KB. No build had to wait. One read was dropped in
transit (`g.py`, a GET, read again by the helper); no write was sent twice.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| S1 | `selling-firm` | `T100667G6-S` | | A: PRCQ-58, 60, 61, 62, the return after a credit note; B2, B3, B5, B6, B7, B9; unchanged items |
| S2 | `selling-firm` | `T10064CYP-S` | | A: PRCQ-58, 60, 61, 62; B5, B6, B7; unchanged items |
| N1 | `selling-firm` | `T100657VP-S` | | A: the return after a credit note on a second firm with a GST number; B2, B3, B9 |
| C1 | `commission-firm` | `T1006MWGX-T` | | A: PRCQ-59 and the clawback; B1 |
| C2 | `commission-firm` | `T1006DWN6-T` | | A: PRCQ-59; B1 |
| R1 | `ready-firm` | `T10067V0N-R` | | A: PRCQ-62 (a); B4; B8 |
| S3 | `selling-firm` | `T100659Z3-S` | | A: PRCQ-62 (a); B4 |
| R2 | `ready-firm` | `T1006X0KB-R` | | B8 (read only) |
| P1, P2 | `pharma-firm` | `T1006THK2-P`, `T1006EJV8-P` | | the batch over-pin, unchanged |
| N2 | `selling-firm` | `T1006WO42-S` | yes | C: cases 001, 002, 004, 009, 011; budgets, claims, the rate difference; generic checks |
| R3 | `ready-firm` | `T10061BYP-R` | yes | C: buying by the box |
| L3 | `loyalty-points` | `T1006ULEU-S` | yes | C: cases 005, 010; round 3's and round 4's loyalty scripts |
| C3 | `commission-firm` | `T1006IN90-T` | yes | C: cases 006, 007, 008 |
| D3 | `selling-invoiced` | `T100625YI-S` | yes | C: case 012 |
| O3 | `selling-ordered` | `T10067YL6-S` | yes | C: case 003 |
| L1, L2, D1, D2, O1, O2 | | | | books only |

Scripts and logs are in the scratchpad folder `pricing6`, beside `pricing5`.
Round 3's, 4's and 5's scripts were copied and run unchanged for the
regression; the new ones are `r6.py` (helpers), `a58.py`, `c59.py`,
`dup6.py`, `s6.py`, `b1.py`, `p6.py`, `b8.py`, `b9.py`, `u6.py` and
`peek.py`. Logs were compared by round 4's `cmp4.py`. "The same on both"
means that comparison showed nothing.

What went wrong on my side, so the record is straight:

- **`a22.py` is not a valid regression this round.** I ran `c911.py` before
  it on N2 so that product QQ would be 84.00 (round 5 had it the other way
  and case 009 read 460.00). `c911.py` makes QQ with no stock, `a22.py` then
  finds it and its notes are refused at dispatch ("Insufficient available
  stock"). Eleven approved notes on N2 cannot ship. `a24.py`, `a35.py`,
  `a27.py`, `a28.py` and `cr.py` do not use QQ and are unaffected.
- **The first swap probe (`a58.py` part w) proved nothing**: a budget of 2
  free units does not give a draft that needs 5 any, so there was nothing to
  echo. It was run again with a budget of 5. Its three orders are on S1 and
  S2.
- **`s6.py` part e stopped at its first line on S1**: offer code QE6 was
  round 5's. Codes were changed to QH6 and Z6H and the part run again.
- **One heredoc was sent to the shell** (a no-op `print`), against the rule;
  every script edit was made with the file tool.
- **A draft credit note of 2,773.00 was saved and cancelled** on S1 and S2
  to show the cap admits exactly what is left.

## A. The findings of round 5

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| PRCQ-58 | **Fixed** by its reproduction; one shape left (PRCQ-63) | S1, S2 | `b5.py` part d again, budget of 2 spent by another order: the three-line draft with line 1 deleted and the other two echoed as 1 and 2 saves as **2 BOX alone**, approved, 24 reserved, no claim; the draft with a line inserted first, the same; the control the same; the offer reads 2 of 2. Shipped: 24 leave (3,000 to 2,976, to 2,952). `b5h.py` again, a principal's offer with a budget of 8: A (left as saved), B (line 1 deleted, renumbered), C (24 PIECE with 2 free on the line, renumbered) and D (echoed in place) each end **offer named, CLAIMED 2**; the offer reads **8.0000 claimed, 0.0000 remaining**; `POST /principal-claims/preview` **480.00**, four lines of 2 at 120.00 (round 5: 240.00). **A line moved and its quantity changed in one PUT**: box line moved to 1 and made 3 BOX, the free line echoed as 2: 3 PIECE free, named, claim 3, 39 reserved; 24 PIECE with 2 free moved and made 36: 3 free on the line, named, claim 3. **Two lines of one product, one moved** (24; Z5E; 36 with the middle deleted): 2 and 3 free, both named, one claim of 5. **A gift of another product moved**: gift line at 2, named, claim 1. **Typed figures stay typed**: a free-only line typed by hand (0 + 2 of a product with no offer) moved from 3 to 2: still 0 + 2, no offer named; 24 PIECE with a typed 3 moved: 3, typed, no claim, 27 reserved; the engine's own free line moved and sent as 0 + 5: 5, typed, no claim, 29 reserved. **Quotations**: the line response carries `free_promotion_id`; budget open, 24 PIECE: the order reads 24 with 2 free, **offer named, CLAIMED 2**, 26 reserved (round 5: no offer named, no claim); a typed 3: carried as 3, typed, no claim; the quotation echoed with line 1 deleted (the line renumbered 1, and the box line sent alone): the order names the offer and claims 2; **budget spent** (4 of 4): the quotation itself shows nothing free, its order has nothing free, 24 reserved, no claim; a typed 3 with the budget spent: 3, typed. Cancelling brings the offer to 0 |
| PRCQ-59 | **Fixed** | C1, C2 | 24 PIECE at 2.50: +60.00; 7 back: **-17.50**; the other 17 back: **-42.50** (0.00 left). 2 BOX billed by the box: +60.00; 1 BOX back -30.00; 7 PIECE back -17.50. 2 BOX billed as 24 PIECE: 7 PIECE back -17.50; 1 BOX back -30.00. 24 + 2 free billed: +60.00; **1 free PIECE back: 0.00**; **a credit note of 400.00 (472.00): 0.00**; then 7 charged PIECE back: -17.50 (the return is 688.33, priced on what the bill is still worth). The control, 5%: +120.00 and -35.00. The same on both firms. **The clawback (C1)**: the PAID period 1 to 5 October now reads 368.50 against the 386.00 paid. Accruing today alone is refused: 422 "That period has not ended. … accrue it from 2026-10-07." So a sale of 2,832.00 was dated 30 September (5% on invoiced: 120.00) and September accrued: **`earned_amount` 120.00, `clawback_amount` 17.50, `payable_amount` 102.50**, DRAFT. The person who accrued it cannot approve it (403); the firm manager approved it: **Dr 5600 102.50 / Cr 2400 102.50**; 2400 equals approved unpaid payouts. Accruing August afterwards: "Nobody earned anything in that period." (the shortfall is not taken twice) |
| PRCQ-60 | **Fixed** | S1, S2 | 422 "Lines 1 and 2 of the request are both numbered 1. Number each line once." on **create and update** of sales order, quotation, delivery note, sales bill, sales return, goods receipt, supplier bill and purchase return: 16 of 16 on each firm. Lines numbered 2, 1, 2: "Lines 1 and 3 of the request are both numbered 2." The draft after the refused `PUT` still reads 413.00 over lines 1 and 2. The rendered shape: `{"success":false,"error":{"code":"validation_error","message":"The request validation failed.","details":[{"field":"body.lines","message":"Value error, Lines 1 and 2 of the request are both numbered 1. Number each line once.","code":"value_error"}]},"timestamp":"…","requestId":"…"}` |
| PRCQ-61 | **Fixed** for a bill raised after the return; two shapes left (PRCQ-69) | S1, S2 | Round 5's reproduction: 1 BOX and 1 free PIECE back off the note; the bill of 1 BOX reads and prints **"Free with QH6, 0 + 1 free, PIECE"**; one more free piece comes back off the bill, a second is refused "(0 PIECE sent and 1 free, 0 and 1 already returned; …)". Both free pieces back: sending the free line is refused "Line 2 bills a quantity of 0 and supplies nothing free. Type a quantity, or leave the line off the bill."; the bill of the charged line alone prints no free line. Charged and free on one line (24 with 2 free, 1 free back): the bill reads and prints **"24 + 1 free"**; 2 free back off it refused "(24 sent and 1 free, …)". A part bill before the return: PRCQ-69 |
| PRCQ-62 | **Fixed** | S1, S2; (a) R1, S3 | (a) A draft supplier bill of 2 BOX approved after 7 PIECE went back: "…line 1 bills 2 BOX where 1.4167 BOX is left to bill (2 BOX received, 0 BOX billed, 0.5833 BOX returned before billing). Change the bill's quantity to what the supplier billed for the goods the firm kept."; typed as 18 PIECE at save: "line 1 bills 1.5 BOX where 1.4167 BOX is left to bill (2 BOX received, 0 BOX on other bills, 0.5833 BOX returned before billing)."; 17 PIECE saves and approves at 1,203.60. (b) "Line 1: 1 BOX of the 2 BOX delivered came back before being billed, so 1 BOX is left to bill." (c) "A credit note cannot credit more than the line was charged: 2400.00 charged, 50.00 already credited."; 2,350.00 exactly saves; on a free line "Invoice line 2 was charged nothing, so there is nothing on it to credit." (d) One note with lines of 6 and 6 against 10: "Line 1 of DN-… delivers 12 where SO-… has 10 left to deliver of the 10 ordered. Change this note's lines to what is left." (e) "Line 1 delivers 4 BOX where SO-… has 3 BOX left to deliver of the 4 BOX ordered: DN-… delivers the rest. Change the line to what is left."; with free pieces "Line 2 delivers 3 PIECE where SO-… has 2 PIECE left to deliver of the 2 PIECE ordered, free goods included." |
| The return after a credit note (D-SELL-88, PR #1294) | **Fixed** for one bill of one note; not for a note billed in parts (PRCQ-65) or a typed price (PRCQ-64) | S1, N1 | Each on a fresh bill of 2,832.00. Credit note 472.00, then both boxes: **2,360.00** (`gross_amount` 2,400.00, `bill_discount_amount` 400.00, tax 360.00). In two parts: 1,180.00 and 1,180.00. Through the delivery note: 2,360.00. A return of 1 BOX first, then a credit note of 1,200.01: 422 "…2400.00 charged, 0.00 already credited, 1200.00 already returned."; 1,200.00 is taken; the other box then comes back at 0.00. A credit note approved between a return's approval and its completion: 422 "Line 1: SI-… has been credited since this return was saved, and these goods are now worth 2000.00 before tax where the return credits 2400.00. A customer cannot be credited more than they were billed. Cancel this return and raise it again, …"; raised again: 2,360.00. 7 PIECE off the box line after the credit note: 688.29, the other 17: 1,671.71; together 2,360.00. **After each of the six, on both firms: credits equal the bill (2,832.00), 1100 moved 0.00, the customer's account moved 0.00, the statement's closing balance equals the account, GSTR-1 `cdnr` rows add to 2,832.00 and the journals credit 1100 2,832.00.** The same on both |

Left on purpose, and unchanged (one line each, not re-reported):

| Id | Firms | What was seen |
| --- | --- | --- |
| PRCQ-53 | S1, S2 | An order and a quotation of 2 naming no unit on a product sold by the BOX: 2 pieces, 236.00 |
| PRCQ-55 | S1, S2 | A draft bill of 7 PIECE reads 0.5833; sent back as read: 422 "PIECE is counted in whole numbers, so 0.5833 PIECE cannot be entered."; sent as 7 PIECE: 826.00 |
| PRCQ-56 | S1, S2, R1, S3, P1, P2 | Valuation against the stock account: **0.01 on S1 and S2, 0.04 on R1 and S3, 0.02 on P1 and P2**; 0.00 on the other sixteen |
| Batch over-pin | P1, P2 | 4 BOX (48 pieces) pinned to a batch holding 24: approved, 48 reserved; cancelled again |
| 419.98 | S1, S2 | 7 PIECE of X4K leave 0.5833 of a box: Dr 5200 419.98 / Cr 1200 419.98 |

## B. The nine suspicions

| No | Suspicion | Verdict |
| --- | --- | --- |
| 1 | A return off the delivery note after the bill exists | **Defect, PRCQ-66 (High).** The customer is credited (826.00) and the journal is right; commission, the commission report's `invoiced_amount`, sales targets and the bill's own outstanding do not move. C1, C2 |
| 2 | A return priced above its bill, no credit note | **Defect, PRCQ-64 (High).** 3,540.00, 3,422.00 and 3,332.00 credited against 2,832.00. S1, N1 |
| 3 | A note billed in two parts, a credit note on the second bill, a return off the note | **Defect, PRCQ-65 (High).** Not capped: 3,304.00 against 2,832.00. With the credit note on the first bill the return is 472.00 short. S1, N1 |
| 4 | The purchase twin | **Defect, PRCQ-67 (High).** 2,171.20 claimed against a bill of 1,699.20, off the bill or off the receipt. R1, S3 |
| 5 | A draft bill saved before free goods came back, then approved | **Yes, it states them: PRCQ-69 (Low).** Approved at "0 + 2 free" where 1 is held. Documented ("keeps the figure it was saved with until it is saved again"). A charged box coming back is refused at approval; the free figure is not asked again. The return cap still holds. S1, S2 |
| 6 | "0 free" typed on a quotation line | **Works on the quotation, lost at conversion: PRCQ-68 (Low).** The quotation now shows nothing free, on create and on a later save; its order gives the 2 free and claims them. S1, S2 |
| 7 | One note, two lines of one order line over it | **Works.** Saved (1,416.00); refused at approval: "Line 1 of DN-… delivers 12 where SO-… has 10 left to deliver of the 10 ordered. Change this note's lines to what is left." 6 and 4 approve. S1, S2 |
| 8 | Payables 2,194.80 under the suppliers' report on R1 and R2 | **Works: it is three unapplied supplier credits.** See below |
| 9 | Anything new around loyalty, price lists, slabs or claims | **Nothing new in what was driven**: see below |

**B8, read properly (R2, untouched this round; R1 and R3 the same).**
`GET /payments/supplier-credits` needs `vendor_id`; round 5's script sent
none, which is why the list came back empty. For supplier V1 on R2: three
credits, **PR-…-000001 849.60, PR-…-000002 849.60, PR-…-000005 495.60**,
each `applied_amount` 0, `available_amount` in full: 2,194.80. The
outstanding report says 20,390.40 over 14 bills; the payables report says
`amounts` 20,390.40, **`credits` -2,194.80, `total` 18,195.60**; the
supplier's statement closes at 18,195.60; Trade Payables is 18,195.60. The
three are `bx.py`'s purchase returns of goods already billed and paid for by
nobody: the firm is owed them and has not set them against a bill. The
outstanding report lists bills and does not net credits; the payables
report, the statement and the books do. Nothing is wrong. On all thirteen
firms with a supplier, bills outstanding less credits available equals the
payables report's total and account 2100.

**B9, what was driven.** (1) A bill returned in full off the note, then a
credit note of 400.00 on the bill line: refused, "2400.00 charged, 0.00
already credited, 2400.00 already returned."; a box off the bill as well:
refused, "2 BOX sent, 2 BOX already returned against it or the bill for it"
(S1, N1). (2) A principal's free goods claimed (120.00), then one free piece
returned **off the note**: the raised claim stands, the preview is empty,
and after a second bill it holds +60.00 and -60.00 "Came back after claim
CLM-…" (S1, N1). (3) The clawback payout approved (above). (4) Loyalty under
the return after a credit note: points come off with each credit (9.44 with
the credit note, 47.20 with the return of 2,360.00), and Loyalty Payable
equals the report on every firm. Commission slabs and price list breaks were
driven only through the regression (cases 001, 006, 007, 008; `a24.py`).

## C. Regression

**Buying by the box (R3, fresh; `bx.py` unchanged, against round 5's log).**
One line differs and it is PRCQ-62's wording: a bill of 25 PIECE is refused
as "line 1 bills 2.0833 BOX where 2 BOX is left to bill (2 BOX received, 0
BOX on other bills, 0 BOX returned before billing)". Everything else is line
for line round 5's.

**The rate difference claim (N2; `cr.py` unchanged).** The same on both,
nothing differing: 100 at 60.00 to 55.00 is 500.00, Dr 1420 500.00 / Cr 5400
500.00. By batch (`pm.py`): not driven; no fresh pharmacy firm.

**Promotion budgets and principal claims with free goods (N2; `a27.py`,
`a28.py` unchanged).** The same figures. The differing lines are two
receipts at the same instant landing in the other order (one 201 and one
422 either way) and three offers `c911.py` had already made when `a28.py`
listed them.

**Round 3's own scripts (N2).** `a24.py` and `a35.py`: nothing differing.
`a22.py`: not valid this round (above).

| Case | Firm | Verdict | Difference from round 5 |
| --- | --- | --- | --- |
| 001, 002, 004 | N2 | **Pass** | None; one audit list read one row later |
| 003 | O3 | **Pass** | None |
| 005 | L3 | **Pass**, text wrong in one figure as before | None |
| 006 | C3 | **Case text wrong, product right**, as before | None |
| 007 | C3 | **Not runnable as written**, as before; the flow passes | None |
| 008 | C3 | **Pass** | None |
| 009, 011 | N2 | **Pass** | QQ is 84.00 again, so the mixed-product lines read 420.00 as in round 4 |
| 010 | L3 | **Pass** | None |
| 012 | D3 | **Pass** | None; the print is 4 bytes shorter |

The per-unit commission (C3, `cm.py`): 60.00 three ways, as before.

**Generic checks.** `gg5.py`, 69 requests on N2 (other firm S1, buying R3):
the same bad input, cross-firm and read-only checks as round 5. Round 4's
`n4g.py` (N2, S2, R3; nothing differing) and round 2's `g.py` (N2, S2, L3).
`dup6.py`, 17 requests on each of S1 and S2. **All refused cleanly and
nothing at 500.** Three answers differ from round 5 and each is expected:
the `PUT` with two lines numbered 1 is now 422 (PRCQ-60); a note of 3 BOX
is refused in boxes; and GSTR-1 over four months, and backwards, answer
"This firm has no GST number, so it has no return to file." on N2, which
has none (the three-month limit itself was not asked again).

**The books at the end, all twenty-two firms.** Every trial balance
balances; no journal is unbalanced (between 1 and 615 journals a firm).

| Firm | Trial balance | 1100 = customers less advances | 2100 = bills outstanding less supplier credits | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 7,778,191.98 | 198,126.56 | 28,567.80 | 4,055.12 | 0 | 240.00 | 7,377,400.04 against **7,377,400.05** |
| S2 | 6,480,097.40 | 147,799.19 | 28,567.80 | 2,965.41 | 0 | 184.54 | 6,199,980.06 against **6,199,980.07** |
| S3 | 482,422.04 | 7,761.85 | 46,964.00 | 155.23 | 0 | 63.54 | 457,619.23 against **457,619.19** |
| N1 | 1,281,150.54 | 66,228.33 | 29,618.00 | 1,407.71 | 0 | 229.40 | 1,127,242.27 |
| N2 | 791,785.44 | 51,807.31 | 29,618.00 | 1,036.13 | 0 | 109.40 | 702,682.27 |
| R1 | 43,528.56 | 1,270.00 | 35,541.60 | 0 | 0 | 0 | 35,436.96 against **35,436.92** |
| R2, R3 | 20,023.20 | 1,270.00 | 18,195.60 | 0 | 0 | 0 | 14,577.60 |
| P1, P2 | 37,759.20 | 21,599.20 | 0 | 0 | 0 | 240.00 | 4,586.97 against **4,586.99** |
| L1 | 184,506.27 | 20,235.02 | 28,320.00 | 622.44 | 0 | 0 | 137,820.00 |
| L2, L3 | 54,260.67 | 16,333.02 | 28,320.00 | 588.84 | 0 | 0 | 19,860.00 |
| C1 | 503,965.50 | 27,749.67 | 0 | 0 | 102.50 | 0 | 409,980.00 |
| C2 | 432,527.00 | 24,563.67 | 0 | 0 | 0.00 | 0 | 354,480.00 |
| C3 | 128,876.00 | 8,496.00 | 0 | 0 | 0.00 | 0 | 92,880.00 |
| D1, D2, D3 | 7,881.10 | 1,231.57 | 354.00 | 24.63 | 0 | 227.10 | 4,980.00 |
| O1, O2, O3 | 6,000.00 | 0 | 0 | 0 | 0 | 0 | 6,000.00 |

Receivables, payables, Loyalty Payable, commission and claims agree with
their sub-ledgers on every firm. What does not come out clean is PRCQ-56
(above) and what the new findings left, which the books carry faithfully:
the over-credits of PRCQ-64 and 65 are in the customer's account and in
1100 alike, and the over-claims of PRCQ-67 are supplier credits the payables
report nets. Purchase Price Variance: -456.96 on R1 and -956.96 on S3 (round
5's figures less the 900.00 of debit notes this round raised on each); N1
and N2 -500.00 and P1, P2 -240.00 are rate difference claims; R2 and R3
-57.60 as in round 5.

## Findings

Ids continue from round 5. High = wrong money, tax or stock, or a control
that can be bypassed; Medium = wrong behaviour with a workaround; Low =
wording, paisa, cosmetics. Causes are from reading the code named, not from
a debugger.

| Id | Severity | Module | What | Firms | Where from |
| --- | --- | --- | --- | --- | --- |
| PRCQ-63 | **High** | Pricing (offers) | Two lines of one product under an offer, sent back in the other order, keep the offer's free goods as typed: no offer named, no claim, outside the budget | S1, S2 | A, PRCQ-58 |
| PRCQ-64 | **High** | Selling | A sales return with a typed price, line charge or header charge above the bill's credits more than was billed | S1, N1 | B2 |
| PRCQ-65 | **High** | Selling | A note billed in parts: a return off the note is priced on the earliest bill alone, so a credit note on a later bill is not netted (472.00 over) and one on the first is netted twice (472.00 short) | S1, N1 | B3 |
| PRCQ-66 | **High** | Commission (pricing), with selling | A return raised off the delivery note after the bill exists takes nothing off commission, targets or the bill's outstanding | C1, C2 | B1 |
| PRCQ-67 | **High** | Buying | A supplier bill, a debit note for value against it, then a full purchase return: more is claimed from the supplier than was billed | R1, S3 | B4 |
| PRCQ-68 | Low | Pricing (offers) | "0 free" typed on a quotation line refuses the offer on the quotation and is lost when it becomes an order | S1, S2 | B6 |
| PRCQ-69 | Low | Selling | A bill can still state free goods the customer does not hold: each part bill of a note restates the whole free line, and a draft saved before the return is approved as saved | S1, S2 | A, PRCQ-61; B5 |
| PRCQ-70 | Low | Several | Wording: "Value error, " in front of the line-number refusal; a debit note's cap counted to four places; "Line 1 … delivers 12" for two lines of 6 | S1, S2, R1, S3 | several |

### PRCQ-63: two lines of one product sent back in the other order (High, pricing)

S1 15:10:03 IST, S2 15:10:13 (`a58.py` part w, second run); first seen with
no budget on S1 at 15:06:40 and S2 at 15:09 (`a58.py` part v, case 2b). The
same on both.

Offer "buy 10 get 1" on product Z6X, at most 5 free units in all.

1. `POST /sales-orders`, customer PC: line 1, 24 of Z6X; line 2, 36 of Z6X.
   Read back: line 1 `free_quantity` 2.0000, line 2 3.0000, both with
   `free_promotion_id`. A second draft the same (the control).
2. `PUT` the first draft with exactly what `GET` returned for each line,
   **the two in the other order**: line 1 is now 36 with `free_quantity`
   3.0000, line 2 is 24 with 2.0000. **200.** Read back: 36 with 3 free and
   24 with 2 free, **`free_promotion_id` null on both**, 6,525.40.
3. Approve: 200. 65 reserved. `GET /promotions/reports/redemptions`: **no
   row for the order**. The offer reads `free_quantity_claimed` 0,
   `remaining_free_quantity` 5.0000.
4. The control, `PUT` as read in place and approved: both lines keep the
   offer, one claim of 5; the offer reads **5.0000 claimed, 0.0000
   remaining**.
5. The first order ships: 65 leave (3,000 to 2,935).

**10 free units were given against a budget of 5, and the offer counts 5.**

**Expected:** `docs/PRICING_AND_PROMOTIONS.md`: "an editor may drop the
engine's lines or echo the whole read: either way the order ends with one
free line naming its offer, claimed once and counted against the budget
once", and "A line is recognised by what the stored order says about it,
not by where it stands". **Actual:** true for a line that moved to a number
no stored line of its product holds. Two lines of one product that change
places are each read as the *other* having stayed; the figures differ (3
where the stored line says 2), so both are kept as typed. Sent with the
same figure on both lines (24 and 24) the echo would match and nothing
would show. **Reach:** as PRCQ-58: the desktop's order editor does not send
an offer's free figures back; an API client or an import that echoes what
it read and reorders lines does. Workaround: send no `free_quantity` for a
line the read shows with `free_promotion_id`.

**Suspected:** `app/sales_order/services/offer_echoes.py:112` to `:123`
(the first pass of `echoes_of_what_an_offer_gave`): a sent line at a stored
line's number with the same product and kind is marked as having stayed
*before* its figures are compared, so it is never offered to the second
pass (`:124`), which is the one that would find the stored line carrying
its figure. A line could count as "stayed" only if it is also an echo, or
the first pass could prefer the stored line of that product whose figures
match.

### PRCQ-64: a return priced above its bill (High, selling)

S1 15:19:05 to 15:19:16 IST, N1 15:19:28 (`s6.py` part x). The same on both.

Each on a fresh bill of 2 BOX at 1,200.00: 2,832.00, with no credit note.
`POST /sales-returns` off the bill line, approved and completed:

| The return line or header carries | The return | Journal | Customer credited against 2,832.00 billed |
| --- | --- | --- | --- |
| `unit_price` 1500 (2 BOX) | 3,540.00 | Dr 4100 3,000.00, Dr 2220 270.00, Dr 2230 270.00 / Cr 1100 3,540.00 | **708.00 over** |
| `charges_amount` 500 on the line | 3,422.00 | Dr 4100 2,900.00, tax 522.00 / Cr 1100 3,422.00 | **590.00 over** |
| `additional_charges` 500 on the return | 3,332.00 | Dr 4100 2,900.00, tax 432.00 / Cr 1100 3,332.00 | **500.00 over** |
| `unit_price` 1500 on 1 of the 2 BOX | 1,770.00 | Dr 4100 1,500.00, tax 270.00 / Cr 1100 1,770.00 | 354.00 over for the one box |

Receivable, the customer's account, the statement and the journal agree
with each other on the wrong figure. GSTR-1 `cdnr` shows 3,000.00 + 540.00
and 2,900.00 + 522.00 for the first two: **more output tax reversed than
the bill charged (432.00)**. For `additional_charges` GSTR-1 shows 2,400.00
+ 432.00 while the books credit 3,332.00: the 500.00 is in Sales Returns
and in no return. Loyalty is taken back only up to what the bill earned
(56.64).

**Expected:** `docs/SALES_CHAIN_RULES.md`: "A customer is never credited
more than they were billed". **Actual:** the cap added for D-SELL-88 is
applied only where a credit note already names the bill line; a return on
a bill with no credit note is "priced as before", and before means
whatever the request types. A typed lower price is a legitimate
restocking deduction; a higher one, or a charge, has no bill behind it.
Workaround: none short of review before approval.

**Suspected:** `app/sales_return/services/sales_return_service.py:1657`
(`if credits.credited_taxable > ZERO and taxable > ZERO:`): the cap at
`still_worth` is skipped when nothing has been credited yet. The typed
price is taken at `:1602` to `:1615`, the line charge at `:1631`, and the
header charge is added to the total at `:1409` with no line behind it.

### PRCQ-65: a note billed in parts (High, selling)

S1 15:19:16 IST, N1 15:19:40 (`s6.py` part y). The same on both.

One order of 2 BOX at 1,200.00, one delivery note, two bills of 1 BOX each
(1,416.00 and 1,416.00: 2,832.00).

| Credit note of 400.00 (472.00) on | Then | The return | Credited in all against 2,832.00 |
| --- | --- | --- | --- |
| the **second** bill | both boxes returned off the note | **2,832.00** (`bill_discount_amount` 0) | **3,304.00: 472.00 over** |
| the **first** bill | both boxes returned off the note | **1,888.00** (`bill_discount_amount` 800.00) | **2,360.00: 472.00 short**; the customer has returned everything and owes 472.00 |
| the second bill | the box returned off that bill itself | 944.00 (`bill_discount_amount` 400.00) | right |

Journals, the statement, GSTR-1 and 1100 agree with each other on each
figure. Loyalty follows the same line: off the note the return takes back
28.32 points (the first bill's) where 47.20 are left.

**Expected:** the same sentence as PRCQ-64. `docs/SALES_CHAIN_RULES.md`
says a return off the note is netted "against the bill line that charged
those goods (`charging_bill_line`, the earliest if the note was billed in
parts …)". **Actual:** with two bills of one note line, every unit coming
back off the note is priced as if the earliest bill had charged all of
them: its credit note is spread over both boxes (800.00 off where 400.00
was credited), and a later bill's credit note is never read. Workaround:
raise the return off each bill.

**Suspected:** `app/sales_return/billing.py:376` to `:393`
(`charging_bill_line`, `.limit(1)` on the earliest bill), and its use at
`sales_return_service.py:1648`: the units coming back want to be spread
over the bill lines that charged the note line, each with its own credits.

### PRCQ-66: a return off the delivery note after the bill (High, commission and selling)

C1 15:20:37 IST, C2 15:21:05 (`b1.py`). The same on both.

A salesman under 5% of what is invoiced on product VD6, and 2.50 a unit on
VA6. For each product, twice: 24 pieces ordered, delivered and billed
(2,832.00); then 7 pieces returned (826.00, completed), once off the bill
and once off the delivery note the bill was raised from.

| | Off the bill | Off the delivery note |
| --- | --- | --- |
| Customer's account, 1100, the journal (Dr 4100 700.00, tax 126.00 / Cr 1100 826.00) | -826.00 | -826.00 |
| Commission, 5% rule | **-35.00** | **0.00** |
| Commission, 2.50 a unit | **-17.50** | **0.00** |
| The commission report's `invoiced_amount` | -826.00 | 0.00 |
| `GET /sales-targets/achievement`, `achieved_amount`, over the sale and the return | +2,006.00 | **+2,832.00** |
| `GET /receipts/outstanding`, the bill's row | `allocated_amount` 826.00, `outstanding_amount` 2,006.00 | **`allocated_amount` 0, `outstanding_amount` 2,832.00** |

**Expected:** `docs/COMMISSION_FRAMEWORK.md`: commission "is earned on net
sales"; D-PRC-59: "the quantity is net of what came back". **Actual:** what
came back is read from returns raised from the bill's own lines. A return
raised off the note, which the product accepts after the bill exists and
credits correctly (and, since D-SELL-88, prices on the bill that charged
the goods), is seen by none of the readers of net sales: the salesman is
paid on the returned goods, the target counts them, and the bill reads
wholly outstanding beside a credit on the customer's account. This is
PRCQ-59's failure by another route, for a percentage rule as well.
Workaround: raise returns off the bill once one exists.

**Suspected:** `app/settlements/services/settlement_service.py:203`
(`SalesReturnLine.source_document_type == "SALES_INVOICE"` in
`_returns_off_bills`), read by `credited_against` and
`returned_units_against`, and through them by
`app/settlements/services/net_sales.py:110` and `:173` and
`app/commission/services/commission_service.py:1398`. The returns module
already knows the bill line a note line was charged on
(`charging_bill_line`).

### PRCQ-67: the purchase twin (High, buying)

R1 15:22:11 IST, S3 15:22:35 (`p6.py` part b). The same on both.

A fresh supplier each time. 2 BOX at 720.00 received and billed: 1,699.20
(Trade Payables +1,699.20). `POST /debit-notes` against the bill line,
`reason` PRICE_DIFFERENCE, `taxable_amount` 400.00, approved: 472.00 (Dr
2100 472.00 / Cr 5400 400.00, Cr 1320 36.00, Cr 1330 36.00). Then both
boxes sent back, approved and completed:

| The return raised off | The return | Trade Payables for this supplier at the end | A further debit note of 100.00 |
| --- | --- | --- | --- |
| the bill | **1,699.20** (Dr 2100 1,699.20 / Cr 1200 1,440.00, Cr 1320 129.60, Cr 1330 129.60) | **472.00 in debit**; a supplier credit of 472.00 "available" | refused: "…1440.0000 billed, 400.0000 already claimed, 1440.0000 already returned." |
| the receipt | **1,699.20**, the same journal | 472.00 in debit, then **590.00** | **saved and approved** |

**2,171.20 is claimed from the supplier for a bill of 1,699.20**, and
input tax of 331.20 is reversed where 259.20 was claimed. The supplier's
statement closes at -472.00 and -590.00.

**Expected:** what D-SELL-88 gives the sales side: the goods go back at
what the bill is still worth, 1,227.20. **Actual:** a purchase return does
not read the debit notes against its bill line, and a debit note counts
only the returns raised off the bill line, not those off the receipt.
Workaround: none short of review.

**Suspected:** `app/purchase_return/services/purchase_return_service.py:2250`
to `:2257` (the line is priced from the source line with no netting of
debit notes); `app/debit_note/services/debit_note_service.py:753`
(`_returned_by_line` over the bill line's own returns).

### The Low findings

- **PRCQ-68 (pricing).** S1 15:07:15 IST, S2 15:09:33 (`a58.py` part q).
  Offer "buy 10 get 1" on Z5E. A quotation of 20 with `free_quantity` "0":
  the quotation reads 20, nothing free, no offer named (and the same when a
  saved quotation's line is sent back with "0.0000"). Sent, accepted and
  converted: **the order reads 20 with 2 free, offer named**, and claims
  them at approval. A sales order typed the same way keeps its 0. The
  customer was quoted nothing free and is given 2. Workaround: type the 0
  again on the draft order. Suspected:
  `app/quotation/services/quotation_service.py:821`
  (`else line.free_quantity or None`): a stored 0 is handed to the order as
  silence; the comment above it says so on purpose (D-SELL-41), from when a
  quotation could not tell a typed 0 from none.
- **PRCQ-69 (selling).** S1 15:16:40 to 15:16:53 IST, S2 15:17:35 to 15:17:47
  (`s6.py` part e). A note of 2 BOX + 2 PIECE free. (a) Billed in two parts,
  each sending the free line with a quantity of 0, no return at all: **both
  bills read "0 + 2 free"**, 4 stated for 2 given (S2 only; the control was
  added after S1's run); with one free piece returned between the two, the
  first reads 2 and the second reads and prints 1 (S1 and S2). (b) A
  draft bill of the whole note saved, one free piece returned off the note,
  the draft approved: 200, "0 + 2 free" where 1 is held; the same draft
  with a charged box returned is refused at approval ("… Change the bill to
  what the customer kept."). No value moves and the return cap holds by
  the note in every case ("2 PIECE sent free, 2 PIECE already returned
  against it or the bill for it"). (b) is documented as a limit; (a) is
  not. Suspected: `app/sales_invoice/services/sales_invoice_service.py:5571`
  (the free figure inherited from the note line is netted by what came
  back, `free_returned_off_notes`, and not by what other live bills of the
  line already state; the approval re-check covers the charged quantity
  only).
- **PRCQ-70 (several).** (a) The line-number refusal reads "Value error,
  Lines 1 and 2 of the request are both numbered 1. …": the validator's
  prefix is in front of the sentence, on all eight documents (S1, S2). (b)
  A debit note's cap: "1440.0000 billed, 400.0000 already claimed,
  1440.0000 already returned", where the credit note's twin says money to
  the paisa (R1, S3). (c) One note with lines of 6 and 6: "Line 1 of DN-…
  delivers 12" (S1, S2); line 1 delivers 6 and the note 12.

## Case text to correct

Round 3's, 4's and 5's tables still stand; nothing in them was applied.
Changes, for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 5's held-back cases | Can be written as passing: an echoed order whose lines moved (deleted above, inserted above: offer named, claimed once, a spent budget gives nothing); a return under a per-unit commission rule (24 at 2.50: 60.00, 42.50 with 7 back, 0.00 with all back; free goods and a credit note take nothing off); the clawback (a paid period short by 17.50 comes off the next accrual) |
| New cases wanted | (1) two lines numbered 1 on each of the eight documents; (2) a return after a credit note (2,832.00, 472.00, 2,360.00; refused at completion when the credit note comes in between); (3) a bill after free goods came back (0 + 1 free; 24 + 1 free); (4) a quotation under an offer converted (names the offer, claims, nothing free once the budget is spent) |
| Hold back until fixed | Two lines of one product swapped (PRCQ-63); a return priced above its bill (PRCQ-64); a note billed in parts then returned (PRCQ-65); a return off the note after the bill, under commission (PRCQ-66); a debit note then a purchase return (PRCQ-67) |
| 009 | Unchanged from round 5's note: state QQ's price (84.00) in the case |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **A figure typed on the engine's own free line is kept if the line moved
  and discarded if it stayed** (S1, S2): 0 + 5 sent on the offer's 0 + 2
  line after a line above was deleted stands as 5, typed, no claim, and the
  offer's own 2 are not added; round 5 saw the same 5 sent in place come
  back as 2.
- **A return that credits nothing still appears in GSTR-1** (S1, N1): after
  a credit note for all a line was still worth, the last box comes back at
  0.00 and `cdnr` carries a row of 0.00 and 0.00 for it.
- **Loose pieces off a box line after a credit note part by paise from the
  same pieces off a piece line**: 7 PIECE of 24 worth 2,000.00 is 688.29
  off a box line (S1, N1) and 688.33 off a piece line (C1, C2). The line's
  returns still add to 2,360.00 exactly.
- **A return refused at completion stays APPROVED** until somebody cancels
  it (S1, N1); the message says to.
- **Accruing a period that holds today is refused**, so a shortfall on a
  paid period waits for the next period to end; and it is recovered only
  from a period that earned something (C1).
- **The suppliers' outstanding report does not net supplier credits** (R1,
  R2, R3): it is 2,194.80 above Trade Payables, and the payables report
  beside it is not (B8).
- **`GET /payments/supplier-credits` with no `vendor_id`** answers a
  validation refusal that a script reading only the list takes for "no
  credits".
- **The background loops log a warning for a firm between its creation and
  its provisioning** ("Firm storage for … has not been provisioned yet"),
  twice during one build.
- Round 5's gaps were not driven again except where A or B covers them. Two
  are closed: a quotation with an offer's free goods on the line (it names
  the offer and claims), and a full return after a credit note.

## Left on the firms

- **C1: a commission payout for September, APPROVED and not paid, 102.50**
  (earned 120.00, clawback 17.50); a bill of 2,832.00 dated 30 September;
  an August accrual that made nothing; a new customer B1C; per-unit rules
  on VA6, VB6, VC6, VE6 and 5% on VD6, all ACTIVE (the same five on C2);
  eight bills and eight returns from B1 on each of C1 and C2; offer QE6C
  retired.
- **S1 and N1: customer PC credited more than billed** by 708.00, 590.00,
  500.00 and 354.00 (PRCQ-64) and 472.00 (PRCQ-65), and owing 472.00 for
  goods returned in full (PRCQ-65's control); six fresh bills each with a
  credit note of 472.00 and their returns; one return left APPROVED and
  cancelled; a claim RAISED on principal PR8 (120.00); on N1 also products
  Z6R and Z6J, offer QJ6 retired and principal PR8.
- **S1 and S2**: one order each shipped with 5 free units no offer counts
  (PRCQ-63), and one each from the first swap probe shipped with nothing
  free; four orders each from `b5h.py`'s twin shipped and billed, two from
  `b5.py`'s twin shipped and not billed; the bills and returns of the
  PRCQ-61 probes, among them one bill each stating 2 free where 1 is held
  and two part bills each stating 2 free; orders approved and not shipped
  from the quotation probes (cancelled where the script could); products
  Z6A, Z6D, Z6H, Z6K, Z6M, Z6P, Z6Q, Z6V, Z6W, Z6X on both, Z6R and Z6J on
  S1;
  offers QD6, QK6, QV6, GV6, QW6, QX6, QQ6, QZ6, QH6, QM6, QJ6 retired;
  principals PR7 and PR8; one more supplier bill of 247.80; X4K at 98.8334
  boxes (S1) and 96.2501 (S2).
- **R1 and S3**: suppliers V6A and V6B with Trade Payables in debit by
  472.00 and 590.00 (PRCQ-67); three debit notes approved; product NP6;
  one receipt with 7 PIECE returned and 17 billed; purchase stages as
  found.
- **N2**: eleven approved delivery notes that cannot be dispatched for want
  of stock of QQ, and their orders (`a22.py`, my running order).
- **P1 and P2**: 12 more pieces sold from batch BP.
- **N2, R3, L3, C3, D3, O3**: what the regression scripts leave on a firm.

## Not verified

- **Nothing on screen.** The desktop was not opened.
- **Nothing was read from the database.** That the server runs `d19b3f66`
  was taken from the hand-over and from the fixes behaving as merged.
- **Everything ran once, in one window** (15:05 to 15:38 IST).
- **One firm where two would be better**: the clawback (C1); the regression
  (one firm each, as asked).
- **`a22.py`** (lines sold by the box, round 3's script): spoiled by my
  running order, not run again; no seventh firm.
- **The rate difference by batch** (`pm.py`): no fresh pharmacy firm.
- **PRCQ-63**: three or more lines of one product; a swap where one line
  also changes quantity; an import.
- **PRCQ-64**: a return off the delivery note with a typed price; a typed
  discount lower than the bill's; whether the desktop sends any of the
  three fields.
- **PRCQ-65**: a note billed in three parts; parts of different sizes; two
  notes on one bill.
- **PRCQ-66**: slabs; a commission on COLLECTED; a payout accrued over such
  a return; the customer ageing report.
- **PRCQ-67**: a debit note for quantity (SHORT_SUPPLY); a part return; the
  purchase side of GSTR-3B.
- **GSTR-1 over four months** was asked on a firm with no GST number and
  answered that, not the limit.
- **The general ledger read of account 2100** was refused for my
  parameters and not followed; B8 rests on the supplier's statement, the
  credits list and the payables report.
