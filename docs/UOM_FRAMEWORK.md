# UOM & Packaging Framework

How one product is bought in boxes, stocked in strips and sold in strips —
without any of those units being hardcoded.

Verified against the running backend and the seeded firms on 2026-08-12.
Counts and conversions below were read from `/api/v1/uom-framework`, not
remembered — including the worked example, which is live output.

## The idea

The unit you **buy** in is rarely the unit you **keep stock** in, and neither is
always the unit you **sell** in. The module exists to hold those three answers
per product and to convert between them at the moment a document line is
written.

```
uoms                    the catalogue: PIECE, BOX, KG, LITRE …  (36 seeded)
uom_groups              units that may convert; one is flagged is_base
  └ uom_group_units
packaging_types         box / carton / pallet tokens

uom_conversion_rules    from → to × factor, versioned and effective-dated
products.*_uom_id       per product: stock / purchase / sales / receipt / dispatch unit
product_packaging_levels the physical hierarchy, each level with its own barcode
unit_sets               a named template for a product's units ("Strip, box of 10")
  └ unit_set_goods_types  which goods types a set suits; orders the picker only
```

A `Uom` carries a `dimension` (`COUNT`, `WEIGHT`, `VOLUME`, `LENGTH`) and
`is_decimal_allowed` — which is why 1.5 KG is fine and 1.5 BOX is not. In the
seeded catalogue `BOX`, `BOTTLE`, `CASE` and `CRATE` are whole-number units
while `CAPSULE` and `BUNDLE` allow decimals.

**Enforced since D-CFG-11 (2026-09-19); before that it was only recorded.**
`assert_quantity_fits_unit` (`app/uom/services/uom_service.py`) refuses a
fractional quantity, by name, when the unit it was entered in -- or the
product's stock unit, for a line with none -- has `is_decimal_allowed` off, or
the product has `allow_decimal` off. It runs on every document line where the
quantity is written (quotation, purchase order, goods receipt, purchase
invoice and return, sales order, delivery note, sales invoice and return) and
on every stock movement that brings a quantity in, through
`InventoryService._resolve_base_quantity`; releasing a reservation is exempt,
because it only gives back what was held. A product's `allow_fraction` is
**not** read: it is false on every product, so
enforcing it would refuse every 2.5 KG a firm records today, and nothing says
how it differs from `allow_decimal`. Driven on `fx_t0919duz7_r`: 1.5 PACK was
ordered, received and stocked before the fix.

**`uoms` is not firm-owned** — the table has no `firm_id` and one row serves
every firm sharing a store. That has a consequence for custom fields: the
uniqueness rule on `uom_attribute_values` is *(firm, unit, attribute)*, not
*(unit, attribute)*, because keying on the unit alone would let whichever firm
saved first claim the attribute and lock every other firm in that store out of
setting it. Reads must pass `firm_id` to `AttributeService` for the same reason.

**So the shared catalogue is the platform's to write (D-CFG-9, 2026-09-19).**
Units, groups and packaging types carry no firm, and their
writes needed only `UOM_MANAGE` / `PACKAGING_MANAGE`, which every firm
administrator holds: in `firm_shared` TESTSH1's administrator created, renamed
and deleted a unit TESTSH2 was offered, with no audit row. Creating, changing
and deleting them now takes the platform designation, as the geography
masters do (`tests/unit/test_platform_only_routes.py` pins the routes). A
unit's `PUT` is the exception, because the calling firm's own custom-field
values on it are the firm's: it still takes `UOM_MANAGE`, and refuses a body
that changes any of the unit's own columns to anybody without the designation.
The desktop offers the catalogue's Add, Edit and Delete to a platform
administrator only.

What *is* a firm's -- a product's packaging levels and its conversion rules --
must name that firm's own product. Both took the product unchecked, so a level
carrying a barcode was hung on another firm's product (201) and the first
firm's barcode lookup answered with that product's code and name; both now
answer "Product not found.", and the lookup ignores any level already written
on another firm's product.

## One product, several units

**A product's units are columns on `products`.** Seven unit slots, plus
`allow_fraction` / `allow_decimal` and the physical dimensions — written by the
product form and read by every transactional module when it builds a line.

There used to be a second home for exactly those fourteen columns,
`product_uom_configs`, with its own `GET`/`PUT
/uom-framework/products/{id}/config`. Nothing ever wrote it, nothing outside
`app/uom` read it, and it held zero rows in every store — but `_assert_uom_unused`
checked *it* before soft-deleting a unit, so the guard passed however many
products used the unit. Deleting STRIP left every medicine pointing at a unit
the catalogue no longer offered. The table was dropped in `20260812_0068` and
the guard now reads `products`.

The seven slots:

| Slot | Meaning | Medicine example |
| --- | --- | --- |
| `base_uom_id` | the unit everything reduces to | STRIP |
| `inventory_uom_id` | what stock is counted in | STRIP |
| `purchase_uom_id` | how you order from a supplier | BOX |
| `sales_uom_id` | how you sell | STRIP |
| `minimum_sales_uom_id` | the smallest sellable unit | STRIP |
| `default_receiving_uom_id` | what arrives on a GRN | BOX |
| `default_dispatch_uom_id` | what leaves on a delivery note | STRIP |

### Who applies them, and who does not

The slots are **defaults for a line, not rules the services enforce**, and the
two sides of a document do not agree on how much of a default they take:

| Module | Line unit comes from |
| --- | --- |
| `purchase` | `line.purchase_uom_id` **or** `product.purchase_uom_id`; its **stock** unit is the product's (below) |
| `goods_receipt` | the order line's unit, always; another unit on the receipt line is refused |
| `purchase_invoice`, `purchase_return` | the line's unit against the *source line's* unit, stored in the source line's |
| `sales_order` | `line.sales_uom_id` only — no fallback to the product; its **stock** unit is the product's (below) |
| `sales_invoice` | the invoice line's unit against the *source line's* unit, stored in the source line's |

**A quotation or order line that names no unit is in the product's selling
unit** (D-PRC-53, 2026-10-15), as a purchase line naming none is in its
buying unit. `in_selling_units` (`app/uom/services/uom_service.py`) names
`sales_uom_id` on such a line before anything prices it, where the product's
`sales_uom_id` is not its stock unit; the line then converts as any line in
another unit does. A line naming either unit is left as sent, so a client
that means pieces names them. A saved line sent again for the same product
keeps the unit it was saved in, and a quotation line saved in no unit is
ordered in the stock unit, so nothing saved before the rule is re-read. A
counter bill follows through the order it raises. The screens' Unit column
already showed the selling unit (D-UI-98).

