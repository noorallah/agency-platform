# Multi-Industry Business ERP Architecture

**Status:** Architecture design  
**Scope:** Future platform enhancement; no implementation in this phase  
**Applies to:** FastAPI backend, PostgreSQL, Flutter Desktop, and all future ERP modules  
**Compatibility:** Existing Authentication, RBAC, Firm, Customer, audit, and desktop framework contracts remain unchanged

## 1. Executive Summary

Agency Platform should evolve into a configurable Business ERP Platform rather
than encode one industry's terminology and rules in its core entities.

The proposed architecture separates five concerns:

1. **Core business entities** contain only stable, cross-industry fields.
2. **Business Profiles** are versioned templates describing an industry's
   recommended modules, features, attributes, terminology, and validation.
3. **Firm Capabilities** are firm-local, versioned activation snapshots derived
   from a profile and explicit overrides.
4. **Configurable Attributes** add typed data without adding columns to core
   entities.
5. **Industry Extensions** implement behavior-heavy capabilities such as batch
   inventory, serial tracking, recipes, prescriptions, projects, and warranties.

This is a metadata-driven modular monolith, not a runtime plug-in system and not
an unrestricted entity-attribute-value database. Metadata controls composition;
typed domain services remain authoritative for behavior, transactions,
authorization, and invariants.

## 2. Architectural Principles

1. **Generic core, explicit extensions.** Put universally meaningful data in
   core tables and industry behavior in bounded extensions.
2. **Firm context is mandatory.** Effective configuration, data, validation,
   and module availability are resolved for the active firm.
3. **Profiles are templates, not mutable global state.** A profile update must
   not silently alter a live firm's behavior.
4. **Configuration is versioned and auditable.** Every activation and override
   has an effective version and mutation history.
5. **Capabilities do not grant authority.** Access requires the intersection of
   profile/module enablement, licensing, firm membership, and RBAC permission.
6. **Metadata describes fields; services enforce behavior.** Dynamic attributes
   may express requiredness and value constraints, but do not replace domain
   services for stock, finance, manufacturing, or compliance.
7. **Fail closed.** Unknown profiles, invalid configuration, missing schemas, or
   incompatible versions disable the affected capability rather than guessing.
8. **Stable identifiers over display labels.** Codes are immutable integration
   keys; labels and terminology are localizable presentation metadata.
9. **No per-industry forks.** Medical, food, garments, and other profiles use
   the same deployable application.
10. **Backward-compatible evolution.** Existing firms begin with a Generic
    Trading profile that preserves current behavior.

## 3. Logical Architecture

```text
+--------------------------------------------------------------------------+
| Flutter Desktop                                                          |
| Shell -> Effective Module Manifest -> Metadata Forms -> Shared Workspaces |
+------------------------------------+-------------------------------------+
                                     |
                              REST / OpenAPI
                                     |
+------------------------------------v-------------------------------------+
| FastAPI Application                                                      |
|                                                                          |
| Identity/RBAC | Firm Context | Capability Resolver | Schema/Policy API    |
|                                                                          |
| Core Domains       Extension Domains           Cross-Cutting Services     |
| Product            Batch/Lot                   Audit                      |
| Category           Serial/IMEI                 Validation                 |
| Unit/Tax           Recipe/BOM                  Configuration Cache        |
| Pricing            Warranty                    Import/Export              |
|                    Medical Compliance          Search/Reporting           |
|                    Projects/Service                                       |
+------------------------------------+-------------------------------------+
                                     |
+------------------------------------v-------------------------------------+
| PostgreSQL                                                               |
| Core tables | Profile metadata | Typed attributes | Extension tables      |
+--------------------------------------------------------------------------+
```

The application remains a modular monolith. Each bounded context exposes
application services and repository interfaces. FastAPI routers are adapters;
SQLAlchemy models are persistence details; Flutter consumes server-provided
effective manifests and schemas.

## 4. Business Profile Architecture

### 4.1 Concepts

**Business Profile Template**

A platform-owned, versioned definition for a business archetype, such as
Medical, Restaurant, Garments, Service, or Generic Trading. It contains
recommended capabilities and metadata, but no firm data.

**Firm Profile Activation**

