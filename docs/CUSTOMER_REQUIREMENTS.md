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
| SUP-3 | Add a new branch while recording goods received | The order is on the company and the goods can come from a branch not entered yet: a **New branch** button beside *Received from* on the goods receipt, already set as a branch of that company. A bill raised against an order has a **Billed by** box and the same button | Built | F9 |
| SUP-4 | One GST number, one supplier | The customers' rule (CUS-3) for suppliers and their branches: a branch leaves it blank to use its main office's, or types its own | Built | F5 |
| SUP-5 | The brands a supplier may sell | Ticked on the supplier. A stockist is a supplier with several companies' brands | Built | M11 |
| SUP-6 | Buys in boxes and pieces, per supplier | A tick on the supplier, as CUS-6 | Planned | L5 |

## 4. Products

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| PRD-1 | Company, brand, product | A company has many brands; a product is under one brand | Built | M11 |
| PRD-2 | A product always has a brand, a brand always a company | Neither can be saved without its parent. Products with none before this went under *Unbranded* (one with a brand typed kept that brand), brands with none under *General*, to be moved by the owner; the product list has an *Unbranded* filter | Built | F7 |
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
| LIC-5 | Shops under a parent | A shop's own licence first; where it has none of that type, its parent's counts and the check says so. A shop that holds one of its own, even a lapsed one, is checked on its own. A firm setting, *A shop must hold its own licence*, makes each shop hold its own. Suppliers' branches the same way | Built | F8 |
| LIC-6 | A product needing several licences | A product, or its category, names a list of licence types, with no fixed size. The customer must hold every one, each valid on the bill's date; the check names each one missing. A shop's two drug licences are two entries on the customer | Planned | P3 |

## 6. Buying

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| BUY-1 | Plan an order for one company | Every product of the company's brands, with a suggested quantity: average sold per day x days of stock wanted, less stock in hand, less open orders | Built | M12 |
| BUY-2 | The plan reads six months by default and can be raised | Opens on the last six months (180 days); one month, three months and a year one click away; quantities raised line by line or all at once by a percentage, rounded up to the supplier's pack | Built | F11 |
| BUY-3 | Narrow the product list by brand | A Brand box on the purchase order, starting at the supplier's brands | Built | M11 |
| BUY-4 | Every purchase line is a lot | See section 7 | Building | L2 |
| BUY-5 | Scan a paper from the scanner and keep it with the document | A **Scan** button where a file is attached: the pages are taken from the scanner and kept as one PDF. Mostly for a supplier's bill, and for the firm's own bill after the customer has signed it. Today a file is attached from a folder after scanning it apart. The scanner is one on the computer, chosen in the application from those Windows knows. Backlog 145 | Later | |

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
| PRT-2 | Half or full page | The firm chooses. Full page: every bill is a full page. Half page: a customer may be set to full page, the person printing may switch that one print, and a bill that does not fit moves to a full page by itself. The screen says which paper the bill needs before it prints, since the tray holds half sheets | Built, but for the choice at printing, which is Planned | S13, P1 |
| PRT-3 | Boxes and pieces on the print | In the quantity cell as the customer's own bill prints them, with the box size added: **3/5 (x12)**; free goods **0/2**. May be changed later | Planned | L5 |
| PRT-4 | Full-page bill as the customer's sample | A manufacture date column, filled only where the lot has one; the total quantity under the lines; the firm's terms at the foot; Order By (the salesman) and Market (the route). The customer's licence numbers stay under his details at the top. The interest line of the sample is words in the terms: no interest is worked out. The sample's discount boxes D1, D2 and D3 wait for the customer | Planned | P2 |
| PRT-7 | The bill number | One series for the whole firm, as the sample: the series word and a running number. The customer confirms it | Decided | |
| PRT-9 | Print from each row of the bill list | A **Print** on every row of the list of bills, where today printing is reached from the bar above the list or from the open bill. Low priority (the owner, 2026-10-13): which other lists get it is decided at the end | Later | |
| PRT-10 | A dot matrix printer | Not needed by this customer, who prints on cut A4 sheets. For a later customer: printing in plain text, sized for continuous paper. Backlog 146 | Later | |
| PRT-8 | Order By | The bill's salesman. The salesman list also holds entries such as *Phone order* and *Company staff*, which earn no commission | Decided | P2 |
| PRT-5 | Bill layout settings | The bill in fixed parts (header, lines, summary, footer), how many lines a page shows, and a rule for long shop and product names | Later | F12 |
| PRT-6 | A code on the bill to pay by scanning | The firm's UPI ID is entered once (the bill's Print settings, or the bank account marked to print). Every printed bill, full page, half page and roll, then carries a QR code for what the bill still owes; any UPI app reads it with the amount and the bill number filled in. No gateway and no internet. The money is not recorded by itself: the receipt is still typed. A link that marks the bill paid needs a gateway account and is not built (backlog 51 B4) | Built | |

