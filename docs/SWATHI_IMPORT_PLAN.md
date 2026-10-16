# Importing from Swathi: plan

**Status: plan, written 2026-10-12. Nothing in it is built, and the build is
not started** (owner, 2026-10-12: kept separately, to be checked with the
customer first). It is not part of `docs/CUSTOMER_BUILD_TASKS.md`. It records
what the first customer's old software holds, how each part reaches our app,
what is in the way, and the order to build in. The gaps it lists are worked
one by one; update the status column as each closes.

The backups it was written from are kept outside this repository, in
`D:\ws\customerdata`. They hold a portal password in plain text and real
customer records, so they are never copied into the repository, and this
document names no customer, GST number or bank account.

## 1. What Swathi gives us

A backup is one **MySQL 5.7 dump** (`mysqldump`, a `.sql` file) per firm per
financial year. Restoring it needs any MySQL 5.7 or 8 server; reading it needs
no server at all, because the file is plain `CREATE TABLE` and `INSERT`
statements.

The first customer is **two firms** at one address, each with its own GST
number and books. Fifteen yearly databases exist; three were handed over
(the larger firm for 2025-26 to mid September, the smaller firm for 2023-24
and for 2025-26 to mid September).

**The smaller firm goes first, and the larger one follows only when that has
gone well** (owner, 2026-10-12). The smaller firm is the easy case: 56 items
from one principal, one GST rate, 306 customers, 782 sales bills and 50
purchase bills in five and a half months, and nearly every purchase line
carries a batch. The larger firm adds three GST rates, eleven principals,
free goods on a quarter of its lines and lots with no batch.

Size of the larger firm, five and a half months: 2,371 sales bills with 6,645
lines, 237 purchase bills with 1,490 lines, 2,844 receipts, 289 return lines,
767 customers, 434 items.

### The tables that matter

| Swathi table | Holds | Notes |
| --- | --- | --- |
| `firm` | The firm itself | The name is stored with each letter shifted by one; everything else is plain |
| `company` | The principals whose goods are sold | Also the bill series: a bill number prints as series name + running number |
| `codehead` | Brand heads under a principal | |
| `codes` | Every account: customers, suppliers, banks, expenses | `hcode` names the head; customers are heads 8 and 28 |
| `acchead` | The 29 account heads | Balance sheet, trading or profit and loss |
| `beatman` | Several small masters in one table, told apart by `ctype` | B = beat, O = outlet type, S = salesman, G = HSN group, C = sales account by GST rate, D = return reason |
| `item` | Goods | Name is in two parts; HSN is in `sku`; pieces per case in `nopsc`; unit is blank on every row |
| `phead`, `purch` | Purchase bills and their lines | **Every line is a lot**: its own number (`links`), cost, MRP, batch, expiry |
| `shead`, `sales` | Sales bills and their lines | **Every line names the lot it sold from** (`links`); free quantity is `gift` |
| `receipt` | Money received | Names the bill it pays (`bno` this year, `old` an earlier year); `cdis` is discount given at collection |
| `ohead` | Bills unpaid from earlier years | |
| `returns`, `crdr` | Goods returned, credit notes | |
| `cash`, `contra` | Cash book and bank vouchers | |
| `daily` | Collection sheets: bills handed to a collector for a day | |
| `master` | Stock balances | Empty in every backup; stock has to be worked out |
| `tt_*`, `*_book`, `qhead`, `qsales` | Report work tables | Ignored |

## 2. How the import is built

**One reader, then our own imports.** A reader inside `app/` parses the dump
into rows. A converter per subject turns those rows into the file our
existing import for that subject already takes, and that import does the
checking and the saving. This keeps the rule in `CLAUDE.md`: a file in
another program's layout is mapped onto our template, never read by a sixth
hand-written importer.

- It lives in `app/` and is reached from `app/cli.py` and from a screen,
  because `scripts/` does not reach an installed copy.
- **Check first, write nothing.** Every step lists its problems by record
  before anything is saved, as our imports do today.
- **All or nothing per step**, in one transaction.
- **Safe to run again.** A record already brought in is recognised by its
  Swathi number and skipped, never duplicated. This needs somewhere to keep
  the old number against our record (gap G2).