An immutable snapshot linking a firm to one profile version. It records the
effective modules, feature configuration, terminology, and attribute policies
at activation time.

**Firm Override**

An explicit, auditable difference from the activated profile. Overrides are
allowed only where a feature definition declares itself configurable.

**Custom Profile**

A firm-local profile derived from Generic Trading or another compatible
template. It uses registered modules, features, and attributes only; it cannot
inject executable code.

### 4.2 Profile Lifecycle

```text
DRAFT -> PUBLISHED -> DEPRECATED -> RETIRED
```

- Published versions are immutable.
- Editing a profile creates a new version.
- Existing firm activations remain pinned to their current version.
- Upgrading a firm is an explicit plan/apply operation with compatibility
  validation and an audit event.
- A profile cannot be hard-deleted while referenced.

### 4.3 Resolution Precedence

The effective firm configuration is resolved in this order:

```text
Platform defaults
  < Published profile version
  < Firm activation snapshot
  < Allowed firm overrides
  < Temporary operational state (for example, license suspension)
```

Temporary operational state may disable a capability but may never enable one
that is absent from the activation.

### 4.4 Firm Assignment

Each active firm has exactly one active Business Profile activation. A future
profile change does not mutate historical documents. Transactions record the
relevant configuration/schema version where interpretation may change.

Recommended initial profiles:

- `GENERIC_TRADING`
- `AGENCY`
- `MEDICAL`
- `FOOD`
- `RESTAURANT`
- `GARMENTS`
- `ELECTRONICS`
- `MANUFACTURING`
- `SERVICE`
- `CONSTRUCTION`
- `WHOLESALE`
- `RETAIL`
- `CUSTOM`

Profiles may include classifications and tags, but inheritance should be
limited to one parent. Deep or multiple inheritance makes effective behavior
unpredictable; composition through capabilities is preferred.

### 4.5 Version Vocabulary

Version identifiers have distinct responsibilities:

| Identifier | Changes when | Purpose |
| --- | --- | --- |
| Profile version | A published template changes | Pins the platform-authored profile definition |
| Activation ID | A firm applies or rolls back a profile | Identifies one immutable activation snapshot |
| Firm configuration version | An activation or allowed override changes | Monotonic cache key and optimistic concurrency token |
| Attribute definition version | An attribute contract changes | Interprets stored attribute values |
| Category schema version | A category hierarchy or rule changes | Invalidates effective category schemas |
| Effective schema ETag | Any contributing version changes | Identifies the compiled form and validation contract |
| Policy snapshot ID | Effective rules are compiled for an operation | Explains historical transaction validation |

The effective schema ETag is a deterministic fingerprint of the firm
configuration version, relevant category schema version, extension contract
versions, and referenced attribute definition versions. It is the value sent
by clients on schema-dependent writes. Products retain the ETag used for their
last schema-validated write; historical operational documents retain the
policy snapshot ID that governed posting. No generic, unqualified
`schema_version` is used across these boundaries.

## 5. Feature Flag and Capability Architecture

### 5.1 Capability Registry

Every configurable feature is registered centrally:

```text
CapabilityDefinition
  code: INVENTORY.BATCH_TRACKING
  kind: BOOLEAN | ENUM | NUMBER | STRING | OBJECT
  scope: FIRM | CATEGORY | PRODUCT | LOCATION
  default_value
  configuration_schema
  dependencies
  conflicts
  required_module
  minimum_platform_version
  overridable
```

Examples:

- `INVENTORY.BATCH_TRACKING`
- `INVENTORY.EXPIRY_TRACKING`
- `INVENTORY.SERIAL_TRACKING`
- `INVENTORY.IMEI_TRACKING`
- `PRODUCT.WARRANTY`
- `MANUFACTURING.RECIPE`
- `MEDICAL.DRUG_LICENSE`
- `MEDICAL.PRESCRIPTION_REQUIRED`
- `SALES.COMMISSION`
- `SALES.TERRITORY`
- `SERVICE.PROJECTS`

Capabilities use namespaced immutable codes. A boolean flag answers only
whether behavior exists; structured configuration belongs in a validated
configuration value, for example:

