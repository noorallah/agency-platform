# Business Profile Framework

How one codebase serves a pharmacy, a food distributor and a restaurant kitchen
without a branch per industry.

Verified against the running database on 2026-08-09; row counts are from
`firm_shared`.

## The idea

A firm is assigned exactly one **business profile** — PHARMACY, FOOD,
RESTAURANT, WHOLESALE and so on. That profile answers four questions:

| Question | Answered by |
| --- | --- |
| What capabilities does this firm operate with? | **Features** |
| Which workspaces does it see and use? | **Modules** |
| What extra fields do its records carry? | **Attribute definitions** |
| What units does it buy and sell in? | **UOM defaults** |

Nothing about an industry is hardcoded into an entity. A pharmacy tracks batches
because its profile enables `BATCH_TRACKING`, not because `Product` has a
pharmacy branch in its code.

## The tables

```
                        platform schema
                        ┌──────────┐
                        │  firms   │
                        └────┬─────┘
                             │ (firm_id, no FK across schemas)
─────────────────────────────┼──────────────────────────────── firm_shared
                             │
                  ┌──────────▼─────────────┐
                  │ firm_business_profiles │   2 rows — one per assigned firm
                  └──────────┬─────────────┘
                             │
                  ┌──────────▼──────────┐
                  │  business_profiles  │   12 rows — the industries
                  └──────────┬──────────┘
                             │
     ┌───────────────┬───────┴────────┬──────────────────┐
     │               │                │                  │
┌────▼─────────┐ ┌───▼──────────┐ ┌───▼───────────────┐ ┌▼─────────────────────┐
│profile_      │ │profile_      │ │attribute_         │ │business_profile_     │
│features      │ │modules       │ │definitions        │ │uom_defaults          │
│75 rows       │ │130 rows      │ │13 rows            │ │5 rows                │
└────┬─────────┘ └───┬──────────┘ └───┬───────────────┘ └──────────────────────┘
     │               │                │
┌────▼─────────┐ ┌───▼──────────┐ ┌───▼───────────────────┐
│business_     │ │business_     │ │ per-module value      │
│features      │ │modules       │ │ tables, e.g.          │
│21 rows       │ │14 rows       │ │ product_attribute_    │
└──────────────┘ └──────────────┘ │ values                │
                                  └───────────────────────┘
                                              │
                                  ┌───────────▼───────────┐
                                  │category_attribute_    │
                                  │rules   7 rows         │
                                  └───────────────────────┘
```

Every one of these lives in the **firm-owned** schema (`firm_shared`, or a
dedicated firm schema/database). Only `firms` is a platform table, which is why
`firm_business_profiles.firm_id` carries no foreign key in firm schemas.

### Catalogue tables — what exists

| Table | Rows | Holds |
| --- | ---: | --- |
| `business_profiles` | 12 | The industries. `code`, `industry_type`, `is_default` (GENERIC is the default). |
| `business_features` | 21 | Capability switches: `BATCH_TRACKING`, `EXPIRY_TRACKING`, `DRUG_LICENSE`, `RECIPE_MANAGEMENT`, `IMEI`, `COMMISSION`… |
| `business_modules` | 14 | Workspaces: `DASHBOARD`, `MASTERS`, `PRODUCTS`, `PURCHASES`, `SALES`, `INVENTORY`, `ACCOUNTING`, `REPORTS`, `KITCHEN`, `RECIPES`, `PROJECTS`, `CONTRACTS`, `ADMINISTRATION`, `SETTINGS`. |
| `attribute_definitions` | 13 | Custom field definitions, targeted by `entity_type` and optionally scoped to one profile. |

### Mapping tables — what each profile enables

| Table | Rows | Meaning |
| --- | ---: | --- |
| `profile_features` | 75 | profile × feature, with `is_enabled`. |
| `profile_modules` | 130 | profile × module, with `is_enabled`, `is_visible`, `display_order`. |
| `business_profile_uom_defaults` | 5 | Default base/purchase/inventory/sales units per profile, optionally overridden per firm. |
| `category_attribute_rules` | 7 | Makes an attribute mandatory for a profile + product category. **Live**: read by `AttributeService.mandatory_ids` when saving, and by `GET /api/v1/products/metadata` to tell a client which fields to render. Seeded rules make `EXPIRY_DATE`, `MANUFACTURER` and `BATCH_NUMBER` mandatory for PHARMACY/MEDICINE, `EXPIRY_DATE` and `SHELF_LIFE_DAYS` for FOOD/FOOD, `IMEI` and `WARRANTY_MONTHS` for ELECTRONICS. |

