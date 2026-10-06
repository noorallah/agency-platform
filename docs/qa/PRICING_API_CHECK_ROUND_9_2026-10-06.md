# Pricing, promotions, loyalty, commission, claims and the returns and credits around them: checked through the API, round 9, 2026-10-06

The ninth pass over this module, driven the way rounds 1 to 8 were: the real
server over HTTP at http://127.0.0.1:8000 (`main` at `1e16df78`, PR #1317,
migration head `20261006_0348`), books read back through the API, nothing
read from the database, no source file changed, nothing fixed, no test suite
run, no git write, no restart and no migration.

Ids are the registered ones: round 8's findings are **D-PRC-80 to D-PRC-87**
and this round's start at **D-PRC-88**.

**Every round 8 finding is fixed by its original reproduction, on two firms
wherever round 8 used two, and in every further shape this round was asked
to try.** D-PRC-80 to D-PRC-87 are closed.

**The round does not close the module: it found two High, two Medium and one
Low (D-PRC-88 to D-PRC-92).**

- **The round found nothing new in pricing proper** (offers, price lists,
  discounts, loyalty, commission, claims). A discount on a line with free
  units is claimed and given back whole in every shape tried: several lines,
  a bill discount an offer set, a line sold by the box, and a return after a
  claim was raised. Commission on collected money counts a credit applied to
  a bill once, and loyalty is untouched by it.
- **The round found two new High elsewhere.** One in compliance (e-invoice,
  selling): a sales return raised off a delivery note that credits a bill
  prints as a valid credit note with no IRN on a firm that must e-invoice,
  is missing from the pending registrations and cannot be registered at all
  (D-PRC-89). One in buying: with the receipt stage off, a supplier bill
  raised off an order in parts receives the order line's **whole** free
  quantity on every part, so 4 free units are in stock where 2 were ordered
  and came (D-PRC-90). Two Medium, both in the new customer-credit feature
  (D-PRC-88, D-PRC-91), and one Low (D-PRC-92).
- **Section D, the regression, was not run.** The brief was to run it only
  if sections A to C produced no new High finding, and they produced two.
  The books check on every firm and the server-log scan were run all the
  same.

## When, and on which firms

Everything was driven between **21:05 and 21:39 IST on 6 October 2026, which
is 15:35 to 16:09 UTC on the same day** (two read-only reads followed at
21:46). **One fixture was built** (N5, a
`selling-firm`, at 21:24); the thirty-four firms of rounds 4 to 8 were used
again for everything else. The server was not restarted; `/health` answered
200 before each of the 53 script runs the runner made and at the end.

**No request answered 500 or 503.** The server log for the window holds
14,815 completed requests (12,008 at 200, 2,221 at 201, 469 at 422, 52 at
403, 25 at 404, 22 at 409, 16 at 401, 2 at 405), none at 5xx, no ERROR, and
20 WARNING lines, all "Concurrent update rejected": the 409s of the races
this round fired on purpose and of two sign-ins of one user at the same
instant (gaps).

**Memory.** Free memory was read before every script and the build; every
step would have waited under 1.5 GB and none had to. **The lowest reading of
the round was 1,904,176 KB at 21:24:22**, straight after the build (2,659,592
KB before it). Seven reads were dropped in transit and read again by the
helper; no write was sent twice.