```json
{
  "capability": "INVENTORY.EXPIRY_TRACKING",
  "enabled": true,
  "configuration": {
    "minimum_remaining_shelf_life_days": 90,
    "sale_strategy": "FEFO",
    "allow_expired_sale": false
  }
}
```

### 5.2 Dependency Rules

The resolver validates dependency graphs when publishing and activating:

- IMEI tracking requires serial tracking.
- Expiry tracking generally requires batch/lot tracking.
- Recipe management requires the Kitchen or Manufacturing module.
- Drug Register requires Medical Compliance and Inventory.
- Table Management requires Restaurant Operations.

Cycles are prohibited. Conflicting capabilities produce an activation error,
not last-write-wins behavior.

### 5.3 Effective Capability Service

All consumers use one `CapabilityResolver` interface:

```text
resolve(firm_id, capability_code, resource_context?) -> EffectiveCapability
manifest(firm_id, user_id) -> EffectiveFirmManifest
```

The manifest contains only effective, user-visible capabilities. Resolution is
cached by `(firm_id, firm_configuration_version)`. Every committed
configuration change increments that version, so all workers and replicas
naturally move to a new cache key; old keys expire by bounded TTL. An optional
cross-process invalidation event accelerates eviction but is not required for
correctness.

Resource-scoped configuration uses this default precedence:

```text
Firm < Category < Product < Location
```

Only scopes declared by the capability are considered. Definitions may publish
a different precedence when domain semantics require it, but publishing fails
if overlapping scopes have no deterministic rule. A more specific value may
override only properties marked overridable and may not bypass dependencies,
conflicts, licensing, or authorization.

Feature checks must not be scattered as raw string comparisons. Domain services
depend on the resolver abstraction; HTTP and Flutter use serialized manifests.

## 6. Module Enablement Strategy

### 6.1 Module Registry

Modules are registered independently from profiles:

```text
ModuleDefinition
  code
  API version
  navigation metadata
  required permissions
  required capabilities
  dependencies
  lifecycle state
```

Examples include `CUSTOMERS`, `PRODUCTS`, `INVENTORY`, `SALES`, `PURCHASE`,
`ACCOUNTING`, `RECIPES`, `KITCHEN`, `PROJECTS`, and `DRUG_REGISTER`.

A module is available only when:

```text
registered by platform
AND enabled by effective firm profile
AND enabled by license/edition
AND dependencies are satisfied
AND user has required RBAC permission
AND firm membership is valid
```

No condition can bypass another. Profile enablement is product configuration,
not authorization.

### 6.2 Navigation

The backend returns an effective module manifest ordered by stable module
metadata. Flutter maps manifest codes to registered screen factories. Unknown
codes are ignored and reported; they must not crash the shell.

The current permission-driven `ModuleCatalog` evolves into:

- a static registry of installed Flutter module factories;
- a server-provided effective manifest;
- a composition service intersecting both.

Existing navigation layout remains unchanged.

## 7. Core Product and Extension Strategy

### 7.1 Core Product

The future `products` table contains only stable fields:

- UUID
- Firm ID
- Product code
- Name and display name
- Description
- Product kind (`GOODS`, `SERVICE`, `COMPOSITE`)
- Category ID
- Base unit ID
- Primary barcode, when one is sufficient
- Default purchase price
- Default sales price
- Tax classification/GST
- HSN/SAC
- Status
- Shared audit, version, and soft-delete fields
- Active product schema version

Prices, barcodes, units, and taxes may later become dedicated core child tables
when their multiplicity requires it. Industry fields never become nullable
columns on `products`.

### 7.2 Three Extension Mechanisms

Use the least powerful mechanism that correctly models the requirement:

| Mechanism | Use | Examples |
| --- | --- | --- |
| Configurable attribute | Descriptive typed value with metadata validation | color, material, voltage, duration |
| Core child entity | Cross-industry repeating structure | barcodes, alternate units, price lists |
| Industry extension aggregate | Behavior, lifecycle, transactions, or strong invariants | batches, serials, recipes, warranties, prescriptions |

An attribute is not appropriate when the value:

- has its own lifecycle or permissions;
- participates in stock quantity or accounting;
- needs multiple rows per product;
- is referenced by transactions;
- requires relational integrity;
- has high-volume history;
- carries regulated workflow.

