# Business Profile Framework

How one codebase serves a pharmacy, a food distributor and an electronics
wholesaler without a branch per industry.

Verified against the running backend and all four seeded firms on 2026-08-12.
Every count and every refusal message below was produced by querying the live
stores, not written from memory.

## The idea

A firm is assigned exactly one **business profile** — PHARMACY, FOOD,
WHOLESALE, ELECTRONICS and so on. That profile answers four questions:

| Question | Answered by |
| --- | --- |
| What capabilities does this firm operate with? | **Features** |
| Which workspaces does it see and use? | **Modules** |
| What extra fields do its records carry? | **Attribute definitions** |
| What units does it buy and sell in? | **UOM defaults** |

Nothing about an industry is hardcoded into an entity. A pharmacy tracks expiry
dates because its profile enables `EXPIRY_TRACKING`, not because `BatchRecord`
has a pharmacy branch in its code.

## Why it is worth having

The alternative to a profile framework is an `if industry == "PHARMACY"` inside
the entity, and then a second one inside the form, and then a third inside the
report. This framework buys four things instead:

**One deployment serves every industry.** The same binary, the same schema and
the same endpoints run a chemist and a garment wholesaler. Onboarding a new
industry is a row in `business_profiles` plus its feature and module mappings —
a migration, not a release branch.

**A capability is declared once and enforced everywhere.** `EXPIRY_TRACKING` is
a single row; the batch service, the product form and the desktop menu all read
that one answer. Turning it off cannot leave a stray code path still accepting
expiry dates — that defect actually happened, in `products`, when a private
resolver filtered neither `is_active` nor `is_deleted` while every
`require_feature` endpoint refused correctly. One resolver, one answer.

**The server is authoritative, not the client.** The desktop's
`/active-modules` filtering only hides menu entries. Gating lives in the
backend, so a firm cannot reach a capability its profile denies by calling the
API directly.

**A configuration gap degrades instead of failing.** A firm with no assignment
falls back to the platform default profile; a store with no default enforces
nothing at all. Neither state locks anyone out, because an unseeded catalogue is
an accident, not a decision.

## The tables

```
                        platform schema
                        ┌──────────┐
                        │  firms   │
                        └────┬─────┘
                             │ (firm_id, no FK across schemas)
─────────────────────────────┼──────────────── every firm store, one copy each
                             │
                  ┌──────────▼─────────────┐
                  │ firm_business_profiles │   assigns one profile to one firm
                  └──────────┬─────────────┘
                             │
                  ┌──────────▼──────────┐
                  │  business_profiles  │   12 — the industries
                  └──────────┬──────────┘
                             │
     ┌───────────────┬───────┴────────┬──────────────────┐
     │               │                │                  │
┌────▼─────────┐ ┌───▼──────────┐ ┌───▼───────────────┐ ┌▼─────────────────────┐
│profile_      │ │profile_      │ │attribute_         │ │business_profile_     │
│features      │ │modules       │ │definitions        │ │uom_defaults          │
│75            │ │130           │ │13                 │ │5                     │
└────┬─────────┘ └───┬──────────┘ └───┬───────────────┘ └──────────────────────┘
     │               │                │
┌────▼─────────┐ ┌───▼──────────┐ ┌───▼───────────────────┐
│business_     │ │business_     │ │ per-module value      │
│features      │ │modules       │ │ tables, e.g.          │
│21            │ │14            │ │ product_attribute_    │
└──────────────┘ └──────────────┘ │ values                │
                                  └───────────┬───────────┘
                                  ┌───────────▼───────────┐
                                  │category_attribute_    │
                                  │rules   7              │
                                  └───────────────────────┘
```

### The catalogue exists once per firm store, not once per platform

This is the fact to internalise before changing anything here. Every table
above is **firm-owned**, so each firm store carries its own complete copy of the
catalogue. Only `firms` is a platform table, which is why
`firm_business_profiles.firm_id` carries no foreign key.

Measured on 2026-08-12 across the three stores this deployment has:

| Store | Schema | `business_profiles` | `business_features` | `profile_features` | Assignments |
| --- | --- | ---: | ---: | ---: | --- |
| Shared | `firm_shared` | 12 | 21 | 75 | MEDI01 → PHARMACY, FOOD01 → FOOD |
| WHOLE01 dedicated schema | `wholesale_hub` | 12 | 21 | 75 | WHOLE01 → WHOLESALE |
| ELEC01 dedicated database | `electrolink_ops` | 12 | 21 | 75 | ELEC01 → ELECTRONICS |

