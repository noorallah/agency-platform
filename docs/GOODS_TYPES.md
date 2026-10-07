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

No new permission code. Goods types shape what a firm's records look like, as
its custom fields do, so the firm's administrator keeps both under
`CUSTOM_FIELD_MANAGE` -- held by `FIRM_ADMIN` and not by `FIRM_MANAGER`.
Reading rides on `PRODUCT_VIEW` because the category and product forms need
the list.

## How far §89 has got

| Step of §89's order | State |
| --- | --- |
| 1. The goods type, the two columns, the migration and the seeds | **Built 2026-10-08, not yet tested by hand** |
| 2. Product save and the product form | Not started: a product **stores** its type today, and its tracking switches are still the ones typed on the form |
| 3. Unit sets | Not started |
| 4. Batch and serial checks read the product | Not started: the firm's profile still decides whether batches, expiry and serial numbers may be used |
| 5. Extra fields and compulsory rules by goods type | Not started |
| 6. Menus, import, the profile clean-up, the docs | Not started |
| 7. Closing sweep | Not started |

So after step 1 a goods type groups products and is recorded on them, and
changes nothing yet about what a product may or must carry.

## Related

- `docs/BACKLOG.md` §89 -- the design, the decisions and the order of work.
- `docs/BUSINESS_PROFILE_FRAMEWORK.md` -- what a profile is for.
- `docs/CUSTOM_FIELDS_FRAMEWORK.md` -- the shared-catalogue-plus-own pattern
  goods types copy.
- `tests/unit/test_goods_types.py` -- each rule above as a test.