For example, “batch tracking enabled” is a capability, batch number is a
lot-level field, and actual batches are inventory extension entities. Neither
belongs as a single product attribute.

### 7.3 Extension Contracts

Each installed extension declares:

- capability and module codes;
- supported entity and attribute scopes;
- API routes and permissions;
- schema contributions;
- validators;
- lifecycle hooks;
- search/index contributions;
- desktop section factories;
- compatibility version.

Extension hooks are called through explicit interfaces, not reflection or
arbitrary scripts. Hook execution order is deterministic and transactional.
Extensions cannot commit independently inside a parent use case.

## 8. Product Attribute Framework

### 8.1 Attribute Definitions

Attribute definitions are metadata, either platform-owned or firm-owned:

```text
ProductAttributeDefinition
  id
  owner_scope: PLATFORM | FIRM
  firm_id (for firm-owned definitions)
  code
  label and description keys
  data_type
  value_scope
  unit_family
  allowed_values / option_set_id
  validation_schema
  searchable
  filterable
  sortable
  variant_axis
  sensitive
  lifecycle state
  definition_version
```

Supported data types:

- text
- long text
- integer
- decimal
- boolean
- date
- datetime
- duration
- measurement
- money
- enum
- multi-enum
- reference to an approved entity type

Supported value scopes:

- product
- variant
- category default
- lot/batch
- serial unit
- transaction line

Scope is essential. Expiry date is usually a lot value, not a product value;
IMEI is a serial-unit value, not a product value.

### 8.2 Typed Value Storage

Do not store all values as strings. The generic value store is deliberately
limited to product- and variant-scoped descriptive values. Category defaults
remain in category rules. Lot/batch, serial-unit, and transaction-line values
are owned by their extension aggregates because they participate in operational
lifecycles; extension schema contributors expose them through the same
effective-schema and validation contracts without placing them in the product
value table.

Use a typed scalar value table with exactly one value column populated:

```text
ProductAttributeValue
  firm_id
  product_id
  variant_id (nullable)
  attribute_definition_id
  definition_version
  value_text
  value_integer
  value_decimal
  value_boolean
  value_date
  value_datetime
  value_unit_id
  value_currency_code
  value_json (only for validated composite types)
```

Database check constraints enforce one matching value column. Unique constraints
enforce one scalar value per product/variant and attribute. PostgreSQL uses one
partial unique index for product values (`variant_id IS NULL`) and another for
variant values (`variant_id IS NOT NULL`), avoiding nullable-key uniqueness
semantics. Enum values use foreign keys to option tables rather than
unvalidated text. Measurement and money definitions declare the permitted unit
family or currency policy; each stored value carries the selected unit or
currency when it is not fixed by the definition.

Multi-enum values use a separate `ProductAttributeOptionValue` link table with
the same product/variant identity and an `attribute_option_id`. Its unique
indexes prevent duplicate option selections but permit multiple options for one
attribute.

Shared indexes begin with firm and attribute identifiers. Multi-attribute
filters use bounded self-joins generated from whitelisted definitions. At
larger scale, approved hot attributes may be promoted to concurrently-created
partial indexes or maintained read models. Index promotion has per-table
budgets, operational review, and rollback; application traffic never performs
ad hoc DDL.

### 8.3 JSONB Boundary

JSONB is appropriate for:

- immutable published metadata schemas;
- capability configuration documents;
- validated composite attribute values;
- audit snapshots.

JSONB is not the canonical store for frequently filtered scalar product values,
stock quantities, serial numbers, batches, prices, or financial values.

### 8.4 Schema Versioning

Published attribute definitions are immutable. Changes produce a new version.
Products retain the definition version used for stored values. Compatible
changes may be migrated automatically; incompatible changes require a preview,
mapping, and explicit migration job. The version relationships and client
concurrency contract follow Section 4.5.

## 9. Category Attribute Rules

Categories compose attribute policies without copying definitions:

```text
CategoryAttributeRule
  firm_id
  category_id
  attribute_definition_id
  usage: REQUIRED | OPTIONAL | HIDDEN | READ_ONLY | DEFAULTED
  default_value
  value_scope
  validation_overrides
  display_group
  display_order
  effective dates
```