## 11. Collections and money

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| COL-1 | The customer's account as a table | Rows with a running balance; a last row adds a receipt, on account or against one bill | Built | M3 |
| COL-2 | All rows, and a download | An **All** choice beside 20, 50, 100, read in pages as the rows are scrolled; an Excel download of the rows of the choice; the choice remembered per user on the machine | Built | F10 |
| COL-3 | Bills handed to a collector | Handed over by ticking, or by date, area, or a run of bill numbers; taken back the same way. It never touches the books | Built | M4 |
| COL-4 | A bill collector's own screen | A ready-made role that sees one screen: his bills, by customer, with that customer's older unpaid bills marked apart | Built | M5 |
| COL-5 | End-of-day return | Each bill out: collected, part, promised, not collected. A firm switch, off to start, decides whether his line records the receipt or the office confirms it | Built | M6 |
| COL-6 | One receipt from a parent over its shops' bills | A parent's receipt lists the bills of every shop under it; a shop can still pay for itself | Built | M8 |
| COL-7 | Discount at collection | The owner waives part of a due as discount, GST unchanged, within a firm ceiling | Built | S10 |
| COL-8 | Only the firm admin gives it | A permission of its own, held by the firm admin alone | Built | F4 |
| COL-9 | A collector's phone app | Morning sync, marking during the day with no connection, evening sync back by Wi-Fi, Bluetooth or a file. Office entry stays | Later | F12 |
| COL-10 | Print a cheque for a supplier's payment | A payment saved with the mode Cheque has **Print cheque**: the date, the supplier's name (another can be typed), the amount in words and in figures, onto the bank's own cheque leaf. Each bank account is lined up once with a test print | Built | |
| COL-11 | A cheque to any account, the amount typed, dated today or ahead | **Write a cheque**: the bank account it is drawn on, the account it pays (a supplier, a customer for a refund, an expense, any other account), the name on the cheque, the amount, the cheque number and its date. Dated today or before, it is saved as a payment and printed. Dated ahead, it is printed now and held as a post-dated cheque: nothing is posted until its date, when it becomes the payment. A cheque is never printed without a record of it | Planned (the server is built, the screen is not) | F13 |
| COL-12 | One customer pays another customer's bill | Two independent shops. The receipt has **Paid by**: the bill is closed, the bill's customer's account reads *Paid by* the other and the payer's reads *Paid for* this one. A customer's money on account can be used for another's bill the same way | Planned | P5 |
| COL-13 | Who pays for a shop under a parent | Either: the parent office for its shops (COL-6), or the shop for itself. To be tried on a running firm | Built, to be checked | C5 |

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
| USR-3 | An account per employee for salary advances | No payroll. Each employee has an account under *Staff advances*; an advance is paid from cash or a bank, recovered when the salary is paid, and a list shows what each still owes | Planned | P4 |

## 16. Coming from the old program

Plan: `docs/SWATHI_IMPORT_PLAN.md`. **Not started**; it waits for the
customer to agree, and the smaller firm goes first.

| No. | Requirement | How it works | Status | Row |
| --- | --- | --- | --- | --- |
| IMP-1 | Masters and opening figures brought across | Products, customers, suppliers, opening bills, opening stock by lot, opening balances | Later | |
| IMP-2 | Old bills kept for reference | As history bills: stored as issued, moving no stock and no books. Wanted as a record for audit; how many years is the customer's to say | Later | |
| IMP-4 | The start date | Not fixed (the owner, 2026-10-13): the application is tested first, then the import, then the customer tries it. A start in the middle of a year is possible: the year's bills up to that day come in as history and the books open from that day's figures | Open | |
| IMP-3 | The working year | A filter, not a wall: all years in one place, every list opens on the current year, an older bill is reached by widening the dates. Old years archived when they grow is backlog 147 | Planned | P6 |

## 17. Open questions

**For the customer**

