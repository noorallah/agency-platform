# Pricing, promotions, loyalty, commission, claims and the returns around them: checked through the API, round 8, 2026-10-06

The eighth pass over this module, driven the way rounds 1 to 7 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `e3c5710a`, PR #1310,
migration head `20261006_0347`), books read back through the API, nothing
read from the database, no source file changed, nothing fixed, no test suite
run, no git write, no restart and no migration.

Ids are the registered ones: round 7's PRCQ-71 to PRCQ-78 are **D-PRC-72 to
D-PRC-79**, D-PRC-71 is the purchase return capped at its supplier bill
(PR #1303), and this round's findings start at **D-PRC-80**.

**Every round 7 finding that was fixed is fixed by its original reproduction,
on two firms wherever round 7 used two.** D-PRC-71, 72, 73, 74, 76, 77, 78
and 79 are closed. D-PRC-75 is unchanged, as expected.

**The round does not close the module: it found three High, two Medium and
three Low (D-PRC-80 to D-PRC-87).**

- **In pricing proper (offers, price lists, discounts, loyalty, commission,
  claims) the round found one thing, and it is High.** Where an order line
  carries free units beside an offer's discount -- the free goods of a second
  offer, or a figure somebody typed -- the discount is spread over the
  charged and the free units alike. The principal is claimed 110.76 where
  120.00 is its half of the 240.00 given, and after the whole order comes
  back the offer's value budget still reads 18.4615 claimed (D-PRC-82).
  Nothing else new was found in pricing: commission, targets and loyalty
  count a refused return as nothing and a cancelled and re-raised one once,
  a price-list tier comes back to the paisa of its documents, and the claim
  adjustment for goods that came back is carried once.
- **Elsewhere the round found seven things.** Two High, both in buying: a
  supplier bill that a return was set against can be cancelled when the
  return was raised off the goods receipt, which leaves the supplier
  claimed 849.60 for goods no bill charges (D-PRC-80); and two purchase
  returns open at once by the two routes, completed receipt first, claim
  472.00 less than the bills and leave 72.00 of input tax unreversed
  (D-PRC-81). Two Medium: a purchase return's header charge is not counted
  on its bill, the buying twin of D-PRC-74 (D-PRC-83); the printed credit
  note of a sales return names no invoice at all (D-PRC-84). Three Low:
  D-PRC-85 to D-PRC-87.

**The regression is unchanged**: lines sold by the box (run first, on a
fresh firm), buying by the box, the rate difference claim, promotion
budgets, principal claims and the twelve cases give what they gave in round
7; every differing line is a list read in the other order or the time of
day.

## When, and on which firms

Everything was driven between **19:04 and 20:02 IST on 6 October 2026, which
is 13:34 to 14:32 UTC on the same day**. Six fixtures were built, one at a
time (N4 at 19:33; R5, L5, C5, D5 and O5 between 19:44 and 19:47); the
twenty-eight firms of rounds 4 to 7 were used again wherever a clean firm
was not needed. The server was not restarted; `/health` answered 200 before
each of the 92 script runs the runner made and at the end (seven more
runs, all read-only, were made by hand).

**No request answered 500 or 503.** The server log for the window holds
14,804 completed requests, none at 5xx, no ERROR, and five WARNING lines,
all from the background messaging and reservation passes meeting a fixture
firm in the second between its creation and its provisioning (gaps).

**Memory.** Free memory was read before every script and every build, and
this round every step waited under 1.5 GB, not only the builds. The lowest
before a build was 1,865,980 KB (O5). **The lowest reading of the round was
1,056,176 KB at 19:35:35**, with nothing of mine running: the chain was
paused from 19:35:04 to 19:37:38 (five readings under the floor) and went on
at 1,832,192 KB. Twelve reads were dropped in transit and read again by the
helper; no write was sent twice.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| S1 | `selling-firm` | `T100667G6-S` | | A: D-PRC-72, 74, 76, 77, 78, 79; B1, B2, B5, B6 (loyalty), B7, B8; D-PRC-82, 84 to 87; unchanged items |
| S2 | `selling-firm` | `T10064CYP-S` | | A: D-PRC-74, 76, 77, 78, 79; B6 (loyalty), B7; D-PRC-82, 87; unchanged items |
| N1 | `selling-firm` | `T100657VP-S` | | A: D-PRC-72, 74 with a GST number; D-PRC-73, 80, 81 against GSTR-3B; B1, B2, B5, B8 |
| R1 | `ready-firm` | `T10067V0N-R` | | A: D-PRC-71, 73; B3, B4; D-PRC-80, 81, 83 |
| S3 | `selling-firm` | `T100659Z3-S` | | A: D-PRC-71, 73; B3, B4; D-PRC-80, 81, 83 |
| C1 | `commission-firm` | `T1006MWGX-T` | | A: D-PRC-74 under commission and targets; B6 |
| C2 | `commission-firm` | `T1006DWN6-T` | | the same; D-PRC-75 |
| P1, P2 | `pharma-firm` | `T1006THK2-P`, `T1006EJV8-P` | | the batch over-pin, unchanged |
| N4 | `selling-firm` | `T1006L8H7-S` | yes | C: lines sold by the box first; cases 001, 002, 004, 009, 011; budgets, claims, the rate difference; generic checks |
| R5 | `ready-firm` | `T1006600A-R` | yes | C: buying by the box |
| L5 | `loyalty-points` | `T1006TF9V-S` | yes | C: cases 005, 010; round 3's and round 4's loyalty scripts |
| C5 | `commission-firm` | `T1006T3IE-T` | yes | C: cases 006, 007, 008 |
| D5 | `selling-invoiced` | `T1006LLKW-S` | yes | C: case 012 |
| O5 | `selling-ordered` | `T10066VCZ-S` | yes | C: case 003 |
| N2, N3, R2 to R4, L1 to L4, C3, C4, D1 to D4, O1 to O4 | | | | the migration check (N3, R4, L4) and the books |

Scripts and logs are in the scratchpad folder `pricing8`, a copy of
`pricing7` with round 7's logs under `r7`. Round 3's to round 7's scripts
were run unchanged for the regression and the unchanged items (`a22.py`,
`bx.py`, `cr.py`, `a24.py`, `a27.py`, `a28.py`, `a35.py`, the case scripts,
`gg5.py`, `g.py`, `n4g.py`, `dup6.py`, `u6.py`, `s5a.py`, `m5.py`,
`adv.py`). The new ones are `s8.py` with `s8h.py` (D-PRC-72, 74, 77, 79, B1,
B2, B5, B8), `p8.py` (D-PRC-71, 73, B3, B4, D-PRC-80, 81, 83), `i8.py`
(D-PRC-76), `q8.py` (D-PRC-78), `c8.py` (commission, targets, loyalty),
`o8.py` (B7, D-PRC-82), `m8.py` (the migration check) and four read-only
`peek` scripts. "The same on both" means the two logs were read side by
side and differed in document numbers alone.

What went wrong on my side, so the record is straight:

- **My first "Record Payment after a spill" did not reach its point.** A
  return typed on a bill's own line cannot exceed what that line billed, so
  18 PIECE on a line of 1 BOX is refused; a spill happens only when the
  named line's units already went back off the receipt. Part `d` of `p8.py`
  was rewritten that way after its first run on R1, which left one supplier
  there with a payment of 424.80 and 6 pieces returned; S3 ran the
  rewritten part twice.
- **Several "want" figures in my logs are wrong and are not what this
  report states**: the b4 and z1 scenarios of `p8.py` (a refused line I had
  expected to be accepted, and the reverse), and the GSTR-1 check of
  `s8h.py` on a customer with no GSTIN (S1's and S2's B8H, C01), which
  reads `cdnr` alone and so prints DIFFER where nothing differs; N1 carries
  that check.
- **`o8.py` ran twice on S2.** Its first run there completed while S1's
  stopped on a principal code already taken (PR8); after the code was
  changed the chain ran S2 again, with the two offers already retired, so
  five more orders of 24 went out there at full price (two of them
  returned) and the first run's log was overwritten. S2's figures in this
  report for D-PRC-82 are read back from the firm (the claims and the
  offers' claim rows), and its control (`o8.py` part c) ran cleanly.
- **One line of a here-document was sent to the shell** (a `print` that
  edited nothing). Every script edit was made with the file tool.
- **`a22.py`, run first, makes product QQ at 100.00** on the fresh firm, so
  `setqq.py` was run before `c911.py` and case 009's mixed-product lines
  read 460.00 as in rounds 5 and 7.

## A. The findings of round 7

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| D-PRC-71 | **Fixed** | R1, S3 | Each on a fresh supplier, 2 BOX at 720.00 received and billed 1,699.20. `unit_price` 900: **422 at save**, off the bill and off the receipt alike: "Line 1: the return claims 1800.00 before tax for goods that PI-… billed at 1440.00, and they are still worth 1440.00 on it. No more can be claimed from a supplier than they billed. Lower the price or the charge to the bill's, or leave them out and the line claims what the bill is still worth." Line `charges_amount` 500: the same, 1940.00 against 1440.00, by both routes. Header `additional_charges` 500: "This return claims 500.00 of additional charges, and PI-… charged 0.00 of them, 0.00 already claimed back by other returns. … Lower the charges to 0.00 or less.", by both routes. **720.01: refused** (1440.02 against 1440.00), by both routes. 900 on one of the two boxes: 900.00 against 720.00. **720.00 exactly: 1,699.20**, Trade Payables moves 0.00 in all. **600.00: 1,416.00**, 283.20 still owed. **Received at 720.00 a box and billed at 648.00** (the 100 against 90): both boxes off the receipt with nothing typed claim **1,529.28**, not refused (`bill_discount_amount` 144.00); with the receipt's own 720.00 typed: the same 1,529.28, not refused. **A part-billed receipt** (4 BOX received, 2 billed): 3 BOX off the receipt claim 849.60 for the one billed box (Dr 2100 849.60, Dr 2300 1,440.00 / Cr 1200 2,160.00, tax 129.60); typed at 900.00: refused. **7 PIECE of the box line, nothing typed: 495.60** by either route, not refused and not trimmed. **PUT of a draft** to 900.00, and to a header charge of 1.00: refused in the same words; the draft keeps 1,699.20. **`purchase-returns/import`** with a good record and one at 900.00: 422 "Record 2 of 2: Line 1: the return claims 900.00 … Nothing was imported."; 61 returns before and after. **A bill with a header charge of 100.00** (1,799.20): 1 BOX and 60.00: 909.60; the other box and 60.00 again: "… charged 100.00 of them, 60.00 already claimed back by other returns. … Lower the charges to 40.00 or less."; the first return cancelled, then both boxes and the whole 100.00: 1,799.20, Trade Payables 0.00 in all. (What the bill then reads: D-PRC-83.) |
| D-PRC-72 | **Fixed** | S1, N1 | One note of 2 BOX in two bills of 1,416.00. A box off the note, then a box on the first bill's own line: **422**, "Line 1: SI-… line 1 billed 1 BOX, and 1 BOX of that has already come back and been credited on it, so 0 BOX is left to return against this bill where the return brings back 1 BOX. Raise the return off DN-… instead, and the goods are credited on the bill that still carries them." (deliberate, confirmed; the control with no credit note is refused the same way). The same box then off the note, or on the second bill's own line: with the credit note of 472.00 on the **second** bill 1,416.00 then **944.00**; on the **first** 944.00 then **1,416.00**; raised **after** the return off the note 1,416.00 then 944.00; none 1,416.00 and 1,416.00. **Credited 2,832.00 against 2,832.00 in all eight orders** (the credit note among it), both bills leave Record Receipt. **Stability.** A return off the note approved, a return on the first bill's line completed, then the first completed: refused, "… these goods are now worth 800.00 before tax where the return credits 1200.00. … Cancel this return and raise it again …"; cancelled and raised again: 944.00; 2,832.00 in all (with no credit note it completes at 1,416.00). A completed return cancelled (Dr 1100 1,416.00 back, the bill reads 1,416.00 again), a box on the first bill's line (1,416.00), the return raised again (944.00), cancelled and raised once more (944.00): 2,832.00. **A backdated bill**: a note of 4 BOX, bill A of 1 today, a box off the note (unbilled: credits nothing), bill B of 2 dated the 5th, a box off the note (1,416.00, set on B), a box on A's line, 2 BOX on B's line refused, 1 BOX on B's line: 4,248.00 against 4,248.00. A draft bill dated the 5th beside an approved one: the box off the note is the draft's and credits nothing, and the draft is refused at approval by name. **A note of 6 BOX in three bills** (1,416.00, 2,832.00, 4,248.00), credit note 472.00 on the second: 18 PIECE off the note 2,006.00, 1 BOX on bill 3's line 1,416.00, 30 PIECE off the note 3,186.00, 1 PIECE on bill 2's line refused, 13 PIECE off the note refused, the last 12 PIECE 1,416.00: **8,496.00 against 8,496.00**. After each: 1100 and the customer's account move alike, the statement closes on the account, GSTR-1 `cdnr` rows and the journals' credits to 1100 equal what was credited, and the bills' outstanding sum to what is owed |
| D-PRC-73 | **Fixed** for every order completed one at a time; two returns open at once by two routes is D-PRC-81 | R1, S3; GSTR-3B on N1 | A receipt of 2 BOX billed 849.60 and 849.60. Debit note 472.00 on the **second**, 1 BOX off the receipt **849.60**, then 1 BOX off the first bill's own line **377.60** (`bill_discount_amount` 400.00): **1,699.20 claimed against 1,699.20**, Trade Payables 0.00 in all. The mirror, debit note on the **first**: 377.60 then 849.60. **GSTR-3B (N1): eligible ITC +259.20, ITC reversed +259.20** in both, and +777.60 each with three bills. **Three bills of 1, 2 and 3 BOX** (5,097.60), debit note on the second: 2 BOX off the receipt 1,463.20, 1 BOX off bill 1's line 613.60, 18 PIECE off bill 3's line 1,274.40, 19 PIECE off the receipt refused, the last 18 PIECE 1,274.40: 0.00 in all. **Pieces across a spill**: 6 PIECE off the receipt 424.80, 12 PIECE on the first bill's line 613.60 (six its own, six on the second bill at what it is still worth), 7 PIECE refused, the last 6 PIECE 188.80: 0.00 in all. **A debit note of 1.00 on each bill after mixed routes**: refused on all of them, "… 720.00 billed, 400.00 already claimed, 320.00 already returned." **A completed return cancelled and raised again**: 849.60 off the receipt cancelled, 849.60 on the first bill's line, 377.60 off the receipt: 0.00. **Drafts by both routes**: completed bill route first, right (377.60 then 849.60); receipt route first, **472.00 short: D-PRC-81**. **Cancelling a supplier bill a receipt-route return was placed on: it cancels: D-PRC-80.** **Round 7's over-claims** on R1, S3 and N1 stand as the migration found them (suppliers V704 and V6A 472.00 in debit, V707 and V708 424.80, V709 and V6B 590.00, V710 500.00, V711 0.02; V704 on N1 472.00), and a debit note of 1.00 or a return of 1 PIECE on any of those bills is refused |
| D-PRC-74 | **Fixed** | S1, S2, N1; C1, C2 | A bill of 2,932.00 with 100.00 of `additional_charges`; 1 BOX and 60.00 back: the bill reads `allocated_amount` 1,476.00, `outstanding_amount` **1,456.00**; the other box and 40.00: **the bill leaves Record Receipt**, the customer reads 0.00, the ageing lists nothing for it, and a receipt of 100.00 allocated to it is **422** "An allocated invoice does not belong to this party, is not approved, or is already settled in full." **A note in two bills where only the first charged 100.00**: both boxes off the note with 100.00: 2,932.00, both bills gone; 1 BOX off the note with 100.00 then 1 BOX with 1.00: "This return credits 1.00 of additional charges, and SI-…, SI-… charged 100.00 of them, 100.00 already given back by other returns. …"; a box on the second bill's line with 50.00: "… SI-… charged 0.00 of them …". **Two bills charging 100.00 and 50.00**, both boxes off the note with 90.00: the bills read **40.00 and 20.00** outstanding (shared 60.00 and 30.00). On N1 the journals, the statement, GSTR-1 and the bills agree in every case. **Commission and targets (C1, C2)**: a bill of 2,932.00 earns 120.00 (5% of 2,400.00) and counts 2,932.00 to the target; 12 back with 60.00: -60.41 and -1,476.00; the other 12 with 40.00: -59.59 and -1,456.00; **0.00 and 0.00 in all**. On collected money (4%): paid in full +96.00, all back with the 100.00 -96.00 |
| D-PRC-75 | **Not fixed, as expected** | C2 | Customer B7F owes 826.00 and holds 826.00: a refund naming the bill 422, `allocate` from either receipt 422 "… has only 0.00 left unapplied." |
| D-PRC-76 | **Fixed** | S1, S2 | Eleven routes driven (the nine documents, `products/import`, `inventory/opening-stock/import`), 44 requests a firm: **no 500**. `sales-orders/import`: two lines numbered 1 in the second order: 422 "Record 2 of 2: Lines 1 and 2 of the request are both numbered 1. Number each line once." with `details` naming `records.1.lines`; no customer and no lines: "Record 1 of 1: customer_id: Field required (3 more problems in the details.)"; a quantity "many": "Record 1 of 1: lines[1].quantity: Input should be a valid decimal"; an unknown field: "Record 1 of 1: colour: Extra inputs are not permitted"; no records: "records: List should have at least 1 item …"; text that is not JSON: "The import is not valid JSON, so none of it was read. Check the file is the one exported for this import."; 401 orders before and after on S1. A record the schema refuses, text that is not JSON and two lines numbered 1 on each of the other routes: 422 in the same shape (`sales-invoices/import` answers 422 "The request validation failed." as before; `inventory/opening-stock/import` names the field, its payload being one document). The server log gains no error |
| D-PRC-77 | **Fixed** | S1, S2 | A draft bill of 2 BOX, a box back off the note: approval refused by name (1 BOX left to bill), **the draft cancels (200)**, and the box left is billed afresh, 1,416.00. A box back first and a draft of the box left: cancels. **Two approved bills and a completed return off the note**: the second bill cancels (200) and its box is billed again; **the first is refused**: "SI-… cannot be cancelled while it has sales return SR-…. Reverse or cancel those first." The same with the return only approved. A return on the second bill's own line: the second is refused, the first cancels |
| D-PRC-78 | **Fixed** | S1, S2 | Offer "buy 10 get 1". A quotation of 2 BOX with `free_quantity` "0": **one line**, `free_goods_refused` true, no offer named; it prints the box line alone; its order has the box line alone, 24 reserved, no claim. Nothing typed (the control): 0 + 2 PIECE free, named, printed "Free with Q8Q, 0 + 2 free, PIECE", order reserves 26, claim 2. `free_quantity` "1" typed: "2 + 1 free BOX", no offer named, no engine line, the order reserves 36, no claim. A saved quotation with the engine's free line saved again with "0" on the box line: the free line goes, `free_goods_refused` true, and stays so when saved as read. 24 PIECE with "0" and with "5": nothing free, and 5 free with no offer named. (A quarter of a box typed free: D-PRC-87) |
| D-PRC-79 | **Fixed**; a paisa a document remains on the account | S1, S2 | A bill of 2 BOX at 1,200.00 returned as 7, 7 (typed at 100.00), 7 and 3 PIECE: 826.00, 826.00, 826.00, 354.00: **2,832.00, the bill leaves Record Receipt**; the same with nothing typed. **A box at 100.00 (118.00) returned as three fours**: 39.3333, 39.3333, 39.3334: the documents total 118.0000 and the bill leaves Record Receipt; the journals credit 39.33 three times, **117.99: the customer's account ends 0.01 in debit with no bill behind it**. As 5, 5 and 2 pieces: 49.17, 49.17, 19.67, **118.01: the account ends 0.01 in credit**. The price-list sale of B7 leaves the same paisa (bills of 831.86 and 831.86, returns of 369.72, 831.86 and 462.15: 0.01 held by the customer) |

**The migrations.** Read before this round touched them, S3, C1 and C2, and
at the end N3, R4 and L4, give round 7's closing figures to the paisa:

| Firm | 1100 = customers less advances | Bills in Record Receipt | Ageing total | 2100 = bills outstanding less supplier credits |
| --- | --- | --- | --- | --- |
| S3 | 7,761.85 | 7,761.85 (15 bills) | 7,761.85 | 45,472.78 (59,354.00 less 13,881.22) |
| C1 | 47,455.67 (49,933.67 less 2,478.00) | 51,585.67 (29 bills) | 51,585.67, of it `unapplied_credits` 1,652.00 | 0 |
| C2 | 43,679.67 (46,157.67 less 2,478.00) | 46,157.67 (27 bills) | 46,157.67 | 0 |
| N3 | 58,636.48 | 58,636.48 (58 bills) | 58,636.48 | 29,618.00 |
| R4 | 1,270.00 (1,770.00 less 500.00) | 1,770.00 (3 bills) | 1,770.00 | 18,195.60 (20,390.40 less 2,194.80) |
| L4 | 16,333.02 | 16,333.02 (16 bills) | 16,333.02 | 28,320.00 |

No bill reads a negative outstanding on any of them. Bills and accounts
differ on one customer of the six: C1's C4, whose bills read 1,652.00 more
than the account, shown by the ageing as `unapplied_credits`; its returns
of 5 October stand on bills that were paid before them. On S1 and N1, read
after this round's work, the same line reads 3,786.00 and 3,214.00
(customers PC and PD); every bill this round made for them reads what its
scenario left, so the difference is older, round 7's over-credits of
944.00 a firm among it. **Round 7 recorded no figure per bill, so whether
those three lines read as they did before the migrations cannot be said;
the firm totals do.**

Left on purpose, and unchanged (one line each, not re-reported):

| Id | Firms | What was seen |
| --- | --- | --- |
| D-PRC-53 | S1, S2 | An order and a quotation of 2 naming no unit on a product sold by the BOX: 2 pieces, 236.00 |
| D-PRC-55 | S1, S2 | A draft bill of 7 PIECE reads 0.5833; sent back as read: 422 "PIECE is counted in whole numbers, so 0.5833 PIECE cannot be entered."; sent as 7 PIECE: 826.00 |
| D-PRC-56 | S1, S2, R1, S3, P1, P2 | Valuation against the stock account: **0.02 on S1 (0.01 in round 7), 0.02 on S2, 0.04 on R1 and S3, 0.02 on P1 and P2**; 0.00 on the other twenty-eight |
| Batch over-pin | P1, P2 | 2 BOX (24 pieces) pinned to a batch with none left: approved, 24 reserved |
| 419.98 | S1, S2 | 7 PIECE of X4K leave 0.5833 of a box: Dr 5200 419.98 / Cr 1200 419.98 |

## B. The nine probes

| No | Probe | Verdict |
| --- | --- | --- |
| 1 | A return on a bill's own line after part of that line came back off the note | **Works.** Credited for what is left, refused beyond it. The figures are right in BOX; a quantity typed in PIECE is answered in fractions of a BOX (**D-PRC-86, Low**). S1, N1 |
| 2 | `sales-returns/import` naming a bill line whose units are back | **422 with the single save's message, nothing written.** In a file of two it does not say which record (**D-PRC-85, Low**). S1, N1 |
| 3 | A supplier bill line worth nothing, returned | **Works.** A line billed at 0.00 and free goods go back at 0.00, not refused; a price typed above 0.00 is refused. An opening supplier bill has no lines and cannot be returned against. R1, S3 |
| 4 | Record Payment after a bill-route return that spilled | **The supplier's total is right.** Per bill the spilled unit's value sits on the bill that was named, and the other bill can be paid in full while a credit stands (round 7's gap, unchanged). R1, S3 |
| 5 | Credit note, header charge and another unit on a note billed in three | **Works.** 8,596.00 credited against 8,596.00, every over-step refused by name. S1, N1 |
| 6 | Commission, targets and loyalty after the refusal, and after a cancel and re-raise | **Works.** Nothing counted for the refused return; the cancelled one given back and counted once. C1, C2; S1, S2 |
| 7 | An offer's discount and free goods, billed in two, returned off the note | **The free-unit budget comes back whole and the adjustment is carried once. The value budget does not come back whole, and the principal is under-claimed: D-PRC-82 (High).** S1, S2 |
| 8 | The print of a credit note for a return placed across two bills | **It names no invoice**, and neither does one raised on a bill's own line: **D-PRC-84 (Medium).** GSTR-1 names the first bill of the two. S1, N1 |
| 9 | Anything else | D-PRC-80, 81 and 83 (buying), D-PRC-87 (quotations), found on the way through A |

**B1, what was read (S1, N1, the same on both).** A note of 4 BOX billed A
and B, 2 BOX each (2,832.00 and 2,832.00). 1 BOX off the note: 1,416.00, set
on A. On A's own line: 2 BOX: "… billed 2 BOX, and 1 BOX of that has
already come back and been credited on it, so 1 BOX is left to return
against this bill where the return brings back 2 BOX. …"; 13 PIECE: "… so 1
BOX is left … where the return brings back 1.0833 BOX."; 7 PIECE: 826.00;
6 PIECE: "… 1.5833 BOX of that has already come back …, so 0.4167 BOX is
left … where the return brings back 0.5 BOX."; 5 PIECE: 590.00. A is gone
from Record Receipt, B reads 2,832.00. Then B2, then B's two boxes: 5,664.00
credited against 5,664.00.

**B2.** `POST /sales-returns/import` (multipart, `format` json), one record
naming A's line for 1 BOX: 422 "Line 1: SI-… line 1 billed 2 BOX, and 2 BOX
of that has already come back and been credited on it, so 0 BOX is left to
return against this bill where the return brings back 1 BOX. Raise the
return off DN-… instead, …". A good record on B's line followed by that
one: the same 422, the same words, 177 returns before and after on S1. The
good record alone: 201, a draft of 1,416.00, completed.

**B3, what was read (R1, S3).** An order of 10 PIECE at 60.00 and a line of
4 PIECE at 0.00, received and billed 708.00. 2 PIECE of the 0.00 line off
the bill: the return reads 0.00, completes, and the stock leaves at its
average (Cr 1200 117.09 / Dr 5400 117.09 on R1); 1 PIECE off the receipt:
the same; 1 PIECE typed at 0.01: "Line 1: the return claims 0.01 before tax
for goods that PI-… billed at 0.00 …"; 2 PIECE where 1 is left: refused.
Trade Payables stays at the bill's 708.00. **Free goods**: 10 PIECE with 2
free received; a bill line stating the free units is refused ("Free goods
are the goods receipt's. A bill line naming a receipt cannot state its
own."); billed 708.00; a free piece off the **bill**: refused, "free goods
go back off the goods receipt that brought them in"; off the **receipt**: 1
free at 0.00 (twice, once with 60.00 typed, which is not used), 3 free
where 2 were given refused. `VendorOpeningBillImportRow` is a reference,
dates, an amount and a narration.

**B4, what was read (R1, S3).** Two bills of 2 BOX (1,699.20 each). 1 BOX
off the receipt: 849.60, set on the first bill. 2 BOX on the first bill's
own line: 1,699.20, one box its own and one valued on the second bill.
Three of four boxes are back and 849.60 is owed: the statement, the
payables report (`credits` -849.60, `total` 849.60) and Trade Payables say
so. In Record Payment the first bill is gone, **the second reads
`allocated` 0.00, `outstanding` 1,699.20**, and a supplier credit of 849.60
stands. A payment of 0.01 on the first bill: 422. **A payment of 1,699.20
on the second: 201**, the supplier 849.60 in debit (reversed); 849.61: 201
(reversed); 849.60: 201, then the credit applied to the second bill (422 on
the first, 200 on the second): 0.00 everywhere. The supplier ageing reads
1,699.20 before any payment.

**B5, what was read (S1, N1).** A note of 6 BOX billed 2,832.00, 2,932.00
(100.00 of header charges) and 2,832.00; credit note 472.00 on the first.
30 PIECE off the note with 50.00: 3,118.00 (`bill_discount_amount` 400.00;
the 50.00 goes to the second bill, which reads 758.00 allocated). 1 BOX on
bill 3's line with 10.00: refused (bill 3 charged none); without: 1,416.00.
18 PIECE on bill 2's line with 60.00: "… Lower the charges to 50.00 or
less."; with 50.00: 2,174.00, bill 2 gone. 7 PIECE off the note at 100.01:
"… credits 700.07 before tax for goods that SI-… billed at 700.00 …"; 7
PIECE: 826.00; 6 PIECE where 5 are left: refused; the last 5 PIECE on bill
3's line: 590.00. **8,596.00 against 8,596.00**; a credit note of 1.00
afterwards: "… 2400.00 charged, 0.00 already credited, 2400.00 already
returned."

**B6, what was read.** C1, C2: a note of 24 billed 12 and 12 (+120.00,
+2,832.00 invoiced, +2,832.00 to the target). 12 off the note: -60.00,
-1,416.00, -1,416.00. 12 on the first bill's line: refused, **0.00, 0.00,
0.00**. The first return cancelled: +60.00, +1,416.00, +1,416.00; raised
again: -60.00; the other 12: -60.00; nothing left over all. S1, S2 (a fresh
customer): two bills +56.64 points; a box off the note -28.32; the refused
return 0; the cancel +28.32; raised again -28.32; the other box -28.32; 0
in all, Loyalty Payable 0.00.

**B7, what was read (S1, S2).** Two offers on a new product at 100.00, cost
60.00, both half paid by a principal: 10% with a value budget of 1,000.00,
and buy 10 get 1 with a budget of 10 free units. An order of 24: discount
240.00, 2 free; billed 12 and 12 (1,274.40 each, 1 free on each).

| Step | Seen | Wanted |
| --- | --- | --- |
| Claim preview after the sale | scheme **55.38 a bill** and 60.00 for the 2 free: **170.76** | 60.00 a bill and 60.00: 180.00 |
| All 24 back off the note, then the 2 free | 2,548.80 credited against 2,548.80; stock back whole; **free units claimed 0, 10 left** | the same |
| The value budget after it | **18.4615 claimed, 981.5385 left**; 36.9230 after a second order came back | 0 claimed, 1,000.00 left |
| Preview after it came back | nothing to claim | the same |
| A sale claimed (170.76), then returned | nothing new; `adjustments_carried_forward` 170.76; raising refused by name | the same, at 180.00 |
| The next sale | 170.76 new less 170.76 carried: 0.00 | |
| A further sale, claimed | 341.52 new less 170.76: **170.76**, with three negative lines naming the first claim | |
| Preview after that claim | nothing new, **nothing carried** | the same |

24 and the 2 free in one return line is refused by the schema ("Restock,
damaged and scrap quantities must add up to the returned quantity (24).");
the free units went back in a return of their own. The control is in
D-PRC-82. **A price-list tier** (18 DET to C01, 6.75%, 1,663.7292) billed 9
and 9 and returned as 4 off the note, 9 on the second bill's line, 6 on the
first refused, 5 off the note: 369.7176, 831.8646, 462.1470, the documents'
total exactly; the paisa is in A, D-PRC-79.

**B8, what was read (S1, N1).** One note in two bills, both boxes back off
the note in one return of 2,832.00. `GET /sales-returns/{id}/print`: "CREDIT
NOTE … Credit note no. SR-… Credit note date 06 Oct 2026 Reason Not wanted
CREDITED TO … 1 Z8R … 2 BOX 1,200.00 … 2,832.00 …". Neither bill's number
is in it, nor the note's. A return on the second bill's own line prints the
same way. GSTR-1 `cdnr` gives the return one row, `against_invoice` the
first bill, 2,400.00 and 432.00.

## C. Regression

**Lines sold by the box (N4, fresh, run first; `a22.py` unchanged, against
round 7's log).** Nothing differing, 167 lines.

**Buying by the box (R5, fresh; `bx.py` unchanged).** Nothing differing, 239
lines.

**The rate difference claim (N4; `cr.py` unchanged).** Nothing differing, 76
lines. By batch (`pm.py`): not driven; no fresh pharmacy firm.

**Promotion budgets and principal claims with free goods (N4; `a27.py`,
`a28.py` unchanged).** The same figures. The differing lines are two
receipts at the same instant landing in the other order (one 201 and one
422 either way) and the offers `c911.py` makes, which ran before `a28.py`
this round.

**Round 3's own scripts (N4).** `a24.py` and `a35.py`: nothing differing.

| Case | Firm | Verdict | Difference from round 7 |
| --- | --- | --- | --- |
| 001, 002, 004 | N4 | **Pass** | None; two lists read in the other order |
| 003 | O5 | **Pass** | None |
| 005 | L5 | **Pass**, text wrong in one figure as before | None |
| 006 | C5 | **Case text wrong, product right**, as before | None |
| 007 | C5 | **Not runnable as written**, as before; the flow passes | None |
| 008 | C5 | **Pass** | None |
| 009, 011 | N4 | **Pass** | None beyond the offers present when it ran; QQ is 100.00 here, 460.00 as in round 7 |
| 010 | L5 | **Pass** | The quotation raised "now" reads 9.25% from the price list where round 7 read the offer's 5%: it ran at 19:53, outside the offer's 16:00 to 18:00 window, and at 17:33 last round |
| 012 | D5 | **Pass** | None; the print is 47 bytes longer |

The per-unit commission (C5, `cm.py`): 60.00 three ways, as before.

**Generic checks.** `gg5.py`, 69 requests on N4 (other firm S1, buying R5);
round 4's `n4g.py` (N4, S2, R5) and round 2's `g.py` (N4, S2, L5);
`dup6.py`, 17 requests on each of S1 and S2; the 44 import requests a firm
of `i8.py`. **All refused cleanly and nothing at 500.** No answer differs
from round 7.

**The books at the end, all thirty-four firms.** Every trial balance
balances; no journal is unbalanced (between 1 and 1,481 journals a firm).

| Firm | Trial balance | 1100 = customers less advances | 2100 = bills outstanding less supplier credits | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 10,529,927.84 | 254,254.62 | 29,063.40 | 5,255.98 | 0 | 581.52 | 9,860,420.08 against **9,860,420.10** |
| S2 | 9,114,235.37 | 191,551.41 | 29,063.40 | 3,754.29 | 0 | 526.06 | 8,690,200.10 against **8,690,200.12** |
| S3 | 510,436.78 | 7,761.85 | 67,207.20 | 155.23 | 0 | 63.54 | 482,572.81 against **482,572.77** |
| N1 | 2,328,574.93 | 84,295.13 | 29,923.62 | 1,888.68 | 0 | 229.40 | 2,019,982.27 |
| N2 | 791,785.44 | 51,807.31 | 29,618.00 | 1,036.13 | 0 | 109.40 | 702,682.27 |
| N3, N4 | 840,751.20 | 58,636.48 | 29,618.00 | 1,172.72 | 0 | 109.40 | 736,402.27 |
| R1 | 73,409.08 | 1,270.00 | 57,484.00 | 0 | 0 | 0 | 61,440.46 against **61,440.42** |
| R2 to R5 | 20,023.20 | 1,270.00 | 18,195.60 | 0 | 0 | 0 | 14,577.60 |
| P1, P2 | 40,447.20 | 24,287.20 | 0 | 0 | 0 | 240.00 | 3,157.67 against **3,157.69** |
| L1 | 184,506.27 | 20,235.02 | 28,320.00 | 622.44 | 0 | 0 | 137,820.00 |
| L2 to L5 | 54,260.67 | 16,333.02 | 28,320.00 | 588.84 | 0 | 0 | 19,860.00 |
| C1 | 694,176.50 | 44,523.67 | 0 | 0 | 187.50 | 0 | 523,140.00 |
| C2 | 623,124.00 | 40,747.67 | 0 | 0 | 85.00 | 0 | 467,640.00 |
| C3 to C5 | 128,876.00 | 8,496.00 | 0 | 0 | 0.00 | 0 | 92,880.00 |
| D1 to D5 | 7,881.10 | 1,231.57 | 354.00 | 24.63 | 0 | 227.10 | 4,980.00 |
| O1 to O5 | 6,000.00 | 0 | 0 | 0 | 0 | 0 | 6,000.00 |

Receivables, payables net of supplier credits, Loyalty Payable, commission
and claims agree with their sub-ledgers on every firm; the payables
report's total equals account 2100 on every firm. What does not come out
clean is D-PRC-56 (above) and what the findings left, which the books carry
faithfully: one supplier a firm on R1, S3 and N1 left 849.60 in debit by
D-PRC-80's second row (one on R1 and two on S3 more read 849.60 in debit
rightly, B4's last box returned after its bill was paid; a debit note of
1.18 stands on one supplier a firm) and 472.00 still owed to one supplier
a firm on R1, S3 and N1 for goods all returned (D-PRC-81); the open claims of
D-PRC-82 on S1 and S2, 170.76 each where 180.00 was due; round 7's
over-claims as they were. Advances held: 5,410.00 on each of C1 and C2
(2,478.00 from round 7 and one more return on a paid bill of 2,932.00,
D-PRC-75), 500.00 on R1 to R5, 110.00 on L1, 0.01 on S1 and 0.02 on S2 (the
paisa of D-PRC-79). Purchase Price Variance: -1,941.48 on R1 and -2,471.56
on S3; -901.00 on N1; -500.00 on N2 to N4; -57.60 on R2 to R5; -240.00 on
P1 and P2.

## Findings

Ids continue from D-PRC-79. High = wrong money, tax or stock, or a control
that can be bypassed; Medium = wrong behaviour with a workaround; Low =
wording, paisa, cosmetics. Causes are from reading the code named, not from
a debugger.

| Id | Severity | Module | What | Firms | Where from |
| --- | --- | --- | --- | --- | --- |
| D-PRC-80 | **High** | Buying | A supplier bill that a return was set against cancels when the return was raised off the goods receipt, or named another bill and spilled onto it. The claim stands with no bill under it: 849.60 claimed for goods no bill charges | R1, S3, N1 | A, D-PRC-73 |
| D-PRC-81 | **High** | Buying | Two purchase returns open at once, one off the receipt and one on a bill's own line, with a debit note on the other bill: completed receipt first, 1,227.20 is claimed against 1,699.20 with every box back, and 72.00 of input tax is not reversed | R1, S3, N1 | A, D-PRC-73 |
| D-PRC-82 | **High** | Pricing (offers, claims) | An offer's discount on a line that also carries free units is spread over the charged and the free units: the principal is claimed 110.76 of 120.00, and a returned order leaves 18.4615 of 240.00 claimed on the offer's budget | S1, S2 | B7 |
| D-PRC-83 | Medium | Buying (what a bill owes) | A purchase return's header `additional_charges` are not counted on its bill: a bill returned in full reads 100.00 outstanding beside a supplier credit of 100.00 | R1, S3 | A, D-PRC-71 |
| D-PRC-84 | Medium | Selling (print) | The printed credit note of a sales return names no invoice, whichever route raised it | S1, N1 | B8 |
| D-PRC-85 | Low | Selling | A return the service refuses inside `sales-returns/import` is not named by its record | S1, N1 | B2 |
| D-PRC-86 | Low | Selling | The refusal for a bill line whose units are partly back answers a quantity typed in PIECE in fractions of a BOX | S1, N1 | B1 |
| D-PRC-87 | Low | Selling (quotations) | A quotation takes a quarter of a BOX typed free and prints it; its order cannot be made | S1, S2 | A, D-PRC-78 |

### D-PRC-80: a supplier bill cancels under a return that was set against it (High, buying)

R1 19:22 and 19:26 IST (`p8.py` parts s and x), S3 19:24 and 19:27, N1 19:28.
The same on all three.

A fresh supplier each time. 2 BOX at 720.00 received; two bills of 1 BOX
(849.60 and 849.60); no debit note.

| Then | Then | Seen | Right |
| --- | --- | --- | --- |
| 1 BOX returned off the **receipt**: 849.60, set on the first bill | `POST /purchase-invoices/{first}/cancel`: **200, CANCELLED** | Trade Payables for the supplier **0.00**: the second bill reads 849.60 outstanding beside a supplier credit of 849.60, and `POST /payments/supplier-credits/{return}/apply` to the second bill answers 200, so the bill is settled without money. Accounts over it all: 2300 +720.00, 1200 one box, input tax 0.00. **GSTR-3B (N1): eligible +129.60, reversed +129.60** | One box is kept and billed: 849.60 owed, 129.60 of input tax held, nothing in Goods Received Not Invoiced |
| 1 BOX off the receipt (on the first bill), then 1 BOX on the **first bill's own line** (849.60, set on the second) | `POST /purchase-invoices/{second}/cancel`: **200, CANCELLED** | Trade Payables **849.60 in debit**; the statement closes at -849.60; a supplier credit of 849.60; 2300 +720.00; **GSTR-3B (N1): eligible +129.60, reversed +259.20, net -129.60** | Both boxes are back against one live bill: 0.00 |
| 1 BOX on the first bill's own line (the control) | cancel the first bill | **422** "PI-… cannot be cancelled while it has purchase return PR-…. Reverse or cancel those first." | as seen |

After the first row the receipt's box can be billed again (a bill of 849.60
was approved on R1 and S3), which is how a wrongly keyed bill is corrected
and brings the books back; nothing asks for it, and the credit can be spent
in the meantime.

**Expected:** `docs/PURCHASE_FRAMEWORK.md`: "No more is claimed from a
supplier than they billed", and the selling side's rule for the same
position (`docs/SALES_CHAIN_RULES.md`, D-PRC-77): a bill is held from
cancelling by "a completed return off the note that was placed on this
bill". **Actual:** the guard reads only returns whose own source document
is the bill. Since D-PRC-73 the units and the value of a return off the
receipt, and of a return that named another bill, are stored against the
bill they fell on (`purchase_return_bill_placements`); the cancel does not
ask that table. Workaround: cancel the return first, or enter the bill
again at once.

**Suspected:** `app/purchase_invoice/services/purchase_invoice_service.py:3983`
to `:3998` (the blockers: `PurchaseReturnSource.source_document_type ==
"PURCHASE_INVOICE"` and `source_document_id == row.id`); the stored
placements are read in `app/purchase_return/billing.py:230` (`_placed`).

### D-PRC-81: two returns open by two routes, completed receipt first (High, buying)

R1 19:21 IST (`p8.py` part s, scenario s1), S3 19:24, N1 19:28. The same on
all three.

1. 2 BOX at 720.00 received; bills of 849.60 and 849.60; `POST /debit-notes`
   on the **second**, 400.00: 472.00, approved.
2. R1: 1 BOX off the **receipt**, saved and approved: 849.60.
3. R2: 1 BOX on the **first bill's own line**, saved and approved: **377.60**
   (`bill_discount_amount` 400.00: it is valued on the second bill, R1
   being taken to hold the first).
4. `POST /purchase-returns/{R1}/complete`: **422** "Line 1: The supplier's
   bill for GRN-… has had a debit note approved since this return was
   saved, and these goods are now worth 320.00 before tax where the return
   claims 720.00. … Cancel this return and raise it again, and it will be
   priced on what the bill is still worth." No debit note was approved
   since; R2 is now taken to hold the first bill.
5. R1 cancelled and raised again, as the message says: **377.60**, completed.
6. `POST /purchase-returns/{R2}/complete`: 200, 377.60.

**Both boxes are back and 472.00 + 377.60 + 377.60 = 1,227.20 has been
claimed against 1,699.20.** Trade Payables for the supplier ends 472.00
still owed; over the scenario Purchase Price Variance (5400) is left
400.00 in debit and 36.00 + 36.00 of input tax is still held; the bills
read 472.00 and 377.60 outstanding beside a credit of 377.60.
**GSTR-3B (N1): eligible ITC +259.20, reversed +187.20, net +72.00.**
Completed the other way round (R2, then R1) the same two returns come to
377.60 and 849.60 and everything is 0.00.

**Expected:** `docs/PURCHASE_FRAMEWORK.md`: "a return not yet completed is
still derived, on top of the stored rows, in the order raised (date,
number, line), by either route". **Actual:** the return being priced or
completed is left out of that order and placed after every other open
return, whenever it was raised. So each of the two takes the other to be
ahead of it, both are valued on the second bill, and the first bill's
720.00 is claimed by neither. Nothing refuses a return for claiming less
than its bill, so R2 completes at 377.60 on a bill line worth 720.00.
Workaround: complete or cancel one return before raising the other; after
the fact, cancel R2 and raise it again.

**Suspected:** `app/purchase_return/billing.py:344` to `:357`
(`bill_line_claims`: `_pending_returns(…, exclude_return_id=…)` and the
loop over `sorted(waiting)`, which places every open return but the one
asked about) with `placing_order` at `:270`. The message of step 4 is the
completion re-check's and names a cause it did not test for.

### D-PRC-82: a discount on a line with free units is spread over the free units (High, pricing)

S1 19:37 and 19:42 IST (`o8.py` parts o and c), S2 19:31 and 19:43. The same
on both.

The control and the fault, on one product (100.00 a piece, cost 60.00) with
one offer: 10% off, value budget 1,000.00, a principal paying half.

| | An order of 24, nothing free | An order of 24 with `free_quantity` 2 typed |
| --- | --- | --- |
| The order | discount 240.00; the offer reads 240.00 claimed | the same |
| The note line | `ordered_quantity` 24, `current_delivery_quantity` 24 | `ordered_quantity` **26**, `current_delivery_quantity` 24 |
| Two bills of 12 | discount 120.00 each | discount 120.00 each, 1 free each |
| `POST /principal-claims/preview`, kinds SCHEME and FREE_GOODS | SCHEME **60.00** a bill: 120.00 | SCHEME **55.38** a bill: **110.76** (and FREE_GOODS 120.00 for the typed units) |
| All of it returned off the note | the offer reads **0 claimed, 1,000.00 left** | the offer reads **18.4615 claimed, 981.5385 left** |

With the free units given by a second offer (buy 10 get 1, B7) the figures
are the same: 55.38 a bill, and 18.4615 left on the value budget for every
order that comes back whole; 55.38 is 240.00 x 12/26 x 50%, and 18.4615 is
240.00 x 2/26. Two claims were raised at those figures on each firm
(CLM-…000003 and 000004 on S1, 000008 and 000009 on S2: Dr 1420 170.76 /
Cr 6940 110.76, Cr 5200 60.00).

**Expected:** `app/principal_claims/services/passed_on.py`'s own account:
the principal owes "its share of what the firm actually gave a customer";
each bill gave 120.00. And `docs/PRICING_AND_PROMOTIONS.md`: a returned
order gives its budget back. **Actual:** the share of the order line a bill
line took is worked as invoiced over delivered, times the note line's
delivered over **ordered**, and a note line's `ordered_quantity` counts the
order line's free units (26). Each bill of 12 is taken to carry 12/26 of
the discount, and the 2/26 that falls on the free units is never passed on
to any bill and never comes back with any return. The claim and the offer's
budget read the same statement (D-PRC-45), so both are short. Workaround:
none; a line with no free units is right.

**Suspected:** `app/promotions/services/bill_discounts.py:176` to `:187`
(`share`: `_part(DeliveryNoteLine.current_delivery_quantity,
DeliveryNoteLine.ordered_quantity)`), read by
`app/principal_claims/services/passed_on.py:117` and `:176` and by
`discount_came_back` at `:269`.

### D-PRC-83: a purchase return's header charge is not counted on its bill (Medium, buying)

R1 19:19 IST (`p8.py` part a, scenario a6), S3 19:23. The same on both.

1. 2 BOX at 720.00 received; a bill with `additional_charges` 100.00:
   1,799.20 (Cr 2100 1,799.20; the 100.00 is debited to 5400).
2. `POST /purchase-returns` off the bill line, 2 BOX, `additional_charges`
   100: 1,799.20, completed. Trade Payables for the supplier: 0.00.
3. `GET /payments/outstanding`: the bill reads **`allocated_amount`
   1,699.20, `outstanding_amount` 100.00**. `GET
   /payments/supplier-credits`: PR-… **100.00 available**. The payables
   report: `credits` -100.00, `total` 0.00.

**Expected:** the selling side's rule since D-PRC-74: "A return's header
figures come off the bill as well as the account". **Actual:** what a
supplier bill owes counts the return's lines; the header charge of a
return raised on the bill itself becomes a supplier credit beside it. The
totals are right. The bill goes on being offered in Record Payment, takes a
payment (B4 shows one accepted while a credit stands) and is in the
supplier ageing, which does not net credits. Workaround: apply the credit
to the bill.

**Suspected:** `app/settlements/services/settlement_service.py:1069` to
`:1110` (`_returned_by_goods` sums `PurchaseReturnLine.net_amount`; the
return's `additional_charges` and `round_off` are on the header).

### D-PRC-84: the printed credit note names no invoice (Medium, selling)

S1 19:10 IST (`s8.py` part w), N1 19:17. The same on both.

`GET /sales-returns/{id}/print` for a completed return of 2,832.00 placed
on two bills, and for one of 1,416.00 raised on a bill's own line. The
print carries the firm, "Credit note no.", "Credit note date", "Reason",
the customer twice, the lines, the tax by component and the total. **No
bill number or date, and no delivery note number, appears on either.**

**Expected:** the return's own readers already know the bill: GSTR-1 `cdnr`
gives `against_invoice`, the GST register `against_invoice_number`
(D-SELL-75), and since D-PRC-72 the bills a return off a note was set on
are stored row by row. A GST credit note is issued against a tax invoice
and is expected to state the number and date of the invoice it corrects; a
customer's accountant cannot match this one to a bill. **Actual:** the
print's references hold the reason alone. Workaround: write the bill
number in the return's reason.

**Suspected:** `app/sales_return/services/credit_note_print_service.py:229`
to `:233` (`references` is built from `row.return_reason` only).

### The Low findings

- **D-PRC-85 (selling).** S1 19:08 IST, N1 19:16 (`s8.py` part b).
  `POST /sales-returns/import` with a good record followed by one the
  service refuses answers 422 with the single save's sentence ("Line 1:
  SI-… line 1 billed 2 BOX …") and no record number; `details` is empty.
  `purchase-returns/import` answers the same position "Record 2 of 2: … 
  Nothing was imported." and every schema refusal now names its record
  (D-PRC-76). Nothing is written. Suspected:
  `app/sales_return/services/sales_return_service.py:3213` to `:3220`
  (`import_returns` re-raises as it stands; compare
  `app/purchase_return/services/purchase_return_service.py:2551` to
  `:2558`). The other selling imports read the same way in the code and
  were not driven with a service refusal.
- **D-PRC-86 (selling).** S1 19:08 IST, N1 19:16 (`s8.py` part b); S1 19:06
  (part t). The refusal D-PRC-72 added states every figure in the bill
  line's unit to four places: 13 PIECE is "1.0833 BOX", 6 PIECE against 5
  left is "0.4167 BOX is left … where the return brings back 0.5 BOX", 1
  PIECE is "0.0833 BOX". The refusals beside it speak in the unit typed
  ("1 PIECE of the 2 PIECE sent free …"). Suspected: the message built in
  `app/sales_return/billing.py` for a line with nothing left on its bill,
  which formats the bill line's quantities and not the entered ones.
- **D-PRC-87 (selling, quotations).** S1 19:29 IST, S2 19:30 (`q8.py`).
  `POST /quotations`, 2 BOX with `free_quantity` "0.25": 201; it reads and
  prints "2 + 0.25 free BOX". Sent, accepted and converted: 422 "BOX is
  counted in whole numbers, so 2.25 BOX cannot be entered." The quotation
  can be quoted and accepted and never ordered. Suspected: the whole-unit
  check the order applies to quantity plus free quantity is not applied
  when a quotation is saved (`app/quotation/services/quotation_service.py`).

## Case text to correct

Round 3's to round 7's tables still stand; nothing in them was applied.
Changes, for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 7's held-back cases | Can be written as passing: a unit off the note then the first bill's own line (refused by name; off the note 944.00 or 1,416.00; 2,832.00 in all); its buying twin (849.60 then 377.60); a purchase return typed above its bill (refused; 720.00 passes, 600.00 gives 1,416.00); a return with a header charge and what the bill then owes (1,456.00, then gone); an import file the schema refuses (422, "Record 2 of 2: …"); cancelling a draft bill of a note with a return (200) |
| New cases wanted | (1) "0 free" on a quotation's box line (one line, printed alone); (2) a bill of 2 BOX returned as 7, 7, 7 and 3 pieces (2,832.00); (3) a completed return off a note cancelled and raised again (1,416.00, then 944.00); (4) two approved bills of a note, a return off the note, cancel each bill (200 and 422); (5) commission after a refused return and after a cancel and re-raise (0.00; +60.00 then -60.00); (6) a purchase line billed at 0.00 returned (0.00, stock out at its average) |
| Hold back until fixed | Cancelling a supplier bill under a return off its receipt (D-PRC-80); two purchase returns open by two routes (D-PRC-81); a principal claim for a discount on a line with free units (D-PRC-82); a purchase return's header charge and what the bill owes (D-PRC-83); the credit note print (D-PRC-84) |
| 009 | Unchanged: state QQ's price (84.00) in the case |
| 010 | Say that the last step depends on the time of day: inside the offer's window the quotation reads the offer's 5%, outside it the price list's 9.25% |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **The refusal at completion names a cause it did not test for** (S1, N1;
  R1, S3, N1): "DN-… has been credited since this return was saved" and
  "has had a debit note approved since this return was saved" are answered
  when another return took the bill's units in between and nothing was
  credited or claimed.
- **"billed at 2160.00" for goods partly unbilled** (R1, S3): 3 BOX off a
  receipt of which 2 are unbilled, typed at 900.00, is refused as claiming
  2,700.00 "for goods that PI-… billed at 2160.00"; the bill billed
  1,440.00 and the rest is the receipt's price.
- **"50.00 already given back by other returns"** in the refusal of a
  header charge on a bill that charged none (S1, N1): the 50.00 was given
  back on another bill of the same note.
- **GSTR-1 names one bill for a return set on two** (S1, N1):
  `against_invoice` is the first bill for the whole 2,400.00.
- **The e-invoice gate of the credit note print asks only for lines raised
  on a bill** (read in `credit_note_print_service.py:133` to `:146`, not
  driven: no fixture firm issues e-invoices): a return off the note that
  credits a bill would print without the IRN check.
- **A return's commission follows its header charge** (C1, C2): on a bill
  of 2,932.00 earning 120.00, returns of 1,476.00 and 1,456.00 take back
  60.41 and 59.59, not 60.00 and 60.00; 0.00 in all.
- **A return that credits nothing still states a value** (S1, N1),
  unchanged: 1,416.00 on a return of an unbilled box.
- **A box returned in pieces reads odd quantities** (S1, S2): the last 3
  PIECE of 24 read `current_return_quantity` 0.2501 and the last 4 of 12
  read 0.3334, the rounding of the earlier parts carried into the last.
- **After one of two bills is cancelled, a return approved before it takes
  the unbilled box and credits nothing** (S1, S2): the return completes at
  200 stating 1,416.00, the customer's account does not move, and the bill
  that was refused cancelling "while it has sales return SR-…" goes on
  reading 1,416.00. Each step follows its rule; the two messages together
  do not tell the user that.
- **The supplier ageing and the suppliers' outstanding report do not net a
  supplier credit**, and **a supplier's bill can be paid in full while a
  credit stands** (R1, S3): round 7's gaps, unchanged; B4 and D-PRC-83 add
  two more ways to reach them.
- **The messaging pass and the reservation lapse warn about a firm that is
  being provisioned** (the server log, 19:44 to 19:47): "Firm storage for
  '…' has not been provisioned yet", once or twice for three of the six
  fixtures built.
- **24 charged and 2 free cannot go back in one return line** (S1, S2): the
  schema wants restock to equal the returned quantity (24), so the free
  units need a return of their own.
- Round 7's gaps were not driven again except where A or B covers them.
  Closed: a draft purchase return's wording was not re-read; the header
  charge on a sales bill is now counted on the bill.

## Left on the firms

- **S1 and N1**: about forty bills each from the D-PRC-72, 74 and B
  scenarios, nearly all returned in full (left owing: one bill of 1,416.00
  beside a cancelled draft, one of a note half returned, and the header
  charge scenario's 40.00 and 20.00, for B8H on S1 and PC on N1); ten
  credit notes of 472.00 each; product Z8R (and on S1 Z8Q, Z8O, Z8P); on S1
  customers B8H and B8L.
- **S1 and S2**: offers Q8Q, O8D, O8F and P8D retired; principals PR8R and
  PR8C with their brands and suppliers; **two claims each on PR8R at 170.76
  (D-PRC-82), RAISED**; three orders of 24 + 2 free out on S1 and three on
  S2, and on S2 five more orders of 24 at full price from the second run
  (two returned); quotations left DRAFT or converted, one with a quarter
  box free that cannot convert; 0.01 held by C01 on S1 and 0.02 on S2; an
  order of 7 PIECE of X4K shipped and billed each; three draft or cancelled
  bills from the D-PRC-77 scenarios and one approved bill each of 1,416.00
  whose return credited nothing.
- **C1 and C2**: customer B8K; product VH8; one receipt of 2,932.00 and the
  advance it became after its bill was returned (D-PRC-75); five bills
  and their returns, one return cancelled.
- **R1 and S3**: about thirty-five new suppliers each (V8nn); **suppliers
  in debit by 849.60** (two on R1, three on S3: one each from D-PRC-80, the
  rest B4's last box returned after payment); **one supplier each owed
  472.00 for goods all returned** (D-PRC-81); supplier credits unapplied
  beside bills; debit notes of 472.00 and one of 1.18; four bills each
  cancelled (D-PRC-80's scenarios and the stability check), one entered
  again; eight payments on R1, six of them reversed, and six on S3, four
  reversed; two draft returns cancelled; purchase stages as found. **N1**:
  about fifteen new suppliers, one 849.60 in debit, one owed 472.00; three
  bills cancelled; purchase stages put back as found.
- **P1 and P2**: one more approved order pinned over its batch, and one
  more bill of 1,344.00, as `m5.py` leaves them.
- **N4, R5, L5, C5, D5, O5**: what the regression scripts leave on a firm.

## Not verified

- **Nothing on screen.** The desktop was not opened.
- **Nothing was read from the database.** That the server runs `e3c5710a`
  was taken from the hand-over, from `git log` on the working tree and from
  the fixes behaving as merged; that the head is `20261006_0347` on every
  store was taken from the hand-over.
- **Everything ran once, in one window** (19:04 to 20:02 IST).
- **Whether three customers' bills read as they did before the migrations**
  (C1's C4, S1's and N1's PC and PD): round 7 kept no figure per bill.
- **One firm where two would be better**: GSTR-3B (N1 alone has a GST
  number among the buying firms); GSTR-1 for a customer with a GSTIN (N1);
  D-PRC-75 (C2); the regression (one firm each, as asked).
- **An opening or imported supplier bill returned**: it has no lines, by
  its schema; no return was attempted against one.
- **D-PRC-82 beyond one line**: an order of several lines, a bill discount
  an offer set, and a waived delivery charge on a line with free units were
  not driven.
- **D-PRC-80 on a bill with a payment or a debit note** (those block the
  cancel on their own), and **D-PRC-81 with three bills**: not driven.
- **D-PRC-85** on the other selling imports with a service refusal.
- **The e-invoice gate** named in the gaps: read, not driven.
- **The rate difference by batch** (`pm.py`): no fresh pharmacy firm.
- **Commission**: a margin rule, and a category rule, under a return off
  the note; a payout over a refused return.