### 9.1 Rule Precedence

```text
Attribute definition defaults
  < Business profile rule
  < Category rule inherited from ancestors
  < Direct category rule
  < Explicit product-kind rule
```

A firm override may strengthen a rule (optional to required) when permitted. It
may weaken a compliance rule only if the profile explicitly marks it
overridable.

### 9.2 Category Inheritance

- Categories form a tree with a bounded depth.
- Child categories inherit parent rules.
- Direct child rules may override only declared overridable properties.
- The effective rule set is materialized or cached by category version.
- Cycles are prevented by service validation and database-safe hierarchy logic.

Example:

```text
Medical
  -> Medicine: BATCH required, MANUFACTURER required
      -> Schedule Drug: PRESCRIPTION_REQUIRED fixed true
Food
  -> Perishable: MANUFACTURED_DATE and EXPIRY_DATE required at lot scope
Electronics
  -> Mobile Phone: WARRANTY required, IMEI required at serial scope
```

## 10. Validation Architecture

### 10.1 Validation Layers

1. **Schema validation:** transport shape, types, lengths, and formats.
2. **Configuration validation:** profile, feature, category, and attribute
   definitions are internally consistent.
3. **Effective policy validation:** required/hidden/read-only rules for the
   active firm, category, product kind, and operation.
4. **Domain validation:** behavioral invariants in extension services.
5. **Database constraints:** concurrency-safe uniqueness and referential rules.

Flutter performs guidance validation using the same effective schema, but the
backend is authoritative.

### 10.2 Policy Model

Rules are declarative and restricted:

```text
ValidationRule
  code
  target entity and field/attribute
  operations: CREATE | UPDATE | POST | ISSUE | SELL
  condition expression
  constraint
  severity: ERROR | WARNING
  message key
  source profile/version
```

Use a safe, bounded expression DSL or JSON rule model. Never evaluate Python,
SQL, Dart, or user-supplied scripts. Supported predicates should include only
approved operations such as equality, membership, presence, numeric/date
comparison, and capability checks.

Examples:

```text
IF capability(INVENTORY.EXPIRY_TRACKING)
AND category_rule(EXPIRY_DATE) = REQUIRED
THEN lot.expiry_date IS REQUIRED

IF product.kind = SERVICE
THEN inventory_tracking MUST BE false

IF capability(MEDICAL.PRESCRIPTION_REQUIRED)
AND product.schedule_drug = true
THEN sale.prescription_id IS REQUIRED
```

### 10.3 Compiled Policy

The backend compiles effective rules into an immutable policy snapshot keyed by
firm and configuration version. APIs and Flutter receive a projection of this
snapshot. Validation responses use stable rule and field codes:

```json
{
  "field": "attributes.expiry_date",
  "rule": "MEDICAL.EXPIRY_REQUIRED",
  "message": "Expiry date is required.",
  "severity": "error"
}
```

Warnings require explicit acknowledgement where policy allows; errors block the
transaction.

## 11. Future Database Design

Recommended future tables:

### Profile and Capability Metadata

- `business_profiles`
- `business_profile_versions`
- `profile_modules`
- `capability_definitions`
- `profile_capabilities`
- `firm_profile_activations`
- `firm_capability_overrides`
- `module_definitions`
- `profile_validation_rules`
- `configuration_change_sets`

### Product Core

- `products`
- `product_categories`
- `units`
- `product_units`
- `product_barcodes`
- `product_prices`
- `product_variants`

### Attributes

- `attribute_definitions`
- `attribute_definition_versions`
- `attribute_option_sets`
- `attribute_options`
- `category_attribute_rules`
- `product_attribute_values`
- `product_attribute_option_values`

### Industry Extensions

- `inventory_lots` and `inventory_lot_attributes`
- `serialized_inventory_units` and `serialized_inventory_unit_attributes`
- transaction-line extension tables where line-scoped metadata is required
- `warranty_policies` and `warranty_registrations`
- `recipes`, `recipe_versions`, and `recipe_lines`
- `medical_product_profiles`
- `prescriptions` and `prescription_lines`
- `projects`, `contracts`, and `time_entries`
- `commission_plans` and `territories`