Two consequences that have each cost time:

1. **A migration that touches this catalogue must run against every store.**
   Use `scripts/migrate_all_stores.py`, never a bare `alembic upgrade head` —
   that advances only the platform schema, which holds none of these tables.
2. **A firm's assignment is invisible from the wrong store.** Querying
   `firm_shared.firm_business_profiles` returns two rows and makes WHOLE01 and
   ELEC01 look unassigned. They are not; their rows live in their own stores.
   Read capabilities through the API or through `resolve_capabilities`, which
   runs on whichever session `get_db` resolved.

## Table reference

Sixteen tables in four layers. Every one also carries the `BaseEntity` columns
(`id`, `created_at`/`created_by`, `updated_at`/`updated_by`, `version`,
`is_deleted`, `deleted_at`/`deleted_by`), so only the columns each table *owns*
are listed. Row counts are from `firm_shared` on 2026-08-12.

### Layer 1 — Catalogue: what can exist

#### `business_profiles` — 12 rows

The industries themselves. One row is one operating model.

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `PHARMACY`, `WHOLESALE`, … |
| `industry_type` | Industry classification; mirrors `code` in the seed |
| `status` | `ACTIVE` or inactive |
| `is_default` | Exactly one row is true — GENERIC. The fallback for unassigned firms |
| `default_settings` | JSON of seeded defaults. **Written by the seed, read by nothing today** |

#### `business_features` — 21 rows

The capability switches. **Three separate booleans, and conflating them is the
classic mistake:**

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `BATCH_TRACKING` |
| `category` | What the capability is *about* — display only, see below |
| `default_enabled` | What applies when a profile has **no** mapping row. True for `ATTACHMENTS` and `BARCODE` only |
| `is_active` | An **administrator's** choice — withdraws the feature from every profile at once |
| `is_implemented` | A **fact about the codebase**. False for the 7 roadmap features; the service refuses to enable them |

**`category` decides nothing.** No gate, no resolution and no filter reads it;
it groups the feature picker and is matched by the catalogue search. It was
seeded as `OPERATIONS` for all 21 rows, which grouped nothing, and was given
real buckets by `20260812_0067`:

| Category | Features |
| --- | --- |
| `TRACEABILITY` | BATCH_TRACKING, SERIAL_NUMBER, IMEI, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| `CATALOGUE` | BARCODE, QR_CODE, ATTACHMENTS |
| `DISTRIBUTION` | TERRITORY, VEHICLE_TRACKING, MULTIPLE_WAREHOUSES |
| `COMPLIANCE` | DRUG_LICENSE, PRESCRIPTION_REQUIRED |
| `SALES` | COMMISSION, WARRANTY |
| `PRODUCTION` | RECIPE_MANAGEMENT, KITCHEN_MANAGEMENT |
| `SERVICES` | PROJECT_MANAGEMENT, SERVICE_CONTRACTS |
| `CONTROLS` | APPROVAL_WORKFLOW |

They describe what the capability is about, **not which industry uses it** — a
feature belongs to several industries, so grouping by industry would duplicate
every row. A new feature should be given one; an uncategorised feature falls
into "General" in the picker rather than being hidden.

#### `business_modules` — 14 rows

The workspaces.

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `SALES`, `KITCHEN`, `ACCOUNTING`, … |
| `ui_route` | The desktop route the shell navigates to |
| `default_enabled` | True for the six core modules: `DASHBOARD`, `MASTERS`, `PRODUCTS`, `REPORTS`, `ADMINISTRATION`, `SETTINGS` |
| `is_active` | Administrator's switch |

#### `attribute_definitions` — 13 rows

The custom-field catalogue — the *definition*, never the value.

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `EXPIRY_DATE`, `FSSAI_NUMBER` |
| `entity_type` | Which record it extends: `PRODUCT`, `CUSTOMER`, `VENDOR`, `BRANCH`, `WAREHOUSE`, `TAX_PROFILE`, `UOM` |
| `data_type` | `TEXT` / `NUMBER` / `DATE` / `BOOLEAN` — decides which value column is used |
| `mandatory` | Required on every record of that type |
| `default_value` | Pre-filled value |
| `applicable_category` | Narrows to one product category; NULL means all |
| `applicable_business_profile_id` | Narrows to one industry; NULL means all |
| `is_active` | Hides it without deleting |
| `validation_rule` | JSON. **Unused** — the natural home for an allowed-values list |

