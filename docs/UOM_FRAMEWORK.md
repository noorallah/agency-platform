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
business_profile_uom_defaults   what an industry starts with
uom_industry_templates  reusable industry payloads
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
**not** read: it is false on every product and every profile default, so
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
Units, groups, packaging types and industry templates carry no firm, and their
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

So a sales order raised without a unit on the line converts nothing, whatever
the product says. Worth knowing before assuming a product's `sales_uom_id`
governs what leaves the shelf.

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

**The e-invoice and GSTR-1 say what the bill says.** Neither names a unit:
the e-invoice payload sends no `Unit` (the portal's UQC codes are not this
system's unit codes, and nothing maps them), and GSTR-1's HSN summary is
keyed on the code and the rate. Both report a **quantity**, and both now
report the one the bill states -- `Qty` 24 and `UnitPrice` 100.000 for the
bill above, and 24 in the HSN summary -- where they reported the stored 2
(at 1,200.00). For a box line billed by the box both report 2. The e-invoice
reads `stated_invoice_lines`, the function the print reads, so the paper and
the portal cannot state a line differently.

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

`business_profile_uom_defaults` supplies the starting point for a firm's
industry (base, inventory, purchase and sales units, plus the two fraction
flags), with `firm_id` nullable so a platform default can be overridden per
firm.

**Resolution is two-level, and only the second level used to exist.** NULL
`firm_id` is the profile-wide default every firm on that profile inherits; a
set `firm_id` is that firm's own override, and it wins. `get_profile_default`
filtered on the caller's firm alone until 2026-08-12, so it never matched the
seeded rows: `GET /api/v1/uom-framework/profiles/{id}/defaults` answered `null`
for a profile whose row was sitting in the same store, and all five industry
defaults shipped invisible. The rank is now explicit —
`case((firm_id.is_(None), 1), else_=0)` — rather than an `ORDER BY firm_id`,
because PostgreSQL sorts NULLs first in DESC and SQLite last, which is exactly
how a firm-wide conversion rule once outranked a product's own factor in
production while the unit suite saw the right answer.

### Writing either level

`PUT /profiles/{id}/defaults` takes `apply_to`:

| `apply_to` | Writes | Needs |
| --- | --- | --- |
| `FIRM` *(default)* | this firm's override | `CONVERSION_RULE_MANAGE` |
| `PROFILE` | the row every firm on the profile inherits | `PLATFORM_SETTINGS` |

`FIRM` is the default so a client that does not know about the distinction
cannot change another firm's units by accident. `PROFILE` needs platform
authority because it reaches every firm on the profile, not just the caller's —
that is a different decision from "what units does *my* firm trade in", and the
role that makes it is different too.

Until `apply_to` existed, only `seed_uom_reference_data` could write a
profile-wide row, so a profile created through the API could never carry
defaults for the firms put on it: each firm had to set its own copy. Only five
profiles are seeded with defaults (GENERIC, AGENCY, PHARMACY, FOOD, WHOLESALE);
the other seven start empty and are filled in this way.

Both levels are audited (`uom.profile_default.created` / `.updated`). A
profile-wide row has no owning firm, so the entry is written against the firm
whose store the change happened in — otherwise the trail would lose it.

**A `PROFILE` write reaches every store, not only the caller's** (D-CFG-21).
The row is reference data held per store, so it is written into each firm's
store in turn, matched to the profile there by code, since each store seeds
its own catalogue. A firm whose store cannot be reached, or has no such
profile, is named in the response's message rather than skipped silently. A
store that already holds the same units writes no audit row, which is what a
shared schema visited once per firm needs; both levels record the units
before and after (D-CFG-23).

**The unit catalogue's baseline is the same everywhere; what is added is
not.** The 19 units in `SEED_UOMS` are in every store and reseeded on every
reset. A unit an administrator adds lives in the store it was added in, like
any master, so two stores can legitimately hold different totals. Units,
groups and packaging types are keyed on their code among **live** rows
(`UQ_uoms_code_active` and its siblings, `20260924_0160`), so a deleted code
can be used again. A unit recorded on any document line or stock movement
cannot be deleted: every column ending in `uom_id` is asked, found from the
schema rather than listed.

`UQ_business_profile_uom_defaults_firm_profile` covers `(firm_id,
business_profile_id)` and PostgreSQL treats NULLs as distinct, so it constrains
overrides and not profile-wide rows. That did not matter while only the seed
could write one; `20260812_0066` adds the partial unique index now that the API
can, because two administrators saving at once would otherwise each insert one
and a firm would inherit whichever the query happened to return.

Edit both from **Administration → Business Profiles → Default units**
(`ui/uom/profile_uom_defaults_dialog.dart`). The dialog says which level it is
showing, and offers the profile-wide switch only to someone who holds
`PLATFORM_SETTINGS`; it defaults to off.

### How the defaults reach a product

**By pre-filling the create form, not by filling them in on the server.** A
unit the user can see and change before saving is one they can disagree with; a
unit applied silently is noticed only when a conversion comes out wrong three
documents later. So `ProductService` still stores exactly what it is sent, and
`products/product_management_page.dart` seeds a *new* product's base,
inventory, purchase and sales units — plus `allow_fraction` / `allow_decimal` —
from the firm's profile, saying so above the fields.

Two rules the widget tests pin:

- **Only a product being created.** Defaulting an edit would put the profile's
  units back on a product whose units someone had deliberately cleared.
- **A default naming a withdrawn unit is dropped.** A stored default can point
  at a deactivated unit, and a dropdown throws when its value is absent from
  its items.

A firm reads its own defaults from `GET /api/v1/uom-framework/profile-defaults`
— no profile id, because every route that reveals one is platform-admin only,
which is why a client previously had no way to reach the defaults meant for it.
The profile is resolved through `app.business.gating.resolve_profile_id`, so
the units a firm is offered come from the same assignment its feature gates
use.

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

**Until 2026-08-23 none of this was reachable and none of it was read.** The
four CRUD endpoints had existed since the module was written with nothing in
the desktop calling them, so no firm could record a level; and no code path
anywhere read the four code columns, so the sentence above was a claim with no
implementation behind it. Global search matches `products.barcode` and has
never looked at a packaging level.

Note the division of labour: packaging levels describe the **physical**
hierarchy and carry the barcodes; `uom_conversion_rules` are what documents
actually convert with. They are not the same table and do not read each other.

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
| Tables | `backend/app/uom/models/uom.py` |
| Conversion and configuration | `backend/app/uom/services/uom_service.py` |
| Endpoints (`/api/v1/uom-framework`) | `backend/app/uom/api/router.py` |
| Demo conversions | `backend/scripts/seed_multi_firm_demo.py` (`_seed_sales_conversion_rule`) |
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
