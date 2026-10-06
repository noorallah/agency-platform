# Pricing — discounts, price lists, promotions, loyalty and freight

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

The resolution order lives in `app/core/utils/pricing.py`;
`docs/SALES_TO_RECEIPT_FLOW.md` traces it through a whole sale.

## No line editor may prefill a discount box

**No line editor may prefill a discount box.** `resolve_line_discount` ranks an explicit percentage above the price list, so filling the box turns an inherited arrangement into an override. The quotation editor filled it with the customer's standing rate -- and with a literal `0` where they had none, which the server reads as a refusal of every arrangement -- so **no price list could reach a quotation raised from the desktop at all**, from the day price lists shipped. Driven against a running backend: the same line resolved to a 15% list saying nothing and to nothing saying `discount_percent: "0"`. Both sales line editors now leave the box blank and *say* what blank takes; the reasoning behind the prefill (a salesman must see the rate) was right, and helper text is the honest version of it, because the form cannot resolve which arrangement is in force.

## A line discount is resolved in one place

**A line discount is resolved in one place**, `app/core/utils/pricing.py`, and
every sales and purchase document calls it: an explicit amount beats an
explicit percentage, which beats `customers.default_discount_percent`, which
beats nothing. `docs/SALES_TO_RECEIPT_FLOW.md` is the reference. Three things
to know before touching it. **`None` and `0` are different answers** -- saying
nothing takes the customer's standing rate, sending zero refuses it for this
line -- which is why the discount fields on the nine line-write schemas are
`Decimal | None` with no default; giving them `Decimal("0")` back makes an
omission indistinguishable from a refusal and switches the arrangement off
for everybody. **The percentage was stored and never applied** by
`sales_invoice`, `sales_return`, `purchase_invoice` and `purchase_return`
until 2026-08-23: all four read the discount *amount* alone for both the tax
base and the subtotal, so a ten percent order was invoiced at full price with
`discount_percent = 10` sitting on the line as a lie, and the three documents
upstream did apply it, so the order looked right and the bill did not match
it. And **the recorded rate is derived from the amount applied**, not echoed
from the request -- a line saying 10% and 50.00 against 1,000.00 is one
nobody can reconcile. The discount reduces the taxable value, so it is
applied before tax and revenue is booked net of it; a discount above the line
or a rate above a hundred is refused, which only `goods_receipt` did before.
An invoice **inherits from the line it bills** rather than re-reading the
customer, so an edit to the master in August cannot rewrite a price agreed in
March; a rate inherits as itself, an amount is pro-rated by the share billed.

## A promotion's identity is its `version_group_id`

**A promotion's identity is its `version_group_id`; the row is only the
version that is current.** An ACTIVE promotion is superseded rather than
edited, so anything that identifies an offer by row id breaks the moment
somebody changes it -- and changing it is the routine act, because there is
no other way. Three checks did, and the 2026-09-03 review found all three:
a coupon was orphaned by any edit to its offer (a driven line went from
109.00 to 10.00 while the code stayed listed ACTIVE), the offer's
`max_redemptions` and `max_redemptions_per_customer` **reset to zero** on the
same edit so an exhausted campaign came back to life, and retiring an offer
left its codes live and pointing at nothing. `_claimed` counts across the
version group, `_coupon_reaches` matches on it, and retiring the **last live
version** retires the codes that reach it -- only the last, since a
superseded predecessor's codes still have a live offer to reach. `app/tax`
supersedes the same way and carries the same column, so ask its equivalent
checks the same question.

## Promotions stack; tax does not

**Promotions stack; tax does not.** `app/promotions` copies `app/tax`'s shape
-- rule, typed condition rows, action rows, execution log -- but where the tax
engine breaks at the first match, the promotion engine applies every matching
offer in `priority ASC, code ASC, version_number DESC, created_at ASC` order
until one with `allow_stacking = false` is applied. Two consequences worth
knowing before touching it. **Percentages compound on what is left**, so two
stacked ten percent offers take nineteen percent -- which is the retail
meaning and also the only basis on which stacked benefits cannot exceed the
line, and `resolve_line_discount` refuses one that does. And **a stacking
engine must collapse to one live version per `version_group_id`**: superseding
leaves the predecessor ACTIVE and tax survives that only by stopping at the
first match, so copying its query verbatim hands the customer the same offer
twice -- 190.00 for one ten percent promotion, which is what the guard was run
against before the collapse existed. The result feeds one new tier in
`app/core/utils/pricing.py`, between what was typed and the price list, and
`PromotionService.evaluate` never commits for the reason
`TaxRuleService.simulate` never does. A line somebody priced by hand is
skipped and the trace says so: a log that reports a benefit the line never
received is a lie told to the person asking why the price is what it is.

**A firm may choose one offer instead of a stack** (backlog 59,
`sales_workflow_settings.promotion_mode`, migration `20261001_0178`).
`COMBINE` is the default and is everything above. `BEST_OFFER` values each
matching offer **alone, on a fresh copy of the lines** -- discounts, the bill
discount, free units at the line's own rate, a free product at its selling
price, a waived delivery at its charge -- and applies only the most valuable;
a tie goes to the earlier in the ordering above, and every loser's trace says
what it was worth against the winner. Valuing runs through the same `_apply`
that applies, so a cap below is honoured in the comparison: 20% up to 100 on
a 1,000 line is worth 100, not 200. A mode is a firm setting, never a
property of a promotion -- an offer that decided whether it combined would
make the outcome depend on which offers happened to match.

**Combine mode may cap one line** (backlog 59 item 3,
`sales_workflow_settings.max_line_discount_percent`, migration
`20261001_0193`; null is no cap). After the stack, a line whose offer discount
exceeds the cap % of its gross gives back the excess **latest-applied offer
first** -- compounding means it added the last slice -- and each trimmed
offer's `benefit_amount` falls by what it gave back, so campaign costing stays
true. The bill discount is not a line discount and is not counted. The trace
carries one decision per capped line naming the offers trimmed.

**A percentage may be capped** (backlog 60 item 1): `max_amount` on a
`LINE_DISCOUNT_PERCENT` or `BILL_DISCOUNT_PERCENT` action -- "20% off, up to
500" -- bounds what the offer takes off the **document**, not each line. On
line percentages the cap is split across the matched lines with `apportion`
in proportion to what each would have had, so the lines sum to the cap
exactly. A cap is written only for a percentage; on an amount it is refused,
because an amount is already its own limit.

## A delivery note ships the deal the order struck

**A delivery note ships the deal the order struck.** It re-read the customer's
*current* standing rate and the price lists instead of inheriting the order
line it ships, so a rate agreed in March was replaced by whatever the master
said in August -- the exact thing the invoice's own inheritance rule exists to
prevent, one document earlier. Worse once promotions existed: an offer is
applied when the order is priced, the note discarded the result, and the
invoice inherits the *note*, so a customer promised a promoted price was
billed the undiscounted one. Seeded data showed it plainly -- order lines at
1, 5, 5.95, 7.5 and 8.425 percent, and 43 of 58 note lines at zero. Fixed
2026-09-03: `_line_discount` inherits the source line, a rate as itself and an
amount pro-rated by the share shipped, and the price list and standing rate
are deliberately not consulted -- the order resolved both already, so a line
that came out at nothing came out at nothing on purpose.

## A claim on an offer is counted at approval, never while a document is priced

**A claim on an offer is counted at approval, never while a document is
priced.** `promotion_redemptions` records PENDING when the engine prices a
document, CLAIMED when it is approved under a `with_for_update` lock on the
promotion, and REVERSED when it is cancelled -- and **only CLAIMED counts
against a limit**. A counter on the promotion would have to be written during
pricing, which must never commit, so it would either publish a half-written
order or count a draft edited five more times and never approved. Two
behaviours follow and both are deliberate: an offer already exhausted is
**not quoted at all**, so nobody is promised a price the approval would
refuse; and two documents priced while it still had room race at approval,
where the loser is **refused by name** rather than silently repriced --
changing an agreed price underneath somebody is not the service's decision.
A coupon is a way of reaching an offer, not a second kind of one: the
benefit, the conditions and the stacking rule stay on the promotion, and
`sales_orders.coupon_code` is on the order rather than the quotation because
the order is what gets approved. An unrecognised code leaves the order
saveable and simply gives nothing -- a typo in a field that gives money away
must not refuse a sale.