### Layer 2 — Mappings: what each profile enables

#### `profile_features` — 75 rows

Profile × feature. This is the table the gate reads.

| Column | Stores |
| --- | --- |
| `business_profile_id`, `feature_id` | The pair |
| `is_enabled` | The answer, overriding `business_features.default_enabled` |
| `configuration` | JSON of per-profile feature settings; returned by `/active-features`, empty today |

#### `profile_modules` — 130 rows

Profile × module. **Two different booleans:**

| Column | Stores |
| --- | --- |
| `is_enabled` | May the firm use it — what `require_module` would gate on |
| `is_visible` | Should it appear in the menu. Enabled-but-hidden is expressible, and is **not** a permission |
| `display_order` | Sidebar sort position |
| `configuration` | JSON, per-profile module settings |

#### `category_attribute_rules` — 7 rows

Makes an attribute mandatory for a **profile + product category** pair — finer
than `attribute_definitions.mandatory`, which is global. Read by
`AttributeService.mandatory_ids` on save and by `GET /api/v1/products/metadata`
to tell a client which fields to render.

| Column | Stores |
| --- | --- |
| `business_profile_id` | **Nullable** — NULL means the rule applies to every profile |
| `category_code` | NOT NULL — `MEDICINE`, `FOOD`, `ELECTRONICS` |
| `attribute_definition_id` | Which field |
| `is_mandatory` | The rule |
| `validation_override` | JSON, per-category validation. Unused |

Seeded: PHARMACY/MEDICINE requires `BATCH_NUMBER`, `EXPIRY_DATE` and
`MANUFACTURER`; FOOD/FOOD requires `EXPIRY_DATE` and `SHELF_LIFE_DAYS`;
ELECTRONICS requires `IMEI` and `WARRANTY_MONTHS`.

#### `business_profile_uom_defaults` — 5 rows

Default units per industry.

| Column | Stores |
| --- | --- |
| `business_profile_id` | NOT NULL — the industry |
| `firm_id` | **Nullable, and this is the point.** NULL is the profile-wide default; a set value is one firm's override of it, and it wins. The rank is explicit, never an `ORDER BY firm_id` — NULLs sort first in PostgreSQL and last in SQLite |
| `base_uom_id`, `inventory_uom_id`, `purchase_uom_id`, `sales_uom_id` | The four unit slots |
| `allow_fraction`, `allow_decimal` | Whether part-units are permitted |

### Layer 3 — Assignment: which firm gets what

#### `firm_business_profiles` — 2 rows in `firm_shared`

The link between a firm and its industry. Unique on `firm_id` — one profile per
firm. Only two rows here because WHOLE01 and ELEC01 keep theirs in their own
stores.

| Column | Stores |
| --- | --- |
| `firm_id` | **No foreign key** — `firms` lives in `platform`, this table does not |
| `business_profile_id` | The assigned profile |
| `is_active` | Inactive rows are ignored by resolution |
| `effective_from` | When the assignment began |
| `notes` | Free text — why this firm was put on this profile |

### Layer 4 — Values: the actual per-record data

Seven tables of **identical shape**, differing only in the owner column. All are
empty today.

| Table | Owner column | Reachable through its module's API? |
| --- | --- | --- |
| `product_attribute_values` | `product_id` | **yes, end to end** |
| `customer_attribute_values` | `customer_id` | table only |
| `vendor_attribute_values` | `vendor_id` | table only |
| `branch_attribute_values` | `branch_id` | table only |
| `warehouse_attribute_values` | `warehouse_id` | table only |
| `tax_profile_attribute_values` | `tax_profile_id` | table only |
| `uom_attribute_values` | `uom_id` | table only |

Shared columns:

| Column | Stores |
| --- | --- |
| `firm_id` | Owning firm |
| `<owner>_id` | Real FK to the record, `ON DELETE CASCADE` |
| `attribute_definition_id` | Which field, `ON DELETE RESTRICT` — a definition in use cannot be deleted |
| `value_text` / `value_number` / `value_date` / `value_boolean` | **Exactly one is populated**, chosen by the definition's `data_type`. Numbers are `NUMERIC(18, 6)` |

