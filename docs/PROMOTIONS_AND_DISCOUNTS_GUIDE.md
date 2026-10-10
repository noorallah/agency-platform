# Promotions, discounts and coupons: how a price is decided, with test cases

For the firm's owner, the sales manager and QA. It explains every way a sales
line can be discounted -- price lists, the customer's own rate, promotions,
coupons, a discount typed by hand, a discount on the whole bill -- which one
wins, how two promotions combine, and what a person typing a discount
overrides. Every rule has a worked example with the figures to expect, and
section 12 shows how to set up each kind of offer, section 13 how to try
one safely before it goes live, and section 14 turns the examples into
test cases anybody can run on their own.

Written 2026-09-28 against the version 2 screens, from the code
(`app/core/utils/pricing.py`, `app/promotions/services/promotion_service.py`)
and the `selling-firm` test fixture. Menu paths brought up to release 1.3.0 on
2026-10-04: since 1.2.0 Price Lists, Promotions and Loyalty are under the gear,
in **Settings > Set up > Pricing**, not in the Sell menu. `docs/PRICING_AND_PROMOTIONS.md` holds
the engineering rules behind it.

Extended 2026-10-10 with four reference sections at the end: **16** lists
every kind of thing that changes a price, **17** says what price a line starts
at before any discount, **18** goes through every field on every create screen
and says what it changes, and **19** follows one order through every step.

## 1. The test firm every example uses

Every example uses the **`selling-firm` fixture**, so the figures can be
checked on a firm of your own without touching anybody else's data. From
`backend`, with the backend running:

```powershell
.\.venv\Scripts\python.exe scripts\test_fixture.py selling-firm
```

It prints a suffix (written `<S>` below) and sign-in details, and builds:

| What | Set up as |
| --- | --- |
| Product `<S>-DET` | Detergent 1kg, selling price **84**, GST **18%** (local), 100 in stock at MAIN |
| Customer `<S>-C01` Vijaya Stores | own standing discount **7.5%**, group **Retailer** (1.75%) |
| Customer `<S>-C02` Anand Agencies | no standing discount, group **Wholesaler** (3.25%) |
| Price list **STANDING** (everyone) | DET: **2%** from 0, **4.25%** from 15, **6.75%** from 18 |
| Price list **NEGOTIATED** (Anand only) | DET: **9.25%** from 0 |
| Promotion **BULK5** | applies at **10**; line quantity at least 25 → **7.5%** off the line; others may still apply |
| Promotion **BIGORDER** | applies at **20**; order value at least 4,500 → **200** off the whole bill; **ends the stack** |
| Promotion **CLEARANCE** | applies at **30**; line quantity at least 40 → **1%** off the line; others may still apply |
| Promotion **WELCOME** | applies at **40**; **coupon only** (codes `WELCOME10`, `WELCOME10B`) → **2.5%** off each line |

"Applies at" is the promotion's priority: lowest first.

Amounts below are **before tax** unless they say otherwise. GST is 18% of
the taxable value (the value after every discount).

## 2. One line takes one discount -- the first that applies

For each line the system walks down this list and uses the **first** answer
it finds. It never adds two of them together and never picks the largest.