**A coupon is taken where the price is set, on a new bill and on its edit
alike.** A counter bill -- one typed straight in, whose order the service
raised -- is priced on the bill, so any edit of its draft takes a coupon: one
the order does not hold raises the order again with it, the one it holds
changes nothing, leaving it out keeps it, and an explicit `null` takes it
off. The edit that shipped the same used to answer 422 for the coupon the
quantity edit took. A bill of documents somebody raised still refuses one, on
create and on edit ("This bill continues documents already priced, so it
cannot take one."), because a field that gives money away must not be
accepted and do nothing (D-SELL-40).

**"Approval" is the approval of the document a person approves: a counter
bill claims when the bill is approved, not when its hidden order is**
(D-SELL-85, 2026-10-06). The order behind a counter bill is approved at every
*save* of the draft, because that is what reserves the stock, and the claim
was made there with it. So a draft held one live claim, a held bill held one,
and every edit reversed it and claimed again on the order raised in its
place: two unapproved bills could exhaust an offer limited to two, which is
the rule above broken by another route. The chain now approves that order
with `claim_offers=False`, its rows stay PENDING, and
`SalesInvoiceService.stage_approval` makes the claim through the same
`RedemptionService.claim` -- the same lock on the version group, the same
refusal: "Promotion TENOFF has been claimed as often as it allows. Re-save
the document to price it without." A draft, a held bill, an edited bill and a
cancelled draft hold nothing. The rows are still the order's
(`document_type` SALES_ORDER), so the redemption, performance and coupon
reports count one claim per sale as they did, and an order a person types
claims at its own approval exactly as before. **"Re-save" has to be true for
a bill**: a save that changes nothing on a counter bill normally raises
nothing again, so the save asks `RedemptionService.has_run_out` first, and
where an offer the order was priced with has none left the order is raised
again and priced without it -- otherwise the bill would keep a price it can
never be approved at. Sending `coupon_code: null` does the same by hand.
`tests/unit/test_counter_bill_claims_at_approval.py` is the guard.

**A scheme has a budget, and it is counted the way the number of claims is**
(2026-10-06). A principal funds a scheme with "up to 50,000 of discount" or
"up to 500 free units", and an offer could be capped only by how many times
it was claimed. `promotions.max_benefit_amount` and `max_free_quantity` are
the two budgets, null for none, and `promotion_redemptions.free_quantity`
records the free units a claim gave -- more of a line's own product and gifts
of another together -- beside the `benefit_amount` it always carried. Both are
summed from **CLAIMED** rows across the version group by one function,
`budget_rooms` in `promotion_service.py`, which pricing, approval, the list
and the report all read, so they cannot disagree. Nothing is stored on the
offer: a draft has taken nothing, a cancelled order gives its part back, an
order closed short gives back what it never delivered (below), and an edit
carries the budget to the new revision without refilling it.

**What a claim gave is one figure, read from one statement** (D-PRC-28,
D-PRC-34, 2026-10-06). A redemption's `benefit_amount` and `free_quantity`
say what the document **claimed** at approval, and two things make what it
*gave* less: part of it is released when the order is closed short, and a
free unit that came back on a completed return was not given. The offer and
its budgets netted the second and the performance report did not, so one
offer read 3 free units claimed of 3 on its own row and 4 beside the same
cap in the report. `claims_given` in `app/promotions/services/offer_use.py`
is now the one statement -- one row per claim with `benefit_given` (claimed
less released) and `free_given` (claimed less released less returned, never
below zero) -- and `budget_rooms`, the performance report, the redemptions
report, the coupon report and the discount-by-promotion report
(`/sales-invoices/reports/discount-by-promotion`, which gains
`free_quantity`) all group it. Free units come back to **the claim that gave
them**: the order line names the offer and the claim names the order. The
redemptions report shows the netted figures as `benefit_amount` and
`free_quantity` and what the document claimed as `claimed_benefit_amount`
and `claimed_free_quantity`; a REVERSED or PENDING row reads what was
claimed in both. Money is still not netted by a return -- only a short close
moves `benefit_given`; what a return does to the principal's share is in the
claim, below.

**An order closed short keeps what it delivered of a claim and gives back the
rest.** Closing an order with a note or a bill against it used to keep every
claim whole ("the claim was used", D-SELL-22), so an order of 4 under a 10%
offer and a buy 2 get 1, closed after a note of 2, left 40.00 and 2 free
units counted against the two budgets where 20.00 and 1 were given, and a
capped scheme stopped early. `close_order` now calls
`RedemptionService.release_undelivered`: the money each offer took is read
off the order's own lines (`offer_took_off`, the reading a principal's claim
uses) and kept in the share of each line that **left** -- notes whose goods
went out, or a standing bill straight off the order; a note still a draft or
approved at the close can never ship, so its part goes back too -- and free
units are kept as the notes shipped them. The row stays CLAIMED and records
what went back in `released_benefit_amount`, `released_free_quantity` and
`released_at` (`20261006_0339`), with an audit row
`promotion_redemption.released` naming the order; nothing is deleted and
`benefit_amount` is not rewritten. **A count limit is a claim made, not an
amount**: "one use" stays used if anything was delivered. A claim none of
which was delivered is REVERSED, as a cancellation's is
(`promotion_redemption.reversed`), and the use is free again. An order
closed short before `20261006_0339` keeps its whole claim: nothing recorded
how much of it had been delivered.

**An offer that gives a document nothing is not applied, and records no
claim** (D-PRC-32). An offer could match and give nothing -- its free
quantity typed over by hand on the line, its gift product retired, no
delivery charge to waive -- and still read "Applied." and stage a claim of 0
and 0, which used up `max_redemptions` and "once a customer" for nothing.
`apply_one` now undoes such an offer as it does one that overruns its
budget; the trace says "A free quantity was typed on the line this offer
matched, so the offer's own was not given and nothing is claimed." or "This
offer gave nothing on this document, so nothing is claimed." (followed, for
a retired gift, by the sentence that was already there), and a non-stacking
offer that gave nothing no longer stops the offers after it.

**Only a claim can be reversed.** `RedemptionService.reverse` used to turn
PENDING rows REVERSED along with CLAIMED ones, so a counter bill priced again
without its offer -- its hidden order withdrawn and raised afresh -- left a
REVERSED row for a claim never made, and the performance report counted it
under reversed. A PENDING row whose document is withdrawn is dropped, the way
re-pricing a draft drops it. `tests/unit/test_offer_use_is_one_figure.py`
guards all four.

**A claim fits whole or not at all.** Approval refuses the document under the
same lock, in the same function as the count (`RedemptionService._assert_room`):
"Promotion SCHEME has 10.00 left of its budget of 50.00, and this document
would take 40.00. Re-save the document to price it without." -- or "has 1 left
of its budget of 3 free units, and this document would take 2." Giving the
ten that was left would approve a document at a discount no offer states,
which is the silent repricing the count limit already refuses to do. Pricing
follows the same rule, or "re-save" would be a lie: a budget with nothing left
is not quoted, and one with too little left for *this* document is applied,
measured and taken back off, with the figures in the trace ("This offer has
10.00 left of its budget of 50.00, and this document would take 40.00."). A
smaller document that fits is still quoted it. Under best-offer-only, an offer
passed over this way hands the document to the next most valuable rather than
leaving it with none.

Three things to know. The money budget counts what `benefit_amount` counts --
line and bill discount and waived delivery, not the value of free goods, which
are charged nothing; the free budget counts units in the unit each line is
sold in, added across products. A free quantity **typed** on a line stands
(D-SELL-41) and is not the offer's, so `PromotionLineRequest.free_typed` keeps
the engine from counting it; a gift whose product somebody already typed as a
line is still counted, since the engine cannot tell that line from a sale.
And claims made before `20261006_0334` carry a free quantity of zero, so a
free-unit budget put on an offer already running counts from that day. On an
edit the two budgets are the one part of `PUT /promotions/{id}` that is not
replaced whole: left out they keep what the offer has, `null` clears them --
an editor that has never heard of a budget must not lift a principal's by
saving a name. `tests/unit/test_promotion_budgets.py` is the guard.

**Bonus points are an offer settled at approval, not at pricing** (SEL-4,
A73): `LOYALTY_MULTIPLIER` is the only benefit on its offer, the pricing
engine passes over it, and `LoyaltyService.bonus_for` applies the largest
live multiplier whose conditions hold for the bill as a whole when the
points are earned. Multipliers do not stack -- they are rates.

**An offer can hold to days and hours** (SEL-7, A72): `weekday` is the
document date's ISO weekday and `time_of_day` the minutes after midnight in
India time of when the document was raised -- its own `created_at`, so a
later save does not move it across the window's edge. Both ends count; a
window across midnight is two offers, because every condition must hold.

**A campaign's codes are minted as a batch** (SEL-5, A70): up to 5,000 random
`PREFIX-XXXXXXXX` codes against one offer, each single-use in all and per
customer, all or nothing, with one audit row for the batch. Random, never
sequential, so the next code cannot be guessed; drawn from an alphabet with no
0/O or 1/I/L, since it is read off paper. `UQ_promotion_coupons_firm_code`
covers retired codes too, so a candidate clashing with any code the firm ever
minted is drawn again. The offer's codes export as CSV with their uses.

**An order converted from a quotation is priced and claims as an order.**
A quotation quotes offers but claims nothing; converting it used to hand the
order both figures of every line, so every line read as priced by hand, the
engine skipped it and no offer's limit ever saw a converted order (D-SELL-9,
2026-09-19). Only what somebody typed on the quotation -- a line's percentage
or amount, a bill discount -- carries over as typed; everything the pricing
rule derived is derived again by the order on its own date, which is what
stages the pending claim that approval counts under the lock.

