# Tax Framework

How the system decides what tax a document line carries, and why it is
configuration rather than code.

Verified against the running backend and the seeded `WHOLE01` firm on
2026-08-11. Every number below was produced by
`POST /api/v1/tax-framework/simulate`, not written from memory.

## The idea

Four things, in a line:

```
tax system  ──has──▶  components   (CGST, SGST, IGST, CESS)
     │
     └──────────────▶  profiles    ──hold──▶ profile components (the rates)
                          ▲
                          │
                       rules ──decide which profile a transaction actually uses
```

- A **tax system** is the regime for a country — GST, VAT. It owns the
  components that regime can levy.
- A **profile** is what a product points at: "an 18% GST good". It selects
  components from its system and gives each one a rate.
- A **rule** looks at the transaction and can change that decision — the same
  product bills differently inside the state, across states, and on export.

**What decides the money is the profile component's `percentage`**, not the
component's. The component's own percentage is only the default the form offers
when you build a profile.

## The tables

```
                          firm store (one per firm)
  ┌───────────────┐        ┌────────────────────┐
  │  tax_systems  │───────▶│   tax_components   │  code, percentage (default),
  └───────┬───────┘        └─────────┬──────────┘  calculation_order,
          │                          │             included_in_price, recoverable
          │                          │
          ▼                          │ FK (kept, not copied)
  ┌───────────────┐        ┌─────────┴──────────────┐
  │  tax_profiles │───────▶│ tax_profile_components │  percentage  ← the rate charged
  └───────┬───────┘        └────────────────────────┘  calculation_order,
          │ group_code,                                 included_in_price, recoverable
          │ effective_from/to,
          │ is_historical
          │
          │        ┌──────────────┐      ┌──────────────────────┐
          └───────▶│  tax_rules   │─────▶│ tax_rule_conditions  │ field_key, operator, value
                   └──────┬───────┘      └──────────────────────┘
                          │              ┌──────────────────────┐
                          └─────────────▶│   tax_rule_actions   │ action_type, targets,
                                         └──────────────────────┘ percentage_override

                   ┌──────────────────────────┐
                   │ tax_rule_execution_logs  │  every evaluation, with reasons
                   └──────────────────────────┘
```

All of it is firm-owned, so it lives in each firm's own store — never in
`platform`.

## What a profile actually holds

A profile holds a **subset** of its system's components — one
`TaxProfileComponent` row per component it uses. There is no "all components
present, some switched off": a profile that does not name `IGST` has no `IGST`
row at all. `_create_profile` in
`backend/app/tax/services/tax_framework_service.py` writes exactly the
components the payload lists, and the unique constraint
`UQ_tax_profile_components_profile_component` allows each at most once.

The seeded firm shows the pattern — eight profiles, each holding one or two
components:

| Profile | Components |
| --- | --- |
| `GST_18_LOCAL` | CGST 9, SGST 9 |
| `GST_18_INTERSTATE` | IGST 18 |
| `GST_5_LOCAL` | CGST 2.5, SGST 2.5 |
| `EXEMPT` | *(none)* |

It is a **reference with overrides**, not a copy. The row keeps a real FK to
`tax_component_id`; what it copies at creation are defaults (`label`,
`short_label`), and what it owns are the four values that decide money:

| Field | Meaning |
| --- | --- |
| `percentage` | the rate charged for this profile |
| `calculation_order` | the order components are applied in |
| `included_in_price` | the price already contains this tax |
| `recoverable` | input tax the firm can reclaim |

`included_in_price` is the one people miss. A ₹110 line carrying an inclusive
10% component is **not** invoiced at ₹121: the tax is extracted, reported in
`inclusive_tax_amount`, and contributes **nothing** to `total_tax_amount`. That
is how MRP pricing works, and it is pinned by
`tests/unit/test_tax_framework.py::test_tax_inside_the_price_is_extracted_not_added`.

## Rates that change

A rate change never edits a profile. It creates a **new profile in the same
group**, and the old one is closed off:

| | `code` | `group_code` | `effective_from` | `effective_to` | `is_historical` |
| --- | --- | --- | --- | --- | --- |
| old | `GST_18_LOCAL` | `GST_LOCAL` | 2025-04-01 | 2026-09-30 | true |
| new | `GST_12_LOCAL` | `GST_LOCAL` | 2026-10-01 | *(null)* | false |

An invoice dated 15 September resolves to the 18% row and bills ₹180 on ₹1,000.
An invoice dated 15 October resolves to 12% and bills ₹120. **Reprinting the
September invoice in December still shows ₹180**, because resolution uses the
document's date, not today's. Editing the profile in place would make that
reprint disagree with the money actually collected and filed.

`effective_to` null means "current". The product keeps pointing at the group,
so nothing on the product master changes when a rate moves.

## Rules

A rule is firm-owned and has three parts:

**Scope** — `country_id`, `business_profile_id`, `tax_profile_id`,
`effective_from`/`effective_to`, `priority`. A null scope field means "do not
care"; a set one must equal the transaction's.

**Conditions** — `field_key operator value`, and **every one must pass**.
Conditions are AND only; there is no OR. Express alternatives with the `IN`
operator or a second rule. Operators: `EQUALS`, `NOT_EQUALS`, `IN`, `NOT_IN`,
`GREATER_THAN`, `GREATER_OR_EQUAL`, `LESS_THAN`, `LESS_OR_EQUAL`, `BETWEEN`,
`EXISTS`, `NOT_EXISTS`.

**Actions** — run in `sequence` order when the rule wins:

| Action | Effect |
| --- | --- |
| `APPLY_TAX_PROFILE` | replace the component set with another profile's |
| `APPLY_TAX_COMPONENT` | add one component |
| `OVERRIDE_COMPONENT_PERCENTAGE` | change one component's rate |
| `EXEMPT_TAX` | no components at all |
| `ZERO_RATED` | components stay, rates go to zero |
| `REVERSE_CHARGE` | the recipient accounts for the tax; the supplier bills none |
| `INPUT_CREDIT_ALLOWED` / `INPUT_CREDIT_BLOCKED` | flag for the ledger |

The seeded rules, as they read:

```
EXPORT_ZERO       priority 1    WHEN transaction_type EQUALS EXPORT
                                THEN APPLY_TAX_PROFILE, ZERO_RATED

INTERSTATE_GST_18 priority 12   WHEN transaction_type       EQUALS SALES_INTERSTATE
                                WHEN tax_profile_group_code EQUALS GST_18_LOCAL
                                THEN APPLY_TAX_PROFILE
```

## Evaluation order

`TaxRuleService.simulate` runs five stages, and it stops early.

**1. Build the context.** `_build_context` gathers the facts once:
`transaction_type`, `transaction_date`, `tax_profile_id`, plus
`tax_profile_group_code`, `product_category_id` and `product_type` from the
product, plus `country_id` and `business_profile_id` derived from the firm when
the caller omits them.

**2. Load candidates, deterministically.**

```sql
WHERE firm = … AND is_deleted = false AND status = 'ACTIVE'
ORDER BY priority ASC, code ASC, version_number DESC, created_at ASC
```

Lowest priority number wins. `code` breaks ties so two equal-priority rules
never swap places between runs; `version_number DESC` puts the newest version
first. The ordering is total on purpose — the same document must always produce
the same tax. `DRAFT` rules never participate.

**3. Test each rule** (`_rule_matches`), cheapest gate first: scope, then the
effective window against the **document's** date, then every condition. The
first failure rejects the rule and records why. A rule with no conditions
matches on scope alone.

**4. First match wins — and evaluation breaks.** No rule after the winner is
examined. Rules do not accumulate. This is why `EXPORT_ZERO` sits at priority 1:
an export must be decided before any interstate rule gets a chance.

**5. Apply that rule's actions** in `sequence` order.

If nothing matches, the product's own profile is used exactly as configured.

Every rule considered is recorded with its reasons, which is how you answer
"why did this line get IGST?" — visible in the desktop's **Tax rule simulator**
and persisted to `tax_rule_execution_logs`.

