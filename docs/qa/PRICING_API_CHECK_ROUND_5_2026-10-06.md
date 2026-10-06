# Pricing, promotions, loyalty, commission, claims and lines in another unit: checked through the API, round 5, 2026-10-06

The fifth pass over this module, driven the way rounds 1 to 4 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `3ee89dd1`, PR #1288),
books read back through the API, nothing read from the database, no source
file changed and nothing fixed.

**The round found new things, so it does not close the module: two High, one
Medium and two Low (PRCQ-58 to PRCQ-62).**

- **An offer's free goods still get out unclaimed when a draft order comes
  back with its lines moved.** The fix for PRCQ-48 finds the engine's free
  line by its line number. A client that echoes the read after deleting the
  line above it, or inserting one, sends the free line at another number; it
  is then kept as typed: free, no offer named, no claim. On an offer a
  principal pays for, four orders gave 8 free units, the offer counts 4 and
  the claim preview is 240.00 where 480.00 is due. The desktop does not send
  it; an API client or an import that echoes what it read does (PRCQ-58).
- **A per-unit commission is paid on units that came back.** 24 pieces
  billed at 2.50 a unit earn 60.00; all 24 returned, the report still says
  60.00. A payout was accrued, approved and paid at 386.00 where 368.50 was
  earned. A percentage rule beside it nets the same return correctly. This
  has nothing to do with the unit a line is typed in (PRCQ-59).

**Every round 4 finding that was meant to be fixed is fixed**, each by its
original reproduction and on two firms except where said. The four left on
purpose are unchanged. **Purchase by the box, the rate difference claim,
promotion budgets, principal claims and the twelve cases give what they gave
in round 4**; the only changed lines are the fixes' own wordings.

## When, and on which firms

Six fixtures were built between 13:38 and 13:41 IST, one at a time, and
everything was driven between **13:42 and 14:05 IST on 6 October 2026, which
is 08:12 to 08:35 UTC on the same day**. Round 4's ten firms were used again
wherever a clean firm was not needed. The server was not restarted; `/health`
answered 200 before each of the 64 script runs and at the end. **No request
answered 500 or 503.** The server's log for the window holds four "Database
integrity conflict" warnings, all raised by one probe of mine (two lines
carrying one line number, PRCQ-60), and no error.

**Memory.** Free memory was read before each build and before each script.
The lowest reading of the round was **2,086,480 KB, before the sixth build
(O2, 13:40)**; the lowest while driving was 2,543,496 KB (13:42). No build
had to wait. No read was dropped in transit this time: pages of 25 whole
bills (about 134 KB) read back whole on S1, S2 and N1.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| S1 | `selling-firm` | `T100667G6-S` | | A: PRCQ-47, 48, 49, 50, 51, 52, 53, 55; B: every selling probe; generic checks |
| S2 | `selling-firm` | `T10064CYP-S` | | the same again, except PRCQ-50 |
| S3 | `selling-firm` | `T100659Z3-S` | | A: PRCQ-48 by round 4's own script, PRCQ-51, 54 and 57 on purchase |
| R1 | `ready-firm` | `T10067V0N-R` | | A: PRCQ-51, 54, 57 on purchase; the purchase HSN report |
| P1, P2 | `pharma-firm` | `T1006THK2-P`, `T1006EJV8-P` | | PRCQ-47 with a pinned batch; the back-order rule |
| L1 | `loyalty-points` | `T100617FE-S` | | B: loyalty on documents typed in another unit |
| C1 | `commission-firm` | `T1006MWGX-T` | | B: commission on documents typed in another unit, accrued and paid |
| N1 | `selling-firm` | `T100657VP-S` | yes | C: cases 001, 002, 004, 009, 011; budgets, claims, the rate difference; PRCQ-50 on a second firm; generic checks |
| R2 | `ready-firm` | `T1006X0KB-R` | yes | C: buying by the box |
| L2 | `loyalty-points` | `T1006B9EO-S` | yes | C: cases 005, 010; round 3's and round 4's loyalty scripts |
| C2 | `commission-firm` | `T1006DWN6-T` | yes | C: cases 006, 007, 008; PRCQ-59 on a second firm |
| D2 | `selling-invoiced` | `T10067YTU-S` | yes | C: case 012 |
| O2 | `selling-ordered` | `T1006XCSI-S` | yes | C: case 003 |
| D1, O1 | | | | books only |

Scripts and logs are in the scratchpad folder `pricing5`, beside `pricing4`.
Round 3's and round 4's scripts were copied and run unchanged for the
regression; the new ones are `s5a.py`, `p5a.py`, `g5.py`, `b5.py`, `b5h.py`,
`l5.py`, `c5.py`, `c5b.py`, `m5.py`, `gg5.py` and `dup.py`. Logs were
compared by round 4's `cmp4.py` (firm tags, ids, times and document numbers
masked, the two logs compared as bags of lines). "The same on both" means
that comparison showed nothing.

What went wrong on my side, so the record is straight:

- **`c911.py` stopped at its first line on N1** ("Product code already
  exists"): `a22.py` had made product QQ on that firm a minute earlier. The
  product's id was put in the script's state file and the script run again.
  QQ is priced 100.00 on N1 where the case assumes 84.00, so the
  mixed-product figures of case 009 differ from round 4's by exactly that.
- **Two bodies of mine were wrong and were sent again corrected**: a price
  list step's fixed rate is `rate`, not `unit_price`; a credit note's reason
  is an enum (`RATE_DIFFERENCE`), not text. Each cost one refused request.
- **`m5.py` found batch BN down to 5 pieces on P1 and P2** and could not ship
  a box from it; it was changed to receive a fresh batch BP of 48 and run
  again. That receipt is not billed.
- **The pharmacy script `pm.py` (the rate difference by batch) did not run
  again**: its firm has done it once and the script skips. No fresh
  `pharma-firm` was built; six new firms was the limit.
- **Four script edits were made with `sed` or an inline patch, not the file
  tool** (moving one part of `s5a.py`, two literals in `b5.py`, one tuple in
  `c5b.py`, and the renamed copies `b5x.py`, `n4x5.py`, `n4z5.py`).
- **N1 was given a GST number** (and its customer PC one) so GSTR-1 and the
  e-invoice export could be read on a second firm.

## A. The findings of round 4

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| PRCQ-47 | **Fixed** | S1, S2; with a batch P1, P2 | Order of 2 BOX at 1,200.00; a note line of 24 naming PIECE: **422 "Line 1 is delivered in PIECE where SO-2026-2027-000118 orders it in BOX. Deliver it in the order's unit."** (2 PIECE: the same). Order of 24 PIECE, named or not; a note line of 2 BOX: 422 "…delivered in BOX where SO-… orders it in PIECE…". A note line naming the order's own unit saves. A note line of 2 naming BOX and `inventory_uom_id` BOX, and one naming only `inventory_uom_id` BOX: saved at 2,832.00, **24 leave** (movement `quantity` 24.0000, `entered_quantity` 2.0000), billed 2,832.00, order DELIVERED. Part delivery (4 BOX, 1 shipped): a second note of 12 PIECE refused at save, and a draft of 1 BOX edited to 12 PIECE refused. With free goods (2 BOX + 2 PIECE free): the box line typed 24 PIECE refused; the free line naming BOX refused as "Line 2 is delivered in BOX where … orders it in PIECE"; each line in its own unit saves, 26 leave, the offer counts 2, the bill is 2,832.00. Pinned to a batch (1 BOX at 1,200.00, GST 12%): 12 PIECE refused with the batch named or not; 1 BOX with the batch ships 12 and bills 1,344.00. Round 4's own script (`n4x.py` part q): refused both ways on both firms |
| PRCQ-48 | **Fixed**, for an order whose lines keep their numbers | S1, S2; S3 by round 4's script | "Buy 10 get 1", 2 BOX. `PUT` of the box line alone with **no** `free_quantity`, once and twice: 2 BOX + 2 PIECE free naming the offer, 26 reserved, one claim of 2. `PUT` of both lines as read, once and twice: the same. The box quantity 3 either way: 3 PIECE free, 39 reserved, claim 3; quantity 1: 1 free. The box line alone with `free_quantity` "0.0000": no free line, 24 reserved, no claim, as D-SELL-41 intends. Free goods on the line (24 PIECE, 2 free): echoed, or sent with no figure: 2 free, offer named, claim 2; sent 0: none; sent 3: 3, typed, no claim; echoed at 36: 3 free, claimed. A gift of another product: claimed once whichever way it is sent. The offer retired before the echo: the free line goes and 24 are reserved, on the box order and on the line. **A budget of 2 free units**: the first draft takes it; the second, untouched, is refused "Promotion Z48 has 0 left of its budget of 2 free units, and this document would take 2."; the third echoed as read and the fourth sent the desktop's way save **without** a free line and are approved at 24; the offer reads 2 given of 2 (S1, S2 with a new offer; S3 with round 4's script, where the third order's note ships 24, not 26). Sending both lines with no `free_quantity` on either is refused by the schema ("Line 2 orders a quantity of 0 and supplies nothing free"). **What is left: PRCQ-58** |
| PRCQ-49 | **Fixed** | S1, S2 | Drafts of 6 and 6 against 10: the first approved; the second **422 "Line 1 of DN-26-27-000113 delivers 6 where SO-2026-2027-000153 has 4 left to deliver of the 10 ordered: DN-26-27-000112 delivers the rest. Cancel this note and raise one for what is left, or cancel the other note first."** The first cancelled: the second approved and dispatched, 6 leave, a note of 4 finishes the order. The same refusal when the first is dispatched, and when its 6 have since come back on a sales return. **Two approvals at the same moment, six fresh orders on each firm: exactly one 200 and one 422 every time**, 12 of 12; three drafts of 4 at once: two approved, one refused naming both. One note with lines of 3 and 3 beside an approved 5: refused. A line with free goods (20 + 2 free): drafts of 12 and 12 refused as "delivers 13 where … has 9 left to deliver of the 22 ordered, free goods included"; 12 then 8 ship 13 and 9. Bulk approve of both drafts: `done` 1, `refused` 1, the refused row carrying the same sentence |
| PRCQ-50 | **Fixed** | S1, N1 (sales); R1, S3 (purchase) | A bill typed 24 PIECE of 2 BOX, then 7 PIECE returned: GSTR-1's HSN row reads `unit` PIECE, quantity **17.0**, taxable 1,700.00 (24.0 and 2,400.00 before), and so does `/sales-invoices/reports/hsn-summary`. The return's e-invoice export: `Qty` **7.0**, `UnitPrice` **100.0**. The same code billed by the box (3 BOX, 3,330.00 after its offers) is a second row, `unit` BOX; 1 BOX returned leaves 2 and exports `Qty` 1.0 at 1110.0; 5 PIECE returned off the box bill exports 5.0 at 92.5 and comes off the **PIECE** row (12.0, 1,237.50). A BOX return off the bill typed in pieces: the credit note prints "1, BOX, 1,200.00", exports 1.0 at 1200.0, and comes off the BOX row; on N1, where no box bill existed yet, that row read **quantity -1.0, taxable -1,200.00** beside PIECE 17.0 until a box bill was raised (the documented limit). Purchase: bills of 7 and 17 PIECE of a receipt of 2 BOX read `unit` PIECE 24.0000, 1,440.00; 5 PIECE returned: 19.0000, 1,140.00; a bill of 2 BOX is a second row; 7 PIECE returned off it come off the PIECE row (12.0000, 720.00) |
| PRCQ-51 | **Fixed** | S1, S2 (sales); R1, S3 (purchase) | Sales, off the bill's free line: 0 with nothing free refused, "Line 1 returns a quantity of 0 and nothing free. Type a quantity, or leave the line off the return."; **0 + 1 free completes** with or without `return_uom_id` (reads 1 returned, 1 free; Dr 1200 60.00 / Cr 5200 60.00; total 0.00); the offer's count goes 2, 1, 0; a third, typed either way, refused "(0 PIECE sent and 2 free, 0 and 2 already returned; line 1 can still bring back 0 PIECE charged and 0 free)"; 0 + 1 free on the charged line refused, "the source line sent nothing free". Off the note before a bill: the same. Purchase, off the receipt's free-only line: 0 + 1 free completes twice, each **Dr 5400 Purchase Price Variance 55.38 / Cr 1200 Inventory 55.38**, Trade Payables and GRNI untouched, total 0.00 (as documented); a third refused "can still send back 0 PIECE bought and 0 free"; on the charged line "2 BOX bought and 0 free". Off the bill's free line: refused, "free goods go back off the goods receipt that brought them in"; off the receipt after the bill: completes |
| PRCQ-52 | **Fixed** | S1, S2; the fixed rate on S1 only | Product kept in BOX, sold in PIECE, list "2% from 0, 5% from 2 boxes": **24 PIECE take 5%** (2,690.40), 12 PIECE 2%, 23 PIECE 2% (`base_quantity` 1.9167), 25 PIECE 5%, 2 BOX 5%, 1 BOX 2%. A list with a fixed 1,080.00 a box from 2 boxes: 24 PIECE at **90.00** a piece (2,548.80), 23 at 100.00, 2 BOX at 1,080.00, 1 BOX at 1,200.00. The known limit, reported as a figure: 7 PIECE leave 0.5833 of a box, cost of goods **419.98**; the shelf reads 99.4167 boxes (S1) |
| PRCQ-54 | **Fixed** | R1, S3 | 7 PIECE returned before any bill: **Dr 2300 420.00 / Cr 1200 420.00**, nothing to 5400; the other 17 billed: Dr 2300 1,020.00; GRNI cleared 1,440.00 exactly. The mirror, 7 billed then 17 returned: 420.00 and 1,020.00, 5400 untouched. 5 returned, 5 billed, 7 returned, 7 billed: 300.00, 300.00, 420.00, 420.00, 5400 untouched |
| PRCQ-57 | **Fixed** for the messages it named | S1, N1; R1, S3 | "Return quantity exceeds what was dispatched on the source document (2 BOX sent, 0.5833 BOX already returned)."; "line 1 can still send back 1.4167 BOX bought and 0 free."; a receipt line of 24 typed in PIECE is refused in the unit's sentence; an offer's free units read `0.0000` and `3.0000`. Other messages still count to four places with no unit: PRCQ-62 |
| A claim receipt dated tomorrow | **Fixed** | S1, N1 | 422 "A payment cannot be received on a day that has not happened yet."; dated before its claim: "A payment cannot come before its claim." |

Left on purpose, and unchanged:

| Id | Firms | What was seen |
| --- | --- | --- |
| PRCQ-53 | S1, S2 | A product sold by the BOX: an order and a quotation of 2 naming no unit are 2 pieces, 236.00 |
| PRCQ-55 | S1, S2 (sales side only) | A draft bill of 7 PIECE reads 0.5833 with unit PIECE; sent back as read: 422 "PIECE is counted in whole numbers, so 0.5833 PIECE cannot be entered."; sent as 7 PIECE: saved, 826.00 |
| PRCQ-56 | S2, R1, S3, P1, P2 | Valuation against the stock account: 0.01 on S2, P1 and P2; **0.04 on R1 and S3** (0.01 in round 4; they have taken more free goods since) |
| An order pinned to a batch for more than it holds | P1, P2 | 5 BOX (60 pieces) pinned to a batch holding 36: approved, 60 reserved; cancelled again |

## B. Probes around the fixes

**1. A quotation under an offer (S1, S2).** A quotation of 2 BOX shows the
free line, "Free with QA5", 0 + 2 PIECE. Sent back with both lines it is
refused by the schema ("Input should be greater than 0"), as documented; sent
back with the box line alone it keeps its free line. Converted, the order
has the engine's line naming the offer, reserves 26 and claims 2. Right. A
quotation of **24 PIECE** shows 2 free on the line; its order carries the 2
free and **names no offer and claims nothing**. That is the gap
`docs/PRICING_AND_PROMOTIONS.md` records ("One gap stays"); it is in Gaps
with its figures.

**2. An order amended after approval (S1, S2).** There is nothing to drive:
every `PUT` of an approved order, on hold or not, is 422 "Only draft sales
orders can be updated." The order ships 26 and the claim stands.

**3. The offer changed between two saves (S1, S2).** Four drafts under
"buy 10 get 1"; the offer edited to "get 2" (version 2). A box draft echoed
as read, and one sent the desktop's way: the free line becomes 4 PIECE,
claim 4. The draft with 2 free on the line, echoed: 4, claim 4. A draft
never saved again is approved at the 2 it was saved with, claim 2. One claim
each; cancelling all four brings the offer to 0.

**4. The engine's free line sent back at another line number (S1, S2).**
PRCQ-58.

**5. A note line naming no unit on a product sold by the BOX (S1, S2).** The
order line is in pieces (PRCQ-53); its note naming no unit, or PIECE, saves
at 236.00; naming BOX is refused, "delivered in BOX where … orders it in
PIECE".

**6. The cap at approval against a note that is dispatched, cancelled or
returned (S1, S2).** In A, PRCQ-49. A dispatched note counts; a cancelled one
does not; a note whose 6 pieces have all come back on a sales return still
counts (the order reads PARTIALLY_DELIVERED with 4 reserved).

**7. Returns before the bill (S1, S2).** 2 BOX + 2 PIECE free dispatched; 1
BOX and 1 free PIECE come back off the note. A bill of the whole note is
refused, "Line 1: 1.0000 of the 2.0000 delivered came back before being
billed, so 1.0000 is left to bill." The bill of 1 BOX is 1,416.00 and its
free line reads and prints **"0 + 2 free"** (PRCQ-61). Off that bill one
more free piece comes back; a second is refused, "2 PIECE sent free, 2 PIECE
already returned against it or the bill for it". Nothing over-returns.

**8. Free units returned after the bill was part-credited (S1, S2).** A
credit note of 400.00 (472.00) on the charged line, approved. A credit note
on the free line is refused, "0.0000 charged, 0.0000 already credited". One
free piece returned: completes at 0.00, Dr 1200 60.00 / Cr 5200 60.00, the
customer's balance untouched, the offer's count 2 to 1. Right. (Both boxes
of the charged line then come back at the full 2,832.00: Gaps.)

**9. A principal's free goods claimed, then returned (S1, S2).** Offer paid
in full by a principal; 2 BOX + 2 PIECE free billed; preview 120.00; claim
raised, Dr 1420 120.00 / Cr 5200 120.00. One free piece returned: the raised
claim stands at 120.00, the preview is empty, and after a second bill (1
free) the preview holds +60.00 and **-60.00 "Came back after claim
CLM-…"**. Right. 1420 equals open claims.

**10. HSN totals against the registers (S1, N1).** The day's HSN summary
adds to 119,327.61 taxable and 21,478.97 tax on S1 (47,149.45 and 8,486.90
on N1); GSTR-3B's outward supplies read the same; the GST sales register
adds to 119,327.60 and 21,478.97 (47,149.44 and 8,486.90). A paisa apart on
the taxable value on both firms: Gaps.

**11. Loyalty on documents typed in another unit (L1).** Two customers, each
2 BOX: one billed by the box, one billed as 24 PIECE. Both earn 56.64. 7
PIECE back on each: 40.12. 1 BOX more: 11.80. +60 and 55 redeemed: 16.80,
each owing 535.00. The last 5 pieces back: points unchanged, 55.00 becomes an
advance. Bills 40 days back under a one-month expiry: born lapsed, 56.64
each; 7 PIECE returned: the lapse is taken to the books; the sweep finds
nothing. **The two customers read the same at every step, and Loyalty
Payable equalled the report at all nine readings.**

**12. Commission on documents typed in another unit (C1; the report on C2
too).** Sales dated yesterday for one salesman. 2 BOX billed as 24 PIECE
under 2.50 a unit: +60.00. 2 BOX billed as 24 PIECE, and as 2 BOX, under
the firm's percentage, collected: +96.00 each. 7 PIECE back off each
percentage bill: -28.00 each. Right. 7 PIECE back off the per-unit bill:
**0.00**. The payout was accrued at 386.00 (the report's figure), approved
(Dr 5600 386.00 / Cr 2400 386.00) and paid; 2400 ends 0.00. PRCQ-59.

## C. Regression

**Buying by the box (R2, fresh; round 3's `bx.py` unchanged, against round
4's log).** Three lines differ and each is a fix's wording: the two refusals
now say "2 BOX bought", and 24 typed in PIECE on a receipt is refused in the
unit's sentence. Everything else is line for line round 4's.

**The rate difference claim (N1; `cr.py` unchanged).** The same on both: 100
at 60.00 to 55.00 is 500.00, Dr 1420 500.00 / Cr 5400 500.00, cancelled and
raised again, receipts of 200.00 and 300.00. By batch: not driven again.

**Promotion budgets and principal claims with free goods (N1; `a27.py`,
`a28.py` unchanged).** The same figures. The differing lines are an offer's
free units now reading `0.0000` and `3.0000` where they read `0` and
`3.00000000000000`, two receipts landing in the other order, and three
offers `c911.py` had not yet made when `a28.py` listed them.

**Lines sold by the box, and round 3's own scripts (N1; `a22.py`, `a24.py`,
`a35.py` unchanged).** The same on both, with nothing differing.

| Case | Firm | Verdict | Difference from round 4 |
| --- | --- | --- | --- |
| 001, 002, 004 | N1 | **Pass** | None; two lists read in the other order |
| 003 | O2 | **Pass** | None beyond `0` reading `0.0000` |
| 005 | L2 | **Pass**, text wrong in one figure as before | None |
| 006 | C2 | **Case text wrong, product right**, as before | None |
| 007 | C2 | **Not runnable as written**, as before; the flow passes | None |
| 008 | C2 | **Pass** | None |
| 009, 011 | N1 | **Pass** | QQ is 100.00 on this firm, so the mixed-product lines of 009 differ by that (DET x 3 and QQ x 3 is 460.00, not 420.00); every DET figure and the combo at 150.00 are round 4's |
| 010 | L2 | **Pass** | None |
| 012 | D2 | **Pass** | None; the print is 5 bytes longer |

The per-unit commission (C2, `cm.py`): 60.00 three ways, as before.

**Generic checks.** `gg5.py`, 69 requests, on S1 (other firm S2, buying R1)
and on N1 (S1, R2): a note line of 0, negative, text, five decimals, 0.5
BOX, a unit id that does not exist or is not a UUID, a field the write does
not have; a note, an approval and a bulk approval by a read-only user (403)
and from another firm (404, or the row "Delivery note not found"); bulk
approve of none, of 101, of an unknown id, of a stale version, of one note
named twice; a draft order's `PUT` with `free_promotion_id` sent, a negative
or text free quantity, line number 0, no lines, another firm, a read-only
user, a stale `If-Match` (409); free units returned negative, as text, as
0.5 PIECE, more than went out, restocking more than returned, in a unit
that does not exist; price list steps negative, five decimals, over 100%,
two at one break, another firm's product; claim receipts dated tomorrow, a
year ahead, before the claim; GSTR-1 over four months and backwards; the
HSN summaries by a read-only user (200) and from a firm the user is not in
(403). Round 4's `n4g.py` (N1, S2, R2) and round 2's `g.py` (N1, S2, L2)
gave their round 4 answers, the fixes' wordings apart. **All refused
cleanly and nothing at 500, with one exception that is a finding**: a
`PUT` with two lines numbered 1 is accepted (PRCQ-60).

**The books at the end, all sixteen firms.**

| Firm | Trial balance | 1100 = customers less advances | 2100 = suppliers' outstanding | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation | 5400 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 5,855,978.60 balanced | 165,055.56 | 28,320.00 | 3,310.54 | 0 | 120.00 | 5,555,820.02 | 0 |
| S2 | 4,948,221.95 balanced | 116,840.71 | 28,320.00 | 2,346.24 | 0 | 184.54 | 4,729,680.04 against **4,729,680.05** | 0 |
| S3 | 481,380.44 balanced | 7,761.85 | 46,822.40 | 155.23 | 0 | 63.54 | 456,599.23 against **456,599.19** | -56.96 |
| N1 | 882,940.82 balanced | 61,300.33 | 29,618.00 | 1,225.99 | 0 | 109.40 | 770,962.27 | -500.00 |
| R1 | 42,930.00 balanced | 1,270.00 | 35,400.00 (reports 37,594.80) | 0 | 0 | 0 | 34,416.96 against **34,416.92** | 443.04 |
| R2 | 20,023.20 balanced | 1,270.00 | 18,195.60 (reports 20,390.40) | 0 | 0 | 0 | 14,577.60 | -57.60 |
| P1, P2 | 36,415.20 balanced | 20,255.20 | 0 | 0 | 0 | 240.00 | 5,301.62 against **5,301.63** | -240.00 |
| L1 | 184,506.27 balanced | 20,235.02 | 28,320.00 | 622.44 | 0 | 0 | 137,820.00 | 0 |
| L2 | 54,260.67 balanced | 16,333.02 | 28,320.00 | 588.84 | 0 | 0 | 19,860.00 | 0 |
| C1 | 327,466.00 balanced | 12,036.00 | 0 | 0 | 0.00 (all paid) | 0 | 268,200.00 | 0 |
| C2 | 258,962.00 balanced | 11,682.00 | 0 | 0 | 0.00 (paid) | 0 | 211,260.00 | 0 |
| D1, D2 | 7,881.10 balanced | 1,231.57 | 354.00 | 24.63 | 0 | 227.10 | 4,980.00 | 0 |
| O1, O2 | 6,000.00 balanced | 0 | 0 | 0 | 0 | 0 | 6,000.00 | 0 |

No journal is unbalanced on any firm (between 1 and 422 journals a firm).
Receivables equal customers less advances, Loyalty Payable equals the report,
commission and claims agree, on every firm. What does not come out clean:

- **Trade Payables on R1 and R2** sit 2,194.80 under the suppliers'
  outstanding report on each. Round 4 traced the same figure on R1 to the
  supplier credit `bx.py` leaves; R2 ran the same script. The credits list
  came back empty through my script this time, so that explanation is
  carried from round 4 and was not read again.
- **Purchase Price Variance.** -500.00 on N1 and -240.00 on P1 and P2 are
  rate difference claims. 443.04 on R1 is eight free pieces sent back at
  55.38 (three in round 4, five in this one); S3 is the same 443.04 less
  its 500.00 claim. -57.60 on R2 is a receipt of 24 at 60.00 cancelled
  after free goods had brought the average to 57.60: the stock leaves at
  the average and the accrual at the document's value, as the posting rules
  say. No variance was left by a unit conversion.
- **Stock**: PRCQ-56, above. GRNI of 5,760.00 on R1 and S3 and 13,940.00 on
  P1 and P2 is receipts the probes left unbilled.

## Findings

Ids continue from round 4. High = wrong money, stock or tax, or a rule that
can be bypassed; Medium = a wrong record or a broken flow with a workaround;
Low = wording or convenience. Causes are from reading the code named, not
from a debugger.

| Id | Severity | What | Firms | Where from |
| --- | --- | --- | --- | --- |
| PRCQ-58 | **High** | A draft order echoed with its lines moved keeps the offer's free goods as typed: no offer named, no claim, outside the budget and the principal's claim | S1, S2 | PRCQ-48 |
| PRCQ-59 | **High** | A per-unit commission is paid on every unit billed, whatever came back | C1, C2 | B12 |
| PRCQ-60 | Medium | A draft order saved with two lines carrying one line number loses a line and keeps a total for both | S1, S2 | generic checks |
| PRCQ-61 | Low | A bill prints an offer's free goods as they left, not less those that came back before it was raised | S1, S2 | B7 |
| PRCQ-62 | Low | Wording: refusals that still count to four places with no unit, and one that names a note that does not exist | S1, S2, R1, S3 | several |

### PRCQ-58: an echoed draft whose lines moved (High)

S1 13:49:09 and 13:58:31 IST, S2 13:51 and 13:59 (`b5.py` part d, `b5h.py`);
first seen on S1 at 13:43 (`s5a.py` part b, the free line renumbered 5). The
same on both.

Offer "buy 10 get 1" on a product with 1 BOX = 12 PIECE, paid in full by a
principal, at most 6 free units in all. Product Z5E is any other product.
Each `PUT` sends, for every line kept, exactly what `GET` returned
(`line_number`, `product_id`, `quantity`, `free_quantity`, `unit_price`,
`sales_uom_id`, `inventory_uom_id`), renumbered from 1.

| Draft | What is done | Lines before approval | Claim |
| --- | --- | --- | --- |
| A: 2 BOX | Nothing | 2 BOX; 0 + 2 PIECE free, offer named | CLAIMED, 2 |
| B: Z5E; 2 BOX; (the engine's free line) | `PUT`: line 1 left out, the other two sent as lines 1 and 2 | 2 BOX; 0 + 2 PIECE free, **no offer named** | **none** |
| C: Z5E; 24 PIECE with 2 free on the line | `PUT`: line 1 left out, the line sent as line 1 | 24 PIECE, 2 free, **no offer named** | **none** |
| D: Z5E; 24 PIECE with 2 free on the line | `PUT`: both lines as read, at their own numbers | 24 PIECE, 2 free, offer named | CLAIMED, 2 |

All four are approved, shipped and billed; 26 pieces leave each time (3,000
to 2,896 on hand). **8 free units were given. The offer reads
`free_quantity_claimed` 4.0000, `remaining_free_quantity` 2.0000.**
`POST /principal-claims/preview`: **240.00**, two lines of 2 at 120.00 (A
and D); at a cost of 60.00, 8 units are 480.00.

The same with a line inserted first (the two echoed lines sent as 2 and 3),
and with a budget of 2 already spent by another order (`b5.py`): the free
line is kept, approved (200) and shipped, where the control, echoed at its
own numbers, loses its free line because the budget is spent. Three approved
orders carried 6 free units against a budget of 2, and the two the offer
does not count shipped 26 pieces each.

**Expected:** `docs/PRICING_AND_PROMOTIONS.md`, "What an offer gave is the
server's on every later save of a sales order": "an editor may drop the
engine's lines or echo the whole read: either way the order ends with one
free line naming its offer, claimed once and counted against the budget
once." **Actual:** true only while every line keeps its number. An editor
that echoes the read and lets somebody delete or insert a line above sends
the engine's figures at new numbers, and they are taken as typed: outside
the offer's budget, its once-a-customer limit, its reports and the
principal's claim. The doc does say the line is dropped "where it comes back
at its line number"; what it promises an echoing editor does not survive
that condition. **Reach:** the desktop's order editor does not send an
offer's free figures back at all
(`desktop/lib/ui/sales/sales_order_editor_dialog.dart:574`), so this is an
API client or an import. Workaround: send no `free_quantity` for anything
the read shows with `free_promotion_id`, and leave the free-only line out.

**Suspected:** `app/sales_order/services/sales_order_service.py:2260`
(`stored = existing.get(item.line_number)` in
`_without_what_the_engine_gave`): the stored line is looked up by the
number the item now carries, so a moved line finds another line or none.
The stored free-only lines naming an offer could be matched by product
instead, and a line's own free figure by product and offer.

### PRCQ-59: a per-unit commission and a return (High)

C1 13:58:11 IST, C2 14:00:47 (`c5b.py`); the payout on C1 at 13:52:28
(`c5.py`). The same on both.

1. A rule for one salesman: `rate_type` PER_UNIT, `per_unit_amount` 2.50,
   `basis` INVOICED, on one product.
2. An order of 24 pieces of it at 100.00, delivered and billed: 2,832.00.
   `GET /commission/report`: the salesman's commission +60.00,
   `invoiced_amount` +2,832.00.
3. A sales return of 7 pieces, completed (826.00): `invoiced_amount`
   -826.00, **commission unchanged**.
4. A return of the other 17 (2,006.00): `invoiced_amount` is back where it
   started, **commission still +60.00**.

The same for 2 BOX billed by the box (1 BOX and 7 PIECE returned: 0.00 off)
and for 2 BOX billed as 24 PIECE. The control beside it, 5% of another
product on the same basis: +120.00 on the bill, **-35.00** on 7 pieces
returned.

On C1 a payout over such a bill (24 billed, 7 returned, dated yesterday) was
accrued at **386.00**, approved (Dr 5600 Commission Expense 386.00 / Cr 2400
386.00) and paid. At 2.50 for the 17 kept it is 368.50; 17.50 was paid on
goods that came back.

**Expected:** `docs/COMMISSION_FRAMEWORK.md`: commission "is earned on net
sales"; D-TER-3: a credit note, a return or a refund comes off commission.
**Actual:** a PER_UNIT rule's value base is net of credits and its quantity
is not, and only the quantity is paid on. A salesman under a per-unit rule
is paid in full for a sale that was returned in full. Workaround: none short
of an adjustment on each payout.

**Suspected:** `app/commission/services/commission_service.py:1001`
(`under_rule_quantity[key] = … + line.quantity`): the bill line's whole
quantity, beside `portion = amount * line.share / billed` at `:990`, which
is what the bill is now worth. The quantity wants the same proportion, or
the returned quantity taken off in `_lines_of` (`:1270`).

### PRCQ-60: two lines carrying one line number (Medium)

S1 14:02:35 IST, S2 14:02:42 (`dup.py`); first seen in `gg5.py`. The same on
both.

1. `POST /sales-orders`: line 1, 2 of product DU1 at 100.00; line 2, 3 of
   DU2 at 50.00. 413.00.
2. `PUT` the draft with the same two lines, **both numbered 1**: **200**.
   The answer and the read back: `grand_total` **413.0000**, and one line:
   line 1, 3 DU2, 177.00.
3. Approve: 200. 3 DU2 are reserved and nothing of DU1. Its note is 177.00.

A **new** order or quotation with two lines numbered 1 is not accepted, but
as **409 "The request conflicts with existing data. Please retry."**, the
database's unique key and not a sentence about the line; the server logs a
"Database integrity conflict" each time. A purchase order has no
`line_number` to send.

**Expected:** 422 naming the line, on both routes. **Actual:** on a save the
second item is written over the first item's row, the first product is gone
without a word, and the header keeps the total of both. The bill is raised
from the note, so the customer is billed 177.00; the order, its register row
and anything that reads the order's total say 413.00. Needs a client that
sends a repeated number; none was seen to. Workaround: save again with
distinct numbers.

**Suspected:** `app/sales_order/services/sales_order_service.py:2545` to
`:2762`: the update matches each item to `existing.get(item.line_number)`
and nothing checks that the numbers sent are distinct; the write schema
(`app/sales_order/schemas/sales_order.py:67`) checks only `ge=1`. The same
check is missing on the create path and on the quotation's.

### The Low findings

- **PRCQ-61.** S1 13:52:00 IST, S2 13:51:41 (`b5.py`, `b5x.py`, part e).
  A note of 2 BOX + 2 PIECE free; 1 BOX and 1 free piece returned off the
  note. The charged line is netted (only 1 BOX may be billed). The bill's
  free line reads `free_quantity` 2.0000 and the tax invoice prints "Free
  with QE5, 0 + 2 free, PIECE", where one of the two came back before the
  bill was raised and the offer's own count reads 1. No value moves and the
  return cap is right afterwards.
- **PRCQ-62.** (a) A supplier's bill for more than is left: "line 1 bills
  1.5000 where 1.4167 is left to bill (2.0000 received, 0.0000 on other
  bills, 0.5833 returned before billing)", to somebody who typed 18 PIECE
  (R1, S3). (b) A sales bill after a return off the note: "Line 1: 1.0000
  of the 2.0000 delivered came back before being billed, so 1.0000 is left
  to bill." (c) A credit note: "0.0000 charged, 0.0000 already credited."
  (d) A single note whose two lines of one order line add to 12 against 10
  is refused at approval with "…has 10 left to deliver of the 10 ordered.
  Cancel this note and raise one for what is left, **or cancel the other
  note first**": there is no other note. (e) The same refusal for a note of
  3 BOX counts in the stock unit: "delivers 36 PIECE where … has 12 PIECE
  left to deliver of the 48 PIECE ordered". All S1 and S2 unless said.

## Case text to correct

Round 3's and round 4's tables still stand; nothing in them was applied.
Changes, for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 4's held-back cases | Can be written as passing: a delivery note in another unit (refused by name, both ways); a draft order under an offer saved again (the box line alone with no free figure, and both lines as read: 26 reserved, one claim; a budget of 2 holds); two notes of 6 against 10 (the second refused at approval naming the first; bulk approve refuses one row); free units returned as "0 charged, 1 free" on both sides |
| New cases wanted | (1) a return typed in pieces in GSTR-1 (PIECE row 17, 1,700.00) and on the e-invoice (7 at 100.00); (2) a break "from 2 boxes" on a product sold in pieces (24 PIECE take it, 23 do not; a fixed rate of 1,080.00 a box is 90.00 a piece); (3) loose pieces returned before the bill (420.00 off the accrual, nothing to variance); (4) a claim receipt dated tomorrow |
| Hold back until fixed | An echoed order whose lines moved (PRCQ-58); a return under a per-unit commission rule (PRCQ-59) |
| 009 | State QQ's price in the case; a firm on which QQ already exists at another price gives other mixed-product figures |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **A quotation with an offer's free goods on the line, converted** (S1,
  S2): the order carries "24 PIECE, 2 free", names no offer and claims
  nothing; with the offer's budget open or spent it is approved and reserves
  26. `docs/PRICING_AND_PROMOTIONS.md` records this as the one gap left
  ("indistinguishable from typed ones, on the quotation as on the order").
  Since D-PRC-48 the order can tell them apart; the quotation cannot. The
  consequence is PRCQ-58's.
- **A full return after a rate-difference credit note credits more than was
  billed** (S1, S2): a bill of 2,832.00; a credit note of 472.00 approved;
  both boxes returned at 2,832.00. The customer is credited 3,304.00 for a
  2,832.00 bill. `docs/DATA_TRAIL_BY_OPERATION.md` says of the credit note's
  cap that "Returns are not netted against it"; the return does not net the
  credit note either. This belongs to the selling module and wants a
  decision there.
- **"0 free" on a quotation line does not refuse the offer** as it does on
  an order: a quotation's box line sent back with `free_quantity` "0.0000"
  keeps its free line, and so does its order.
- **A free figure typed on the engine's own free line is discarded
  silently**: 5 sent on the line the offer gave 2 on comes back 2.
- **A note with two lines of one order line saves over the cap** (6 and 6
  of 10) and is refused only at approval.
- **A dispatched note whose goods have all come back still counts against
  its order line**: the order cannot be delivered again for those 6.
- **An order of nothing sold and 2 free typed by hand saves at 0.00**; it
  names no offer. Whether anything limits free goods typed by hand was not
  established.
- **GSTR-1's HSN summary and the GST sales register part by a paisa** on the
  day's taxable value (119,327.61 against 119,327.60 on S1; 47,149.45
  against 47,149.44 on N1). **GSTR-3B's central and state tax part by
  paise** for supplies inside the state (4,243.47 against 4,243.43 on N1).
- **A return in another unit than its bill moves the other unit's HSN row**:
  5 PIECE back off a box bill come off the PIECE row; 1 BOX back off a bill
  typed in pieces leaves a BOX row of -1 and -1,200.00 until a box bill
  exists (N1). Documented as "true rather than tidy".
- **A draft delivery note, refused at approval, prints a delivery challan**
  headed "ORIGINAL FOR CONSIGNEE" (S1, S2). Not followed further.
- **Two price lists for one product, both active** (S2: round 4's and this
  round's): the discount list was taken over the fixed-rate list. Which of
  two lists wins was not established.
- Round 4's gaps were not driven again except where A or B covers them. The
  claim receipt dated tomorrow is closed.

## Left on the firms

- **N1 has GSTIN 29AAGCB7384J1Z3 (PAN AAGCB7384J) and its customer PC
  29AAPFU0940F1ZY.** S1 keeps the ones round 4 gave it.
- **C1: a commission payout of 386.00 for 1 to 5 October, PAID**, 17.50 of
  it on returned goods (PRCQ-59); per-unit rules on UE5, VA5, VB5, VC5 and
  5% on VD5, all ACTIVE (the same four on C2); sales and returns dated
  yesterday.
- **S1 and S2: orders shipped with free goods no offer counts** (PRCQ-58):
  two each shipped and billed, two more each shipped and not billed; one
  order whose total reads 413.00 over one line of 177.00, cancelled; a
  credit note of 472.00 approved and its bill then returned in full; claims
  RAISED on principals PR5 (120.00 each); notes dispatched and not billed
  (Y47, Y55, Z5B, Z5D); 29 orders on S1 and 25 on S2 approved, draft or part
  delivered; the approved notes that cannot ship are round 4's (5 and 4);
  products Y47 to Y55, YA, YB, YG, Z5A to Z5K, Z6F, Z6G, H000, GG5, DU1,
  DU2; price lists `Y…` and `W…` INACTIVE; **round 4's list `X…` is still
  ACTIVE on S2**; offers B47, B48, G48, Z48, F49, B51, QA5 to QK5, QE6, QF6,
  B10Y, GG5O, GG5R retired; X4K at 99.4167 boxes (S1) and 96.8334 (S2).
- **S3**: offers GY, QY, BY retired; one more order approved and shipped.
- **R1 and S3**: five more free pieces in Purchase Price Variance (276.90);
  two more receipts unbilled (GRNI 5,760.00); product NH5; purchase stages
  as found.
- **P1 and P2**: batch BP, 48 received and not billed, 12 sold from it.
- **L1**: four more customers, product LB5, 55.00 of advances on two of
  them; the scheme as the fixture set it.
- **N1, R2, L2, C2, D2, O2**: what round 4's scripts leave on a firm, and on
  R2 a supplier scheme "10 + 1" on NGP.

## Not verified

- **Nothing on screen.** The desktop was not opened. That its order editor
  does not send an offer's free figures back was read at one place in the
  source and not watched.
- **Nothing was read from the database.** That the server runs `3ee89dd1`
  was taken from the hand-over and from the fixes behaving as merged.
- **Everything ran once, in one window** (13:42 to 14:05 IST).
- **One firm where two would be better**: the fixed-rate break of PRCQ-52
  (S1; on S2 round 4's list outranked it); loyalty in another unit (L1); the
  commission payout (C1; the report on C2 too); PRCQ-55 on the purchase
  side was not driven again; the regression (one firm each, as asked).
- **The rate difference by batch** (`pm.py`) was not re-run: no fresh
  pharmacy firm.
- **PRCQ-50**: the e-invoice was read from the offline export, not from a
  registration; GSTR-3B was read for its totals only; a financial credit
  note's HSN row was not driven.
- **PRCQ-49**: twelve pairs and two triples at once, not a load test; a
  tolerance setting; two approvals of notes of different lines of one order.
- **PRCQ-58**: an import; a once-a-customer limit; whether a moved line
  also loses a typed discount was not looked at.
- **PRCQ-59**: a per-unit rule by category; a credit note in place of a
  return; a clawback on a payout already paid.
- **PRCQ-60**: the same on a delivery note, a bill and a return.
- **The claims in Gaps** were each driven but not traced to code.