### Assignment and values

| Table | Rows | Meaning |
| --- | ---: | --- |
| `firm_business_profiles` | 2 | Assigns one profile to one firm. Unique on `firm_id`. |
| `product_attribute_values` | 0 | Custom field values for products. One table per module, all extending `AttributeValueBase`. |
| `customer_attribute_values`, `vendor_attribute_values`, `branch_attribute_values`, `warehouse_attribute_values`, `tax_profile_attribute_values`, `uom_attribute_values` | 0 | The same, for the other supported objects (`20260810_0063`). Storage and validation are live; **the owning modules do not call `AttributeService` yet**, so values are not reachable through those modules' APIs. |

## How a firm resolves its capabilities

```
X-Firm-ID header
   └─> firm_business_profiles  (firm → profile)
         └─> if none assigned: business_profiles WHERE is_default  → GENERIC
               └─> profile_features / profile_modules WHERE is_enabled
                     └─> BusinessCapabilities(features, modules)
```

Implemented in `app/business/gating.py::resolve_capabilities`. A firm with no
assignment falls back to the default profile rather than being denied — two of
the four firms are in that state today.

Current assignments:

| Firm | Profile | Effect |
| --- | --- | --- |
| MEDI01 | PHARMACY | batch, expiry, manufacturing date, shelf life, drug licence, prescription |
| FOOD01 | FOOD | batch, expiry, manufacturing date, shelf life |
| ELEC01 | *(none)* → GENERIC | barcode, attachments |
| WHOLE01 | *(none)* → GENERIC | barcode, attachments |

## What the profile actually changes today

Be precise here — the framework is wired into more places than it *drives*.

**Enforced (behaviour changes):**

- `app/business/gating.py` — `require_feature` blocks writes when a profile
  disables the capability. Applied only to `batch_serial` (`BATCH_TRACKING`,
  `SERIAL_NUMBER`) as the reference. `require_module` exists alongside it but is
  **not yet applied to any route**.
- `app/products` — `_validate_feature_gated_fields` rejects a barcode or QR code
  when `BARCODE` / `QR_CODE` are disabled, and resolves which custom attributes
  apply via profile + category.

**Recorded (stamped, not enforced):** `business_profile_id` is written onto
records in `branches`, `inventory`, `delivery_note`, `purchase_invoice` and
others. Useful for reporting on "which operating model produced this record";
it does not change behaviour.

**Catalogue only:** `business_profile_uom_defaults` is readable and editable
through `/api/v1/uom-framework/profiles/{id}/defaults` but is **not** applied
automatically when a product is created. The defaults exist; nothing consumes
them yet.

```
GENERIC    base=UNIT   purchase=BOX     sales=UNIT
PHARMACY   base=STRIP  purchase=BOX     sales=STRIP
FOOD       base=PACK   purchase=CARTON  sales=PACK
WHOLESALE  base=UNIT   purchase=CASE    sales=UNIT
```

**Not behaviour at all:** `business_profiles` and `business_features` appear in
global search as *searchable records*. That is search coverage, not gating.

**Still unenforced:** 18 of the 21 features have no code reading them. Only
`BARCODE`, `QR_CODE` and `TERRITORY` are referenced outside `app/business`.

## How to extend it

### Add a capability that changes behaviour

1. Insert the feature into `business_features` (migration).
2. Enable it for the right profiles in `profile_features`.
3. Gate the routes: `dependencies=[require_feature("YOUR_CODE")]`.

Gates are **write-only** — safe methods always pass, so enabling one can never
hide data a firm already has.

### Gate a whole module

Enable it in `profile_modules`, then apply `require_module("SALES")` to that
module's write routes. Note the desktop's `/active-modules` filtering only hides
menu entries; it is not a security boundary.

### Add a custom field to a module

1. `AttributeEntityType` gains a member if the module is new.
2. A ~20-line table extending `AttributeValueBase`, setting `ENTITY_TYPE` and
   `OWNER_COLUMN`, with a real FK to the owning record.
3. Call `AttributeService.replace_values` on save, `values_for` /
   `values_for_many` on read.

