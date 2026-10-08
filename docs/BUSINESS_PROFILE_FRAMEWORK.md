# Business Profile Framework

How one codebase serves a pharmacy, a food distributor and an electronics
wholesaler without a branch per industry.

Brought up to date on 2026-10-08 (backlog 89, steps 1 to 6; the screens and
menus it describes were added on 2026-10-08 and are not yet tested by hand). The
counts of rows in firm stores were measured on 2026-08-12 and are marked as such;
counts after 2026-10-08 are derived from the migrations, not read from a store.

## The idea

A firm is assigned exactly one **business profile** (PHARMACY, FOOD, WHOLESALE,
ELECTRONICS and so on). The profile is smaller than it was. What it still does:

| Tied to the profile | When it acts | Can the firm change it afterwards |
| --- | --- | --- |
| The goods types a new firm starts with | Once, when the firm is first given a profile | Yes: the firm's administrator adds or drops a type |
| Which **modules** and menus the firm has, including the ones only some trades have (kitchen and recipes, projects and contracts) | Every sign-in | By the platform administrator, through the profile |
| The **features about the firm**, not about a product, that code really enforces: `ATTACHMENTS`, `VEHICLE_TRACKING`, `DRUG_LICENSE`, `COMMISSION`, `BATCH_PTR_PTS` | On each write that uses one | By the platform administrator, through the profile |

A profile hands a firm **no unit sets**: the goods types it starts the firm with
decide which unit sets the firm's products are offered first, and a set tied to
no goods type is offered to everyone (`docs/UOM_FRAMEWORK.md`, *Unit sets*).

