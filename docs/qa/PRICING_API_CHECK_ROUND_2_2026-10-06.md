# Pricing, promotions, loyalty, commission and targets: checked through the API, round 2, 2026-10-06

The second pass over this module, driven the way round 1 was: the real server
over HTTP at http://127.0.0.1:8000 (version 1.3.0, `main` at `292de2be`),
fresh fixture firms only, books read back through the API, nothing read from
the database, no source file changed and nothing fixed.

**The round found new things: five High, five Medium and four Low
(PRCQ-22 to PRCQ-35), none of them a regression from the fixes.** Three of
the High ones are the gaps the fixers themselves flagged and left open
(section C), now with figures.

**Of the 21 findings of round 1, 20 are fixed and one is partly fixed**
(PRCQ-17: `expiring_soon` is right; the paisa between Loyalty Payable and the
balances report was not seen on any of fifteen firms, so it could be neither
confirmed nor called fixed). Every fix was driven by its round 1 reproduction
on two firms. **Both features built since round 1 work as specified** (the
scheme budget, and free goods in the claim to the principal). **The twelve
cases give what they gave in round 1** apart from what the fixes changed;
007 still cannot be run as written.

## When, and on which firms

Fifteen fixtures were built between 06:36 and 06:45 IST and everything was
driven between **06:46 and 07:08 IST on 6 October 2026, which is 01:16 to
01:38 UTC on the same day**: this time the server's UTC day and the firm's
day agreed (round 1 ran with UTC a day behind). The server was not restarted
and `/health` answered before and after. **No request answered 500.** Three
reads failed in transit (connection reset by the server) and were sent again;
all three were `GET`s.

| Key | Fixture | Firm | Used for |
| --- | --- | --- | --- |
| S1 | `selling-firm` | `T1006T74U-S` | cases 004, 001, 002; A: PRCQ-1, 2, 4, 5, 8, 10 to 16; generic checks |
| S2 | `selling-firm` | `T1006NEI8-S` | the same again |
| S3 | `selling-firm` | `T1006CCU2-S` | cases 011, 009; B: budgets (second firm); C7 |
| S4 | `selling-firm` | `T100656D6-S` | B: budgets; C7 |
| S5 | `selling-firm` | `T10069HPV-S` | B: free goods in the claim; C8; C1 to C4, C6 (second firm) |
| S6 | `selling-firm` | `T1006UM6W-S` | the same; C1 to C4, C6 first |
| L1 | `loyalty-points` | `T1006DGIM-S` | case 005; PRCQ-3, 6, 17, 21; C5 |
| L2 | `loyalty-points` | `T1006SHNY-S` | cases 010, 005 again; the same |
| C1 | `commission-firm` | `T10061JYX-T` | cases 006, 008, 007 (with sales dated yesterday); PRCQ-9, 19, 20 |
| C2 | `commission-firm` | `T1006CCBY-T` | cases 006, 008, 007 as written and then as C1; the same |
| P1 | `pharma-firm` | `T10064796-P` | PRCQ-7, 18 |
| P2 | `pharma-firm` | `T10065HTS-P` | the same again |
| D1 | `selling-invoiced` | `T10069EEM-S` | case 012 |
| D2 | `selling-invoiced` | `T1006MGE2-S` | case 012, second run |
| O1 | `selling-ordered` | `T1006XAJP-S` | case 003 |

Scripts and logs are in the scratchpad folder `pricing2`, beside `pricing1`;
round 1's helpers and case scripts were copied, not changed. Every script and
edit went through the file tool. Outputs of the same script on two firms were
compared line by line after masking ids and times; where this document says
"the same on both" that comparison came back empty.

## A. The 21 findings of round 1