| Rank | Source | Screen says (side panel, under Discount) |
| --- | --- | --- |
| 1 | An **amount** typed in "Disc amt" | typed on this order |
| 2 | A **percent** typed in "Disc %" | typed on this order |
| 3 | **Promotions** (all that match, combined -- section 4) | from a promotion |
| 4 | The **price list** (the customer's own list replaces the firm-wide one) | from the price list |
| 5 | The customer's **standing discount** | from the customer's standing rate |
| 6 | The customer **group's** discount | from the customer group's rate |

**Blank and 0 are different.** A blank box means "use whatever arrangement
applies". A **0** typed in the box means "no discount on this line" and
refuses every arrangement below it.

### Examples

| # | Customer, quantity of DET | Discount | Why |
| --- | --- | --- | --- |
| 2a | C01, 12 | **2%** (20.16) | STANDING's first break; it outranks Vijaya's own 7.5% |
| 2b | C01, 18 | **6.75%** | highest break at or below 18 |
| 2c | C02, 18 | **9.25%** | Anand's own list replaces STANDING |
| 2d | C02, 30 | **7.5%** (189.00) | BULK5 outranks the list -- **even though the list gives more** |
| 2e | C01, 30, Disc % typed **0** | **0** | a typed 0 refuses everything; 30 x 84 = 2,520 taxable |

Example 2d is the one people get wrong: ranking decides, not the bigger
number. A promotion beats Anand's 9.25% list and gives him 7.5%.

To see ranks 5 and 6 you need a product that no price list names (every
price list line is rank 4). Create `<S>-SOAP` at **100**, GST 18%:

| # | Customer, 10 SOAP (gross 1,000) | Discount | Taxable | GST | Total |
| --- | --- | --- | --- | --- | --- |
| 2f | C01 | **7.5%** standing = 75.00 | 925.00 | 166.50 | 1,091.50 |
| 2g | C02 | **3.25%** group = 32.50 | 967.50 | 174.15 | 1,141.65 |

A standing discount of 0 means "none set", so Anand falls through to his group.

## 3. What a promotion can check and give

Settings (the gear) → Set up → Pricing → **Promotions** → New.

**Applies when** (every condition must hold; no conditions means every line).
There are eighteen things a condition can look at and eleven tests; section
18.3 lists them all with an example each.

**Gives** -- ten kinds of benefit. Section 18.2 has the fields and a worked
example for each:

| Benefit | What it does |
| --- | --- |
| Percent off each line | on every line that met the conditions |
| Amount off each line | never more than what is left of the line |
| Percent off the whole bill | on the bill after line discounts |
| Amount off the whole bill | never more than the bill |
| Free goods (buy X, get Y) | more of the same product; whole multiples only: "buy 10 get 1" on 25 gives **2** free, not 2.5 |
| A free product (buy X, get another) | a different product, added as its own line at no charge |
| Buy X, get Y at a discount | "buy 1, get the second at 50%" -- a discount on units already on the line |
| Combo price | a set price for products bought together |
| Free delivery | the delivery charge is waived whole |
| Bonus loyalty points | multiplies the points the bill earns; changes nothing on the price |

**Other settings:** From / Until dates, Status (only **ACTIVE** applies),
**Other promotions may still apply** (the stacking switch, section 4),
**Only with a coupon**, **Total uses**, **Uses per customer**, **Budget
(value)**, **Budget (free units)** and **Funded by principal**. Section 18.1
says what each one changes.

## 4. Two promotions together: they combine

1. Every ACTIVE promotion in its dates is considered, **lowest "Applies at"
   first** (equal numbers: by code, A before B).
2. Each one whose conditions hold is **applied**.
3. If the one just applied has **Other promotions may still apply** switched
   **off**, nothing after it is considered. That is "ends the stack".
4. **Percentages compound**: each is taken off what is left, not off the
   original. Two 10% offers make 19%, not 20% -- and stacking can never take
   a line below zero.

This is the default, **Combine offers**. A firm can choose **Best offer only**
instead, and in Combine mode can cap what offers together take off one line --
both under Settings > Selling > Sales Stages > *When several offers match*
(section 18.8). To make one offer exclude another without changing the firm's
mode, give it the lower "Applies at" and switch stacking off.

### Examples (customer C01)

**4a -- two line offers compound.** DET **40** (gross 3,360; below 4,500 so
BIGORDER does not match):

| Step | Offer | Taken off | Left |
| --- | --- | --- | --- |
| 1 | BULK5 7.5% of 3,360 | 252.00 | 3,108.00 |
| 2 | CLEARANCE 1% of 3,108 | 31.08 | 3,076.92 |

Discount **283.08** (8.425%, not 8.5%). Taxable 3,076.92.

**4b -- an offer that ends the stack.** DET **60** (gross 5,040):

| Step | Offer | Taken off |
| --- | --- | --- |
| 1 | BULK5 7.5% on the line | 378.00 |
| 2 | BIGORDER 200 off the bill -- stacking off, so it stops here | 200.00 |
| - | CLEARANCE (1% at 40+) -- **not applied** though the line qualifies | - |

Taxable 4,462.00, GST 803.16, **grand total 5,265.16**.

**4c -- a coupon offer on top.** DET **32**, coupon `WELCOME10` (gross 2,688):

| Step | Offer | Taken off | Left |
| --- | --- | --- | --- |
| 1 | BULK5 7.5% | 201.60 | 2,486.40 |
| 2 | WELCOME 2.5% | 62.16 | 2,424.24 |

Discount **263.76**, taxable 2,424.24.

## 5. A discount typed by hand wins

| What you type | Effect |
| --- | --- |
| Disc % or Disc amt on a line | **That line is left out of every promotion** and every list. Other lines still get their offers. |
| **0** in Disc % | No discount at all on that line (example 2e). |
| Discount on the whole order (% or amount) | **Bill-level promotions are skipped.** Line-level promotions still apply. A bill offer that ends the stack still ends it. |
| Only the **Rate** (price) | Does **not** block promotions -- the offer is worked out on your price. |
| Free goods on a line | Blank takes the offer's free goods; a typed number replaces them on that line, and **0** refuses them (D-SELL-41, fixed 2026-09-30). |

### Examples (customer C01)

| # | Order | Result |
| --- | --- | --- |
| 5a | DET 30, Disc % **5** | 126.00 off, "typed on this order"; BULK5 not applied. Taxable 2,394.00, total 2,824.92 |
| 5b | DET 30, Rate **80** | gross 2,400, BULK5 still 7.5% = 180.00. Taxable 2,220.00, total 2,619.60 |
| 5c | DET 60, whole-order amount **100** | BULK5 378.00 on the line; BIGORDER's 200 **not** taken (you typed the bill discount); CLEARANCE still not applied. Taxable 4,562.00, total 5,383.16 |
| 5d | Two lines: DET 30 blank, DET 30 with Disc % 5 | line 1 BULK5 189.00 "from a promotion"; line 2 126.00 "typed on this order" |

## 6. Coupons

- A coupon belongs to a promotion marked **Only with a coupon**. Codes are
  made under Promotions → **Coupons** → New coupon, each with its own dates
  and usage limits.
- The code is typed in **Coupon** on the **sales order**. An unknown code is
  ignored -- it neither gives a discount nor refuses the order.
- **Quotations** have a Coupon box too (D-SELL-43), so a quote shows the
  coupon's offer and the order converted from it is priced the same. A bill
  typed straight in by a firm with the stages off has one (D-SELL-40), on a
  new bill only: a bill of a delivery note carries none, because that note was
  priced when it was raised.

### Examples (customer C01, DET 12, gross 1,008)

| # | Coupon | Discount |
| --- | --- | --- |
| 6a | none | 2% from the price list = 20.16 |
| 6b | `WELCOME10` | **2.5%** from a promotion = 25.20 -- replaces the list's 2%, does not add to it |
| 6c | `WELCOME10B` | 2.5% -- another code for the same offer |
| 6d | `NOSUCHCODE` | back to 2% from the price list; the order saves |

## 7. Limits are counted when the order is approved

"Total uses" and "Uses per customer" (on the promotion or the coupon) are
counted when an order is **approved**, not while it is typed -- so a draft
uses nothing. When the limit is reached the approval is **refused by name**:

- "Promotion `<code>` has been claimed as often as ..."
- "This customer has claimed promotion `<code>` as ..."
- "Coupon `<code>` has been used as often as it ..."
- "This customer has used coupon `<code>` as often as ..."

Cancelling an approved order gives the use back.

## 8. A discount on the whole bill, and freight, reach the GST

A whole-order discount (typed or from a promotion) is **spread over the
lines** in proportion to what each is worth after its own discount, so it
lowers each line's taxable value and therefore the GST. Freight is spread the
same way and is taxed with the goods. Example 4b: 200 off the bill takes 36.00
off the GST (18% of 200).

## 9. Along the chain the price does not change

Quotation → order → delivery note → invoice each **inherit** the discount,
free goods and freight of the line they continue. Nothing re-reads the price
list or the promotions later: switch BULK5 off after an order was approved at
7.5%, and its delivery note and invoice still bill 7.5%.

## 10. A one-person firm billing straight from the invoice

With **Settings → Selling → Sales Stages** all switched off, a bill typed
straight in raises its order behind the scenes, and that order is priced the
ordinary way, so **automatic promotions apply**, and a **Coupon** box on the new
bill takes the customer's code (D-SELL-40, fixed 2026-09-30). The box is on a
new bill only. Test case TC-PROMO-015 is the check.

## 11. Loyalty points are not a discount

Spending points **pays** part of the bill; it does not lower the price, so
the full GST is still charged. The fixture earns 2 points per 100.
`INDEPENDENT_TEST_CASES.md` TC-INCENT-005 is the case.

## 12. Setting up offers, step by step

Everything is under **Settings → Set up → Pricing** (the gear at the right of
the menu bar; the foot of the Sell drop-down links to it too): **Price Lists**,
**Price Levels**, **Promotions** and **Loyalty**. Coupons are on the Promotions page
under **Coupons**. You need the promotion or price-list permissions to change
them; a salesman can see them but not edit them.

### Before you save any offer

| Check | Why |
| --- | --- |
| **Applies at** | Lower numbers are tried first. Look at the list: where does the new offer sit among the ones already live? |
| **Other promotions may still apply** | Off means nothing after this offer is tried. Put an offer like that **after** the ones it must not block (a higher number). |
| **From / Until** | The offer is judged on the **document's date**, and only inside this window. Leave Until blank for no end. |
| **Status** | Only **ACTIVE** offers apply. DRAFT and INACTIVE never do. |
| **Only with a coupon** | On means nobody gets it without typing a code on the order. |
| **Total uses / Uses per customer** | Blank means unlimited. Counted when an order is approved. |

**Editing an ACTIVE offer saves a new revision** and switches the old one
off. Documents already priced keep what they were given.

### Recipes for common offers

**12.1 Festival discount on everything** (Diwali 10%, 20 Oct to 5 Nov).
Promotions → **New promotion** → Code `DIWALI10`, Name "Diwali 10%"; Applies
at **50**; Status **ACTIVE**; From **20-10**, Until **05-11**; Other promotions
may still apply **on**. Gives → Add benefit → **Percent off each line**, 10.
Applies when → nothing (every line). Save.

**12.2 Festival discount on one category** (15% on Sweets).
As 12.1, then Applies when → Add condition → When **Product category**, Test
**is one of**, then pick each category (*Sweets*, *Snacks*, ...) -- one offer
covers them all (D-SELL-42).

**12.3 Amount off a big bill** (300 off orders of 5,000 or more).
Gives → **Amount off the whole bill**, 300. Applies when → **Order value** **is
at least** 5000. Order value is before any discount.

**12.4 Slabs on order value** (2% at 5,000, 4% at 10,000 -- only one slab).
Two offers, highest slab first, each **ending the stack**, and numbered
**after** every line offer so they block nothing:

- `SLAB4`: Applies at **900**, stacking **off**, Order value is at least
  10000 → Percent off the whole bill 4.
- `SLAB2`: Applies at **910**, stacking **off**, Order value is at least
  5000 → Percent off the whole bill 2.

An order of 12,000 gets 4% and stops; one of 6,000 misses SLAB4 and gets 2%.

**12.5 Buy 10, get 1 free** (on Detergent).
Gives → **Free goods (buy X, get Y)**, Buy **10**, Get free **1**. Applies when
→ Product **is** Detergent. Whole multiples only: 25 bought gives 2 free.
Free goods are not discounted and not billed.

**12.6 Festival coupon** (`DIWALI100`: 100 off, once per customer, 500 in all).

1. New promotion `DIWALI-CPN`: **Only with a coupon** on, Gives **Amount off
   the whole bill** 100, dates as the festival, ACTIVE.
2. Promotions → **Coupons** → **New coupon**: Offer `DIWALI-CPN`, Code
   `DIWALI100`, Status Active, **Total claims allowed** 500, **Per customer**
   1, Live from / Live until as the festival.
3. The salesman types `DIWALI100` in **Coupon** on the sales order.

Several codes can point at one offer (one per shop, one per salesman), each
with its own limits; the offer's own limits cap them all together.

**12.7 An offer for some customers only.**
Applies when → **Customer** is *X*, or **Territory** / **Route** is *Y*. Every
condition must hold, so "Customer is A" plus "Territory is T" means both.

**12.8 A festival price list instead of an offer.**
Price Lists → **New price list** → Applies to Everyone / One customer / One
territory; In force from / Until; Add product with **From qty** and
**Discount %** for each break. A promotion **outranks** a price list on the
same line (section 2).

**12.9 Customer and group discounts.**
The customer's standing discount is on the customer record; a group's is on
Settings → Set up → Party lists → **Customer Groups**. Both are last in the ranking.

**Also on the screen** (D-SELL-42): buy X get a **different** item free
(*A free product*), *Free delivery*, and conditions on customer group, branch,
salesman, document type or date.

## 13. Trying an offer before it goes live

Use **Try offers** on the Promotions screen (the "..." in the toolbar). It asks
the same engine every order uses what a made-up document would earn. **Nothing
is saved, no stock is reserved and no offer limit is used up**, so it is safe
to try as often as you like.

**Step 1 -- describe the document.** Type the **Date** -- a future date is the
point: put the festival's first day and see today what that offer does. Choose
the document (order or quotation), and optionally a customer, a coupon code and
a delivery charge. An offer aimed at one customer or group needs that customer.

**Step 2 -- add lines.** Pick a product, a quantity and a rate for each line;
the rate fills in from the product's price. Add as many lines as you need.

**Step 3 -- press Try.** You see each line's discount and free quantity, the
bill discount, delivery waived, any free goods, and the **total saved**. Below
that, **every offer tried** is listed with its priority, whether it applied and
the reason -- so when an offer does not apply, the table says why.

| Try | You are checking |
| --- | --- |
| A line that should qualify | the offer applies, at the rate you meant |
| A line just **below** the condition (24 when it needs 25) | it does **not** apply |
| A line **exactly at** the condition (25) | it **does** apply ("is at least" includes 25) |
| The largest realistic order | the combined discount with the other live offers is what you intend (section 4) |
| An offer that should end the stack | the offers after it are absent |

A **DRAFT** offer never applies, so make it ACTIVE with its dates before
trying it. A discount typed on a real line beats every offer (section 5); Try
shows what the offers alone would give.

**On the first day.** Open the first real order that should get the offer and
check its side panel. Reports → Operational → **Promotion performance**
and **Promotion claims** show every approved use.

### Testing before a software release (QA)

On a fresh `selling-firm` fixture (section 1), run the cases in section 14.
When time is short, this smoke set covers every rule once: **TC-PROMO-001,
004, 005, 007, 010, 012, 014** and **018**.

## 14. Test cases

Each case runs on a fresh `selling-firm` fixture, on its own, in any order.
"Order" means Sell → **Sales Orders** → New; after **Create draft**, open it
again and click the line to read the side panel. Customer C01 unless stated.

| Case | Steps | Expect |
| --- | --- | --- |
| **TC-PROMO-001** Ranking | Quotations: C01 DET 12; C01 DET 18; C02 DET 18; C02 DET 30 | 2% price list; 6.75% price list; 9.25% price list; **7.5% from a promotion** (example 2d) |
| **TC-PROMO-002** Typed zero | Order C02 DET 30, Disc % **0** | discount 0, "typed on this order", taxable 2,520.00 |
| **TC-PROMO-003** Standing and group | Create `<S>-SOAP` at 100, GST 18%. Order C01 SOAP 10; order C02 SOAP 10 | 7.5% "from the customer's standing rate", total 1,091.50; 3.25% "from the customer group's rate", total 1,141.65 |
| **TC-PROMO-004** Compounding | Order DET 40 | discount 283.08 (8.425%), taxable 3,076.92 |
| **TC-PROMO-005** End of stack | Order DET 60 | line 7.5% (378.00), 200 off the whole order, CLEARANCE absent, grand total **5,265.16** |
| **TC-PROMO-006** Coupon on top | Order DET 32, Coupon `WELCOME10` | discount 263.76, taxable 2,424.24 |
| **TC-PROMO-007** Coupon replaces the list | Order DET 12 with `WELCOME10`, then `WELCOME10B`, then `NOSUCHCODE` (save and reopen each time) | 2.5%, 2.5%, then 2% "from the price list"; every save succeeds |
| **TC-PROMO-008** Typed line discount | Order DET 30, Disc % 5 | 126.00 "typed on this order", total 2,824.92 |
| **TC-PROMO-009** Typed rate | Order DET 30, Rate 80 | 7.5% "from a promotion" = 180.00, total 2,619.60 |
| **TC-PROMO-010** Typed bill discount | Order DET 60, whole-order amount 100 | line 378.00; bill 100 (not 200); total 5,383.16 |
| **TC-PROMO-011** Mixed lines | Order: DET 30 blank + DET 30 Disc % 5 | line 1 from a promotion 189.00; line 2 typed 126.00 |
| **TC-PROMO-012** Free goods | New promotion FREE10: applies at 5, others may still apply, condition Product is DET, Free goods buy 10 get 1, ACTIVE. Order DET 25 | Free **2** (not 2.5); discount 7.5% of 2,100 = 157.50 (free goods are never discounted); taxable 1,942.50 |
| **TC-PROMO-013** Dates and status | New promotion OLD5: applies at 1, 5% off each line, Until = yesterday, ACTIVE. New promotion DRAFT5: same but From today, Status DRAFT. Order DET 12 | 2% from the price list -- neither applies |
| **TC-PROMO-014** Usage limit | Promotions → Coupons → New coupon `ONCE1` on WELCOME, Total uses 1. Two orders DET 12 with `ONCE1`; approve the first, then the second | first approves; second refused: "Coupon ONCE1 has been used as often as it ..."; cancel the first, and the second then approves |
| **TC-PROMO-015** Direct bill | Settings → Selling → Sales Stages: switch all three off. New invoice, C01, DET 30, no source | 7.5% from a promotion; a **Coupon** box is on the new bill (D-SELL-40) |
| **TC-PROMO-016** Price holds along the chain | Order DET 30, approve. Edit BULK5 to **10%** (saves as a new revision). Deliver and bill the order; then a new order DET 30 | note and bill both 7.5%, 189.00; the new order 10%, 252.00 |
| **TC-PROMO-017** Free goods cannot be refused | With FREE10 from TC-PROMO-012, order DET 25 with Free **0** typed | 0 free (D-SELL-41, fixed 2026-09-30); with Free left blank, 2 |
| **TC-PROMO-018** Trying an offer before launch | Section 13 steps 1-5 with a new offer TRY20: 20% off each line, Customer is ZZTEST, From today. Quotation ZZTEST DET 12; quotation C01 DET 12; then remove the ZZTEST condition and save; quotation C01 DET 12 again | ZZTEST: 20% from a promotion; C01 first: 2% from the price list (TRY20 reaches nobody else); after: C01 20% from a promotion; the list shows TRY20 revision 2, and revision 1 INACTIVE |

Already covered in `docs/INDEPENDENT_TEST_CASES.md`, with data checks:
TC-SELL-001 to 004 (ranking), TC-SELL-006 (coupons), TC-SELL-010 (the note
keeps the order's deal), TC-INCENT-001 (ladder), TC-INCENT-002 (editing an
active promotion makes a new revision), TC-INCENT-003 (claims counted at
approval), TC-INCENT-004 (end of stack), TC-INCENT-005 (loyalty).

## 15. Known gaps

D-SELL-40, 41, 42 and 43 (direct-bill coupon, refusing free goods with 0, the
full promotion screen, the quotation coupon) were fixed on 2026-09-30 and are
described where they apply above.

The offer types backlog 60 listed as missing -- buy X get Y at a discount,
combo prices, bonus points, bulk coupon codes, first-order offers, copying
offers to new dates, scheme budgets and principal claims -- have been built
since and are described in section 18.

**Percent off, up to a limit (2026-10-01).** A percentage benefit -- on the line or on the bill -- takes an optional **Up to**: "20% off, up to 500" never takes more than 500 off the document. On line percentages the 500 is shared across the lines the offer matched, in proportion to what each would have had, so the lines still add up to exactly 500. Blank means no limit.

**Best offer only (2026-10-01).** Settings > Selling > Sales Stages > *When several offers match* chooses how offers meet. *Combine offers* (the default) applies every matching offer in Applies-at order until one that does not stack. *Best offer only* tries each matching offer on its own and gives the customer only the one worth most -- free goods counted at what they would have cost -- with ties going to the earlier Applies at. Try offers shows each one's worth and why it lost.

**Most offers may take off one line (2026-10-01).** In *Combine offers* mode the same screen takes an optional cap, as a % of the line: when the offers together would take more off a line, the offer applied last gives back first. Blank means no cap; the bill discount is not counted.

## 16. Every kind of thing that changes a price

Twelve things can change what a customer pays. They do not all do the same
job: some set the **price**, some take a **discount** off it, some give
**goods**, and some act on the **whole bill**.

| # | Kind | Job | Where it is set up | Who it reaches |
| --- | --- | --- | --- | --- |
| 1 | Product selling price | starting price | the product | everyone |
| 2 | Price level | starting price | Set up > Pricing > Price Levels; the level's price is kept per product | customers on that level (their own, else their group's) |
| 3 | Batch trade rate (PTR / PTS) | starting price | on the batch | Retailer or Stockist customers, where the firm keeps batch rates |
| 4 | Price list -- **Rate** | starting price | Set up > Pricing > Price Lists | everyone, one territory, or one customer |
| 5 | Price list -- **Discount %** | line discount | the same list | the same |
| 6 | Customer's standing discount | line discount | the customer record | that customer |
| 7 | Customer group's discount | line discount | Set up > Party lists > Customer Groups | every customer in the group |
| 8 | Promotion (ten kinds of benefit) | line discount, bill discount, free goods, free delivery or bonus points | Set up > Pricing > Promotions | whoever meets its conditions |
| 9 | Coupon | a key that opens a promotion marked *Only with a coupon* | Promotions > Coupons | whoever types the code |
| 10 | Something typed on the document | price, line discount, free quantity, bill discount, delivery charge | the order, quotation or bill | that document only |
| 11 | Delivery charge (freight) | added to the bill and taxed | the document | that document |
| 12 | Loyalty points | **pays** part of the bill; not a discount | Set up > Pricing > Loyalty | customers with points |

