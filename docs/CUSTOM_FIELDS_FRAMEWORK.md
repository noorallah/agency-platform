# Configurable custom fields — the attribute framework

Moved out of `CLAUDE.md` on 2026-09-15, when that file passed the 150k-character
limit. Verbatim; the imperative half stays in `CLAUDE.md` with a pointer here.

A module gains industry-specific fields through `AttributeService`
(`app/business/services/attribute_service.py`), never by adding columns. An
`AttributeDefinition` targets an `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`,
…). Which records of that sort carry it follows the **kind of record** -- a
product's goods type, a customer's group, a supplier's type -- and never the
firm's business profile (backlog 89, step 5; see *Fields by kind of record*
below).

- **A firm keeps its own fields beside the shared catalogue** (MST-8, 2026-10-03). Several firms share `firm_shared`, so `attribute_definitions` and `category_attribute_rules` carry a nullable `firm_id`: a value is that firm's own row, offered on its forms and no other's; null is the platform's shared catalogue, offered to every firm and read-only to it. `AttributeService.offered` and `rules_for` filter on it, and every other read goes through them (`applied`, `definitions_for`, `mandatory_ids`), so **any new read of the definitions must too**, or one firm's field appears on another's form. Shared rows were deliberately not copied per firm -- the values already held point at them. A code is unique per firm among live rows (`UQ_attribute_definitions_firm_code_active`) and among the shared ones (`UQ_attribute_definitions_shared_code_active`); that a firm's code also stays clear of the shared codes is a service check, which no single index can say. The firm's screen is `/business-framework/firm-custom-fields`, under `CUSTOM_FIELD_VIEW` / `CUSTOM_FIELD_MANAGE`.
- **The catalogue is shared; value storage is per module.** Each module owns a small table extending `AttributeValueBase` — `product_attribute_values` is the reference — which keeps a real FK to the owning record and its own indexes. The service is parameterised by that model, so there is still one implementation, one set of tests, and one form renderer.

- **A TEXT definition may carry `validation_rule.allowed_values`** (2026-09-08), the first meaning the rule column has had: a list of fixed choices, trimmed and deduplicated by `AttributeDefinitionCreate`, refused on any other data type, refused by name in `AttributeService._coerce` when a value is outside it, exposed as `allowed_values` on the response through a model property, and rendered as a dropdown by `AttributeFormField` on every form -- with a stored value no longer in the list kept selectable, the same trap the geography picker had. The Dynamic Attributes form edits it as a comma-separated **Allowed values** box and folds it into whatever else the rule holds, so the form no longer has to round-trip a rule it cannot see.

- Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index and query them. Never store custom fields as JSON: a `products.category_attribute_values` blob existed until 2026-08-09 and could not be filtered.

- **To extend a new module:** add an `AttributeEntityType` member, a ~20-line table extending `AttributeValueBase` with `ENTITY_TYPE` / `OWNER_COLUMN` set, a migration, and calls to `replace_values` on save and `values_for` / `values_for_many` on read. **Customers and vendors did exactly that on 2026-09-08**, and the shape to copy is theirs rather than the product's: `AttributeValueInput` / `AttributeValueResponse` from `app/business/schemas` on the write and response models (products still carry their own copies), `replace_values` on create and **only when the field was sent** on update -- `model_fields_set` for customers, `None` for vendors, matching each module's own partial-update rule -- `AttributeService.value_rows` for the response, and one `_response` helper per router so no route answers an empty list for a record that has values. The form asks `GET /business-framework/attribute-definitions/applicable?entity_type=` for the fields to offer, resolved for the firm the way a save resolves them; the product form has its own answer in `/products/metadata`. `CustomFieldsController` and `CustomFieldsSection` in `desktop/lib/ui/workspace/custom_fields_section.dart` are the one client implementation, and a form sends `attributes` **only once the definitions arrived**: absent is "leave them alone" and an empty list is "clear them", so a form that could not read the fields must not send the empty one. Branches and warehouses followed the same afternoon, as a section at the foot of each dialog rather than a tab, since neither dialog has tabs. UOMs and tax profiles take `attributes` on the API but have no form for it -- and a unit is **shared** by every firm in the store while its values are per firm, so `value_rows` takes `firm_id` there and `_uom_response` names the calling firm; without it one firm would read another's values on the same unit.

- Read attributes for a list of records with `values_for_many`, never per row — `ProductService._products_matching_attribute` shows the pattern for filtering.

- **Once a field holds values, its type and its existence are settled** (backlog 16 lifecycle guards, 2026-10-01). `update_attribute` refuses a `data_type` change while `attribute_value_count` finds a live value -- refused rather than converted, because a value left in `value_text` while reads look in `value_number` is orphaned and nothing reports it; add a field of the new type and retire the old. `delete_attribute` refuses while values exist and says to deactivate (`is_active` false) instead -- a soft delete never reaches the `RESTRICT` key on the value tables. Making a field mandatory, on the definition or through a mandatory category rule, is allowed but answers with `warning` (and `message`): up to how many records of that kind hold no value and will be refused at their next save. The count is an upper bound -- it ignores a category or a kind. The value table for an `entity_type` is found from the mapped `AttributeValueBase` subclasses, so a new module's table is counted with no list to update. The generic resource page shows a save's `data.warning` after the save.


## Fields by kind of record (backlog 89 step 5, added on 2026-10-08, not yet tested by hand)