| Id | Verdict | Firms | Evidence |
| --- | --- | --- | --- |
| PRCQ-1 | **Fixed** | S1, S2 | 60 DET for C01: order, note and bill all **5,265.16**; bill `bill_discount_amount` 200.00, `bill_discount_source` `inherited`; Dr 1100 5,265.16 / Cr 4000 4,462.00 / CGST 401.58 / SGST 401.58. Typed 100 off: **873.20** down to the bill (Cr 4000 740.00, 66.60 + 66.60). Typed 10% with freight 50: **951.08** (806.00, 72.54 + 72.54). Details below |
| PRCQ-2 | **Fixed**, with two holes the fix names | S1, S2 | 2 DET at a typed 42.00: `POST …/approve` as the sales manager **422** "Line 1 is priced at 42.00 where the customer's price is 84.00: 50.00% off in all, above your limit of 5.00%. It needs approval by someone allowed at least 50.00%." Details below; the holes are PRCQ-23 and PRCQ-24 |
| PRCQ-3 | **Fixed** | L1, L2 | A batch of 70.8000 lapsed on 2026-09-27: `GET /loyalty/{customer}` reads `points` 2.3600, `lapsed_points` 70.8000, `redeemable` false. Redeem 70: **422** "That customer holds 2.3600 points, not 70.0000. 70.8000 more ran out of time on 2026-09-27 and can no longer be spent." Details below |
| PRCQ-4 | **Fixed** | S1, S2 | Order of 12 + 1 free (FREE11); a note of 12 with `free_quantity` absent ships **13** (stock 290 to 277, nothing left reserved), the order reads DELIVERED, the bill reads 12 + 1 free. Details below; two drafts at once is PRCQ-29 |
| PRCQ-5 | **Fixed** | S1, S2 | Twelve conditions and four benefits naming an unknown or the other firm's record: **422** "Condition 1: the product was not found in this firm." (and category, customer, customer group, branch, territory, route; "Benefit 1: the free product…", "Benefit 1: a product of the combo…"). An edit of a live offer is refused the same way. FREE_PRODUCT with **no buy quantity**, ACTIVE: a quotation and an order of 9 answer **201** with the gift line (0 charged, 1 free); approved, claimed with `free_quantity` 1 |
| PRCQ-6 | **Fixed** | L1, L2 | A bill of 118.00 with 10 points spent: `POST …/cancel` **200**; `LOY-RED-SI-…-REV` Cr 2600 10.00 / Dr 1100 10.00, a REDEEMED entry of +10.0000 "10.0000 points put back from SI-…: SI-… cancelled.", balance back to 69.6642, the customer owes 343.21 as before the bill. Details below |
| PRCQ-7 | **Fixed** | P1, P2 | B3 (MRP 120.00) pinned at 130.00: `POST /sales-orders` **422** "Line 1: charges 145.60 a unit with tax, above the MRP of 120.00 printed on the batch it ships."; the same on an edit up to 130 and at 108.00 (120.96 with tax). A counter bill naming B3 at 130: 422 at save. Unpinned order at 130 (every batch given an MRP): the note saves and approves, **dispatch 422** naming the MRP 110.00 of the batch it would ship; the batch still holds its 8. A counter bill with no batch named: 422 at approval |
| PRCQ-8 | **Fixed** | S1, S2 | Bill of 12 + 1 free: 14 back is **422** "…(12.0000 sent and 1.0000 free, 0.0000 and 0.0000 already returned; line 1 can still bring back 12.0000 charged and 1.0000 free)."; 12 back credits 1,079.42; **1 more: COMPLETED, total 0.0000, `free_quantity` 1**, stock +1, the customer's balance unmoved. Details below |
| PRCQ-9 | **Fixed** | C1, C2 | `paid_on` three days ahead and tomorrow: **422** "A payout cannot be paid on a day that has not happened yet." Yesterday: **422** "A payout cannot be paid before it was approved (approved on 2026-10-06)." Today: 200, `COMM-202610-…-PAY` Dr 2400 190.00 / Cr 1010 190.00 |
| PRCQ-10 | **Fixed** | S1, S2 | The coupon, performance and redemptions reports carry `free_quantity`: FREE11 2 claims, benefit 0.0000, free 2.0000; GIFT7 free 1.0000. The benefit stays 0 by rule (free goods take nothing off a bill) |
| PRCQ-11 | **Fixed** | S1, S2 | `search=WELCOME-NOV`, `NOV` and `welcome-nov` each find WELCOME-NOV; `WELCOME` finds both |
| PRCQ-12 | **Fixed** | S1, S2 | Price list with another firm's or an unknown product: 422 "Row 1: the product was not found in this firm."; customer: 422 "The customer this price list names was not found in this firm."; two rows at one break: 422 "Row 2: …-DET already has a rate from a quantity of 5 on row 1. A product takes one rate at each quantity."; a used code: 409 "A price list with the code STANDING already exists."; an edit of a superseded offer row: 409 "This is revision 2 of offer BULK5, and revision 3 has replaced it. Open the current revision and edit that one." |
| PRCQ-13 | **Fixed** | S1, S2 | `POST` and `PUT /price-levels` answer `ETag`; `If-Match: "99"` **409** "This record changed since you loaded it. Reload and try again."; the current version 200 and `ETag "2"`; the old one again 409; none sent 200 |
| PRCQ-14 | **Fixed** | S1, S2 | After a bill of 2 G5 at 100 with no discount: by customer, by product and by salesman all total gross **22,661.99** and discount 2,017.20; the undiscounted product has its row |
| PRCQ-15 | **Fixed** | S1, S2 | MRP 40 under selling 50: 422 "MRP must be greater than or equal to selling price."; dated three days back and yesterday: 422 "New rates start today (06-10-2026) or later, not from 03-10-2026. A price dated back would change today's price without saying so; date it today instead."; with a revision of 86.00 from today the product read and the list row show `selling_price` 84.00, `selling_price_in_force` 86.0000, and a quotation takes 86.00 |
| PRCQ-16 | **Fixed** | S1, S2 | ONE1 with its offer switched INACTIVE: `status` INACTIVE, `own_status` ACTIVE, `offer_status` INACTIVE on the read, the list and the report; with the code itself switched off, all three INACTIVE |
| PRCQ-17 | **Partly** | L1, L2, and all 15 | `expiring_soon` reads 0.0000 for the customer holding a lapsed 70.8000 (round 1: 70.8000). **The paisa was not seen**: Loyalty Payable equals the balances report (`amount` + `lapsed_amount`) at fourteen readings each on L1 and L2, through redemptions of 100.3333 and 60 points, and on all fifteen firms at the end. The report's worth is now the sum of each entry's rounded worth, so it follows the ledger and can sit a paisa off points times value: S1 and S2 498.5633 points read 498.55; C01 on L2 277.6606 points read 277.65 |
| PRCQ-18 | **Fixed** | P1, P2 | PTS 95 over PTR 90 on a batch create, an edit (whole, PTS alone, PTR lowered alone) and a goods receipt: **422** "PTS 95.00 cannot exceed the PTR 90.00: a stockist buys at or below the price to a retailer."; equal is taken |
| PRCQ-19 | **Fixed** | C1, C2 | Paid again: 422 "This payout has already been paid on 06-10-2026. It cannot be paid a second time." A cancelled one: 422 "This payout was cancelled, and its entry reversed, so there is nothing to pay. Accrue the period again if it is still owed." |
| PRCQ-20 | **Fixed** | C1, C2 | `target_amount` 0 and 0.00: 422 "A target must be above zero. A target of nothing is always met, and would pay its bonus on no sales at all."; an edit down to 0 the same; 0.01 is taken |
| PRCQ-21 | **Fixed** | L1, L2 | Two batches of 59.4720 on one day, the first worth 1.00 a point and the second 2.00: 70 points redeem for **80.53** (round 1: 129.47). With a lapsed batch in front and three live ones: 70 points for 78.17, and the lapsed batch is expired in the same request |

### PRCQ-1 in detail

All on S1 and S2, the same on both.

- **Part delivery.** An order of three lines (7 DET at 84, 3 DET at 90, 3 of
  a 5% product at 33.33) with 100.00 off and freight 50.01: total 1,059.1196.
  Notes of (3, 1, 1) and (4, 2, 2), a bill of each: bill discount 39.1790 +
  60.8210 = **100.0000**, freight 19.5934 + 30.4166 = **50.0100**, totals
  415.6716 + 643.4478 = 1,059.1194. Journals: Dr 1100 415.67 + 643.45 =
  **1,059.12**; CGST 29.96 + 45.60, SGST 29.97 + 45.59 = 151.12 against the
  order's 151.1196. To the paisa; the order document itself carries two
  ten-thousandths more than its bills.
- **A note billed in two parts.** 10 DET with 100.00 off, one note, bills of
  4 and 6: bill discount 40.00 + 60.00, totals 349.28 + 523.92 = **873.20**.
- **Three notes of one line** (3, 3, 4) with 7.5% typed on the line and 33.33
  off the bill: 9.9990 + 9.9990 + 13.3320 = 33.3300; totals sum to the
  order's 877.5306 exactly.
- **The counter bill** (stages off). 60 DET for C01: **5,265.16**, line 7.5%
  378.00, bill discount 200.00; the journal as above. Typed 100 off: 873.20.
  Both read `bill_discount_source` `inherited` (the bill asks the order it
  raised; see Gaps).
- **A typed figure replaces.** On the note: `bill_discount_amount` 0 gives a
  note and bill of 991.20; 40 typed (the order says 100) gives 944.00 on
  both. On a bill of the note: 0 typed gives 991.20 `typed`; **an explicit
  null re-inherits** 100.00 (873.20, `inherited`); 25 typed gives 961.70
  `typed`; the inherited 100 sent back stays `inherited`. One oddity:
  PRCQ-35.
- **The report.** Performance: BIGORDER 2 claims, 400.0000; the two bills
  that carry it took 200.00 + 200.00. Discount-by-customer for C01 reads
  `bill_discount` 400.00 (round 1: 0.00). Performance equals the claims list
  for every offer on both firms.

### PRCQ-2 in detail

S1 and S2, limit SALES_MANAGER 5%, the sales executive raising and the sales
manager approving unless said.