Definitions are configured at runtime through
`/api/v1/business-framework/attribute-definitions` — adding a *field* needs no
code, only adding a new *module* does.

## Status — what is built and what is not

As of 2026-08-09, branch `backend/finance-audit-platform-hardening`.

### Built

| Capability | State |
| --- | --- |
| Profile catalogue | 12 profiles, 21 features, 14 modules seeded |
| Profile → feature/module mappings | Populated for every industry by `20260809_0046`. Previously only GENERIC had a real configuration. |
| Firm → profile assignment | `firm_business_profiles`, one profile per firm, default-profile fallback |
| Capability resolution | `resolve_capabilities` in `app/business/gating.py` |
| `require_feature` gate | Built and applied to `batch_serial` (`BATCH_TRACKING`, `SERIAL_NUMBER`) |
| Feature checks in products | `BARCODE` and `QR_CODE` reject a disabled field |
| Attribute catalogue with entity targeting | `entity_type` on `AttributeDefinition`, exposed on the API, `data_type` validated against the enum |
| Attribute storage and validation | `AttributeService` plus `AttributeValueBase`; typed, indexed columns |
| Product custom fields | `product_attribute_values`, wired end to end including the desktop Attributes tab |
| Category-scoped mandatory rules | `category_attribute_rules`, read at save time and by `/products/metadata` |

### Not built

Ordered by what blocks the most.

| # | Gap | Why it matters |
| --- | --- | --- |
| 1 | **Desktop attribute inputs are untyped** | The product form *does* render an Attributes tab with a field per applicable attribute and required-field validation. But every field is a plain text box regardless of `data_type`, and the payload always sends a string. Harmless today because all 13 seeded definitions are `TEXT`; the moment a DATE, NUMBER or BOOLEAN definition is created the user gets a free-text box and must type exact ISO format or a lowercase boolean, or the backend rejects it. Needs type-aware inputs: date picker, checkbox, numeric field. |
| 2 | **`require_module` is defined but applied nowhere** | Module gating exists as a mechanism only. A firm whose profile disables a module can still call its endpoints. |
| 3 | **18 of 21 features have no enforcement** | Only `BARCODE`, `QR_CODE` and `TERRITORY` are read outside `app/business`. Each remaining feature needs a product decision about what it actually does before it can be wired. |
| 4 | **Only products *read and write* custom fields** | Every declared object now has a value table (`20260810_0063`), and `AttributeService` stores and returns values for all of them. What is missing is the last mile: only `ProductService` calls `replace_values`/`values_for`, so the other six modules' create, update and read paths ignore attributes entirely. Each needs the same ~10 lines products already has, plus a schema field. |
| 5 | **`vendors.business_attributes` is an untyped JSON blob** | Unvalidated, unlinked to the catalogue, looks like this feature but is not. Should migrate onto the framework before anyone stores data in it. |
| 6 | **UOM defaults are not applied** | `business_profile_uom_defaults` is readable and editable but nothing consumes it when a product is created. |
| 7 | **ELEC01 and WHOLE01 have no profile** | Both fall back to GENERIC, so neither gets the electronics or wholesale capabilities its business implies. A data gap, not a code one. |
| 8 | **Line-level attributes undecided** | See the note in the coverage table; needs its own design round. |

### Smaller follow-ups

- `ProductService._category_attribute_ids` and `AttributeService.mandatory_ids`
  now compute overlapping things. Both are correct and both are used; they
  should converge on the service when `/products/metadata` is next touched.
- `data_type` supports TEXT, NUMBER, DATE and BOOLEAN, each stored in its own
  indexed column so reports can filter on it:

  | Type | Column | Notes |
  | --- | --- | --- |
  | `TEXT` | `value_text` | |
  | `NUMBER` | `value_number` | `NUMERIC(18, 6)` — signed, decimals to six places, **silently rounded beyond that**. Returned as `Decimal`, never float. |
  | `DATE` | `value_date` | Desktop always sends ISO-8601 from a picker. |
  | `BOOLEAN` | `value_boolean` | Tristate: unset is distinct from false. |

  An unrecognised type falls back to text rather than failing, so a new type can
  be added without breaking existing screens.
- **A list of allowed values is not supported** — a fixed dropdown such as
  storage temperature (Ambient / Chilled / Frozen) has to be modelled as TEXT
  today, which will not hold up for reporting. `validation_rule` is an unused
  JSON column on the definition and is the natural home for an allowed-values
  list.
