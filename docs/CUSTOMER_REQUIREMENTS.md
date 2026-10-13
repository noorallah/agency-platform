# First customer: requirements

**One place for what the first customer needs, section by section.** Started
2026-10-13 from the requirements review of 2026-10-12, the customer's sample
bills and old data, and the owner's answers on 2026-10-13. It is kept up to
date: when a requirement is added, changed or built, its row here changes in
the same work.

## How to read this

Each requirement has a number that never changes (for example `SEL-4`), what
is wanted, how it works as decided, and its status.

| Status | Means |
| --- | --- |
| **Built** | In the application. Tried by the build loop over HTTP; not yet clicked through by hand unless the row says so |
| **Building** | Being built now |
| **Planned** | Decided and in the build list, not started |
| **Later** | Wanted, recorded in the backlog, not scheduled |
| **Open** | Waits for an answer; section 17 says from whom |

The last column names the row of `docs/CUSTOMER_BUILD_TASKS.md` that carries
the work; that file holds the detail and the pull request of each row. The
three large designs are in `docs/design/`.

The customer runs two distribution firms, selling hardware, paints and
medicines to shops, and comes from an older billing program. No customer
name, GST number or bank detail is written in this file.

## 1. Firm set-up and accounts

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| SET-1 | Ready-made accounts for owner's capital and drawings, transport, fuel and petty cash | Every firm has them; a firm that already had some got only the missing ones | Built | S1 |
| SET-2 | Each document type decides whether it needs approval | A switch per document on the selling side (order, delivery note, bill) and the buying side (order, goods receipt, supplier's bill). Off, one Save completes the document and its author is who approved it | Built | M1, M2 |
| SET-3 | Paying out of cash that is not there | Cash and Petty Cash ask "Save anyway?" when a payment would take them below zero. Never a block. Bank accounts are not asked | Built | F2 |
| SET-4 | A second copy of every backup | A copy in a second folder (another drive or a cloud-synced folder), password-protected, the last ten days kept | Built | S7 |
| SET-5 | Starting a new financial year | A **Start next year** button makes the year and its months; bill numbers restart by themselves on the first day | Built | C3 |

## 2. Customers

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| CUS-1 | Tell apart two customers of the same name | Area and city are shown beside the name in every picker and list. Never on a print | Built | S3 |
| CUS-2 | A parent buyer with several shops | A customer can be a **Shop of** another. One level only | Built | M7 |
| CUS-3 | One GST number, one customer | A number is held by one customer. A shop leaves it blank to use its parent's, or types its own. Two customers with no parent between them can never share one. A number removed becomes free again | Built | M7 |
| CUS-4 | Credit limit | Per firm: warn and ask, or warn near the limit and refuse at it. The screen asks; the server decides | Built | S2 |
| CUS-5 | Retailer or wholesaler | A customer is marked one or the other; a new bill starts with that (see PRC-3) | Built, to be joined to lot prices | M13, L3 |
| CUS-6 | Bills in boxes and pieces, per customer | A tick on the customer; a new bill for him opens with box and piece cells (see SEL-6) | Planned | L5 |
| CUS-7 | Licences a customer holds | Several per customer, each with its type, number and validity (see LIC-1) | Built | S11 |
| CUS-8 | Fetch a customer's details from the GST system by number | Name, address, state and registration status filled in from a provider. Off until a firm enters its own provider account | Later | F6 |

## 3. Suppliers

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| SUP-1 | A supplier company with branches | The company is the main supplier; a branch is a supplier marked **Branch of** it, with its own GST number. Order on the main office, goods and bills from any branch, payment to either | Built | M9 |
| SUP-2 | Add a supplier while typing a purchase | A button on a new purchase order and on a supplier's bill typed directly | Built | M10 |
| SUP-3 | Add a new branch while recording goods received | The order is on the company and the goods can come from a branch not entered yet: a **New branch** button beside *Received from*, already set as a branch of that company | Planned | F9 |
| SUP-4 | One GST number, one supplier | The customers' rule (CUS-3) for suppliers and their branches: a branch leaves it blank to use its main office's, or types its own | Built | F5 |
| SUP-5 | The brands a supplier may sell | Ticked on the supplier. A stockist is a supplier with several companies' brands | Built | M11 |
| SUP-6 | Buys in boxes and pieces, per supplier | A tick on the supplier, as CUS-6 | Planned | L5 |

## 4. Products

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| PRD-1 | Company, brand, product | A company has many brands; a product is under one brand | Built | M11 |
| PRD-2 | A product always has a brand, a brand always a company | Neither can be saved without its parent. Products with none today go under *Unbranded*, brands with none under *General*, to be moved by the owner | Planned | F7 |
| PRD-3 | Goods type | The kind of goods (medicine, food, hardware). It decides batch, expiry, serial number, the extra fields and which are compulsory, the usual HSN and GST, and the starting margins. Kept per firm, not per company | Built (margins: Planned) | L3 |
| PRD-4 | Product category | The firm's own grouping, with levels, for finding, reports, offers and the licence needed. Separate from the goods type | Built | |
| PRD-5 | One box size per item | An item has a piece and a box and no third level. A supply packed differently is still counted by the item's own box | Decided | L5 |

## 5. Licences

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| LIC-1 | Some goods may be sold only to a licence holder | A product, or its category, names the licence type needed. The check is per line: a bill of goods needing none is not checked at all | Built | S11 |
| LIC-2 | Licence expiry | Judged on the bill's own date when an order, delivery note or bill is approved | Built | S11 |
| LIC-3 | Warn or stop | A firm setting: off, warn, or block. A blocked sale can be passed by someone with the right, giving a reason | Built | S11 |
| LIC-4 | The firm's own licence numbers on the bill | Printed under the firm's address | Built | S11 |
| LIC-5 | Shops under a parent | A shop's own licence first; where it has none of that type, its parent's counts and the check says so. A firm setting makes each shop hold its own | Planned | F8 |
| LIC-6 | A product needing two licences | Whether a medicine needs two separate licences both valid | Open | |

## 6. Buying

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| BUY-1 | Plan an order for one company | Every product of the company's brands, with a suggested quantity: average sold per day x days of stock wanted, less stock in hand, less open orders | Built | M12 |
| BUY-2 | The plan reads six months by default and can be raised | Opens on the last six months; other periods one click away; quantities raised line by line or all at once by a percentage | Planned | F11 |
| BUY-3 | Narrow the product list by brand | A Brand box on the purchase order, starting at the supplier's brands | Built | M11 |
| BUY-4 | Every purchase line is a lot | See section 7 | Building | L2 |

## 7. Stock and lots

Design: `docs/design/LOT_COST_DESIGN.md`.

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| STK-1 | Each purchase line is a lot with its own cost and prices | Made when the goods are received. A second delivery of the same printed batch at another cost is a second lot | Building | L2 |
| STK-2 | Lot and batch number | The list is called **Lots**; **Batch no.** is the maker's printed number, a field of the lot that may be blank. Goods with no batch get our own lot number | Building | L2 |
| STK-3 | Cost of a sale | Per firm: **By lot** (preferred; the cost of the lots actually sold) or **Average** (as today). New firms start By lot; firms trading today stay on Average until switched | Building | L2 |
| STK-4 | Switching a firm to By lot | Any day, one way. Stock is carried in at that day's average; nothing is re-valued; bills already made keep their price and cost | Planned | L2 |
| STK-5 | Which lot leaves first | Nearest expiry, then oldest. The bill maker may pick another | Planned | L2 |
| STK-6 | A return traces to the supplier's bill | The sales line keeps its lot; a return goes back into that lot at the cost it left with | Planned | L2 |
| STK-7 | A supplier's bill at another rate than the receipt | The lot is corrected for what is still in stock; the share already sold goes to price difference | Planned | L2 |
| STK-8 | Billing without stock | Refused by default. A firm may allow it; then the bill maker is asked, the sale takes the last purchase cost for now and is settled when the purchase is typed. A report lists bills waiting for their cost | Planned | L2 |
| STK-9 | Stock value at MRP beside value at cost | On the stock valuation report | Built | S4 |
| STK-10 | Stock shown as boxes and pieces | A **Show boxes** toggle on the stock screens and reports; display only | Planned | L5 |

## 8. Prices, margins and offers

Design: `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`.

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| PRC-1 | Two margins on the purchase price | Retail and wholesale, on each product; the goods type gives a new product its starting pair | Planned | L3 |
| PRC-2 | Margins changeable per lot | Both can be changed on the purchase line, for that lot only. Every lot has a retail price and a wholesale price, GST on top. A price above MRP warns | Planned | L3 |
| PRC-3 | Retail or wholesale on the bill | A new bill starts with the customer's kind; one switch changes the whole bill | Built on price levels; to read lot prices | M13, L3 |
| PRC-4 | No rounding of an item's price | The worked-out price stays exact; the bill total is rounded instead (SEL-8) | Decided | L3 |
| PRC-5 | Cost and margin on the bill line | On screen only, to users allowed to see cost. Never on a print | Planned | L3 |
| PRC-6 | Offers and discounts listed on the line | Every offer, price-list discount and standing discount that fits is listed; one is applied to start (offers, then price list, then the customer's own) and the bill maker can tick another | Planned | L7 |
| PRC-7 | One discount source a line | Discounts from two sources are not added. Free goods can sit beside any | Decided | L7 |
| PRC-8 | "Best offer only" works per line | Each item gets its own best scheme | Planned | L7 |
| PRC-9 | "Buy N more to get ..." | Shown as a hint on the line | Planned | L7 |
| PRC-10 | Part of an offer | A switch on each "buy N get M free" offer of the same item. 5.5 charged + 0.5 free is allowed where the total is whole pieces | Planned | L7 |
| PRC-11 | Who may change the offer applied | A permission given to every role that makes bills; each change recorded | Planned | L7 |
| PRC-12 | Discount limit per role | One largest discount per role, judged by the server | Built | S9 |

## 9. Selling and billing

Design: `docs/design/BOX_AND_PIECE_LINE_DESIGN.md`.

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| SEL-1 | Bill in one step | With approval off, one Save bills, ships and posts (SET-2) | Built | M1 |
| SEL-2 | Narrow the product list by company or brand | A Brand box on the order and the bill. It shortens the list and refuses nothing | Built | M11 |
| SEL-3 | Billing and shipping address | The customer's default, or any of his addresses; printed apart | Built | C1 |
| SEL-4 | Rate typed including GST | Per document. The line totals exactly quantity x the rate typed, with the tax taken out of that | Built | C2, F1 |
| SEL-5 | Boxes and pieces on one line | 10 boxes + 5 pieces typed in two cells; free goods the same way. Stored as one quantity in pieces; boxes are always full boxes (2 + 17 of a 12-pack becomes 3 + 5) | Planned | L5 |
| SEL-6 | Who gets the box cells | The firm switches it on (selling and buying apart); then a customer's or supplier's tick decides how a new document opens; a toggle on the document changes it; the document keeps its choice and reopens in it | Planned | L5 |
| SEL-7 | Rate always per piece | The rate of a box is shown, never typed | Decided | L5 |
| SEL-8 | Round the bill to the nearest rupee | A firm setting. On, every bill and credit note is rounded and shows the round-off line. Off, the bill is left as worked out | Built | F3 |
| SEL-9 | Choose the lot at billing | Lots listed with price, batch and expiry, nearest expiry first (STK-5) | Planned | L2 |

## 10. Bill print

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| PRT-1 | Half-page bill as the customer's sample | Half of A4; MRP, quantity, free, rate, discount, GST, net amount, batch and expiry; a GST summary and round-off | Built | S13 |
| PRT-2 | Half or full page | Per firm and per customer; a bill that does not fit moves to a full page by itself | Built | S13 |
| PRT-3 | Boxes and pieces on the print | In the quantity cell as the customer's own bill prints them, with the box size added: **3/5 (x12)**; free goods **0/2**. May be changed later | Planned | L5 |
| PRT-4 | Full-page bill as the customer's sample | To compare with his sample: manufacture date column, total quantity, where the customer's licence numbers print | Open | |
| PRT-5 | Bill layout settings | The bill in fixed parts (header, lines, summary, footer), how many lines a page shows, and a rule for long shop and product names | Later | F12 |

## 11. Collections and money

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| COL-1 | The customer's account as a table | Rows with a running balance; a last row adds a receipt, on account or against one bill | Built | M3 |
| COL-2 | All rows, and a download | An **All** choice beside 20, 50, 100; an Excel download; the choice remembered per user | Planned | F10 |
| COL-3 | Bills handed to a collector | Handed over by ticking, or by date, area, or a run of bill numbers; taken back the same way. It never touches the books | Built | M4 |
| COL-4 | A bill collector's own screen | A ready-made role that sees one screen: his bills, by customer, with that customer's older unpaid bills marked apart | Built | M5 |
| COL-5 | End-of-day return | Each bill out: collected, part, promised, not collected. A firm switch, off to start, decides whether his line records the receipt or the office confirms it | Built | M6 |
| COL-6 | One receipt from a parent over its shops' bills | A parent's receipt lists the bills of every shop under it; a shop can still pay for itself | Built | M8 |
| COL-7 | Discount at collection | The owner waives part of a due as discount, GST unchanged, within a firm ceiling | Built | S10 |
| COL-8 | Only the firm admin gives it | A permission of its own, held by the firm admin alone | Built | F4 |
| COL-9 | A collector's phone app | Morning sync, marking during the day with no connection, evening sync back by Wi-Fi, Bluetooth or a file. Office entry stays | Later | F12 |

## 12. Tax

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| TAX-1 | TDS and TCS per party | A switch on each supplier and customer, and another figure can be typed on one bill | Built | S8 |
| TAX-2 | Reverse charge set-up | Not yet described by the customer | Open | |

## 13. Commission

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| COM-1 | A slab pays a fixed amount or a percentage | A choice on each slab | Built | S5 |
| COM-2 | A period of any length | A start date and a number of days | Built | S6 |

## 14. Reports

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| REP-1 | Excel download on every report and statement | A Download button on each; figures as numbers | Built | S12 |
| REP-2 | Year-end workbook for the accountant | Which statements and what layout | Open | |

## 15. Users

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| USR-1 | A collector sees only his bills | His own screen only (COL-4). Limiting every list and report to a user's own customers is not built | Built | M5 |
| USR-2 | What each role must not see or do | Not yet described by the customer | Open | |
| USR-3 | An account per employee for salary and advances | Not yet described by the customer | Open | |

## 16. Coming from the old program

Plan: `docs/SWATHI_IMPORT_PLAN.md`. **Not started**; it waits for the
customer to agree, and the smaller firm goes first.

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| IMP-1 | Masters and opening figures brought across | Products, customers, suppliers, opening bills, opening stock by lot, opening balances | Later | |
| IMP-2 | Old bills kept for reference | As history bills: stored as issued, moving no stock and no books | Later | |
| IMP-3 | Working financial year selector | A wall between years, or a filter | Open | |

## 17. Open questions

**For the customer**

| For | Question |
| --- | --- |
| LIC-6 | The bill to a medical shop prints two drug licence numbers. Two licences that must both be valid, or one licence with two numbers? |
| LIC-5 | May a parent's licence cover a shop for medicines, where a licence is for one premises? |
| TAX-2 | How reverse charge should be set up |
| REP-2 | Which statements the accountant wants at year end, and in what layout |
| USR-2 | What each role must not see or do |
| USR-3 | Whether each employee needs an account for salary and advances |
| IMP-3 | Whether the working year is a wall or a filter |

**For the accountant**

| For | Question |
| --- | --- |
| STK-3 | That the cost of a sale is the cost of the lots actually sold |
| STK-7 | The treatment of a supplier's bill at another rate than the receipt |

**For the owner**

| For | Question |
| --- | --- |
| PRT-4 | The walk through of the three sample bills, and what the full page must match |
| CUS-8 | Which GST provider, at what price |

## 18. Changes to this document

| Date | Change |
| --- | --- |
| 2026-10-13 | First written, from the review of 2026-10-12, the sample bills and the owner's answers of the day |
| 2026-10-13 | COL-8 built (F4): the discount at collection has a permission of its own, the firm admin's alone |
| 2026-10-13 | SUP-4 built (F5): a supplier's GST number is held once; a branch takes its main office's or types its own |
| 2026-10-13 | CUS-8 logged (F6) as backlog 137, open and not built: it waits on the provider and its price, which are the owner's to choose. Status stays Later |
