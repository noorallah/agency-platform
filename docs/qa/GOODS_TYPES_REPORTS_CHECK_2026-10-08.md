# Goods type in reports and lists (backlog 89, step 8): API check, 2026-10-08

Backend verified over HTTP; **screens not clicked**. Driven against the
running backend on branch `feat/89-goods-type-in-reports` before the merge,
on TEST01, every store on `20261008_0353` (this step has no migration).

**Outcome: TC-MAST-031, one kept script, 92 comparisons, all clean. No
finding.** Three things the data on TEST01 could not show are listed under
*Not covered*.

## How to run it again

```powershell
# from the repository root, with the fixtures of the goods types round in place
backend\.venv\Scripts\python.exe docs\qa\checks\run.py goods_types tc_mast_031
```

The script (`docs/qa/checks/goods_types/tc_mast_031.py`) builds nothing and
leaves nothing: it reads what the firm holds and checks every figure against
the same report asked another way, so it holds on any data.

## What was asked, and what answered

| Step | Asked | Answer |
| --- | --- | --- |
| (a) | Sales Analysis and Purchase Analysis by `goods_type`, on every basis (billed, ordered; billed, received, ordered) | Each row reads General or the name of a goods type the firm can see; the rows add up to the grand total; the grand total and the count of documents equal the same analysis by product; by month the cells add up |
| (b) | The same analysis by product, filtered with `goods_type_id` | The grand total is that goods type's row; General is what no type claims |
| (c) | `reports/analysis/invoices` with `goods_type_id` | 200, and never more than the type's gross sales |
| (d) | Purchases by goods type | On TEST01: received -- General 21,48,392.00 and Medicine 2,016.00; ordered -- General 23,13,308.80 and Medicine 7,074.00 |
| (e) | Stock valuation, Stock ageing, Dead stock | Every item reads its own product's goods type (General where it has none); the valuation's three closing rows carry none. On TEST01: 240 General and 6 Medicine items valued |
| (f) | `GET /products` with `goods_type_id`, and with `general_goods=true` | Each lists only its own products; the count under the list matches; General and the types together are every product of the firm (726); a value that is not an id is refused, 422 |
| (g) | `goods_type` on both rows and columns | Refused, 422: "Choose a different dimension for the columns." |
| Roles | The sales user reads sales by goods type; the store user filters the product list | 200 both |

## Not covered

- **Sales of a product that has a goods type.** Every invoice and sales order
  on TEST01 is of General goods, so the sales analysis showed one row. The
  typed row is covered on the purchase side live, and for sales by
  `tests/unit/test_goods_type_in_reports.py`.
- **The screens.** The *Goods type* dimension and filter of the two analysis
  screens, the new column of the four stock reports and the Products filter
  were not clicked. `desktop/test/phase2_products_page_test.dart` covers the
  Products filter as a widget test.
- **A second firm of the SHARED store.** One firm was asked.

## Seen on the way, not a finding of this step

Three live products on TEST01 (`*-D2`) hold a goods type that has since been
deleted. They were filed by `p_deleted_category.py` before D-MST-21 was fixed
(#1359), which now refuses that delete. The reports show such a product under
the deleted type's name and the product list finds it by the type's id; the
firm's list of goods types no longer shows the type.

## Timed on PERF01

`scripts/time_routes.py`, median of three, milliseconds, before the change and
after it, the same hour on the same PC with 2.4 GB free.

| Route | Window | Before | After |
| --- | --- | --- | --- |
| `sales-invoices/reports/analysis` | year | 2,242 | 2,041 |
| `sales-invoices/reports/analysis` | month | 1,056 | 963 |
| `sales-invoices/reports/analysis/invoices` | year | 3,366 | 3,017 |
| `purchase-invoices/reports/analysis` | year | 335 to 801 | 746 to 797 |
| `purchase-invoices/reports/analysis/bills` | year | 936 | 810 |
| `inventory/reports/stock-valuation` | month | 3,140 | 2,685 |
| `inventory/reports/stock-ageing` | year | 2,118 | 2,334 |
| `inventory/reports/slow-moving` | month | 1,998 | 2,057 |
| `inventory/reports/dead-stock` | month | 2,768 | 2,048 |

Nothing moved beyond the spread between two runs of the same code: the
purchase analysis read 801 and then 398 on the unchanged code, minutes apart.
The new shapes, asked by hand for the financial year: sales by goods type
1,190 (by category 1,450), sales by goods type and month 1,478, purchases by
goods type 91 (by category 121), the product list 33, filtered to General 32,
filtered to one type 29.

**Slow before this step and still slow, not touched by it:**
`inventory/reports/stock-statement` (10.2 s for a year, 7.5 s for a month,
target 3 s), `sales-invoices/reports/analysis/invoices` for a year (3.0 to
3.4 s) and `inventory/reports/stock-valuation`, which sits on the 3 s line.
PERF01 holds no product with a goods type, so the timings above are of one
General group; a store with several types groups on the same indexed column.