A profile does **not** decide what goods look like. Whether a product carries a
batch, an expiry date, a serial number, a warranty, a manufacturing date or a
shelf life is the product's own switches (`track_batch`, `track_expiry`,
`track_serial`, `track_manufacturing_date`, `track_warranty`), filled from its
goods type (`docs/GOODS_TYPES.md`). Barcode and QR code are plain product fields
any firm may fill. Which extra fields a record carries is the firm's own rules
and its goods types, see
[How a firm resolves its attributes](#how-a-firm-resolves-its-attributes).

Nothing about an industry is hardcoded into an entity. A pharmacy tracks expiry
dates because the product carries a `track_expiry` switch, not because
`BatchRecord` has a pharmacy branch in its code.

## Why it is worth having

The alternative to a profile framework is an `if industry == "PHARMACY"` inside
the entity, and then a second one inside the form, and then a third inside the
report. This framework buys four things instead:

**One deployment serves every industry.** The same binary, the same schema and
the same endpoints run a chemist and a garment wholesaler. Onboarding a new
industry is a row in `business_profiles` plus its module mappings and, if it
needs any, its starting goods types — a migration, not a release branch.

**A capability is declared once and enforced everywhere.** A feature is a
single row; the service, the form and the desktop menu all read that one
answer. Turning it off cannot leave a stray code path still accepting the
field — that defect actually happened, in `products`, when a private resolver
filtered neither `is_active` nor `is_deleted` while every gated endpoint
refused correctly. One resolver, one answer.

**The server is authoritative, not the client.** The desktop's
`/active-modules` filtering only hides menu entries (the Inventory tabs that
follow the goods are one more such filter, see
[Menus follow the goods](#menus-follow-the-goods)). Gating lives in the
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
     ┌───────────────┴────────┐
     │                        │
┌────▼─────────┐ ┌────────────▼─┐
│profile_      │ │profile_      │
│features      │ │modules       │
│15 (derived)  │ │130           │
└────┬─────────┘ └───┬──────────┘
     │               │
┌────▼─────────┐ ┌───▼──────────┐
│business_     │ │business_     │
│features      │ │modules       │
│5             │ │14            │
└──────────────┘ └──────────────┘
```

The extra-field tables (`attribute_definitions`, `category_attribute_rules`,
`firm_attribute_switches` and the per-module value tables) used to hang off the
profile in this picture. They no longer do: no column in them names a profile
(backlog 89, step 5, migration `20261008_0352`). They are described under
[Custom fields](#custom-fields).

### The catalogue exists once per firm store, not once per platform

This is the fact to internalise before changing anything here. Every table
above is **firm-owned**, so each firm store carries its own complete copy of the
catalogue. Only `firms` is a platform table, which is why
`firm_business_profiles.firm_id` carries no foreign key.

Measured on 2026-08-12 across the three stores this deployment has (the feature
counts were 21 and 75 then; `20261008_0353` took them to 5 and 15 on
2026-10-08, derived from the migrations and not re-measured):

| Store | Schema | `business_profiles` | Assignments |
| --- | --- | ---: | --- |
| Shared | `firm_shared` | 12 | MEDI01 → PHARMACY, FOOD01 → FOOD |
| WHOLE01 dedicated schema | `wholesale_hub` | 12 | WHOLE01 → WHOLESALE |
| ELEC01 dedicated database | `electrolink_ops` | 12 | ELEC01 → ELECTRONICS |

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

Sixteen tables in four layers, plus `firm_attribute_switches` (added on 2026-10-08). Every one also carries the `BaseEntity` columns
(`id`, `created_at`/`created_by`, `updated_at`/`updated_by`, `version`,
`is_deleted`, `deleted_at`/`deleted_by`), so only the columns each table *owns*
are listed. Row counts are from `firm_shared` on 2026-08-12 unless dated otherwise.

### Layer 1 — Catalogue: what can exist

#### `business_profiles` — 12 rows

The industries themselves. One row is one operating model.

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `PHARMACY`, `WHOLESALE`, … |
| `industry_type` | Industry classification; mirrors `code` in the seed |
| `status` | `ACTIVE` or inactive |
| `is_default` | Exactly one row is true — GENERIC. The fallback for unassigned firms |
| `default_settings` | JSON of seeded defaults. **Written by the seed, read by nothing today.** `20261008_0353` removed `inventory_tracking`, `batch_required` and `expiry_required` from it, notes about goods that nothing read; `system_seed.py` no longer writes them |

#### `business_features` — 5 rows

The capability switches, about the **firm** and not about a product. Migration
`20261008_0353` (2026-10-08) withdrew the other rows, in every store, with every
profile's mapping to them:

- what goods look like: `BATCH_TRACKING`, `EXPIRY_TRACKING`,
  `MANUFACTURING_DATE`, `WARRANTY`, `SERIAL_NUMBER`, `SHELF_LIFE`, `BARCODE`,
  `QR_CODE` (now each product's own switches or plain fields);
- `TERRITORY`, `MULTIPLE_WAREHOUSES`, `APPROVAL_WORKFLOW`, which no code enforced,
  so every firm already used them;
- `IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`, `PROJECT_MANAGEMENT`,
  `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`, which had no code behind them;
- `SERIAL_TRACKING`, a code only the demo seeder wrote.

The five that remain are `ATTACHMENTS`, `VEHICLE_TRACKING`, `DRUG_LICENSE`,
`COMMISSION` and `BATCH_PTR_PTS`. All five carry `is_implemented = true`. Grep
`assert_feature_fields(` and `feature_enabled(` under `app/` to see where they
act: `ATTACHMENTS` on the seven transactional modules and on document files,
`VEHICLE_TRACKING` on `delivery_note` and `goods_receipt`, `DRUG_LICENSE` on
vendors, `BATCH_PTR_PTS` on batches, goods receipts and the batch rate in
`app/pricing`. `COMMISSION` is a catalogue row only: no `feature="COMMISSION"`
check exists under `app/` (the commission module is gated by its permission codes,
`COMMISSION_VIEW`, `COMMISSION_MANAGE`, `COMMISSION_PAY`).

| Column | Stores |
| --- | --- |
| `code`, `name`, `description` | `ATTACHMENTS` |
| `category` | What the capability is *about* — display only, see below |
| `default_enabled` | What applies when a profile has **no** mapping row. True for `ATTACHMENTS` only |
| `is_active` | An **administrator's** choice — withdraws the feature from every profile at once |
| `is_implemented` | A **fact about the codebase**. The service refuses to enable a feature where it is false; it is true on all five today |

**`category` decides nothing.** No gate, no resolution and no filter reads it;
it groups the feature picker and is matched by the catalogue search. It was given
real buckets by `20260812_0067`; of the five, `ATTACHMENTS` is `CATALOGUE`,
`VEHICLE_TRACKING` is `DISTRIBUTION`, `DRUG_LICENSE` is `COMPLIANCE`,
`COMMISSION` is `SALES`. A new feature should be given one; an uncategorised
feature falls into "General" in the picker rather than being hidden.

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
| `firm_id` | NULL is a shared field, kept by the platform. Otherwise the firm's own field |
| `entity_type` | Which record it extends: `PRODUCT`, `CUSTOMER`, `VENDOR`, `BRANCH`, `WAREHOUSE`, `TAX_PROFILE`, `UOM` |
| `data_type` | `TEXT` / `NUMBER` / `DATE` / `BOOLEAN` — decides which value column is used |
| `mandatory` | Required on every record of that type |
| `default_value` | Pre-filled value |
| `applicable_category` | Narrows to one product category; NULL means all |
| `is_active` | Hides it without deleting |
| `validation_rule` | JSON. **Unused** — the natural home for an allowed-values list |

### Layer 2 — Mappings: what each profile enables

#### `profile_features` — 15 rows (derived from the migrations on 2026-10-08; 75 before)

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

#### `category_attribute_rules`

*Rewritten 2026-10-08 (backlog 89, step 5, added on 2026-10-08, not yet tested
by hand).* A rule no longer names a business profile: `business_profile_id` was
dropped (migration `20261008_0352`). A rule now names **one thing** and a field,
and says what the rule does there. Read by `AttributeService.applied` and by
`GET /api/v1/products/metadata` to tell a client which fields to render.

This is the *only* way a requirement can be stated, since `20260815_0087`
cleared the four global flags that asked a pharmacy for an IMEI. The list is
paginated and searchable like every other list in this module, and each row
carries the attribute *name* beside its id.

| Column | Stores |
| --- | --- |
| `firm_id` | NULL is a shared rule, kept by the platform. Otherwise the firm's own rule |
| `category_code` | A product category code. Now optional |
| `goods_type_id` | A goods type |
| `customer_group_id` | A customer group |
| `vendor_type_id` | A supplier type |
| `attribute_definition_id` | Which field |
| `is_mandatory` | Whether the field must be filled there |
| `validation_override` | JSON, per-category validation. Unused |

A rule names **exactly one** of `category_code`, `goods_type_id`,
`customer_group_id` and `vendor_type_id`. There is one live rule per firm, field
and thing named, held by four partial unique indexes,
`UQ_category_attribute_rules_<category_code|goods_type|customer_group|vendor_type>_active`.

What a rule does depends on what it names:

- A category rule only makes a field **compulsory** for products in that
  category, as before.
- A rule on a goods type, a customer group or a supplier type **ties the field
  to that kind**. The field is shown only on products of that goods type, on
  customers in that group or on suppliers of that type, and `is_mandatory` says
  whether it must be filled there. A field with no such rule is shown on every
  record of its sort.
- A product with no goods type (General), a customer in no group, a supplier
  with no type and every document are shown no tied field.

Shared rules, kept on the platform's Category Attribute Rules screen, may name a
category code or a shared goods type. A firm's administrator keeps the firm's own
rules on the firm's Custom Fields rules screen and may name any of the four. The
permission is `CUSTOM_FIELD_MANAGE`; no new code was added.

The migration turned the seven seeded shared rules (on category codes MEDICINE,
FOOD and ELECTRONICS) into rules on the shared goods types Medicine, Food and
Electronics. They now only **show** their fields on those products; they no
longer make them compulsory. A firm that wants one compulsory adds its own rule.

#### `firm_attribute_switches`

*Added on 2026-10-08, not yet tested by hand.* One row per firm and field of the
**shared** catalogue: `firm_id`, `attribute_definition_id`, `is_enabled`. One
live row per firm and field. No row means the field is on. A firm's
administrator switches a shared field off or on for their own firm with
`PUT /api/v1/business-framework/firm-custom-fields/{field_id}/use`, sending
`{"is_enabled": false}`. Off hides the field on that firm's forms and **keeps
every stored value**; on shows them again. A firm's own field is retired with its
own Active flag instead. The audit action is `firm_custom_field.use_changed`.
The code is `FirmCustomFieldService.set_use` in
`app/business/services/firm_custom_fields.py`.

Default units left the profile on 2026-10-08: the `business_profile_uom_defaults`
table is gone, and a business profile no longer says anything about units. A
new product's units come from a unit set the user picks; see
`docs/UOM_FRAMEWORK.md`, *Unit sets*.

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

Features, derived on 2026-10-08 from the migrations that map them
(`20260809_0046`, `20260810_0059`, `20261005_0316`, then `20261008_0353`), not
read from a live store. Modules and starting goods types are read from the code
(`PROFILE_MODULES` in `20260809_0046`, `PROFILE_STARTING_GOODS_TYPES` in
`app/products/goods_type_seed.py`).

| Profile | Features | Modules beyond the ten core | Starting goods types |
| --- | --- | --- | --- |
| PHARMACY | ATTACHMENTS, DRUG_LICENSE, BATCH_PTR_PTS | — | Medicine |
| FOOD | ATTACHMENTS, BATCH_PTR_PTS | — | Food |
| WHOLESALE | ATTACHMENTS, BATCH_PTR_PTS | — | — |
| RESTAURANT | ATTACHMENTS | KITCHEN, RECIPES | Food |
| ELECTRONICS | ATTACHMENTS | CONTRACTS | Electronics |
| MANUFACTURING | ATTACHMENTS | RECIPES | — |
| SERVICE | ATTACHMENTS | PROJECTS, CONTRACTS | — |
| GENERIC, AGENCY, RETAIL, GARMENTS | ATTACHMENTS | — | — |
| CUSTOM | *(none mapped; `ATTACHMENTS` is on by its default)* | — | — |

The ten core modules are DASHBOARD, ADMINISTRATION, SETTINGS, MASTERS, PRODUCTS,
PURCHASES, SALES, INVENTORY, REPORTS and ACCOUNTING. No profile maps
`VEHICLE_TRACKING` or `COMMISSION`; they are off until an administrator maps them.

## Are twelve profiles still needed

Facts only, derived on 2026-10-08 from the table above. The decision is the
owner's; nothing has been deleted or merged.

- **Seven profiles differ from the rest in something that is enforced**:
  PHARMACY (Medicine, `DRUG_LICENSE`, `BATCH_PTR_PTS`), FOOD (Food,
  `BATCH_PTR_PTS`), WHOLESALE (`BATCH_PTR_PTS`), RESTAURANT (Food, KITCHEN and
  RECIPES), ELECTRONICS (Electronics, CONTRACTS), MANUFACTURING (RECIPES) and
  SERVICE (PROJECTS, CONTRACTS).
- **GENERIC, AGENCY, RETAIL and GARMENTS are identical to one another in
  everything enforced**: the ten core modules, `ATTACHMENTS` only, no starting
  goods types, no starting unit sets. CUSTOM resolves the same way (no mapped
  feature, `ATTACHMENTS` through its default, the ten core modules) unless an
  administrator has configured it.
- By modules alone there are five groups: the ten core only (GENERIC, AGENCY,
  RETAIL, GARMENTS, CUSTOM, PHARMACY, FOOD, WHOLESALE), plus KITCHEN and RECIPES,
  plus RECIPES, plus CONTRACTS, plus PROJECTS and CONTRACTS.
- By features alone: PHARMACY has three, FOOD and WHOLESALE the same two, and
  every other profile `ATTACHMENTS` only.
- By starting goods types: Medicine (PHARMACY), Food (FOOD, RESTAURANT),
  Electronics (ELECTRONICS), none for the other eight. No profile starts a firm
  with Paint or Cosmetics.
- By starting unit sets: no profile differs, because none hands over any.
- `industry_type`, `description` and `default_settings` (retailer pricing,
  salesman tracking and similar notes) differ per profile but are read by nothing.
- The profile is also stamped onto records in `branches`, `inventory` and others
  for reporting (see *Recorded, not enforced*).

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

Current assignments — all four firms carry a real profile. What each gets
from it is in the table under *What each profile actually enables*:

| Firm | Store | Profile |
| --- | --- | --- |
| MEDI01 | `firm_shared` | PHARMACY |
| FOOD01 | `firm_shared` | FOOD |
| WHOLE01 | `wholesale_hub` | WHOLESALE |
| ELEC01 | `electrolink_ops` | ELECTRONICS |

## How a firm resolves its attributes

*Rewritten 2026-10-08 (backlog 89, step 5, added on 2026-10-08, not yet tested
by hand).* The section above resolves *features and modules*, and the profile
owns those. Custom fields no longer have anything to do with the profile. They
resolve separately, through one resolver, `AttributeService.applied`
(`app/business/services/attribute_service.py`):

```
AttributeService.applied(entity_type, firm_id=, category_code=, kind=RecordKind(...))
   └─> attribute_definitions WHERE
         entity_type = the record being edited (PRODUCT, CUSTOMER, ...)
         is_active   = true
         shared (firm_id NULL) or the firm's own
         applicable_category IN (NULL, the category)
   └─> drop a shared field the firm has switched off (firm_attribute_switches)
   └─> category_attribute_rules, shared and the firm's own:
         a rule on the record's goods type / customer group / supplier type
           ties the field to that kind (shown there, nowhere else)
         a rule on the product's category code makes the field compulsory
```

`app/business/services/field_rules.py` holds what a rule may name. The
`RecordKind` is the record's goods type, customer group or supplier type. A
field with no rule that ties it is shown on every record of its sort. A product
with no goods type (General), a customer in no group, a supplier with no type,
and every document, are shown no tied field.

**NULL on `applicable_category` means every category, not none.** A field every
product needs carries NULL. Get it backwards and a field written for one kind of
goods appears on all of them, which is how `20260801_0011` came to ask a pharmacy
for an IMEI. (It used to be the same for `applicable_business_profile_id`. That
column was removed by backlog 89 step 5.)

`GET /api/v1/business-framework/attribute-definitions/applicable?entity_type=...`
also returns `kind_rules`, so a customer or supplier form can show and hide
fields when the group or type changes, without another call. The product form
still gets its fields from `/products/metadata`, resolved by the category's goods
type.

### Two independent ways a field becomes mandatory

`AttributeService.mandatory_ids` unions them, and they behave differently
enough that choosing the wrong one is a bug rather than a preference.

| | `attribute_definitions.mandatory` | `category_attribute_rules.is_mandatory` |
| --- | --- | --- |
| Scope | **every** record the definition applies to | the one thing the rule names: a category code, a goods type, a customer group or a supplier type |
| Screen | Dynamic Attributes | Mandatory Attributes (shared), Custom Fields rules (a firm's own) |
| Use when | the field is required wherever it appears | the field is required only for some goods, customers or suppliers |

Two properties worth knowing before using either. A rule can only make
mandatory something **already in the applicable set** — `mandatory_ids`
intersects the rules against the applicable definitions, so a rule naming a field
this firm has switched off is inert rather than an error. And the blunt flag
is the one with a history: `20260801_0011` set it on EXPIRY_DATE,
BATCH_NUMBER, MANUFACTURER and IMEI with **no** category scope, so
`AttributeService` refused every product write on a freshly migrated database
until `20260815_0087` cleared it. Where a field really is required, say so in
`category_attribute_rules`.

Either way, **mandatory means a value, not merely a key in the request.** The
same union decides both refusals in `replace_values`: the field must be sent,
and what is sent must not be blank (`""`, whitespace or `null`). Until
2026-09-19 the second refusal read only the definition's own flag, so a field a
category rule required was satisfied by sending it blank and stored with every
value column null (D-CFG-5) -- the desktop form refused the blank, and no other
client did.

### What changing a firm's profile does to existing data

*Changed 2026-10-08 (backlog 89, step 5, not yet tested by hand).* Nothing. A
profile no longer decides which extra fields a firm sees or which are
compulsory, so assigning or changing one takes no extra-field value out of any
read and makes no field appear on old records. Before that change a definition
that stopped applying took its values out of every read while they sat in the
table; that is gone with `applicable_business_profile_id`.

Moving a customer to another group, or a supplier to another type, deletes
nothing either. The old kind's stored value stays and can still be saved back.
The new kind's required fields are asked for at the next save that sends custom
fields.

Switching a shared field off for a firm hides it and keeps every value; see
`firm_attribute_switches`. `docs/BACKLOG.md` §16 records the unguarded edits that
remain in this area: a changed `data_type` strands values in the wrong typed
column, a deleted definition is a bare soft delete with no check for values, and
the mandatory flag blocks the next save of every record missing one.

### A shared store shares the shared catalogue

A definition or a rule with no `firm_id` is **shared**: it lives once per *store*
and is kept by the platform. Two firms in `firm_shared` therefore see one shared
set (measured on 2026-09-06, FOOD01 and MEDI01 shared the rows). A firm's own
definitions and rules carry its `firm_id` and are its own. The shared set is
what `firm_attribute_switches` lets a firm turn off. A firm in its own schema or
database has its own copy of the shared set. `SHARED` is the mode every new firm
gets by default.

## What the profile actually changes today

Be precise here — the framework is wired into more places than it *drives*.

### A firm's starting goods types (2026-10-08)

The first time a firm is given a profile it is handed that profile's
**goods types**: `PHARMACY` starts with Medicine, `FOOD` and `RESTAURANT` with
Food, `ELECTRONICS` with Electronics, every other profile with none
(`PROFILE_STARTING_GOODS_TYPES` in `app/products/goods_type_seed.py`). This is a
starter kit and not a ceiling: it acts once, only for a firm that holds no goods
type (a type the firm dropped counts as held), and a later change of profile adds
nothing. The firm's administrator adds and drops types from then on.
`start_firm_goods_types` writes one audit row, `goods_type.starting_set` (entity
type `firm`; the after data holds the profile and the type codes), and only when
it handed something over. `docs/GOODS_TYPES.md` is the reference.

### Menus follow the goods

*Added on 2026-10-08, not yet tested by hand.* The profile decides the
**modules**. Inside the Inventory module the tabs Batches, Lots, Serial Numbers
and Expiry Monitor follow the firm's goods instead: they show only when the
firm's goods need them. `GET /api/v1/business-framework/active-modules`, the call
the shell already makes at start, carries `goods_tracking` on the row whose code
is `INVENTORY`: a list holding any of `BATCH`, `EXPIRY`, `SERIAL`, and null on
every other row and when no firm is selected. A kind is needed when a goods type
the firm uses switches it on, or when a live product of the firm has that switch
on (a product keeps its own switches, and products filed before goods types
existed have no type). The code is `GoodsTypeRepository.tracking_in_use`,
`GoodsTypeService.tracking_in_use` and
`BusinessProfileFrameworkService.goods_tracking`; the schema field is
`ActiveModuleResponse.goods_tracking`. The desktop side is in
`desktop/docs/DESKTOP_FRAMEWORK.md`. The answer is read when the shell reads the
modules (sign-in, firm switch), so after a firm takes its first tracked goods type
into use the menu appears at the next sign-in or firm switch. Permissions still
apply on top: a user without `BATCH_VIEW` does not see Batches whatever the goods.

### Two enforcement shapes, and when to use which

**`require_feature("CODE")` gates a whole endpoint.** Right when the feature
owns its own resource. Applied as a route dependency, exactly like
`require_permission`. It is defined in `app/business/gating.py` and **no route
under `app/` uses it today**; it is kept as the documented gate for a feature that
owns a whole endpoint, and whether to delete it is the owner's call.

**`assert_feature_fields(...)` gates a capability, not a resource.** Most
features are optional *fields* on a resource every firm uses. Gating the
endpoint would stop a firm creating a delivery note because it does not record a
vehicle. The service calls this instead, and the write is refused only when it
actually populates one of the named fields. `feature_enabled(...)` answers the
same question as a plain yes or no, for a service that wants to branch.

`require_feature` and `assert_feature_fields` are **write-only**: `GET`, `HEAD`
and `OPTIONS` always pass, so switching enforcement on can never hide data a firm
already has. Blank and unchanged always pass in `assert_feature_fields` too —
otherwise disabling a feature would freeze every record that already carried the
field. A firm whose store resolves no profile *and* no default is never gated,
because a configuration gap is not a decision.

### Enforced today

| Feature | Shape | Where | Refused when |
| --- | --- | --- | --- |
| `DRUG_LICENSE` | field | `vendors` | licence fields |
| `BATCH_PTR_PTS` | field | `batch_serial`, `goods_receipt`; read by `pricing` | `ptr`, `pts` |
| `ATTACHMENTS` | field | all 7 transactional modules, `document_files` | `attachments` |
| `VEHICLE_TRACKING` | field | `delivery_note`, `goods_receipt` | `vehicle`, `driver`, `vehicle_number` |

`COMMISSION` is the fifth feature and has no field check (see `business_features`
above).

Batches, serial numbers, expiry and manufacturing dates, shelf life, warranty,
barcode and QR code are not here. They are the product's own switches and fields
(`docs/GOODS_TYPES.md`, `docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`). Territory,
more than one warehouse and approval workflow never had a gate, so every firm
uses them; their feature rows were withdrawn, and a firm's reach to those modules
is its profile's **modules** and its roles' permissions. The six features with no
code behind them (`IMEI`, `KITCHEN_MANAGEMENT`, `PRESCRIPTION_REQUIRED`,
`PROJECT_MANAGEMENT`, `RECIPE_MANAGEMENT`, `SERVICE_CONTRACTS`) are withdrawn
too; the modules KITCHEN, RECIPES, PROJECTS and CONTRACTS are untouched.

`is_implemented` is a fact about the codebase and is deliberately **not**
`is_active`, which is an administrator's choice. Conflating them would let an
administrator switch on a feature that does nothing, and would let a developer's
progress silently re-enable something a firm had turned off. It has to be
revisited when the codebase changes: `COMMISSION` outlived its flag once
(`20260903_0107`) and an administrator was refused a feature the platform had.

### Recorded, not enforced

`business_profile_id` is stamped onto records in `branches`, `inventory`,
`delivery_note`, `purchase_invoice` and others. Useful for reporting on "which
operating model produced this record"; it changes no behaviour.

### Units are not applied by the profile

A new product copies its units from a **unit set** the user chooses
(`unit_sets`, `products.unit_set_id`); with none chosen nothing is pre-filled.
`ProductService` stores exactly what it is sent. The `business_profile_uom_defaults`
table is gone. See `docs/UOM_FRAMEWORK.md`, *Unit sets*.

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

Which records show a field, and which fields are compulsory, is stated in
`category_attribute_rules`, by category code, goods type, customer group or
supplier type, and no longer by profile (backlog 89 step 5, 2026-10-08, not yet
tested by hand). The seeded shared rules are on the shared goods types:
Medicine shows `BATCH_NUMBER`, `EXPIRY_DATE` and `MANUFACTURER`; Food shows
`EXPIRY_DATE` and `SHELF_LIFE_DAYS`; Electronics shows `IMEI` and
`WARRANTY_MONTHS`. They only show the fields. A firm that wants one compulsory
adds its own rule.

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

Only for something about the **firm**. A property of a product is a product
switch or field, set by its goods type, and is not a feature.

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
4. Leave `is_implemented = false` until step 3 is real, and set it true the day
   it is.

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
industry offers, with nothing reported. (That column was removed by backlog 89
step 5; the rule that a replacing endpoint needs every column still stands.)
Anything editing a definition must send every column, `validation_rule`
included; it has no editor and is round-tripped.

The narrowing controls — `entity_type` and, then, `applicable_business_profile_id`
— were also missing from the form, so a CUSTOMER attribute or an industry-scoped
one could not be created from the desktop at all. `entity_type` and `data_type`
are dropdowns now (the profile control went with the column);
`applicable_category` is a picker over the firm's product
categories that submits the category's **code**, since an id stored there
matches no category and the definition silently never applies.

## Administration API

| Route | Who | Purpose |
| --- | --- | --- |
| `/api/v1/business-framework/profiles`, `/features`, `/modules` | platform admin | the catalogue, full CRUD |
| `…/profiles/{id}/configuration`, `…/features`, `…/modules` | platform admin | which features and modules a profile enables |
| `…/attribute-definitions`, `…/category-rules` | platform admin | the shared custom field catalogue and its shared rules (a category code or a shared goods type) |
| `…/firm-custom-fields/{field_id}/use` (PUT, `{"is_enabled": false}`) | firm administrator, `CUSTOM_FIELD_MANAGE` | switch a shared field off or on for this firm (added on 2026-10-08, not yet tested by hand) |
| `…/firms/{id}/profile` | platform admin | assign a profile to a firm |
| `…/active-features`, `…/active-modules` | any authenticated user | what *this* firm resolves to |

The two `active-*` routes are the ones a client calls; everything else is
administration. Profiles, features and modules are editable from the desktop's
administration workspace, which calls `setBusinessProfileFeatures` /
`setBusinessProfileModules` on save.

**A profile written at runtime reaches every store** (backlog 17, option 1,
2026-10-01). Creating, changing or deleting a profile saves it in the caller's
store, then writes the same row -- **the same id** -- to every other store the
registry routes to (`app/business/services/profile_replication.py`), each store
committed and audited on its own. The response's `stores` (a list for a delete)
says per store `WRITTEN` with created, updated, deleted or unchanged, or
`FAILED` with why: unprovisioned storage, an inactive firm, a store holding a
different profile under the same code (reported, never overwritten), or a
delete refused because a firm there is assigned the profile. `message` sums it
up. Firms sharing a store are named together and the store is written once.
Setting a profile's features or modules travels the same way, through the
same service method in each store -- so a store whose catalogue lacks one of
the features (one created at runtime in another store) reports `FAILED` by
name. Features and modules created at runtime are not yet copied themselves.

## Status — what is not built

Ordered by what blocks the most.

| # | Gap | Why it matters |
| --- | --- | --- |
| 1 | ~~**Only `products` reads and writes custom fields**~~ closed 2026-09-08 | Every declared entity has a value table (`20260810_0063`) and all seven now read and write it through the API: `attributes` on the write schema (replaced when sent, left alone when absent), `attributes` on the response, and `GET /business-framework/attribute-definitions/applicable?entity_type=` to tell a form which fields to offer. Products, customers, vendors, branches and warehouses carry the fields on their forms. **UOMs and tax profiles are API-only**: a unit is shared by every firm in the store, so its values are the calling firm's own and a read names the firm; neither desktop editor shows the section yet, which is the remaining gap. |
| 2 | **`require_module` is applied nowhere** | A firm whose profile disables a module can still call its endpoints. The gate is written and tested; no route uses it. |
| 3 | ~~**3 implemented features are ungated**~~ closed 2026-10-08 | `TERRITORY`, `APPROVAL_WORKFLOW` and `MULTIPLE_WAREHOUSES` were withdrawn from the catalogue by `20261008_0353`: no code enforced them and every firm already used them. |
| 4 | **`vendors.business_attributes` is an untyped JSON blob** | Unvalidated, unlinked to the catalogue, looks like this feature but is not. Should migrate onto the framework before anyone stores data in it. |
| 5 | *(closed 2026-10-08)* **UOM defaults** | Replaced by unit sets the user picks; `business_profile_uom_defaults` is gone. See `docs/UOM_FRAMEWORK.md`. |
| 6 | ~~**No allowed-values list**~~ closed 2026-09-08 | A TEXT definition may carry `validation_rule.allowed_values`, a list of fixed choices: the schema trims and deduplicates it and refuses it on any other data type, `AttributeService` refuses a value outside the list by name, the response exposes `allowed_values`, and every form renders such a field as a dropdown -- with a stored value no longer in the list kept selectable, or the field would assert and save blank. **Allowed values** on the Dynamic Attributes form is the editor, comma-separated. |
| 7 | **Line-level attributes undecided** | Needs its own design round — see below. |

Fixed on 2026-08-12: `resolve_capabilities` ignored `default_enabled`, so the
gate and `/active-features` disagreed for any profile missing a mapping row;
and `get_profile_default` ignored the profile-wide UOM row, so every seeded
industry default was unreachable. Both were two-level lookups with only one
level implemented — worth suspecting wherever a nullable scope column means
"inherit".

Also fixed on 2026-08-12: the Attribute Definitions form dropped four columns
into a full-replace update, so editing a definition wiped its description and
un-scoped it from its business profile (the column was removed by backlog 89 step 5). The lesson generalises — **a form
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
- **A feature is about the firm, never about a product.** Anything a product
  carries or tracks is a product switch filled by its goods type. Gating it on
  the profile was the two-sources-of-truth defect that backlog 89 removed.
- **A missing mapping row is not "disabled".** It means "inherit
  `default_enabled`". Any new code that resolves capabilities must apply that
  fallback, or it will disagree with `/active-features` and refuse writes the
  screen has already invited.
- **Blank is not populated.** `assert_feature_fields` ignores `None`, empty
  strings and collections, and `False`. A zero *number* is populated, because
  somebody typed it. Clearing a field is always allowed.
- **Resolve the profile through `resolve_profile_id`, never with a local
  query.** A module that reads `firm_business_profiles` itself answers None for
  an unassigned firm, where the gate answers GENERIC, and the two then disagree
  about the same firm. Both divergences are fixed: the tax engine skipped every
  profile-scoped rule for an unassigned firm, and territory stamped its
  hierarchy and nodes with no profile at all. `app/uom`, `app/tax` and
  `app/uom`, `app/tax`, `app/sales`, `app/products` and `app/inventory` all go
  through it now -- `resolve_profile_id` for the id, `resolve_profile` for the
  row -- and `test_every_module_resolves_the_same_business_profile` fails the
  build if one of them starts answering differently. `20260821_0095` fills the
  profile on the hierarchy configs, territories and beat plans the old
  resolvers left NULL, per firm store.
- **An assigned profile decides even when it is INACTIVE.** Products, inventory
  and territory each demanded `status = 'ACTIVE'` on the assignment and fell
  back to the default when it was not, while the gate went on enforcing the
  assigned one -- a form offering a field the save refuses, which is the
  disagreement this framework exists to prevent. `status` gates the *default*
  only. Deactivating a profile does not move its firms off it; reassign them.
- **A store with no default profile enforces nothing.** `resolve_capabilities`
  returns empty capabilities rather than denying everything, so an unseeded
  catalogue degrades instead of causing an outage. Do not "fix" this by raising.
- **`/active-modules` filtering in the desktop is cosmetic.** It hides menu
  entries (the modules, and the Inventory tabs that follow the goods through
  `goods_tracking`); it is not a security boundary.
- **Never hardcode industry behaviour into an entity.** Declare a feature and
  gate on it. That rule is what lets a twelfth industry be a migration.

## Related

- `docs/GOODS_TYPES.md` — goods types, and the starting set a profile hands a new firm
- `app/products/goods_type_seed.py` — the shared goods types and `PROFILE_STARTING_GOODS_TYPES`
- `app/uom/unit_set_seed.py` — the shared unit sets (a profile hands none over)
- `docs/FIRM_DOMAIN_MODEL.md` — where the profile sits among the firm's other entities, and which tier each one lives in
- `app/business/gating.py` — capability resolution and both gate shapes
- `app/business/services/attribute_service.py` — custom fields (`AttributeService.applied` is the one resolver)
- `app/business/services/field_rules.py` — what a rule may name
- `app/business/services/firm_custom_fields.py` — a firm's own fields, rules and the shared-field switch
- `app/business/services/framework_service.py` — profile administration API
- `docs/MULTI_INDUSTRY_ERP_ARCHITECTURE.md` — the original design intent
- `docs/MODULE_REVIEW_CHECKLIST.md` — the per-module review checklist

---

## Gating, and what is actually implemented

*Moved out of `CLAUDE.md` on 2026-09-15 when that file passed the 150k-character limit; brought up to date on 2026-10-08.*

- Enforce server-side with `require_feature("CODE")` / `require_module("CODE")` from `app/business/gating.py`, used exactly like `require_permission`. They are **write-only**: safe methods always pass, so enabling a gate can never hide data a firm already has. A firm with no profile resolves to the platform default (GENERIC). Those gate a whole **endpoint**, which only suits a feature that owns its own resource. Most features are optional *fields* on a resource every firm uses, so gating the endpoint would stop a firm creating a delivery note because it does not record a vehicle: for those call `assert_feature_fields(session, firm_id, feature=..., values={...})` from the service, which refuses the write only when it populates one of the named fields. Blank and unchanged always pass, and a firm with no resolvable profile is never gated — a configuration gap is not a decision. **Enforced as of 2026-10-08 (backlog 89, step 6):** only `DRUG_LICENSE`, `ATTACHMENTS` (all seven transactional modules), `VEHICLE_TRACKING` (`delivery_note`, `goods_receipt`) and `BATCH_PTR_PTS`, all fields. `COMMISSION` is the fifth catalogue row and has no check. The other seventeen features that were in the catalogue were withdrawn by `20261008_0353`: eight were what goods look like (now the product's own switches, filled by its goods type), three were enforced nowhere, and six had no code behind them. Gating makes the seeded profile assignments load-bearing: if a profile omits a feature its firms were using, they lose that field. **The catalogue lives in every firm store, not in `platform`** — migrate each firm target, and remember a firm's assignment is only visible from its own store (querying `firm_shared` makes the two dedicated-store firms look unassigned). Features and modules are toggled from the desktop administration workspace, which calls `setBusinessProfileFeatures` / `setBusinessProfileModules` on save.

- The desktop's `/active-modules` filtering is cosmetic and is *not* a security boundary — it only hides menu entries.