A supplier's price list (*One supplier*), rate contract and free scheme do the
same jobs on the **buying** side; purchase orders read them.

The order they are applied in, for one sales line:

1. **Starting price** -- typed, else 4, 3, 2, 1 in that order (section 17).
2. **Free goods** from promotions are added.
3. **Line discount** -- one source only: typed amount, typed percent,
   promotions, price list, standing, group (section 2).
4. **Bill discount** -- typed, else from promotions -- is spread over the lines.
5. **Delivery charge** is spread over the lines (or waived by an offer).
6. **GST** on what is left of each line.
7. At approval: offer limits and budgets are counted, and the discount limit,
   price floor and credit limit are checked. These never change the price;
   they can refuse the approval.
8. After the bill: loyalty points are earned, or spent as payment.

## 17. The price a line starts at

A discount comes off a price, so the price is settled first. When the **Rate**
box is left blank, the first of these that exists is used:

| Rank | Source | Example for DET (selling price 84) |
| --- | --- | --- |
| 1 | A price **typed** on the line, 0 included | typed 80 → 80 |
| 2 | A price list's fixed **Rate** for this customer, at the quantity break reached | list says Rate 78 from 50 → a line of 60 starts at 78 |
| 3 | The batch's **PTR** (Retailer) or **PTS** (Stockist), where the line names one batch and the firm keeps batch rates | batch PTR 79 → a Retailer starts at 79 |
| 4 | The customer's **price level** (their own, else their group's) | WHOLESALE level price 76 → 76 |
| 5 | The product's **selling price** | 84 |