**A quotation shows every offer an order would take, and claims none.** It
asked the engine for line discounts only, so an offer on the whole bill, a
free gift and free shipping reached the order and never the quotation, which
read higher than the order it became -- 5,678.16 against 5,265.16 for the
same 60 units (D-SELL-32, 2026-09-19). It is now priced through the same
evaluation as the order, bill, gift and delivery included, and still stages
nothing. What the offers gave is recorded as theirs so the conversion can
leave it to the order: `sales_quotations.bill_discount_source` (only a
`typed` one is handed over, as the order's editor refills only a typed one),
`freight_waived_amount` (the order is handed the charge that was *asked*, and
waives it again only if an offer still does), and a gift line is the one line
with a quantity of zero, which the write schema refuses from anybody else, so
the conversion drops it and the order's offers add it back. One gap stays: a
`FREE_QUANTITY` offer's free goods on a line are indistinguishable from typed
ones, on the quotation as on the order, so they carry over as the line's.

## `customer_type` is a legal classification, not a commercial one

**`customer_type` is a legal classification, not a commercial one.** It holds
INDIVIDUAL or BUSINESS, and hanging a price or an offer on it was never
possible. `customer_groups` is the firm's own segmentation -- Retailer,
Wholesaler, Institution -- added 2026-09-03 with `customers.customer_group_id`
nullable and unassigned, so no existing document changed price. A flat list
rather than a tree: `sales_territories` is already a hierarchy and a second
one leaves two answers to "which group is this customer in". The segment's
rate is the **last** tier of `resolve_line_discount`, below the customer's
own standing rate, because a rate agreed with one shop is more specific than
one agreed with a segment of them. Deleting a group somebody is in is refused
**in the service**: `ondelete="RESTRICT"` is not a guard on a soft-deleted
table, so a retired group would otherwise stay on every customer's record
while vanishing from every list -- the same trap the geography masters have.

## A price list holds a ladder, not a rate

**A price list holds a ladder, not a rate.** `price_list_items.min_quantity`
is the quantity a rate starts at, and `PriceListResolver.rate_for(product,
quantity)` takes the **highest break at or below** the line -- so 0, 50 and
200 prices a line of 120 at the 50. Zero is the ordinary rate, which is what
every existing row became, so no list changed what it promised. Two things to
know: the unique key had to widen to `(list, product, min_quantity)` or a
list could still hold only one row per product, which is the whole
limitation; and a **more specific list replaces the ladder rather than
merging into it** -- a customer's own arrangement is the arrangement, not an
amendment to the firm-wide one, and merging would silently give them breaks
nobody agreed with them.

**A break counts stock units, for the discount as for the fixed rate**
(2026-10-06). A list names no unit, so "from 20" is 20 of the unit the product
is kept in, and a line in another unit is asked about at the stock quantity it
stands for -- the line's quantity times `UomService.stock_factor`, the factor
its stock moves at. D-PRC-25 did this for the list's fixed rate and left the
discount counting the quantity as typed, so 2 BOX of 12 took the *rate* of the
break at 20 and the *discount* of the break at 0: one line, two rungs of one
ladder. The sales order, the quotation and the purchase order (the supplier's
list) all ask `rate_for` at the stock quantity now; a delivery note and a bill
inherit. On a quotation only a line a list actually mentions has its unit
converted, since a quotation converts nothing else.

**Which quantity each thing counts, for a line in another unit than its
stock** -- checked on 2026-10-06, one answer each:

| What | Counts | |
| --- | --- | --- |
| Price list: fixed rate, discount (customer and supplier lists) | stock units | this change and D-PRC-25 |
| Customer price level | nothing -- a level holds one rate per product, no breaks | converted to the line's unit by `price_in_unit` |
| Commission `PER_UNIT` | stock units | this change; `docs/COMMISSION_FRAMEWORK.md` |
| Rate contract | its own unit; a line in another unit is not priced from it | unchanged |
| Supplier's order terms (minimum, multiple) | the line's quantity, in the buying unit the catalogue is kept in | unchanged |
| **Promotions** (line-quantity conditions, buy X get Y, slabs) and **supplier schemes** | **the line's quantity as typed, and free goods in the line's unit** | unchanged -- see below |

**An offer counts the line as typed, and that is still open.** "Buy 10 get 1"
on a line of 12 BOX gives 1 BOX; on 2 BOX of 12 it gives nothing, where 24
pieces typed as pieces earn 2. Counting stock units is the better rule, and
it is not a change to which number is read: the offer's free goods are put on
the line in the line's unit, a box cannot carry two free pieces, and the
claim and the free-unit budget record what the engine gave. Doing it means
free goods in stock units on a line of their own and budgets that count stock
units, inside `app/promotions`. Until then a firm that sells by the box and
by the piece states its offer for the unit it means, and an offer with a
quantity condition should be tried in both units before it is published.

## A discount on the whole document reaches the lines, and therefore the tax

**A discount on the whole document reaches the lines, and therefore the tax.**
`bill_discount_percent`/`bill_discount_amount` on a quotation, sales order,
delivery note or sales invoice is resolved by `resolve_bill_discount` and
split by `apportion` (`app/core/utils/pricing.py`) across the lines in
proportion to what each is worth *after* its own discount, then stored on
each line as `bill_discount_amount`. Three things follow. It comes off what
the lines discounted to, **never off the gross** -- off the gross each
discount is computed as though the other had not happened. The share has to
be **stored and taxed**, not derived at print time: `header_discount_amount`
on a purchase order was subtracted *after* tax, so it reduced no taxable value
and tax was paid on money never charged. D-BUY-19 (2026-09-30) put it on the
lines the same way, and a purchase receipt, bill and return line inherit their
share pro-rated by quantity (`inherited_share`). And the rounding residual goes to the
**largest** line so the shares sum exactly to the figure they split; a
document whose lines do not add up to its own total is one no reconciliation
can accept. A conversion carries the *deal* and re-splits it, because copying
each line's share agrees only while both documents hold the same lines; a
sales return **inherits** its share pro-rata from the line it credits, since
crediting the undiscounted figure hands back more than was charged. All four
sales services price every line before taxing any of them for this reason --
`sales_invoice` carries the intermediate state in `_PricedInvoiceLine`.

**The order's bill discount goes down the chain with the lines** (D-PRC-1,
2026-10-06). A delivery note read only a bill discount typed on itself and a
bill read only its own, so an order approved at 5,265.16 -- a 7.5% line offer
and an offer of 200 off the bill -- was delivered and billed at 5,501.16, and
the journal followed the bill; a typed 100 and a typed 10% were lost the same
way, while freight was carried. A note line now takes its order line's stored
share and a bill line its note line's, by the quantity it continues, exactly
as a line discount amount is inherited. The slice is `continued_share`
(`app/core/utils/pricing.py`): the share up to where this part stops less the
share up to where the earlier parts stopped, each rounded once, so two notes
and two bills of one order sum to the order's figure and its tax to the
paisa and the part that completes the line takes what rounding left. "Earlier
parts" are the approved notes of the order line, and every live bill of the
note line. The header shows the total inherited and the rate it comes to.

**A figure typed on the note or the bill replaces the inherited one**, zero
included -- the freight precedent, where silence inherits and `0` waives. It
does not add: a document then states its own discount, split by `apportion`
over its own lines, and one that continues an order has one rule rather than
two figures to reconcile. A figure **equal to the one inherited is the
inheritance sent back** (the editor refills the box with the rate it was shown
and re-sends it on every save), so it keeps the source lines' own shares and
moves nothing. On a bill of documents an explicit `null` means "as the
documents say", as it does for freight; typing `0` is how the discount is
refused. `sales_invoices.bill_discount_source` (migration `20261006_0336`)
says `typed` or `inherited`, and both readers need it: an edit that leaves
the discount out carries only a typed one as its rate (an inherited one is
inherited again at the share now billed, and a counter bill asks the order it
raised, whose `bill_discount_source` says `typed` or `promotion`), and the
approver's discount limit judges only a typed one -- an offer's 200 is
nobody's hand, and a typed order's was judged on the order. Nothing is
written to `promotion_redemptions` on the way down: the claim is the order's,
and what the performance report says an offer gave is now what came off the
bills.

**A line's own discount is sliced the same way, by whoever raises the note**
(D-PRC-22, 2026-10-06). With the delivery-note stage off, a bill of part of an
order raises the note itself (`SalesChainService._note_line`), and that hidden
line *stated* the order line's whole `discount_amount` -- and an amount stated
beats everything. An order of 10 at 100.00 with 100.00 off the line and 90.00
off the bill, 955.80, billed 4 and then 6, took the 100.00 off both bills:
311.52 + 526.28 = 837.80, the customer under-billed 118.00 and 18.00 of GST
never charged, the same whether the order's discount was typed as an amount or
as 10%. The hidden line now says nothing about a discount, as a note a person
types says nothing, and one rule serves both. Silent, **at the price of the
line it continues**, a note line takes its slice of the order line's
`discount_amount` and a bill line its slice of the note line's
(`continued_share`, with the same "earlier parts" as the bill discount), so
the parts sum to the order's discount exactly: 100.00 off 3 units is 33.3333,
33.3334 and 33.3333 over three bills, where the order's rate of 33.3333%
applied to each part alone lost a ten-thousandth each time -- on a counter
bill as well, whose bill read 99.9999 under its order's 100.0000. The rate
recorded beside the slice is derived from it, so a percentage is still read as
that percentage. A line continued **at another price** inherits the rate as
itself, because the order's amount no longer describes it. The bills above are
382.32 and 573.48. Free goods needed no change: a part bill's hidden note
already said nothing about them.

## A bill can state what was given away

**A bill can state what was given away.** `free_quantity` is goods supplied at
nil value: outside the gross and outside the tax base, but real stock leaving
the warehouse. It existed on quotation, sales order and delivery note lines
and **not on the sales invoice** until 2026-08-23, so goods could be
promised, ordered and dispatched free and then not appear on the document the
customer reads. The invoice **inherits** it from the line it bills, pro-rated
by the share being billed, and **refuses** more than the source line offered
-- the goods left on somebody else's document, and a bill claiming free goods
nobody dispatched is one the warehouse cannot reconcile. The desktop's
quotation editor is the only screen that can give a line away; there was no
field for it anywhere before, so the column was unreachable without the API.

## Free goods can come back, credited nothing

**Free goods can come back on a sales return, credited nothing** (D-PRC-8,
2026-10-06, the selling twin of D-BUY-56). A bill of 12 + 1 free: the return
of the 12 went through and a second return of 1 for the same line was refused
-- "(12.0000 sent, 12.0000 already returned)" -- because a return was capped
at what the line *charged* for. The thirteenth unit had nowhere to go but a
stock adjustment. `sales_return_lines.free_quantity` (migration
`20261006_0337`) is the free goods a line brings back **beside** its charged
units, and `current_return_quantity` stays the charged ones, which every
price, tax, billing and credit figure is worked on.

On the request, `current_return_quantity` is **everything coming back** and
`free_quantity` says how many of those are free. **Left blank, the charged
units are taken first** and only what comes back beyond them is free, so the
return of "the last one" above simply works; a number says so outright -- the
free unit coming back on its own while the charged ones stay sold. The
response reads the same way: the total, and the free part of it. A line may
bring back what its source line sent, charged and free, less what earlier
live returns took of each, and the refusal says what is left: "Return quantity
exceeds what was dispatched on the source document (4.0000 sent and 1.0000
free, 0.0000 and 0.0000 already returned; line 1 can still bring back 4.0000
charged and 1.0000 free)." A source line with no free goods keeps the wording
it had. Unlike a purchase return, **a line off the bill may bring free goods
back as well as one off the note**: a counter firm never sees its notes, and
the bill line carries the free quantity it inherited.

**The same free unit comes back once, whichever document the return names**
(the twin of D-BUY-61). The charged cap already counted across the note line
and the bill line that billed it (`_goods_behind`, D-SELL-7); the free cap
does the same against the note line's `free_quantity`: "Free quantity exceeds
what left free on DN-… (1.0000 sent free, 1.0000 already returned against it
or the bill for it)."

Free units are priced, taxed and credited nothing -- a line of free goods
alone posts no credit note and writes nothing to the customer's account --
and **arrive in stock with the charged ones at the cost the product is
carried at**, so `Dr Inventory / Cr Cost of Goods Sold` follows the whole
movement. The damaged and scrap buckets are parts of everything that came
back. The by-product report counts them in `return_quantity` and states them
in `free_quantity`, with no value; the register, the by-customer report and
the summary read the credited amount, which they do not change. **GSTR-1 is
left alone, deliberately**: a bill's free goods are not in its HSN quantity,
so a credit's free goods are not either -- adding them only on the way back
would net a product's quantity below what was declared sold.

**A free unit that came back was not given.** Two readers count free goods on
the way out, and both net what completed returns brought back through one
join (`free_goods_returned` in `app/sales_return/free_goods.py`, by either
route). An offer's free-unit budget: `budget_rooms` takes the units returned
off lines whose order line names the offer (`free_promotion_id`) out of
`free_claimed`, so a scheme of 500 free units that gave 2 and took 1 back has
given 1 -- since D-PRC-34 through `claims_given`, which every report of the
offer reads too. The money budget is not moved by a return -- nothing nets
`benefit_amount` for one. And the principal's claim: the preview for a period
leaves out free goods that have since come back, a line with nothing left is
dropped, and **a claim already raised is not rewritten** by a return that
comes after it: the next claim takes it back (below).
`tests/unit/test_sales_return_free_goods.py` is the guard.