| For | Question |
| --- | --- |
| PRT-4 | On the sample bill: what the boxes D1, D2 and D3 mean and when each is filled; what the letter B under the lines of one bill and the nought near Net Payable are |
| PRT-7 | Whether one series in the present form is right, or the year should be inside the number |
| IMP-2 | What he needs from the old years, how many years back, and whether the other backups and a fresh one can be given |
| IMP-1 | Two printouts from the old program for the larger firm: the opening trial balance and the customers' outstanding, because the opening figures in the backup do not agree |
| REP-2 | Samples of the reports he takes every day, and what the accountant asks for each month |
| REP-2 | Whether the accountant works in Tally; what he needs at the year's end (which statements, in what form), and whether he wants a closing statement |
| TAX-2 | Which bills he means by reverse charge: transport, or goods he sells |
| USR-2 | What each kind of staff must not see or do: cost and margin, discount, editing or cancelling a bill, the books, receipts and cash, prices and masters |
| PRT-5 | How many lines on a half page and on a full page, and how a long shop or product name should print. Answered already: plain A4 cut in two, on a sheet printer |
| COL-9 | Which phones the collectors carry, whether they may join the office Wi-Fi, and whether a receipt is handed over at the shop |

**For the accountant**

| For | Question |
| --- | --- |
| STK-3 | That the cost of a sale is the cost of the lots actually sold |
| STK-7 | The treatment of a supplier's bill at another rate than the receipt |

**For the owner**

| For | Question |
| --- | --- |
| IMP-4 | The start date, once the application and the import are tested |
| CUS-8 | Which GST provider, at what price |
| COL-9 | The go-ahead to write the design note for the collector's phone app |
| COL-12 | That paying for another customer needs no right of its own, only a question on the screen |
| BUY-5 | The word to build the Scan button |

## 18. Changes to this document

| Date | Change |
| --- | --- |
| 2026-10-13 | First written, from the review of 2026-10-12, the sample bills and the owner's answers of the day |
| 2026-10-13 | COL-8 built (F4): the discount at collection has a permission of its own, the firm admin's alone |
| 2026-10-13 | SUP-4 built (F5): a supplier's GST number is held once; a branch takes its main office's or types its own |
| 2026-10-13 | CUS-8 logged (F6) as backlog 137, open and not built: it waits on the provider and its price, which are the owner's to choose. Status stays Later |
| 2026-10-13 | PRD-2 built (F7): a product cannot be saved without a brand, nor a brand without a company; what was there before is filed under *Unbranded* and *General* |
| 2026-10-13 | LIC-5 built (F8): a shop with no licence of the kind needed is covered by its parent's and the check says so; a firm setting makes each shop hold its own. The question to the customer stays open: the setting is how the firm answers it |
| 2026-10-13 | SUP-3 built (F9): a new branch of the supplier is added from the goods receipt, and from a bill raised against an order, without leaving the document |
| 2026-10-13 | COL-2 built (F10): the customer's Account view shows the whole account, downloads to Excel and remembers how many entries each user chose |
| 2026-10-13 | BUY-2 built (F11): Plan an order opens on the last six months of sales, and every suggested quantity can be raised by a percentage at once |
| 2026-10-13 | PRT-6 and COL-10 added as Built: the owner asked for a pay-by-scan code on the bill and for cheque printing, and both were already there. COL-11 added (the owner): a cheque to any account with the amount typed, post-dated too; row F13 |
| 2026-10-13 | PRT-5 and COL-9 logged (F12) as backlog 143 and 144, open and not built. PRT-5 waits on the customer's answers about his paper and printer; COL-9 needs a design note first. Both stay Later |
| 2026-10-13 | The walk through of the sample bills and the backups with the owner: PRT-2 restated (the firm chooses; the choice at printing is row P1), PRT-4 decided and Planned (row P2), PRT-7, PRT-8, BUY-5 (backlog 145), PRT-9 (low priority) and IMP-4 added, IMP-2 is for audit. Five questions for the customer added to section 17 |
| 2026-10-13 | The customer question list gone through with the owner. Decided by him: LIC-6 a product may need several licences (row P3); USR-3 an account per employee for advances (P4); COL-12 one customer pays another's bill (P5); IMP-3 the working year is a filter (P6); COL-13 a shop or its parent pays (check C5); the scanner is one on the computer (BUY-5); PRT-10 a dot matrix printer logged as backlog 146, old years archived as backlog 147. Section 17 holds only what is still the customer's |
| 2026-10-13 | Notifications (who is told about what on the bell) taken off the customer's questions: the owner defines them when the firm's users are created |
| 2026-10-14 | COL-11, the server half (F13, backlog 150): a cheque can be written to a supplier, a customer, an expense or any other account, recorded at once when dated today and held when dated ahead, and printed from its record. The screen is not built, so the status stays Planned |