Every firm-owned table includes `firm_id`, shared audit columns, soft-delete
state where appropriate, and indexes beginning with the firm key. Child rows
must not rely solely on the parent's firm scope for query safety when they are
queried independently; include or derive a constrained firm key.

### 11.1 Isolation

Application services continue to enforce active membership and firm scope.
PostgreSQL Row-Level Security may be added as defense in depth after connection
pooling and background-job context are designed for it; it is not a substitute
for service-level authorization.

### 11.2 Audit and History

Configuration publishing, activation, upgrade, override, and rollback emit
shared audit events. Published profile/schema documents are immutable.
Operational documents record relevant policy versions so historical behavior
remains explainable.

## 12. API Strategy

### 12.1 Configuration APIs

Future versioned endpoints:

```text
GET  /api/v1/business-profiles
GET  /api/v1/business-profiles/{code}/versions/{version}
POST /api/v1/business-profiles/{code}/versions
POST /api/v1/business-profiles/{code}/versions/{version}/publish

GET  /api/v1/firms/{firm_id}/profile
POST /api/v1/firms/{firm_id}/profile/plan
POST /api/v1/firms/{firm_id}/profile/apply
GET  /api/v1/firms/{firm_id}/capabilities
PUT  /api/v1/firms/{firm_id}/capability-overrides/{code}

GET  /api/v1/me/firm-manifest
GET  /api/v1/schemas/products/effective
GET  /api/v1/categories/{category_id}/attribute-schema
```

`plan` returns changes, warnings, blocking incompatibilities, required data
migrations, and affected modules without modifying state. `apply` requires the
planned version or ETag to prevent stale configuration changes.

### 12.2 Product APIs

Future product APIs accept a stable core plus an attribute bag:

```json
{
  "core": {
    "code": "MED-001",
    "name": "Example Medicine",
    "kind": "GOODS",
    "category_id": "...",
    "base_unit_id": "...",
    "sales_price": "125.00"
  },
  "attributes": {
    "medical.manufacturer": "Example Labs",
    "medical.composition": "..."
  },
  "effective_schema_etag": "\"product-schema-c641...\""
}
```

Lot, serial, warranty, and recipe data use dedicated extension endpoints and
contracts. They are not embedded in the product attribute bag.

### 12.3 Contract Rules

- Existing response envelopes, pagination, errors, request IDs, and active-firm
  headers remain standard.
- Configuration responses carry `ETag` and version identifiers.
- Mutation requests carry expected entity/configuration versions.
- Attribute errors use stable attribute codes and JSON paths.
- Unknown or disabled attributes are rejected, never silently discarded.
- Import first validates against a pinned schema version, produces a preview,
  then applies atomically or through an auditable background job.
- OpenAPI documents stable core contracts; effective metadata endpoints
  document firm-specific composition.

## 13. Desktop UI Strategy

### 13.1 Firm Manifest Bootstrap

After authentication and active-firm selection, Flutter loads:

- effective module manifest;
- capability summary;
- terminology;
- effective schema ETag.

The manifest is cached locally for startup resilience but is never trusted for
authorization. A firm switch invalidates feature controllers, schemas, cached
queries, and selection state before rendering the new firm's modules.

### 13.2 Dynamic Forms

Add a metadata form renderer to the reusable desktop framework:

```text
EffectiveFormSchema
  sections and tabs
  fields/attributes
  widget type
  required/read-only/hidden state
  options and units
  validation guidance
  display order
  capability source
  schema version
```

The renderer maps approved data types to registered widgets. Profiles may
configure composition but cannot provide arbitrary Flutter code. Specialized
extension widgets are registered by capability code for complex editors such
as recipes, serial lists, lot allocation, or prescriptions.

Fields are hidden only when inapplicable. Existing stored values that become
hidden during a profile upgrade must be resolved by migration policy; the UI
must not silently delete them.

### 13.3 Module Composition

Future modules continue to use:

- `WorkspaceLayout` and `ManagementWorkspaceLayout`
- `WorkspaceDialog`
- shared toolbar, grid, search, filters, status, loading, and empty states
- notification and confirmation services
- context menus and keyboard shortcuts
- user preferences and theme infrastructure

