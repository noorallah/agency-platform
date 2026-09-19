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
on a purchase order is subtracted *after* tax, so it reduces no taxable value
and the counterparty pays tax on money they were never charged -- that shape
is deliberately not copied to sales. And the rounding residual goes to the
**largest** line so the shares sum exactly to the figure they split; a
document whose lines do not add up to its own total is one no reconciliation
can accept. A conversion carries the *deal* and re-splits it, because copying
each line's share agrees only while both documents hold the same lines; a
sales return **inherits** its share pro-rata from the line it credits, since
crediting the undiscounted figure hands back more than was charged. All four
sales services price every line before taxing any of them for this reason --
`sales_invoice` carries the intermediate state in `_PricedInvoiceLine`.

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
names the entry it takes, so it can be run twice. `expiry_months` NULL means points never
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
`header_discount_amount` does on a purchase order and is deliberately not
copied. `additional_charges` stays **outside** the tax and is left alone --
it is for additions that really are outside it, and re-taxing it would
change every document that carries one. A line discounted to nothing carries
no freight; freight and a bill discount both survive on the line rather than
netting; and both `app/gst_returns` and the e-invoice payload put it inside
the taxable value, since leaving it out declares less than the invoice
charged tax on.