Three things to know:

- **All these prices are for one stock unit.** A line sold by the box takes
  the piece price times the pieces in the box: DET at 84 a piece, 12 to a box,
  is 1,008 a box. A typed price is the price of the unit on the line and is
  never converted.
- **A price list can give both.** With Rate 78 and Discount % 5 on the same
  row, the line starts at 78 and then takes 5% off -- unless a promotion or a
  typed discount outranks the list's discount (section 2).
- **Rate includes GST.** Where that switch is on, a typed rate is read as the
  shelf price and converted to the before-tax price first: 100 typed at 18%
  is stored as 84.7458.

## 18. Every field, and what it changes

### 18.1 Promotion -- the top of the screen

Settings > Set up > Pricing > **Promotions** > New promotion.

| Field | What it changes | Example |
| --- | --- | --- |
| **Code** | The offer's name on documents, reports and refusals. One code is one offer for good. | `DIWALI10` |
| **Name**, **Description** | For people only. | "Diwali 10%" |
| **Applies at** (1 to 9999, starts at 100) | The order offers are tried in, lowest first. It decides which percentage compounds first, which offer ends the stack, and who wins a tie in Best offer mode. | 10 is tried before 20 |
| **Status** | Only **ACTIVE** applies. DRAFT can be edited freely and never applies; INACTIVE is switched off. Editing an ACTIVE offer saves a new revision. | DRAFT while you build it |
| **From / Until** | The offer applies only when the **document's date** is inside the window. Blank Until means no end. | 20-10 to 05-11 |
| **Other promotions may still apply** | On: offers after this one are still tried. Off: this offer **ends the stack**. | off on BIGORDER |
| **Only with a coupon** | On: nobody gets it without one of its codes. | on for WELCOME |
| **Total uses** | How many approved documents may claim it, in all. Blank is no limit. Counted at approval. | 500 |
| **Uses per customer** | The same, per customer. | 1 |
| **Budget (value)** | The most money the offer may take off bills over its life. An order that would take more than is left is priced without the offer. Blank is no budget. | 50,000 |
| **Budget (free units)** | The most free units it may give, in stock units. | 500 |
| **Funded by principal** and its share % | Who pays for the scheme. The share is claimed back from that principal on the bills that passed the discount on. *None* is the firm's own offer. | Principal X, 50% |
| **Gives** | One or more benefits (18.2). | |
| **Applies when** | Zero or more conditions (18.3). | |

