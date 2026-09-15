# Configurable custom fields — the attribute framework

Moved out of `CLAUDE.md` on 2026-09-15, when that file passed the 150k-character
limit. Verbatim; the imperative half stays in `CLAUDE.md` with a pointer here.

A module gains industry-specific fields through `AttributeService`
(`app/business/services/attribute_service.py`), never by adding columns. An
`AttributeDefinition` targets an `entity_type` (`PRODUCT`, `CUSTOMER`, `VENDOR`,
…) and is optionally scoped to one business profile, so a pharmacy firm carries
fields a food firm does not.

- **The catalogue is shared; value storage is per module.** Each module owns a small table extending `AttributeValueBase` — `product_attribute_values` is the reference — which keeps a real FK to the owning record and its own indexes. The service is parameterised by that model, so there is still one implementation, one set of tests, and one form renderer.

- **A TEXT definition may carry `validation_rule.allowed_values`** (2026-09-08), the first meaning the rule column has had: a list of fixed choices, trimmed and deduplicated by `AttributeDefinitionCreate`, refused on any other data type, refused by name in `AttributeService._coerce` when a value is outside it, exposed as `allowed_values` on the response through a model property, and rendered as a dropdown by `AttributeFormField` on every form -- with a stored value no longer in the list kept selectable, the same trap the geography picker had. The Dynamic Attributes form edits it as a comma-separated **Allowed values** box and folds it into whatever else the rule holds, so the form no longer has to round-trip a rule it cannot see.

- Values live in typed `value_text` / `value_number` / `value_date` / `value_boolean` columns so list filters and reports can index and query them. Never store custom fields as JSON: a `products.category_attribute_values` blob existed until 2026-08-09 and could not be filtered.

- **To extend a new module:** add an `AttributeEntityType` member, a ~20-line table extending `AttributeValueBase` with `ENTITY_TYPE` / `OWNER_COLUMN` set, a migration, and calls to `replace_values` on save and `values_for` / `values_for_many` on read. **Customers and vendors did exactly that on 2026-09-08**, and the shape to copy is theirs rather than the product's: `AttributeValueInput` / `AttributeValueResponse` from `app/business/schemas` on the write and response models (products still carry their own copies), `replace_values` on create and **only when the field was sent** on update -- `model_fields_set` for customers, `None` for vendors, matching each module's own partial-update rule -- `AttributeService.value_rows` for the response, and one `_response` helper per router so no route answers an empty list for a record that has values. The form asks `GET /business-framework/attribute-definitions/applicable?entity_type=` for the fields to offer, resolved for the firm the way a save resolves them; the product form has its own answer in `/products/metadata`. `CustomFieldsController` and `CustomFieldsSection` in `desktop/lib/ui/workspace/custom_fields_section.dart` are the one client implementation, and a form sends `attributes` **only once the definitions arrived**: absent is "leave them alone" and an empty list is "clear them", so a form that could not read the fields must not send the empty one. Branches and warehouses followed the same afternoon, as a section at the foot of each dialog rather than a tab, since neither dialog has tabs. UOMs and tax profiles take `attributes` on the API but have no form for it -- and a unit is **shared** by every firm in the store while its values are per firm, so `value_rows` takes `firm_id` there and `_uom_response` names the calling firm; without it one firm would read another's values on the same unit.

- Read attributes for a list of records with `values_for_many`, never per row — `ProductService._products_matching_attribute` shows the pattern for filtering.
