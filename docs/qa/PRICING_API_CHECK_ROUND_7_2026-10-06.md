# Pricing, promotions, loyalty, commission, claims and the returns around them: checked through the API, round 7, 2026-10-06

The seventh pass over this module, driven the way rounds 1 to 6 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `a64e3512`, PR #1302,
migration head `20261006_0345`), books read back through the API, nothing
read from the database, no source file changed, nothing fixed, no test suite
run, no git write, no restart and no migration.

**Every round 6 finding is fixed by its original reproduction, on two firms
wherever round 6 used two.** PRCQ-63 to PRCQ-70 are closed.

**The round does not close the module, because it found new things: two High,
four Medium and two Low (PRCQ-71 to PRCQ-78), and the buying twin of PRCQ-64
is still open as expected.**

- **In pricing proper (offers, price lists, discounts, loyalty, commission,
  claims) the round found one thing, and it is Low**: a quotation's box line
  typed "0 free" still shows and prints the offer's free line, and its order
  gives nothing free (PRCQ-77). Nothing else new was found in pricing:
  commission under slabs, on collected money and through a clawback, loyalty,
  the import of orders under an offer, price-list tiers and discounts under
  the new return cap all read right.
- **Elsewhere the round found seven things.** The two High are one hole on
  both sides of the house: after a unit comes back off the delivery note (or
  the goods receipt) of a line billed in parts, a further return raised on
  the earliest bill's own line is priced as if that unit had never been
  credited there. With a credit note on the later bill the customer is
  credited 3,304.00 against bills of 2,832.00; with it on the first bill the
  customer is 472.00 short (PRCQ-71, selling). The supplier is claimed
  2,171.20 against bills of 1,699.20 the same way (PRCQ-72, buying).
- The four Medium: a return's header charge is not counted on its bill, which
  reads 100.00 outstanding for ever (PRCQ-73); money a return leaves on
  account cannot be set against a later bill, only refunded (PRCQ-74); eight
  of the nine JSON import routes answer 500 for a file their schema refuses
  (PRCQ-75); a draft bill of a note that has any return cannot be cancelled
  (PRCQ-76). The other Low is paise: a bill returned in loose pieces credits
  2,831.93 of 2,832.00 (PRCQ-78).

**The regression is unchanged**: lines sold by the box (run first, on a fresh
firm, valid this round), buying by the box, the rate difference claim,
promotion budgets, principal claims and the twelve cases give what they gave
in rounds 5 and 6; every differing line is a fix's own wording or my running
order.

## When, and on which firms

Everything was driven between **16:56 and 17:52 IST on 6 October 2026, which
is 11:26 to 12:22 UTC on the same day**. Six fixtures were built, one at a
time (N3 at 16:56; R4, L4, C4, D4 and O4 between 17:28 and 17:30); the
twenty-two firms of rounds 4 to 6 were used again wherever a clean firm was
not needed. The server was not restarted; `/health` answered 200 before each
of the 69 script runs and at the end.

**Forty-two requests answered 500, every one of them a probe of the import
routes (PRCQ-75).** Nothing else answered 500 or 503. The server's error log
for the window holds those 42 errors (`pydantic_core.ValidationError`
reaching the unhandled-exception handler) and no warning.

**Memory.** Free memory was read before each build and before each script.
The lowest before a build was 2,115,468 KB (O4); no build had to wait. **The
lowest reading of the round was 1,384,576 KB at 17:33:04, during the
regression chain** (before `c35.py` on L4, three minutes after the sixth
build). That is under the 1.5 GB floor; the floor was applied to builds only
and the chain was not paused. Two reads were dropped in transit (`g.py`,
both GETs, read again by the helper); no write was sent twice.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| S1 | `selling-firm` | `T100667G6-S` | | A: PRCQ-63, 64, 65, 68, 69, 70; B2, B6, B7, B9; PRCQ-71, 73, 75 to 78; unchanged items |
| S2 | `selling-firm` | `T10064CYP-S` | | A: PRCQ-63, 68, 69, 70; B2, B6, B7, B9; PRCQ-73, 75 to 78; unchanged items |
| N1 | `selling-firm` | `T100657VP-S` | | A: PRCQ-64, 65; PRCQ-71; B2 and PRCQ-73 with a GST number; PRCQ-67 and PRCQ-72 against GSTR-3B |
| C1 | `commission-firm` | `T1006MWGX-T` | | A: PRCQ-66; B4, B5, B8; PRCQ-74 |
| C2 | `commission-firm` | `T1006DWN6-T` | | A: PRCQ-66; B4, B5, B8; PRCQ-74 |
| R1 | `ready-firm` | `T10067V0N-R` | | A: PRCQ-67; B1, B3; PRCQ-72 |
| S3 | `selling-firm` | `T100659Z3-S` | | A: PRCQ-67; B1, B3; PRCQ-72 |
| P1, P2 | `pharma-firm` | `T1006THK2-P`, `T1006EJV8-P` | | the batch over-pin, unchanged |
| N3 | `selling-firm` | `T1006S484-S` | yes | C: lines sold by the box first; cases 001, 002, 004, 009, 011; budgets, claims, the rate difference; generic checks |
| R4 | `ready-firm` | `T100693ZU-R` | yes | C: buying by the box |
| L4 | `loyalty-points` | `T1006JQR2-S` | yes | C: cases 005, 010; round 3's and round 4's loyalty scripts |
| C4 | `commission-firm` | `T1006FUJ1-T` | yes | C: cases 006, 007, 008 |
| D4 | `selling-invoiced` | `T10069CWY-S` | yes | C: case 012 |
| O4 | `selling-ordered` | `T1006LMHV-S` | yes | C: case 003 |
| N2, R2, R3, L1 to L3, C3, D1 to D3, O1 to O3 | | | | books only |

Scripts and logs are in the scratchpad folder `pricing7`, beside `pricing6`.
Round 3's to round 6's scripts were copied and run unchanged for the
original reproductions and the regression (`b1.py`, `p6.py`, `dup6.py`,
`u6.py`, `s5a.py`, `m5.py`, `a22.py` and the rest). The new ones are `a63.py`
(PRCQ-63, 68), `s7.py` (PRCQ-64, 65, 69, 71), `b7c.py` (PRCQ-66, B4, B5, B8),
`p7.py` (PRCQ-67, 72, B1, B3), `px.py` (PRCQ-70, B2, B6, B7 and odds),
`imp.py` (PRCQ-75, 76), `b97.py` (B9), `adv.py`, `g1.py`, `j2r.py`,
`b87.py` and `setqq.py`. Logs were compared by round 4's `cmp4.py`. "The
same on both" means that comparison showed nothing but document numbers and
running balances.

What went wrong on my side, so the record is straight:

- **Two of my scripts looped on a list that is not paged.** `s7.py`'s first
  run read `GET /receipts/outstanding` page after page for seven minutes
  (17:02 to 17:09 on S1) and `b8.py` did the same on
  `GET /purchase-invoices/reports/outstanding` for ten minutes once a firm
  held ten suppliers. Both were stopped; both were reads only. The first
  left one bill on S1 (SI-26-27-000137, 2,832.00) and a refused return. The
  payables check was rewritten as `b87.py`, one read a firm.
- **`c911.py` stopped at its first line on N3**: `a22.py`, run first as
  asked, had already made product QQ at 100.00. The script was pointed at
  that product, as round 5 did, so case 009's mixed-product lines read
  460.00 as in round 5 (420.00 in rounds 4 and 6, with QQ at 84.00).
- **My "want" figures for a note billed in three were wrong.** Orders of 4
  and 6 boxes earn the fixture's own offers, so the bills are 7,622.80 and
  2,501.60, not 8,496.00 and 2,832.00. The check that matters there, credits
  equal bills, holds in every case.
