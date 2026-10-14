# Retail and wholesale margins on the lot: design note

**Status: design note for row L3 of `docs/CUSTOMER_BUILD_TASKS.md`, written
2026-10-15 by the unattended loop while the owner is away. Nothing in it is
built.** The owner has said to build without waiting (2026-10-12: a
requirement may reshape tables, design first, then build); the points decided
here by the usual standard are listed in section 8 for him to confirm, and
the build goes ahead on them.

It covers customer requirements PRC-1, PRC-2, PRC-3, PRC-5, CUS-5 and the
margins half of PRD-3, and builds on the lot of row L2
(`docs/design/LOT_COST_DESIGN.md`, section 7 of which says what the lot must
carry for L3).

## 1. What the owner asked (2026-10-13)

> Two margins on the purchase price, **retail** and **wholesale**. Each
> product holds both; a goods type gives a new product its starting pair.
> Each lot takes the product's pair and both can be changed on the purchase
> line, for that lot only, so every lot has a retail price and a wholesale
> price of its own, GST on top. A customer is marked Retailer or Wholesaler;
> a new bill starts with the customer's kind and ONE switch on the bill
> changes it, every line following. M13 built that switch on price levels:
> join the two, so Retail and Wholesale read the lot's two prices and the
> bill has one switch, not two. A price above the lot's MRP warns. **No
> rounding of the worked-out price** (row F3 rounds the bill instead). Cost
> and margin shown on the bill line, on screen only, to users allowed to see
> cost.

### Worked example

Item *Soap 100 g*, goods type *FMCG* (starting pair: retail 12 %, wholesale
6 %). GST 18 %, MRP 40.00.

| Step | Retail | Wholesale |
| --- | --- | --- |
| Receipt line: 100 at 28.00, 5 % discount, so 26.60 a piece before GST | | |
| Margins taken from the product (which took them from FMCG) | 12 % | 6 % |
| Worked-out price, before GST: 26.60 x 1.12 and 26.60 x 1.06 | 29.79 | 28.20 |
| With GST, to judge against the MRP: x 1.18 | 35.15 | 33.28 |
| Purchase clerk changes the retail margin on this line only to 20 % | 31.92 (37.67 with GST) | 28.20 |
| Lot LOT-...-000041 now carries | 31.92 | 28.20 |

A retail shop buying from that lot is billed 31.92 a piece plus GST; a
wholesaler 28.20 plus GST. The next receipt of the same item at 27.50 makes a
lot of its own at its own two prices; the first lot's prices do not move.

## 2. What exists today

| Piece | Where | What it does now |
| --- | --- | --- |
| The lot | `batches`, one per purchase line for a firm costing by lot (L2) | Carries MRP, `selling_price`, `ptr`, `pts`, all Numeric(18,2), before tax except MRP |
| The lot's cost | `batch_valuations.unit_cost` | Cost of one stock unit before GST |
| Price to retailer and to stockist | `ptr`, `pts` on `goods_receipt_lines` and `batches` (PG-14) | Typed on the receipt line, handed to the lot; refused unless the firm's profile has `BATCH_PTR_PTS` and the line names a printed batch; `assert_trade_rates_within_mrp` refuses a rate above the MRP and PTS above PTR |
| The customer's kind | `customers.trade_class`: `RETAILER`, `STOCKIST`, `OTHER` | `batch_trade_rate` in `backend/app/core/utils/pricing.py`: a RETAILER takes the lot's PTR, a STOCKIST its PTS |
| Price levels | `price_levels`, `product_price_levels` (SEL-9), a level on the customer or its group | A rate per product per level |
| The bill's switch | `sales_orders.price_level_id` (M13, backlog 131) | The document's level takes the customer's level's place in the ranking |
| The ranking | `UnitPriceResolver` in `backend/app/pricing/services/unit_price.py` | typed price > price list's fixed rate > batch PTR/PTS by trade class > the document's level, else the customer's > the product's selling price |
| Goods type defaults | `firm_goods_types.default_hsn_sac`, `default_tax_profile_group_code` | Filled into a new product of the type |
| The MRP ceiling | `backend/app/batch_serial/services/mrp_ceiling.py` | A sale above the MRP of a lot it ships is **refused** (legal metrology), on the order, the dispatch and the bill |
| The lot's cost on the bill line | `cost_amount` on bill lines (D-SELL-100), behind `PRODUCT_VIEW_COST_PRICE` | Sent, not shown |
| Picker rows | `_pick_group` in `backend/app/batch_serial/services/batch_serial_service.py` | Lots that agree on batch, expiry, MRP, selling price, PTR and PTS are one row |
| Batch selling price on the line | `batch_sale_settings.price_from_batch`, read by the sales screens | The screen fills a line's price from the chosen batch's `selling_price` |