### 18.2 Promotion -- the ten benefits

Examples use DET at 84. "Matched lines" are the lines that met the conditions.

| Benefit | Fields | What happens | Example |
| --- | --- | --- | --- |
| **Percent off each line** | Percent; **Up to** (optional) | That % comes off every matched line. *Up to* caps what the offer takes off the whole document, shared across the matched lines. | 10% on 30 DET (2,520) → 252.00 off |
| **Amount off each line** | Amount | That amount comes off each matched line, never more than is left of it. | 50 off a line of 2,520 → 2,470 |
| **Percent off the whole bill** | Percent; **Up to** (optional) | % of what the lines come to after their own discounts, spread over all lines. | 5% of 2,520 = 126; with Up to 100 → 100 |
| **Amount off the whole bill** | Amount | A fixed amount off the bill, spread over all lines. | 200 off |
| **Free goods (buy X, get Y)** | Buy; Get free | More of the **same** product, whole multiples only. Counted in stock units. | Buy 10 get 1: 25 bought → 2 free |
| **A free product (buy X, get another)** | Product given away; Get free; Buy (optional) | A **different** product added as its own line, charged nothing. Buy is counted across all matched lines; blank Buy gives it once per order. | Buy 20 DET get 1 SOAP: 45 bought → 2 SOAP |
| **Buy X, get Y at a discount** | Buy (at full price); Get (at the discount); % off | In every complete group of Buy + Get units on a line, the Get units take the % off. | Buy 1 get 1 at 50%: 5 DET → 2 groups → 2 units at half = 84.00 off |
| **Combo price** | Two or more products with a Qty each; Set price | Every complete set on the document costs the set price; the saving is spread over those lines. | 1 DET + 1 SOAP for 150 (normally 184): 3 DET + 2 SOAP → 2 sets → 68.00 saved |
| **Free delivery** | none | The delivery charge is removed whole, so nothing is charged or taxed for it. | freight 150 → 0 |
| **Bonus loyalty points** | Times the usual points (above 1, up to 10) | The bill earns that many times its points at approval. Must be the only benefit on its offer. | 2 → 4 points per 100 instead of 2 |