| Line | Answer |
| --- | --- |
| typed 84.00 (the customer's price), 90.00, and 79.80 (exactly 5% under) | approved |
| typed 79.79 | 422 "…5.01% off in all…" |
| 82.00 with 3% typed | 422 "Line 1 is priced at 82.00 where the customer's price is 84.00, with a typed discount besides: 5.31% off in all…" |
| 82.00 with 2% typed (4.33%) | approved |
| 82.00, discount blank (C02's own list gives 9.25%) | approved: an arrangement is not counted |
| 80.00 with 1% typed on the whole order | 422 "…5.71% off in all…" |
| a customer on a price level at 60.00: nothing typed, and 60.00 typed | approved |
| the same customer at a typed 50.00 | 422 "…priced at 50.00 where the customer's price is 60.00: 16.67% off in all…" |
| 42.00 approved by a firm manager (no limit row) | 200; its note billed and approved by the sales manager: 200 (the order was judged) |
| a price of 50.00 typed on the **note** line against an order at 100.00 (S5, S6) | note saved, approved, dispatched; **the bill's approval 422** "Line 1 is priced at 50.00 where the customer's price is 100.00: 50.00% off in all…" |
| counter bills (stages off): 30% off the bill, 252.00 off the bill, 30% on the line, a typed 42.00 | all four 422 at the bill's approval |

The customer's price level and segment: the sales manager's `PUT
/customers/{id}` with `price_level_id` is **403** "Changing a customer's
price level needs the manage customer settings permission
(CUSTOMER_MANAGE_SETTINGS)."; a new customer with a level is 403. Into a
segment with no discount and no level, and between two such: 200. Into
RETAILER (1.75%), out of it to a plain one, and out of it to none: **403**
"Moving a customer into or out of a segment that carries a discount or a
price level needs…". An edit that names the same segment, or neither field:
200.

### PRCQ-3, 6, 21 in detail

L1 and L2, the same on both.

- **Redeeming within the live points stages the lapse.** A customer with
  70.8000 lapsed, 2.3600 earned today and 100 given: 103 is refused (live is
  102.3600); 60 is taken, and the same request posts `LOY-RED-…` Dr 2600
  60.00 / Cr 1100 60.00 **and** `LOY-EXP-…` Dr 2600 70.80 / Cr 5700 70.80,
  with an EXPIRED entry "Earned 2026-08-27, lapsed 2026-09-27." A sweep
  afterwards takes only what other customers still held.
- **Loyalty Payable.** Before anything was spent: 2600 142.82 = `amount`
  72.02 + `lapsed_amount` 70.80 (L1); 354.58 = 283.78 + 70.80 (L2).
- **The reversal route.** `POST /loyalty/redemptions/{id}/reverse` with no
  reason: 422; as a sales executive: 403; an unknown id, an entry that is not
  a redemption, and another firm's redemption: 404 "Redemption not found.";
  as the sales manager with a reason: 200 "Points put back.",
  `LOY-RED-SI-…-REV`; again: 422 "Those points were already put back, on
  2026-10-06." Ten points spent again on the same bill post
  `LOY-RED-SI-…-2`, and cancelling the bill reverses that one too.
- **A bill with points and a receipt.** Cancel: 422 "SI-… cannot be cancelled
  while it has money applied from RC-2026-2027-000001. Reverse or cancel
  those first."; the points stay spent.
- **`agency-server loyalty-expire` was not run**: it is a subcommand of the
  shipped binary and this round drives HTTP only. `POST /loyalty/expire` was
  used where a sweep was wanted.

### PRCQ-4 and PRCQ-8 in detail

S1 and S2, the same on both.

- **Explicit 0** on the note: 12 leave, the order reads PARTIALLY_DELIVERED
  with 1 reserved, the bill shows no free goods. **3 typed** where the order
  gives 1: 422.
- **Part deliveries in whole units.** 10 + 1 free in notes of 4, 3, 3: free
  0, 0, **1**; the bills the same. 10 + 3 free in notes of 5 and 5: free 1
  and 2; the second note billed 2 then 3: free 0 then 2.
- **A gift line** (GIFT7): the note raised with the order's quantities (7,
  and 0 for the mug) and nothing about free goods ships the mug; round 1
  needed `free_quantity` 1 typed.
- **Returns.** After the 12 charged came back, 2 more: 422 "…can still bring
  back 0.0000 charged and 1.0000 free"; the free one alone: accepted, no
  credit note, `SR-…-COST` Dr 1200 60.00 / Cr 5200 60.00. A bill of 4 + 1
  free: `free_quantity` 2 is refused; 1 said to be free is taken with the
  customer's balance unmoved; the same unit again through the note: 422
  "Free quantity exceeds what left free on DN-… (1.0000 sent free, 1.0000
  already returned against it or the bill for it)." The by-product report
  reads `return_quantity` 14.0000, `free_quantity` 2.0000, amount 1,079.4168.
- The budget and the claim to the principal after a free unit comes back are
  in B.

## B. The two features built since round 1

### A scheme's budget (#1234)

S4 and S3, the same on both. Product at 100.00 with no price list.