- **Every Swathi code becomes our code.** Customer `acode`, item `icode` and
  bill number are kept, so a person can still find a record by the number
  they know.

### Steps, in the order they must run

| Step | From | Into | Fits today? |
| --- | --- | --- | --- |
| 1. Firm set-up | `firm`, `company` | Firm, financial year, bill series | By hand on the Firms screen |
| 2. Small masters | `beatman`, `codehead`, `company` | Routes (beats), customer segments (outlet types), salesmen, brands, principals | No import for these (G3) |
| 3. Goods | `item` | Products import | Yes, after a unit is chosen per item (G4), and only once every brand of step 2 is there: a product is refused without a brand the firm keeps, and the import does not make one (backlog 138) |
| 4. Customers | `codes` heads 8, 28 | Customers import | Yes, less beat and licence (G5) |
| 5. Suppliers | `codes` heads 9, 27, 29 | Suppliers import | Yes; about half the rows under these heads are tax and display accounts and go to step 6 |
| 6. Accounts | `codes` other heads, `acchead` | Chart of accounts | No import; mapped by hand once (G6) |
| 7. Opening ledger balances | `codes.opbal` | Opening trial balance | Yes, once it balances (D1) |
| 8. Unpaid bills | `ohead`, and bills of the running year still unpaid | Customer and supplier opening bills import | Yes |
| 9. Opening stock | `purch` lots less what `sales` took from them | Opening stock import | Partly: no MRP or selling price per lot (G1) |
| 10. Bills and receipts | `shead`, `sales`, `phead`, `purch`, `receipt`, `returns`, `crdr` | See section 3 | No |

Steps 1 to 9 are a normal go-live on a start date. Step 10 is the open
question.

## 3. Bills: what is in the way

Our app has a sales invoice import today (`POST /sales-invoices/import`, up
to 500 bills a call). It does not do what is needed here, for these reasons.

1. **An imported bill is a live bill.** It goes through the same path as one
   typed on the screen: stock leaves the warehouse and the ledger is posted.
   So the stock has to be there first, on the right date, in the right lot.
   That means every purchase bill of the year must be imported before the
   sales bills, in date order, with opening stock before both.
2. **Our app works the figures out again.** Price, discount, GST and
   round-off are recalculated by our own rules. These bills were already
   issued and the GST returns for those months already filed, so every
   figure must come out exactly as printed. A difference of one paisa on one
   line changes a return that is closed. There is no "store the figures as
   given" mode today.
3. **Cost is by lot in Swathi and by average in ours.** Each Swathi sales
   line names its purchase lot. Our stock is valued at one running average
   until backlog 101/103 is built, so profit and stock value would not match
   the old books.
4. **Receipts have no import.** 2,844 receipts, most tied to a bill, 810 of
   them with a discount given at collection. Without them every imported
   bill shows as unpaid.
5. **Returns, credit notes and cash vouchers have no file import either.**
6. **Things a live bill sets off must stay quiet:** messages to the customer,
   e-invoice, loyalty points, offers, commission, credit limit warnings,
   approval steps.
7. **The import takes our internal ids**, not codes, and is JSON rather than
   a file. This one is small.

### Two ways to bring bills in

**A. History bills (recommended).** A bill from before the start date is
stored exactly as issued: same number, date, customer, lines, free quantity,
lot, discount, GST and total. It can be searched, opened, reprinted, shown
on the customer's account and used to trace a return. **It moves no stock
and posts nothing to the ledger**; the books start from the opening figures
of steps 7 to 9. Purchase bills, receipts and returns are kept the same way.

- Reasons 1 to 6 above do not arise, because nothing is recalculated and
  nothing is posted.
- It is also the read-only archive of old years already decided on
  2026-10-12, so one piece of work serves both.
- It gives purchase planning (backlog 93) the past sales it averages from.
- New work: somewhere to hold a history bill that the stock, ledger and GST
  screens leave alone (G7), and screens to search and print it.

**B. Replay the year.** Every purchase, sale, return, receipt and voucher
from 1 April is imported as a live document in date order, and our app
builds the books itself.