Free goods are outside the line's value: they are not discounted and not
taxed, but they do leave stock.

### 18.3 Promotion -- conditions

Each condition is **When** (what to look at), **Test**, and a value. Every
condition must hold.

| When | Looks at | Example |
| --- | --- | --- |
| Product | the line's product | Product **is** DET |
| Product category | the product's category | **is one of** Sweets, Snacks |
| Product type | goods or service | **is** goods |
| Customer | the document's customer | **is** Vijaya Stores |
| Customer group | the customer's group | **is** Retailer |
| Territory, Route | where the customer is | Territory **is** North |
| Branch | the selling branch | **is** MAIN |
| Salesman | the salesman on the document | **is** Ravi |
| Document type | Sales order or Quotation | **is** Sales order |
| Document date | the document's date | **is between** two dates |
| Quantity on the line | the line's quantity, in stock units | **is at least** 25 |
| Line value | quantity x price of the line, before discount | **is at least** 1,000 |
| Order value | all lines together, before discount | **is at least** 4,500 |
| Days of the week | the document date's weekday | Saturday and Sunday |
| Time of day | when the document was raised (India time) | 16:00 to 18:00 |
| Customer's approved orders so far | bills approved before this document | **is** 0 -- first order only |
| Days since the customer's last order | days since their last approved bill | **is at least** 60 -- win-back |

Tests: **is**, **is not**, **is one of**, **is none of**, **is more than**,
**is at least**, **is less than**, **is at most**, **is between**, **is set**,
**is not set**. A time window cannot cross midnight; make two offers.

A condition on the line (product, quantity, line value) decides **which lines**
get a line benefit. A condition on the document (customer, order value, date)
decides whether the offer applies **at all**.

### 18.4 Coupon

Promotions > **Coupons** > New coupon. A coupon gives nothing itself; it opens
its offer.

| Field | What it changes |
| --- | --- |
| **Offer** | The promotion the code opens. Fixed once saved. |
| **Code** | What the customer says and the salesman types in **Coupon**. |
| **Status** | An inactive code opens nothing. A code under a switched-off offer reads as off too. |
| **Total claims allowed**, **Per customer** | Limits for this code alone. The offer's own limits still cap all its codes together. |
| **Live from / Live until** | The code's own window, inside the offer's. |

**Generate coupon codes** mints up to 5,000 random single-use codes for one
offer (How many, Prefix, dates) and saves them as a CSV.

### 18.5 Price list

Set up > Pricing > **Price Lists** > New price list.

| Field | What it changes |
| --- | --- |
| **Code**, **Name** | Identify the list. |
| **Applies to** -- Everyone / One customer / One territory / One supplier | Who the list reaches. For a product it names, a customer's list replaces the territory's, which replaces the firm-wide one -- they are never merged. *One supplier* is a buying list. |
| **In force from / Until** | The list counts only for documents dated inside the window. |
| Per product: **From qty** | The quantity this row starts at, in stock units. The highest row at or below the line's quantity is used. Blank is "any quantity". |
| Per product: **Discount %** | The line discount this row gives (rank 4 in section 2). |
| Per product: **Rate** | Optional fixed price: the price the line starts at (rank 2 in section 17). |

Example -- DET with three rows: from 0 → 2%, from 15 → 4.25%, from 18 → 6.75%.
A line of 12 takes 2%, 16 takes 4.25%, 18 or more takes 6.75%.