**A note that says nothing ships the order's free goods** (D-PRC-4,
2026-10-06). `free_quantity` on a delivery note line defaulted to `0`, so
silence and a refusal were one value: an order of 12 with 1 free shipped 12,
stayed part-delivered with one unit reserved, and its bill showed nothing
free. The field is `Decimal | None` now, for the reason the price and the
discount are. `None` takes the order line's free goods in proportion to the
quantity shipped, **in whole units** (`continued_free_goods`): what the share
shipped so far has earned less what already went, and the delivery that
completes the line takes all that is left -- 1 free on 10 shipped 4, 3, 3
goes with the last three, never as 0.4 of a gift and never twice. A number is
taken as typed and `0` ships none. A bill inherits from its note the same
way, so a note billed in parts states whole units too. A line of quantity 0
that is silent about free goods is judged in the service, which alone knows
whether its order line gives any. **The desktop's note editor still sends an
explicit `0`** from a box that starts at 0, so the screen ships no free goods
until it sends nothing for a blank box.

**A principal is asked for what was passed on to a customer, not for what an
order claimed** (D-PRC-27, 2026-10-06). A redemption is the order's: it is
claimed at approval and its `benefit_amount` is what the offer took off the
order. The claim read that figure, so with a 10% offer of which the principal
bears half, an order of 4 at 100.00 claimed 20.00 from the principal whether
it was never delivered, closed after half was delivered (10.00 passed on) or
billed and returned in full. The scheme money on a claim is now read off the
**approved bills dated in the claim's period**
(`app/principal_claims/services/passed_on.py`): each bill line's share of its
order line -- the part of the note line it billed times the part of the order
line that note shipped -- of what the offer took off that order line (the line
discount where the order line's `discount_source` is `promotion`, its share of
the bill discount where the order's `bill_discount_source` is `promotion`, a
waived delivery charge by value). That is the figure the bill line inherited
(`continued_share`), taken from the order's own numbers so a discount somebody
typed over downstream is not charged to the principal. **Less what came
back**: a completed sales return of the bill line or of the note line it
billed, and an approved credit note against it, take the same share of the
discount back -- 1 of 4 returned leaves three quarters. Nothing billed,
nothing claimed. Three things to know:

- **The source is the redemption and the bill**, `scheme_bill_source`, a
  fixed-namespace key like a rate difference's, so a line reads
  `source_number` = the bill's number, `source_date` = the bill's date and
  "Promotion P10 on order SO-...". Two part bills are two sources; a part
  billed in a later month is claimed in that month's claim and in no other;
  and the partial unique index on the lines refuses the same bill's discount
  a second time.
- **A claim already raised is not rewritten.** One raised before this rule
  holds the redemption whole under its own id, and none of that redemption's
  bills is claimed again while it stands.
- **An order records one discount per line, not which offer gave how much of
  it**, so where several offers took money off one order each redemption
  takes the order's passed-on discount in proportion to its own benefit. With
  one offer on the order that is the discount exactly.

Returns and credit notes are netted as they stand when the claim is previewed
or raised, whatever their date. `tests/unit/test_principal_claim_scheme_bills.py`
is the guard.

**What comes back after a claim was raised comes off the next claim**
(D-PRC-31, 2026-10-06). A claim of 120.00 was raised, one of its two free
units came back, and nothing anywhere took the 30.00 back: the claim stood,
no later preview showed anything negative, and cost of goods sold had been
credited for that unit twice. Cancelling and re-raising netted it, which a
part-settled claim refuses. The claim raised is still **not rewritten** -- the
principal may have paid it -- and the next claim on that principal carries a
negative **adjustment line**, the debit adjustment a distributor carries
forward to its next claim:

- **What is owed back is summed, never stored.** For an earlier line of kind
  SCHEME or FREE_GOODS that something has come back against (a completed
  return, an approved credit note, the bill cancelled), the source is worked
  again exactly as a claim raised today would work it, and the adjustment is
  what the line was claimed for -- its amount plus the live adjustments
  naming it (`principal_claim_lines.adjusts_line_id`, `20261006_0340`) --
  less that. A second look therefore finds nothing more to take, and a
  return that was already netted when the claim was raised owes nothing.
- **The line** has the earlier line's kind, document number and date, a
  negative `amount` (and, for goods, a negative `quantity`), and reads "Came
  back after claim CLM-... (SR-...): Free goods under Acme 2 + 1". Its
  `source_id` is `adjustment_source(line, n)`, so two claims raised at once
  cannot both take it. The response names the earlier claim in
  `adjusts_claim_number`.
- **A claim is never negative.** It is settled by a payment or a credit note,
  and neither can settle less than nothing. Adjustments are taken oldest
  claim first as far as the claim's own lines reach; the one that would take
  it below zero is taken in part and the rest is **carried forward**
  (`adjustments_carried_forward` on the preview) to the claim after. A claim
  that nets to exactly 0.00 is raised and reads SETTLED. With nothing new to
  claim, none is raised: "Nothing is left to claim from Acme Ltd for that
  period. Goods or discounts worth 30.00 came back after earlier claims; that
  comes off the next claim on this principal that has something to claim."
- **The ledger mirrors what the earlier line credited**: an adjustment for
  goods debits cost of goods sold and one for a discount debits promotional
  expense, inside the new claim's one journal
  (`docs/LEDGER_POSTING_RULES.md`).
- **The earlier claim cannot be cancelled from under its adjustment**: "Claim
  CLM-... takes back goods or a discount that came back after this claim was
  raised; cancel that claim first." Cancelling the later claim frees the
  adjustment, and the next preview shows it again.

Three limits. Only documents dated within two years before the new claim's
period are looked for (`_LOOK_BACK`), so a preview does not re-read every bill
the firm ever claimed. A scheme line raised before D-PRC-27 names its
redemption, not a bill, and is never adjusted. And expiry, breakage and rate
difference lines are not adjusted: nothing brings them back.
`tests/unit/test_principal_claim_adjustments.py` is the guard.

**Goods given free are claimed from the principal at what they cost**
(2026-10-06). A claim (`app/principal_claims`) counted a scheme's money
from its redemptions' `benefit_amount`, and free goods are no part of that figure -- they take
nothing off a bill -- so a principal's "2 + 1" offer claimed nothing, and the
"10 + 1" a salesman types was no source at all. Both now are, from one read of
the period's **shipped** delivery note lines (`_free_goods`), valued from the
stock ledger's DISPATCH for the note and product, split over the note's lines
by what each shipped and then by the free part of the line. **NULL cost is not
zero cost**: a dispatch with no cost on the ledger contributes nothing. The
journal gives the cost back where the dispatch put it -- Dr claims receivable,
Cr **cost of goods sold** -- not to promotional expense, which is where a
scheme's discount goes.

**Whose free goods they are is written on the order line.**
`sales_order_lines.free_promotion_id` names the offer that gave the line its
free quantity -- on the line, or as the gift line the engine added -- and is
null where a person typed the figure. An offer's free goods are claimed under
**SCHEME**, from the principal that funds that offer and at its
`principal_share_percent`, whatever the product; typed free goods are their
own kind, **FREE_GOODS** (`principal_claims.free_goods_amount`), claimed in
full where the product's brand is the principal's. Free goods under an offer
the firm funds itself are claimed from nobody. Three limits. A line written
before `20261006_0335` has no marker and reads as typed. An editor that sends
an offer's free quantity back as a figure makes it a typed one on that save --
the gap the quotation section above records -- which also takes it out of the
offer's free-unit budget; `SalesOrderLineResponse.free_promotion_id` is there
so an editor can leave the box blank instead. And a sales return of the
charged units alone reduces no claim: the free goods stayed given. Free
goods that did come back are netted, below.
`tests/unit/test_principal_claim_free_goods.py` is the guard.