- **`p7.py`'s over-claim flag reads the sign backwards.** Trade Payables
  moving below zero is the supplier being claimed too much; the figures in
  this report are read by sign, not by the flag.
- **Two `p7.py` scenarios did not reach their point at first** and were run
  again as parts `d` and `e`: an approved return off the bill blocks the
  debit note at save, so the refusal at completion needs the return raised
  off the receipt; and the unbilled scenario ordered nothing.
- No heredoc was sent to the shell; every script edit was made with the file
  tool.

## A. The findings of round 6

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| PRCQ-63 | **Fixed** | S1, S2 | Offer "buy 10 get 1" on a new product, at most 5 free units. The draft of 24 (2 free) and 36 (3 free) sent back in the other order: **both lines keep the offer, one claim of 5, 65 reserved; the offer reads 5.0000 claimed, 0.0000 remaining**; 6,525.40. The control, echoed in place after the budget is spent: nothing free, 60 reserved, no claim. The swapped order ships 65 (3,000 to 2,935). **Three lines** (24, 36, 48) rotated and reversed: 3, 4 and 2 named, one claim of 9, 117 reserved. **A swap with one quantity changed**: the 24 made 48 with its 2 echoed: 36 with 3 and 48 with 4, claim 7; the 36 made 60 with its 3 echoed: 60 with 6 and 24 with 2, claim 8. **One of two deleted**: the 36 sent alone with its 3: named, claim 3; the 24 alone with its 2: named, claim 2. **A typed figure equal to another line's offer figure**: 3 typed on the line of 24 with the line of 36 present: 24 with 3, **no offer named**, and 36 with 3 named, claim 3, 66 reserved (typed stands); with the line of 36 deleted: 24 with 2, named, claim 2 (the offer afresh, the documented reading). **BOX and PIECE**: [2 BOX; 36 PIECE; the engine's free line] with the first two swapped: 3 on the piece line, 0 + 2 PIECE free, one claim of 5, 65 reserved; [2 BOX; 3 BOX] swapped: free lines of 3 and 2, one claim of 5. Every order cancelled: the offer reads 0 claimed |
| PRCQ-68 | **Fixed**; one shape left on a box line (PRCQ-77) | S1, S2 | Offer "buy 10 get 1" on Z5E. A quotation of 20 with `free_quantity` "0": the read shows `free_quantity` 0.0000, **`free_goods_refused` true**, no offer named; converted: **the order reads 20, nothing free, no offer named; approved: 20 reserved, no claim**. The control, no figure typed: 2 free, named, 22 reserved, claim 2. A box line, 2 BOX with "0": the order has no free line, 24 reserved, no claim (the control: 0 + 2 PIECE free, 26 reserved, claim 2). A saved quotation line of a product with no offer sent back with "0.0000": `free_goods_refused` true; an offer made on the product afterwards; converted: nothing free (documented: an echoed 0 is a refusal). The refusal taken back by saving the line with no free figure: 2 free, named, `free_goods_refused` false |
| PRCQ-64 | **Fixed** | S1, N1 | Each on a fresh bill of 2 BOX at 1,200.00 (2,832.00). `unit_price` 1500: **422 at save**, "Line 1: the return credits 3000.00 before tax for goods that SI-… billed at 2400.00, and they are still worth 2400.00 on it. A customer cannot be credited more than they were billed. Lower the price or the charge to the bill's, or leave them out and the line is credited what the bill is still worth." `charges_amount` 500: the same, 2900.00 against 2400.00. `additional_charges` 500: "This return credits 500.00 of additional charges, and SI-… charged 0.00 of them, 0.00 already given back by other returns. … Lower the charges to 0.00 or less." 1,500.00 on one of the two boxes: 1500.00 against 1200.00. **1,200.01: refused** (2400.02 against 2400.00). **1,200.00 exactly: 2,832.00.** **1,000.00: 2,360.00**, the bill reads 472.00 outstanding. **7 PIECE of the box line: 826.00** (700.00 + 126.00), then the other 17: 2,006.00; 2,832.00 in all. **A bill with a header charge of 100.00** (2,932.00): 1 BOX and 60.00: 1,476.00; the other box and 60.00 again: "… charged 100.00 of them, 60.00 already given back by other returns. … Lower the charges to 40.00 or less."; with 40.00: 1,456.00; 2,932.00 in all. **Off an unbilled note at 1,500.00**: "Line 1: the return credits 1500.00 before tax for goods that DN-… sent at 1200.00, and no bill has charged them yet. Goods cannot come back at more than they were sold for. …"; with no price: completed, the customer's account does not move. After each: 1100, the customer's account, the statement, GSTR-1 `cdnr` and the journals agree, except that the header charge is in no GSTR-1 row (B2) and is not counted on the bill (PRCQ-73) |
| PRCQ-65 | **Fixed** for every return off the note; a later return on a bill's own line is PRCQ-71 | S1, N1 | One note of 2 BOX in two bills of 1,416.00. Credit note 472.00 on the **second**, both boxes off the note: **2,360.00** (`bill_discount_amount` 400.00). On the **first**: **2,360.00**. Credits equal bills (2,832.00) both ways; both bills leave the outstanding list. **A note of 6 BOX in three bills** of 1, 2 and 3 boxes (1,270.47, 2,540.93, 3,811.40: 7,622.80 under the fixture's offers), a credit note of 472.00 on each in turn, all six off the note: 7,150.80 each time, credits 7,622.80. A credit note of 118.00 on each of the three, 2 boxes then 4 off the note: 2,363.93 and 4,904.87, credits 7,622.80. **Part off the note, the rest off the bill**: credit note on the second, 1 BOX off the note (1,416.00), then 1 BOX off the second bill's own line: 944.00; and credit note on the first, 1 BOX off the second bill's line (1,416.00), then 1 BOX off the note: 944.00; 2,832.00 each. **A part-billed note**: 4 BOX delivered, 2 billed (2,501.60), credit note 472.00, all 4 off the note: 2,029.60 credited beside the note's 472.00, the 2 unbilled crediting nothing; a further bill refused: "Line 1: 2 BOX of the 4 BOX delivered came back before being billed, so 0 BOX is left to bill."; 3 off the note: 1,014.80 credited, the bill reads 1,014.80 outstanding. After each: 1100 and the customer's account move alike, the statement closes on the account, GSTR-1 `cdnr` rows and the journals' credits to 1100 equal what was credited, and each bill's outstanding follows |
| PRCQ-66 | **Fixed** | C1, C2 | `b1.py` again: 7 of 24 off the delivery note after the bill: **commission -35.00 at 5% and -17.50 at 2.50 a unit**, `invoiced_amount` -826.00, target +2,006.00 over the sale and the return, **the bill reads `allocated_amount` 826.00, `outstanding_amount` 2,006.00**: the same as off the bill. **A slab rule** (2% to 2,000.00, then 5%, marginal): a first sale of 2,400.00 earns 60.00; 7 off the note: -26.00 (1,700.00 at 2%); a second sale: +111.00; 7 off the bill: -35.00: the ladder, by either route. **A bill paid in full, then 7 off the note**: commission -35.00, `collected_amount` -826.00, the bill leaves the outstanding list, the customer reads `current_outstanding` 0.00 and `unapplied_advance_balance` 826.00, 1100 -826.00: the same as off the bill (what can be done with the 826.00: B4). **Ageing**: a bill dated the 5th with 6 returned off the note on the 6th reads 708.00 `as_of` the 6th (both firms) and 1,416.00 `as_of` the 5th (read on C2). **A note with no bill**: 7 off the note moves commission, the target and the customer by nothing; the 17 left billed: +85.00, +2,006.00 |
| PRCQ-67 | **Fixed** for every return off the bill or the receipt alone; the two routes together are PRCQ-72 | R1, S3; GSTR-3B on N1 | `p6.py` part b again: bill 1,699.20, debit note 472.00, both boxes back off the bill and off the receipt: **the return is 1,227.20** (Dr 2100 1,227.20, Dr 5400 400.00 / Cr 1200 1,440.00, Cr 1320 93.60, Cr 1330 93.60), **Trade Payables moves 0.00 in all**, and the further 100.00 is refused: "A debit note cannot claim more than is left of the bill line: 1440.00 billed, 400.00 already claimed, 1040.00 already returned." **A part return then the rest**: 1 BOX off the bill, 613.60; the other off the receipt, 613.60; a third refused. **A receipt billed in two bills** of 849.60, the debit note on the second, then on the first: both boxes off the receipt: 1,227.20 each way. **A return off the receipt approved, a debit note approved in between**: completion refused, "Line 1: The supplier's bill for GRN-… has had a debit note approved since this return was saved, and these goods are now worth 1040.00 before tax where the return claims 1440.00. No more can be claimed from a supplier than they billed. Cancel this return and raise it again, …"; cancelled and raised again: 1,227.20. (A return off the *bill*, even a draft, refuses the debit note at save instead.) **A draft debit note, the return completed, the note approved**: refused, "… 1440.00 billed, 0.00 already claimed, 1440.00 already returned." After each the supplier's statement closes at 0.00 and the payables report nets to 0.00. **GSTR-3B (N1)**: each scenario adds 129.60 + 129.60 to eligible ITC and the same to ITC reversed, the debit note's 72.00 and the returns' 187.20 together |
| PRCQ-69 | **Fixed**; the draft it now refuses cannot be cancelled (PRCQ-76) | S1, S2 | A gift line of its own (2 BOX and 0 + 2 PIECE free): the first part bill states **0 + 2 free whole**; the second, sending the free line again, is refused by name: "Line 2: the free goods of DN-… line 2 are already stated on another bill (2 PIECE free), so nothing is left for this line to state. Leave the line off the bill." (deliberate, confirmed); with the charged line alone it saves and prints no free line. **24 + 2 free billed 12 and 12: 1 free on each**; billed 8, 8, 8: 0, 1, 1. **A typed figure**: 2 typed on the first part bill stands; 1 typed on the second: "Free quantity exceeds what the source document supplied free: DN-… line 1 gave 2 free and other bills already state 2, so 0 is left to state."; nothing typed: 0. 3 typed where 2 were given: refused. **A draft saved before a free piece came back**: approval refused, "SI-… line 2: 1 PIECE of the 2 PIECE sent free came back before being billed, so 1 PIECE is left to state free where the bill states 2 PIECE. Change the bill to what the customer kept."; saved again as first sent: 0 + 1 free; approved; prints "Free with QH7, 0 + 1 free, PIECE" |
| PRCQ-70 | **Fixed** | S1, S2; R1, S3 | (a) "Lines 1 and 2 of the request are both numbered 1. Number each line once." with no prefix, on create and update of all eight documents, 16 of 16 on each firm, and "Lines 1 and 3 … both numbered 2". No "Value error" in the twelve other refusals read for it, six of them validators' own sentences, among them "A promotion cannot end before it starts.", "Free goods need a buy quantity and a free quantity.", "A target cannot end before it starts." and "Line 1 returns a quantity of 0 and nothing free. …". (b) The debit note's cap to the paisa, above. (c) "**Lines 1 and 2 of DN-… together deliver 12** where SO-… has 10 left to deliver of the 10 ordered. Change this note's lines to what is left."; three lines: "Lines 1, 2 and 3 of DN-… together deliver 13" |