### 18.6 Price level

Set up > Pricing > **Price Levels**: Code, Name, Order (listing order only),
Active. A level is a named set of prices -- one price per product, no quantity
breaks and no discount. A customer is put on a level on the customer record,
or takes their group's. It sets the starting price only (rank 4 in section 17).

### 18.7 Customer and customer group

| Field | Where | What it changes |
| --- | --- | --- |
| Standing discount % | customer record | Rank 5 line discount. 0 means none set. |
| Price level | customer record | Starting price. |
| Customer group | customer record | Which group's discount and level the customer falls back to; also what a promotion's *Customer group* condition tests. |
| Group discount % | Customer Groups | Rank 6 line discount -- the last resort. |
| Group price level | Customer Groups | Starting price for members with no level of their own. |

Changing a customer's standing discount, level, or a group that carries
either needs the customer-settings permission, because each is a price
decision.

### 18.8 Firm-wide settings

| Setting | Where | What it changes |
| --- | --- | --- |
| **When several offers match** -- Combine offers / Best offer only | Settings > Selling > Sales Stages | Combine applies every matching offer in order. Best offer tries each alone and gives only the one worth most. |
| **Most offers may take off one line** (%) | the same screen, Combine mode | A cap per line; the offer applied last gives back first. |
| **Rate includes GST** | the firm's selling settings, and on each document | Typed rates are read as shelf prices. |
| Discount limit per role | role settings | A **typed** discount or price cut above the approver's limit waits for someone allowed more. |
| Price floor -- Off / Warn / Block | selling settings | Whether a sale below cost or minimum price warns or is refused. |

### 18.9 On the document itself

| Box | Blank means | A number means | 0 means |
| --- | --- | --- | --- |
| **Rate** | take the starting price (section 17) | this price; promotions still apply on it | given away |
| **Disc %**, **Disc amt** | take whatever arrangement applies (section 2) | this discount; the line is left out of promotions and lists | no discount on this line |
| **Free** | take the offer's free goods | this many free; the offer gives the line nothing more | refuse the offer's free goods |
| **Discount on the whole order** | take a bill offer if one matches | this discount; bill offers are skipped | no bill discount |
| **Coupon** | no coupon offers | opens that code's offer; an unknown code gives nothing and the order still saves | -- |
| **Delivery charge** | none | charged and taxed with the goods, unless an offer waives it | none |

### 18.10 How the kinds meet each other

| Together | Result |
| --- | --- |
| Price list discount + standing + group | **One** only -- the list, if it names the product. |
| Promotion + price list discount | The promotion **replaces** the list's discount, even when the list gives more (example 2d). The list's fixed Rate still sets the price. |
| Two line promotions | Compound, lowest *Applies at* first (10% + 10% = 19%). |
| Line promotion + bill promotion | Both: the line discount first, the bill discount on what is left. |
| Free goods + a discount | Both: the discount is on the charged units only. |
| Coupon offer + automatic offers | Stacks like any other offer, in *Applies at* order. |
| Typed line discount + anything automatic | Typed wins; nothing else touches that line's discount. |
| Typed bill discount + bill promotion | Typed wins; line promotions still apply. |
| Line discount + bill discount + delivery charge | All three: each line's taxable value is its value, less its discount, less its share of the bill discount, plus its share of the delivery charge. |
| Loyalty points + any discount | Independent: points pay the bill after it is priced. |

## 19. One order, start to finish

These figures were worked by hand from the rules above and have not been run
on a server. They use the `selling-firm` fixture with two additions: product
`<S>-SOAP` at 100 (GST 18%) and promotion **FREE10** (applies at 5, others may
still apply, Product is DET, buy 10 get 1). The firm is in Combine mode.

**The order:** customer C01 (Vijaya Stores), DET 60, SOAP 10, delivery charge
150, every discount box left blank.

**Step 1 -- starting price.** No list fixes a Rate and C01 has no price
level, so DET starts at 84 and SOAP at 100.

| Line | Quantity x price | Gross |
| --- | --- | --- |
| DET | 60 x 84 | 5,040.00 |
| SOAP | 10 x 100 | 1,000.00 |
| Order value | | 6,040.00 |

**Step 2 -- promotions, lowest "Applies at" first.**

| Applies at | Offer | Matches? | Gives |
| --- | --- | --- | --- |
| 5 | FREE10 | DET line | **6 free** DET (60 / 10) |
| 10 | BULK5 | DET line (60 is at least 25); not SOAP (10) | 7.5% of 5,040 = **378.00** off DET |
| 20 | BIGORDER | order value 6,040 is at least 4,500 | **200.00** off the bill -- and it ends the stack |
| 30 | CLEARANCE | would match DET (60 is at least 40) | **not tried** -- the stack ended |
| 40 | WELCOME | no coupon typed | not tried |

**Step 3 -- one discount per line.**

| Line | Source used | Discount | Left |
| --- | --- | --- | --- |
| DET | promotion (rank 3) -- outranks the list's 6.75% | 378.00 | 4,662.00 |
| SOAP | no promotion, no list names it, so the standing 7.5% (rank 5) | 75.00 | 925.00 |
| | | | 5,587.00 |

**Step 4 -- the bill discount of 200 and the delivery charge of 150 are
spread** in proportion to what each line is left at (4,662 : 925).

| Line | Left | Bill discount share | Delivery share | Taxable |
| --- | --- | --- | --- | --- |
| DET | 4,662.00 | 166.8874 | 125.1656 | 4,620.2782 |
| SOAP | 925.00 | 33.1126 | 24.8344 | 916.7218 |
| | | 200.0000 | 150.0000 | **5,537.00** |

**Step 5 -- GST and total.**

| | |
| --- | --- |
| Taxable | 5,537.00 |
| GST 18% | 996.66 |
| **Grand total** | **6,533.66** |

**Stock:** 66 DET leave (60 charged + 6 free) and 10 SOAP.

**At approval:** FREE10, BULK5 and BIGORDER each record one use; where a
budget is set, FREE10 counts 6 free units, BULK5 378.00 and BIGORDER 200.00
against it.