| Key | Fixture | Firm | New | Used for |
| --- | --- | --- | --- | --- |
| R1 | `ready-firm` | `T10067V0N-R` | | A: D-PRC-80, 81, 83; C1, C3 |
| S3 | `selling-firm` | `T100659Z3-S` | | the same |
| N1 | `selling-firm` | `T100657VP-S` | | A: D-PRC-80, 81 against GSTR-3B; D-PRC-81's selling twin, 84, 85, 86, 87; C2 |
| S1 | `selling-firm` | `T100667G6-S` | | A: D-PRC-81's selling twin, 82, 84, 85, 86, 87; B9 (loyalty) |
| S2 | `selling-firm` | `T10064CYP-S` | | A: D-PRC-87; B9 (loyalty) |
| C1 | `commission-firm` | `T1006MWGX-T` | | B1 to B10 |
| C2 | `commission-firm` | `T1006DWN6-T` | | B1 to B10 |
| N5 | `selling-firm` | `T10063PPT-S` | yes | A: D-PRC-82 (round 8's `o8.py` parts c and o, then the further shapes); C2 on a second firm |
| the other twenty-seven | | | | the books at the end |

Scripts and logs are in the scratchpad folder `pricing9`, a copy of
`pricing8` with round 8's logs under `r8`. Round 8's scripts were run
unchanged for the original reproductions (`p8.py` parts x, s and a; `s8.py`
parts t and b; `q8.py`; `o8.py` parts c and o). The new ones are `p9.py`
(D-PRC-80, 81, 83 further; C3), `cc9.py` (section B), `s9.py` (D-PRC-84, 85,
87), `o9.py` (D-PRC-82 further), `c9.py` (C1), `g9.py` with `gst9.py` (C2),
and the read-only `peek9.py`, `stock9.py` and `logscan9.py`. "The same on
both" means the two logs were compared after masking document numbers, firm
tags and the stock averages that differ from firm to firm, and differed in
nothing else.

What went wrong on my side, so the record is straight:

- **The first run of section B on C1 ran out of stock.** Product VD6 had 281
  pieces and cannot be given opening stock twice, so parts 7 to 10 stopped
  at "Insufficient available stock" after the first six had run. They were
  run again on a new product (V9S); C1 therefore carries part 6 twice and
  one opening bill of 1,000.00 that was never used (customer B9L1).
- **My first races were not races.** Each side signed in at the instant it
  fired, and two sign-ins of one user at the same moment answer 409 for one
  of them, so one request never left. The pairs in this report are from the
  second run, with both sessions signed in beforehand.
- **Two "want" figures in my logs are wrong and are not what this report
  states**: `p9.py` part k expected Trade Payables to end at 0.00 where a
  bill is cancelled under an open return (849.60 is right: one box is kept
  and billed), and `s9.py` first sent `sales-invoices/import` as a form
  where it takes a JSON body (run again as it should be).
- **One line of a here-document reached the shell** (an empty one, to a
  `python` that is not on the path; it hung for two minutes and wrote
  nothing). Every script edit was made with the file tool; one edit left a
  syntax error in `s9.py`, found on its next run and corrected.
- **Three firm settings were changed and put back**: the purchase stages on
  R1, S3 and N1 (as round 8), and "e-invoicing applies from" on N1 and N5,
  set to today for the thirty seconds of `g9.py` and cleared again. N5 was
  given a GST number, and its customer PC one, to drive C2 on a second firm;
  those stay.

## A. The findings of round 8

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| D-PRC-80 | **Fixed** | R1, S3, N1 | Round 8's three rows (`p8.py` part x). A box back off the **receipt** (placed on the first bill), then `POST /purchase-invoices/{first}/cancel`: **422** "PI-… cannot be cancelled while it has purchase return PR-…. Reverse or cancel those first." A box off the receipt and a box on the first bill's own line (spilled onto the second), then the **second** bill cancelled: 422, naming the spilled return. The control (a return on the bill's own line) as before; the bill nothing was placed on cancels (200). **GSTR-3B (N1)**: one box back, both bills standing: eligible +259.20, reversed +129.60; both back: +259.20 and +259.20. **An open return off the receipt, in three positions (draft and approved alike):** fully billed in two bills: the first bill is refused by name, the second cancels (200), and the return then completes on the box the cancelled bill let go, claiming nothing (Dr 2300 720.00 / Cr 1200, Cr 5400): 849.60 is owed for the box kept, and GSTR-3B (N1) reads eligible +129.60, reversed 0. Part-billed (2 received, 1 billed): the bill cancels (200). After the return completed as unbilled: the bill cancels (200); the box still held is billed again (849.60) and a second is refused, "… bills 1 BOX where 0 BOX is left to bill (2 BOX received, 1 BOX on other bills, 1 BOX returned before billing)." **A spilled return only approved** holds both bills: the second "… while it has purchase return PR-…129", the first "… PR-…128, PR-…129" |
| D-PRC-81 | **Fixed** | R1, S3, N1; the selling twin S1, N1 | Round 8's scenario s1 (`p8.py` part s): two bills of 849.60, debit note 472.00 on the second, a return off the receipt (849.60) and one on the first bill's line (377.60) both approved. **Completed receipt first: 200 and 200. Bill first: 200 and 200.** 1,227.20 of returns and the 472.00 note: Trade Payables 0.00 in all, bills read 472.00 and 377.60 outstanding beside the receipt-route credit of 849.60. **GSTR-3B (N1): eligible +259.20, reversed +259.20**, both orders. **Three bills of 1 BOX, a debit note on each in turn, three approved returns (off the receipt, on bill 1's line, on bill 3's line) completed in every order**: 18 scenarios on R1, 9 on S3, 9 on N1: every return completed at what it was saved at (377.60, 849.60, 849.60 in the place the note decides), **no refusal, Trade Payables 0.00 in all 36**, GSTR-3B (N1) eligible +388.80 and reversed +388.80 in all nine. **Cancel and re-raise the receipt-route return while the bill-route one is open**: re-raised it is saved at 377.60 (it is now behind the other); the bill-route return, cut to 377.60 when it was saved, is refused at completion: "Line 1: these goods are now worth 720.00 before tax on PI-… where the return claims 320.00, the figure it was cut to when it was saved. … Cancel this return and raise it again, and it will claim what the goods are worth now."; each re-raise then completes: **377.60 and 849.60, 0.00 in all** (the refusal met three times on the way: gaps). **A backdated return raised while another is open**: the earlier-raised, later-dated return is refused at completion with the standing list ("… debit note DBN-… for 400.00 on PI-…; purchase return PR-… for 720.00 on PI-…. … one of those has been approved, completed or raised ahead of it since."), comes to 377.60 raised again, and the backdated one completes at 849.60: 0.00. **A draft saved again with PUT after a later return was saved**: 849.60 stays 849.60 and 377.60 stays 377.60; both complete; 0.00. **4 received, 2 billed, one open off the receipt, then both of the bill's boxes off its own line: 1,699.20**, the bill's full value; the open one completes claiming nothing. **The selling twin** (`s8.py` part t, S1 and N1): a return off the note approved, one on the first bill's line completed, then the first: 422 "Line 1: these goods are now worth 800.00 before tax on SI-… where the return credits 1200.00. Since this return was saved a credit note has been approved against the bill, or another return has taken the units it was priced on. …"; cancelled and raised again 944.00; 2,832.00 against 2,832.00; with no credit note it completes at 1,416.00. Every other scenario of round 8's part t gives round 8's figures |
| D-PRC-82 | **Fixed** | N5 (fresh), S1 | `o8.py` part c on N5: 24 with 2 free typed under the 10% offer: preview SCHEME **60.00 a bill** (and FREE_GOODS 120.00 for the typed units); all of it returned: the offer reads **0 claimed, 1,000.00 left**. Part o (the free units from a second offer): 60.00, 60.00 and 60.00 for the 2 free: **180.00**; returned whole: 0 claimed and 10 free units left; a claim of 180.00 raised, its sale returned, 180.00 carried, the next sale 0.00, the one after 180.00, then nothing carried. **Several lines** (24 + 2 free, 12, 12 + 3 free under two offers, billed 12/6/4 and 12/6/8): SCHEME 240.00 in all; returned: 0 claimed on both offers. **A bill discount an offer set** (5% for one customer, 24 + 2 free): 60.00 off each bill, SCHEME **30.00 a bill**; returned: 0 claimed; the control with nothing free the same. **A line of 2 BOX** (240.00 off, billed 1 BOX and 1 BOX): SCHEME **60.00 a bill**, where a twelfth would be 5.00; with 1 BOX free typed the same, FREE_GOODS 720.00; returned: 0 claimed. **A return after a claim** (claim of 240.00 raised, the sale returned): nothing new, 240.00 carried, raising refused by name; a sale worth 60.00 next: total **0.00**, 180.00 still carried; a sale worth 120.00: 0.00, 60.00 carried; never below zero. The same on S1 for the first four shapes |
| D-PRC-83 | **Fixed** | R1, S3 | Round 8's a6 (`p8.py` part a): 1 BOX and 60.00, then the whole after a cancel: Trade Payables 0.00, **no bill in Record Payment, no supplier credit**. **A full return with its header** (bill 1,799.20, both boxes and the 100.00): the bill is gone from `payments/outstanding`, no credit, the payables report has no row, supplier ageing and the outstanding report list nothing; a payment of 100.00 on the bill: 422 "An allocated invoice does not belong to this party, is not approved, or is already settled in full."; **a debit note of 1.00: refused**, "… 1440.00 billed, 0.00 already claimed, 1440.00 already returned." **60 then 40**: after the first the bill reads 909.60 allocated, **889.60** outstanding in all five readers; after the second, gone. **Off the receipt** with the 100.00: the bill reads 1,799.20 beside a credit of 1,799.20 (unchanged, as designed); applied: gone. **A bill already paid**, then returned with its header: the supplier 1,799.20 in debit, a credit of 1,799.20; half paid: a credit of 899.60. Two bills charging 100.00 and 50.00: 50.01 on the second refused, 50.00 accepted, both gone. 7 PIECE with 33.33 of the charge and 0.07 of round-off: 529.00 comes off the bill, 1,270.20 in every reader. **The payables report equals account 2100** on R1 (79,984.62 when read) and S3, and on every firm at the end. **Round 8's own bills** (PI-…000080 on R1, PI-…000067 on S3), which read 100.00 outstanding beside a credit of 100.00 then, read settled now: gone from Record Payment, no credit, no row in the payables report, the statement closing at 0.00. A firm where that old credit had been applied by hand was not found (round 8's logs show it left unapplied): not driven |
| D-PRC-84 | **Fixed** | S1, N1 | One note in two bills, both boxes back off the note in one return of 2,832.00: the print reads "Against invoice SI-…189 dated 06 Oct 2026", "Against invoice SI-…190 dated 06 Oct 2026", "Delivery note DN-…153". A return on the second bill's own line names that bill alone. **A draft return off the note** prints "DRAFT - NO CREDIT GIVEN YET", names its note and no bill; completed, it names the bill it was set on. **GSTR-1 `cdnr` (N1): one row**, `against_invoice` "SI-…189, SI-…190", `against_invoices` 1,200.00 + 216.00 twice: **2,400.00 and 432.00, the row's own**. Round 8's return (SR-…114) reads the same 2,400.00 and 432.00 it read then, now against both its bills. The day's `cdnr` section gained one row of 2,400.00 and 432.00 for the return and nothing else moved; GSTR-3B: outward supplies +2,400.00 for the bills, -2,400.00 for the return |
| D-PRC-85 | **Fixed** | S1, N1 | A good record followed by one the service refuses, on each of the five: `quotations/import` and `sales-orders/import` "Record 2 of 2: BOX is counted in whole numbers, so 2.5 BOX cannot be entered. Nothing was imported."; `delivery-notes/import` "Record 2 of 2: Line 1 delivers 3 BOX where SO-… has 2 BOX left to deliver of the 2 BOX ordered. … Nothing was imported."; `sales-invoices/import` "Record 2 of 2: Invoice quantity exceeds the available source quantity. Nothing was imported."; `sales-returns/import` "Record 2 of 2: Return quantity exceeds what was dispatched … Nothing was imported." **The count of documents is the same before and after on all five** (the first record is not there), stock and the customer's balance do not move, and the refused record first answers "Record 1 of 2" |
| D-PRC-86 | **Fixed** | S1, N1 | 13 PIECE: "… billed 24 PIECE, and 12 PIECE of that has already come back …, so 12 PIECE is left … where the return brings back 13 PIECE." 6 PIECE: "… 19 PIECE … so 5 PIECE is left … brings back 6 PIECE." 1 PIECE on a line with nothing left: "… 24 PIECE … so 0 PIECE is left … brings back 1 PIECE." A line typed in BOX still speaks BOX (gaps) |
| D-PRC-87 | **Fixed** | S1, S2, N1 | 2 BOX with 0.25 free at create: 422 "Line 1, free quantity: BOX is counted in whole numbers, so 0.25 BOX cannot be entered."; a saved quotation updated to 0.25 free: the same, and it still reads 1 free; 0.5 PIECE free refused the same way. **A product kept in KG, 2 with 0.5 free: saved, and converted to an order of 2 + 0.5** |

## B. A customer's credit set against another bill (D-PRC-75)

Driven on C1 and C2, the same on both unless said; loyalty on S1 and S2. A
bill of 24 at 100.00 is 2,832.00, 7 back is 826.00, a bill of 12 is 1,416.00.

| No | What | Verdict |
| --- | --- | --- |
| 1 | Bill paid, 826.00 returned, a second bill, the credit applied | **Works.** Listed 826.00 available, held 826.00. Applied: bill 2 reads 826.00 allocated, 590.00 outstanding; the customer 590.00 and 0.00; **no journal (252 before and after) and 1100 moved 0.00**; ageing 590.00, statement closes 590.00 with an `ADVANCE_APPLY` row, the outstanding list 590.00. A receipt of 590.01 is refused, 590.00 clears it. The invoice print states no balance (not verified) |
| 2 | The 826.00 refunded in cash in round 7 | **Works as asked**: listed with `refunded_amount` 826.00, nothing available; apply 826.00, apply 0.01 and a refund naming it are refused. **But with money later held on account it comes back as available: D-PRC-91 (Medium)** |
| 3 | B7F: apply, then reverse | **Works.** C1: 1,416.00/826.00 becomes 590.00/0.00; C2: 826.00/826.00 becomes 0.00/0.00 and the bill leaves Record Receipt. Reversed: the customer, the bill, the ageing and the statement read exactly as before; 1100 and the journals never moved. A blank reason and a second reversal are refused |
| 4 | Part apply, refund the rest | **Works.** Held credit: 300.00 applied, 526.01 refused ("has only 526.00 of credit left to be paid back"), 526.00 refunded (Dr 1100 / Cr 1000), nothing left to apply, the refund's row cannot be reversed as an application, the refund reversed frees it; a refund naming no source takes the oldest held credit. A return that landed while another bill was open is held 0.00: it applies, and a refund is refused ("Refund amount exceeds unapplied advance") |
| 5 | Cancel the source, cancel the target, a credit note as source | **Works.** Source return cancelled: the application is withdrawn, bill 2 owes 1,416.00 again, 1100 +826.00. Target bill: 422 "SI-… cannot be cancelled while it has credit applied from SR-…"; reversed, it cancels. A credit note of 472.00 on a paid bill applies (472.01 refused) and is withdrawn when the note is cancelled |
| 6 | The first bill's receipt reversed after its credit was used | **The bills and the account agree while the application stands** (2,832.00 + 590.00 = 3,422.00; ageing and statement the same; both paid: 0.00 and 0.00). **Reversing the application afterwards leaves the customer owing 826.00 on no bill and holding 826.00 from no source: D-PRC-88 (Medium)** |
| 7 | Over-apply, wrong bill, wrong dates, races | **Works.** Fourteen refusals, each by name or by the schema. Nine pairs fired together: two applies of the whole credit, four times: one 200 and one 422 each time; two of 400.00: both 200; two of 300.00 on a bill owing 354.00: one each; an apply against a refund of the same credit, twice: one each; an apply against a receipt on the same bill: 200 and 409 |
| 8 | An opening bill; a note billed in parts; header charges | **Works.** An opening bill of 1,000.00 takes 826.00 and reads 174.00 (its cancel is refused in a receipt's words: **D-PRC-92, Low**). 14 back off a note billed 12 and 12, both paid: one credit of 1,652.00; 1,416.00 applied, 236.00 refunded. 12 back with 60.00 of a header charge on a paid bill: credit 1,476.00 |
| 9 | Collected-basis commission, targets, loyalty | **Works; nothing counts twice.** Figures below |
| 10 | Permissions and cross-firm | **Works.** Viewer: reads, cannot apply, reverse or refund (403). Inventory manager and sales executive: 403 on all four. Cashier with billing executive, and accountant: all four. Another firm's return, bill, application and customer: 404, 422, 404 and an empty list. No token 401; no firm 403 |

**B1, what was read.** `GET /receipts/customer-credits?party_id=`: one row,
`credit_amount` 826.00, `available_amount` 826.00, `held_amount` 826.00.
`POST …/{source}/apply` 826.00: 200, `applied_to` the second bill. The
audit trail holds `customer_credit.applied` with `advance_amount` 826.00.
The statement before reads the return as a row of 0 and 0 (the 826.00 went
to the advance) and closes at 1,416.00; after, an `ADVANCE_APPLY` credit of
826.00 closes it at 590.00.

**B4, the one that is held 0.00.** Bill 1 paid, bill 2 open, then 7 back on
bill 1: the 826.00 comes straight off what the customer owes (590.00 and
0.00), bill 2 still reads 1,416.00 and the ageing shows `unapplied_credits`
826.00. Applying 400.00 and then 426.00 moves nothing on the customer and
brings bill 2 to 590.00: bills and account agree.

**B5, a second return after a credit was used.** The 826.00 applied to bill
2, then all of bill 2 returned (1,416.00): the customer holds 826.00 again,
now as the second return's credit, which applies to a third bill. And the
other 17 of bill 1 returned after its first return's credit was used:
a credit of 2,006.00, 590.00 of it applied to bill 2 and 1,416.00 refunded:
0.00 and 0.00.

**B7, the refusals.** "SR-… has only 826.00 of credit left to set against a
bill."; "SI-… owes only 354.00."; another customer's bill, the paid first
bill and an unknown bill id: "That bill is not this customer's, is not
approved, or is already settled in full."; tomorrow: "A credit cannot be
applied on a future date."; yesterday: "SR-… is dated 2026-10-06 and SI-…
2026-10-06: the credit meets the bill on or after both."; 0, -5, 1.005 and
an unknown field: the schema; an unknown id and a bill's id as the source:
404; a draft return: "… leaves no credit on the customer's account: it is
not completed, or its bill still owed everything it credited."

**B9, what was read (C1, C2).** Product VH8 (the firm-wide 4% on collected
money):

| Step | Commission | Collected | Invoiced and target |
| --- | --- | --- | --- |
| Bill 1 of 2,832.00 | 0.00 | 0.00 | +2,832.00 |
| Paid in full | +96.00 | +2,832.00 | |
| 7 returned | -28.00 | -826.00 | -826.00 |
| Bill 2 of 1,416.00 | 0.00 | 0.00 | +1,416.00 |
| The 826.00 applied to bill 2 | **+28.00** | **+826.00** | 0.00 |
| In all so far | +96.00 | +2,832.00, the cash received | +3,422.00 |
| The application reversed, then applied again | -28.00, +28.00 | -826.00, +826.00 | |
| The 590.00 left paid | +20.00 | +590.00 | |
| In all | **+116.00** | **+3,422.00** | +3,422.00 |

The control (the 826.00 refunded in cash instead): +68.00 and +2,006.00. A
product on the invoiced basis (VD6, 5%): the application moves commission,
invoiced value and the target by 0.00. **Loyalty (S1, S2)**: the points do
not move when a credit is applied, and a redemption is capped at what the
bill owes after it: 1,200 and 600 points against a bill owing 590.00 are
refused ("SI-… owes only 590.00, and those points are worth 600.00."), 590
clear it.

## C. The probes

| No | Probe | Verdict |
| --- | --- | --- |
| 1 | The purchase twin of D-PRC-82 | **The discount is not spread over the free units**: the purchase side divides by the charged quantity, and bills, Goods Received Not Invoiced, stock value and payables agree with the order in every shape where the discount is a rate or a header amount. **But with the receipt stage off, a bill raised off the order in parts receives the order line's whole free quantity each time: D-PRC-90 (High).** R1, S3 |
| 2 | A return placed on a bill by the delivery-note route, on a firm that e-invoices | **It skips the check, and more: D-PRC-89 (High).** Driven on N1 and N5 |
| 3 | A spilled bill-route return and Record Payment | **Unchanged from round 8 (a gap, not a new finding).** The other bill takes a payment of its full 1,699.20 while 849.60 is owed (the supplier ends 849.60 in debit); the payables report equals account 2100; the supplier ageing and the outstanding report do not net the credit. R1, S3 |
| 4 | Anything else | D-PRC-88, 91 and 92 (section B) |

**C1, what was read (R1, S3, the same on both).** A fresh product and
supplier each time; 24 PIECE at 60.00 with 2 free.

| Scenario | Order | Bills | Free in | Stock | Accounts |
| --- | --- | --- | --- | --- | --- |
| Stages on; 10%; whole, and in two parts | 1,529.28 | 1,529.28 | 2 | 26 at 1,296.00 | 2100 +1,529.28, 1200 +1,296.00, tax 233.28, 2300 0.00 |
| Stages on; header discount 100.00; whole, and in two parts | 1,581.20 | 1,581.20 (50.00 a part) | 2 | 26 at 1,340.00 | agree |
| Stages on; a supplier scheme (buy 12 get 1) and 10%; two parts | 1,529.28 | 1,529.28 | 2 | 26 at 1,296.00 | agree |
| Receipt stage off; 10%, or 144.00 typed; whole | 1,529.28 | 1,529.28 | 2 | 26 at 1,296.00 | agree |
| Receipt stage off; 144.00 off; two parts, 1 free typed on each bill | 1,529.28 | 764.64 + 764.64 | 2 | 26 at 1,296.00 | agree |
| Receipt stage off; header 100.00, and header with 144.00; parts and whole | 1,581.20; 1,411.28 | the same | 2 | 26 | agree |
| **Receipt stage off; two parts, nothing typed free** | 1,529.28 | 1,529.28 | **4** | **28** at 1,296.00 | money agrees: **D-PRC-90** |
| **Receipt stage off; the scheme's free goods; two parts** | 1,529.28 | 1,529.28 | **4** | **28** | **D-PRC-90** |
| Stages on; 144.00 off typed; each receipt sent 72.00 as an amount | 1,529.28 | **1,699.20** | 2 | 26 at 1,296.00 | 5400 +144.00 (gaps) |

## D. Regression: not run

Skipped, as the brief directs, because sections A to C produced two new
High findings. Not run: lines sold by the box, buying by the box, the rate
difference claim, promotion budgets and principal claims by round 3's
scripts, the twelve TC-INCENT cases, and the generic bad-input checks. What
this round's own scripts exercised of them is in A (D-PRC-82: budgets and
claims with free goods, by `o8.py` and `o9.py`), B10 and B7 (some thirty
cross-firm, permission and bad-input requests on the new routes), and A
(D-PRC-85: ten import refusals a firm).

**The books at the end, all thirty-five firms.** Every trial balance
balances; no journal is unbalanced (between 1 and 1,721 journals a firm).
The firms this round wrote to:

| Firm | Trial balance | 1100 = customers less advances | 2100 = bills outstanding less supplier credits = payables report | 2600 = points' worth | 2400 = approved unpaid | 1420 = open claims | 1200 against valuation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 13,294,875.96 | 255,670.62 | 29,063.40 | 6,306.10 | 0 | 581.52 | 12,563,960.08 against **12,563,960.10** |
| S2 | 10,919,335.81 | 191,551.41 | 29,063.40 | 4,732.73 | 0 | 526.06 | 10,488,460.10 against **10,488,460.12** |
| S3 | 566,316.39 | 7,761.85 | 114,553.90 (165,219.40 less 50,665.50) | 155.23 | 0 | 63.54 | 530,698.92 against **530,698.81** |
| N1 | 2,384,057.47 | 85,711.13 | 33,320.84 (61,902.80 less 28,581.96) | 1,917.00 | 0 | 229.40 | 2,033,182.27 |
| N5 | 2,026,479.01 | 11,469.60 | 0 | 229.41 | 0 | 600.00 | 1,979,160.00 |
| R1 | 129,354.31 | 1,270.00 | 104,830.70 (164,487.80 less 59,657.10) | 0 | 0 | 0 | 109,632.19 against **109,632.10** |
| C1 | 2,630,486.50 | 59,591.67 (71,945.67 less 12,354.00) | 21,240.00 | 0 | 187.50 | 0 | 2,296,080.00 |
| C2 | 2,525,740.00 | 54,815.67 (66,343.67 less 11,528.00) | 0 | 0 | 85.00 | 0 | 2,226,720.00 |

The other twenty-seven read what round 8's table gives them, to the paisa.
Receivables, payables net of supplier credits, Loyalty Payable, commission
and claims agree with their sub-ledgers on every firm, and the payables
report's total equals account 2100 on every firm. What does not come out
clean: D-PRC-56, left on purpose, now 0.02 on S1 and S2, **0.09 on R1 and
0.11 on S3** (0.04 each in round 8; this round returned about 150 boxes
there), 0.02 on P1 and P2; and what the findings left, which the books
carry faithfully: on C1 two customers and on C2 one owing 826.00 on no
bill and holding 826.00 (D-PRC-88), and two phantom free units a firm on
two products of R1 and S3 (D-PRC-90; quantity only, the value is right).
Bills in Record Receipt against the customers' accounts differ on S1
(3,786.00), S2 (571.99), N1 (3,214.00) and C1 (C4, 1,652.00) by the
`unapplied_credits` the ageing shows, as in round 8.

## Findings

Ids continue from D-PRC-87. High = wrong money, tax or stock, or a control
that can be bypassed; Medium = wrong behaviour with a workaround; Low =
wording, paisa, cosmetics. Causes are from reading the code named, not from
a debugger.

| Id | Severity | Module | What | Firms | Where from |
| --- | --- | --- | --- | --- | --- |
| D-PRC-88 | Medium | Finance (settlements, customer credit) | Reversing a credit application after the source's own bill came to owe again (its receipt reversed) puts back an advance the credit no longer holds: with everything paid the customer owes 826.00 on no bill and holds 826.00 from no source, and the 826.00 can be refunded in cash | C1, C2 | B6 |
| D-PRC-89 | **High** | Compliance (e-invoice), selling | A sales return off a delivery note that credits a bill prints as a valid credit note with no IRN on a firm that must e-invoice, is not in the pending registrations and is refused registration as crediting "no tax invoice", while its print and GSTR-1 name the invoice | N1, N5 | C2 |
| D-PRC-90 | **High** | Buying (inventory) | With the receipt stage off, a supplier bill raised off an order in parts receives the order line's whole free quantity on each part: 4 free units in stock where 2 were ordered | R1, S3 | C1 |
| D-PRC-91 | Medium | Finance (settlements, customer credit) | A credit paid back before credits were tracked reads as available again once the customer holds other money on account; applied, it spends that money and strands the receipt that brought it | C1, C2 | B2 |
| D-PRC-92 | Low | Finance (wording) | Cancelling an opening bill a credit is set against is refused in a receipt's words: "826.00 has been received against OBC-…. Reverse those receipts before cancelling it." | C1, C2 | B8 |

### D-PRC-88: a reversed application puts back an advance that is no longer there (Medium, finance)

C1 21:17 and 21:20 IST (`cc9.py` part f), C2 21:22. The same on both.

1. A bill of 2,832.00 paid in full by receipt; `POST /sales-returns` of 7
   on its line, completed: 826.00; the customer reads 0.00 owed and 826.00
   held.
2. A second bill of 1,416.00. `POST /receipts/customer-credits/{return}/apply`
   826.00: 200; bill 2 reads 590.00; the customer 590.00 and 0.00.
3. `POST /receipts/{first}/reverse`: 200. Bill 1 reads **2,832.00**, bill 2
   590.00, the customer 3,422.00 and 0.00: right, and the credit reads
   `credit_amount` 0 with 826.00 applied.
4. `POST /receipts/customer-credits/applications/{id}/reverse`: 200. The
   bills read 2,006.00 and 1,416.00 (3,422.00: right). **The customer reads
   4,248.00 owed and 826.00 held**; the ageing: `total_outstanding`
   3,422.00, `account_balance` 4,248.00, `charges_not_billed` 826.00; the
   credits list is empty.
5. Receipts of 2,006.00 and 1,416.00: both bills leave Record Receipt.
   **The customer reads 826.00 owed and 826.00 held**, the statement closes
   at 826.00, the ageing lists nothing, and there is no credit to apply.
6. `POST /refunds` 826.00, no source named: **201**, Dr 1100 826.00 / Cr 1000
   826.00; the customer then owes 826.00 with no bill (reversed).

The control, the same without step 4: both bills paid as they read
(2,832.00 and 590.00): 0.00 and 0.00. And the source return cancelled at
step 4 instead: 4,248.00 and 0.00, bills 2,832.00 and 1,416.00: right.

**Expected:** everything billed is paid or returned (4,248.00 = 826.00 +
2,006.00 + 1,416.00), so the customer owes nothing and holds nothing, as
the control reads. `docs/LEDGER_POSTING_RULES.md`: "A reversed receipt puts
used credit back on its bill": after step 3 the return's 826.00 is no
longer an advance, it is part of what bill 1 does not owe. **Actual:** the
reversal goes back "by that row's own deltas": +826.00 owed and +826.00
held, the split the application made when the credit was an advance.
Account 1100 is right throughout; the customer's two figures are both
826.00 too high, the statement tells the customer they owe 826.00, and the
feature built to end "owes 826.00 on one line and is owed 826.00 on
another" has no route out of it. Workaround: do not reverse the
application; pay the bills as they read.

**Suspected:** `app/settlements/services/customer_credits.py:1036` to `:1056`
(`_take_back`: `reverse_receivable_transaction` on the stored row whatever
the credit now gives), called from `reverse_customer_credit_application` at
`:1081`; `drawn_back_onto_bills` at `:697` already knows the credit is short.

### D-PRC-89: a return off the note that credits a bill is outside e-invoicing (High, compliance)

N1 21:32 IST, N5 21:36 (`g9.py`). The same on both. Round 8 read the print's
gate in code and could not drive it; it was driven here by setting
`PUT /tax-framework/gst-compliance-settings` `einvoice_applicable_from` to
today for the run and clearing it after.

A customer with a GSTIN; one delivery note of 2 BOX in two bills. R-note: 1
BOX back **off the note**, completed, 1,416.00, placed on the first bill.
R-bill: 1 BOX back on the second bill's own line, completed, 1,416.00.

| Asked | R-bill (the bill's own line) | R-note (off the note) |
| --- | --- | --- |
| `GET /sales-returns/{id}/print` | **422** "SR-… has no IRN yet. The firm e-invoices from 06 Oct 2026 and the buyer is registered for GST, so it is not a valid tax invoice until it is registered on the portal (CGST rule 48(4)). …" (`irn_required`) | **200**, a credit note reading "Against invoice SI-… dated 06 Oct 2026", no banner |
| The same with `reference_copy=true` | 200 with "NO IRN YET - NOT A VALID TAX INVOICE" | 200, **no banner** |
| `GET /einvoice/pending` | listed | **not listed** |
| `POST /einvoice/sales-returns/{id}/register` | reaches the portal checks (refused here for a product with no HSN code) | **422** "SR-… returns goods no invoice billed, so it credits no tax invoice and is not registered." |
| GSTR-1 `cdnr` | one row against its bill, 1,200.00 and 216.00 | one row against its bill, 1,200.00 and 216.00 |

The bill itself is refused at print the same way as R-bill.

**Expected:** `docs/GST_DOCUMENT_COMPLIANCE.md` (D-TAX-2, A45): "a completed
return of billed goods registers as a CRN naming each invoice it returns
goods from; a return of goods never invoiced is not registered", and
`docs/SALES_CHAIN_RULES.md` (D-PRC-84): a line off a delivery note names
the bills its stored placements name. R-note returns billed goods: its own
print and GSTR-1 say which invoice. **Actual:** three readers ask "does the
return have a line whose source document is a sales invoice", and a return
off the note has none whatever it was placed on. So the control at print is
passed by the route the return was raised by, and the firm cannot register
the credit note even when it wants to. It is the route the product itself
sends users down: the refusal for a bill line whose units are back says
"Raise the return off DN-… instead". Workaround: raise returns of billed
goods on the bill's own line where units are left on it; none for a return
already completed off the note.

**Suspected:** `app/sales_return/services/credit_note_print_service.py:134`
to `:146` (`_credits_an_invoice`); `app/einvoice/services/note_registration.py:176`
to `:203` (the lines read, and the refusal); `app/einvoice/services/reporting_window.py:180`
to `:195` (the pending list). `bills_credited` in `app/sales_return/billing.py`
already answers the question for the print and GSTR-1.

### D-PRC-90: a bill off an order in parts brings the free goods in again each time (High, buying)

R1 21:34 IST, S3 21:35 (`c9.py` scenarios 10 and 15). The same on both.

1. `PUT /purchases/workflow-settings` with `goods_receipt_stage` false (put
   back at the end).
2. `POST /purchases`: a fresh product, 24 PIECE at 60.00, `free_quantity` 2,
   `discount_amount` 144: 1,529.28, approved.
3. `POST /purchase-invoices` off the order line (`source_document_type`
   `PURCHASE_ORDER`), `current_invoice_quantity` 12, nothing typed for the
   free goods; approved: 764.64. The receipt it raised: 12 with
   **`free_quantity` 2**.
4. The same again for the other 12: 764.64. Its receipt: 12 with
   **`free_quantity` 2**.

**Stock on hand 28; the order's line says 24 and 2 free.** The valuation
reads 28 at 46.2857 (1,296.00) where 26 at 49.8462 came in; the bills, the
tax, payables and the stock **value** agree with the order. With the free
goods given by a supplier scheme (buy 12 get 1, nothing typed on the order):
the same 4 and 28. With `free_quantity` 1 typed on each bill: 2 and 26. In
one bill: 2 and 26. With the receipt stage on, where the receipt states its
own free goods: 2 and 26.

**Expected:** the order line's free goods come in once; a part of the line
brings its share, or the bill is asked. **Actual:** each receipt the bill
raises takes the bill line's free quantity or, where it is blank, the order
line's whole figure. Two units that never arrived are saleable, the stock
count is out, and the average cost of everything on the shelf is diluted.
Workaround: type the free quantity on every part bill.

**Suspected:** `app/purchase_invoice/services/purchase_chain_service.py:320`
to `:324` (`_receipt_line`: `free = bill_line.free_quantity if … else
order_line.free_quantity`), eleven lines under the discount that is
pro-rated by `quantity / order_line.ordered_quantity`.

### D-PRC-91: a credit paid back before credits were tracked comes back beside other money (Medium, finance)

C2 21:21 IST (`cc9.py` part b), C1 21:33 (part x). The same on both.

Customer B7G: a return of 826.00 on a paid bill, refunded in cash in round
7, before `customer_credit_applications` existed. Listed today:
`credit_amount` 826.00, `refunded_amount` 826.00, `available_amount` 0.00;
apply and a refund naming it are refused. Then, with nothing owed:

1. `POST /receipts` 500.00 naming no bill: the customer holds 500.00.
2. `GET /receipts/customer-credits`: the return now reads
   **`refunded_amount` 326.00, `available_amount` 500.00, `held_amount`
   500.00**.
3. A bill of 708.00. `POST …/{return}/apply` 500.00: **200**. The bill reads
   500.00 allocated; the customer 208.00 and 0.00.
4. The receipt still reads `unallocated_amount` 500.00, and
   `POST /receipts/{id}/allocate` 208.00 is **422** "Advance apply amount
   exceeds unapplied advance."

**Expected:** `docs/LEDGER_POSTING_RULES.md`: "the credit paid back cannot
be applied as well"; the 500.00 is the receipt's. **Actual:** a refund with
no row is inferred from how far the customer's advance falls short of the
credits held, so any advance from another source reads as the credit not
having been refunded. The customer's totals stay right; the bill is settled
by the wrong document and the receipt cannot be allocated. Only credits
refunded before migration `20261006_0348` are exposed. Workaround: reverse
the application, then allocate the receipt (driven: both 200).

**Suspected:** `app/settlements/services/customer_credits.py:671` to `:692`
(`customer_credits`: `gone = held - on_account`, with `on_account` the
customer's whole `unapplied_advance_balance`).

### The Low finding

- **D-PRC-92 (finance, wording).** C1 21:20 IST, C2 21:23 (`cc9.py` part h).
  An opening bill of 1,000.00 with 826.00 of a return's credit set against
  it; `POST /customers/opening-bills/{id}/cancel`: 422 "826.00 has been
  received against OBC-00002. Reverse those receipts before cancelling it."
  No receipt exists; a sales invoice in the same position names the
  document ("… while it has credit applied from SR-…"). Suspected:
  `app/customers/services/opening_bill_service.py:392` to `:398`, which sums
  receipts, adjustments and applied credit into one figure and one sentence.

## Case text to correct

Round 3's to round 8's tables still stand; nothing in them was applied.
Changes, for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| Round 8's held-back cases | Can be written as passing: cancelling a supplier bill under a return off its receipt (422 by name; the bill nothing was placed on cancels); two purchase returns open by two routes, completed in either order (849.60 and 377.60, 0.00 in all); a principal claim for a discount on a line with free units (60.00 a bill; 0 claimed after the return); a purchase return's header charge (the bill reads 889.60, then is gone); the credit note print ("Against invoice …" for each bill) |
| New cases wanted | (1) a customer's credit applied to another bill (826.00; 590.00 left; no journal); (2) applied and reversed (as before); (3) part applied, the rest refunded naming the source (526.01 refused); (4) cancelling the source return and the target bill (withdrawn; refused by name); (5) a credit applied on the collected basis (+28.00 and +826.00, once); (6) a service refusal as record 2 of each selling import ("Record 2 of 2: … Nothing was imported."); (7) 0.5 free on a product kept in KG |
| Hold back until fixed | Reversing an application after the first bill's receipt was reversed (D-PRC-88); the credit note of a return off the note on a firm that e-invoices (D-PRC-89); a supplier bill off an order in parts with free goods and the receipt stage off (D-PRC-90) |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.

- **A receipt line whose discount is an amount passes none of it to its
  bill** (R1, S3). The rule is written ("a rate is inherited and an absolute
  amount is not"), but the receipt keeps no rate for an amount where the
  order does (144.00 typed on the order reads 10%), so two receipts of
  764.64 were billed 849.60 each: 1,699.20 against an order of 1,529.28,
  144.00 to Purchase Price Variance, approved with no refusal. A receipt
  line sent no discount at all values the stock at 1,440.00 and bills the
  same 1,699.20: the order's discount is not carried to a receipt unless the
  client sends it.
- **Two returns left open can be sent round in a circle** (R1, S3, N1): with
  both approved, each cancel-and-raise-again puts that return behind the
  other, and the "cut to" refusal was met three times before both
  completed. Completing each straight after raising it again ends it; the
  totals are exact either way.
- **A return that cannot be cancelled because its credit was refunded is not
  told why** (C1, C2): "Reversing this would drive the customer's balance
  negative. It has been overtaken by later transactions." The refund is not
  named; `docs/LEDGER_POSTING_RULES.md` says the refund "stops naming it"
  and stands, which holds only where the customer holds other money.
- **Two sign-ins of one user at the same instant: one answers 409**
  "Concurrent update rejected" (C1, C2, eighteen times in the first run).
- **The invoice print states no balance**, so a credit set against a bill is
  not on its paper; the one figure it draws from what the bill owes is the
  UPI QR amount, and no fixture firm has a UPI id.
- **A return on a paid bill reads as a row of 0 and 0 on the customer's
  statement** until its credit is applied (C1, C2): the 826.00 goes to the
  advance, which the statement does not show.
- **A line typed in BOX is still answered in fractions of a BOX** (S1, N1):
  "… 1.5833 BOX of that has already come back …, so 0.4167 BOX is left …
  where the return brings back 1 BOX." As written: a line typed in the bill
  line's own unit speaks it.
- **After one of two supplier bills is cancelled, an open return off the
  receipt completes on the box no bill charges and claims nothing** (R1, S3,
  N1), while stating 849.60; the bill that was refused cancelling "while it
  has purchase return PR-…" goes on owing in full. The buying twin of round
  8's selling gap; each step follows its rule.
- **A claim of 0.00 is raised and reads SETTLED** where what came back
  after earlier claims covers a new sale (N5): two of them, each using up
  part of the 240.00 carried.
- **The supplier ageing and the suppliers' outstanding report do not net a
  supplier credit**, and **a supplier's bill can be paid in full while a
  credit stands** (R1, S3): round 7's gaps, unchanged (C3).
- Round 8's other gaps were not driven again.

## Left on the firms

- **C1 and C2**: about twenty-five new customers each (B9 and a letter);
  product V9S with 30,000 of opening stock; **customers owing 826.00 on no
  bill and holding 826.00** (B9I1 on both, B9I2 on C1: D-PRC-88); B9T with a
  credit of 826.00 beside a bill of 1,416.00, B9J with 472.00 of credit
  beside 1,416.00, B9G and B9N holding credits with no bill; B7F as it was;
  B7G with its bills paid, two receipts of 500.00 allocated and its old
  return reading 326.00 refunded; about ten refunds each, half reversed;
  six receipts reversed; one cancelled return and one cancelled credit note
  each; an opening bill of 1,000.00 paid (and on C1 one more, unused, on
  B9L1). On C1 300 VD6 bought from a new supplier (a bill of 21,240.00,
  unpaid). Advances held: 12,354.00 on C1 and 11,528.00 on C2.
- **S1 and S2**: customer B9S with 978.44 points after an adjustment of
  1,500 (Loyalty Payable is that much higher), one bill settled by a credit
  and points. **S1**: offers A9D, B9D, B9E, C9B and D9D retired, four
  principals with their brands and products, customer B9O; product Z9K (kept
  in KG) and a cancelled order of it; about thirty bills returned in full.
- **N1**: the same selling scenarios as S1; about forty new suppliers
  (V9nn); the GST compliance settings now read `is_configured` true with no
  e-invoicing date, as found otherwise; two returns printed during C2.
- **N5** (new): a GST number (29AAGCB7391J1Z4) and one for customer PC;
  offers P8D, O8D, O8F and five of `o9.py` retired; **three claims RAISED**
  (180.00, 180.00 and 240.00, the last for a sale since returned, 60.00 of
  it still to come off the next claim) and two of 0.00 SETTLED; five orders
  of the claim scenarios out and billed.
- **R1 and S3**: about seventy new suppliers each (V8nn continued, V9nn,
  VQnn) and sixteen products (NQ01 to NQ16), **NQ10 and NQ15 holding 28
  where 26 came** (D-PRC-90); two supplier schemes; suppliers in debit by
  1,799.20 and 899.60 (returns after payment, D-PRC-83's scenarios) beside
  round 8's; supplier credits unapplied beside bills; four payments each,
  two reversed; purchase stages put back as found.

## Not verified

- **Nothing on screen.** The desktop was not opened.
- **Nothing was read from the database.** That the server runs `1e16df78`
  and that the head is `20261006_0348` on every store were taken from the
  hand-over and from the fixes and the new routes behaving as merged.
- **Everything ran once, in one window** (21:05 to 21:39 IST).
- **Section D**: not run (above).
- **The invoice print against a credit**: the print states no balance, and
  its UPI amount was not driven.
- **One firm where two would be better**: GSTR-3B and GSTR-1 for a customer
  with a GSTIN (N1); D-PRC-82's return after a claim (N5).
- **D-PRC-89 with a real registration**: the fixture products have no HSN
  code, so no document reached the sandbox portal; the bill-route return
  was shown to get as far as the portal checks and the note-route one was
  refused before them.
- **D-PRC-90 with a line bought by the box, with batches, or in three
  parts**; and whether a receipt typed by hand may bring in more free goods
  than the order states.
- **Section B on a firm with a GST number**, a credit applied on a day after
  its documents, the ageing as of an earlier day, and a payout raised over a
  period holding an application (`POST /commission/payouts/preview`
  answered 405; the report was read instead).
- **A legacy refund beside a credit of another return** (D-PRC-91 was driven
  with one credit a customer).
- **D-PRC-83 where the old 100.00 credit had been applied to its bill by
  hand before the fix**: no firm carries one that I could find; whether such
  a bill then reads settled twice over is not known.
- **D-PRC-80's and D-PRC-83's further shapes against GSTR-3B** on more than
  N1; D-PRC-84 and D-PRC-85 on S2.