- **All 13 seeded definitions are `TEXT`, including `EXPIRY_DATE`,
  `SHELF_LIFE_DAYS`, `WARRANTY_MONTHS` and `WEIGHT`.** That defeats the typed
  columns: an expiry date held as text cannot answer "what expires in 30 days",
  which is the reason typed storage was chosen over JSON. Retyping them should
  happen together with the type-aware form inputs, since one without the other
  breaks data entry.

## Planned coverage — which modules should get custom fields

Every major ERP supports custom fields in the same three places: **master data**,
**transaction headers**, and **transaction lines**. SAP does it with append
structures and CDS extensions, NetSuite with entity/item/transaction-body and
transaction-line custom fields, Dynamics 365 Business Central with table
extensions, Odoo with Studio fields on any model. Line-level is the one most
often skipped early and most often regretted, because discount schemes, batch
notes and per-line compliance data have nowhere else to go.

Recommended order for this platform, driven by what the pharmacy, food and
kitchen verticals actually need:

| # | Entity | Why it matters | Typical fields |
| --- | --- | --- | --- |
| 1 | **Customer** | Compliance identifiers are per-customer and legally required | drug licence no + expiry, FSSAI licence, GST treatment, credit rating |
| 2 | **Vendor** | Same, and `vendors.business_attributes` is an untyped JSON blob that should migrate onto this framework | drug licence, FSSAI, MSME registration |
| 3 | **Branch / Warehouse** | In Indian pharma each *premises* carries its own licence, so this cannot live on the firm | premises drug licence, cold-chain certification, storage category |
| 4 | **Batch / Lot** | Pharma and food traceability; some of this already has dedicated columns, so check before duplicating | country of origin, QA release reference, retest date |
| 5 | **Transaction headers** (sales/purchase order, invoice, delivery note) | Logistics and statutory references that vary by industry | e-way bill number, transport mode, vehicle number, LR number |
| 6 | **Transaction lines** | The largest design decision — defer deliberately, do not drift into it | scheme code, per-line batch remarks, free-quantity reason |

Items 1–5 are the same pattern already proven on products: one value table, a
migration, and two service calls each.

**Item 6 needs a decision before any work.** Line-level attributes multiply row
counts by an order of magnitude (lines per document × attributes per line) and
raise questions the header case does not: are line attributes copied when a
purchase order becomes a goods receipt, and then an invoice? Do they survive an
amendment? Treat it as its own design round.

`AttributeEntityType` declares `PRODUCT`, `CUSTOMER`, `VENDOR`, `BRANCH`,
`WAREHOUSE`, `TAX_PROFILE` and `UOM`. Every one now has a value table.

**`UOM` is the exception to the pattern and worth reading before copying it.**
Every other owning table is firm-owned, so the owning record already belongs
to exactly one firm and the owner id alone identifies one firm's data. `uoms`
carries no `firm_id` and a single row serves every firm sharing a store, so
the firm is part of that table's identity: uniqueness is (firm, unit,
attribute), and reads must pass `firm_id` to `values_for` / `values_for_many`.
Keyed on the unit alone, the first firm to save would have claimed the
attribute and locked every other firm in the store out of setting it, and one
firm saving a unit's fields would have cleared another firm's values. Apply
the same shape to any future catalogue table that has no `firm_id`.

## Design decisions worth knowing

**The catalogue is shared; value storage is per module.** One
`attribute_definitions` table describes every custom field, but each module owns
its value table so values keep a real foreign key and their own indexes. A
single polymorphic value table was built first and rejected: it lost referential
integrity, forced every index to lead with a discriminator, and encouraged
per-row lookups instead of joins.

**Values are typed, never JSON.** `value_text` / `value_number` / `value_date` /
`value_boolean`, each indexed. A `products.category_attribute_values` JSON blob
existed until 2026-08-09 and could not be filtered or reported on.

**Unassigned firms fall back to the default profile** rather than erroring, so a
configuration gap degrades to "generic behaviour" instead of an outage.

## Related

- `app/business/gating.py` — capability resolution and route gates
- `app/business/services/attribute_service.py` — custom fields
- `app/business/services/framework_service.py` — profile administration API
- `docs/MULTI_INDUSTRY_ERP_ARCHITECTURE.md` — the original design intent
- `docs/MODULE_REVIEW_CHECKLIST.md` — the per-module review checklist