So the two prices per lot and the customer's two kinds **already exist** as
PTR and PTS: a retail shop is what the pharma trade calls a retailer, and a
wholesaler buys at the price to stockist, which is the lower of the two and
already held at or below PTR. What is missing is the margins that work the
two prices out, the reach beyond pharma firms, and one switch on the bill
instead of two (the trade class and M13's level).

## 3. The design

### 3.1 Retail is PTR, wholesale is PTS: no new price columns

The lot's **retail price is `ptr`** and its **wholesale price is `pts`**.
Section 7 of the lot note proposed retail as `selling_price` and wholesale as
`ptr`; that would have put a retail shop (trade class RETAILER, which today
takes PTR) on the wholesale price. Mapping onto the existing pair keeps every
rule already proved on it: PTS at or below PTR, both before tax, both on the
lot, both in the picker's group key, both reaching a line through
`batch_trade_rate`.

`selling_price` stays what it is: the price to anybody who is neither, the
counter customer, and what `price_from_batch` fills.

**Labels follow the firm's profile.** A firm whose profile has
`BATCH_PTR_PTS` (pharma) sees *PTR* and *PTS* and *Retailer* and *Stockist*
as today; every other firm sees *Retail price*, *Wholesale price*,
*Retailer* and *Wholesaler*. One pair of columns, two sets of words.

### 3.2 Where the margins live

| Column | Table | Meaning |
| --- | --- | --- |
| `retail_margin_percent`, `wholesale_margin_percent` | `firm_goods_types` | The starting pair for a new product of the type. Null is "no margin set" |
| `retail_margin_percent`, `wholesale_margin_percent` | `products` | The product's pair. Filled from its goods type when the product is made and the person gives none; never written over afterwards, as `default_hsn_sac` is |
| `retail_margin_percent`, `wholesale_margin_percent` | `goods_receipt_lines` | The pair this line used: the product's unless changed on the line |
| `retail_margin_percent`, `wholesale_margin_percent` | `batches` | The pair the lot was priced at, kept so the lot's page can say how its prices were reached |

All Numeric(9,4), nullable, at or above zero and below 1,000. One migration,
idempotent, per store; nothing backfilled (a product with no pair works out
no price, section 3.4).

### 3.3 How a price is worked out

- **On the purchase price before GST:** the receipt line's net rate per stock
  unit, after its own discounts and its share of a bill-level discount, before
  tax and before freight and landed costs. It is what the clerk sees on the
  line, and it is fixed when the lot is made.
- **A margin on cost (mark-up), not on the selling price:** price = cost x
  (1 + margin / 100). The owner's words are "margin on the purchase price";
  Marg and Busy work the sale rate this way.
- **Kept to the paisa, never rounded further.** The columns hold two places;
  the worked-out figure is quantized half up to the paisa and nothing else.
  Rounding to the rupee is the bill's (row F3), not the price's.
- **Before GST.** The lot's prices are before tax, as every rate in the
  ranking is; GST goes on top on the bill.
- **Worked out once.** A supplier's bill at another rate, or a landed cost,
  corrects the lot's cost (L2 step 8) and does **not** re-price the lot: a
  price the firm may already have quoted does not move behind its back. The
  lot's page can change both prices by hand (section 3.6).

### 3.4 On the purchase line

The receipt line shows, beside the rate, **two margins and the two prices
they give**, for a firm costing by lot:

- The margins start at the product's pair. Changing one re-works its price;
  typing a price instead keeps it and works the margin back from it (two
  places). Either is for this line only, so for this lot only.
- A line sends either a margin or a price for each kind, or neither. The
  server works out whatever was not sent, from the line's net rate, and
  stores both the margins and the prices on the line and on the lot.
- A product with no pair and no price typed gives the lot no price of that
  kind, and a sale from it falls through the ranking to the level and the
  product's own price, as today.
- **Above the MRP warns.** Where a worked-out or typed price **with GST**
  is above the lot's MRP, the line carries a warning naming the price and the
  MRP, and the screen shows it in place with the price that would sit exactly
  at the MRP. It does not stop the receipt: the sale above MRP is still
  refused by the MRP ceiling, so nothing above it can be billed. A price
  **before GST** above the MRP stays refused, as now: no tax rate makes that
  lawful, so it is a typing mistake.
- The `BATCH_PTR_PTS` gate and the "PTR needs a printed batch" refusal
  apply to a firm on Average only. A firm costing by lot has a lot on every
  stocked line, printed batch or not, and its two prices are a feature of
  costing by lot, not of the pharma profile.

The other places a lot is made take their prices as follows:

| Source | Prices |
| --- | --- |
| Opening stock line | Typed PTR and PTS as now; else worked from the product's pair on the line's cost |
| Stock found at a count (`ADJUSTMENT`) | Copied from the lot whose cost it takes (the newest), else worked from the pair on the cost used |
| Repack output (`REPACK`) | Worked from the output product's pair on the value used |
| Switch-over (`CARRIED_FORWARD`) | The batch's own PTR and PTS as they stand; nothing is worked out for lots already made |

### 3.5 One switch on the bill

**The bill's kind is its price level.** Each firm costing by lot gets two
reserved price levels, **RETAIL** and **WHOLESALE**, made when it switches to
by lot (and on first read for a firm already switched), with a new column
`price_levels.trade_class` naming the class each stands for (`RETAILER`,
`STOCKIST`; null on every other level). They may be renamed and reordered
but not deleted or made inactive, and their `trade_class` cannot be changed.

- **The customer's kind** is `trade_class`, shown as *Retailer* or
  *Wholesaler*. The customer's usual level is, as now, his own level, else his
  group's; where neither is set, the reserved level matching his kind. So a
  new bill starts on the customer's kind with no extra field.
- **The switch** is M13's *Price level* box, unchanged on screen: choosing
  *Wholesale* on a retailer's bill reprices every line.
- **The ranking** keeps its order, and the batch-rate tier reads the
  **document's** class instead of the customer's: the class of the level the
  document names, else the customer's trade class. A level with no class
  (Dealer) leaves the customer's class in force for the lot price, as today.
  So: typed price > price list's fixed rate > the lot's price for the bill's
  kind > the level's rate for the product > the product's selling price.
- **A line names a lot or it does not.** A line whose lot is chosen (picker,
  pin, serial) takes that lot's price. A line with no lot chosen yet is priced
  at the lot that would leave first at the line's warehouse (nearest expiry,
  then oldest received, `lot_tie_break`), which is the lot the dispatch will
  take; dispatch does not re-price it.
