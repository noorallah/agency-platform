# Pricing, schemes, loyalty, commission and targets: compared with the market, 2026-10-06

A reading study. Nothing was run, no server was called and no code was changed.
"This product" is judged from the code and the menu on `main` (8cd6dd8f); "reachable"
means a phase 2 menu entry exists (`desktop/lib/phase2/menu_layout.dart`), not that
the screen was opened. The other tools are judged from general knowledge of them,
not from a fresh check; **"?" means not sure**, and those cells should not be quoted
to a customer without checking.

## 1. What this product already does

| Capability | Where (server) | Phase 2 screen |
| --- | --- | --- |
| Price lists: discount % by product with quantity breaks, for one customer, one territory or everyone, dated; a fixed rate per product ("Anand pays 80") | `/api/v1/price-lists`, `app/pricing` | Settings > Set up > Pricing > Price Lists |
| Price levels (Retail, Wholesale, Dealer): a price per product per level; a customer or its group sits on one | `/api/v1/price-levels` | Settings > Set up > Pricing > Price Levels |
| Standing discount % on a customer and on a customer group | `customers`, `customer_groups` | Customer form, Customer Groups |
| One ranking for every sales document: typed > offer > price list > customer rate > group rate; start price: typed > list rate > batch PTR/PTS > level > product | `app/core/utils/pricing.py` | all sales editors (no box is prefilled) |
| Batch-wise MRP, PTR, PTS; retailer / stockist class on the customer; a bill above the batch MRP is refused | `batches.ptr/.pts`, `customers.trade_class` | Receipt line, batch list, batch picker, customer form (feature `BATCH_PTR_PTS`) |
| Price revision with an effective date (selling, purchase, MRP), by hand or by file, with history | `/api/v1/products/{id}/price-revisions`, `.../price-revisions/import-file` | Product editor, price revisions section |
| Offers: % or amount off a line or the bill (with "up to" cap), buy X get free (same item), free other product, buy X get Y at a discount, combo price, free delivery, bonus loyalty points | `/api/v1/promotions`, 10 benefit types | Settings > Set up > Pricing > Promotions |
| Offer conditions: product, category, customer, group, branch, territory, route, salesman, quantity, line value, bill value, date, weekday, time, first order, days since last order | `PromotionField` | same screen |
| Offer control: dates, priority, combine or best-offer-only, cap per line, coupon codes (single and bulk, CSV), limit by number of claims (total and per customer), counted at approval, try-before-launch, copy with new dates | `/promotions/simulate`, `/copy`, `/coupons`, `/{id}/coupons/generate` | Promotions screen; Settings > Selling > Sales Stages |
| Offer reports: performance, claims, coupons; discount given by customer, salesman, product and source | `/promotions/reports/*`, `sales_invoice/services/discount_report.py` | Reports |
| Bill-level discount and freight spread onto the lines and taxed correctly | `resolve_bill_discount`, `apportion` | all sales editors |
| Free quantity on a sale line, carried order > delivery > bill, printed; "Offers" and "You saved" on the bill | `free_quantity`, `invoice_print_service.py` | sales editors, bill print |
| Selling below minimum price or below cost: warn or block, override needs a permission and a reason; near-expiry exemption | `price_floor_settings`, `SALES_PRICE_OVERRIDE` | Settings > Selling > Price Floor |
| Maximum typed discount per role; above it the document waits for a higher role | `role_discount_limits` | Settings > Selling > Discount Limits |
| Last price to this customer while billing, with "Use the last price" | backlog 55 G6 (built) | sales line editor |
| Rate typed including GST (counter bill, order, quotation) | `app/tax/services/inclusive_rate.py` | editors, Sales Stages |
| Cash discount for early payment (customer or firm terms), taken on the receipt; interest on overdue as a taxed debit note | `customers/services/payment_terms.py` | Record Receipt (screen not checked for this study) |
| Loyalty: earn per value, minimum to spend, expiry, redeem against a bill, adjust, take back on return or cancel, reports | `/api/v1/loyalty` | Settings > Set up > Pricing > Loyalty; "Use points" on a bill |
| Customer turnover rebate: slabs by customer or group, accrue, settle against the balance, statement | `/api/v1/customer-rebates` | Sell > Documents > Customer Rebates |
| Commission: by salesman or firm-wide, by product or category, on billed or collected, on value or margin, slabs, per-unit, floor, cap, target bonus; payout accrue > approve > pay with three different people | `/api/v1/commission` | Sell > Incentives > Commission |
| Targets by salesman, territory or firm, billed or collected, with achievement | `/api/v1/sales-targets` | Sell > Incentives > Targets |
| Buying side: supplier price list and standing discount, supplier catalogue, rate contracts, supplier free-goods schemes (same or other product), supplier volume rebates, gifts register with 194R | `price_lists.vendor_id`, `/rate-contracts`, `/supplier-schemes`, `/supplier-rebates` | Buy > Rate contracts, Supplier schemes, Supplier Rebates |
| Claims to the principal: schemes it funds (its share), expiry write-offs, damaged returns; settle by credit note or payment | `/api/v1/principal-claims` | Buy > Money > Principal Claims |
| Credit note without goods (rate difference, post-sale discount) reversing tax at the bill's own rate; supplier debit note the same way | `app/credit_note`, `app/debit_note` | Sell / Buy documents |

