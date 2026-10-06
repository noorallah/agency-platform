# Pricing, promotions, loyalty, commission, claims and the returns and credits around them: checked through the API, round 10, 2026-10-07

The tenth pass over this module and the intended closing round, driven the way
rounds 1 to 9 were: the real server over HTTP at http://127.0.0.1:8000 (`main`
at `f167a117`, PR #1321, migration head `20261006_0348`), books read back
through the API, nothing read from the database, no source file changed,
nothing fixed, no test suite run, no git write, no restart and no migration.
The file carries the next day's date as asked; everything was driven between
**23:06 and 23:40 IST on 6 October 2026** (17:36 to 18:10 UTC).

Ids are the registered ones: round 9's findings are **D-PRC-88 to D-PRC-92**
(and D-PRC-93, fixed with them). This round's new findings would start at
**PRCQ-94**.

**Every round 9 fix holds, on documents created in this round.** D-PRC-88, 89,
90, 91, 92 and 93 are fixed by their original reproductions and in every
further shape this round was asked to try.

**The round found one new finding, Low (PRCQ-94, buying wording).** Nothing in
pricing proper (offers, price lists, loyalty, commission, claims). The twelve
TC-INCENT cases and the regression ran with nothing differing from round 8 in
substance. The module can be called closed on the evidence of this round,
subject to "Not driven or not clean" below.

## When, and on which firms