Until 2026-10-08 a definition could name one business profile
(`applicable_business_profile_id`) and a rule a profile and a category, so a
firm on the pharmacy profile was offered *Drug licence number* on its paint
dealers and the food rules did nothing for food sold by a pharmacy-profile
firm. Both columns are dropped by `20261008_0352`. What replaced them:

**One resolver.** `AttributeService.applied(entity_type, firm_id=, category_code=, kind=)`
returns what one record may carry and what it must, from two statements plus
the switch sub-select: the fields (`offered`) and their rules (`rules_for`).
`definitions_for` and `mandatory_ids` are views of it, and `replace_values`
calls it once. `kind` is a `RecordKind(goods_type_id=, customer_group_id=,
vendor_type_id=)`; a record with no kind -- a General product, a customer in
no group, every document -- passes none.

**A rule names exactly one thing** (`category_attribute_rules`, validated on
`CategoryAttributeRuleCreate`):

| The rule names | Column | Field must be on | Effect |
| --- | --- | --- | --- |
| A product category | `category_code` | (not checked, as before) | Compulsory for a product saved in that category |
| A goods type | `goods_type_id` | `PRODUCT` | **Ties** the field to that goods type; compulsory there when `is_mandatory` |
| A customer group | `customer_group_id` | `CUSTOMER` | Ties it to that group; compulsory there when `is_mandatory` |
| A supplier type | `vendor_type_id` | `VENDOR` | Ties it to that type; compulsory there when `is_mandatory` |

- **A tied field is offered only on records of the kinds its rules name.**
  One field can have several rules (storage temperature for Medicine and for
  Food), compulsory in one and not in another. A field no rule ties is
  offered on every record of its sort, as before.
- **A rule is the firm's own or shared.** `firm_id` null is a shared rule the
  platform keeps (`/business-framework/category-attribute-rules`): it may
  name a category code or a **shared** goods type, never a customer group or
  a supplier type, which are each firm's own. A firm's administrator keeps
  the firm's rules at `/business-framework/firm-custom-field-rules` under
  `CUSTOM_FIELD_MANAGE` and may name any of the four. A firm's rule ties the
  field in that firm only.
- **One live rule per firm, field and thing named**: four partial unique
  indexes (`UQ_category_attribute_rules_goods_type_active` and its three
  siblings). A shared rule has a null `firm_id`, which no index compares, so
  `assert_rule_new` in `app/business/services/field_rules.py` is its guard;
  that module also holds what a rule may name (`assert_rule_target`) and the
  words a grid shows (`describe_rules`, answered as `applies_to`).
- **Moving a record to another kind removes nothing.** The value it holds for
  the old kind's field stays, and can still be sent back (the retained
  definitions rule); the new kind's compulsory fields are asked for at the
  next save that sends `attributes`.
- **The product is judged by the goods type it stores** (`products.goods_type_id`),
  which a later change to its category's type does not move. The product form
  is offered the fields of the type its *category* gives today
  (`/products/metadata`), so for a product whose category changed type after
  it was filed the form and the save can differ until the product is filed
  again.
- **A customer or supplier form asks once.** `GET
  /business-framework/attribute-definitions/applicable` returns every field
  the firm uses for that sort of record, `mandatory_ids` (compulsory whatever
  the kind) and `kind_rules`; `CustomFieldsController` shows a tied field
  only while the record's group or type matches one of its rules, with no
  second call when the group changes.

**A firm switches a shared field off for itself.** `firm_attribute_switches`
holds one live row per firm and field; no row means on. `PUT
/business-framework/firm-custom-fields/{field_id}/use` with `{"is_enabled":
false}` hides the field from that firm's forms and **keeps every stored
value**; on shows them again. `GET /firm-custom-fields` answers
`enabled_for_firm` per row. Only a shared field has the switch -- a firm's own
is retired with `is_active` -- and each change writes
`firm_custom_field.use_changed`.

**What the profile still does here: nothing.** §89 says a profile ticks a
starting set of fields when a firm is created. No shared field for customers,
suppliers or documents is seeded and no store held a profile-scoped field on
2026-10-08, so there is no starting set to tick and none was invented; the
migration switches a profile-scoped shared field off for each firm assigned
another profile, should a store hold one.

**What the migration did to the seeded rules.** The seven shared rules of
`20260801_0011` named a profile and the category codes `MEDICINE`, `FOOD` and
`ELECTRONICS`. They became rules on the shared goods types of the same codes,
and **show** their fields on those products without making them compulsory:
carried over as written they would have demanded an IMEI of every television
and refused a product import that gives only the category. So no field is
compulsory for a goods type until a firm (or the platform) says so in a rule.


## Documents (MST-6, 2026-10-03)

Six documents carry custom fields: quotation, sales order, delivery note, sales invoice, purchase order and purchase invoice. Each has its own value table in `app/business/models/document_attributes.py`, and every document service goes through `app/business/services/document_attributes.py` rather than calling `AttributeService` itself:

- `store` on create, and on update only when `attributes` was sent;
- `responses_for_many` inside each `*_responses` page builder, so a list reads the values once;
- `carry` / `carry_from_sources` when a document is raised from another, matching fields by **name** (a code is unique within a firm across every record, so two documents cannot share one);
- `printed` for the print services: definitions with `show_on_print` appear in the document's reference block.