Nothing in this list is API-only as far as the menu shows.

## 2. Comparison

Y = yes, P = partly, N = no, ? = not sure. DMS = Bizom / FieldAssist (they keep no books, so GST and ledger rows are N by design).

| # | A distributor expects | This product (evidence) | Tally Prime | Marg 9+ | Busy | Zoho Books/Inv | ERPNext | DMS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Price list per customer | Y (`price_lists.customer_id`) | P (via level) | Y | Y | Y | Y | Y |
| 2 | Price list per customer group | P: group gets a level and a flat %, not a product-wise list | Y (level) | Y | Y | P | Y | Y |
| 3 | Price list per area / route | Y (`territory_id`) | N | P | P | N | Y (territory) | Y |
| 4 | Quantity-break pricing | Y (`min_quantity`) | Y | P | Y | Y (volume) | Y | Y |
| 5 | Several named price levels | Y (`price_levels`) | Y | Y (rates A-E) | Y | P | Y | Y |
| 6 | Price as MRP less %, or cost plus markup % | N: list % is off the selling price only | P | Y | Y | Y (markup/markdown) | Y (margin) | P |
| 7 | Batch-wise MRP | Y (`batches.mrp`) | P | Y | Y | N | P | N |
| 8 | PTR / PTS (pharma, FMCG) | Y (`batches.ptr/.pts`, PG-14) | N | Y | P | N | N | P |
| 9 | Free same item (10+1) | Y (`FREE_QUANTITY`, typed free qty) | P (typed) | Y | Y | N | Y | Y |
| 10 | Free other product | Y (`FREE_PRODUCT`) | P (zero value) | Y | P | N | Y | Y |
| 11 | Slab discount by quantity or bill value | Y (one offer per slab, or list breaks) | P | Y | Y | P | Y | Y |
| 12 | Combo / bundle price | Y (`COMBO_PRICE`, kits) | N | ? | P | P (bundles) | P | Y |
| 13 | Period schemes (dated) | Y (`effective_from/to`) | P | Y | Y | N | Y | Y |
| 14 | Separate trade, scheme and cash discount columns on a line; compound "10+5" | P: one line discount + bill discount, source recorded | P | Y | Y | N | P | P |
| 15 | Cash discount for early payment | Y (SEL-14) | P | Y | P | P | Y | N |
| 16 | Scheme given later by claim (period quantity of a product or brand > credit note or free goods) | P: turnover rebate on all sales only (`customer_rebates`) | N | P | ? | N | N | Y |
| 17 | Scheme budget: stop at a total value or free quantity | P: number of claims only (`max_redemptions`) | N | ? | N | N | ? | Y |
| 18 | Price change with effective date | Y (MST-2) | Y | P | P | ? | Y | Y |
| 19 | Bulk revision by % or by brand, approved | P: file import only; levels are not dated | Y (no approval) | Y | Y | P | P | Y |
| 20 | Last sale price / party-wise price memory | Y (G6) | Y | Y | Y | P | P | P |
| 21 | Below cost / below floor control | Y (`price_floor_settings`) | N | P | Y | N | Y | N |
| 22 | Discount limit and approval | Y (`role_discount_limits`) | N | ? | P | P (approval) | P | P |
| 23 | Discount and free goods printed on the bill | Y (discount, free qty, MRP, offers, You saved) | Y | Y | Y | Y | Y | n/a |
| 24 | Principal's scheme passed on and claimed back | Y for offers; N for typed free quantity (TC-INCENT-012 note) | N | Y | P | N | N | Y |
| 25 | Expiry and breakage claims on the principal | Y (`principal_claims`) | N | Y | P | N | N | P |
| 26 | Rate difference / price protection claim on stock in hand when the principal cuts a price | N | N | Y | ? | N | N | Y |
| 27 | Supplier schemes, rebates, rate contracts | Y | P | Y | P | N | P | n/a |
| 28 | Commission by product, margin, collection, slabs | Y (`commission_rules`) | N (add-ons) | P | P | N | P (flat rate) | P |
| 29 | Commission by brand / principal, or by customer | N (product or category only) | N | ? | ? | N | N | P |
| 30 | Commission payout with approval and posting | Y (`commission_payouts`) | N | N | N | N | P | N |
| 31 | Outside brokers / agents with TDS | N (backlog 87 row 22, Later) | P | P | Y | N | Y (sales partner) | N |
| 32 | Targets vs achievement by salesman / area | Y | P (budgets) | P | ? | N | Y | Y |
| 33 | Targets by brand, product, quantity or outlet count | N (money only) | N | ? | ? | N | Y (item group, qty) | Y |
| 34 | Loyalty points | Y | N | P | ? | N | Y (with tiers) | P |
| 35 | Credit note for rate difference / scheme with GST reversed | Y (`app/credit_note`) | Y | Y | Y | Y | Y | N |
| 36 | Financial credit (no GST) for a post-sale discount | Y (rebate settled as an adjustment) | P | P | P | P | P | N |
| 37 | Choice per agreement: GST credit note or financial credit | N (rebate is always without tax) | manual | manual | manual | manual | manual | N |
| 38 | Input credit reversed when stock is given as a sample/gift or written off | N (no code found) | P (manual journal) | ? | P | P | P | N |

