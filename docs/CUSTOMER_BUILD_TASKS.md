# First customer: build tasks

**Written 2026-10-12 from the requirements review of that day.** One row is
one piece of work small enough to build, test and merge on its own. The loop
takes the first row marked READY, top to bottom, and writes its result in the
Status column.

The Swathi import is **not** in this list. It is kept in
`docs/SWATHI_IMPORT_PLAN.md` and is not started.

## Decisions this list stands on

- Owner's points of 2026-10-12, in
  `dist\customer\CUSTOMER_REQUIREMENTS_QUESTIONS_answers_2026-10-11.xlsx`
  (sheets Questions and Not shown).
- Questions A1 to A20 in `dist\customer\OPEN_QUESTIONS_2026-10-12.md`: **all
  decided as recommended** (owner, 2026-10-12 night).
- A collector sees his bills on **his own screen only**. Limiting every list
  and report to a user's own customers is not built.
- Order: small items, then medium, then large. A large item starts with a
  design note the owner reads before any code.

## How one item is worked

1. Branch from `main`. Check open pull requests first.
2. **Look at what exists before building.** Each row was written from the
   review, not from a full reading of the code; part of it may be there
   already. Build only what is missing, and say what was found.
3. Backend, then the screen in the **new UI only** (`desktop/lib/phase2/`).
4. Targeted tests, then drive it over HTTP against the running backend. Run
   the "Try" column where the row has one.
5. Reference doc, user guide and QA test cases in the same work.
6. One pull request per row; merge on targeted tests; migrate every store
   and restart the backend if a migration landed.
7. Give the item its entry in `docs/BACKLOG.md` (next free number 106) and
   write Status here: `DONE #PR`, or `STOPPED: reason`.
8. A row marked WAITS or DESIGN is skipped. If a READY row turns out to need
   an answer nobody has given, write the question in the Status column, mark
   it WAITS and take the next row.

## Group 1: small items

| # | Item | Done when | Try | Status |
| --- | --- | --- | --- | --- |
| S1 | Ready-made accounts for every firm: Capital, Drawings, Transport, Fuel, Petty cash. New firms get them; existing firms get only the ones missing | A new firm and an existing firm both show the five; nothing existing is overwritten | | DONE #1427 (backlog 106). Drawings was already there; Petty Cash 1005, Capital 3200, Transport 6450, Fuel 6460 added; existing firms by migration `20261012_0355` |
| S2 | Credit limit, per firm: either warn and ask to confirm, or warn near the limit and refuse at it | Both modes work on a sales order and an invoice; the screen asks to confirm and never blocks on its own | D8 | DONE #PRNUM (backlog 107). Both modes were already on the server, at order and bill approval (`credit_control_settings`: Warn, or Warn then block, with the two percentages) and on Settings > Credit Control. Missing was the asking: the screen showed a notice that passed by. It now asks, with Approve anyway and Cancel. Tried over HTTP on a fixture firm: 30 checks |
| S3 | Area and city shown beside a customer's or supplier's name in pickers and lists. Screens only, never on a print | Two parties of the same name can be told apart in every picker | | READY |
| S4 | Stock report shows value at MRP beside value at cost | Both totals agree with a hand count of three items | | READY |
| S5 | A commission slab pays a fixed amount or a percentage | A payout on a fixed-amount slab matches the amount; a slab cannot hold both | | READY |
| S6 | Commission period is a start date plus a number of days | A payout for a range that is not a month is right | D9 | READY |
| S7 | Second backup folder: a copy of each backup to a second folder (a cloud-synced folder or another drive), last 10 days kept, password-protected | A backup lands in both places; the eleventh day removes the oldest; the copy does not open without the password | D14 | READY |
| S8 | TDS and TCS switch on each customer and supplier, with an override on the document | Switch off: no deduction. Override on one bill changes that bill only | D4 | READY |
| S9 | Discount limit per role at billing | A user over his role's limit is refused by the server with the limit named | | READY |
| S10 | Discount at collection: the owner waives part of a due as discount, GST unchanged. A one-time clearance percentage as a firm setting, allowed to the owner only | The bill closes, the GST on it is unchanged, and a salesman cannot give it | D3 | READY |
| S11 | Licence check, and the firm's own licence numbers printed on the bill | Warn and block both work; an expired licence is caught; the numbers print as on the sample bill | D2 | READY |
| S12 | Excel download on every statement and report | Every report screen has the download and the sheet opens with the same figures | | READY |
| S13 | Half-page bill, laid out as the customer's sample (`D:\ws\customerdata\bill-1.pdf`): MRP, rate, free, discount, GST, batch and expiry columns, a GST summary by rate, round-off. Half or full page per firm and per customer, switching to full by itself when the lines do not fit | A one-line bill prints on half a page and matches the sample's columns; a long bill prints on a full page | D10 | READY |

## Group 2: medium items