Feature metadata supplies module visibility, form sections, optional columns,
filters, and summary cards. It does not redesign navigation or shared
interactions.

### 13.4 Terminology

Profiles may supply display terminology such as Product/Item, Customer/Patient,
or Warehouse/Store. Internal codes, API paths, permission codes, database names,
and analytics dimensions remain stable. Terminology is localized and
presentation-only.

## 14. Migration Strategy

### Phase 0: Architecture Contracts

- Approve capability, profile, attribute, and extension interfaces.
- Establish immutable namespaced codes and ownership rules.
- Add architecture tests preventing core modules from importing extensions.

### Phase 1: Profile Foundation

- Add profile, version, capability, activation, and override tables.
- Seed `GENERIC_TRADING` with current module behavior.
- Assign every existing firm to a pinned Generic Trading activation.
- Expose read-only effective manifest APIs.
- Keep current static navigation as a compatibility fallback.

### Phase 2: Dynamic Module Manifest

- Intersect installed modules, profile, license, and RBAC on the backend.
- Make Flutter navigation consume the manifest.
- Add configuration caching, ETags, invalidation, and audit.

### Phase 3: Attribute Metadata

- Add typed definition, option, category-rule, and value tables.
- Add effective schema and validation services.
- Add metadata-driven desktop form components.
- Do not migrate Product data because Product is not yet implemented.

### Phase 4: Core Product

- Implement the minimal core Product aggregate.
- Store configurable descriptive values through typed attributes.
- Introduce variants only where needed.
- Pin schema versions on writes.

### Phase 5: Industry Extensions

- Implement extensions incrementally behind capabilities.
- Prefer complete vertical slices: persistence, services, APIs, permissions,
  metadata contributions, Flutter composition, tests, and documentation.

### Phase 6: Profile Administration

- Add draft/publish, plan/apply, and rollback tooling.
- Provide impact reports and background migrations for incompatible changes.
- Restrict profile administration with dedicated permissions.

### Migration Safety

- All changes are additive until consumers have migrated.
- Published codes are never renamed; labels may change.
- Feature removal uses deprecation and data-impact checks.
- Profile upgrades use a dry-run plan and optimistic configuration version.
- Large attribute migrations run as resumable, idempotent jobs.
- Rollback restores the prior activation snapshot; it does not blindly reverse
  operational transactions created under the newer profile.
- Mandatory legal or safety changes are published as platform compliance
  constraints, not silent profile mutations. Affected operations fail closed
  with an upgrade-required reason until the firm applies a compatible
  activation; emergency denial can therefore take effect without
  reinterpreting historical data or silently changing the pinned profile.

## 15. Industry Examples

### 15.1 Medical / Pharmacy

**Modules:** Customers, Products, Purchase, Sales, Inventory, Batch/Expiry,
Medical Compliance, Drug Register.

**Capabilities:** batch tracking, expiry tracking, FEFO, prescription required,
drug license, schedule classification, manufacturer.

**Product attributes:** manufacturer, composition, dosage form, strength,
schedule class. Batch number, manufacturing date, and expiry are lot-scoped
extension data. Prescription is a sales workflow entity.

**Category rules:** Medicine requires manufacturer and composition; Schedule
Drug fixes prescription-required to true; perishable medicines require lot
expiry.

### 15.2 Food / Bakery / Food Manufacturing

**Modules:** Products, Purchase, Inventory, Manufacturing or Recipes, Sales,
Quality, Reports.

**Capabilities:** lot tracking, manufacturing and expiry dates, shelf life,
recipe/BOM, allergen declaration, FSSAI metadata, FEFO.

**Product attributes:** brand, net weight, allergen labels, storage condition,
FSSAI classification. Production dates and expiry remain lot-scoped. Recipes
are versioned extension aggregates.

**Category rules:** Perishable Food requires shelf-life policy and lot dates;
ingredient categories may require allergen and storage attributes.

### 15.3 Garments / Textile

**Modules:** Products, Purchase, Inventory, Sales, Variants, Reports.