**Money.** SCHEME, 10% on the line, `max_benefit_amount` 50 (0 and −5 are
422). Two orders of 4 both quote 40.00. Approve the first: the offer reads
`benefit_amount_claimed` 40.0000, `remaining_benefit_amount` 10.0000.
Approve the second: **422** "Promotion SCHEME has 10.00 left of its budget of
50.00, and this document would take 40.00. Re-save the document to price it
without." Re-saved, it prices at 472.00 with no discount and approves. While
10.00 is left a new order of 4 is not quoted (trace "This offer has 10.00
left of its budget of 50.00, and this document would take 40.00."), an order
of 2 is not, **an order of 1 is quoted 10.00** and claims it; after that the
trace reads "This offer's budget of 50.00 has all been given." Cancelling the
first order gives 40.00 back (REVERSED) and a new order of 4 is quoted again.

**An edit.** A new revision with the budgets left out of the body keeps 50
and the 10.00 claimed; `max_benefit_amount: null` lifts it; 50 again restores
it with the count intact (revision 4 still reads 10.00 claimed).

**Free units.** FREEC, buy 2 get 1, `max_free_quantity` 3. Two orders of 4
quote 2 free each (`free_promotion_id` set, 6 reservable). After the first is
approved the second is **422** "Promotion FREEC has 1 left of its budget of 3
free units, and this document would take 2. Re-save the document to price it
without."; re-saved it has no free goods and approves. An order of 2 (1 free)
fits and is claimed; the next is not quoted ("…budget of 3 free units has all
been given."). **One free unit returned** (PRCQ-8's route): the offer reads 2
claimed, 1 left, and the next order of 2 is given its free unit. The 4
charged units returned as well move nothing. A new revision keeps counting.

**Counter bills** (stages off). Two bills of 4 quote 40.00 each; the second
is refused **at the bill's approval** in the same words; the bill re-saved
unchanged prices without the offer (472.00) and approves. The same with the
free budget ("…1 left of its budget of 3 free units…").

**The race.** Approvals sent together from separate connections, started
within a millisecond of each other: two for the last 40.00 of 50.00, one 200
and one 422; four at once, one 200 and three 422; the same for free units,
two and four at once. **Exactly one succeeded every time**, eight races over
two firms; the losers stay DRAFT and their claims PENDING.

**Reports.** Performance carries `max_benefit_amount`,
`remaining_benefit_amount`, `max_free_quantity`, `remaining_free_quantity`,
`benefit_amount` and `free_quantity`; the redemptions report carries
`free_quantity` a claim. One figure disagrees: PRCQ-34.

### Free goods in the claim to the principal (#1235)

S5 and S6, the same on both. DET at a cost of 60.00, branded to principal A;
stages off.

- A counter bill of 4 with `free_quantity: 1` typed: the order behind it
  reads `free_promotion_id` **null**. Offer P22 (buy 2 get 1, principal A,
  share 50) and a bill of 4 with nothing typed: 2 free, `free_promotion_id`
  **set**, claim CLAIMED with `free_quantity` 2.
- `POST /principal-claims/preview` for the month: `scheme_amount` 60.00,
  `free_goods_amount` 60.00, total 120.00. One **SCHEME** line "Free goods
  under P22", 2 units, 60.00 (half of 2 × 60.00); one **FREE_GOODS** line
  "Free goods given on the bill", 1 unit, 60.00.
- Raise: `CLAIM-CLM-…` **Dr 1420 Claims Receivable from Principals 120.00 /
  Cr 5200 Cost of Goods Sold 120.00**. Raise again: 422 "Nothing is left to
  claim from Principal PRA … for that period." Cancel: `…-REV` mirrors it and
  the preview shows the lines again. The print has a "Free goods" row.
- **Not claimed from A:** free goods of a product branded to principal B
  (they appear on B's preview at B's product's cost, 50.00); of a product
  held at a cost of 0; on a draft bill; under an offer the firm funds itself
  (`free_promotion_id` set, no principal).
- `kinds: ["FREE_GOODS"]` gives the typed unit alone; `["SCHEME"]` the
  offer's.

What a return does to a claim already raised is C8.

## C. What the fixers flagged and did not fix

**C1. A part bill of an order, the delivery-note stage off.** Confirmed, and
wider than suspected. S6 and S5. An order of 10 at 100.00 with 100.00 typed
off the line and 90.00 off the bill: 955.80. Billed 4 then 6 straight off the
order: the bill of 4 carries a line discount of **100.0000** (25%) and the
bill of 6 **100.0002** (16.6667%), so the line discount comes off twice:
200.00 against the order's 100.00. The bill discount is shared correctly
(36.00 + 54.00). The bills come to 311.52 + 526.28 = **837.80 against
955.80**; the customer is billed 118.00 less, sales 100.00 and GST 18.00
short. It is the same when the order line's discount is a **percentage**
(10%): the part bills still take 100.00 each. PRCQ-22.

**C2. A discount typed on a delivery note line, above the limit.** Refused
nowhere. S6 and S5, sales manager limited to 5%, acting alone throughout.
Order of 10 at 100.00 (1,180.00). A note with `discount_percent` 30 on the
line: saved 826.00, approved, dispatched; the bill of it saved and **approved
by the same sales manager**, 826.00. The same with `discount_amount` 300, and
with `bill_discount_percent` 30 typed on the whole note (the bill reads
300.00 `inherited`). Only a typed **price** on the note is caught, at the
bill's approval. PRCQ-23.

**C3. A line sold by the box.** Not judged. S6 and S5, 1 BOX = 12 PIECE,
piece price 100.00, limit 5%. With both units named on the line (base 24 for
2 BOX): 2 BOX at a typed **600.00** a box, half of twelve pieces' worth, is
approved by the sales manager, delivered (24 leave) and billed 1,416.00; a
typed 30% on the same line is refused as usual. With **no price typed** the
box takes the piece's price: 2 BOX, 24 pieces, for 236.00. The price check
does report both ("sold at 50.0000 a unit, below what it cost", "8.3333 a
unit") but the floor is WARN unless a firm changes it. PRCQ-24, PRCQ-25. A
line that names the box and leaves `inventory_uom_id` out is PRCQ-26.

**C4. Two draft notes of one order line.** The money sums; the free goods do
not. S6 and S5. Order of 10 with 33.33 off the line, 100.00 off the bill,
freight 50.01 and 3 free: 1,081.6824. Notes of 3 and 7 saved as drafts, then
both approved, dispatched and billed: line discount 9.9990 + 23.3310 =
33.33, bill discount 30.00 + 70.00, freight 15.0030 + 35.0070, totals
324.5048 + 757.1776 = **1,081.6824**, the order's. Free goods: 0 on the
first and **2** on the second, of 3: one unit never ships, the order reads
PARTIALLY_DELIVERED and keeps it reserved. PRCQ-29.

**C5. A negative adjustment beyond the spendable points.** Taken, and from
the wrong batch. L1 and L2. A customer with 2.3600 live and 70.8000 lapsed:
`POST /loyalty/adjust` −50 answers **200** "Balance adjusted.", Dr 2600 50.00
/ Cr 5700 50.00; afterwards `points` is still **2.3600** and `lapsed_points`
20.8000. A further −2 leaves `points` 2.3600, lapsed 18.8000. The books stay
whole (2600 = `amount` + `lapsed_amount` at each step) but the points taken
away are ones the customer could not have spent, and the ones he can are
untouched. PRCQ-30.

**C6. An offer whose only benefit is passed over.** It reads Applied and
claims. S6 and S5. A product in stock cannot be deleted (422 "…cannot be
deleted: it holds 20 in MAIN…"); one with no stock and no movement can (204)
while a live offer gives it away. A quotation and an order of 7 then answer
201 with no gift line; the trace holds both "Applied." and "The product this
offer gives away is not one of this firm's products any more, so nothing was
given."; `applied` lists the offer with benefit 0.0000 and free 0. Approved,
the offer has a claim: CLAIMED, 0.0000, 0.0000; performance counts 1. The
same happens when a free quantity is typed on a line an offer matches (P22 in
B: a CLAIMED row of 0 and 0). PRCQ-32.

**C7. Cancelling an approved order that claimed two budgets, after a part
delivery.** S4 and S3. Order of 4 under a 10% offer (budget 100.00: 40.00
claimed) and 4 under buy 2 get 1 (budget 5: 2 claimed); a note of 2 and 2
ships 20.00 of discount and 1 free unit. Cancel: **422** "SO-… cannot be
cancelled while delivery note DN-… stands against it. Cancel those first, or
close the order to stop what is still to come." Close: 200, the reservations
go. **Both budgets stay as claimed**: 40.00 and 2 units, where 20.00 and 1
were given; the bill of the note carries 20.00 and 1 free. The same order
cancelled before any delivery gives both back in full. PRCQ-28; what this
does to a claim on the principal is PRCQ-27.

**C8. A return after the claim was raised.** Netted nowhere. S5 and S6. Claim
CLM-…-000003 raised at 120.00 (above). One of the offer's two free units is
then returned: `SR-…-COST` Dr 1200 60.00 / Cr 5200 60.00. The claim still
reads 120.00 RAISED, outstanding 120.00; the preview for the same period
shows nothing new and nothing negative; a period starting tomorrow cannot be
previewed ("A claim is raised on or after its period starts."). Cost of goods
sold has now been credited for that unit twice, 30.00 of it by the claim.
Only cancelling the claim and raising it again nets it: the preview then
reads SCHEME 30.00 for 1 unit, total 90.00. The same for the typed unit
(60.00 claimed for a unit back on the shelf). The rule is written this way
("a claim already raised is not rewritten"); PRCQ-31.

## D. The twelve cases again

Run from round 1's scripts, unchanged, on fresh fixtures, and the output
compared with round 1's line by line.

| Case | Firms | Verdict | Difference from round 1 |
| --- | --- | --- | --- |
| 001 A price list is a ladder | S1, S2 | **Pass** | None in the figures (7.5% `promotion` at 30, 6.75% `price_list` at 24, 2,750.58) |
| 002 Editing an active promotion | S1, S2 | **Pass** | Expected from #1246: an edit of the superseded row now answers 409 "This is revision 1 of offer BULK5, and revision 2 has replaced it…" |
| 003 Reports count a claim once | O1 | **Pass** | Expected: the three reports carry `free_quantity`, performance the four budget columns |
| 004 An offer that does not stack | S1, S2 | **Pass, now down to the bill** | Expected from #1237: order 5,265.16; the note and the bill of it are 5,265.16 too (A, PRCQ-1) |
| 005 Loyalty | L1 | **Pass**, text wrong in one figure as before | Expected from #1242: balances carry `lapsed_points`, `lapsed_amount`. Step 4 still answers "holds **109.6642** points, not 5000.0000". The second run, on L2 after case 010, repeated round 1's slip (the script takes the newest bill, which is the other customer's, and is refused "holds 3.7666 points, not 100.0000"), so the case stands on one firm; redemption itself was driven on both in A |
| 006 Commission blends rates | C1, C2 | **Case text wrong, product right**, as before | None: Asha 5,900.00 collected, **420.00**; Bala 4,720.00, **80.00** |
| 007 Payouts | C2 as written; C1, C2 driven | **Not runnable as written**, as before; the flow passes | "Accrue this month": 422 "That period has not ended…accrue it from 2026-11-01."; to yesterday: "Nobody earned anything in that period." With sales dated yesterday the flow is as round 1 (Asha 190.00, Bala 40.00; accruer cannot approve, approver cannot pay). Expected from #1246: paying the paid payout now says so |
| 008 Whoever states a debt | C1, C2 | **Pass** | None |
| 009 Buy X get Y, combo | S3 | **Pass** | None in the figures (42.00, 84.00, none, 42.00; cap 33.33 / 16.67; combo 18.00 and 9.00 a line) |
| 010 Bonus points, history, day and time | L2 | **Pass** | None in the answers. It ran in one piece this time (round 1's script stopped on a field the bill line now has) |
| 011 Bulk codes, copying an offer | S3 | **Pass** | Expected: the coupon report has `free_quantity` |
| 012 Claims to the principal | D1, D2 | **Pass** | Expected from #1235: `free_goods_amount` on the preview, the claim and the print. **New:** on D1 the script's second receipt landed in the same second as the first and was refused (PRCQ-33); the settlement steps were driven again on D1 and on D2 a second apart and pass (credit note 113.55 Dr 2100 / Cr 1420, SETTLED, a receipt reversed, the credit note cancelled, cancel refused while part settled) |

No difference is a regression.

**The generic checks.** Round 1's probe 11 was run again on S1 against S2 and
compared: every changed line is one of the fixes (the price-list refusals,
the offer naming an unknown product now 422, the price level's stale
`If-Match` now 409). On the routes the fixes added or changed, on S1 and S2:
fifteen paged lists and reports answer 422 for `page_size` 101, 1000, 0 and
−1 and for `page` 0, and an empty 200 past the end; seventeen calls with an
unknown id answer 404 by name (422 for a malformed id and for one body my
probe sent short, and "That principal is not one of this firm's." on the
claim preview and on an offer); eleven calls with the other firm's offer,
customer, bill, price level, product and principal answer 404 or 422 and
leave the other firm's rows as they were, and L2 reversing a redemption of
L1 is 404 with the entry untouched; a
stale `If-Match` on an offer's budget edit is 409; a deleted draft offer is
gone from the list, the read and the performance report; performance equals
the claims list for every offer in count, benefit and free quantity; the
loyalty balances report equals each customer's entries and own read on L1 and
L2.

**The books at the end, all fifteen firms.**

| Firm | Trial balance | 1100 = customers | 2600 = points' worth + lapsed | 2400 = approved unpaid | 1420 = claims | 1200 = valuation |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | 78,461.48 balanced | 24,928.17 | 498.55 | 0 | 0 | 30,848.00 |
| S2 | 78,461.48 balanced | 24,928.17 | 498.55 | 0 | 0 | 30,848.00 |
| S3 | 62,734.99 balanced | 2,289.20 | 45.79 | 0 | 0 | 58,560.00 |
| S4 | 58,025.66 balanced | 3,162.40 | 63.26 | 0 | 0 | 52,080.00 |
| S5 | 89,945.68 balanced | 10,319.29 | 206.39 | 0 | 90.00 | 66,800.00 |
| S6 | 91,390.00 balanced | 11,735.29 | 234.71 | 0 | 90.00 | 65,360.00 |
| L1 | 64,663.95 balanced | 29,487.30 | 337.62 | 0 | 0 | 12,360.00 |
| L2 | 66,521.11 balanced | 31,272.70 | 549.38 | 0 | 0 | 11,340.00 |
| C1 | 30,380.00 balanced | 0.00 | 0 | 0.00 (230.00 paid, 5600 230.00) | 0 | 7,200.00 |
| C2 | 30,380.00 balanced | 0.00 | 0 | 0.00 (230.00 paid) | 0 | 7,200.00 |
| P1 | 2,537.60 balanced | 257.60 | 0 | 0 | 0 | 2,100.00 |
| P2 | 2,537.60 balanced | 257.60 | 0 | 0 | 0 | 2,100.00 |
| D1 | 7,881.10 balanced | 1,231.57 | 24.63 | 0 | 227.10 | 4,980.00 |
| D2 | 7,881.10 balanced | 1,231.57 | 24.63 | 0 | 227.10 | 4,980.00 |
| O1 | 6,000.00 balanced | 0 | 0 | 0 | 0 | 6,000.00 |

**Every figure agrees with its sub-ledger on every firm**, and no journal on
any firm is unbalanced (read 25 a page). The books agree even where a
finding below says the documents are wrong: PRCQ-22 posts what the bills say.

## Findings

Ids continue from round 1. High = wrong money, stock or tax, or a rule that
can be bypassed; Medium = a wrong record or a broken flow with a workaround;
Low = wording or convenience. Causes are from reading the code named.

| Id | Severity | What | Firms |
| --- | --- | --- | --- |
| PRCQ-22 | **High** | With the delivery-note stage off, every part bill of an order takes the whole of the order line's discount | S5, S6 |
| PRCQ-23 | **High** | The discount limit is passed by typing the discount on the delivery note | S5, S6 |
| PRCQ-24 | **High** | The discount limit does not judge a typed price on a line sold by the box | S5, S6 |
| PRCQ-25 | **High** | A line sold by the box with no price typed is charged the price of one piece | S5, S6 |
| PRCQ-27 | **High** | A scheme is claimed from the principal at what the order claimed, not at what was billed | S5, S6 |
| PRCQ-26 | Medium | An order line that names the box and not the stock unit reads 2 where 24 leave the warehouse | S6 (the line on S5 too) |
| PRCQ-28 | Medium | A scheme's budget keeps the undelivered part of an order that was closed short | S3, S4 |
| PRCQ-29 | Medium | Two draft notes saved before either is approved ship fewer free goods than the order gave | S5, S6 |
| PRCQ-30 | Medium | A negative loyalty adjustment comes out of lapsed points and leaves the spendable balance as it was | L1, L2 |
| PRCQ-31 | Medium | Free goods returned after the claim was raised stay claimed from the principal | S5, S6 |
| PRCQ-32 | Low | An offer that gives nothing still records a claim | S5, S6 |
| PRCQ-33 | Low | Two receipts against one claim in the same second: the second is refused for its journal reference | D1, D2 |
| PRCQ-34 | Low | The performance report states the free units claimed before returns, beside a budget counted after them | S3, S4 |
| PRCQ-35 | Low | A typed bill discount of 25.00 becomes 25.0001 when the bill is saved again without it | S1, S2 |

### PRCQ-22: each part bill takes the whole line discount (High)

S6 07:01:37 IST, S5 07:03:50 (`cp.py`, part 1).

1. `PUT /sales-orders/workflow-settings` with `delivery_note_stage` false.
2. `POST /sales-orders`: 10 of a product at 100.00, `discount_amount` 100 on
   the line, `bill_discount_amount` 90. Approve. Total **955.80** (line
   discount 100.00, bill discount 90.00, tax 145.80).
3. `POST /sales-invoices` with `source_document_type` `SALES_ORDER`,
   `current_invoice_quantity` 4. The bill line reads `discount_percent`
   25.0000, **`discount_amount` 100.0000**, bill discount 36.0000; total
   311.52. Approve: Dr 1100 311.52 / Cr 4000 264.00 / 23.76 + 23.76.
4. The same for the remaining 6: `discount_percent` 16.6667,
   **`discount_amount` 100.0002**, bill discount 54.0000; total 526.28.
   Approve. The order reads DELIVERED.
5. Repeat from step 2 with `discount_percent` 10 on the line in place of the
   amount: the two bills are the same figures.

**Expected:** 40.00 and 60.00 of line discount, bills of 382.32 and 573.48,
955.80 in all. **Actual:** 200.00 of line discount, **837.80** in all: the
customer is billed 118.00 too little and 18.00 of GST is not charged. The
more parts an order is billed in, the more it gives away.

**Suspected:** `app/sales_invoice/services/sales_chain_service.py:464`
and `:465` (`_note_line` hands the note line the order line's
`discount_percent` and whole `discount_amount`, whatever part is billed;
the amount wins).

### PRCQ-23: the limit is passed on the delivery note (High)

S6 07:01:50 IST, S5 07:04 (`cp.py`, part 2).

1. `PUT /sales-orders/discount-limits`: SALES_MANAGER 5%.
2. As the sales manager: order of 10 at 100.00, discount 0; approve. 1,180.00.
3. As the sales manager: `POST /delivery-notes` with `discount_percent` 30 on
   the line: 201, 826.00. Approve 200, dispatch 200.
4. As the sales manager: `POST /sales-invoices` for the note: 826.00, line
   30%, 300.00. **Approve: 200.**
5. The same with `discount_amount` 300 on the note line, and with
   `bill_discount_percent` 30 on the note's header (the bill reads
   `bill_discount_amount` 300.00, `bill_discount_source` `inherited`): all
   approved by the sales manager.

**Expected:** refused at the bill's approval, as the same 30% typed on the
order or on the bill is ("Line 1 carries a discount of 30.00%, above your
limit of 5.00%…"), and as a price typed on the note now is. **Actual:** one
person limited to 5% gives 30% without anybody allowed more seeing it.
`docs/PRICING_AND_PROMOTIONS.md` says so in its own words ("a *discount*
typed on a delivery note reaches the bill as inherited and is judged
nowhere"), so this is the rule as written; the rule does not hold what it is
for.

**Suspected:** `app/sales_order/services/discount_limit.py` (a bill line
whose source is `inherited` is not judged; nothing compares the note line's
discount with the order line's).

### PRCQ-24 and PRCQ-25: a line sold by the box (High)

S6 07:03:36 IST, S5 07:04:36 (`xu.py` with both units named; `cp.py`, part 3).

1. `POST /uom-framework/conversion-rules`: for the product, BOX to PIECE,
   factor 12. `POST /uom-framework/convert` 1 BOX: 12.0000. The product sells
   at 100.00 a piece and costs 60.00. Limit SALES_MANAGER 5%.
2. As the sales manager: order of 2 with `sales_uom_id` BOX,
   `inventory_uom_id` PIECE, `unit_price` 600, `discount_percent` 0. The line
   reads `base_quantity` 24.0000, `conversion_factor` 12, gross 1,200.00.
   **Approve: 200** (24 reserved). Note: 24 leave. Bill 1,416.00, approved by
   the sales manager: Dr 1100 1,416.00 / Cr 4000 1,200.00.
3. The same line with `unit_price` left out: `unit_price` **100.0000**, gross
   200.00, total **236.00** for 24 pieces. Approve: 200.
4. `GET …/price-check` on both: a finding each ("sold at 50.0000 a unit,
   below what it cost", "sold at 8.3333 a unit…"), `would_block` false under
   the default WARN.
5. For comparison, 12 PIECE at a typed 50.00: 422 "Line 1 is priced at 50.00
   where the customer's price is 100.00: 50.00% off in all…".

**Expected:** a box is twelve pieces' worth, so 600.00 a box is half price
and is refused like 50.00 a piece (PRCQ-24), and a box with no price typed is
1,200.00 (PRCQ-25). **Actual:** the limit compares the box's price with the
price of one piece, so anything at or above 100.00 a box passes; and the
blank price is the piece's. The doc records the first ("a line sold in
another unit than its stock is kept in is judged on its typed discount alone,
because the ranking's price carries no unit"). Whether the desktop can send a
box line with a blank price was not checked; through the API it can be done
by any role that raises orders.

**Suspected:** `app/sales_order/services/discount_limit.py:301` and the
`customer_prices` lookup (no conversion applied to the customer's price);
the price resolver for the blank price.

### PRCQ-27: a scheme is claimed from the principal off the order (High)

S5 07:00:40 IST, S6 07:01:30 (`b2b.py`, part 3).

1. Offer P10: 10% on a product at 100.00, `principal_id` A,
   `principal_share_percent` 50.
2. **Order A** of 4, approved, never delivered: claim CLAIMED 40.00.
   `POST /principal-claims/preview` with `kinds` `["SCHEME"]`: a line for
   SO-…-000011, **20.00**.
3. **Order B** of 4: a note of 2, the order closed, the note billed (discount
   on the bill 20.00). Preview: a line for it of **20.00** (half of 40.00).
4. Cancel order A: its line goes.
5. **Order C** of 4, delivered and billed, then all 4 returned (credit
   424.80). Preview: its line stays, **20.00**.

**Expected:** the principal is asked for its share of what was passed on to
customers: nothing for A, 10.00 for B, nothing for C. **Actual:** 20.00 each.
A claim raised at month end includes every approved order still waiting to be
delivered, at full value. Case 012 and the doc both speak of a scheme
"claimed on an approved bill".

**Suspected:** `app/principal_claims/services/` (`_schemes`, line 833 on:
`redemption.benefit_amount` times the share at `:860`, read from the order's
claim with no look at bills or returns).

### PRCQ-26: a box line without the stock unit (Medium)

S6 07:02:41 IST (`xu.py`, first run); the line's figures also on S5.

1. Order of 2 with `sales_uom_id` BOX and **no** `inventory_uom_id`,
   `unit_price` 600. The line reads `conversion_factor` 1, `base_quantity`
   **2.0000**, `reservable_quantity` 2.0000.
2. Approve: reserved stock rises by **24**. Note: `ordered_quantity` 2,
   `delivered_quantity` 2; stock falls 428 to **404**.
3. `GET …/price-check`: no finding, though each piece went for 50.00 against
   a cost of 60.00.

**Expected:** the line and the stock agree, or the line is refused for the
missing unit. **Actual:** the documents say 2 and the stock ledger 24, and
the price floor judges 600.00 as the price of one unit.

**Suspected:** `app/sales_order/services/sales_order_service.py:3192`
(no conversion unless both units are sent) against the reservation, which
converts from the product's own units.

### PRCQ-28: a budget keeps what a closed order never took (Medium)

S4 06:58:15 IST, S3 06:59 (`b1b.py`, part 7). Steps in C7. After the close
the offers read `benefit_amount_claimed` 40.0000 of 100 and
`free_quantity_claimed` 2.0000 of 5; the only bill carries 20.00 and 1 free.

**Expected:** closing gives back what will never be delivered, as cancelling
gives back the whole. **Actual:** 20.00 and 1 unit of each budget are spent
on nothing, so a capped scheme stops early; the performance report says the
offer gave 40.00.

**Suspected:** the close in
`app/sales_order/services/sales_order_service.py` (no call into
`RedemptionService` for the part closed).

### PRCQ-29: two drafts ship fewer free goods (Medium)

S6 07:01:58 IST, S5 07:04 (`cp.py`, part 4). Steps in C4.

**Expected:** 3 free units over the two notes (0 and 3, or 1 and 2).
**Actual:** 0 and 2. Each draft works out its share against notes already
approved; with neither approved, the second does not know it completes the
line. Workaround: approve the first note before raising the second, or type
the free quantity on the second.

**Suspected:**
`app/delivery_note/services/delivery_note_service.py:1855` (the notes
counted are "approved onwards") used at `:2057`; the share is not worked
again when the note is approved.

### PRCQ-30: a negative adjustment taken from lapsed points (Medium)

L1 06:53:05 IST, L2 06:54:10 (`a3.py`). Steps in C5.

**Expected:** refused, as a redemption of 70 is ("holds 2.3600 points…"), or
taken from the points the customer can spend. **Actual:** 200, and the
customer's spendable balance is not reduced at all. Workaround: run the sweep
first.

**Suspected:** `app/loyalty/services/loyalty_service.py:963` (`adjust`
reads `_points_of`, the raw sum, and does not stage the lapse as `redeem`
now does).

### PRCQ-31: returned free goods stay claimed (Medium)

S5 07:00:35 IST, S6 07:01:30 (`b2b.py`, part 2; `b2.py`, part 6). Steps in C8.

**Expected:** a later claim, or the claim itself, takes the 30.00 (or 60.00)
back. **Actual:** nothing does unless the claim is cancelled and raised
again, which a part-settled claim refuses. The doc states it as a limit.

**Suspected:** `app/principal_claims/services/` (`_free_goods` nets
returns only for lines not yet on a live claim; there is no negative line).

### The Low findings

- **PRCQ-32.** S5, S6. Steps in C6. The claim of 0 and 0 counts toward
  `max_redemptions` and "once a customer", so an offer that gave nothing can
  use up a customer's turn. Not driven with a limit set.
- **PRCQ-33.** D1 06:47:15, 06:48:31; D2 06:48:47 (`c12.py`, `c12x.py`).
  `POST /principal-claims/{id}/receipts` 1.00, and again 0.15 s later: the
  first 201, the second **409** "A journal entry with reference
  CLAIM-CLM-2026-2027-000002-PAY-20261006011831 already exists."; a second
  later the same body is taken. The reference is the clock to the second
  (`app/principal_claims/services/`, line 524; the reversal's at `:554`).
- **PRCQ-34.** S4, S3. FREEC after one free unit came back and was given
  again: the offer and the list read `free_quantity_claimed` 3.0000,
  `remaining_free_quantity` 0; the performance report reads `free_quantity`
  **4.0000** beside `max_free_quantity` 3.0000
  (`app/promotions/services/report_service.py:96`).
- **PRCQ-35.** S1, S2. A draft bill of a note with `bill_discount_amount` 25
  (961.70), then `PUT` with the discount left out: `bill_discount_amount`
  **25.0001**, total **961.6999**. The typed amount is carried as its rate
  (2.9762%) and worked again. The ledger rounds it away here; on a large bill
  a four-place rate can move a paisa
  (`app/sales_invoice/services/sales_invoice_service.py:2066` to `:2075`).

## Case text to correct

Round 1's table still stands in full: `docs/qa/09_PRICING_AND_INCENTIVES.md`
was generated on 2026-10-05 and still reads as it did. Changes to that table,
for `docs/INDEPENDENT_TEST_CASES.md`:

| Case | What the text must say now |
| --- | --- |
| TC-INCENT-004 | Drop round 1's caveat. Add a step: "Approve, deliver and bill it: the note and the bill both read 5,265.16, with 200.00 taken off the whole bill." |
| TC-INCENT-005 | As round 1 ("holds **109.6642** points, not 5000.0000"; the 50 is a balance to reach). Add: "The balances report has a lapsed column: 0 here." |
| TC-INCENT-006 | As round 1: Asha **420.00**, Bala **80.00**, commission on net sales |
| TC-INCENT-007 | As round 1 (sales dated before today; three people). Add to step 2: "**(HTTP)** paying it a second time: 422 'This payout has already been paid on DD-MM-YYYY. It cannot be paid a second time.'" and "Paid on must be the approval day or later, and not after today." |
| TC-INCENT-012 | Replace the last sentence ("Free quantity on a bill line is not claimed yet.") with: "Free goods are claimed at what they cost: a free quantity typed on a bill of the principal's product as **Free goods**, and free goods under an offer the principal funds as a scheme line 'Free goods under …' at the principal's share. Raising posts Cr Cost of Goods Sold for them." Keep round 1's three additions (an open supplier bill; cancel refused while part settled; who may read). Add: "Record the two payments at least a second apart (PRCQ-33)." |
| TC-INCENT-002 | Add: "Editing the old row again is refused: 'This is revision 1 of offer BULK5, and revision 2 has replaced it. Open the current revision and edit that one.'" |
| New cases wanted | Round 1's four are now passable and should be written as passing cases (bill discount down to the bill; free goods with and without a word on the note; lapsed points at the counter; a typed price against the limit). Add: (5) a scheme budget in money and in free units, with the refusal and the re-save; (6) free goods on a claim to the principal; (7) a return of a free unit; (8) a redemption put back, and a bill with points cancelled. Hold back until fixed: a part bill with the note stage off (PRCQ-22) |

## Gaps noticed

Not defects against a written rule; listed so they are decided, not lost.
Round 1's list was not driven again and is not repeated.

- **A discount of 0 typed on a line also refuses a free-goods offer.** A line
  sent with `discount_percent` 0 under buy 2 get 1 gets no free units and
  the offer is not claimed; the trace still reads "Applied."
- **A note that refuses the order's free goods (`free_quantity` 0) leaves
  the order PARTIALLY_DELIVERED** with the units reserved until somebody
  closes it.
- **A counter bill reads `bill_discount_source` `inherited`** even when the
  discount was typed on that bill; `typed` appears only on a bill of
  documents.
- **A full return gives back free units to a budget and nothing else**: the
  money budget, the claim's status and the principal's scheme line stay
  (PRCQ-27 is the part that costs money).
- **A product with no stock can be deleted while a live offer gives it
  away**; the offer then gives nothing and says so only in the trace.
- **A condition on `salesman_id` takes an unknown id** (201). The code says
  why: users live in the platform store. Such an offer never matches.
- **A counter bill priced again without its offer leaves a REVERSED claim
  row** for a claim that was never made, which the performance report counts
  under reversed.
- **Two approvals at once of unrelated orders for one product**: on S3 one of
  a pair answered 409 "This record changed since you loaded it. Reload and
  try again." and stayed a draft. Seen once; the retry was not driven.
- **The discount-by-promotion report has no `free_quantity`**, where the
  other three promotion reports now do.
- **An order's total keeps four decimals where its bills are rounded line by
  line** (1,059.1196 against 1,059.1194); the ledger agrees to the paisa.
- **The price floor is WARN by default**, so PRCQ-25's box at a piece's price
  is reported by the price check and approved all the same.

## Left on the firms

Offers made and retired on S1 to S6 (INACTIVE); draft WELCOME-NOV on S1, S2,
S3 and draft multiplier offers on L2. On S1 and S2: products G5, GFT, QQ, RV
(revisions of 86.00 from today and 91.00 from the 9th), customers PC and
LV, segments PLAINGRP and PLAIN2, price level WSALE,
one order PARTIALLY_DELIVERED with 1 reserved, limits off, stages on. On S3
and S4: products BQ, BF, customers PC, PD, several draft orders holding
PENDING claims, one order CLOSED. On S5 and S6: principals PRA and PRB with
brands, products OTH, NC, PQ, QQ, GON, a deleted GO2, a BOX rule on QQ,
claims of 60.00, 60.00 and 120.00 CANCELLED and one of 90.00 RAISED, approved
orders by the box not delivered. On L1 and L2: five extra customers each, the
scheme back at 2 per 100, 1.00, 24 months, one bill with points and a receipt
of 50.00. On C1 and C2: both payouts PAID (190.00 by bank, 40.00 by cash,
Cash at −40.00). On P1 and P2: every AMX batch with an MRP (110.00 or
120.00), batch BR received, an order approved with a note APPROVED and not
dispatched. On D1 and D2: claims RAISED for 227.10 in all, an open supplier
bill of 354.00.

## Not verified

- **Nothing on screen.** The desktop was not opened. In particular the note
  editor, which the doc says still sends `free_quantity` 0 from a blank box,
  was not checked; nor whether the order editor can send a box line with a
  blank price (PRCQ-25).
- **Nothing was read from the database.** That every store is at
  `20261006_0337` was taken from the hand-over.
- **`agency-server loyalty-expire`** was not run (a subcommand of the binary,
  not a route).
- **Everything ran once, in one window** (06:46 to 07:08 IST), after 05:30
  IST, so with the two days agreeing; no date rule was run again with UTC a
  day behind, as all of round 1 was.
- **PRCQ-17's paisa** was neither reproduced nor traced. Round 1 saw it after
  a bonus-points earning (29.1413 points booked at 29.14); the same earning
  on L2 now reads worth 29.14 in the report as well, which is why the two
  agree.
- **PRCQ-1:** GSTR-1 and GSTR-3B (the firms have no GSTIN); an inter-state
  sale; the printed bill; a credit note or debit note down the chain.
- **PRCQ-2:** a price typed on the **bill** of a note (only the note's price
  and counter bills were driven); a product with no selling price.
- **PRCQ-6:** a redemption reversed after its points' batch lapsed; a
  reversal after the bill was returned.
- **PRCQ-7:** a line shipped from two batches with different MRPs; a batch
  whose MRP is lowered after the order was approved and pinned.
- **PRCQ-8:** damaged or scrapped free goods; a return of free goods by the
  box.
- **B, the budget:** a budget on a bill-discount offer, on free shipping and
  under best-offer-only mode; a claim made before migration `20261006_0334`;
  the race was eight runs of two or four requests, not a load test.
- **B, the claim:** free goods delivered on a note and not yet billed; a
  claim settled before the return (C8 was driven on RAISED claims only).
- **C6:** a product in stock cannot be deleted, so the case was made with a
  product that never had stock; the inactive-product variant was not needed
  and not driven.
- **C7:** cancelling the note first and then the order was not driven.
- **PRCQ-27 and PRCQ-32** were found late and seen through the preview; no
  claim was raised and settled on those figures, and PRCQ-32 was not driven
  against a claim limit.
- **The generic checks** covered the routes named above on S1 and S2; the
  access matrix of round 1 (probe 10) was not run again, beyond the roles
  named in A.
- **The causes** given for every finding are from reading the code named,
  not from a debugger or a failing test.