- Needs: an "as issued" mode (reason 2), cost by lot (reason 3, backlog
  101/103), receipt, return and voucher imports (reasons 4 and 5), and a
  switch that silences reason 6.
- The result has to agree with Swathi's trial balance and stock to the
  rupee before go-live, and every difference has to be explained.
- Only worth it if the firm must start in the middle of a year with no
  closing figures to start from.

**Decided by the owner on 2026-10-12: way A, history bills.** Way B is not
built.

## 3a. What we can offer the customer

Written to be read out or sent. The likely start is the next financial year,
**1 April 2027**, with the old years brought in as well.

**The start date is not fixed** (the owner, 2026-10-13): the application is
tested first, then this import, and only then is the customer asked to try
it. The old years are wanted as a record for audit, to look up and print.

**On the start date, the firm opens our app and finds:**

- Every customer, supplier and item it has today, under the same code
  numbers it knows.
- Beats, salesmen, outlet types, brands and principals.
- Each customer's unpaid bills, one by one, with bill number, date and due
  date, so collection carries on from the same list.
- What is owed to each supplier, bill by bill.
- Stock in hand by batch and expiry, at its purchase cost.
- The closing balance of every account as the opening balance of the new
  year.

**Old years, to look at and not to change:**

- Every old sales bill, purchase bill, receipt, return and credit note,
  exactly as it was issued, for as many years as backups are given.
- Find a bill by number, customer, date or item; open it; print it again.
- A customer's old account, bill by bill and receipt by receipt.
- A return in the new year can point to the old bill it came from.
- Past sales by item, for planning what to buy.

**What does not come across:**

- Old bills cannot be edited or cancelled in our app. They are a record.
- GST returns of old years are not prepared again from our app. They were
  filed from Swathi and stay as filed.
- Profit and stock reports in our app start from the start date. Old-year
  reports are read from Swathi's own printouts or from the old bills.
- Swathi's users and passwords. People are created afresh.

**Why the start of a year is the best date:**

- The accountant has closed the old year, so the closing figures are final
  and agreed.
- Bill numbers begin from 1 in both programs on the same day.
- No GST month is split between two programs.

**What we need from the firm:**

1. A backup of every year it wants kept, and a fresh backup of the last
   year taken after its final bill.
2. From Swathi, as on the last day: a trial balance, a stock report by
   batch, and the list of unpaid bills per customer and per supplier. We
   check our import against these three, and go live only when they agree.
3. Two or three days before the start to correct the lists we send back:
   customers with no PIN or GST number, items with no MRP, and a unit for
   every item.
4. One trial run some weeks earlier on a copy, so the firm sees its own data
   in our app before the real day.

**If the firm wants to start before April 2027:** the same import works on
any date, but the figures on that date are not closed by the accountant, a
GST month may be split, and bill numbers carry on mid-series. It can be
done; it needs more checking by the firm.

## 4. Gaps to work on