Left on purpose, and unchanged (one line each, not re-reported):

| Id | Firms | What was seen |
| --- | --- | --- |
| PRCQ-53 | S1, S2 | An order and a quotation of 2 naming no unit on a product sold by the BOX: 2 pieces, 236.00 |
| PRCQ-55 | S1, S2 | A draft bill of 7 PIECE reads 0.5833; sent back as read: 422 "PIECE is counted in whole numbers, so 0.5833 PIECE cannot be entered."; sent as 7 PIECE: 826.00 |
| PRCQ-56 | S1, S2, R1, S3, P1, P2 | Valuation against the stock account: **0.01 on S1, 0.02 on S2, 0.04 on R1 and S3, 0.02 on P1 and P2**; 0.00 on the other twenty-two |
| Batch over-pin | P1, P2 | 3 BOX (36 pieces) pinned to a batch holding 12: approved, 36 reserved |
| 419.98 | S1, S2 | 7 PIECE of X4K leave 0.5833 of a box: Dr 5200 419.98 / Cr 1200 419.98 |

## B. The nine probes

| No | Probe | Verdict |
| --- | --- | --- |
| 1 | A purchase return typed above its supplier bill, no debit note | **Open, as expected (the known twin of PRCQ-64).** More is claimed than was billed by every route tried; figures below. R1, S3 |
| 2 | A sales return's header `additional_charges` | **Credited without tax and in no GSTR-1 row, which is how the bill charged and declared them.** Capped at what the bill charged. But the credit is not counted on the bill: **PRCQ-73 (Medium)**. S1, S2, N1 |
| 3 | What the supplier is owed after a return off the goods receipt of a billed line | **Works as documented.** The bill reads fully outstanding and a supplier credit stands beside it; the payables report, the statement and Trade Payables net it and nothing is counted twice. Two reports do not net it, and the bill can be paid in full while the credit stands (gaps). R1, S3 |
| 4 | A bill paid in full, then a return off the note | **The return is right and the credit can be refunded cleanly; it cannot be set against another bill: PRCQ-74 (Medium).** Ageing, the statement and the account agree with each other. C1, C2 |
| 5 | A backdated second bill of a note after a return off the note | **Works.** Totals per note, the receivable, each bill's outstanding, commission, the target, ageing and the statement stay right. C1, C2 |
| 6 | An import of orders under an offer | **The import is the create.** A line with no free figure is named and claimed; a typed figure stands as typed; the budget holds. But a file the schema refuses answers **500: PRCQ-75 (Medium)**. S1, S2 |
| 7 | Loyalty on a bill whose return off the note now counts against it | **Works: the points come back once.** S1, S2 |
| 8 | Commission on COLLECTED with a return off the note; a paid payout, then the next accrual | **Works**, the same by either route, and the clawback carries. C1, C2 |
| 9 | Anything else around price lists, discount limits, offers, claims | **One Low in pricing (PRCQ-77).** Line discounts, bill discounts and a price-list tier under the new return cap read right. Driven on the way: PRCQ-71, 72, 76, 78 |

**B1, the figures (R1 and S3, the same on both).** Each on a fresh supplier:
2 BOX at 720.00 received and billed, 1,699.20, no debit note; then a return,
approved and completed.