- **One line, one price.** Lots that differ in the bill's price never share a
  line: the picker's rows already split on PTR and PTS, and a quantity typed
  past what one price group holds is split by the screen into a second line
  at the next group's price, as Marg does one line per batch. The server
  refuses a line whose chosen lots differ in the bill's price, naming the
  two prices.

### 3.6 The lot's prices after receipt

The lot's page (batch details) shows both prices and both margins and lets a
holder of `BATCH_UPDATE` change the prices, with the MRP warning as on
the receipt line. Nothing changes the prices of a lot by itself.

### 3.7 Cost and margin on the bill line, screen only

- On the sales order and the sales bill, each line shows **cost** (the cost
  of its lots: the picked lots' cost before dispatch, the line's
  `cost_amount` after) and **margin** (taxable value less cost, and as a
  percentage of cost), and the bill shows the total margin.
- Sent only to a holder of `PRODUCT_VIEW_COST_PRICE`, as the cost already
  is (D-SELL-100); the columns are not drawn for anybody else.
- **Never printed.** No print service reads them; a guard test asserts the
  invoice, order and challan print paths name neither field.

## 4. Effect on existing features

| Feature | Effect |
| --- | --- |
| Firms on Average | None. PTR and PTS stay pharma-only and typed; levels and the switch as now |
| Pharma firms costing by lot | PTR and PTS are worked out from the margins unless typed |
| Price lists | Still win over the lot's price: an agreement with this customer |
| Discount limit (D-PRC-2) | Unchanged: measured against the customer's own price, so a wholesale switch on a retailer's bill is a reduction that needs somebody allowed it |
| Price floor | Unchanged: judged on the lots' cost (L2 step 10) |
| `price_from_batch` | Unchanged; it fills `selling_price`, which the two kinds do not use |
| Commission on margin | Reads `cost_amount` as now |