**What changes it:**

| Change | Effect |
| --- | --- |
| Type Disc % 5 on DET | DET takes 252.00 instead of 378.00 and BULK5 is skipped on that line; BIGORDER still applies. |
| Type Free 0 on DET | no free goods; everything else the same. |
| Type 100 as the whole-order discount | 100 comes off instead of BIGORDER's 200. |
| Add coupon `WELCOME10` | nothing -- BIGORDER ended the stack before WELCOME (40). |
| Firm in Best offer mode | only the single most valuable of the matching offers applies. |
| The delivery note and the bill | inherit all of the above, pro-rated by the quantity shipped and billed; nothing is priced again. |

## 20. Who pays for an offer, where to see it, and claiming it back

### Who bears the cost

| **Funded by principal** on the offer | Who pays |
| --- | --- |
| Empty | The firm, all of it. A discount lowers what is billed; free goods leave stock at no charge. |
| A principal with a share % | The customer still gets the whole offer. That share is owed to the firm by the principal; the rest is the firm's cost. At 50% on a discount of 100, 50 is claimable and 50 is the firm's. |
| A principal at 100% | The whole offer is claimable. It costs the firm nothing once the principal settles. |

Until the principal pays or gives credit, the firm carries the full amount.

The list offers only the firm's own **Principals** (the master that brands are
filed under). A firm with no principal sees no name to choose: add one first,
with the supplier it is bought through, then set it on the offer with its
share %.

### Where to see what offers and discounts cost

All under **Reports**.

| Question | Report | Shows |
| --- | --- | --- |
| What has each offer cost in all? | **Promotion performance** | Per offer: customers, Benefit (money given), Free units, limit and budget left |
| The same, for a date range | **Discount given by offer** | Claims, customers, Given, Free units given, costliest first |
| Which document took which offer? | **Promotion claims** | One row per claim: offer, coupon, customer, amount given, free units |
| What did each coupon cost? | **Coupon performance** | Per code: times claimed, customers, benefit, free units, uses left |
| All discount, not only offers | **Discount given by customer / salesman / product** | Gross, then Typed, Arranged (price list or standing rate), Offers, Bill discount, Total and % of gross |
| Promotional items as stock | **Free goods** | Only products marked **free issue only**: received per supplier and scheme, written off as given free or as a sample (at cost), and still on hand. Free units an offer gave of an ordinary product are **not** here -- they are in the promotion reports above. |

An offer's use is counted when the order is **approved**, so a draft shows
nothing in the promotion reports. The three *Discount given by ...* reports read
**bills**, so an order not yet billed is not in them. The promotion reports
show free goods as a quantity, not as money.

### Claiming a principal's share back

**Principal Claims** (type "principal claim" in the command box).

1. **+ New** -- "New claim on a principal". Choose the principal and the
   period. The screen shows what the period holds before anything is saved:
   the principal's share of the offers passed on, with expired and broken
   stock of that principal where there is any. With nothing to claim it says
   so and raises no claim.
2. **Save.** The claim takes a number, shows its Total and Outstanding in the
   grid, and posts to the ledger: the principal now owes the firm that amount.
3. **Print statement** -- the paper sent to the principal, with the lines
   behind the total.
4. Record how it is settled, in part or in full:
   - **Record payment** -- the principal pays money.
   - **Settle by credit note** -- the principal gives credit, set against the
     open purchase bills of the supplier that principal is bought through.
5. **Reverse payment** takes a recorded payment off again; **Cancel** cancels
   the claim with a reason.

Rules worth knowing:

- A source is claimed **once**. A second claim over the same period holds only
  what the first did not.
- Goods or discounts that come back after a claim (a sales return) come off
  the **next** claim on that principal; a claim is never raised for less than
  nothing.
- Only what an **offer** gave is claimed. Free quantity typed by hand on a
  line is not (the note on TC-INCENT-012).
- **Price cut claim** on the same screen is a different claim: the principal
  lowered its price and owes the difference on stock still in hand.

### A discount the supplier gives on a purchase

This is neither a loss nor a claim: it lowers what the firm pays.

| Case | Who bears it | What to do |
| --- | --- | --- |
| The firm gives a customer a discount of its own | The firm | Nothing to claim |
| The firm gives a customer a discount on the principal's scheme | The principal, for its share | *Funded by principal* on the offer, then a Principal Claim |
| The supplier gives a discount on the purchase bill | Nobody; the purchase cost is lower | Nothing to claim -- it is already off the bill |
| The supplier pays a target or turnover discount later, by credit note | The supplier | **Supplier Rebates** |

**Recording it.** A regular arrangement goes in a supplier price list (with
quantity breaks), a rate contract or the supplier's standing discount; leave
the discount blank on the purchase order and it fills in. A one-time discount
is typed on the order line or as a whole-order discount.

**It does not change the selling price.** A supplier price list and a
customer price list are separate. Buying cheaper leaves the selling price
where the firm set it, so the discount becomes margin unless the firm passes
it on with its own sales offer or price list. Tea that costs 100 and sells at
120 earns 20; bought at 95 it earns 25 at the same price, or 20 at 115.

**Old stock and new stock.** Cost is one moving average per product: 100
units bought at 100 and 100 more at 95 are 200 units at 97.50, and every sale
takes its cost at that average whichever pack leaves. The selling price is
per product, not per purchase lot. So nothing has to be chosen at billing --
but a firm that drops its price by the whole 5% while the older stock is
still on the shelf has a thinner margin than it expects. An offer with dates
passes a benefit on and ends by itself. A line priced below cost or below the
product's minimum price warns, and blocks only where the firm asks.

**Free goods move stock like charged goods.** On a sale, the free quantity is
reserved at approval and leaves at dispatch (10 + 1 free takes 11); a free
product of another kind is its own line, quantity 0, free n, worth nothing
and taxed nothing. On a purchase the same shapes bring stock in: accepted
plus free on the receipt, billed at zero. A supplier's free goods are not
passed to customers automatically, nor the reverse.