| The return carries | Raised off | The return | Trade Payables for the supplier at the end | Journal beyond the bill's own figures |
| --- | --- | --- | --- | --- |
| `unit_price` 900 (2 BOX) | the bill | **2,124.00** (1,800.00 + 324.00) | **424.80 in debit**; a supplier credit of 424.80 | Cr 5400 360.00; input tax reversed 324.00 where 259.20 was claimed |
| `unit_price` 900 (2 BOX) | the receipt | **2,124.00** | 424.80 in debit; the bill reads 1,699.20 outstanding beside a credit of 2,124.00 | the same |
| `charges_amount` 500 on the line | the bill | **2,289.20** (1,940.00 + 349.20) | **590.00 in debit** | Cr 5400 500.00, tax 90.00 over |
| `additional_charges` 500 on the return | the bill | **2,199.20** | **500.00 in debit** | Cr 5400 500.00, no tax |
| `unit_price` 720.01 | the bill | 1,699.2236 | 0.02 in debit | Cr 5400 0.02 |
| `unit_price` 900 on 1 of the 2 BOX | the bill | 1,062.00 | the bill reads 637.20 where 849.60 is owed: **212.40 over** | Cr 5400 180.00 |
| `unit_price` 600 (below the bill's) | the bill | 1,416.00 | 283.20 still owed (a deduction, as on the sales side) | |
| `unit_price` 900 on 1 BOX | an **unbilled** receipt | the document reads 1,062.00 | 0.00: Dr 2300 720.00 / Cr 1200 720.00, nothing claimed | |

Nothing refuses any of them at save, approval or completion. Expected, by
`docs/PURCHASE_FRAMEWORK.md`'s own heading: "No more is claimed from a
supplier than they billed". The cap exists only once a debit note does
(`app/purchase_return/billing.py:373`, `still_worth`, reached from
`BillWorths.worth`), and the header charge has no cap at all.

**B2, what was read (S1, S2, N1).** A bill of 2 BOX with
`additional_charges` 100.00: 2,932.00; Dr 1100 2,932.00 / Cr 4000 2,500.00,
Cr 2220 216.00, Cr 2230 216.00; it prints "Taxable value 2,400.00 … Other
charges 100.00"; GSTR-1 `b2b` (N1): `invoice_value` 2932.0, `taxable_value`
2400.0, tax 432.0. So the bill charges it untaxed, inside Sales, and
declares it only in the invoice value. The returns (60.00 and 40.00 with a
box each): Dr 4100 1,260.00, tax 216.00 / Cr 1100 1,476.00, and 1,240.00 /
1,456.00; `cdnr` rows of 1,200.00 and 216.00 each. The same treatment, and
the cap holds (A, PRCQ-64). What follows is PRCQ-73.

**B3, what was read (R1, S3).** Bill 1,699.20 unpaid, 1 of 2 BOX returned.

| | Returned off the receipt | Returned off the bill |
| --- | --- | --- |
| `GET /payments/outstanding`, the bill | `allocated` 0.00, `outstanding` **1,699.20** | `allocated` 849.60, `outstanding` 849.60 |
| `GET /payments/supplier-credits` | PR-… 849.60 available | none |
| Payables report | `credits` -849.60, `total` 849.60 | `total` 849.60 |
| Supplier's statement, Trade Payables | 849.60 | 849.60 |
| `reports/vendor-ageing`, `reports/outstanding` | **1,699.20** | 849.60 |
| A payment of 1,699.20 allocated to the bill | **201**: the statement closes at -849.60 | 422 "… has 849.60 outstanding, so 1699.20 cannot be allocated to it." |
| Then | the credit applied to the bill (200): the bill reads 849.60; paid; 0.00 | paid 849.60; 0.00 |

`docs/PURCHASE_FRAMEWORK.md` says so: "Not changed: what a bill still *owes*
in Record Payment. A return raised off the receipt does not come off its
bill there; it stands as a supplier credit to set against it". On all
twenty-eight firms bills outstanding less credits available equals the
payables report's total and account 2100.

**B5, what was read (C1, C2).** 24 delivered on the 5th. Bill 1 of 6 dated
the 6th (708.00, commission +30.00). 6 off the note: credits nothing (18 are
unbilled). Bill 2 of 12 **dated the 5th** (1,416.00, +60.00). 6 more off
the note: credited 708.00 against the backdated bill, the earliest
(commission -30.00). Over it all: 2,124.00 billed, 708.00 credited, the
customer owes 1,416.00, 1100 +1,416.00, commission +60.00, `invoiced_amount`
+1,416.00, target +1,416.00; the bills read 708.00 and 708.00 outstanding;
ageing 1,416.00 in two rows; the statement closes at 1,416.00. A third bill:
"Line 1: 6 of the 24 delivered came back before being billed, so 0 is left
to bill." Bill 1's own 6 then returned off bill 1: -30.00, the customer owes
708.00. 7 off bill 2's line: "Return quantity exceeds what left on DN-… (24
sent, 18 already returned against it or the bill for it)."

**B6, what was read (S1, S2).** Offer "buy 10 get 1", at most 4 free units.
`POST /sales-orders/import` (multipart, `format` json) with four orders: 24
with nothing typed: 2 free, **offer named, claim 2**; 24 with `free_quantity`
2 typed: 2 free, **no offer named, no claim** (and the same line through
`POST /sales-orders`: the same); 2 BOX: 0 + 2 PIECE free, named, claim 2 (the
offer reads 4 of 4); 24 with 0 typed: nothing free. Cancelled: 0 claimed.

**B7, what was read (S1, S2).** A fresh customer. A bill of 2,832.00: +56.64
points. 7 PIECE off the note: **-16.52, once**; the other 17 off the bill:
-40.12; 0 in all. One note in two bills: +56.64; a credit note of 472.00 on
the second: -9.44; both boxes off the note (2,360.00): -47.20; 0 in all;
Loyalty Payable moves 0.00. 100 points spent on a bill of 2,832.00, then both
boxes off the note: the return credits 2,832.00 where the bill owed
2,732.00, so 100.00 stands as credit on the account; the earn of 56.64 comes
back once and the 100 points spent are not given back (the customer has the
100.00 instead).

**B8, what was read (C1, C2).** A rule of 10% on what is collected. Paid in
full (2,832.00, commission +240.00), 7 back: `collected_amount` -826.00,
commission **-70.00**. Half paid (+120.00), 7 back: 0.00; the bill reads
590.00 outstanding. Unpaid, 7 back: 0.00; then the 2,006.00 left collected:
**+170.00**. Each the same off the note and off the bill. **The payout**: a
sale dated 15 July (5% on invoiced: 120.00); July accrued, approved by the
firm manager, paid by the accountant; 7 returned off the note today; July
re-reads 85.00; a sale dated 15 June; June accrued: **`earned_amount`
120.00, `clawback_amount` 35.00, `payable_amount` 85.00**; approved: Dr 5600
85.00 / Cr 2400 85.00; 2400 equals approved unpaid payouts on both firms.

**B9, what was driven (S1, S2).** A bill of 2 BOX less 10% on the line
(2,548.80): a return typed `discount_percent` 0, `discount_amount` 0 or
`discount_percent` 5 is refused by name, off the bill and off the note
("…credits 1200.00 before tax for goods that SI-… billed at 1080.00…");
nothing typed: 1,274.40 a box. A bill discount of 5% (2,690.40): a box typed
at the bill's own 1,200.00 comes back at 1,345.20 with its 60.00 share;
1,200.01 is refused; 0.00 over it all. 18 of DET to C01 under the price
list's 18+ tier (6.75%, 1,663.73): 4 off the note credit 369.72, 4/18 of the
bill, not the tier of 4; the other 14 off the bill; 0.00 over it all.

## C. Regression