**Capabilities:** variants, size/color matrices, barcode per variant, season and
collection metadata.

**Product attributes:** material, brand, fit, gender, pattern. Size and color
are variant axes backed by controlled option sets, not repeated text.

**Category rules:** Apparel requires size and color variant axes; Fabric may
require width, composition, GSM, and roll tracking.

### 15.4 Electronics / Mobile Store

**Modules:** Products, Purchase, Sales, Inventory, Serial Tracking, Warranty,
Service.

**Capabilities:** serial tracking, IMEI, warranty registration, model and
technical specifications.

**Product attributes:** brand, model, voltage, power, connectivity. Actual
serial/IMEI values are serialized inventory units. Warranty registrations are
extension records linked to sale and serial.

**Category rules:** Mobile Phone requires serial and IMEI; Appliances require a
warranty policy; accessories may disable serial tracking.

### 15.5 Service Company

**Modules:** Customers, Services, Sales, Projects, Contracts, Timesheets,
Tickets, Accounting.

**Capabilities:** inventory optional, project management, recurring contracts,
visit required, engineer required, time billing.

**Product attributes for service items:** duration, delivery mode, visit
required, skill category. Project, contract, visit, ticket, and timesheet data
are extension aggregates.

**Category rules:** On-site Service requires visit duration and skill category;
inventory tracking is prohibited for `SERVICE` product kind.

### 15.6 Agency / Distributor

**Modules:** Customers, Products, Purchase, Sales, Inventory, Commission,
Territory, Reports.

**Capabilities:** commission, territory, principal/manufacturer relationship,
sales targets, batch/expiry optional by product category.

**Product attributes:** brand, principal, pack size, market segment. Commission
plans and territories are dedicated extension entities because they have
effective dates, assignments, calculations, and audit requirements.

**Category rules:** Pharmaceutical lines may enable medical lot policies while
general merchandise remains standard trading, demonstrating that profile rules
and category rules compose within one firm.

## 16. Governance and Guardrails

### 16.1 Ownership

- Platform Architecture owns registries, contracts, and compatibility rules.
- Domain teams own extension behavior and domain schemas.
- Firm administrators choose published profiles and allowed overrides.
- End users cannot define executable validation or workflow code.

### 16.2 Prohibited Patterns

- Adding industry-specific nullable columns to core Product.
- Using profile codes directly throughout feature code.
- Treating feature flags as permissions.
- Storing all attribute values as strings or one unvalidated JSON document.
- Modeling batches, serials, recipes, or warranties as simple attributes.
- Mutating published profile or attribute versions.
- Silently enabling modules after a template update.
- Allowing UI metadata to bypass backend validation.
- Loading arbitrary server-provided Flutter widgets or scripts.

### 16.3 Testing

Future implementation requires:

- profile publication and dependency graph tests;
- effective capability resolution tests;
- firm isolation and RBAC intersection tests;
- schema compilation and rule precedence tests;
- typed attribute persistence/query tests;
- extension contract tests;
- profile upgrade plan/apply/rollback tests;
- golden manifest tests for supported industries;
- Flutter dynamic form and responsive layout tests;
- migration compatibility tests from existing firms.

## 17. Architecture Decision Summary

| Decision | Rationale |
| --- | --- |
| Versioned profile templates with firm snapshots | Predictable live behavior and safe upgrades |
| Capability composition instead of industry forks | One maintainable product supports many domains |
| Minimal core Product | Stable integrations and no nullable-column sprawl |
| Typed attribute values | Extensibility without losing validation and queryability |
| Explicit extension aggregates | Correct modeling of behavior-heavy domains |
| Category policy inheritance | Fine-grained requirements within one business profile |
| Backend-compiled effective schema | One authoritative interpretation for API and UI |
| Manifest-driven Flutter composition | Adaptive UI without redesigning the desktop shell |
| Modular monolith first | Transactional consistency and operational simplicity |
| Explicit plan/apply profile upgrades | Auditable, reversible configuration evolution |

This architecture allows new industries such as Jewellery, Agriculture,
Hospital, School, Hotel, Logistics, Transport, and Real Estate to be introduced
through registered capabilities, metadata, and bounded extensions while keeping
the shared ERP core stable.
