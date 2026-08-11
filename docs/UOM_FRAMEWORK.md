# UOM & Packaging Framework

How one product is bought in boxes, stocked in strips and sold in strips —
without any of those units being hardcoded.

Verified against the running backend and the seeded `WHOLE01` firm on
2026-08-11. Counts below were read from `/api/v1/uom-framework`, not remembered.

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
product_uom_configs     per product: stock / purchase / sales / receipt / dispatch unit
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

`ProductUomConfig` holds seven unit slots per product — this is the module's
whole point:

| Slot | Meaning | Medicine example |
| --- | --- | --- |
| `base_uom_id` | the unit everything reduces to | STRIP |
| `inventory_uom_id` | what stock is counted in | STRIP |
| `purchase_uom_id` | how you order from a supplier | BOX |
| `sales_uom_id` | how you sell | STRIP |
| `minimum_sales_uom_id` | the smallest sellable unit | STRIP |
| `default_receiving_uom_id` | what arrives on a GRN | BOX |
| `default_dispatch_uom_id` | what leaves on a delivery note | STRIP |

Plus `allow_fraction`, `allow_decimal` and physical `weight` / `volume` /
`length` / `width` / `height`.

`business_profile_uom_defaults` supplies the starting point for a firm's
industry (base, inventory, purchase and sales units, plus the two fraction
flags), with `firm_id` nullable so a platform default can be overridden per
firm.

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
- **The seeded firm has 36 units and zero conversion rules.** Same-unit lines
  take the short-circuit and work; the first line whose purchase unit differs
  from its inventory unit fails until a rule exists. Seeding the catalogue is
  not the same as seeding conversions.
