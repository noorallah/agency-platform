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
and the `selling-firm` test fixture. `docs/PRICING_AND_PROMOTIONS.md` holds
the engineering rules behind it.

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

Sell → Pricing → **Promotions** → New.

**Applies when** (every condition must hold; no conditions means every line):
Product, Product category, Product type, Customer, Territory, Route, Quantity
on the line, Line value, Order value. Tests: is, is not, is at least, is more
than, is at most, is less than.

**Gives:**

| Benefit | What it does |
| --- | --- |
| Percent off each line | on every line that met the conditions |
| Amount off each line | never more than what is left of the line |
| Percent off the whole bill | on the bill after line discounts |
| Amount off the whole bill | never more than the bill |
| Free goods (buy X, get Y) | whole multiples only: "buy 10 get 1" on 25 gives **2** free, not 2.5 |

**Other settings:** From / Until dates, Status (only **ACTIVE** applies),
**Other promotions may still apply** (the stacking switch, section 4),
**Only with a coupon**, **Total uses**, **Uses per customer**.

The screen also offers a **free product** (buy X, get a different product
free, added as its own line: pick the product, say how many, and optionally how
many must be bought) and **free delivery**, and can check customer group,
branch, salesman, document type (sales order or quotation) and document date.
Tests include "is one of", "is none of", "is between" (numbers only), "is set"
and "is not set" (D-SELL-42, fixed 2026-09-30).

## 4. Two promotions together: they combine

1. Every ACTIVE promotion in its dates is considered, **lowest "Applies at"
   first** (equal numbers: by code, A before B).
2. Each one whose conditions hold is **applied**.
3. If the one just applied has **Other promotions may still apply** switched
   **off**, nothing after it is considered. That is "ends the stack".
4. **Percentages compound**: each is taken off what is left, not off the
   original. Two 10% offers make 19%, not 20% -- and stacking can never take
   a line below zero.

There is **no "best offer only" mode** and **no maximum discount** setting.
To make one offer exclude another, give it the lower "Applies at" and switch
stacking off. A "best offer only" mode is backlog item 59.

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

With Sales Invoices → ... → **Sales stages** all switched off, a bill typed
straight in raises its order behind the scenes, and that order is priced the
ordinary way, so **automatic promotions apply**, and a **Coupon** box on the new
bill takes the customer's code (D-SELL-40, fixed 2026-09-30). The box is on a
new bill only. Test case TC-PROMO-015 is the check.

## 11. Loyalty points are not a discount

Spending points **pays** part of the bill; it does not lower the price, so
the full GST is still charged. The fixture earns 2 points per 100.
`INDEPENDENT_TEST_CASES.md` TC-INCENT-005 is the case.

## 12. Setting up offers, step by step

Everything is under **Sell → Pricing** (the Configuration part of the Sell
menu): **Price Lists** and **Promotions**. Coupons are on the Promotions page
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
Masters → Parties → **Customer Groups**. Both are last in the ranking.

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
check its side panel. Reports → Operational Reports → **Promotion performance**
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
| **TC-PROMO-015** Direct bill | Sales Invoices → ... → Sales stages: switch all three off. New invoice, C01, DET 30, no source | 7.5% from a promotion; a **Coupon** box is on the new bill (D-SELL-40) |
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

| Id | Gap |
| --- | --- |
| Backlog 59 | No "best offer only" mode: matching promotions always combine. |
| Backlog 60 | Offer types still missing against market practice -- buy X get Y at a discount, combo prices, festival bonus points, bulk coupon codes, first-order offers, offer templates, scheme claims, offers on the print. |

**Percent off, up to a limit (2026-10-01).** A percentage benefit -- on the line or on the bill -- takes an optional **Up to**: "20% off, up to 500" never takes more than 500 off the document. On line percentages the 500 is shared across the lines the offer matched, in proportion to what each would have had, so the lines still add up to exactly 500. Blank means no limit.
