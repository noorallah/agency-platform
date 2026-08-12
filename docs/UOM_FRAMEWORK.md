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

**`uoms` is not firm-owned** — the table has no `firm_id` and one row serves
every firm sharing a store. That has a consequence for custom fields: the
uniqueness rule on `uom_attribute_values` is *(firm, unit, attribute)*, not
*(unit, attribute)*, because keying on the unit alone would let whichever firm
saved first claim the attribute and lock every other firm in that store out of
setting it. Reads must pass `firm_id` to `AttributeService` for the same reason.

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
| `purchase` | `line.purchase_uom_id` **or** `product.purchase_uom_id` |
| `sales_order` | `line.sales_uom_id` only — no fallback to the product |
| `sales_invoice` | the invoice line's unit against the *source line's* unit |

So a sales order raised without a unit on the line converts nothing, whatever
the product says. Worth knowing before assuming a product's `sales_uom_id`
governs what leaves the shelf.

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

All **seven** transactional modules convert this way — purchase, goods receipt,
delivery note, purchase invoice, purchase return, sales order, sales invoice.
Each holds a `UomService` and calls `convert_quantity` per line:

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

Rounding is per rule — `rounding_mode` (`HALF_UP`, `HALF_DOWN`, `HALF_EVEN`,
`UP`, `DOWN`, `CEILING`, `FLOOR`; default `HALF_UP`) and `precision_scale`
(default 4).

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

This is what lets a scanner read a carton label and know it holds 120 pieces.
Levels are per firm per product and are unique on `(firm, product, level_name)`.

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

## Traps

- **Never rank on a nullable column's sort order.** See the `case` above. Any
  "specific overrides general" query in this codebase must express specificity
  explicitly and be covered in `tests/integration/`.
- **`version_number`, never `version`.** `version` is `BaseEntity`'s
  concurrency counter; a business version declared under that name gets
  incremented by every ORM update.
- **The conversion date is the document's date**, resolved with `utc_now()`.
- **An unconfigured pair is an error, not a factor of 1.** The `factor = 1`
  short-circuit applies *only* when the two units are the same or one is unset.
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
