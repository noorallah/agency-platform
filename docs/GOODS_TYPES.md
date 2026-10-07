# Goods types

The reference for goods types: what one is, the tables, the rules the server
keeps, and how far the build of `docs/BACKLOG.md` §89 has got. §89 holds the
design and the reasons; this file says what the code does today.

## The idea

An agency can distribute any goods, and one firm often carries several lines:
medicines, food and paint in the same books. A **goods type** says how one
line is tracked -- Medicine by batch and expiry, Paint by batch alone,
Electronics by serial number under warranty -- so each line follows its own
rules without anybody ticking switches product by product.

It is **not** `product_type`, which already means stock item, service or
bundle.

Three one-to-many steps connect a firm to a product, and the person entering
a product chooses only the category:

| From | To | Set by |
| --- | --- | --- |
| Firm | The goods types it uses | The profile's starting set, once; the firm's administrator afterwards |
| Goods type | Categories | Chosen on the category |
| Category | Products | The product takes the category's type and stores it |

**General is the absence of a type.** A category or a product whose
`goods_type_id` is null tracks nothing and requires nothing. There is no
"General" row to look up, and no product was rewritten when the column was
added.

## The tables

Both live in every firm store (`docs/TABLE_CATALOGUE.md`), beside the
products they describe.

| Table | Holds |
| --- | --- |
| `goods_types` | One line of goods: code, name, description, the five tracking switches a new product of the line starts with (`track_batch`, `track_expiry`, `track_manufacturing_date`, `track_serial`, `track_warranty`) and `is_active`. `firm_id` null is the **shared catalogue**; a value is that firm's own |
| `firm_goods_types` | One row per goods type a firm **uses**, with the firm's defaults for a new product of it: `default_hsn_sac` and `default_tax_profile_group_code` |
| `product_categories.goods_type_id` | The type a new product filed there takes |
| `products.goods_type_id` | The type the product took, stored, and indexed with the firm (`IX_products_firm_goods_type`) so a report by goods type reads the product row alone |

Why the two defaults sit on `firm_goods_types` and not on `goods_types`: a
tax group is the firm's own code, and a shared row serves every firm in the
store. The firm's row is the only place that can hold them for a shared type
and an own type alike.

Keys: one code per firm among live rows (`UQ_goods_types_firm_code_active`),
one among the shared live rows (`UQ_goods_types_shared_code_active`) -- the
service also keeps a firm's code clear of the shared ones, which no single
index can say -- and one live use row per firm and type
(`UQ_firm_goods_types_firm_type_active`).

## The shared catalogue

Seeded by migration `20261008_0350` into every store that holds products, and
by `seed_goods_types` (`app/products/goods_type_seed.py`) into a store built
from the models -- the sample-data reset calls it after it clears a store.

| Code | Name | Starts a product with |
| --- | --- | --- |
| `MEDICINE` | Medicine | batch, expiry, manufacturing date |
| `FOOD` | Food | batch, expiry, manufacturing date |
| `COSMETICS` | Cosmetics and personal care | batch, expiry, manufacturing date |
| `PAINT` | Paint | batch |
| `ELECTRONICS` | Electronics | serial number, warranty |

A firm reads these and cannot change them. A line that is not here is added
as the firm's own type.

## What a profile still does

A business profile hands a firm its **starting** goods types once, the first
time the firm is given a profile (`start_firm_goods_types`, called from
`BusinessProfileFrameworkService.assign_profile_to_firm`). After that the
profile has no say: a later change of profile adds nothing, and a type the
firm dropped stays dropped.

| Profile | Starts with |
| --- | --- |
| `PHARMACY` | Medicine |
| `FOOD`, `RESTAURANT` | Food |
| `ELECTRONICS` | Electronics |
| Every other | None: every product is General until a type is added |

Migration `20261008_0350` gave the firms that already existed the same
starting set from the profile they were on that day.

## The rules the server keeps