**A sales order line that names a selling unit converts to the product's
stock unit, whatever stock unit it was sent** (D-PRC-26, 2026-10-06). The
order converted only when the line carried *both* units, while the
reservation asks the product (`base_uom_id`, else `inventory_uom_id`): a line
naming BOX and no `inventory_uom_id` read a quantity of 2 at a factor of 1,
`base_quantity` 2, while 24 pieces were reserved and left the shelf, and the
price floor judged 600.00 a box as the price of one unit. `stock_unit_of`
(`app/uom/services/uom_service.py`) is that one answer -- the product's base
unit, else its inventory unit, else the unit the line named for a product
that carries neither -- and `SalesOrderService` stores it on the line with the
factor, the rule's version and the base quantity `convert_quantity` gives, so
the reservation, the delivery note (which inherits the order line's units),
the price floor and every report read the same 24. A pair no rule converts is
refused where the line is written, by name: "SKU-001: no active conversion
rule converts CARTON to PIECE. Add one under Units -> Conversion Rules, or
enter the quantity in PIECE." -- never counted at a factor of 1. A product
with **no** stock unit at all has nothing to convert to: its line stays at a
factor of 1, and stock moves the quantity as typed, as before. A counter bill
is covered through the order it raises. **A price follows the same factor**: a
blank price on a line in another unit is the stock-unit price times it
(D-PRC-25, `PRICING_AND_PROMOTIONS.md`). An order line stored before this
keeps the figures it was stored with until it is saved again.

**The buying side is the same rule, and its cost follows the quantity**
(2026-10-06, the buying twin of D-PRC-26). A purchase order line stored the
product's units whatever it was sent, but converted only when it was sent
*both*: 2 BOX naming the box alone -- or naming nothing, for a product whose
buying unit is BOX -- read a factor of 1 and a base quantity of 2 beside units
that said 24 pieces. `buying_units_of` (`app/uom/services/uom_service.py`) is
the one answer for the order and the goods receipt: the unit the line names,
else the product's `purchase_uom_id`, converts to `stock_unit_of` the product
whatever stock unit the line carries; a line with no buying unit at all is in
the stock unit and converts nothing. A buying unit no rule converts is refused
in the same words, where the order is saved -- including a product's *default*
buying unit, which used to be saved at a factor of 1 and refused only at the
receipt.

The larger half was the **cost**, and it did not depend on how the line named
its units. A goods receipt handed the stock ledger what one *received* unit
cost -- a box -- as the cost of one *stock* unit, so 2 BOX at 720.00 put 24
pieces on the shelf at 720.00 each: 17,280.00 of inventory and of goods
received not invoiced for goods bought for 1,440.00, a moving average twelve
times too high for every later sale's cost of goods sold, and the bill then
cleared the accrual by crediting the missing 15,840.00 to purchase price
variance. `InventoryService.record_goods_receipt` now takes
``entered_unit_cost`` -- the cost of one unit *of the line* -- and divides it
by the factor the quantity moved at, so the movement is worth exactly what the
line is: 24 pieces at 60.00. **Stock received before this is not restated**:
its movements, the moving average built on them and the journals stand as
posted, and a firm that bought by the box needs its valuation corrected by a
stock revaluation, not by re-saving documents.

Three more things follow the same unit. **A receipt line is counted in its
order line's unit**: what the order is owed, what a line may still take in,
what is left to bill and what may go back are read off the two quantities side
by side, so a receipt line naming another unit is refused -- "Line 1 is
received in BOX where PO-2026-2027-000004 orders it in PIECE. Receive it in
the order's unit." (2 BOX against 24 PIECE ordered used to put 24 on the
shelf, leave the order 2 of 24 received and cost two pieces' price.) **A bill
or return line typed in another unit is stored in its source line's unit**,
converted by `UomService.continued_quantity`: the rule for the pair where there
is one, else through the product's stock unit, so 24 PIECE bill a receipt of
2 BOX, and 25 are more than came in, with only the box-to-piece rule a firm
actually writes. **A return's stock leaves in the unit its quantity is stored
in**, the source line's: it left in whatever unit the request sent, so a
return of 1 naming no unit took one piece off the shelf for 1 BOX, and 12
PIECE typed against a box line -- stored as 1 -- took one piece too. A return
line saved before this with no unit is answered from its source line when it
is completed. (A return typed in another unit leaves as typed; see "Pieces
that are not whole boxes" below.) `tests/unit/test_purchase_lines_in_another_unit.py` is the
guard; a debit note carries no unit and moves no stock, so it has nothing to
convert.

**A line that continues another line is stored in that line's unit --
quantity and price both** (2026-10-06). This is the shape of a sales bill, a
supplier's bill and a purchase return: `current_invoice_quantity` (or
`current_return_quantity`) and `unit_price` are in the unit of the source
line (`order_uom_id` on a sales bill, `purchase_uom_id` on the buying
documents), and `invoice_uom_id` / `return_uom_id` with `conversion_factor`
only record how the line was typed. So the quantity cap, the discount limit
and everything downstream read one unit. Two things did not follow it. The
conversion needed a rule from the typed unit to the source unit, which is the
direction nobody writes; `continued_quantity` goes through the stock unit. And
a typed price was multiplied by the *converted* quantity as it stood;
`ContinuedQuantity.price_per_source_unit` restates it, because a price
somebody types is the price of the unit they typed. `conversion_factor` on
these lines is typed unit to source unit -- **not** a factor into stock, which
is the source line's own. A sales return is the fourth such line.

### Pieces that are not whole boxes (D-PRC-37, D-PRC-38, 2026-10-06)

**0.5833 of a box is not seven pieces.** The quantity column holds four
places, so 7 PIECE of a box of 12 was stored only as 0.5833 BOX, and every
figure worked from that was a little wrong: a sales bill of 7 PIECE of a note
at 1,200.00 a box was 699.96 where seven pieces are 700.00 (with the other 17
the bills came to 2,831.95 against the note's 2,832.00); a supplier's bill of
17 PIECE was 1,020.024, and one of 7 PIECE at a typed 60.00 was stored at
720.0411 a box and cleared 419.98 of the receipt's accrual, with 0.02 booked
to purchase price variance; and a purchase return of 7 PIECE was saved,
approved, and then refused at completion -- "BOX is counted in whole numbers,
so 0.5833 BOX cannot be entered" -- and stayed APPROVED for ever.

**The storage decision.** The row keeps **both**: the quantity in the source
line's unit, as before, and beside it **`entered_quantity`**, what was typed,
in the line's own `invoice_uom_id` / `return_uom_id` (migration
`20261006_0343`, on `sales_invoice_lines`, `purchase_invoice_lines`,
`purchase_return_lines` and `sales_return_lines`; null on a line typed in its
source line's own unit, and on every line written before it). Storing only
the typed unit and quantity was the other choice and was not taken: about 160
places in some thirty files read `current_invoice_quantity` or
`current_return_quantity` as a count in the source line's unit -- every cap,
every "already billed", the lifecycle sums, commission, the offers' and the
principal's claims -- and each would have had to learn to convert. They are
unchanged, and read what they read before. What changed is what is **worked
from the typed figure**:

- **Money.** The line is worth what was typed
  (`ContinuedQuantity.worth`): seven pieces at the price typed for a piece,
  or, with none typed, seven twelfths of the source line's price for a box
  taken *before* rounding -- 700.00, never 0.5833 of it. `gross_amount` is
  that figure, and the tax is worked on it, not on quantity times price.
- **The price.** `unit_price` stays the price of one source unit and is
  exact: 60.00 a piece is 720.0000 a box (it was restated from the rounded
  quantity as 720.0411), so a bill at the receipt's own price is at the
  receipt's own price for the price-variance report too.
- **`conversion_factor`** is kept at the ten places its column has
  (0.0833333333), where it was rounded to four. `exact_quantity(quantity,
  entered_quantity, conversion_factor)` in `app/uom/services/uom_service.py`
  gives any reader that values a line per source unit the unrounded figure;
  the share of a receipt's accrual a bill clears (`_replay_accrual`) and the
  MRP ceiling on a bill use it. **No purchase price variance arises from a
  conversion.**
- **The stock.** A purchase return and a sales return typed in another unit
  move what was typed, in the unit it was typed in: 7 PIECE, so seven pieces.
- **The parts add up.** Each part rounded on its own, 5 + 5 + 14 PIECE of two
  boxes are 0.4167 + 0.4167 + 1.1667 = 2.0001 BOX, and the third was refused
  as more than was shipped. The part that takes all that is left (to within
  rounding: half a typed unit, and never more than 0.0005) is stored as
  exactly what is left (`ContinuedQuantity.taking`). And where it bills at
  the source line's own price, as every part before it did, it is worth what
  they left of the line to the paisa (`_completing_worth`): a box at 1,000.00
  billed 4 + 4 + 4 pieces is 333.33 + 333.33 + **333.34**.

**The whole-number rule of a unit is asked of what a person typed, never of a
converted figure**, and it is asked where the line is saved. 7 PIECE against a
box line is seven of a unit that takes whole numbers or fractions as PIECE
does; 0.5 BOX typed as a box is refused at save, on a bill and on a return
alike: "BOX is counted in whole numbers, so 0.5 BOX cannot be entered." Two
converted figures used to be put to the rule:

- the 0.5833 BOX a return of pieces was stored as, at completion -- gone, since
  the return moves what was typed;
- **one batch's share of a line split across batches.** A box of twelve drawn
  ten from one batch and two from the next was passed to the stock ledger as
  0.8333 and 0.1667 of a box, so approving an order by the box for a
  batch-tracked product whose batches did not hold whole boxes was refused,
  "BOX is counted in whole numbers, so 0.8333 BOX cannot be entered"; and
  where the unit allows fractions the shares were converted *back* -- 0.1667
  of twelve is 2.0004 pieces -- so the hold and the stock drifted from the
  allocation. The reservation, its release and the dispatch now take
  `share_of_line` for a split: the rule is the line's to pass, and what moves
  is the allocation itself.

**A fraction is judged on what leaves the shelf.** A unit that takes no
fraction refuses 5.5 of itself, but a line that charges 5.5 and gives 0.5
free moves six whole pieces, and that is what the rule is about: a customer
taking half of "buy 10 get 1" is charged for five and a half and given a
half. The sales order, the delivery note and the sales invoice all judge
charged plus free together. The invoice judged the charged quantity alone
until 2026-10-12, so a note that had dispatched the six could not be billed
(D-SELL-91). A bill line typed in another unit than the one it bills is
judged on what was typed.

**What is not typed in pieces.** A goods receipt line and a delivery note
line are counted in their order line's unit and one naming another is refused
where it is saved, as above; loose pieces of an order by the box are received
or delivered on an order line in pieces. A return line that sends back **free
goods beside charged ones** in another unit than its source line is counted
and moved in the source line's unit, so its quantity must be one that unit
can hold, and it is refused at save if not -- never at completion.

**A sales return against a bill reads the bill's line in the note's unit.** A
bill line is counted in the unit of the line it bills whatever unit it was
typed in, and the return read `invoice_uom_id` as that unit: 7 PIECE off a
bill typed 24 PIECE of 2 BOX was refused as more than the "2" dispatched. The
return also needed a piece-to-box rule, which nobody writes, and passed its
stock in the typed unit beside a quantity in the source's.
`tests/unit/test_lines_in_another_unit.py` and
`tests/unit/test_purchase_lines_in_another_unit.py` drive all of it.

### What a document states: quantity, unit and rate that belong together (D-PRC-40, 2026-10-06)

A bill typed 24 PIECE of a note of 2 BOX printed **"2 | PIECE | 1,200.00"** on
the tax invoice -- the stored quantity and price, which are the note line's,
beside the unit the bill was typed in: two pieces for 1,200.00 each. And a
box line billed in its own unit names no `invoice_uom_id`, so its tax invoice
printed **no unit at all** while its order and its challan printed BOX.

`stated_line` in `app/uom/services/uom_service.py` gives the three figures as
one answer:

- a line that **kept what was typed** (`entered_quantity`) is stated as
  typed: 24 PIECE at 100.00, 7 PIECE at 100.00 -- the rate being the stored
  price of a source unit times the line's factor;
- any other line is stated **in the unit its quantity is in**, the source
  line's: 2 BOX at 1,200.00. That includes a line typed in another unit
  before lines kept what was typed -- the typed figure cannot be recovered
  from four places, and 2 BOX is true of it.

| Document | Quantity | Unit printed | Rate |
| --- | --- | --- | --- |
| Tax invoice, thermal bill (`stated_invoice_lines`) | as typed, else `current_invoice_quantity` | the typed unit, else the unit of the note or order line billed, read off that line; then `order_uom_id`; then the product's stock unit | of that unit |
| Credit note of a sales return | as typed, else `current_return_quantity` | `return_uom_id` as typed, else `sales_uom_id` (the source line's) | of that unit |
| Quotation, order confirmation, delivery challan | the line's own | `sales_uom_id`, else the line's `inventory_uom_id` | the line's own |
| Purchase order | the line's own | `purchase_uom_id` | the line's own |
| Financial credit and debit notes | the line's own | none: the line carries no unit | taxable over quantity |

There is no printed purchase return and no printed proforma of its own.

**The e-invoice and GSTR-1 say what the bill says.** The e-invoice payload
sends no `Unit` (the portal's UQC codes are not this system's unit codes, and
nothing maps them). Both report a **quantity**, and both report the one the
bill states -- `Qty` 24 and `UnitPrice` 100.000 for the bill above, and 24 in
the HSN summary -- where they reported the stored 2 (at 1,200.00). For a box
line billed by the box both report 2. The e-invoice reads
`stated_invoice_lines`, the function the print reads, so the paper and the
portal cannot state a line differently.

**So does the credit note of a sales return (D-PRC-50, 2026-10-06).** 7 PIECE
back off a bill typed 24 PIECE left the HSN row reading 23.4167, and went to
the portal as `Qty` 0.5833 at `UnitPrice` 1200.069, beside a printed credit
note that said 7 at 100.00. The return's e-invoice (`_read_return` in
`app/einvoice/services/note_registration.py`) and GSTR-1's credits
(`_returns_as_credits`) now read `stated_line`, as the print does: 7 at
100.000, and 17 left on the row.

**The HSN summary is one row per code, unit and rate (D-PRC-50).** It was
keyed on the code and the rate, so 24 PIECE, 2 BOX and 7 PIECE of one code
read 33 -- of nothing. `_fold_hsn` now keys on the unit the line states as
well, which is Table 12's own shape (HSN, UQC, rate) and the shape the
purchase HSN summary already had; splitting was chosen over converting every
line to the stock unit because that would state a quantity no document
states. Each row of GSTR-1's `hsn` and of
`/sales-invoices/reports/hsn-summary` carries `unit`: this firm's unit code,
**not** a portal UQC. The unit is the printed bill's (`_stated_units`, the
same order of answers as `stated_invoice_lines`); a financial credit or debit
note, which carries none, reads the invoice line it names. **A return line
is netted in the unit of the bill line it credits (D-CMP-26, 2026-10-14):**
it stated its own, so 1 BOX back off a bill typed 24 PIECE left 24 PIECE and
a row of -1 BOX; it is now converted by the product's rule in force on the
return's date, read backwards where the firm wrote it only the other way
(`_units_in`), and the row reads 12 PIECE. Where no rule joins the two units
the line keeps its own unit and its own row. The values and the tax are the same rupees whichever row they
sit on, so no other table of GSTR-1 or GSTR-3B moves. Two things follow that
are true rather than tidy: a box sent back off a bill typed in pieces takes
1 off a BOX row and the value with it, which can leave that row negative
beside a PIECE row that is whole; and a product whose bills name both units
has two rows to add by hand until a UQC mapping converts them.

**The purchase HSN summary had the same mistake the other way round**
(`gst_purchase_register.py`): it was already keyed on the code and the
bill's typed unit, and counted the stored quantity beside it -- 7 PIECE of a
box receipt read "0.5833 PIECE". It counts `entered_quantity` where the bill
or the return kept one.

### Either unit field of a sales bill line names the unit (D-PRC-44, 2026-10-06)

A sales bill line can name a unit in two fields: `invoice_uom_id`, the unit it
is billed in, and `order_uom_id`, the unit of the line it bills. Only the
first was read. A counter bill line naming `order_uom_id` BOX and nothing else
was sold as pieces -- 2 at 100.00, 236.00 with tax, two pieces off the shelf
-- and came back with no unit: the unit asked for was dropped without a word.

**A line that names a unit by either field means that unit**, resolved once
in `app/sales_invoice/services/line_units.py`, and a pair that cannot both be
true is refused rather than one of the two being ignored:

- **A line typed straight onto a bill** has no line behind it, so the two
  fields say the same thing: the unit is whichever is named, and it goes to
  the order the bill raises as its `sales_uom_id`, where `stock_unit_of`
  converts it like any order line by the box. Two different units are
  refused: "Line 1 names two units: BOX as the unit it is ordered in and
  PIECE as the unit it is billed in. A line typed straight onto a bill is
  sold in one unit; name that unit once."
- **A line billing a note or an order**: `invoice_uom_id` is the unit typed;
  `order_uom_id` beside it must then be true of the line billed, or it is
  refused -- "Line 1 says the line it bills is in PIECE, and
  DN-2026-2027-000001 line 1 is in BOX. Leave the ordered unit off, or send
  BOX; the unit the line is billed in is the other field." Named alone,
  `order_uom_id` is the unit the line is in and is converted like any typed
  unit: 24 naming PIECE that way bill a note of 2 BOX, where they were read
  as 24 boxes and refused as more than was shipped.

The row stores what is true of it whatever the request sent: `order_uom_id`
is the unit its quantity is in (the line billed), and `invoice_uom_id` the
unit it was typed in. A unit typed against a line that names none is
converted into the product's stock unit, never taken as the same thing.

## Unit sets (backlog 89, step 3 -- built 2026-10-08, not yet tested by hand)

A product's units were up to seven slots typed one by one, plus a conversion
rule that, when forgotten, was found only when a document line was refused. A
**unit set** is a named template -- *Strip, box of 10* -- that fills them in
one choice on a **new** product.

| Table | Holds |
| --- | --- |
| `unit_sets` | The name, the seven unit slots as the product names them, `allow_decimal`, `conversion_factor` (one purchase unit is this many stock units; null where nothing converts) and `is_active`. A row without `firm_id` is the shared catalogue; a row with one is that firm's own |
| `unit_set_goods_types` | One row per set and goods type, unique on the pair. Replaced by delete and insert, never soft-deleted |
| `products.unit_set_id` | The set a product's units were copied from. Reference only: nothing reads the set again |

**The rules.**

- **A set is copied, never linked.** `UnitSetService.starting_units` hands
  `ProductService.stage_product` the units and the factor; the units are
  written onto the product and the factor becomes the product's **own**
  conversion rule (purchase unit to stock unit, `product_id` set) through
  `UomService.stage_conversion_rule`, in the product's transaction. Editing or
  deleting a set afterwards changes no product: document lines go on reading
  the product's own columns and its own rule, with no extra join.
- **What the caller names is the caller's.** A unit slot, `allow_decimal` or
  `unit_conversion_factor` named in the create body wins over the set's, blank
  included; one left out takes the set's. The desktop form sends every unit
  after showing the set's, so the form decides; an import or API client naming
  only `unit_set_id` gets the set as it stands. A slot the set leaves empty
  fills nothing.
- **The factor.** Named, it must sit between a purchase unit and a different
  stock unit (inventory unit, else base unit) or the save is refused; named
  `null` it means no rule. A set's factor is dropped quietly when the units as
  saved no longer need one. A factor typed with **no** set chosen makes the
  product's own rule all the same. The rule holds from 2000-01-01, so an
  opening bill dated before the product was typed in still converts.
- **The goods type only orders the picker.** The product form offers the sets
  tied to the product's goods type and the sets tied to none; *Show all unit
  sets* reaches the rest. Nothing is refused on save for a set of another
  type. The goods type itself carries no units and no default set.
- **Nothing is pre-filled silently.** With no set chosen the units are typed
  by hand, as before.
- **Shared and own.** The shared sets are read-only to a firm; its
  administrator adds, changes and removes the firm's own (`UOM_MANAGE`). A
  firm's name may not repeat a shared one. `ProductUpdate` accepts neither
  `unit_set_id` nor `unit_conversion_factor`: after creation the units are
  the product's own and are changed as a product's units always were.
- **Every write is audited:** `unit_set.created`, `unit_set.updated`,
  `unit_set.goods_types_changed`, `unit_set.deleted`, and
  `uom.conversion.created` for the product's rule.

**Routes.** `GET|POST /api/v1/uom-framework/unit-sets` and `PUT|DELETE
/api/v1/uom-framework/unit-sets/{unit_set_id}` (`UOM_VIEW` to read). The
product form does not call them: the sets arrive as `unit_sets` in `GET
/api/v1/products/metadata`, the call it already makes, and the form makes one
call fewer than before because it no longer asks for the profile's units.
Screen: **Unit Sets**, where Industry Templates used to be.

**The shared catalogue** (`backend/app/uom/unit_set_seed.py`, written into
existing stores by `20261008_0351`):

| Unit set | Stock | Purchase | Factor | Listed under |
| --- | --- | --- | --- | --- |
| Strip, box of 10 | STRIP | BOX | 10 | Medicine |
| Strip, box of 15 | STRIP | BOX | 15 | Medicine |
| Bottle, carton of 24 | BOTTLE | CARTON | 24 | Medicine, Food, Cosmetics |
| Tube, box of 20 | TUBE | BOX | 20 | Medicine, Cosmetics |
| Pack, carton of 12 | PACK | CARTON | 12 | Food |
| Litre, loose | L | L | none | Paint |
| Piece, loose | PIECE | PIECE | none | every product |
| Unit, box of 10 | UNIT | BOX | 10 | every product |

**What a profile gives a new firm.** No rows of its own: the profile's
starting goods types (`docs/GOODS_TYPES.md`) decide which shared sets the
firm's products are offered first, and there is no per-firm "in use" table for
unit sets. The firm adds its own from there.

**What this replaced, removed on 2026-10-08.** The per-profile default units
(a table, three routes, the *Default units* dialog and the product form's
silent pre-fill): `20261008_0351` turned each firm's own row into that firm's
unit set *Firm default units*, tied to no goods type, and dropped the table.
And the industry templates, a JSON catalogue with a screen and four routes
that nothing ever applied: dropped with no successor.

## Conversion happens on the line, only when the units differ

**Eight** document modules convert this way, counted on 2026-10-06 with
`grep -rlE "convert_quantity|continued_quantity" backend/app --include=*.py`
rather than remembered (this line said seven long after `sales_return` made
it eight; the command also lists `uom` itself and two files that only mention
the name, `inventory` and `pricing`): purchase, goods receipt, purchase invoice, purchase return, sales
order, delivery note, sales invoice, sales return. Each holds a `UomService`.
Four call `convert_quantity` per line; the sales invoice, the purchase
invoice, the purchase return and the sales return, whose line continues
another document's line, call `continued_quantity`, which resolves the same
rule with a second route through the stock unit and keeps the typed figure. `inventory` resolves the rule itself for a movement that
carries no line factor, and `pricing` reads only the factor (`unit_factor`).
The shape, on a line that converts into stock:

```python
if purchase_uom_id is None or inventory_uom_id is None or purchase_uom_id == inventory_uom_id:
    return {"factor": Decimal("1"), "converted": quantity, "version": None}
response = self._uom.convert_quantity(...)
```

Ordering 10 BOX of a product stocked in STRIP, with a rule `BOX → STRIP × 10`,
records **10 BOX on the document and 100 STRIP into stock**, and stores the
factor and the rule's `version_number` on the line.

That version stamp is why `ConversionRule` deliberately names its counter
`version_number`. `version` belongs to `BaseEntity` as the mapper's
optimistic-concurrency column; declaring the business version under that name
made SQLAlchemy increment the rule's published version on every edit, while
documents were recording that number to identify the factor they converted
with. `tax` names the same concept `version_number` for the same reason
(renamed in `20260809_0055`).

**The API said `version` for it until 2026-08-22**, which is why this module
had no `If-Match` at all: the one name the concurrency counter has to have was
taken by the rule's published revision. `ConversionRuleResponse` and the write
schemas now spell the revision `version_number`, the way the column and `tax`
always did, and `version` is the counter -- published in the body and as an
`ETag` on every uom and tax record a screen edits.

That rename surfaced a second copy of the resolver. `InventoryService` matched
a line's stored revision against `ConversionRule.version` -- the counter -- so
the two agreed only until somebody edited a rule, after which the movement was
refused for a rule that plainly exists. It ordered by `product_id DESC` too,
the NULL-ordering defect fixed here in `20260809_0055` and left standing in the
copy. Both corrected 2026-08-22.

## Which rule wins

`_resolve_conversion_rule` takes the active rules for the firm and unit pair
whose effective window contains the **document's** date, then orders them:

```python
case((ConversionRule.product_id.is_(None), 1), else_=0).asc(),  # the product's own rule first
ConversionRule.version_number.desc()                             # newest version
```

So specificity is **this product's rule → the firm-wide rule for the pair →
error**. There is no implicit arithmetic: an unconfigured pair raises *"No
active conversion rule is configured for this UOM pair"* rather than guessing a
factor.

That `case` is load-bearing. It used to be `ORDER BY product_id DESC`, which
depends on where the backend sorts NULLs — PostgreSQL puts them **first**, so
the firm-wide fallback outranked the product's own rule and every quantity for
that product converted with the wrong factor. SQLite sorts them last, so the
unit suite saw the right answer and the defect only existed in production.
`tests/integration/test_uom_conversion_resolution.py` exists solely to hold that
line down, and it must stay in the integration suite: SQLite cannot express the
bug.

**One live rule per version, and firm-wide is its own key.** The version is
what a document line records, so two live rules sharing one would let either
factor move the stock. `UQ_uom_conversion_rules_unique_version` includes the
nullable `product_id`, and PostgreSQL treats two NULLs as distinct, so it never
held a firm-wide rule: BOX -> PIECE was published at 10 and again at 12, both
firm-wide version 1, on 2026-09-19 (D-CFG-10). The partial index
`UQ_uom_conversion_rules_firmwide_version_active` (`20260919_0143`, which
renumbered any live duplicates it found: the earliest keeps its number and each
later one moves to the next free number, noted in its `reason`) holds the firm-wide case, and `create_conversion_rule` refuses a taken
version by name, saying which number is free. A retired rule holds no number.

Rounding is per rule — `rounding_mode` (`HALF_UP`, `HALF_DOWN`, `HALF_EVEN`,
`UP`, `DOWN`, `CEILING`, `FLOOR`; default `HALF_UP`) and `precision_scale`
(default 4). **The line and the stock round the same way**, through
`round_by_rule`: stock used to multiply by the factor and never round, so a
PACK -> KG rule of 0.3333333333 at two places left an order line of 0.33 KG
and a shelf of 0.3333 KG (D-CFG-11).

Both halves, run against the seeded WHOLE01 firm on 2026-08-12:

```
POST /uom-framework/convert   3 BOTTLE of SHAMP180 → ML
  → 540.0000   factor 180, rule version 1

POST /uom-framework/convert   3 CARTON of SHAMP180 → ML   (no rule)
  → 422 "No active conversion rule is configured for this UOM pair."
```

The second is the point. A factor of 1 would have booked 3 ML where 3 cartons
left the shelf, and nothing would have reported it.

The date defaults to `utc_now().date()`, never `date.today()`: the server's
local date can already be tomorrow, which selects a rule that is not yet
effective. That shipped once here already.

## Packaging levels

`ProductPackagingLevel` is a self-referencing tree (`parent_level_id`) with a
`conversion_to_base_factor` and its own `barcode` / `gtin` / `ean` / `upc` per
level:

```
PIECE  ×1
  └ BOX     ×10        barcode 8901234567890
      └ CARTON ×120    barcode 8901234567906
          └ PALLET ×5760
```

This is what lets a scanner read a carton label and know it holds 120 pieces --
through `GET /api/v1/uom-framework/barcode-lookup?code=...`, which resolves a
code across every level's `barcode`, `gtin`, `ean` and `upc` and then the
product's own barcode, and answers with the product and how many **base units**
one scan represents. A product's own barcode is one base unit; there is no
packaging around a piece to multiply by.

Two refusals matter more than the happy path. A code **nothing carries** is a
404 naming the code, because the next thing anybody does is re-scan. A code
**two things carry** is a 409 saying how many -- a scanner that silently picked
one of them would put the wrong stock on a document and nothing downstream
would question it.

Levels are per firm per product and are unique on `(firm, product, level_name)`.

### Where a pack's code is read (backlog 89, market gap 3; built 2026-10-08)

Until 2026-10-08 only the Packaging Levels screen asked the lookup. The counter
bill matched a scan against each product's own barcode in the list it had
read, every document line's product box filtered on the product's name, code
and own barcode, and the product list search looked at `products.barcode` -- so
a carton label found nothing anywhere a document is written. Three things read
a pack's code now, and they are the whole list:

| Where | What it does with a pack's code |
| --- | --- |
| **The counter bill's scan field** (`_scanned` in `desktop/lib/ui/sales/sales_invoice_editor_dialog.dart`) | A product's own barcode, then its code, is answered from the list already read, with no call. Anything else is asked of `GET /barcode-lookup`, and one scan of a pack adds `base_quantity` to the product's line -- a carton of 24 adds 24, a second scan 24 more -- with a note beside the field (*Carton (CTN) of P-1: 24 PCS added.*). A 404 reads *No product has the barcode*, a 409 is shown in the server's words, and a pack of a product the bill's list does not hold is named and not added. |
| **A document line's product box** in the five phase 2 editors -- sales invoice, sales order, quotation, purchase order, supplier bill (`productEntriesMatching` and `productEntryToHighlight` in `desktop/lib/ui/workspace/product_box_search.dart`) | Each product row carries `pack_codes`, every barcode, GTIN, EAN and UPC of its packs, read once for the page (`ProductService.pack_codes_for_many`). The box keeps its match on the label and adds those codes, and puts the highlight on the product a pack's code leaves, so the Enter a scanner sends picks it. **It finds the product; it does not set the quantity** -- the line is the person's to fill, and the unit they are typing in is theirs to say. |
| **Every search fed by the product list** -- `GET /api/v1/products?search=`, so the Products screen and the seven screens using `ProductSearchBox` (batches, bill of entry, principal claims, requisitions, rate contracts, RFQs, supplier schemes) | The search matches a pack's four code columns as well as the product's own (`PACK_CODE_COLUMNS` in `app/uom/models/uom.py`, the one list the lookup also reads). |

**The quantity a scan adds is in the product's stock unit, and that is exact.**
A level's factor counts in the product's base unit; `stock_unit_of` makes the
base unit the unit stock is kept in; and a document line that names no unit is
a line in that unit. So the counter bill adds `base_quantity` to a line as it
stands and never names the pack's unit on it -- the level's factor and the
conversion rules are different tables that do not read each other, and a line
in CARTON would be converted by the rule, not by the label that was scanned.
The lookup answers `uom_code` (the pack's unit) and `stock_uom_code` (the
product's) so the screen can say what it added without another call.

**Not read from a pack:** global search (Ctrl+K) still matches the product's
own barcode only; the opening-stock import matches a file's barcode column
against the product's own; the old (phase 1) editors were left alone. A pack
holds one barcode, one GTIN, one EAN and one UPC -- a second supplier's label
on the same box goes in whichever of the four is free, and a fifth has
nowhere to go until a firm needs it. A code two things carry is still saved
without complaint and refused only when scanned (409); the product search
lists both, which is how somebody finds the second one.

`tests/unit/test_uom_packaging_framework.py` holds the server's half (the two
unit codes, the search, the row's `pack_codes`, and that every role able to
write a counter bill holds `UOM_VIEW`, which the lookup needs);
`desktop/test/counter_billing_test.dart` the scan field;
`desktop/test/product_box_pack_codes_test.dart` the product box, and it fails
when a sixth editor with a *Product (code, name or barcode)* column leaves
the two callbacks out. TC-MAST-032 is the case and
`docs/qa/checks/goods_types/tc_mast_032.py` drives it.

**Until 2026-08-23 none of this was reachable and none of it was read.** The
four CRUD endpoints had existed since the module was written with nothing in
the desktop calling them, so no firm could record a level; and no code path
anywhere read the four code columns, so the sentence above was a claim with no
implementation behind it. Global search matches `products.barcode` and has
never looked at a packaging level.

Note the division of labour: packaging levels describe the **physical**
hierarchy and carry the barcodes; `uom_conversion_rules` are what documents
actually convert with. They are not the same table and do not read each other.

## An item's pack, for boxes and pieces on one line (L5 step 2, 2026-10-15)

A line typed as boxes and pieces is a line in the stock unit
(`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.1); the pack it adds up with is
read here, in `backend/app/uom/services/packs.py`, and nowhere else.

- **`pack_unit_of(product, side)`** is the pack's unit: buying reads the
  purchase unit where it is not the stock unit, else the sales unit; selling
  the other way about.
- **`pack_of(session, product, side=, on_date=)`** is its size: the factor of
  the rule from that unit to the stock unit in force on the date, resolved as
  every line resolves it (the item's own rule before the firm-wide one, then
  the latest version). A factor that is not a whole number above one, or no
  rule, is no pack: the item's lines show pieces only.
  **`packs_of_many`** answers a page in one read of the rules and one of the
  unit codes; `pack_of` is it for one item.
- **`BoxesAndPieces`** splits a total into full packs and loose (41 of 12 is
  3 + 5; 53.5 kg of a 25 kg bag is 2 + 3.5) and adds two typed cells up into
  full packs again (2 + 17 is 3 + 5), refusing a part box or a negative cell.
- **Item rows** (`ProductResponse`) carry `pack_size` and `pack_unit_code` for
  the selling side and `buying_pack_size` and `buying_pack_unit_code` for the
  buying side, on the firm's own today, read once per page
  (`ProductService.packs_for_many`). Null where the item has no pack. Two
  pairs, not one, because an item can be bought by the case and sold by the
  box, and the row does not know which editor reads it.

`tests/unit/test_item_packs.py` is the guard.

### The pack on a quotation and a sales order line (L5 step 3)

`line_packs(session, lines, side=, on_date=, kept=)` in the same file is the
pack each line is **written at**, and both documents store it on the line
(`pack_uom_id`, `pack_size`) for every line of an item that has a pack,
however the line was typed -- a line in BOX included:

- a saved draft line sent again for the same product keeps its own pack, so
  a draft saved at 12 to a box still reads 12 after the item moved to 10
  (design 3.3); `held_packs(rows)` reads the saved lines for it;
- an order raised from a quotation is handed each quoted line's pack
  (`stage_order(..., inherited_packs=)`), so it is ordered at the quoted
  size, not today's;
- any other line takes the item's selling pack on the document's date.

A line typed as boxes and pieces sends `quantity` in pieces and `pack_size`,
the size the screen added the cells up at. The server never stores the figure
sent: it **refuses the line where it differs** from the pack the line is
written at ("Line 1: a box of this item holds 12, not 10. Open the line
again."), where the item has no pack, and where the line names a unit other
than the stock unit. A line sending `pack_size` and no unit is named the
stock unit before it is priced, so D-PRC-53 does not read it in boxes. The
rate is per piece and nothing about tax, offers or reservation changes.

Each header carries `box_and_piece_entry`, the layout it was saved in: off
when absent on create, kept when absent on update, and handed from a quotation
to the order it becomes. `tests/unit/test_box_and_piece_sales.py` is the
guard, with the worked example sold to the paisa (410.00 + 49.20).

### The pack on a delivery note and a sales bill line (L5 step 4)

A line continuing another is **written at its source line's pack**, not
today's (design 3.3 and 3.6): a delivery note line at its order line's, a
bill line at its note line's. 3 boxes + 5 ordered at 12 to a box are shipped
and billed at 12 after the item moved to 10. A source line written before L5
holds none, and the line takes the item's pack on its own document's date (a
saved draft note line keeps what it took). Both lines store and answer
`pack_uom_id` and `pack_size`; nothing about boxes is stored beyond that, and
every quantity on the line -- shipping now, left, billed -- is split by the
screen with the one pack size. The caps stay sums of pieces.

These lines name no product and the note line may name no unit, so the
caller hands `line_packs` a `PackedLine` (line number, the source's product,
the `pack_size` sent, the unit the line is counted in). A typed `pack_size`
is refused where it is not the source line's pack, or where the line is
counted in a unit other than the stock unit -- a line billing a note in BOX
is in boxes, not pieces.

A bill typed straight in (the counter bill) sends `pack_size` on its product
lines; the chain hands it, and the bill's `box_and_piece_entry`, to the order
it raises, where it is checked against the item's pack, and the note and the
bill then continue that order. A bill against an order with the note stage
off hands a line's typed `pack_size` on to the bill line that bills the note
raised for it. A draft counter bill whose edit raises its order and note
again hands the new order the pack each product's line was first written at
(`ensure_invoice_source(..., inherited_packs=)`), so its lines stay at 12.

Headers: a new note takes its order's `box_and_piece_entry` and a new bill
takes it where any note it bills has it; absent (or null) on an update keeps
the document's own. `POST /sales-invoices/preview` answers both, since it is
the save rolled back. `tests/unit/test_box_and_piece_note_and_bill.py` is the
guard.

### The pack on a sales return line (L5 step 5)

A return line comes back **at the pack of the note or bill line it returns**
(design 3.6): a box of 12 sold before the item moved to 10 is returned as a
box of 12, and a `pack_size` of 10 is refused. A source line written before
L5 holds none: a saved draft return line keeps what it took, else the item's
pack on the return's date. Return lines are stored numbered by position, and
that is the number `line_packs` is asked by. The line is counted in the unit
it names (`return_uom_id`), else its source line's, so a line typed as boxes
and pieces naming the box is refused. Every cap -- what was sent, what is
already back, the free goods -- stays a sum of pieces, as before.

Header: a new return takes `box_and_piece_entry` where any note or bill it
returns has it; absent (or null) on an update keeps its own. The worked
example's return -- 1 box + 1 piece off the bill -- is 13 pieces credited
130.00 + 15.60 GST. `tests/unit/test_box_and_piece_return.py` is the guard.

### The pack on a purchase order and a goods receipt line (L5 step 6)

An order line is written at the item's **buying** pack (`side="BUY"`: its
purchase unit, else its sales unit) on the order's date; a saved draft line
keeps its own. Lines are numbered by position. A line typed as boxes and
pieces is in the stock unit: one sending `pack_size` and naming no unit is
put there (`_pair_lines_in_pieces`), where it would otherwise be read in the
item's buying unit and 41 pieces taken for 41 boxes; one naming the box is
refused. A receipt line comes in **at its order line's pack**, so 10 boxes
ordered at 12 are received at 12 after the box moved to 10; an order line
from before L5 holds none, and the receipt takes the saved draft line's, else
the item's on the receipt date. A receipt line is counted in its order line's
unit, as it always was.

Two supplier terms read a pair line in boxes, since they count the buying
unit (design section 5):

- **Minimum and multiple** (`quantity_hints`, `pack_sizes=`): 41 pieces at
  12 to a box are 3.4167 boxes against a minimum of 5, and the quantity that
  would do is said in pieces, 60. The refusal and the preview's hint are the
  same sum.
- **A rate contract kept per box** prices a pair line at the box's rate over
  its pack size (96.00 a box is 8.00 a piece), and draws boxes: the drawn
  total and the over-draw warning count the line's pieces over its pack size
  (`in_contract_units`, and the `case` in `drawn_quantities`). A line in
  pieces that was not typed as a pair is not priced from a box contract, as
  before.

Headers: the order writes `box_and_piece_entry` (absent on create is off,
absent or null on an edit keeps); a new receipt takes its order's. The worked
example's purchase -- 10 boxes at 8.00 a piece, 1 box free -- is 960.00 and
132 pieces in at 7.27. `tests/unit/test_box_and_piece_purchase.py` is the
guard.

### The pack on a supplier's bill and a purchase return line (L5 step 7)

A bill line is billed **at its receipt line's pack**, so 10 boxes taken in at
12 are billed at 12 after the box moved to 10; a receipt line from before L5
holds none, and the item's buying pack on the bill's date is taken. Bill lines
are re-inserted on every save (they are terminal), so the pack is worked out
once all of them are written and set on each, and a line counted in another
unit than stock (`invoice_uom_id`, else its receipt line's) is refused for a
`pack_size`.

A **bill typed straight in** (purchase order and receipt stages off) hands its
`box_and_piece_entry` and each line's `pack_size` to the order and the receipt
`PurchaseChainService` raises behind it, so the three are written at one pack
and a stale pack is refused on the order, naming the line. A pair line naming
no unit is in pieces there too: its blank price is the product's price of a
piece, not of a box. A draft bill of products edited later raises its order
again dated today; each line keeps, per product, the pack it was first
written at (`stage_order(inherited_packs=)`). A bill naming an order for a
firm that types no receipts hands `pack_size` to the receipt it raises, which
checks it against the order line's pack.

A return line goes back **at the pack of the receipt or bill line it
returns**; a source from before L5 holds none, and a saved draft return line
keeps its own, else the item's buying pack on the return's date. Free goods
sent back on their own (0 bought, 12 free) are a line at its pack like any
other. Caps stay sums of pieces.

Headers: a new bill takes `box_and_piece_entry` where a receipt it bills has
it, a new return where a receipt or bill it returns has it; absent or null on
an edit keeps the document's own. `tests/unit/test_box_and_piece_supplier_bill.py`
is the guard.

### Boxes and pieces on the printed page (L5 step 8)

A line of a document **saved in the boxes and pieces layout** prints its
quantity as the customer's own bill does: full boxes before the slash, loose
pieces after it, and what a box holds in brackets. The worked example's 41
pieces of a box of 12 read **3/5 (x12)**, its 2 free **0/2**; 3 boxes and
none over read 3/0. One formatter, `in_packs` in
`backend/app/sales_invoice/services/invoice_pdf.py`, does it for every paper;
`InvoiceLineBlock` carries the line's `pack_size` and answers
`packed_quantity`, `packed_free` and `pack_label`, so the layouts do no
arithmetic.

| Paper | Qty | Free goods |
| --- | --- | --- |
| Full page | "3/5 (x12)" | "Free 0/2" under it |
| Half page and the trade layout | "3/5 (x12)" in Qty | "0/2" in Free |
| 80 mm roll | "3/5 (x12) Free 0/2 x 10.00" on the item's second row | |

Where the pair and its pack do not fit the Qty column, the pack takes a
second row in the cell (`packed_cell`) rather than printing over the next
column; no column is added or widened, so a short bill still fits half a page.
The total under the lines reads the same way: the boxes added up before the
slash, the loose pieces and the whole quantity of each line with no pack after
it (3/5 of soap and 4 torches total **3/9**).

Which lines print so is `printed_pack` in `backend/app/uom/services/packs.py`:
only on a document whose `box_and_piece_entry` is on, only a line holding a
pack, and only a line counted in the item's stock unit -- a line typed in BOX
keeps its pack too (decision 4) and prints its plain "2". The bill, the
order confirmation, the quotation, the challan, the purchase order and the
credit note all ask it. Any other line, and any document not in the layout,
prints as before. `tests/unit/test_box_and_piece_prints.py` is the guard.

### The two switches and the party's mark (L5 step 9)

`sales_workflow_settings.box_and_piece_entry` and
`purchase_workflow_settings.box_and_piece_entry` are the firm's switch for each
side: read and written on the settings routes, off for a firm with no row and
on a first write that does not name them, and an edit that does not name them
keeps them. A customer's `box_and_piece_entry` (*Bills in boxes and pieces*)
and a supplier's (*Buys in boxes and pieces*) are written on create (absent is
false) and on edit (absent keeps), on the import as the `BoxesAndPieces`
column (Yes or No, blank leaves it), recorded on the audit trail, and both lists
take `?box_and_piece_entry=true|false`. The server stores the mark whatever the
switch says; the screens read it only where the switch is on, to choose the
layout a new document opens in (design section 4). A saved document keeps its
own header flag.

On the screens the sum lives once, in `desktop/lib/ui/workspace/box_piece_cells.dart`: the order, quotation and sales bill editors draw Box, Pcs, Free box and Free pcs from it, send the total in pieces in `quantity` and `free_quantity` and the item row's `pack_size` beside it, and a blank free pair still means "take the offer".

### The continuing documents (L5 step 10)

The delivery note, sales return, bill of notes, purchase order, goods receipt,
supplier's bill and purchase return draw the same cells. A document raised
from another takes its pack from the line it continues -- the order line's on
a note or receipt, the note or receipt line's on a bill or return -- and the
billable-documents read (`BillableLine.pack_size`) carries it for a new bill
of notes. A new purchase order or bill of products follows the supplier's
mark; every continuing document opens in the layout of the one it continues,
as the server does when the flag is absent. What the line already holds
(Ordered, Delivered, Received, Due, Left to bill) reads "3 x 12 + 5" through
`boxesAndPieces`. A line counted in a unit other than the stock unit keeps
its box cells closed, and a purchase order line typed in boxes names no
buying unit, because the server puts a boxes line in the stock unit.

### Stock shown as boxes (L5 step 11)

Stock rows -- the stock list and ledger, the stock valuation and its lots, the
stock statement, the batch list, below reorder level and the count lines --
answer `pack_size` and `pack_unit_code`: the item's selling pack on the firm's
today, read once for the page by `display_packs` (`display_packs_by_code` for a
report that names its items by code) in `backend/app/uom/services/packs.py`.
Both are null unless either box-and-piece switch is on, which is how a screen
knows to offer *Show boxes* without a call of its own. The toggle is display
only: `stockInBoxes` in `box_piece_cells.dart` reads 89 pieces of a 12-pack as
"7 x 12 + 5 (89)", a sheet download writes boxes, pieces and total as three
number columns, and nothing stored changes. The choice is kept per user on the
machine. On the counter bill a scan of the line's own pack adds one to Box and
any other scan adds its pieces to Pcs.

## Effective dating

`uom_conversion_rules` are dated (`effective_from`, `effective_to`) and
versioned per `(firm, product, from_uom, to_uom)`. A supplier that changes its
box size creates a **new version** from that date rather than editing the
factor, so a goods receipt from last year still reconciles against the factor
that was in force when it was received — the same reasoning as effective-dated
tax profiles in `docs/TAX_FRAMEWORK.md`.

## Where the code is

| Concern | File |
| --- | --- |
| Tables | `backend/app/uom/models/uom.py`, `backend/app/uom/models/unit_set.py` |
| Conversion and configuration | `backend/app/uom/services/uom_service.py` |
| Endpoints (`/api/v1/uom-framework`) | `backend/app/uom/api/router.py` |
| Demo conversions | `backend/scripts/seed_multi_firm_demo.py` (`_seed_sales_conversion_rule`) |
| Unit sets | `backend/app/uom/services/unit_sets.py`, `backend/app/uom/repositories/unit_set_repository.py`, `backend/tests/unit/test_unit_sets.py`, `desktop/test/product_unit_set_form_test.dart`, `desktop/test/unit_sets_test.dart` |
| Unit tests | `backend/tests/unit/test_uom_packaging_framework.py` |
| NULL-ordering guard | `backend/tests/integration/test_uom_conversion_resolution.py` |
| Desktop UI | `desktop/lib/ui/uom/uom_management_page.dart` |
| Packaging levels and the scan lookup | `desktop/lib/ui/uom/packaging_levels_page.dart` |

## Traps

- **Never rank on a nullable column's sort order.** See the `case` above. Any
  "specific overrides general" query in this codebase must express specificity
  explicitly and be covered in `tests/integration/`.
- **`version_number`, never `version`.** `version` is `BaseEntity`'s
  concurrency counter; a business version declared under that name gets
  incremented by every ORM update.
- **The conversion date is the document's date**, resolved with `utc_now()`.
- **An unconfigured pair is an error, not a factor of 1.** The `factor = 1`
  short-circuit applies *only* when the two units are the same or one is unset
  -- and "unset" is no longer the caller's to choose: a sales order line that
  names a selling unit takes its stock unit from the product (D-PRC-26), and
  a purchase line takes both its buying unit and its stock unit from the
  product where it names neither.
- **A cost is per some unit, and the stock ledger's is the stock unit.** Hand
  it a document's cost per *line* unit and every piece is valued as a box.
  `record_goods_receipt(entered_unit_cost=...)` converts it with the quantity.
- **Seeding the catalogue is not seeding conversions.** 36 units shipped with
  zero rules, so the module was inert: every line took the `factor = 1`
  short-circuit and the first line raised in a different unit would have failed.
  `scripts/seed_multi_firm_demo.py` now creates one rule per demo product from
  the blueprint's `sales_uom_factor` — STRIP → TABLET ×10 for amoxicillin, ×15
  for paracetamol, BOTTLE → ML ×180 for shampoo. They are scoped to the
  **product**, not the firm, because a strip is ten tablets of one medicine and
  fifteen of another; that also exercises the specificity ordering above.
  ELEC01's products sell in the unit they stock in and correctly get no rule.
- **A product's units live on `products`, not in a config table.** The second
  home was dropped in `20260812_0068`; see above.

---

## Which modules convert, and which deliberately do not

*Moved out of `CLAUDE.md` on 2026-09-15 when that file passed the 150k-character limit.*

**UOM & packaging** (`app/uom`) — `docs/UOM_FRAMEWORK.md` is the reference: the seven unit slots a product carries, effective-dated conversion rules, and the resolution order (the product's own rule before the firm-wide one, ranked explicitly rather than by NULL sort). **Eight** document modules convert per line -- `purchase`, `goods_receipt`, `purchase_invoice`, `purchase_return`, `sales_order`, `delivery_note`, `sales_invoice`, `sales_return` (the sales invoice, the purchase invoice and the two returns through `continued_quantity`, which resolves the same rule; count with the `grep` above) -- plus `inventory`, taking a `factor = 1` short-circuit only when the units match. `quotation` deliberately does not: it moves no stock, and the conversion happens when it becomes an order, because `convert_quotation` builds that order through `SalesOrderService.create_order`.