### Reading the priority ladder

```
1   EXPORT_ZERO             most specific, decided first
10  INTERSTATE_GST_5
11  INTERSTATE_GST_12
12  INTERSTATE_GST_18
20  EXEMPT_PROFILE
30  PURCHASE_INPUT_CREDIT   most general, last resort
```

Specific before general, with gaps so a new rule can be slotted between two
existing ones without renumbering. Give a broad rule too low a number and it
shadows every narrower rule beneath it — and because of the break, the narrower
one never appears in the decisions list at all.

## Product versus transaction

| | Lives on | Decides |
| --- | --- | --- |
| Tax profile | the product (`products.tax_profile_id`) | which components and rates normally apply |
| Tax rule | the firm | whether this transaction changes that |

No rule is attached to a product: there is no `product_id` on `tax_rules`.
Rules are evaluated **per document line** at pricing time, and nothing about the
outcome is written back to the product.

The product still *informs* matching, because its
`tax_profile_group_code`, `category_id` and `product_type` enter the context.
That is how a rule targets goods without naming one — `INTERSTATE_GST_18` fires
only for 18% goods because of its `tax_profile_group_code` condition, and 5% and
12% goods have their own rules.

One consequence: an invoice with an 18% good and a 5% good runs the ladder
twice and can match a different rule per line.

## Worked example

₹1,000 on `GST_18_LOCAL`, transaction date 2026-06-01, run against the live
backend:

| Transaction | Matched rule | Components | `total_tax_amount` |
| --- | --- | --- | --- |
| `SALES_INVOICE` | none | CGST 9% → 90, SGST 9% → 90 | 180 |
| `SALES_INTERSTATE` | `INTERSTATE_GST_18` | IGST 18% → 180 | 180 |
| `EXPORT` | `EXPORT_ZERO` | IGST 0% → 0 (`zero_rated=true`) | 0 |

Same product, same profile, same amount. The tax collected is identical in the
first two; the **split** changes, and the split is what the GST return needs.

## Traps

- **`simulate` is the calculation, not a preview.** All seven transactional
  modules call it once per line while building a document, on their own
  session, so it must never commit. Only the `/simulate` endpoint does that.
- **Write conditions against `tax_profile_group_code`, never
  `tax_profile_id`.** A profile id identifies one *version*, so a condition
  written against an id stops matching the moment a rate change creates a new
  version. The group code is stable across versions.
- **`country_id` and `business_profile_id` are derived, not sent.** No document
  supplies either. A country-scoped rule never fired on an invoice, and a
  profile-scoped one fired on five document types but not on goods receipts or
  purchase orders — so the same rule set taxed a purchase order and its invoice
  differently. Both are now filled in from the firm's own store.
- **`total_tax_amount` is only what the counterparty is billed.** Tax that is
  `included_in_price` and tax under `REVERSE_CHARGE` are reported in
  `inclusive_tax_amount` and `reverse_charge_tax_amount` and must **not** be
  added to a document total.
- **Never read the server clock.** Effective windows are judged against the
  document's date. `utc_now().date()` is the only acceptable fallback;
  `tests/unit/test_time_conventions.py` fails the build on `date.today()`.
- **`tax_rule_execution_logs` grows fastest in the system** — one row holding
  three JSON documents per document line. Nothing prunes it automatically;
  `scripts/purge_retention.py` does, across every firm store.

## Where the code is

| Concern | File |
| --- | --- |
| Tables | `backend/app/tax/models/tax_framework.py` |
| Systems, components, profiles | `backend/app/tax/services/tax_framework_service.py` |
| Rule engine, `simulate` | `backend/app/tax/services/tax_rule_service.py` |
| Schemas, enums | `backend/app/tax/schemas/tax_framework.py` |
| Tests | `backend/tests/unit/test_tax_framework.py` |
| Configuration UI | `desktop/lib/ui/tax/tax_configuration_page.dart` |
| Simulator UI | `desktop/lib/ui/tax/tax_rule_simulator_page.dart` |