| # | Item | Done when | Try | Status |
| --- | --- | --- | --- | --- |
| M1 | Approval per document type, taken from the steps the document already has. With only the final step switched on, Save does every step. Sales side | A firm with all steps off bills in one save; a firm with approval on is stopped at it | D5 | READY |
| M2 | The same for the buying side | As M1, on a purchase order through to the supplier's bill | | READY after M1 |
| M3 | Customer account table: the account as rows, adding a row is a new receipt, for the customer or against one bill, the last X entries shown | A receipt added from the table closes the bill and appears in the ledger | | READY |
| M4 | Bills handed to a collector: a separate bill-and-collector table that never touches the books. Assign by date, area, a run of bill numbers, or by ticking | Assigning and taking back change no balance and no report | | READY |
| M5 | A ready-made Bill collector role and his one screen: the bills handed to him, and older unpaid bills of the same customers marked apart | A collector signs in and sees only that screen and only his bills | | READY after M4 |
| M6 | End-of-day return entry per bill handed out: collected, part, promised, not collected. A firm setting decides whether the collector records the receipt himself | The day's sheet adds up to the receipts recorded | | READY after M5 |
| M7 | Parent buyer with shops: the GST number is held once, on the parent | A parent with three shops is created; the GST number is refused on a second parent | | READY |
| M8 | One receipt from a parent spread over its shops' bills; a shop can also pay for itself | One receipt closes bills of three shops; each shop's account is right | | READY after M7 |
| M9 | Supplier company with branches: the company is the main supplier, branches are sub-suppliers with their own GST number. Order on the main office, goods and bills from any branch, payment to the main office or a branch | An order on the main office is received from a branch and billed by it | | READY |
| M10 | A supplier can be added while receiving goods | A new supplier is created from the receiving screen without leaving it | | READY after M9 |
| M11 | Company and brand: a supplier names the brands it may sell; the product list on a purchase order and on a sale can be narrowed by brand. A stockist is a company of his own with the brands he is allowed | A purchase order for one brand offers only that brand's products | D16 | READY |
| M12 | Purchase planning by company from average sales, with stock in hand and quantity already on open orders taken off (backlog 93) | The suggested quantity for three items matches a hand calculation | | READY after M11 |
| M13 | Retail and wholesale: a customer carries his usual choice, and one switch on the bill changes the whole bill | The switch reprices every line; a new bill starts from the customer's choice | D17 | READY |

## Group 3: large items, design note first

The first row of each is a design note in `docs/`, read by the owner before
any code. The loop writes the note, marks the row `NOTE READY` and **stops
that item**; the rows after it stay WAITS until the owner says go.

| # | Item | Status |
| --- | --- | --- |
| L1 | Design note: cost per purchase lot (backlog 101, 103). Every purchase line is a lot with its own cost and prices; goods with no batch get our own lot reference; at billing the user picks from stock per price and batch, nearest expiry first; the sales line keeps the lot, so a return traces to the supplier's bill; books at cost, first in first out by lot | DESIGN |
| L2 | Build L1, in the steps its note sets out | WAITS for L1 |
| L3 | Selling margin on the purchase price, by goods type, changeable on the purchase line, GST on top; the worked-out price rounded to the nearest rupee as a setting, and belonging to that lot only. Retail and wholesale price per lot. Cost and margin shown on the bill line, on screen only, to users allowed to see cost | WAITS for L2 |
| L4 | Design note: one line with a box count and a piece count, rate per piece, free goods entered the same way | DESIGN |
| L5 | Build L4 | WAITS for L4 |
| L6 | Design note: offers and discounts listed on the bill line for the bill maker to choose, one applied to start, combining by the firm's setting, "buy N more", and a part share of an offer as a switch on each offer | DESIGN |
| L7 | Build L6 | WAITS for L6 |

## Checks on a running firm

No build; the loop tries each on a fixture firm and writes what it found. A
defect found goes into `docs/DEFECTS.md` and is fixed in the same work.

| # | What to try | Status |
| --- | --- | --- |
| C1 | D6: billing and shipping address, on the screen and on the print | READY |
| C2 | D11: rate including GST, what the line and the print show in each mode | READY |
| C3 | D12: year end. Closing refused and why; whether the next year, its months and the bill numbers start by themselves | READY |
| C4 | D13: every step of `docs/ACCOUNT_BOOKS_GUIDE.md` | READY |

## Not for the loop

| Item | Waits for |
| --- | --- |
| Pull request #1425 (5.5 charged + 0.5 free on an invoice) | The owner's word to merge |
| Working financial year selector | The customer (C6): wall or filter |
| Year-end workbook for the CA | The customer (C9): which statements, what layout |
| An account per employee for salary and advances | The customer (C16) |
| What each role must not see or do | The customer (C18) |
| Reverse charge set-up | The customer (C10) |
| A product needing two licences | The customer (C14) |
| Swathi import and the old-years archive | `docs/SWATHI_IMPORT_PLAN.md`, after the customer agrees |
| Remote access cost-and-upkeep guide | The owner: wanted, not now |
| Writing the A1 to A20 answers into the dated Excel copy | Owed, by hand, with the owner |
| Rewording questions 2.7 and 7.4 and adding C6, C8 to the question list | The owner's word that the dated copy is the one to keep |