| # | Gap | Needed for | Status |
| --- | --- | --- | --- |
| G1 | Cost and MRP per purchase lot; a sales line names its lot (backlog 101/103) | Step 9, way B, daily billing | Open |
| G2 | Keep the old software's number against our record, so a second run skips it | Every step | Open |
| G3 | Import for routes, segments, salesmen, brands, principals | Step 2 | Open; small enough to create by the converter through the services |
| G4 | A unit for every item (Swathi has none); pieces per case to a pack | Step 3 | Built 2026-10-15 (L5 step 12): the product import's *PiecesPerPack* column (also read as "pieces per case") makes a new item a piece with a box of that many; *PackUnit* names another box unit; one, or blank, is pieces only, and a blank *Unit* on a new item is the piece in every case (owner, 2026-10-15). Every item still needs a brand (backlog 138) |
| G5 | Customer import has no beat and no licence columns | Step 4 | Open |
| G6 | No chart-of-accounts import; 29 heads and about 110 accounts to map | Steps 6, 7 | Open; a mapping table kept per source software |
| G7 | A place for history bills outside stock, ledger and GST | Step 10, way A | Open; design note first |
| G8 | Receipt, return, credit note and voucher imports | Step 10 | Open; as history under A, as live documents under B |
| G9 | Free quantity in fractions on a bill line | Daily billing | Fixed in PR #1425, not merged |
| G10 | Discount given at collection | Daily billing, step 10 | Built (checked 2026-10-16): a receipt carries `discount_amount` (Dr Discount Allowed, Cr Receivables, bill closed, reversible); the receipt screen has the Discount allowed box, prefilled with the cash discount the customer's terms earn (SEL-14); a discount above that is a clearance discount needing `PARTY_ADJUSTMENT_APPROVE` (backlog 115). An imported receipt's `cdis` maps onto `discount_amount`; the receipt import itself is G8 |
| G11 | Bills handed to a collector for a day | Daily work | Open; the bill-and-collector point of 2026-10-12 |
| G12 | Parent buyer with several shops under one GST number | Step 4 (six GST numbers are shared) | Built 2026-10-13 (backlog 125). A shared number is now refused on a second customer: the file names the parent in a **ParentCode** column and leaves the shop's GSTIN blank |
| G13 | Half-page bill print with MRP, PTR, free, batch and expiry columns | Daily billing | Half page built (backlog 118). The full page against the sample is row P2 of `docs/CUSTOMER_BUILD_TASKS.md` |
| G14 | Working financial year selector | Looking at old years | Not decided |
| G15 | Two firms, where the requirement sheet says one | Set-up | Answered 2026-10-12: both move, the smaller first |

Checked and not a gap: a rate to four decimals is held by our bill line; a
shared GST number is accepted; salesman and segment exist on the customer;
principal claims are built.

## 5. Problems in the data

These are in the larger firm's backup; the smaller firm shows the same kinds.

| # | Problem | What the import does |
| --- | --- | --- |
| D1 | Opening balances do not balance: debit 75.75 lakh, credit 66.01 lakh | Refuse step 7 and show the difference; ask the vendor or the accountant which figure is missing |
| D2 | Customer openings total 33.94 lakh but unpaid opening bills total 18.93 lakh | Report it per customer; the firm says which is right |
| D3 | Stock on hand is not stored | Work it out lot by lot and check it against a Swathi stock report before importing |
| D4 | Credit limit is a filler value (999999.99) on almost every customer | Import as no limit |
| D5 | 108 customers have no PIN, 301 no GST number, 46 no city | Import; list them for the firm to complete |
| D6 | 78 items have MRP zero; one item name and one customer name are repeated | Import; list them |
| D7 | Ten bills where the header total and the lines differ by more than a rupee | Under way A the header figure is kept as issued and the bill is listed |
| D8 | The backups are from September 2025 | Take a fresh backup on the day of go-live and run the whole import on it |

## 6. Build order

Every item below is done for the smaller firm first. The larger firm is run
through the same import afterwards, and what it needs beyond the smaller one
is G1 for lots with no batch, G9 and G12.

1. The dump reader and step 3 to 5 converters (goods, customers, suppliers),
   run against the smaller firm into a test firm. Proves the approach and
   gives the firm real lists to correct.
2. G2, G3, G4, G5: the small master gaps.
3. Steps 6 to 8: accounts mapping, opening balances, unpaid bills. Needs D1
   and D2 answered.
4. G7 design note, then history bills, receipts and returns (way A).
5. G1 (backlog 101/103), then step 9, opening stock by lot.
6. A full trial run on a fresh backup, checked against Swathi's own reports:
   trial balance, stock by batch, customer outstanding.

## 7. Questions still open

For the customer or the Swathi vendor:

3. The start date for the smaller firm: 1 April 2027, or earlier (section
   3a).
4. How long the smaller firm runs before the larger one starts.
5. A stock report by batch and a trial balance as on that date, to check
   against.
6. Why the customer opening total is higher than the opening bills (D2).
7. Which old years must be kept, and whether the other twelve backups can be
   handed over. They are wanted for audit (the owner, 2026-10-13), so the
   years an inspection can ask for may be enough.
8. The opening trial balance and the customers' outstanding as the old
   program prints them for the larger firm, to set beside D1 and D2 before
   anybody is asked why they differ.