All in `GoodsTypeService` (`app/products/services/goods_types.py`) and the
two saves in `ProductService` that call it.

- **A firm changes only its own types.** Changing or deleting a shared one is
  refused by name. Using it, dropping it and setting its two defaults are the
  firm's.
- **A category takes only a type the firm uses**, that is live and active. A
  category save that does not mention the type leaves it alone, so a category
  whose type the firm has since dropped still saves its name.
- **A product takes the type of the category it is filed under** and stores
  it. The sub-category speaks first; a category with no type takes its
  nearest parent's; none anywhere is General. One statement, read off the
  category's `path`.
- **Changing a category's type reaches products created afterwards only.**
  Products already filed there keep the type they hold.
- **Moving a product to another category is the one thing that changes its
  type.** The product write schemas do not carry `goods_type_id`, so a client
  cannot send one.
- **A type something carries is neither dropped nor deleted.** Dropping one
  from use is refused while a live category of the firm carries it; deleting
  one of the firm's own is refused while a category or a live product does.
- **A default tax group must be one the firm has**, as on a product.
- **The type fills a new product, and only a new one.** On create
  (`GoodsTypeService.starting_values`, called from
  `ProductService.stage_product`, so the form, the copy and every import go
  through it):
  - each of the type's five switches the caller **did not name** takes the
    type's value. A switch the caller named is theirs, on or off -- `false`
    sent is a decision, not silence -- which is how one product differs from
    its line;
  - the four "must be named" rules follow their switch:
    `require_batch_on_receipt` and `require_batch_on_issue` are on when the
    type tracks batches **and** the product ends up tracking them;
    `require_serial_on_receipt` and `require_serial_on_issue` the same for
    serial numbers. The type holds no column for these. So a new medicine
    cannot be received or issued without a batch, and a medicine saved with
    batch tracking off is not left demanding one;
  - `hsn_sac` and `tax_profile_group_code` take the firm's defaults for the
    type **where the product has none**. A value sent is kept. A default tax
    group the firm has since retired is passed over, not refused;
  - General fills nothing, and `track_lot` is never filled.
  An update, a move to another category and a copy leave the product's
  switches as they are; the rule that a tracking mode is not changed under
  stock (`_assert_stock_shape_unchanged`) is unchanged.
- **The firm's business profile is no longer asked about a product's own
  fields.** The four checks `ProductService` made on save -- barcode, QR
  code, warranty, shelf life -- are gone (step 2); a firm on any profile
  records them. The batch and serial routes stopped asking the profile in
  step 4 (2026-10-08): the product's own switches decide.
- Every add, change, removal and change of use writes an audit row
  (`goods_type.created`, `.updated`, `.deleted`, `.use_changed`).

## Routes

Under `/api/v1/products`, declared before `/{product_id}`.

| Route | Does | Needs |
| --- | --- | --- |
| `GET /goods-types` | The shared types and the firm's own, each with `in_use` and the firm's defaults | `PRODUCT_VIEW` |
| `POST /goods-types` | Add one of the firm's own, in use from the start | `CUSTOM_FIELD_MANAGE` |
| `PUT /goods-types/{id}` | Change one of the firm's own; absent leaves a field alone; `If-Match` honoured | `CUSTOM_FIELD_MANAGE` |
| `PUT /goods-types/{id}/use` | Take a shared or own type into use, drop it, set its two defaults | `CUSTOM_FIELD_MANAGE` |
| `DELETE /goods-types/{id}` | Remove one of the firm's own that nothing carries | `CUSTOM_FIELD_MANAGE` |

`GET /api/v1/products/metadata` -- the call the product form already makes,
on opening and on each change of category -- carries what the form needs, so
the form makes **no call of its own for goods types**:

| Key | Holds |
| --- | --- |
| `goods_types` | Every live type the firm can see: `id`, `code`, `name`, `switches` (all nine product switches a new product of it starts with, by the product's field name, for the form to apply as they stand), `default_hsn_sac`, `default_tax_profile_group_code` (only ever a group the firm has today) |
| `goods_type_id` | The type a product filed under the `category_id` asked about takes, parents already resolved; null is General, and what an ask naming no category gets |

## The product form

`desktop/lib/ui/products/product_management_page.dart`. Added 2026-10-08,
not yet tested by hand.

- **Goods type: X** is shown read-only beside the category (*Set by the
  category*). A new product shows its category's type; a stored product the
  type it holds.
- Picking a category on a **new** product applies that type's switches and
  fills HSN and tax group -- only where the box is empty or still holds what
  the previous category's type filled, so nothing typed is overwritten.
  Opening a stored product, or a copy of one, applies nothing.
- The tracking section shows a switch only when it is on, or on in the
  product's type; **Show all tracking options** reveals the rest. A General
  product with none on reads *No tracking for this goods type.*
- Dependent fields follow their switch: shelf life and the expiry rules
  while *Track expiry* is on; the batch issue rule and the two *Require
  batch* switches while *Track batch* is on; the two *Require serial*
  switches while *Track serial* is on. Switching batch or serial off
  switches its *Require* pair off with it.
- Barcode and QR code are plain boxes, no longer disabled by the profile.
- Calls: opening a new product makes none (the page's metadata is handed
  in); each category picked is one metadata call; a stored product or a copy
  makes its one metadata call for its category. The same as before goods
  types.

No new permission code. Goods types shape what a firm's records look like, as
its custom fields do, so the firm's administrator keeps both under
`CUSTOM_FIELD_MANAGE` -- held by `FIRM_ADMIN` and not by `FIRM_MANAGER`.
Reading rides on `PRODUCT_VIEW` because the category and product forms need
the list.

## How far §89 has got

| Step of §89's order | State |
| --- | --- |
| 1. The goods type, the two columns, the migration and the seeds | **Built 2026-10-08, not yet tested by hand** |
| 2. Product save and the product form | **Built 2026-10-08, not yet tested by hand** |
| 3. Unit sets and their picker on the product form | **Built 2026-10-08, not yet tested by hand** (`docs/UOM_FRAMEWORK.md`, *Unit sets*) |
| 4. Batch and serial checks read the product | **Built 2026-10-08, not yet tested by hand.** Adding a batch, lot or serial by hand needs the product's `track_batch` / `track_lot` / `track_serial`; expiry, manufacturing and warranty fields need `track_expiry`, `track_manufacturing_date`, `track_warranty`. Existing records can always be changed or removed. A goods receipt still creates its batch. The six profile features no longer enforce anything (`docs/BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`, *What a product's switches allow*) |
| 5. Extra fields and compulsory rules by goods type | **Built 2026-10-08, not yet tested by hand.** A rule ties a field to a goods type, a customer group or a supplier type and says whether it is compulsory there; a firm switches a shared field off for itself; the two profile columns are dropped by `20261008_0352` (`docs/CUSTOM_FIELDS_FRAMEWORK.md`, *Fields by kind of record*) |
| 6. Menus, import, the profile clean-up, the docs | Not started |
| 7. Closing sweep | Not started |

So after step 4 a goods type decides how a **new** product starts, what its
form shows and which unit sets it is offered first, and the product's switches
(not the profile) decide what may be recorded on a batch or a serial number.
After step 5 its extra fields follow it too: a field a rule ties to Medicine
is offered on Medicine products and on no other, and the firm's profile is
asked nothing.

## Related

- `docs/BACKLOG.md` §89 -- the design, the decisions and the order of work.
- `docs/BUSINESS_PROFILE_FRAMEWORK.md` -- what a profile is for.
- `docs/CUSTOM_FIELDS_FRAMEWORK.md` -- the shared-catalogue-plus-own pattern
  goods types copy.
- `tests/unit/test_goods_types.py` -- each rule above as a test.