**No request answered 500 or 503.** The server log from 23:06:00 holds 8,231
completed requests (6,481 at 200, 1,166 at 201, 3 at 204, 426 at 422, 80 at
403, 43 at 404, 19 at 409, 13 at 401), none at 5xx, no ERROR and six WARNING
lines, all background passes ("messaging pass failed" and "reservation lapse
failed") meeting a fixture firm in the second between its creation and its
provisioning: three of the firms below and the three unused ones described
next. `/health` answered 200 before each of the 38 runner scripts and at the
end. Two reads were dropped in transit and read again by the helper
(`g.py`); no write was sent twice.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| N5 | `selling-firm` | `T10063PPT-S` | | A: D-PRC-89 (a GSTIN firm with sandbox e-invoicing; HSN code on the products) |
| C6 | `commission-firm` | `T1006HJDE-T` | yes | A: D-PRC-88, 91, 92; case 007; commission per unit |
| R6 | `ready-firm` | `T100668GK-R` | yes | A: D-PRC-90, 93; buying by the box |
| N6 | `selling-firm` | `T1006SZXN-S` | yes | cases 001, 002, 004, 009, 011, 012 (adapted); budgets, claims, rate difference, generic checks |
| L6 | `loyalty-points` | `T10064J7Q-S` | yes | cases 005, 010 |
| C2, C1 | `commission-firm` | `T1006DWN6-T`, `T1006MWGX-T` | | D-PRC-91 on B7G (a credit refunded before credits were tracked) |
| O1, C3, C4, D1, D5 | | | | cases 003 and 008 (and attempts at 006 and 012) |
| S1, S2, S3, N1, R1, P1, P2 and the rest | | | | unchanged scripts and the books |

**A slip that exceeded the cap of four new firms.** The first fixture build
(`mk9.py`) was killed with the shell it ran in (exit 137) after N6 was built,
but its Python child went on and built three more firms (`T1006D6NB-R`,
`T10062Y12-S`, `T1006DCE5-T`) while the second build, which I started because
the log was empty, built R6, L6 and C6 for real. The three are unused, hold
only what the fixture builder gives them, and have no document of mine.
Seven new firms were therefore created in all, three of them idle. Nothing
else reads them. The helper's registry `fx.json` records only the second
build's four. **Memory.** Free memory was 2.1 to 3.9 GB through the round
(lowest read by the runner 1,515,924 KB at 23:23:16, during `i8.py S2`, above
the 1.5 GB floor it enforces); one script at a time was run except for this
build overlap.

Scripts and logs are in the scratchpad folder `pricing10`, a copy of
`pricing9`. The new ones are `e10.py` (D-PRC-89), `t10.py` (D-PRC-88, 91, 92,
copied from `cc9.py`), `b10.py` and `f10.py` (D-PRC-90 and 93, copied from
`c9.py`), `x10.py` (the e-invoice payload), `c12n.py` (case 012 on N6),
`cmpall.py` (compares a regression log with round 8's after masking document
numbers, firm tags, dates, random coupon codes, firm-wide valuation totals and
line order). Round 9's `cc9.py part x` and the regression scripts of rounds 3
to 8 were run unchanged.

What went wrong on my side, so the record is straight:

- **The fixture build overlap above.** Three idle firms.
- **Four of the case fixtures were not clean.** D1 to D5 (case 012), C3 and
  C4 (case 006) had been used by earlier rounds, so `c12.py` stopped at "Vendor
  code or GSTIN already exists" and `c678.py` read earlier sales; the first
  run of cases 006, 007 and 012 on them is not a result. Case 012 was run on
  N6 instead (`c12n.py`, one hard-coded invoice and customer changed), case 007
  on C6 and case 008 on C3 and C4 (the 403s do not depend on data). Case 006 is
  the one that could not be run clean (below).
- **My "A4/A5" refund step in D-PRC-88** refunded a credit that was already
  applied, which is refused by name ("has only 0.00 of credit left to be paid
  back"); the refund shapes were rebuilt as B1 to B4 without the application.
- **The `books3.py` line "2100 ... DIFFER" is the script's own limit** (it
  does not find the suppliers' balance field); payables are read with
  `b87.py`, as in rounds 7 to 9.

## A. The findings of round 9, re-driven

| Id | Verdict | Firm | Evidence |
| --- | --- | --- | --- |
| D-PRC-89 | **Fixed** | N5 | On a firm that e-invoices from today (`einvoice_applicable_from` set for the run and put back), products with HSN code 34022090. **R-note** (1 BOX back off the note that credits bill 1): print **422** "SR-… has no IRN yet. The firm e-invoices from 06 Oct 2026 and the buyer is registered for GST, so it is not a valid tax invoice until it is registered on the portal (CGST rule 48(4)). …" (`irn_required`), the same as R-bill (the return on the second bill's own line). `reference_copy=true`: 200 with the "NO IRN YET" banner and "Against invoice SI-…033" and "Delivery note DN-…" for R-note. Both listed in `GET /einvoice/pending` (56 pending). `POST /einvoice/sales-returns/{id}/register` after the two bills were registered: **200 "Registered in SANDBOX mode."** with an IRN, status REGISTERED; the print then reads 200 with the IRN and no banner. **A note billed in two parts, one return of 2 BOX off the note spanning both**: refused at print, listed pending, reference copy "Against invoice SI-…035 … Against invoice SI-…036", registered; **the sandbox payload (offline export, `x10.py`) holds two `PrecDocDtls` entries** (SI-26-27-000039 and SI-26-27-000040, both dated 06/10/2026). GSTR-1 `cdnr`: R-note against SI-…033 for 1,200.00, R-span against both invoices for 2,400.00. **A return off a note no bill charged**: print 200 with no banner and no "Against" row, not in the pending list, register **422** "SR-… returns goods no invoice billed, so it credits no tax invoice and is not registered.", no `cdnr` row: it stays outside e-invoicing |
| D-PRC-88 | **Fixed** | C6 | Bill 1 of 2,832.00 paid, 7 back (826.00 credit), bill 2 of 1,416.00, the credit applied (customer 590.00 and 0.00). Judged by "the customer's two figures equal the bills' outstanding and the credits held" after each step, **AGREE at every step of every scenario (37 reads)**. **Receipt reversed, then application reversed (A1)**: 3,422.00 / 0.00 after the first, then bills 2,006.00 and 1,416.00, 3,422.00 / 0.00 (the round 9 reproduction read 4,248.00 / 826.00); ageing 3,422.00 and statement 3,422.00; 1100 +2,832.00 over the two steps. **Application first, then receipt (A2)**: 1,416.00 / 826.00 after the first, 3,422.00 / 0.00 after the second. **No application (A3)**: 1,416.00 / 826.00, then 3,422.00 / 0.00. **A credit refunded and the refund reversed, then the rest (B2, B3)**: the same. **A refund left standing, then the receipt reversed (B1, B4)**: 4,248.00 / 0.00, the credit reads refunded 826.00, nothing available. **After settle-up in every scenario (bills paid as they read)**: **0.00 and 0.00, no credit held, statement 0.00, ageing empty, and a further refund of 826.00 is refused** "Refund amount exceeds unapplied advance." **The return cancelled after the absorption (A6)**: 200, bills 2,832.00 and 1,416.00, customer 4,248.00 / 0.00, 1100 +826.00; cancelled with the application standing (A7): the same. Receivable control account, statement and ageing agreed in each |
| D-PRC-91 | **Fixed** | C2 (legacy), C6 | **A credit refunded the old way (B7G on C2, refunded in round 7 before credits were tracked)**: with every bill paid and 500.00 received on account, the return's credit still reads credit 826.00, refunded 826.00, **available 0.00**; a bill of 708.00 and an application of 500.00: 422 "SR-… has only 0.00 of credit left to set against a bill."; the receipt's own 500.00 then allocates (208.00, 200). **On-account receipt refunded before a return (K1)**: 500.00 received and refunded (customer 0.00 / 0.00), a bill paid and 7 back: the credit reads 826.00, available 826.00, refunded 0, applies in full (customer 590.00 / 0.00). **A refunded credit (new style) beside an on-account receipt (K2)**: available 0.00, 500.00 refused. **An untouched credit beside an on-account receipt (K3)**: available 826.00, applied, the receipt still holds 500.00 |
| D-PRC-92 | **Fixed** | C6 | An opening bill of 1,000.00 with 826.00 of a return's credit applied, cancelled: 422 "OBC-… cannot be cancelled while it has 826.00 of credit applied from SR-…. Reverse that application first." With a receipt of 100.00 as well: 422 "… 826.00 of credit applied from SR-…. Reverse that application first, and the receipts for the other 100.00 received against it." |
| D-PRC-90 | **Fixed** | R6 | Receipt stage off; order of 24 PIECE at 60.00 with 2 free and 10% off. **12/12**: receipts of 12 free **1** and 12 free **1**; **8/16**: **0** and **2**; **8/8/8**: **0, 1, 1**; each: bills 1,529.28 in all (the order's), free 2, **stock 26 at 49.8462 (1,296.00)**, accounts 2100 +1,529.28, 1200 +1,296.00, tax 233.28, 2300 0.00. **A supplier scheme (buy 12 get 1), 12/12, nothing typed**: 2 free, 26. **Typed free above what is left**: 3 on the first bill: 422 "Line 1 brings in 3 free, and line 1 of PO-… has 2 left to give: 2 free on the order, 0 already received."; 1 then 2: 422 "… brings in 2 free, … has 1 left to give: 2 free on the order, 1 already received."; 2 then 0: 2 free, 26. **In one bill**: 2 and 26. **A free-only line** (a second line of 5 free that charges for 1 at 0.00, or ordered 0 at 60.00 with 5 free, beside a line of 24): the first bill brings in the whole **5 free** (stock 6 and 5), the second bill none; billed twice for 1 more: 422 "Goods receipt exceeds allowed quantity for PO line 2: 1 PIECE ordered, 1 PIECE already received, …". (A bill of a free-only line on its own: PRCQ-94, below) |
| D-PRC-93 | **Fixed** | R6 | Order line of 24 + 2 free with **144.00 typed as the discount** (reads 10%), two receipts of 12 sending no discount, billed: **bills 764.64 + 764.64**, tax 116.64 each, order 1,529.28, free 2, stock 26 at 1,296.00, **2100 +1,529.28 and 5400 not moved**. The same with a 10% rate. **Each receipt sending 72.00** (round 9 billed 1,699.20 and 144.00 went to 5400): **1,529.28, 5400 not moved**. **A whole receipt of 24** sending no discount: 1,529.28. **A typed 0 stands**: each receipt sent `discount_amount` 0 (or `discount_percent` 0): receipts at 1,440.00, bills **1,699.20**, stock 1,440.00, 5400 not moved (the figures follow what was typed). **Returns**: 6 of 12 off receipt 1 and 6 off bill 2 each carry the amount's share: gross 360.00, discount **36.00**, tax 58.32, **382.32** each |

## B. The twelve TC-INCENT cases

| Case | Driven by | Firm | Verdict |
| --- | --- | --- | --- |
| 001, 002, 004 | `c124.py` | N6 | **Pass.** Nothing differing from round 8 but the firm tag and the order of two audit lines |
| 003 | `c35.py 3` | O1 | **Pass.** None |
| 005 | `c35.py 5` | L6 | **Pass**, the case text wrong in one figure as before. None |
| 006 | `c678.py` | C3, C4 | **Not re-driven clean.** The firms had been used (Asha reads 8,260.00 collected where a fresh firm reads 5,900.00), so the report cannot be compared with the case's figures; the per-unit rules (`cm.py`, C6) give 60.00 a unit three ways as before, and Bala's 80.00 on 4,720.00 reads as round 8 (the case text wrong, the product right, as before) |
| 007 | `c7.py` | C6 | **Pass.** Accrue, approve (the accruer cannot; a sales manager cannot; a firm manager can), pay (the approver cannot; the accountant can), cancel a draft, accrue again: 409 naming the overlap. None |
| 008 | `c678.py` part 8 | C3, C4 | **Pass.** Asha and Bala: 403 on all ten routes |
| 009, 011 | `setqq.py` then `c911.py` | N6 | **Pass.** None |
| 010 | `c10.py` | L6 | **Pass.** Multipliers 11, 0, 1 refused, 10 and 2.5 accepted, a multiplier beside a discount refused; the time-window offer was built around the minute it ran (1399 after midnight) |
| 012 | `c12n.py`, `c12b.py` | N6 | **Pass, on a firm that is not the case's own preparation** (a selling firm with a bill of its own and a damaged return). The preview gathers scheme 20.16, expiry 240.00, breakage 79.80 once (339.96), raising posts Dr 1420 339.96 / Cr 6940 20.16, Cr 5500 319.80, a second claim: 422 "Nothing is left to claim from Principal …", a bank receipt moves it to PART_SETTLED, reversed it comes back, a credit note against the supplier's bill (113.55) posts and cancels, a part-settled claim cannot be cancelled, print 200 (3,118 bytes); access 200/200/200/403 as round 8 |

## C. Regression

Each log was compared with round 8's after masking; "nothing differing" means
the same lines to the paisa.

| Script (firm) | Verdict |
| --- | --- |
| `a22.py`, `a22.py 4 x` (lines sold by the box; N6) | **Nothing differing**, 172 and 31 lines |
| `bx.py 12345678` (buying by the box; R6) | **Nothing differing in the 245 lines but the firm's running totals** (the valuation total and the books line include b10's earlier stock; the product rows are identical) |
| `cr.py` (rate difference claim; N6) | **Nothing differing**, 79 lines |
| `a27.py`, `a28.py` (budgets and principal claims; N6) | **Nothing differing** but the two receipts fired at the same instant landing in the other order (one 201 and one 422 either way), as in round 8 |
| `a24.py`, `a35.py`, `c124.py`, `c911.py` (N6) | **Nothing differing** |
| `adv.py` (C2), `gg5.py`, `n4g.py` (N6, S1, S2, R6) | **Nothing differing** |
| `g.py` (N6, S2, L6) | One dropped read read again; otherwise nothing differing |
| `dup6.py` (S1, S2), `i8.py` (44 import requests a firm; S1, S2) | **Nothing differing** but document counts on S1 and S2 |
| `c8.py` (C1, C2: commission after returns; S1, S2: loyalty), `s5a.py fg`, `u6.py` (S1, S2) | **Nothing differing** but the firm's books lines (older state); `u6.py` has no round 8 log, 3 lines a firm, no error |
| `m5.py` (P1, P2: the batch over-pin) | **The rule half ran, the shipping half could not**: round 8 left the batch at 0 on both firms, so "the batch holds less than a box; the shipping half is skipped"; the documented rule (an order pinned to more than the batch holds) reads the same |
| Cases | Section B |

**No request in any of the 38 runner scripts or the hand runs answered 5xx;
no traceback except the ones named under "What went wrong".**

## D. The books at the end

Run for every firm this round wrote to (nineteen). **Every trial balance
balances and no journal is unbalanced** (between 20 and 1,747 journals a
firm). Receivables agree with the customers less their advances, Loyalty
Payable with the points' worth, commission payable with the approved payouts
and Claims Receivable with the open claims **on every firm**; **account 2100
equals "bills outstanding less supplier credits available" equals the payables
report's total on every firm read** (N6, R6, R1, S1, S2, S3, N1, N5, C1, C2,
C6).

| Firm | Trial balance | 1100 = customers less advances | 2100 = bills less credits = payables report | 1200 against valuation |
| --- | --- | --- | --- | --- |
| N5 | 3,656,079.01 | 11,469.60 | 0 | 3,598,440.00, agree |
| N6 | 842,133.13 | 59,389.79 | 29,972.00 | 735,982.27, agree |
| R6 | 42,077.68 | 1,270.00 (1,770.00 less 500.00) | 40,200.24 (42,777.36 less 2,577.12) | 33,275.44 against **33,275.45** (0.01) |
| L6 | 8,270.03 | 1,988.61 | 0 | 4,260.00, agree |
| C6 | 2,026,518.00 | 18,128.00 (19,128.00 less 1,000.00) | 0 | 1,896,000.00, agree |
| C1 | 2,637,354.50 | agree | 21,240.00 | 2,296,080.00, agree |
| C2 | 2,546,728.00 | 52,999.67 (67,751.67 less 14,752.00) | 0 | 2,222,880.00, agree |
| N1 | 2,384,057.47 | agree | 33,320.84 (61,902.80 less 28,581.96) | agree |
| S1 | 13,298,787.54 | agree | 29,311.20 | 12,562,100.10 against **12,562,100.12** (0.02) |
| S2 | 10,923,230.54 | agree | 29,311.20 | 10,486,600.12 against **10,486,600.14** (0.02) |
| S3 | 566,316.39 | agree | 114,553.90 (165,219.40 less 50,665.50) | 530,698.92 against **530,698.81** (0.11) |
| R1 | 129,354.31 | agree | 104,830.70 (164,487.80 less 59,657.10) | 109,632.19 against **109,632.10** (0.09) |
| P1, P2 | 40,447.20 each | agree | 0 | 3,157.67 against **3,157.69** (0.02) |
| O1, D1, D5, C3, C4 | 6,000.00; 7,881.10 twice; 142,092.00 twice | agree | | agree |

**D-PRC-56 (known, left on purpose)**, as measured: 0.02 on S1, S2, P1 and P2,
0.11 on S3 (0.11 in round 9), 0.09 on R1 (0.09 in round 9) and **0.01 on R6,
which this round created** (the orders of 24 + 2 free units and two purchase returns
of D-PRC-93). Not filed as new. Suppliers in debit on R1, S3 and N1 are the
earlier rounds' returns after payment (round 9's `V915`, `V914`, `V835`, `V832`
and the rest), faithfully carried by the books.

**One thing the books carry that is not a finding:** a purchase return off a
receipt (or the bill) that included free goods credits Purchase Price Variance
for the difference between the returned price (6 PIECE at 54.00 = 324.00) and
the average cost the stock leaves at (49.8462 a piece, diluted by the free
units): 24.92 a return, so account 5400 on R6 reads -49.84 after the two
returns of D-PRC-93. It follows the rule that a leg facing stock is valued from
the movement and a leg facing a counterparty from the document
(`docs/LEDGER_POSTING_RULES.md`).

## Findings

Ids continue from D-PRC-93. High = wrong money, tax or stock, or a control
that can be bypassed; Medium = wrong behaviour with a workaround; Low =
wording, paisa, cosmetics.

| Id | Severity | Module | What | Firms | Where from |
| --- | --- | --- | --- | --- | --- |
| PRCQ-94 | Low | Buying (posting wording) | A supplier bill raised off an order line that charges nothing (a line with only free goods) is refused with the posting engine's words, "A journal entry needs at least one debit and one credit line.", and the free goods cannot be brought in by that bill | R6 | A (free-only line) |

### PRCQ-94: a bill of a free-only line is refused in the ledger's words (Low, buying)

R6 23:14 IST (`b10.py`, `f10.py`; reproduced twice).

1. `PUT /purchases/workflow-settings` with `goods_receipt_stage` false (put back).
2. `POST /purchases`, one line: 0 PIECE ordered at 60.00 with `free_quantity` 5
   (or: 1 PIECE ordered at 0.00 with 5 free); approved: grand total 0.0000.
3. `POST /purchase-invoices` off the order line (`source_document_type`
   `PURCHASE_ORDER`), `current_invoice_quantity` 0 (or 1), approved: **422** "A
   journal entry needs at least one debit and one credit line." Stock for the
   product stays at none; the 5 free units were not brought in.

**Expected:** either the 5 free units come in on the bill (as they do when the
free-only line sits beside a charged line: the first bill brought in all 5 and
the second none, stock 5 and 6), or a plain refusal naming the zero value of
the bill. **Actual:** the posting engine's message surfaces. **Workaround:**
put the free-only line on an order with a charged line, or raise a goods
receipt where the stage is on. Not looked up in code.

## Case text to correct

Round 3's to round 9's tables still stand; nothing was applied. For
`docs/INDEPENDENT_TEST_CASES.md`: the held-back cases of round 9 can be
written as passing: (1) a return off a delivery note that credits a bill on a
firm that e-invoices (refused at print until registered, listed pending,
registered with one preceding-document entry a bill it credits, a return of
goods never billed stays outside); (2) a customer's credit applied, the
receipt reversed and the application reversed, in either order, then the bills
paid and nothing held (0.00 and 0.00); (3) a supplier bill off an order in
parts with the receipt stage off (free goods 1 and 1, 0 and 2, 0, 1 and 1;
stock 26); (4) a typed free figure above what is left (422 by name); (5) a
discount typed as an amount on an order line, received in two receipts and
billed (764.64 each, nothing to purchase price variance); (6) cancelling an
opening bill with credit applied (names the credit). Case 006 needs a clean
`commission-firm` each run (the case text is still 94.40 for a figure the
product reads as 80.00, as in round 8).

## Not driven or not clean

- **Case 006** (above): no clean commission firm left within the cap of four
  new firms.
- **Case 012 on its own preparation** (`selling-invoiced`): D1 to D5 were
  consumed by earlier rounds; driven on N6 instead.
- **`m5.py`'s shipping half** (batch pins): the batches P1 and P2 hold were
  spent in round 8.
- **D-PRC-91's exact legacy shape on a second firm**: a credit refunded before
  credits were tracked cannot be created now; B7G on C2 was the only such
  credit driven (C1's was read in round 9).
- **The sandbox payload only**: e-invoicing was driven against the SANDBOX
  provider; nothing reached a live portal. The `PrecDocDtls` entries were read
  from the offline export, which is the same payload.
- **Nothing on screen**, and **nothing read from the database**: the server
  running `f167a117` and the head `20261006_0348` are taken from the hand-over
  and from the fixes behaving as merged.
- **Three idle fixture firms** left by the build overlap (above).

## Left on the firms

- **N5**: five more orders, notes and bills of the D-PRC-89 shapes (three
  returns registered in the sandbox, six bills registered, one return of goods
  never billed); one E10H product with 9,000 pieces; the e-invoicing date as found (none).
- **C6**: customers of the A, B, K and O series with their bills and receipts (several reversed), two opening bills (OBC-00001 and 00002) with credit
  applied and one receipt of 100.00; commission `cm.py` per-unit rules and one
  paid payout (Bala 40.00) and one cancelled (Asha 190.00).
- **R6**: 16 orders of 24 + 2 free with their bills and receipts (stock 26 each, two with 12 and 13 after the refusals), two
  purchase returns of 6, four orders with a free-only line; stages put back as
  found.
- **N6, L6**: the case scripts' own documents; case 012's claim
  CLM-2026-2027-000009 PART_SETTLED, 1.00 received, one principal and brand.
- **C2**: B7G's old return still reads refunded 826.00; a receipt of 500.00 on
  account part allocated.
- **C1, C2, C3, C4, S1, S2**: the unchanged scripts' own documents; C3 and C4
  carry the per-unit rules of `cm.py` and a paid payout of 40.00.