**A principal's price cut is claimed on the stock in hand** (rate difference,
2026-10-06; gap 2 of the pricing market study). The principal lowers its rate
from a day and owes the firm the difference on what stood on the shelf when
the day before closed -- the claim a Marg or Busy user writes up from a stock
statement and a debit note. It is a fifth kind, **RATE_DIFFERENCE**
(`principal_claims.rate_difference_amount`), and the only one that is not a
period's: `POST /api/v1/principal-claims/preview` and `POST
/api/v1/principal-claims` take `kinds: ["RATE_DIFFERENCE"]` with an
`effective_date`, the claim's period is that one day, and the kind stands
alone on its claim -- a period's claim never gathers it, and `kinds` left out
still means the period's four. Five decisions:

- **The rate is the purchase rate per stock unit before tax** -- what the
  principal bills the firm, which is the thing the cut lowered. Not a batch's
  `pts` or `ptr`: those are what the *firm* sells that batch at, and a batch
  keeps one figure with no history, so there is no "before" to read. The new
  rate defaults from the product's price revision dated that day
  (`product_price_revisions.purchase_price`) and the old one from the rate in
  force the day before -- the latest earlier revision, else the product's own
  purchase price. **A typed rate replaces either**, because the principal's
  circular is the authority and the revision is only somebody's copy of it;
  the line says which it used. A supplier catalogue price
  (`supplier_products.unit_price`) is not read: it is per purchase unit, not
  per stock unit. A revision that lowers only the MRP proposes nothing -- the
  claim is on what was paid -- and that product is added with its rates typed.
- **The stock is never typed.** It is the sum of the movements dated on or
  before the day before the cut, every warehouse together -- the quantity
  *Stock valuation* shows as on that day, so the principal's auditor and the
  firm read one figure. A receipt dated on the day of the cut came in at the
  new rate and is no part of it. A product kept by batch is one line per batch
  with stock; a line that names no batch covers every batch no other line
  names. A cut dated after the firm's today is refused: yesterday has not
  closed.
- **Left to itself the preview proposes; given lines, it takes exactly those.**
  With no `rate_lines` it is every product of the principal with stock and a
  recorded cut that day, less what a live claim already holds; a rise, an
  unchanged rate and an empty shelf are left out in silence. With
  `rate_lines` -- the proposed ones as corrected, less any taken off, plus any
  added by product -- a line that can claim nothing is **refused by name**
  rather than dropped: not the principal's product, a new rate not lower than
  the old, nothing on the shelf, or no rate typed and none recorded.
- **The same stock is claimed once for one cut.** A rate difference has no row
  to name as its source, so the source is a key made of the principal, the
  product, the batch and the effective date (`rate_difference_source`), held
  by the same partial unique index as every other kind. A second claim is
  refused naming the claim that holds it; cancelling that claim soft-deletes
  its lines and frees them. A second cut on another day is another source.
- **The stock is not revalued, and the claim carries no tax.** The moving
  average stays where the purchases put it and the goods leave at the dearer
  cost; the journal -- Dr claims receivable, Cr **purchase price variance**
  -- puts the principal's money beside that cost of sales, where it offsets
  it. Where the principal settles by a GST credit note (section 34) the firm's
  input credit comes down by that note's tax: book the note as a supplier
  credit note, which is where the tax is reversed. The claim itself never
  states any.

Settlement, cancellation and the statement are the other kinds' -- the PDF
gains a *Rate difference on stock in hand* table of item, batch, quantity, old
rate, new rate and amount. `tests/unit/test_principal_claim_rate_difference.py`
is the guard.

## What may be billed is what was charged, not what left the warehouse

**What may be billed is what was charged, not what left the warehouse.** A
delivery note line holds both figures and they are not interchangeable:
`current_delivery_quantity` is what the customer is charged for, and
`delivered_quantity` is that plus the free goods converted into inventory
units, which is right for stock because all of it left. `sales_invoice`
capped billing on the second until 2026-08-24 and was wrong three ways for
it. It **let a bill charge for the gift** -- a seeded note dispatching 12
with 1 free had all 12 billed and still offered a thirteenth unit, accepted
at 195.00 plus tax. It pro-rated the inherited free goods by the wrong
denominator, so a full bill carried 12/13 of a free unit and printed
"12 + 0.923 free". And the units disagree -- `invoice_quantity` is converted
into the source line's *sales* UOM, `delivered_quantity` is post-conversion
inventory units -- so for any product whose two units differ the cap was
inflated by the whole conversion factor. The siblings were checked and are
right: `purchase_invoice` and `purchase_return` cap on `accepted_quantity`,
which excludes free goods, and `sales_return` on
`current_delivery_quantity`. **A quantity that has had free goods added to
it or been converted into another unit is not a billing cap**; the only
reason this survived was that every test billed from a sales order, where
the field is plain `quantity`, so the delivery-note path had no coverage at
all. Found by reading a rendered bill rather than the code.

## `FREE_PRODUCT` emits a line rather than setting a field

**`FREE_PRODUCT` gives something the document never mentioned, so the engine
emits a line rather than setting a field.** `FREE_QUANTITY` gives more of
what was bought and adjusts an existing line; there is no line to adjust for
a different product. `PromotionEvaluationResponse.gifts` is what the engine
answers with, and `SalesOrderService._gift_lines` appends them **before
anything is priced**, so a gift flows through conversion, tax and totals on
the same path a typed line does. The threshold is counted across the lines
the offer **matched**, not per line -- ten bought as two lines of five is
still ten. No threshold means give it once, because the condition is then on
the document. A gift the caller already typed is not doubled. And the gift
line sets `discount_percent` to an **explicit zero**: silence would let the
customer's standing rate resolve, and the line stores the rate it resolved,
so a bill for nothing would print a discount percentage. Making that true
exposed a hole in `resolve_line_discount` -- on a zero-gross line the
recorded rate came off `percent or price_list_percent or customer_default
or ...`, which is falsy for an explicit zero, so a refusal recorded the
customer's rate. It reads the branch actually taken now.

## An offer names only the firm's own masters

**An offer names only the firm's own masters, and a bad one cannot stop a
sale** (D-PRC-5, 2026-10-06). An ACTIVE offer giving away
`00000000-0000-0000-0000-000000000001`, or another firm's product, was
accepted with 201, and every quotation and order it matched then answered
500. Two things were wrong and they were found together. Nothing looked the
ids up: `assert_offer_references` in
`app/promotions/services/references.py` now asks, of every id-typed condition
(product, product category, customer, customer group, branch, territory,
route -- an `IN` list entry by entry) and of every benefit (the product a
`FREE_PRODUCT` gives, the products of a `COMBO_PRICE` set), that the row is
**live and this firm's**, and refuses with 422 naming it: "Benefit 1: the
free product was not found in this firm.", "Condition 2: the customer group
was not found in this firm.", "Benefit 1: a product of the combo was not
found in this firm." It reads the stored shape, so a new offer, an edited
draft, the revision that supersedes a live one and a copy (prefixed with the
offer's code, all or nothing) all ask through it. **An offer being switched
INACTIVE is not checked**, or one holding a product retired since could not
be stopped by the person who owns it. A salesman condition is not checked:
`users` is a platform table.

The second half is the reader. A product can be retired after the offer was
written, and rows written before the check are still in the store, so
`PromotionService._gift_product` passes over a gift whose product is not a
live product of the firm and the trace says "The product this offer gives
away is not one of this firm's products any more, so nothing was given."
And **a `FREE_PRODUCT` offer with no buy quantity crashed on its own**: the
stored shape spells a missing threshold as the text `"None"`, the engine
read it as a number, and that -- not the product -- is what raised on the
checked firms, whose offer was "nine bought, one free" with the nine on a
condition. `_number` reads it as no threshold, which is "give it once".
`tests/unit/test_promotion_references.py` is the guard.

## A downstream document inherits the price of the line it continues

**A downstream document inherits the price of the line it continues.** A
delivery note ships at the order line's price and an invoice bills at the
note line's, where the caller says nothing -- the same rule the discount and
the free goods already followed, and for the same reason: re-deciding the
price one document later is how an agreement gets quietly rewritten.
`unit_price` on both line-write schemas is `Decimal | None` with **no
default** for exactly the None-versus-zero reason everything else here is:
silence means "whatever was agreed" and zero means goods given away. It used
to default to `Decimal("0")`, so the two were the same value and a caller
that named a source line and omitted the price got a note valued at nothing
and a bill for nothing -- no refusal, and nothing on the document to say
why. Nothing was broken in practice because the desktop and the seeder both
passed it, which is also why it survived: **the fixtures repeated the price
too, so every test proved the number it had just supplied**. Found by
driving the chain with minimal payloads.

## Free shipping waives the charge; it does not discount it

**Free shipping waives the charge; it does not discount it.**
`PromotionActionType.FREE_SHIPPING` sets the document's `freight_amount` to
nothing, so nothing is charged for delivery and nothing is taxed on it -- a
document showing a delivery charge beside a discount cancelling it says
something different from one showing no charge. The action takes **no
parameter**: a partial waiver is `BILL_DISCOUNT_AMOUNT`, which already
exists. The engine is told the charge (`freight_amount` on the request) and
answers `freight_waived`, because it cannot waive what it has not been told
about, and an offer on a document with no delivery charge gives nothing
rather than claiming to. Waived whole or not at all, so two offers cannot
waive it twice -- and the waived amount counts towards `benefit_amount`,
since a campaign that gave away shipping cost the firm exactly that.

## Loyalty and cashback are one ledger

**Loyalty and cashback are one ledger, and redeeming settles a bill rather
than discounting it.** `app/loyalty` holds a firm's scheme and every movement
of credit under it; what a firm calls the scheme is a matter of the
conversion rate. The design turns on the tax: a redemption **settles** the
bill, so the supply is worth what it is worth and the full GST is charged --
treating it as a discount would reduce the taxable value and so the tax
collected, which is a decision about tax and not one this module makes
quietly. **Points cost the firm money when earned, not when spent**
(`Dr Loyalty Expense 5700 / Cr Loyalty Payable 2600`), so a scheme's cost
lands in the month it was incurred; redeeming is `Dr Loyalty Payable /
Cr Accounts Receivable` **and** a `LOYALTY` receivable transaction, because
the journal alone moves the control account while the customer's own balance
stays put -- the two books then drift by every redemption, which
`verify_sample_data.py` caught within minutes of the seed running. The
balance is the sum of the ledger and never a column; a redemption is refused
rather than trimmed; an adjustment **posts both ways** -- points given are
accrued as an earning is and points taken back are released as a lapse is,
at the scheme's current value per point (D-SELL-19, 2026-09-19: it used to
post nothing, so goodwill points spent on a bill debited `Loyalty Payable`
for a debt never raised and drove it below zero); and expiry is a sweep that
names the entry it takes, so it can be run twice. A completed sales return and an
approved credit note **take back the points the bill earned on the value
credited** -- in proportion to the bill, capped at what is left of the batch,
with their cost released as a lapse is -- and cancelling either gives them
back (D-SELL-47, 2026-10-05: a customer who returned everything used to keep
the points). `expiry_months` NULL means points never
expire -- zero would mean they expire the day they are earned.

## Points expire out of what is left of a batch

**Points expire out of what is left of a batch, and their cost comes back
with them.** Two defects, found by the 2026-09-03 review. `expire` wrote
back the *whole* earned entry, so a batch the customer had already spent
lapsed a second time and left them on **negative points** -- the balance is
a sum over the ledger with no floor, and `redeem` refuses anything above it,
so the sweep was the only way below zero. Spending is allocated **oldest
batch first**, which is why the fix cannot just cap at the balance: a
customer with one lapsing batch and one fresh one, who spent the older
one's worth, keeps the fresh one in full. And nothing reversed the accrual
when credit ran out of time, so `Loyalty Payable` kept a debt nobody could
claim -- nine lapsed batches worth 936.31 in WHOLE01 with no journal between
them, against 49 earnings that had all posted. A lapse now posts
`Dr Loyalty Payable / Cr Loyalty Expense` for the share that lapsed, and
`expire` takes an `actor_id` because a journal with no author is one nobody
can ask about.

**A lapsed point is not spent, swept or not** (D-PRC-3, 2026-10-06). The
sweep was the only thing that took a batch out of the balance, and the only
caller of the sweep was `POST /api/v1/loyalty/expire`, so a firm that never
pressed it never expired a point: 70 of 70.8 points nine days past their date
settled 70.00 of a bill. A batch is good **through** its expiry date and
lapsed from the day after on the firm's own day (`firm_today`) -- the line
the sweep and the expiring report already drew -- and now the balance, the
balances report and a redemption draw it too. `GET /loyalty/{customer}`
answers `points`, `amount` and `redeemable` without what has lapsed, with
`lapsed_points` beside them, and the balances report carries `lapsed_points`
and `lapsed_amount` so that `amount + lapsed_amount` is still what Loyalty
Payable holds until the sweep runs. **Redeeming stages the lapse first**, for
that customer's overdue batches, in the same transaction and with the same
`Dr Loyalty Payable / Cr Loyalty Expense`, so the ledger is right the moment
anybody spends; asking for more than is left answers "That customer holds
2.3600 points, not 70.0000. 70.8000 more ran out of time on 2026-09-27 and
can no longer be spent." and writes nothing. The expiring report still lists
a batch awaiting the sweep: its cost is still owed, and the row is the notice.

**Points are taken back only from what can be spent** (D-PRC-30, 2026-10-06).
A redemption drew the line and the three things that take points *away* did
not. `adjust` checked a negative figure against the raw sum of the ledger and
pooled it oldest batch first, so a customer with 2.36 points live and 70.80
lapsed had -50 accepted ("Balance adjusted.", Dr 2600 50.00 / Cr 5700 50.00)
and could still spend 2.36: the 50 had come out of the lapsed batch. A
negative adjustment, the take-back of a return or a credit note
(`stage_take_back`) and the take-back of a cancelled bill (`stage_reversal`)
now **stage the lapse first**, exactly as a redemption does, and then read
what is left:

- An adjustment beyond it is refused and writes nothing: "That customer holds
  2.3600 points that can be spent, so -50.0000 would take the balance below
  zero. 70.8000 more ran out of time on 2026-09-27 and are gone already." An
  adjustment of -2 leaves 0.36 to spend, with the 70.80 lapsed in the same
  transaction and its cost released. A positive adjustment lapses nothing.
- A return, a credit note or a cancellation of a bill whose points have run
  out of time **takes nothing back**: the batch has nothing left, the lapse
  (an EXPIRED row naming the batch, with its journal) is the record of where
  the points went, and no shortfall is carried against the customer's other
  points -- the module never had that notion; a take-back was always "what is
  left of the batch".

`tests/unit/test_points_taken_back_are_spendable.py` is the guard.

**So that the cost does not wait on somebody remembering**, the sweep is a
subcommand of the shipped binary, `agency-server loyalty-expire`
(`sweep_every_firm` in `app/loyalty/services/expiry_sweep.py`): every live
firm from the registry, each in its own store, one line per firm, non-zero
when a store could not be reached. Nothing schedules it; that is the
operator's to arrange, as the retention purge is. Its lapses carry the nil
actor an unattended reservation lapse carries.

**Oldest first is the day, then the order written** (PRCQ-21). The ledger was
walked by `earned_on` and then by id, and an id is random, so two batches
credited the same day were spent in either order: 70 points cost 129.47 where
the older batch first cost 80.53. `created_at` breaks the tie now, in the
allocation and in the balances report alike.

**Cancelling a bill takes back what is left of the points it earned.**
`cancel_invoice` reversed the invoice's journal and never touched the
ledger, so a cancelled sale's points could still be spent and `Loyalty
Payable` kept their accrual (D-SELL-2, 2026-09-19). `stage_reversal` writes
a `REVERSED` entry naming the earning, and reverses the `LOY-SI-…` accrual
as `LOY-SI-…-REV` -- a mirror when the whole batch comes back, the share
that is left when it does not. It takes **what is left**, by the same
`unspent_batches` answer the sweep uses: a share that lapsed already had its
cost released, and a share already spent settled another bill, which the
cancellation does not undo. `unspent_batches` attributes a reversal to its
batch as it does an expiry, rather than pooling it with spends.

**A redemption can be undone, and cancelling a bill undoes the ones on it**
(D-PRC-6, 2026-10-06). A bill of 118.00 with 10 points spent on it answered
422 to its cancellation -- "...cannot be cancelled while it has loyalty points
spent on it. Reverse or cancel those first." -- and no route reversed a
redemption, so nobody could ever cancel it. The rule was copied from money: a
receipt on a bill is reversed by a person first, deliberately, because cash
changed hands and somebody has to say what became of it. **Points are not
money that changed hands**, and there is no receipt screen to reverse them
on, so `cancel_invoice` puts them back itself, in its own transaction, before
it takes the bill off the customer's account
(`RedemptionReversalService.stage_for_cancelled_bill` in
`app/loyalty/services/redemption_reversal.py`). A bill that also has a receipt
is still refused for the receipt, and nothing is touched. A redemption keyed
against the wrong bill is undone on a bill that stays by
`POST /api/v1/loyalty/redemptions/{entry_id}/reverse` with a `reason`, on
`LOYALTY_MANAGE` -- the code the redemption itself takes.

**A redemption undone is a second `REDEEMED` row with its signs turned**,
naming the first in `reverses_id`: the points positive, the amount negative.
What a bill owes is everywhere the sum of its `REDEEMED` amounts and a balance
is the sum of points, so every reader nets it without being told, and a
statement as of a day between the two still reads the bill as settled. Three
things go back together, each by the record of what was done: the journal is
mirrored (`Dr Accounts Receivable / Cr Loyalty Payable`) as
`LOY-RED-<bill>-REV`, or `LOY-RED-<bill>-2-REV` for a second redemption, so
two never share a reference; the customer's balance goes back by the deltas
stored on the `LOYALTY` row the redemption wrote; and the points return to
the batches -- the redemption leaves the spending `unspent_batches` allocates
oldest first, so each batch holds again what it held, on its own expiry date
and at its own value. **A batch that has since lapsed stays lapsed**: the
share returned to a batch already past its date is written off there and
then as `EXPIRED` with its cost released, exactly as the sweep would have
done had the points never been spent, and what such a batch held before is
left to the sweep. It is undone once ("Those points were already put back, on
2026-10-06."), and the row that puts points back cannot itself be reversed --
the way to spend them again is to redeem them.
`tests/unit/test_loyalty_redemption_reversal.py` is the guard.

**A point keeps the value it was credited at.** Every credit -- points
earned on a bill and points given by hand -- is a batch carrying its own
value per point (`amount / points`, stored when it was credited).
Redeeming, taking points back, a lapse and a cancellation all release the
batches they use up, oldest first, each at that batch's own value, and the
balance a customer is shown is worth the same. A change to
`amount_per_point` prices only points credited after it (D-CFG-3,
2026-09-19: a redemption and an adjustment valued points at the rate of
the day, so raising the rate debited `Loyalty Payable` more than was ever
credited and lowering it left a residue there for good). Goodwill given
before goodwill was booked at all (D-SELL-19) carries no value and is still
spent at the rate of the day.

## Freight is the bill discount's mirror image, and it has to reach the line

**Freight is the bill discount's mirror image, and it has to reach the
line.** `freight_amount` on the four sales documents is what the customer is
charged for delivery, and it is **part of the taxable value**: a charge the
seller makes for getting the goods to the buyer is part of the value of the
supply. It is apportioned across the lines by the same `apportion`, on the
same weights (what each line is worth after its own discount), with the
residual to the largest line -- one lowers each line's taxable value and the
other raises it. Being on the line is the whole point: a document-level
figure that never touches a taxable value taxes nothing, which is what
`header_discount_amount` did on a purchase order until D-BUY-19. `additional_charges` stays **outside** the tax and is left alone --
it is for additions that really are outside it, and re-taxing it would
change every document that carries one. A line discounted to nothing carries
no freight; freight and a bill discount both survive on the line rather than
netting; and both `app/gst_returns` and the e-invoice payload put it inside
the taxable value, since leaving it out declares less than the invoice
charged tax on.

**Freight that is taxed is also billed.** The line's `net_amount` and the
document's `subtotal` carry its freight share on every sales document, so
`grand_total`, the receivable and the journal follow; the sales invoice left
it out of all three until D-SELL-37 (2026-09-24), taxing a delivery it never
charged for. It is credited to sales revenue with the goods, and the
commission base leaves it out.

## A sale below cost or below a minimum price warns, and blocks only if a firm asks

BACKLOG 64 row 2, built 2026-10-01 (`app/sales_order/services/price_floor.py`).
A line's **net** value -- gross less its own discount and its share of the
bill discount -- is compared with a floor for the stock it moves: the
product's `minimum_selling_price` and, unless the firm turned it off, its
cost (the moving average, else the purchase price). Both are **per stock
unit**, the unit cost is kept in, so a line sold by the box is judged on the
box's share. Free goods charge nothing and are never judged.

It is judged at **approval** -- a sales order, and a bill, which may have no
order or re-price the one it bills; the order a counter bill raises for itself
is not judged twice. `price_floor_settings` holds OFF, WARN (the default, and
what a firm with no row gets) or BLOCK, and whether cost counts. Under BLOCK
the approval is refused unless the caller holds `SALES_PRICE_OVERRIDE` and
gives `price_override_reason`, which the APPROVED event keeps -- the licence
check's shape. `SALES_MANAGER` does not hold the override, for the reason it
does not hold the credit policy: it is a control over the role. A message
names a minimum price but **never the cost**, because whoever sells may not
be allowed to see it. `GET .../{id}/price-check` answers the same question
before approving.

**Near-expiry stock is exempt (decision A2, 2026-10-02).** A line drawn wholly
from batches inside the firm's near-expiry window may be sold below its floor
unless the firm turned that off (`batch_sale_settings.near_expiry_below_floor`).
The finding is still made, with `exemption` naming the batches, and kept on the
APPROVED event as `price_near_expiry`; it never warns or blocks. A line partly
from a fresh batch is judged as usual. Which batches a line takes is in
`BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`, "The firm's batch rules".

## A typed discount above the approver's limit waits for somebody allowed more

BACKLOG 64 row 3 (`app/sales_order/services/discount_limit.py`). Only a
discount somebody **typed** is judged -- a line whose source is `percent` or
`amount`, plus a typed bill discount's share -- because a price list, a
promotion and a standing rate are arrangements the firm already made. It is
judged per line at approval against the **approver's** limit: the largest
among their roles with a row in `role_discount_limits`; nobody is limited
until a row exists, and a platform administrator never is. Above it the
document stays a draft and the refusal names the percentage it needs. A bill
line records `discount_source`, `inherited` when it took its order's, so an
order's discount is judged once; a counter bill reads the source from the
order it raised for itself.

**A price typed below the customer's is judged with the discount** (D-PRC-2,
2026-10-06). With a 5% limit a typed 50% was refused and the same goods at a
typed 42.00 against 84.00, discount nothing, were approved, delivered and
billed below cost: only the discount boxes were read. The limit is judged on
the **whole reduction** from the price the customer would otherwise pay to
what the line charges -- the cut in the price and the typed discounts
together, as a share of the line at the customer's price, so 80.00 against
84.00 with a typed 3% is 7.62% and not two figures each under five. "The
customer's price" is what the ranking in *The price a line starts at* gives
that customer for the product, quantity and date before anything is typed
(`DiscountLimitService.customer_prices`, through `UnitPriceResolver`), so a
customer's own cheaper list or level is their price and not the seller's
doing, and a price typed at or above it is not a discount. An arrangement's
discount on the line (price list, promotion, standing rate) is still not
counted. Above the limit the refusal names both prices: "Line 1 is priced at
42.00 where the customer's price is 84.00: 50.00% off in all, above your
limit of 5.00%. It needs approval by someone allowed at least 50.00%." --
with ", with a typed discount besides" after the price where there is one --
and whoever is allowed more approves it, the APPROVED event keeping
`typed_price` and `customer_price` beside the percentages. A discount alone
is refused in the words it always was.

It is judged where the discount limit already was: the approval of a sales
order, and of a bill. A counter bill is judged against the ranking, like the
order it raised; a bill of documents against **the price its order line
agreed**, so a price cut typed on the note or on the bill is caught where it
is billed. A quotation is not judged, as before. One thing it does not do: a
product with no selling price has no customer's price to cut. The price floor
is unchanged and separate: it asks whether the net is below cost or the
minimum, whoever approves.

**A line sold by the box is judged as a box** (D-PRC-24, 2026-10-06). A line
in another unit than its stock was left out of the price comparison, because
the ranking's price carries no unit: 2 BOX of 12 at a typed 600.00 a box,
where a piece is 100.00, was approved by a sales manager limited to 5%,
delivered and billed 1,416.00. The customer's price for the line's unit is
the ranking's price per stock unit times **the line's own conversion factor**
-- the one its stock moves at -- so the box is 1,200.00, 600.00 is 50% off,
and it is refused in the usual words: "Line 1 is priced at 600.00 where the
customer's price is 1200.00: 50.00% off in all, above your limit of 5.00%. It
needs approval by someone allowed at least 50.00%." A counter bill by the box
is judged the same way through the order it raises. The same change judges a
line that carries **free goods**: it was left out too, because the test for
"another unit" was the stock quantity differing from the quantity charged.
One case is still judged on its typed discount alone: a bill of a note typed
in a different unit from the note line it bills (`conversion_factor` other
than 1 on the bill line).

**A delivery note is judged for what it types** (D-PRC-23, 2026-10-06). The
third thing it did not do: a discount typed on a note reached the bill as
`inherited` and was judged nowhere, so a sales manager limited to 5% typed 30%
on the note -- on the line as a rate or an amount, or on the whole note --
dispatched it, billed it and approved the bill alone. A note line that is
**cheaper than the order line it continues** is the typing person's doing
(`note_reduction` in `app/sales_order/services/discount_limit.py`): a line discount larger than the
order line's share for the quantity shipped, a share of a discount on the
whole note larger than the order's, each counted in whole as on an order, or a
price below the order's, cut against the order's price. It is judged by the
same judge at the **note's approval**, against the approver's limit, and the
refusal is the order's sentence naming the note: "Line 1 of delivery note
DN-2026-2027-000004 carries a discount of 30.00%, above your limit of 5.00%.
It needs approval by someone allowed at least 30.00%." (for a price, "Line 1
of delivery note … is priced at 50.00 where the customer's price is 100.00:
…"). The note stays a draft until somebody allowed more approves it. A note
that types nothing, types what its order already gave, a smaller discount or a
higher price has no such line and is never refused for what its order agreed.

The note's APPROVED event records that the reduction was judged
(`typed_reduction_judged`, beside `discount_approval` where the approver has
a limit), and **a bill treats as inherited only what the order agreed, or
what a note so recorded holds**. A reduction on a note with no record -- one
approved before this rule, or the hidden note a bill raises for itself -- is
judged at the bill's approval as though typed there, so it cannot arrive
unjudged; a note that was judged hands the bill its own price as the agreed
one. The same change stopped a bill judging an order **a person raised** a
second time: with the delivery-note stage off, a bill that only ships an order
read that order's typed discount as its own, and a clerk limited to 5% could
not bill the 30% the head had approved. Only an order the bill raised for
itself is the bill's to answer for.

**The customer's price level and segment are price decisions** (same PR). A
sales manager's edit could put a customer on a cheaper price level, or into a
segment carrying a discount or a level, and then sell at that price inside
the limit. `price_level_id`, and `customer_group_id` where the segment moved
into or out of carries a discount or a price level, need
`CUSTOMER_MANAGE_SETTINGS` on create, edit and both imports, as the standing
discount does (`_assert_may_change_price_terms`, `_assert_may_set_price_terms`
in `app/customers/services/customer_service.py`); resending the stored value
is not a change. A segment that carries neither stays a classification anyone
who edits customers may set -- a salesman adding a shop says what kind of
shop it is.

## A rate typed with GST in it is stored before tax

BACKLOG 64 row 4 (`app/tax/services/inclusive_rate.py`). A counter
bill whose **Rate includes GST** is on (`sales_invoices.rate_includes_tax`,
defaulting from `sales_workflow_settings.rate_includes_tax`) reads each rate
typed on a bare line as the shelf price. Before the order behind the bill is
raised, the rate is divided by the tax the buyer is **billed** -- the
components `TaxRuleService.simulate` adds to the line, so not one already
`included_in_price` and nothing under reverse charge -- for the same buyer,
branch, ship-to, product and date the line is then taxed at. A value-slabbed
rule is asked at the gross value and again at the taxable value; a different
second answer is taken, once. `unit_price` keeps the pre-tax rate, so every
posting, return, GSTR-1/3B and e-invoice reads it as before, and
`entered_rate` keeps the figure typed for the print and the editor. A typed
discount **amount** is gross like the rate and becomes whatever the line's own
gross leaves above the derived taxable value; a percentage applies unchanged.

Only a rate typed on the bill: a line continuing an order or a note keeps the
price it inherited, and a line that types no rate takes the product's price,
which is before tax. The bill discount and freight stay before tax. The
taxable value is kept at the documents' four decimals rather than rounded to
the paisa first, because rounding it first leaves taxable + tax a paisa off the
typed total about one time in seven (100 incl. 18% is 84.75 + 15.26 = 100.01,
against 84.7458 + 15.2542); a residual left by the tax engine's own rounding on
a large quantity is the round-off's, never an adjusted tax.

The **sales order** and the **quotation** carry the same switch
(`sales_orders.rate_includes_tax`, `sales_quotations.rate_includes_tax`;
`lines_before_tax` in the same module, migration `20261002_0207`). Every line
of those documents is typed, so every line with a rate is read back, and its
line keeps `entered_rate` and `entered_discount_amount` -- the discount amount
as typed -- so an editor shows the figures typed and sends them back that way
on an edit, which reads them again. **Absent on a new order or quotation is
off**, unlike the bill: a converted quotation, the order a counter bill raises
and an import all hand over rates already before tax, and a firm default read
on the server would read them a second time. The editors default the switch
from the firm's setting and always send it. A quotation typed at shelf prices
converts into an order typed at them, read back to pre-tax at the order's own
date, so the customer is billed the price quoted; the quotation print shows
both rates. A bill continuing an order inherits the pre-tax price, as before.

## The price a line starts at (SEL-9, 2026-10-03)

The discount ranking above decides what comes off; this decides what it comes
off. A line with no typed price starts at, most specific first: a fixed `rate`
on a price list that applies to the customer (same scope, date and quantity
break as the list's discount), then the customer's price level (its own, else
its group's), then the product's `selling_price` --
`resolve_unit_price` in `app/core/utils/pricing.py`, applied by
`UnitPriceResolver`. A typed price, zero included, beats all three. Levels are
prices, not rates, so a price revision does not move them; a list's discount
still comes off its fixed rate. Sales orders and quotations fill a blank price
on the server, before the GST-inclusive conversion, which converts only typed
prices (level and list prices are pre-tax). Downstream documents inherit the
price of the line they continue, as before.

**The batch's trade rate (PG-14, 2026-10-05).** Where the line leaves from a
known batch -- `pinned_batch_id` on a sales order line, or a counter bill line
whose `batches` all name one batch (handed to the order it raises as
`price_batches`) -- and the firm's profile has `BATCH_PTR_PTS`, the batch's
rate for the customer's `trade_class` joins the ranking: `batch_trade_rate`
gives PTR to a RETAILER and PTS to a STOCKIST, nothing to OTHER or an unclassed
customer, nothing where the batch has no rate for the class. The full order is
**typed > price list > batch PTR/PTS > price level > product price**. The list
outranks the batch because it is a price agreed with this customer; the batch
outranks the level because it is the same kind of tier rate made specific to
the goods actually leaving. `LinePrice.source` says `BATCH_PTR` or `BATCH_PTS`;
sales lines store no price source, so it is not recorded on the line. A
missing rate falls through unchanged.

**Every price in the ranking is per stock unit, and a line in another unit is
given that price converted** (D-PRC-25, 2026-10-06). The product's selling
price, a level's rate, a list's fixed rate and a batch's PTR or PTS are all
kept in the unit the stock is, as the cost and the minimum price are. The fill
handed them to the line as they stood: 2 BOX of a product at 100.00 a piece,
12 to a box, with no price typed, was charged 100.00 a box -- 236.00 with tax
for 24 pieces. A blank price is now filled through
`UnitPriceResolver.price_in_unit`: the ranking is asked at the **stock
quantity** the line stands for (so a list's quantity break counts pieces,
for its fixed rate and, since 2026-10-06, for its discount too -- *A price
list holds a ladder* above), and one line unit is worth that price times the
stock units it holds -- the
factor of the rule `convert_quantity` uses for the line on the document's
date, from the line's unit to the product's stock unit. The box is 1,200.00
and the line 2,400.00 before tax. It is one function for the sales order and
the quotation; a delivery note and a bill inherit the price of the line they
continue, and a counter bill is priced by the order it raises, so all five
agree. **A price somebody typed is the price of the unit on the line** and is
never converted. No price list or level names a selling unit of its own, so
there is no per-box price to prefer; a firm that sells a box for less than
twelve pieces types the price, or gives the discount. A unit no rule converts
to the stock unit is refused by name (below), on a quotation too: a box cannot
be priced without knowing what it holds.

**The buying side had the same hole and has the same answer.** A blank price
on a purchase order line takes, last in its ranking, a dated revision or the
product's `purchase_price`, both per stock unit, and took them unconverted for
a line bought by the box. They, and a supplier price list's fixed rate, are
now multiplied by the factor the line's quantity is converted at
(`UomService.unit_factor`); 2 BOX at 60.00 a piece is 720.00 a box. A rate
contract is per its own unit and the supplier's catalogue price per purchase
unit, so neither is converted. **The factor is the one the quantity converts
at, whichever way the line names its units** (2026-10-06): a purchase line
converted only when it named *both* its units, so a line naming BOX alone, or
relying on the product's buying unit, was counted and priced at a factor of 1.
`PurchaseService._line_units` now gives the price fill and the quantity the
same two units -- the unit the line names, else the product's buying unit,
and the product's stock unit -- so all three shapes are 720.00 a box and 24
pieces. A bill of products typed with no order is priced the same way through
the order it raises. `docs/UOM_FRAMEWORK.md` has the rule, and what the goods
receipt did to the cost of every line bought by the box.

## What the pricing check of 2026-10-06 tightened (D-PRC-10 to D-PRC-16)

Seven small things, each found by driving the routes rather than by reading
them. None changes what a document is charged.

**A free-goods offer is costed in units, not in money** (D-PRC-10). Goods
given free are charged nothing, so they take nothing off the bill and a
claim's `benefit_amount` is 0 for them by design -- adding their worth in
would break the equality between a claim and the discount on its document,
which is what the money budget counts. The figure is
`promotion_redemptions.free_quantity`, and all three reports carry it:
performance, the claims register, and the coupon report (which did not).
Both ranked reports sort by money and then by units, so a free-goods
campaign no longer sits level with one nobody claimed. **No worth is stored
for free goods on a claim**, so none is shown: best-offer mode values them at
the line's rate only to choose between offers, and a claim to the principal
values them at cost, in `app/principal_claims`. A report that wants rupees
has to say which of the two it means.

**The offer list is searched by code as well as by name** (D-PRC-11). Two
offers both named "Welcome" are told apart by `WELCOME-NOV` and
`WELCOME-DEC`, and the code is what the claims register prints.

**A refusal names what clashed, and is asked before the write** (D-PRC-12).
Four requests were answered only "The request conflicts with existing data.
Please retry." because the database was the first thing to object:

| Request | Now |
| --- | --- |
| A price list row naming a product that is not the firm's | 422 "Row 2: the product was not found in this firm." |
| A price list naming a customer, territory or supplier that is not the firm's | 422 "The customer this price list names was not found in this firm." |
| Two rows for one product at one quantity | 422 "Row 2: DET already has a rate from a quantity of 10 on row 1. A product takes one rate at each quantity." |
| An edit sent to an offer revision already replaced | 409 "This is revision 1 of offer BULK5, and revision 2 has replaced it. Open the current revision and edit that one." |

The first two matter beyond the wording: in a store two firms share, the
foreign key is satisfied by the other firm's row, so the list was **accepted**
and named a customer its own firm cannot see. On an edit a party is checked
only where it is changing, so a list naming a customer retired since can
still be saved around it; the rows are checked whenever they are sent. Rows
are counted from one, as the screen lists them.

**A price level takes `If-Match` and publishes its version** (D-PRC-13).
`PUT` and `DELETE /api/v1/price-levels/{id}` refuse a stale version with the
standard 409, and `POST` and `PUT` answer with an `ETag`. There is no
`GET /{id}` for a level; the `version` on each row of the list is what a
client sends back.

**Every product, customer and salesman billed has a row in the discount
report** (D-PRC-14). `discount-by-customer`, `-by-salesman` and `-by-product`
under `/api/v1/sales-invoices/reports/` left out anything given no discount at all, so gross by product (4,941.33) fell short
of gross by customer and by salesman (5,141.33) by one product sold at full
price. A row with a discount of 0.00 is a row; the three now add up to the
same gross and the same discount.

**A price revision starts today or later, keeps the MRP above the price, and
the product says what it sells at today** (D-PRC-15).

- A revision dated before the firm's own day (`firm_today`) is refused, typed
  or from a file: "New rates start today (06-10-2026) or later, not from
  03-10-2026. A price dated back would change today's price without saying
  so; date it today instead." It used to be taken in silence, and once the
  revision ahead of it was deleted it priced a quotation at 70.00 against a
  product reading 84.00. Tally and Marg both date a price change today or
  ahead. A row of an import file is refused the same way, by row.
- "MRP must be greater than or equal to selling price." -- the product
  form's own words -- when one revision names both. Naming one of them is
  judged against the other as it will stand on the revision's date (an
  earlier revision's, else the product's own): "... From 01-12-2026 DET would
  sell at 120 against an MRP of 115."
- `ProductResponse` carries `selling_price_in_force`,
  `purchase_price_in_force` and `mrp_in_force` beside the card prices: the
  latest revision dated today or earlier that names the price, else the card
  price. One read for a page (`prices_in_force_today` in
  `app/products/services/price_revisions.py`). The purchase one is hidden
  with the cost.

**A coupon reads as its offer does** (D-PRC-16). `status` on a coupon is
derived on every read (`shown_status` in
`app/promotions/services/coupon_crud.py`) and stored nowhere: a code switched
off reads as it was set, and a code left ACTIVE reads as the **live revision
of its offer** does -- the newest revision of the `version_group_id` not
retired, never the row the code was minted against, which reads INACTIVE the
moment anybody edits the offer. `own_status` is what the code itself is set
to and is what an editor sends back; `offer_status` is the offer's. The
coupon report follows the same rule. Switching the offer back on brings its
codes back with it, because nothing was written.

`tests/unit/test_promotions.py`, `tests/unit/test_price_lists.py`,
`tests/unit/test_price_levels.py`, `tests/unit/test_price_revisions.py` and
`tests/unit/test_discount_and_collections.py` hold the guards.

## Buy X get Y at a discount, and combo prices (SEL-2, SEL-3, 2026-10-03)

Both are line discounts, so tax stays per line and the best-offer valuation
reads them like any other. `BUY_X_GET_Y_DISCOUNT` takes the percent off the
"get" units of every complete group of buy + get units on each matched line,
at what each unit has left after earlier offers. `COMBO_PRICE` counts complete
sets of its products across the document's lines and spreads the saving --
one set's worth less its price, times the sets -- over the lines the sets used
by value (`apportion`). Neither saves anything on a partial group or set.

## Purchase prices from the supplier's terms (BUY-3, 2026-10-03)

A supplier's price list (`price_lists.vendor_id`) and standing discount
(`vendors.standing_discount_percent`) do on a purchase order line what a
customer's do on a sale: a blank price takes the list's fixed rate at the
line's quantity, else the product's `purchase_price`; a blank discount takes
the list's rate, else the standing discount, through `resolve_line_discount`.
`SupplierPriceResolver` reads only supplier lists; `PriceListResolver` reads
only lists that name no supplier.

The supplier's catalogue (BUY-4, `supplier_products`) sits between the two
price sources: a blank price takes the list's fixed rate, else the catalogue
row in force on the order's date, else the product's purchase price. A blank
supplier code takes the catalogue's.

## A rate contract outranks the supplier's price list (PG-9, 2026-10-05)

The whole supplier-side order for a purchase order line's price is now
`resolve_supplier_unit_price` in `app/core/utils/pricing.py`, most specific
first:

1. a typed price -- zero included;
2. a **rate contract** with the supplier, `ACTIVE` and valid on the order's
   date, naming the product in the line's unit (`app/rate_contracts`);
3. the supplier's price list's fixed rate at the line's quantity (BUY-3);
4. the supplier's catalogue price in force (BUY-4);
5. a dated price revision (MST-2), else the product's `purchase_price`.

Where the contract priced the line, a blank discount takes the contract's
discount percent -- zero included -- in the price list's place in
`resolve_line_discount`; the supplier's standing discount stays below it.

The order line records where its price came from in `rate_source`
(`RATE_CONTRACT`, `PRICE_LIST`, `CATALOGUE`, `PRICE_REVISION`, `PRODUCT` or
`TYPED`) and the contract line in `rate_contract_line_id`. **A typed price
equal to the one the ranking gives is the ranking's price echoed back**, not
an override: the desktop re-sends the price it was shown on every save, and
treating that as typed would take every edited order off its contract. A
different typed price is `TYPED` and draws nothing.

A contract's rate is per its own unit, so a line in another unit is not priced
from it -- which is also why a drawn quantity never needs converting. Two
active contracts covering one supplier and product on overlapping dates are
refused at activation, under a lock on the supplier's contracts; the lookup
still orders on `valid_from`, `contract_number` and `line_number`, none of
them nullable, so a row is never picked by NULL ordering.

## A supplier's free scheme fills the line by itself (PG-11, 2026-10-05)

A scheme is set once in `supplier_schemes` (`app/supplier_schemes`,
`/api/v1/supplier-schemes`, `SUPPLIER_SCHEME_VIEW` / `SUPPLIER_SCHEME_MANAGE`):
buy `buy_quantity` of a product, get `free_quantity` free -- of the same
product, or of `free_product_id` -- from one supplier, or from every supplier
when `vendor_id` is null, between `valid_from` and `valid_to` (open-ended when
null) while `is_active`. A supplier's own scheme beats an all-suppliers one,
ranked explicitly rather than by NULL sort. Two active schemes for the same
supplier (or both for every supplier) and product whose dates overlap are
refused, under a lock on the product. There are no versions: an order line
keeps the scheme's id and its label as it read then
(`purchase_order_lines.scheme_id`, `scheme_name`).

The free quantity is `resolve_supplier_free_goods` in
`app/core/utils/pricing.py`: `floor(ordered / buy) * free`, in the line's own
unit. **`None` and `0` are different answers here too** --
`PurchaseLineWrite.free_quantity` is `Decimal | None` with no zero default:
blank takes the scheme, an explicit `0` refuses it, any other typed figure
stands. A typed figure equal to the scheme's is the scheme echoed back and
keeps `scheme_id`, as a rate contract's price does.

A scheme giving **another product** fills nothing on the line that earns it.
`POST /api/v1/purchases/preview` returns `scheme_suggestions` -- per
earning line, the free product, the quantity, and the line already carrying
it if there is one -- and the client adds the line (ordered 0, free n,
`scheme_id`) when the buyer accepts. Saving takes the lines as sent and never
invents one; a line naming a scheme that does not give its product is
refused.

A free-only line (paid 0, free n) is worth nothing and taxed nothing; the
receipt keeps it (D-BUY-33) and inherits the scheme's label, and the bill
raised from the receipt carries it at zero. Such a line is judged received on
its free goods: it used to read `ORDERED` for ever, so an order carrying one
was never `is_complete` (86 #27).