Where this product is ahead of every accounting tool in the list: offer engine with
best-offer mode and claim limits, commission payouts with separation of duties,
principal claims with a ledger behind them, price floor with override.

## 3. The gaps, ranked

Size: S under a day, M one to three days, L more.

| # | Missing | Who, how often | Who has it | Judgement | Size and what it touches | Backlog |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Input credit reversal on samples, gifts and written-off stock** (see 4.1) | Every firm, each month it writes off or gives away stock | None automatic; all by manual journal | **Critical** by the tax rule (workaround: the CA posts it by hand) | M: inventory adjustment posting, a reversal row per issue, GSTR-3B 4(B)(1), a setting per reason | Not listed |
| 2 | **Rate difference / price protection claim**: principal cuts a price (or GST rate changes), the distributor claims the difference on stock in hand | FMCG, pharma, electronics; a few times a year, large sums | Marg, DMS | Needed | M: a fourth source in `principal_claims` (stock on a date x old less new purchase price from `product_price_revisions`), preview, print | Not listed (68 row 10 is the supplier's credit note against one bill, built as A31) |
| 3 | **Typed free quantity not in the principal claim**; supplier scheme not linked to the customer offer it funds | Agencies, every month | Marg, DMS | Needed | S-M: claim source from bill lines' `free_quantity` for the principal's products; link `supplier_schemes` to a promotion; "received vs given" report | 86 row 21 (Low); 09 QA case 012 says "not claimed yet" |
| 4 | **Scheme budget by value or free quantity**, total and per customer | Every principal-funded scheme | DMS | Needed | S: `max_benefit_amount` / `max_free_quantity` on `promotions`, checked in `RedemptionService.claim` under the lock that exists | Not listed |
| 5 | **Period scheme by product, brand or quantity** ("120 cases of brand X this quarter: 2% or 5 cases free"); rebates count all turnover in money only | Monthly or quarterly, FMCG and pharma | DMS; Marg partly | Needed | M: product / brand / category scope and a quantity basis on `customer_rebates` (and `supplier_rebates`); free-goods settlement is extra | Not listed (87 row 9 built turnover only) |
| 6 | **Dated price levels and bulk revision** by % / brand / file, with approval | Each principal price circular: monthly in FMCG and pharma | Tally, Marg, Busy | Needed (workaround: revision file for product prices; level rates edited by hand on the day) | M: `effective_from` on `product_price_levels`, a bulk "revise by %" action over products, levels and list rates, approval | 87 row 18 (Later) covers bulk; undated levels not listed |
| 7 | **Targets by brand, principal, product or quantity** | Agencies, monthly: principals set brand targets | ERPNext, DMS | Needed | M: scope and unit columns on `sales_targets`, achievement query, screen | Not listed |
| 8 | **Separate discount columns** (trade %, scheme %, cash %) and compound discounts on a line | Every bill for a firm coming from Marg or Busy | Marg, Busy | Needed (workaround: one combined line discount, cash discount on the bill or receipt, source in the discount report) | L: every sales and purchase line schema, the resolver, prints, e-invoice | Not listed |
| 9 | **Rebate settled by a GST credit note** where it was agreed before the sale (see 4.2) | Larger customers, quarterly or yearly | None automatic | Needed for some firms | S-M: settle an accrual through `app/credit_note` spread over the period's bills, instead of an adjustment | Not listed |
| 10 | **Principal settles a claim by a GST credit note**: our input credit must come down; the claim settlement carries no tax | Agencies, monthly | None automatic | Needed (workaround: a debit note against a bill, which does not settle the claim) | S-M: let a debit note name the claim it settles | Not listed |
| 11 | **Price as MRP less % or cost plus markup** | FMCG and general trade without batch PTR/PTS; at setup and each revision | Marg, Busy, Zoho, ERPNext | Needed, has workaround (levels, fixed rates, PTR/PTS) | M: a basis on `price_list_items` (off selling price / off MRP / on cost) in `resolve_unit_price` | Not listed |
| 12 | **Price list for a customer group** (product-wise ladder, not only a level and a flat %) | Setup | Tally, Marg, Busy, ERPNext | Nice to have (levels cover most) | S: `customer_group_id` on `price_lists`, one more rung | Not listed |
| 13 | **Commission by brand / principal or by customer** | Monthly, some firms | DMS partly | Nice to have (category rules cover most) | S-M: two scope columns, two more rungs in the rule ranking | Not listed |
| 14 | **Brokers and outside agents**, brokerage with TDS | Some trades | Busy, ERPNext | Needed by few | M-L | 87 row 22: owner said Later |
| 15 | Loyalty tiers; claim reminders; "buy 2 more to reach the next slab" hint; "10+2" on prints | Occasional | ERPNext (tiers), DMS (hint) | Nice to have | S each | 86 row 26 (print, Low); reminders noted in 42.7 |

Already decided, not re-proposed: gift vouchers and wallet (87 row 24, skip); batch-wise
cost for the cost floor (64, parked; near-expiry exemption built as A2); field-sales
phone app (parked); commission on net sales without tax or freight (decided 09-24);
loyalty settles rather than discounts (decided). A ceiling on a positive commission
adjustment is still an open owner decision (`docs/COMMISSION_FRAMEWORK.md`).

Things I expected to be gaps and are not: PTR/PTS, price levels, fixed customer rates,
last price, below-cost control, discount limits, best-offer mode, coupon batches,
combo price, cash discount, customer rebates, principal claims, commission on margin
and on collection.

## 4. GST and ledger correctness notes

| # | Where | What the product does | What the rule expects | How sure |
| --- | --- | --- | --- | --- |
| 4.1 | Stock issued as *Given free to customer* or *Sample*, and write-offs for damage, expiry, loss (`inventory_service.py`, reasons to `PROMOTIONAL_EXPENSE` etc.) | Posts the cost to expense; I found no input credit reversal (`itc_reversals` is written only by rule 37) | CGST s.17(5)(h): no credit on goods lost, stolen, destroyed, written off, or given as gifts or free samples; the credit taken is reversed (GSTR-3B 4(B)(1)). Free goods given **with a sale under a scheme** are different: CBIC circular 92/11/2019 treats "buy one get one" as a supply at one price and keeps the credit | Fairly sure of the law; sure only by search that the code does not do it |
| 4.2 | Customer rebate (`customer_rebates`): "No tax is computed or posted"; settled by an adjustment | Safe: the firm never under-pays tax | s.15(3)(b): a discount agreed before the supply and traceable to invoices may reduce the taxable value by a s.34 credit note, if the buyer reverses its credit. The firm is allowed, not obliged, so today it pays more tax than it must. Circular 92/11/2019 allows a financial credit note with no tax, which is what is built. The September 2025 Council changes to post-sale discounts (circular 251/08/2025) should be checked with the CA before building item 9 | Sure the present treatment is permitted; not sure of the 2025 changes in detail |
| 4.3 | Line, bill and offer discounts before tax; freight inside the taxable value | As s.15(3)(a) and s.15(2)(c) expect | Correct | Sure |
| 4.4 | Free quantity and free product on a bill at nil value, outside the tax base | As circular 92/11/2019 for scheme goods | Correct for scheme goods. Not correct for a gift to a related party or with no sale behind it (Schedule I), which the product does not distinguish; rare | Fairly sure |
| 4.5 | Cash discount on the receipt: Dr Discount Allowed, tax untouched | A financial discount | Permitted; tax could be reduced by credit note where the terms were on the invoice | Sure |
| 4.6 | Loyalty: cost booked when points are earned, redemption settles the bill, full GST stands | Conservative on tax. As a provision it suits a small firm's books (AS 29 style); a company on Ind AS 115 would defer revenue instead | Acceptable; say so to a firm's auditor | Fairly sure |
| 4.7 | Principal claim: Dr Claims Receivable / Cr expense, no tax; settled by an adjustment "that touches no tax" | Fine when the principal sends a financial credit note or pays. When the principal issues a GST credit note the firm must reduce its input credit, and the claim screen has no way to say so (gap 10). Expired stock written off also falls under 4.1 unless it is returned on a tax invoice (circular 72/46/2018) | Fairly sure |
| 4.8 | Commission: Dr expense / Cr payable at approval, then payment; no TDS | Right for the firm's own staff (it is pay, handled in payroll, which is out of scope). An outside agent would need TDS under s.194H and the agent's GST; the product has no agents (gap 14) | Sure for staff |
| 4.9 | Supplier rebates and free goods with no tax and no 194R; gifts register carries 194R | CBDT circular 12/2022 excludes sales discounts, cash discounts, rebates and free goods of the same trade from 194R | Correct | Fairly sure |

Section numbers above are the Income-tax Act 1961's; the 2025 Act renumbers them.

## 5. Recommendation

Build now, in this order:

1. **Gap 4, scheme budget by value and free quantity** (S). Small, and every principal-funded scheme needs it.
2. **Gap 3 then gap 2, complete the principal claim**: typed free quantity, then the price-drop claim (M + M). This is how an agency earns; the claim document, ledger and screen already exist.
3. **Gap 1, input credit reversal on samples, gifts and write-offs** (M), after the CA confirms which reasons reverse. It is the only place found where the tax result can be wrong.
4. **Gap 6, dated price levels and bulk revision** (M). A monthly task done by hand today.
5. **Gap 5, period schemes by product, brand and quantity** on the rebate modules (M), with **gap 9** (GST credit note option) decided with the CA at the same time.
6. **Gap 7, brand-wise targets** (M), if the first agencies going live report to principals by brand.

Leave: separate discount columns (gap 8; large and touches every document, so ask the
go-live firms first whether one combined column is acceptable), MRP-formula pricing
(gap 11; PTR/PTS, levels and fixed rates cover it), group price lists, commission by
brand, loyalty tiers, brokers (owner: Later), wallets (owner: skip).

## What could not be determined

- Whether each screen in section 1 works as described: nothing was run.
- Whether a manual journal can reach GSTR-3B table 4(B), which would be the present workaround for 4.1.
- The "?" cells in section 2, and Marg's and Busy's commission and target features in general.
- Whether the September 2025 GST changes on post-sale discounts are in force as described.
- `docs/BACKLOG.md` was read by section headings, keyword search and sections 42, 55, 59-61, 64, 67, 75, 78, 86 and 87 in full, not line by line through all 6,100 lines; `docs/OWNER_DECISIONS.md` by keyword.