## 5. Clean-up

Nothing is replaced: no column or table goes. The two notions of the
customer's kind (trade class, level) become one switch by deriving the usual
level from the class, not by dropping either, because a level such as Dealer
still has no class.

## 6. Build steps for L3

Each is a run of its own, merged on its targeted tests.

| Step | What | Migration |
| --- | --- | --- |
| 1 | Tables: the four pairs of section 3.2, `price_levels.trade_class`; a new product takes its goods type's pair; product and goods type schemas and routes read and write the pair | Yes |
| 2 | Receiving: the purchase line's margins and prices (section 3.4), the MRP warning, the other lot sources; the gate lifted for by-lot firms | No |
| 3 | The switch: the two reserved levels, the customer's usual level from his class, the batch tier on the document's class, the price of a line with no lot chosen, the refusal of mixed prices on one line | No (rows only) |
| 4 | Cost and margin on the line: sent behind `PRODUCT_VIEW_COST_PRICE` on the order and the bill, the print guard | No |
| 5 | Screens (new UI only): goods type and product margins, the receipt line's margins, prices and warning, the lot page's prices, the customer's kind words, the line's cost and margin columns, splitting a line across price groups | No |
| 6 | Seeders (TEST03 margins), reference docs, user guides, QA cases | No |

## 7. What is deliberately not here

- Re-pricing lots when a margin changes on the product or the goods type.
- A margin on the selling price (mark-down) as a choice.
- A third or fourth price per lot (Dealer): a level's rate per product covers
  it as today.
- Rounding of the price (row F3 rounds the bill).
- Margins for a firm on Average, which has no lot per purchase line.

## 8. Decided here by the usual standard, for the owner to confirm

1. **Retail is PTR and wholesale is PTS**, not a new pair of columns; pharma
   firms keep the words PTR and PTS, other firms see Retail and Wholesale.
2. **The margin is a mark-up on the purchase price** before GST, net of the
   line's discounts, before freight (Marg, Busy).
3. **Kept to the paisa**, no other rounding.
4. **Worked out once, at receipt**; a later bill rate or landed cost corrects
   the lot's cost but not its prices. Prices are changed by hand on the lot.
5. **Above the MRP with GST warns, does not stop the receipt**; the sale
   above MRP stays refused by law; a price above the MRP before GST stays
   refused as a typing mistake.
6. **The bill's switch is the price level box**, with two reserved levels
   Retail and Wholesale; a customer with no level set starts on the level of
   his kind.
7. **A line with no lot chosen is priced at the lot that will leave first**,
   and one line never mixes two prices; the screen splits it.
8. **Cost and margin on the line are screen-only**, to holders of the
   cost permission, guarded against any print.
9. **Margins are for firms costing by lot only.**