**Lines sold by the box (N3, fresh, run first; `a22.py` unchanged, against
round 5's log).** Valid this round. One line differs and it is PRCQ-62's
wording: a third draft note of 5 is refused as "Line 1 delivers 5 where SO-…
has 4 left to deliver of the 10 ordered: DN-… delivers the rest. Change the
line to what is left."

**Buying by the box (R4, fresh; `bx.py` unchanged, against round 6's log).**
Nothing differing, 239 lines.

**The rate difference claim (N3; `cr.py` unchanged).** The same figures; the
seven differing lines are the validator prefix gone (PRCQ-70). By batch
(`pm.py`): not driven; no fresh pharmacy firm.

**Promotion budgets and principal claims with free goods (N3; `a27.py`,
`a28.py` unchanged).** The same figures. The differing lines are two
receipts at the same instant landing in the other order (one 201 and one
422 either way) and the offers `c911.py` makes, which ran after `a28.py`
this round.

**Round 3's own scripts (N3).** `a24.py` and `a35.py`: nothing differing.

| Case | Firm | Verdict | Difference from round 6 |
| --- | --- | --- | --- |
| 001, 002, 004 | N3 | **Pass** | None; two lists read in the other order |
| 003 | O4 | **Pass** | None |
| 005 | L4 | **Pass**, text wrong in one figure as before | None |
| 006 | C4 | **Case text wrong, product right**, as before | None |
| 007 | C4 | **Not runnable as written**, as before; the flow passes | None |
| 008 | C4 | **Pass** | None |
| 009, 011 | N3 | **Pass** | QQ is 100.00 here (made by `a22.py`), so the mixed-product lines read 460.00 as in round 5; against round 5's log only the prefix and later scripts' claims differ |
| 010 | L4 | **Pass** | None |
| 012 | D4 | **Pass** | None; the print is one byte longer |

The per-unit commission (C4, `cm.py`): 60.00 three ways, as before.

**Generic checks.** `gg5.py`, 69 requests on N3 (other firm S1, buying R4);
round 4's `n4g.py` (N3, S2, R4) and round 2's `g.py` (N3, S2, L4); `dup6.py`,
17 requests on each of S1 and S2; `px.py` part g, 13 refusals on S1. **All refused cleanly and nothing at 500.** The only answers that differ
from round 6 are the validator prefix gone. The import routes are the
exception and were not in those scripts before (PRCQ-75).

**The books at the end, all twenty-eight firms.** Every trial balance
balances; no journal is unbalanced (between 1 and 990 journals a firm).

| Firm | Trial balance | 1100 = customers less advances | 2100 = bills outstanding less supplier credits | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 9,347,804.22 | 238,229.23 | 28,815.60 | 4,867.01 | 0 | 240.00 | 8,793,440.06 against **8,793,440.07** |
| S2 | 7,973,100.03 | 169,878.55 | 28,815.60 | 3,311.01 | 0 | 184.54 | 7,626,100.08 against **7,626,100.10** |
| S3 | 484,788.58 | 7,761.85 | 45,472.78 | 155.23 | 0 | 63.54 | 460,499.23 against **460,499.19** |
| N1 | 1,717,284.67 | 81,403.13 | 29,146.00 | 1,819.04 | 0 | 229.40 | 1,478,602.27 |
| N2 | 791,785.44 | 51,807.31 | 29,618.00 | 1,036.13 | 0 | 109.40 | 702,682.27 |
| N3 | 840,751.20 | 58,636.48 | 29,618.00 | 1,172.72 | 0 | 109.40 | 736,402.27 |
| R1 | 46,516.56 | 1,270.00 | 34,050.38 | 0 | 0 | 0 | 38,316.96 against **38,316.92** |
| R2, R3, R4 | 20,023.20 | 1,270.00 | 18,195.60 | 0 | 0 | 0 | 14,577.60 |
| P1, P2 | 39,103.20 | 22,943.20 | 0 | 0 | 0 | 240.00 | 3,872.32 against **3,872.34** |
| L1 | 184,506.27 | 20,235.02 | 28,320.00 | 622.44 | 0 | 0 | 137,820.00 |
| L2, L3, L4 | 54,260.67 | 16,333.02 | 28,320.00 | 588.84 | 0 | 0 | 19,860.00 |
| C1 | 649,748.50 | 47,455.67 | 0 | 0 | 187.50 | 0 | 487,140.00 |
| C2 | 578,310.00 | 43,679.67 | 0 | 0 | 85.00 | 0 | 431,640.00 |
| C3, C4 | 128,876.00 | 8,496.00 | 0 | 0 | 0.00 | 0 | 92,880.00 |
| D1 to D4 | 7,881.10 | 1,231.57 | 354.00 | 24.63 | 0 | 227.10 | 4,980.00 |
| O1 to O4 | 6,000.00 | 0 | 0 | 0 | 0 | 0 | 6,000.00 |

Receivables, payables net of supplier credits, Loyalty Payable, commission
and claims agree with their sub-ledgers on every firm; the payables report's
total equals account 2100 on every firm. What does not come out clean is
PRCQ-56 (above) and what the findings left, which the books carry
faithfully: the over-credits and the shortfall of PRCQ-71 are in the
customer's account and in 1100 alike; the over-claims of PRCQ-72 and of B1
are supplier credits and suppliers in debit that the payables report nets
(eight suppliers in debit on each of R1 and S3, one on N1). Advances held:
2,478.00 on each of C1 and C2 (three returns on paid bills, PRCQ-74), 500.00
on R1 to R4 and 110.00 on L1 as found. Purchase Price Variance: -2,516.98 on
R1 and -3,016.98 on S3 (round 6's figures less what this round's debit
notes and over-priced returns put there); -900.00 on N1; N2 and N3 -500.00
are rate difference claims; R2 to R4 -57.60 as before.

## Findings

Ids continue from round 6. High = wrong money, tax or stock, or a control
that can be bypassed; Medium = wrong behaviour with a workaround; Low =
wording, paisa, cosmetics. Causes are from reading the code named, not from
a debugger.

| Id | Severity | Module | What | Firms | Where from |
| --- | --- | --- | --- | --- | --- |
| PRCQ-71 | **High** | Selling | A note billed in parts: after a unit comes back off the note, a return on the earliest bill's own line is priced as if nothing had been credited there. 472.00 over with a credit note on the later bill, 472.00 short with it on the first | S1, N1 | A, PRCQ-65 |
| PRCQ-72 | **High** | Buying | The same on a receipt billed in parts: 2,171.20 claimed from a supplier against bills of 1,699.20 | R1, S3, N1 | A, PRCQ-67 |
| PRCQ-73 | Medium | Selling (what a bill owes) | A return's header `additional_charges` credit the customer and are not counted on the bill: it reads 100.00 outstanding for ever and takes a receipt nobody owes | S1, S2, N1 | B2 |
| PRCQ-74 | Medium | Finance (settlements) | Credit a return leaves on a paid bill sits as an advance that no route sets against a later bill; it can only be refunded | C1, C2 | B4 |
| PRCQ-75 | Medium | Selling and buying | Eight of nine JSON import routes answer 500 "An unexpected error occurred." for a file their schema refuses, where the single save answers 422 by name | S1, S2 | B6 |
| PRCQ-76 | Medium | Selling | A draft bill of a note that has any return cannot be cancelled ("cannot be cancelled while it has sales return SR-…"), and goes on holding the note's units | S1, S2 | A, PRCQ-69 |
| PRCQ-77 | Low | Pricing (offers) | "0 free" typed on a quotation's box line: the quotation still shows and prints the offer's free line, and its order gives nothing free | S1, S2 | A, PRCQ-68 |
| PRCQ-78 | Low | Selling | A bill returned in loose pieces of a box line over several returns credits 2,831.93 of 2,832.00, on documents totalling 825.9805 and 825.9476; the bill reads 0.07 outstanding | S1, S2 | B9 |

### PRCQ-71: a unit off the note, then the earliest bill's own line (High, selling)

S1 17:11 and 17:12 IST (`s7.py` parts y and z), N1 17:14 and 17:15. The same
on both.

One order of 2 BOX at 1,200.00, one delivery note, two bills of 1 BOX each
(B1 and B2, 1,416.00 and 1,416.00: 2,832.00).

| Credit note of 400.00 (472.00) | Then | Then | Credited in all against 2,832.00 |
| --- | --- | --- | --- |
| on **B2**, first | 1 BOX returned off the **note**: 1,416.00 (priced on B1, the earliest) | 1 BOX returned off **B1's own line**: **1,416.00** (`bill_discount_amount` 0) | **3,304.00: 472.00 over** |
| on B2, **after** the return off the note | (1 BOX off the note first: 1,416.00) | 1 BOX off B1's own line: **1,416.00** | **3,304.00: 472.00 over** |
| on **B1**, first | 1 BOX off the note: 944.00 (B1 is worth 800.00) | 1 BOX off B1's own line: **944.00** (`bill_discount_amount` 400.00) | **2,360.00: 472.00 short**; everything is back, the customer owes 472.00 and B2 reads `allocated_amount` 944.00, `outstanding_amount` 472.00 |
| none (the control) | 1 BOX off the note: 1,416.00 | 1 BOX off B1's own line: 1,416.00 | 2,832.00, right |

Requests, the first row: `POST /credit-notes` (`sales_invoice_id` B2, one
line, `taxable_amount` 400.00) and approve; `POST /sales-returns` with
`source_document_type` DELIVERY_NOTE, the note line, 1; approve, complete;
`POST /sales-returns` with `source_document_type` SALES_INVOICE, B1's line,
1; approve, complete. Each answers 200. 1100, the customer's account, the
statement, GSTR-1 `cdnr` (400.00 + 72.00, 1,200.00 + 216.00, 1,200.00 +
216.00) and the journals agree with each other on the wrong figure. In the
over-credited rows both bills leave the outstanding list.

The orders that do work, from A: both units off the note; the unit off the
note and the other off **B2's** own line; a bill's own line first and the
note second.

**Expected:** `docs/SALES_CHAIN_RULES.md`: "A customer is never credited
more than they were billed", and of this very case, "a unit later named on
the first bill's own line moves a unit of an earlier return off the note
onto the next bill, which is the only place it can have come from".
**Actual:** the unit moves and its value does not fit where it lands. The
earlier return took 1,200.00 at B1's price; moved to B2, which is worth
800.00, "the last bill taking the rest" puts all 1,200.00 there, B2's worth
is clamped at nothing, and B1's line is priced afresh at its full 1,200.00.
The 400.00 B2 could not absorb is lost from every count. The mirror loses
400.00 the other way. Workaround: return the rest off the note, or off the
later bill.

**Suspected:** `app/sales_return/billing.py:656` to `:672` (`direct_part`
reserves the named units, `standing(reserve=…)`), with `_allocate` at
`:563` to `:572` (`spread_over`: the last bill takes the rest past what it
is worth) and `BillStanding.left` at `:433` (clamped at zero, so the excess
is not seen). What an earlier return off the note already credited at this
bill's price wants to come off what the named line is still worth, or the
excess that the next bill cannot absorb wants to stay on the first.

### PRCQ-72: the same on a receipt billed in parts (High, buying)

R1 17:20 IST, S3 17:22 (`p7.py` part a, scenario a2c), N1 17:38. The same on
all three.

A fresh supplier. 2 BOX at 720.00 received; two bills of 1 BOX (849.60 and
849.60: 1,699.20). `POST /debit-notes` on the **second** bill, 400.00:
472.00. 1 BOX returned off the **receipt**: 849.60. Then 1 BOX returned off
the **first bill's own line**: **849.60** (`bill_discount_amount` 0), where
377.60 is all that is left to claim. Both approve and complete at 200.

**Claimed in all 2,171.20 against 1,699.20.** Trade Payables for the
supplier ends 472.00 in debit (Cr 5400 400.00, Cr 1320 36.00, Cr 1330 36.00
beyond the bills' own figures); the statement closes at -472.00; the second
bill reads 377.60 outstanding beside a supplier credit of 849.60. **GSTR-3B
on N1: eligible ITC +259.20, ITC reversed +331.20, net ITC -72.00.**

**Expected:** `docs/PURCHASE_FRAMEWORK.md`: "No more is claimed from a
supplier than they billed", and "a return's value follows its units --
never more to one bill than it was still worth while another has room".
**Actual:** returns on the bill line are counted first, so the earlier
return off the receipt is placed on the second bill; its 720.00 does not
fit the 320.00 that bill is worth, and "what no bill line has room for
stays with the last" leaves it all there. The first bill then reads
untouched and its unit is priced at 720.00. The mirror (the debit note on
the first bill, which should come out 472.00 short) was not driven on this
side. Workaround: send the rest back off the receipt.

**Suspected:** `app/purchase_return/billing.py:232` to `:293`
(`bill_line_claims`: bill-route returns first at `:232`, then
`place_on_bills` at `:262` and `share_out`), with `share_out` at `:334` to
`:335` (`shares[-1] += left`).

### PRCQ-73: a return's header charge is not counted on its bill (Medium, selling)

S1 17:10 and 17:24 IST (`s7.py` part x, `px.py` part h), S2 17:27, N1 17:13
and 17:27. The same on all three.

1. A bill of 2 BOX at 1,200.00 with `additional_charges` 100.00: 2,932.00.
2. `POST /sales-returns` off the bill line, 1 BOX, `additional_charges` 60:
   1,476.00, completed. Then the other box with `additional_charges` 40:
   1,456.00. **2,932.00 credited; the customer's account reads 0.00.**
3. `GET /receipts/outstanding`: the bill reads **`allocated_amount`
   2,832.00, `outstanding_amount` 100.00**. `GET /customers/ageing`:
   `total_outstanding` 100.00 in the 0 to 29 bucket, `account_balance` 0.00,
   **`unapplied_credits` 100.00**.
4. `POST /receipts` of 100.00 allocated to the bill: **201**. On S1 and S2
   the customer now holds an advance of 100.00; on N1 it comes off what the
   customer owes on other bills. (Reversed afterwards.)

**Expected:** `docs/SALES_CHAIN_RULES.md`: "What a bill still owes counts a
return off its note … so Record Receipt, the ageing, sales targets and
commission see the value". **Actual:** only the return's lines are read;
the header charge the same return gave back is on the customer's account
and on no bill. A bill returned in full goes on being offered in Record
Receipt, ages into the overdue buckets and would be picked up by reminders
and overdue interest, while the account says nothing is owed. Workaround:
none for the bill; the ageing's own reconciling line shows the gap.

**Suspected:** `app/settlements/services/settlement_service.py:363` to
`:371` (`credited_against` sums `SalesReturnLine.net_amount`; the return's
`additional_charges` are on the header and are in no line).

### PRCQ-74: credit a return leaves on a paid bill cannot be set against another bill (Medium, finance)

C1 17:17 IST, C2 17:19 and 17:51 (`b7c.py` part f, `adv.py`). The same on
both. The same whether the return is raised off the note or off the bill.

1. A bill of 2,832.00, paid in full by `POST /receipts` allocated to it.
2. 7 pieces returned (826.00, completed). The customer reads
   `current_outstanding` 0.00, **`unapplied_advance_balance` 826.00**; Dr
   4100 700.00, tax 126.00 / Cr 1100 826.00; the statement shows the return
   as a line of 0 and 0 and `unapplied_advance` 826.00 beside a closing
   balance of 0.00; the receipt still reads `allocated_amount` 2,832.00,
   `unallocated_amount` 0.00.
3. A second bill of 1,416.00. The customer reads `current_outstanding`
   1,416.00 and `unapplied_advance_balance` 826.00.
4. `POST /receipts/{first receipt}/allocate` 826.00 to the second bill: 422
   "RC-… has only 0.00 left unapplied." A receipt of 590.00 allocating
   1,416.00: 422 "Allocations total 1416.00, which is more than the 590.00
   that moved." A receipt of 590.00 allocating 590.00: 201; the customer now
   reads **outstanding 826.00 and advance 826.00**, the bill 826.00
   outstanding, ageing 826.00 (the two receipts of 590.00 and what follows
   were driven on C2). `POST /refunds` naming the bill: 422 "A
   refund returns money held on account, so it is not applied to an
   invoice." `party-adjustments` has no kind for it.
5. What does work: `POST /refunds` of 826.00 in cash: 201, Dr 1100 826.00 /
   Cr 1000 826.00, the advance reads 0.00; one more rupee: 422 "Refund
   amount exceeds unapplied advance."

**Expected:** the statement's own comment
(`app/customers/services/statement_service.py:175`): "an advance a customer
is entitled to have applied". **Actual:** `allocate` moves a receipt's
unapplied money, and this advance belongs to no receipt, so the customer
owes 826.00 on one line and is owed 826.00 on another until somebody pays
it out and takes it back. This is a missing route, not a wrong figure, and
it is older than this week's fixes; it is reported because a return on a
paid bill is the ordinary way such credit arises. Workaround: refund it and
record a receipt, or reverse the original receipt and record it again.

**Suspected:** `app/settlements/services/settlement_service.py:1611` to
`:1629` (`allocate` reads `row.unallocated_amount` of one settlement); the
advance a return creates is written by
`app/customers/services/customer_service.py:734` with no settlement behind
it.

### PRCQ-75: the JSON import routes answer 500 for a file their schema refuses (Medium, selling and buying)

S1 17:24 and 17:26 IST, S2 17:26 and 17:27 (`px.py` part i, `imp.py`). The
same on both. 42 requests.

`POST /sales-orders/import`, multipart, `format` json, `payload`
`{"records": [good, bad]}`:

| The payload | Answer |
| --- | --- |
| The second order has two lines numbered 1 | **500** `{"success":false,"error":{"code":"internal_server_error","message":"An unexpected error occurred."}}` |
| A record with no customer and no lines; a quantity "many"; an unknown field; no records; text that is not JSON | **500**, the same |
| The control: the first payload's order through `POST /sales-orders` | 422 "Lines 1 and 2 of the request are both numbered 1. Number each line once." |

Nothing is written (360 orders before and after on S1). With a record the schema
refuses, and with text that is not JSON: `quotations/import`,
`delivery-notes/import`, `sales-returns/import`, `purchases/import`,
`goods-receipts/import`, `purchase-invoices/import`,
`purchase-returns/import`: **500 each**. `sales-invoices/import`: 422 "The
request validation failed."

**Expected:** `docs/PURCHASE_FRAMEWORK.md` on imports: "the refusal is the
single save's own, naming the record". **Actual:** that holds for what the
service refuses; what the schema refuses never reaches the service. Since
D-PRC-60 put the line-number rule in the schema, a file with a repeated
line number is one of them. The person importing is told nothing about
which record or why. Workaround: find the fault by hand.

**Suspected:** `app/sales_order/api/router.py:797`
(`SalesOrderImportRequest.model_validate_json(payload)` inside the handler:
the `pydantic.ValidationError` it raises is not FastAPI's request
validation error, so it reaches the unhandled-exception handler; the
server log shows exactly that), and the same line in
`app/quotation/api/router.py:289`, `app/delivery_note/api/router.py:830`,
`app/sales_return/api/router.py:366`, `app/purchase/api/router.py:311`,
`app/goods_receipt/api/router.py:588`,
`app/purchase_invoice/api/router.py:1177` and
`app/purchase_return/api/router.py:586`. `app/products/api/router.py:246`
and `app/inventory/api/router.py:965` have the same call and were not
driven.

### PRCQ-76: a draft bill of a note that has a return cannot be cancelled (Medium, selling)

S1 17:25 and 17:26 IST, S2 17:26 and 17:27 (`px.py` part j, `imp.py` part
c). The same on both.

1. A note of 2 BOX. A draft bill of it saved.
2. 1 BOX returned off the note (completed; unbilled, so it credits nothing).
3. Approve the draft: 422 "SI-… line 1: 1 BOX of the 2 BOX delivered came
   back before being billed, so 1 BOX is left to bill. Change the bill to
   what the customer kept." (right).
4. `POST /sales-invoices/{id}/cancel`: **422 "SI-… cannot be cancelled
   while it has sales return SR-…. Reverse or cancel those first."** The
   bill is a draft; the return is the note's.
5. A fresh bill of the 1 BOX left: 422 "Invoice quantity exceeds the
   available source quantity." (the draft still holds both).
6. What does work: `PUT` the draft with 1 BOX: 1,416.00; approve: 200.

The same when the return comes first and the draft of what is left is saved
afterwards (cancel refused), and when a free piece comes back under a draft
of 24 + 2 free. The control, a draft with no return: cancelled, 200.

**Expected:** a draft that has charged nobody can be withdrawn; the message
PRCQ-69 added tells the person to change the bill, and cancelling it to
start again is the other thing they will try. **Actual:** the guard written
for an approved bill (D-SELL-7: goods the bill charged for can also come
back against its note) runs for a draft, names a return that is not the
bill's, and tells the person to cancel a completed return. Workaround: edit
the draft and approve it.

**Suspected:** `app/sales_invoice/services/sales_invoice_service.py:3039`
to `:3068` (the returns of the note lines the bill bills are blockers
whatever the bill's status and whether or not the bill charged the units
that came back).

### The Low findings

- **PRCQ-77 (pricing).** S1 16:59 and 17:25 IST, S2 17:00 and 17:27
  (`a63.py` part q, `px.py` part j). Offer "buy 10 get 1". `POST
  /quotations`, one line: 2 BOX with `free_quantity` "0". The quotation
  answers and reads two lines: 2 BOX, `free_goods_refused` true; and **0 + 2
  PIECE free, offer named**; it prints "Free with QJ7, 0 + 2 free, PIECE".
  Converted, the order has the box line alone, 24 reserved, no claim. An
  order typed the same way has no free line either. So the refusal is kept
  on the line and carried to the order (PRCQ-68, fixed), and the quotation
  itself still quotes the 2 free. A piece line is right (nothing free on the
  quotation). Workaround: none on the quotation; the order is right.
  Suspected: the quotation's pricing adds the engine's free-only line for a
  line in another unit without asking whether that line refused; the order
  drops it (`docs/PRICING_AND_PROMOTIONS.md`: "0 free" sent without the
  engine's line is the refusal). `app/quotation/services/quotation_service.py`,
  where `free_goods_refused` is set.
- **PRCQ-78 (selling).** S1 17:25 IST, S2 17:27 (`px.py` part j, `j2r.py`).
  A bill of 2 BOX at 1,200.00 (2,832.00) returned in pieces: 7 PIECE, 826.00;
  7 PIECE typed at 100.00 a piece, **825.9805** (`bill_discount_amount`
  0.0165; Cr 1100 825.98); 7 PIECE with nothing typed, **825.9476** (0.0444;
  825.95); the last 3 PIECE, 354.00. **2,831.93 credited; the bill reads
  `allocated_amount` 2,831.93, `outstanding_amount` 0.07** with every piece
  back. Returned as 7 and then the other 17 it is exact (A, PRCQ-64). The
  cap PRCQ-64 added works what a piece is "still worth" from box quantities
  kept to four places (0.5833), takes the paise off each middle return, and
  the last return is priced at the bill's price, not at what is left.
  Suspected: `app/sales_return/billing.py:512` to `:528` (`_units_worth`:
  `exact` is passed for the units going back and `out` is the rounded
  remainder), and the caller's "priced as before and only capped".

## Case text to correct

Round 3's to round 6's tables still stand; nothing in them was applied.
Changes, for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 6's held-back cases | Can be written as passing: two lines of one product swapped (both named, one claim of 5); a return priced above its bill (refused by name; 1,200.00 exactly passes); a note billed in parts returned off the note (2,360.00 either way); a return off the note after the bill, under commission (-35.00, -17.50, +2,006.00); a debit note then a purchase return (1,227.20) |
| New cases wanted | (1) "0 free" on a quotation carried to its order; (2) a return's header charge capped at the bill's (60.00, then 40.00); (3) a part bill of a gift line (stated whole on the first, refused on the second) and 24 + 2 free billed 12 and 12; (4) a draft bill refused at approval after free goods came back, saved again and approved; (5) a rule on collected money with a return (-70.00 paid, 0.00 unpaid, +170.00 on collection); (6) a clawback after a return off the note (120.00, 35.00, 85.00) |
| Hold back until fixed | A unit off the note then the first bill's own line (PRCQ-71) and its buying twin (PRCQ-72); a purchase return typed above its bill (B1); a return with a header charge and what the bill then owes (PRCQ-73); an import file the schema refuses (PRCQ-75); cancelling a draft bill of a note with a return (PRCQ-76) |
| 009 | Unchanged: state QQ's price (84.00) in the case |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **`additional_charges` on a sales bill carry no tax and are in no taxable
  value** (S1, S2, N1): "Other charges 100.00" is added after tax, credited
  to Sales, and reaches GSTR-1 only inside `invoice_value`. The repository
  rule is that a header charge must reach the line and therefore the tax;
  `charges` and `freight_amount` do.
- **The supplier ageing and the suppliers' outstanding report do not net a
  supplier credit** (R1, S3): 1,699.20 where 849.60 is owed; the payables
  report, the statement and the books do. Round 6 saw the second; the
  ageing is the same.
- **A supplier's bill can be paid in full while a credit against it
  stands** (R1, S3): the payment is taken and the supplier then owes the
  firm 849.60.
- **A draft purchase return raised off the bill takes the room of a debit
  note**, which is refused as "1440.00 already returned" when nothing has
  gone back (R1, S3). Documented ("any not cancelled"); the wording is not
  true of a draft.
- **A return that credits nothing states a value**: a return off an
  unbilled note reads `grand_total` 1,416.00 and a purchase return off an
  unbilled receipt typed at 900.00 reads 1,062.00, and neither moves the
  party's account (S1, N1, R1, S3).
- **The statement shows a return on a paid bill as a line of 0 and 0**
  (C1, C2): the 826.00 appears only as `unapplied_advance` beside the
  closing balance. A refund is a line of 0 and 0 too.
- **Ageing lists nothing for a customer who is owed money** (C1, C2): with
  0.00 outstanding and 826.00 held, `GET /customers/ageing` for that
  customer is empty.
- **Points spent on a bill are not given back when the bill is returned in
  full** (S1, S2): the customer gets the 100.00 as credit on the account
  instead, which PRCQ-74 then leaves unusable.
- **100 points spent count as 99.99 against the bill on S2** and 100.00 on
  S1 (the customer's points there read 2009.5180, worth 2009.51).
- **Document totals are kept to four places and are not always paise**:
  bills of 1,270.4667 and 1,663.7292, returns of 2,363.9333 and 369.7176, a
  purchase return of 1,699.2236. The journals post the paise.
- **`GET /receipts/outstanding` and
  `GET /purchase-invoices/reports/outstanding` are not paged and ignore
  `page`**: a script that pages them reads the same rows for ever (mine did,
  twice).
- Round 6's gaps were not driven again except where A or B covers them.
  Closed: "0 free" on a quotation; a typed price on a return off the note.

## Left on the firms

- **S1 and N1: customer PC credited 472.00 more than billed twice, and
  472.00 short once** (PRCQ-71: parts y5, z2 and z1), with their six bills,
  three credit notes and six returns; one bill each with a header charge
  returned in full and reading 100.00 outstanding (PRCQ-73; a second on S1
  and one on S2 for customer B7H, a second on N1 for PC); nine fresh bills
  each from the PRCQ-64 probes, five of them unpaid with a refused return,
  one credited 2,360.00
  for goods billed 2,832.00 (the typed deduction); the bills, credit notes
  and returns of PRCQ-65's scenarios (three notes of 6 BOX billed in three,
  two of 4 BOX part billed); on S1 one more bill of 2,832.00 from the run
  that was stopped.
- **S1 and S2**: one order each shipped with 5 free units claimed (PRCQ-63)
  and one approved with nothing free, cancelled; the part bills, drafts and
  returns of the PRCQ-69 scenarios, among them one bill each of 12 with 2
  free typed; **three draft bills each left as drafts that cannot be
  cancelled** (PRCQ-76: one of 24 + 2 free from `s7.py`, one from `px.py`,
  one of 1 BOX from `imp.py`) and two more each changed to what was left
  and approved; one bill each reading 0.07 outstanding (PRCQ-78);
  four bills each from B9 (two with one box still out) and 18 DET sold and
  returned; loyalty: a new customer B7L at 0 points, customer PC 156.64
  points lighter and holding 100.00 of credit; an order of 7 PIECE of X4K
  shipped and billed; products Z7X, Z7Y, Z7B, Z7N, Z7R, Z7H, Z7I, Z7J;
  offers QX7, QY7, QZ7, QB7, QN7, QH7, QI7, QJ7 retired; quotations left
  DRAFT or converted; customers B7H and B7L.
- **C1 and C2**: customers B7S, B7F, B7G, B7U, B7V, B7P and six B7K…; rules
  for Asha on VS7 (slabs) and VK7 (10% on collected), ACTIVE; **payouts for
  July (PAID, 120.00) and June (APPROVED, 85.00)** with sales dated 15 July
  and 15 June; on each firm 2,478.00 held as advances for three customers
  (PRCQ-74), one of them, B7F, also owing 1,416.00 on C1 and 826.00 on C2;
  one refund of 826.00 in cash; eight receipts on C1 and nine on C2; four
  more bills and returns from `b1.py`.
- **R1 and S3**: about twenty new suppliers each (V7nn); **eight
  suppliers in debit** (472.00 from PRCQ-72; 424.80 twice, 590.00, 500.00
  and 0.02 from B1; round 6's two); debit notes and purchase returns of
  every scenario; two payments each, and one payment each recorded and
  reversed; one draft purchase return cancelled, one return left APPROVED
  and cancelled; purchase stages as found. **N1**: six new suppliers, one
  in debit by 472.00; purchase stages put back as found.
- **P1 and P2**: one more approved order pinned over its batch, as `m5.py`
  leaves it.
- **N3, R4, L4, C4, D4, O4**: what the regression scripts leave on a firm.

## Not verified

- **Nothing on screen.** The desktop was not opened.
- **Nothing was read from the database.** That the server runs `a64e3512`
  was taken from the hand-over, from `git log` on the working tree and from
  the fixes behaving as merged.
- **Everything ran once, in one window** (16:56 to 17:52 IST).
- **One firm where two would be better**: GSTR-3B (N1 alone has a GST number
  among the buying firms used); the GSTR-1 row of a bill with a header
  charge (N1); the regression (one firm each, as asked).
- **PRCQ-72's mirror** (the debit note on the first bill): not driven.
  PRCQ-71 and 72 with three bills, or with parts of different sizes: not
  driven.
- **PRCQ-73 on the buying side** (a purchase return's header charge against
  what the supplier's bill owes): not driven; B1 shows the charge is not
  capped there.
- **PRCQ-75** on `products/import` and `inventory/opening-stock/import`
  (the same call in the code): not driven.
- **PRCQ-74**: whether the desktop offers a route the API does not show; an
  advance left by a credit note on a paid bill.
- **The rate difference by batch** (`pm.py`): no fresh pharmacy firm.
- **Commission**: a margin rule, and a category rule, under a return off the
  note.
- **GSTR-1 over four months** was not asked again.