Each carries a unique constraint on (owner, definition) so a record cannot hold
one field twice, plus indexes on `(firm_id, value_*)` so reports can filter on
custom fields. `uom_attribute_values` is the firm-scoped exception described
under [Custom fields](#custom-fields).

## What each profile actually enables

Read live from `profile_features` on 2026-08-12:

| Profile | Features |
| --- | --- |
| PHARMACY | ATTACHMENTS, BARCODE, BATCH_TRACKING, DRUG_LICENSE, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| FOOD | ATTACHMENTS, BARCODE, BATCH_TRACKING, EXPIRY_TRACKING, MANUFACTURING_DATE, SHELF_LIFE |
| MANUFACTURING | APPROVAL_WORKFLOW, ATTACHMENTS, BARCODE, BATCH_TRACKING, MANUFACTURING_DATE, MULTIPLE_WAREHOUSES |
| WHOLESALE | ATTACHMENTS, BARCODE, BATCH_TRACKING, MULTIPLE_WAREHOUSES, TERRITORY |
| AGENCY | ATTACHMENTS, BARCODE, MULTIPLE_WAREHOUSES, TERRITORY |
| ELECTRONICS | ATTACHMENTS, BARCODE, SERIAL_NUMBER, WARRANTY |
| RETAIL | ATTACHMENTS, BARCODE, EXPIRY_TRACKING, QR_CODE |
| GARMENTS | ATTACHMENTS, BARCODE, QR_CODE |
| RESTAURANT | ATTACHMENTS, EXPIRY_TRACKING, SHELF_LIFE |
| GENERIC | ATTACHMENTS, BARCODE |
| SERVICE | APPROVAL_WORKFLOW, ATTACHMENTS |
| CUSTOM | *(none — configured per deployment)* |

Module counts run 10–12 per profile: RESTAURANT and SERVICE get 12 (they add
`KITCHEN`/`RECIPES` and `PROJECTS`/`CONTRACTS`), ELECTRONICS and MANUFACTURING
11, everyone else the 10 core workspaces.

## How a firm resolves its capabilities

```
X-Firm-ID header
   └─> firm_business_profiles  (firm → profile, is_active, not deleted)
         └─> if none assigned: business_profiles WHERE is_default  → GENERIC
               └─> if no default either: enforce nothing
                     └─> for each active catalogue entry:
                           explicit profile_features/profile_modules row?
                             yes → its is_enabled
                             no  → the catalogue's default_enabled
                           └─> BusinessCapabilities(profile_code, features, modules)
```

Implemented in `app/business/gating.py::resolve_capabilities`. Both queries
require `is_active` and `is_deleted = false` on the catalogue row, so
deactivating a feature withdraws it from every profile at once — the fallback
must never resurrect a deactivated entry.

**The `default_enabled` fallback is load-bearing, and it was a defect.**
`resolve_capabilities` used to inner-join the mapping table, reading a missing
row as "disabled", while `BusinessProfileFrameworkService.active_features` — the
endpoint the desktop reads to decide what to render — applied `default_enabled`.
The two disagreed for any profile missing a row. Measured on 2026-08-12, four
combinations were affected: CUSTOM (`ATTACHMENTS`, `BARCODE`), RESTAURANT
(`BARCODE`) and SERVICE (`BARCODE`) were advertised the feature, would have
rendered the field, and would have been refused on save with
`403 …does not enable BARCODE`. No firm sat on those three profiles, so nobody
hit it.

Seeding the missing rows would not have fixed it: a profile created through
`POST /business-framework/profiles` starts with no mapping rows at all, so the
divergence would return with the next profile someone added. The resolver was
corrected instead — one rule, both paths — and
`tests/unit/test_business_profile_gating.py` pins it.

`ProfileModule.is_visible` is deliberately **not** read by the gate. Visibility
decides whether a workspace appears in the desktop's menu; letting it decide
whether a write is refused would mean hiding a module from the sidebar quietly
revoked the right to use it.

Current assignments — all four firms now carry a real profile:

| Firm | Store | Profile | Gets |
| --- | --- | --- | --- |
| MEDI01 | `firm_shared` | PHARMACY | batch, expiry, manufacturing date, shelf life, drug licence |
| FOOD01 | `firm_shared` | FOOD | batch, expiry, manufacturing date, shelf life |
| WHOLE01 | `wholesale_hub` | WHOLESALE | batch, multiple warehouses, territory |
| ELEC01 | `electrolink_ops` | ELECTRONICS | serial numbers, warranty |

## What the profile actually changes today

Be precise here — the framework is wired into more places than it *drives*.

### Two enforcement shapes, and when to use which

**`require_feature("CODE")` gates a whole endpoint.** Right when the feature
owns its own resource: a firm without `BATCH_TRACKING` has no business posting a
batch at all. Applied as a route dependency, exactly like `require_permission`.

**`assert_feature_fields(...)` gates a capability, not a resource.** Most
features are optional *fields* on a resource every firm uses. Gating the
endpoint would stop a firm creating products because it does not scan barcodes.
The service calls this instead, and the write is refused only when it actually
populates one of the named fields.

Both are **write-only**: `GET`, `HEAD` and `OPTIONS` always pass, so switching
enforcement on can never hide data a firm already has. Blank and unchanged
always pass in `assert_feature_fields` too — otherwise disabling a feature would
freeze every record that already carried the field. A firm whose store resolves
no profile *and* no default is never gated, because a configuration gap is not a
decision.

### Enforced as of 2026-08-12 — 11 of 21 features

| Feature | Shape | Where | Refused when |
| --- | --- | --- | --- |
| `BATCH_TRACKING` | endpoint | `batch_serial` (6 routes) | any batch write |
| `SERIAL_NUMBER` | endpoint | `batch_serial` (3 routes) | any serial write |
| `EXPIRY_TRACKING` | field | `batch_serial` | `expiry_date`, `best_before_date` |
| `MANUFACTURING_DATE` | field | `batch_serial` | `manufacturing_date` |
| `SHELF_LIFE` | field | `batch_serial` | `shelf_life_days` |
| `WARRANTY` | field | `batch_serial`, `products` | warranty fields, `track_warranty` |
| `BARCODE` | field | `products` | `barcode` |
| `QR_CODE` | field | `products` | `qr_code` |
| `DRUG_LICENSE` | field | `vendors` | licence fields |
| `ATTACHMENTS` | field | all 7 transactional modules | `attachments` |
| `VEHICLE_TRACKING` | field | `delivery_note`, `goods_receipt` | `vehicle`, `driver`, `vehicle_number` |

Verified live against WHOLE01, whose WHOLESALE profile enables `BATCH_TRACKING`
but not `EXPIRY_TRACKING`:

```
POST /api/v1/batch-serial/batches   {"batch_number":"…","quantity":"10"}
  → 201 Created

POST /api/v1/batch-serial/batches   {"batch_number":"…","quantity":"10",
                                     "expiry_date":"2027-01-31"}
  → 403 {"code":"authorization_denied",
         "message":"This firm's business profile does not enable
                    EXPIRY_TRACKING, so expiry_date cannot be set."}
```

The firm can still keep batches. It just cannot give one an expiry date, which
is precisely what the feature is about. That is the distinction the two shapes
exist to express.

### Declared but deliberately ungated — 3 features

`TERRITORY`, `APPROVAL_WORKFLOW` and `MULTIPLE_WAREHOUSES` all have backing code
and could be gated tomorrow. Each is waiting on a product decision, not on
engineering:

- **`TERRITORY`** is enabled only by AGENCY and WHOLESALE. Enforcing it would
  take territory and route management away from the other ten profiles,
  including PHARMACY, FOOD and RETAIL — all of which plausibly sell by territory
  on a distribution platform. **The seed assignment is what looks wrong, not the
  code.** Deferred on 2026-08-10 pending a decision about which profiles should
  have it, or whether territory is core and should not be a switch at all.
- **`APPROVAL_WORKFLOW`** and **`MULTIPLE_WAREHOUSES`** are the same shape: each
  needs a decision about what disabling it should actually do before a gate can
  mean anything.

### Not implemented — 7 features

`COMMISSION`, `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`,
`PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT` and `SERVICE_CONTRACTS` had no backing
code in either application. They are kept as roadmap and carry
`business_features.is_implemented = false` (`20260810_0059`), which the service
refuses to enable. The same migration withdrew the 17 profile claims that
advertised them, including PHARMACY's `PRESCRIPTION_REQUIRED` and RESTAURANT's
`KITCHEN_MANAGEMENT`.

`is_implemented` is a fact about the codebase and is deliberately **not**
`is_active`, which is an administrator's choice. Conflating them would let an
administrator switch on a feature that does nothing, and would let a developer's
progress silently re-enable something a firm had turned off.

### Recorded, not enforced

`business_profile_id` is stamped onto records in `branches`, `inventory`,
`delivery_note`, `purchase_invoice` and others. Useful for reporting on "which
operating model produced this record"; it changes no behaviour.

### Applied by pre-filling, not by the server

`business_profile_uom_defaults` reaches a product through the **form**: a new
product's base, inventory, purchase and sales units are seeded from the firm's
profile and can be changed before saving. `ProductService` still stores exactly
what it is sent. A unit the user can see is one they can disagree with; a unit
applied silently is noticed only when a conversion comes out wrong. A firm
reads its own defaults from `GET /api/v1/uom-framework/profile-defaults`, which
takes no profile id.

Units are deliberately **not** fields on the create-profile form — the row must
exist before anything can be keyed to its id, and the profile is platform-wide
while a firm's units are its own. They live on their own endpoint and resolve in
two levels: the profile-wide row (`firm_id IS NULL`) every firm on the profile
inherits, and the firm's own override, which wins.

Both levels are writable from **Administration → Business Profiles → Default
units**, and the dialog states which one it is showing — "PHARMACY sells in
strips" and "we sell in strips" are different claims. Setting what every firm
inherits needs `PLATFORM_SETTINGS`; setting a firm's own needs only
`CONVERSION_RULE_MANAGE`, and that is the default, so a client cannot change
another firm's units by accident.

Both halves were missing until 2026-08-12: reading ignored the profile-wide row
so the seeded industry defaults were unreachable, and writing could only ever
produce a firm override, so a profile created through the API could never carry
defaults for the firms put on it.

```
GENERIC    base=UNIT   purchase=BOX     sales=UNIT
PHARMACY   base=STRIP  purchase=BOX     sales=STRIP
FOOD       base=PACK   purchase=CARTON  sales=PACK
WHOLESALE  base=UNIT   purchase=CASE    sales=UNIT
```

## Custom fields

A module gains industry-specific fields through `AttributeService`, never by
adding columns. The 13 seeded definitions all target `PRODUCT`:

| Definition | Type | Definition | Type |
| --- | --- | --- | --- |
| `BATCH_NUMBER` | TEXT | `IMEI` | TEXT |
| `CHASSIS_NUMBER` | TEXT | `MANUFACTURER` | TEXT |
| `COLOR` | TEXT | `SHELF_LIFE_DAYS` | NUMBER |
| `DRUG_LICENSE_NUMBER` | TEXT | `SIZE` | TEXT |
| `ENGINE_NUMBER` | TEXT | `WARRANTY_MONTHS` | NUMBER |
| `EXPIRY_DATE` | DATE | `WEIGHT` | NUMBER |
| `FSSAI_NUMBER` | TEXT | | |

Values live in typed, indexed `value_text` / `value_number` / `value_date` /
`value_boolean` columns so list filters and reports can query them. Never store
custom fields as JSON: a `products.category_attribute_values` blob existed until
2026-08-09 and could not be filtered.

| Type | Column | Notes |
| --- | --- | --- |
| `TEXT` | `value_text` | |
| `NUMBER` | `value_number` | `NUMERIC(18, 6)` — signed, six decimal places, **silently rounded beyond that**. Returned as `Decimal`, never float. |
| `DATE` | `value_date` | Desktop sends ISO-8601 from a date picker. |
| `BOOLEAN` | `value_boolean` | Tristate: unset is distinct from false. |

An unrecognised type falls back to text rather than failing, so a new type can be
added without breaking existing screens.

**The catalogue is shared; value storage is per module.** One
`attribute_definitions` table describes every custom field, but each module owns
a small table extending `AttributeValueBase` so values keep a real foreign key
and their own indexes. A single polymorphic value table was built first and
rejected: it lost referential integrity, forced every index to lead with a
discriminator, and encouraged per-row lookups instead of joins.

Mandatory rules are scoped by profile **and** product category
(`category_attribute_rules`): `BATCH_NUMBER`, `EXPIRY_DATE` and `MANUFACTURER`
for PHARMACY/MEDICINE; `EXPIRY_DATE` and `SHELF_LIFE_DAYS` for FOOD/FOOD; `IMEI`
and `WARRANTY_MONTHS` for ELECTRONICS.

**`UOM` is the exception to the pattern and worth reading before copying it.**
Every other owning table is firm-owned, so the owner id alone identifies one
firm's data. `uoms` carries no `firm_id` and a single row serves every firm
sharing a store, so the firm is part of that table's identity: uniqueness is
(firm, unit, attribute), and reads must pass `firm_id` to `values_for` /
`values_for_many`. Keyed on the unit alone, the first firm to save would have
claimed the attribute and locked every other firm in the store out of setting
it.

## How to extend it

### Add a capability that changes behaviour

1. Insert the feature into `business_features` — in a migration, run against
   **every** store. Give it a `category`, or it lands under "General" in the
   profile form's feature picker.
2. Enable it for the right profiles in `profile_features`.
3. Decide the shape. Does the feature own a resource, or populate fields on a
   resource every firm uses?
   - Resource → `dependencies=[require_feature("YOUR_CODE")]` on the write
     routes.
   - Fields → `assert_feature_fields(session, firm_id, feature=…, values=…)` in
     the service.
4. Leave `is_implemented = false` until step 3 is real.

### Gate a whole module

Enable it in `profile_modules`, then apply `require_module("SALES")` to that
module's write routes. `require_module` is built and tested but **applied to no
route today** — module gating exists as a mechanism only.

### Add a custom field to a module

1. `AttributeEntityType` gains a member if the module is new.
2. A ~20-line table extending `AttributeValueBase`, setting `ENTITY_TYPE` and
   `OWNER_COLUMN`, with a real FK to the owning record.
3. Call `AttributeService.replace_values` on save, `values_for` /
   `values_for_many` on read. Read a list with `values_for_many`, never per row.

Definitions are configured at runtime through
`/api/v1/business-framework/attribute-definitions` — adding a *field* needs no
code; only adding a new *module* does. The desktop form is at **Administration
→ Attribute Definitions**.

**That endpoint replaces the whole record.** `AttributeDefinitionUpdate`
extends `AttributeDefinitionCreate`, so any column a client omits reverts to
its default. The desktop form sent seven of eleven and hardcoded two of those
to `''`, so until 2026-08-12 saving an edit wiped the description and default
value, reset `entity_type` to `PRODUCT`, and cleared
`applicable_business_profile_id` — turning a pharmacy-only field into one every
industry offers, with nothing reported. Anything editing a definition must send
every column, `validation_rule` included; it has no editor and is round-tripped.

The two narrowing controls — `entity_type` and `applicable_business_profile_id`
— were also missing from the form, so a CUSTOMER attribute or an industry-scoped
one could not be created from the desktop at all. Both are dropdowns now, along
with `data_type`; `applicable_category` is a picker over the firm's product
categories that submits the category's **code**, since an id stored there
matches no category and the definition silently never applies.

## Administration API

| Route | Who | Purpose |
| --- | --- | --- |
| `/api/v1/business-framework/profiles`, `/features`, `/modules` | platform admin | the catalogue, full CRUD |
| `…/profiles/{id}/configuration`, `…/features`, `…/modules` | platform admin | which features and modules a profile enables |
| `…/attribute-definitions`, `…/category-rules` | platform admin | custom field catalogue |
| `…/firms/{id}/profile` | platform admin | assign a profile to a firm |
| `…/active-features`, `…/active-modules` | any authenticated user | what *this* firm resolves to |

The two `active-*` routes are the ones a client calls; everything else is
administration. Profiles, features and modules are editable from the desktop's
administration workspace, which calls `setBusinessProfileFeatures` /
`setBusinessProfileModules` on save.

## Status — what is not built

Ordered by what blocks the most.

| # | Gap | Why it matters |
| --- | --- | --- |
| 1 | **Only `products` reads and writes custom fields** | Every declared entity has a value table (`20260810_0063`) and `AttributeService` stores and returns values for all of them. The last mile is missing: only `ProductService` calls `replace_values`/`values_for`, so the other six modules' create, update and read paths ignore attributes entirely. Each needs the same ~10 lines products already has, plus a schema field. |
| 2 | **`require_module` is applied nowhere** | A firm whose profile disables a module can still call its endpoints. The gate is written and tested; no route uses it. |
| 3 | **3 implemented features are ungated** | `TERRITORY`, `APPROVAL_WORKFLOW`, `MULTIPLE_WAREHOUSES` — each needs a product decision first. See above. |
| 4 | **`vendors.business_attributes` is an untyped JSON blob** | Unvalidated, unlinked to the catalogue, looks like this feature but is not. Should migrate onto the framework before anyone stores data in it. |
| 5 | *(closed 2026-08-12)* **UOM defaults** | Readable, inherited correctly, editable from the desktop, and applied by pre-filling a new product's units rather than filling them in server-side. See `docs/UOM_FRAMEWORK.md`. |
| 6 | **No allowed-values list** | A fixed dropdown such as storage temperature (Ambient / Chilled / Frozen) has to be modelled as TEXT today, which will not hold up for reporting. `validation_rule` is an unused JSON column on the definition and is its natural home. |
| 7 | **Line-level attributes undecided** | Needs its own design round — see below. |

Fixed on 2026-08-12: `resolve_capabilities` ignored `default_enabled`, so the
gate and `/active-features` disagreed for any profile missing a mapping row;
and `get_profile_default` ignored the profile-wide UOM row, so every seeded
industry default was unreachable. Both were two-level lookups with only one
level implemented — worth suspecting wherever a nullable scope column means
"inherit".

Also fixed on 2026-08-12: the Attribute Definitions form dropped four columns
into a full-replace update, so editing a definition wiped its description and
un-scoped it from its business profile. The lesson generalises — **a form
backed by a replacing endpoint must carry every column, including the ones it
does not show.**

Closed since the 2026-08-09 revision of this document: desktop attribute inputs
are now type-aware (date picker, checkbox, numeric formatters in
`ui/workspace/attribute_form_fields.dart`); the seeded definitions are no longer
all TEXT; every firm has a real profile assignment; and enforcement went from 3
features to 11.

## Planned coverage — which modules should get custom fields

Every major ERP supports custom fields in the same three places: **master data**,
**transaction headers**, and **transaction lines**. SAP does it with append
structures and CDS extensions, NetSuite with entity/item/transaction-body and
transaction-line custom fields, Dynamics 365 Business Central with table
extensions, Odoo with Studio fields on any model. Line-level is the one most
often skipped early and most often regretted, because discount schemes, batch
notes and per-line compliance data have nowhere else to go.

| # | Entity | Why it matters | Typical fields |
| --- | --- | --- | --- |
| 1 | **Customer** | Compliance identifiers are per-customer and legally required | drug licence no + expiry, FSSAI licence, GST treatment, credit rating |
| 2 | **Vendor** | Same, and `vendors.business_attributes` should migrate onto this framework | drug licence, FSSAI, MSME registration |
| 3 | **Branch / Warehouse** | In Indian pharma each *premises* carries its own licence, so this cannot live on the firm | premises drug licence, cold-chain certification, storage category |
| 4 | **Batch / Lot** | Pharma and food traceability; some of this already has dedicated columns, so check before duplicating | country of origin, QA release reference, retest date |
| 5 | **Transaction headers** | Logistics and statutory references that vary by industry | e-way bill number, transport mode, vehicle number, LR number |
| 6 | **Transaction lines** | The largest design decision — defer deliberately, do not drift into it | scheme code, per-line batch remarks, free-quantity reason |

Items 1–5 are the pattern already proven on products: one value table, a
migration, and two service calls each.

**Item 6 needs a decision before any work.** Line-level attributes multiply row
counts by an order of magnitude (lines per document × attributes per line) and
raise questions the header case does not: are line attributes copied when a
purchase order becomes a goods receipt, and then an invoice? Do they survive an
amendment? Treat it as its own design round.

## Traps

- **The catalogue lives in every firm store.** Migrate with
  `scripts/migrate_all_stores.py`. A bare `alembic upgrade head` advances the
  platform schema, which holds none of these tables.
- **Gates are write-only by design.** Never gate a read. Enabling enforcement
  must never hide data a firm already has.
- **A missing mapping row is not "disabled".** It means "inherit
  `default_enabled`". Any new code that resolves capabilities must apply that
  fallback, or it will disagree with `/active-features` and refuse writes the
  screen has already invited.
- **Blank is not populated.** `assert_feature_fields` ignores `None`, empty
  strings and collections, and `False`. A zero *number* is populated, because
  somebody typed it. Clearing a field is always allowed.
- **A store with no default profile enforces nothing.** `resolve_capabilities`
  returns empty capabilities rather than denying everything, so an unseeded
  catalogue degrades instead of causing an outage. Do not "fix" this by raising.
- **`/active-modules` filtering in the desktop is cosmetic.** It hides menu
  entries; it is not a security boundary.
- **Never hardcode industry behaviour into an entity.** Declare a feature and
  gate on it. That rule is what lets a twelfth industry be a migration.

## Related

- `app/business/gating.py` — capability resolution and both gate shapes
- `app/business/services/attribute_service.py` — custom fields
- `app/business/services/framework_service.py` — profile administration API
- `docs/MULTI_INDUSTRY_ERP_ARCHITECTURE.md` — the original design intent
- `docs/MODULE_REVIEW_CHECKLIST.md` — the per-module review checklist
