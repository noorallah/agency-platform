# What posts to the ledger, and what it is valued at

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

Eleven modules post through `DocumentPostingService`. Also covers settlements,
receivables, TCS, credit notes, GST returns and e-invoicing.

## A ledger leg facing stock is valued from the movement

**A ledger leg facing stock is valued from the movement; a leg facing a counterparty is valued from the document.** Every forward posting already did this -- receipt, dispatch, both returns, both adjustment paths all read `StockLedgerEntry`. All three *reversals* broke it, and all three were fixed on 2026-08-22: a cancelled goods receipt and a cancelled purchase return credit inventory with what the movement removed and book the gap to `PURCHASE_PRICE_VARIANCE`, and a cancelled sales return's cost entry posts both legs at the movement value so the gap stays in cost of goods sold. Goods arrive at one average and leave at another; mirroring an entry across that gap is what puts a store out.

## Applying money already received posts no journal

**Applying money already received posts no journal, and only part of it
moves the balance.** `settlements.sales_order_id` records which order a
deposit came in against -- a note, not a ring-fence: cancelling the order
does not make the deposit vanish. `POST /api/v1/receipts/{id}/allocate` is
the other half, and it was missing entirely: `ADVANCE_APPLY` had been a
declared receivable type since the settlements module shipped with
**nothing able to reach it**. Two rules. **No journal** -- the receipt
debited cash and credited receivables, the invoice debited receivables; the
allocation only decides which invoice the credit belongs to, and a journal
would count the money twice. And **only the part that became an advance
moves the customer's balance**: a receipt splits when it is recorded,
`min(amount, outstanding)` off the balance and the excess into advance, so
posting `ADVANCE_APPLY` for the whole allocation double-counts. The first
version did, and a deposit taken while the customer already owed something
-- the ordinary case -- was refused outright with "exceeds unapplied
advance". `_advance_part_of` reads the split off the receipt's own
receivable row and subtracts what earlier allocations used, or the last of
an advance is stranded for ever.

## Money received on the bill posts as a receipt, not as part of the bill

A counter payment entered on a sales invoice (backlog 64 row 5) posts **two
journals**, the invoice's and a receipt's (`Dr Cash or Bank / Cr Trade
Receivables`), staged in the one approval. Folding it into the invoice's
journal as `Dr Cash` instead of `Dr Receivables` would be one entry fewer and
would leave the customer's statement, the receipt register and the day book
without the payment -- and nothing to reverse when the money turns out not to
have arrived. Cancelling the bill afterwards is refused while the receipt is
applied to it, naming the receipt, as for any money applied to a bill: reverse
the receipt first, then cancel.

## A proforma posts nothing

**A proforma posts nothing, and the absence of anywhere to record that it
did is the design.** `app/proforma` states what an approved sales order will
be charged, for a buyer who needs the figure before the goods move -- a
letter of credit, a payment approval, a customs entry. Neither table carries
a `journal_entry_id` or a `receivable_transaction_id`; adding one is the
first step towards a document that looks like a bill to the books as well as
to the customer, and the unit suite counts journal and receivable rows after
issuing rather than trusting the absence. **Its number comes from its own
`PI` series, never the tax invoice's** -- GSTR-1's DOCS section declares the
invoice series, so a proforma drawn from it would either leave a gap the
return cannot explain or put a number in it that was never a supply. **Its
lines are snapshotted**, not read live: an order can be edited afterwards,
withdrawing its own approval as it goes, and a document somebody is
arranging payment against must not change underneath them. Once ISSUED it
cannot be edited -- a revision is a new document with `supersedes_id`
pointing back -- and withdrawing keeps the row, because the customer holds a
copy.

## A statement's running balance is recomputed in date order, never read off `outstanding_after`

**A statement's running balance is recomputed in date order, never read
off `outstanding_after`.** That column on
`customer_receivable_transactions` is a snapshot taken when the row was
written, in the order things were *recorded*; a statement is read in the
order things were *dated*. Money arriving against last month's bill is
recorded after it and dated before it, so the stored figure shows a balance
that never existed on any day. `CustomerStatementService` sums the opening
balance from the deltas before the period -- the same arithmetic that
produced the current balance -- rather than subtracting the period's
movement from today's, which is right only while nothing is backdated.
**And an ageing row reconciles against the account and says how**: the
bills and the balance are not the same number, because a credit note or a
sales return reduces the account and sits on no invoice while TCS raises it
without being billed. One seeded customer's bills read 27,150.98 against an
account of 21,230.48; `total_outstanding - unapplied_credits +
charges_not_billed` is now the balance exactly, and the buckets always sum
to `total_outstanding`. Two reports about one customer that disagree with
nothing to explain the gap is a bug report waiting to be filed.

## Tax collected at source is charged on the money, not on the bill

**Tax collected at source is charged on the money, not on the bill.**
`app/tcs` implements 206C(1H), and the statute says "at the time of receipt
of such amount" -- so the event that raises it is a **receipt**, never an
invoice being approved, and `SettlementService.create` stages it. Putting it
on the invoice collects on money that may never arrive and misses money that
arrives against an older bill. Five rules follow. **Only the excess counts**
-- the first fifty lakh a buyer pays in the year attracts nothing, so a
receipt straddling the line pays on the part above it; charging the whole
receipt over-collects by the entire remaining headroom. **The running total
is summed from the receipts**, never a counter, net of refunds and excluding
the receipt being charged -- counting that one would make the first receipt
over the threshold pay on itself -- **and only from receipts dated on or
before the one being charged**: summing the whole year charged a back-dated
receipt on money the buyer paid after it (D-CMP-7). **The financial year is the firm's own**,
read off `financial_year_start`, because the threshold resets with it.
**A seller below the turnover threshold collects nothing**, and that
turnover is *stated* rather than derived: the preceding year may predate
this system. And **the tax raises what the buyer owes** (`Dr Accounts
Receivable / Cr TCS Payable`, account **2500** -- not 2200, which is Output
Tax; TCS is filed on a different return on a different cycle). `is_enabled`
defaults false so shipping it charged nobody, and `TCS_MANAGE` is not
granted to `SALES_MANAGER` for the reason the credit policy is not.
The direction check is `SettlementDirection.RECEIPT`, not `"IN"` -- the
first version compared against a string the column never holds, so it
collected nothing anywhere and only the tests said so.

**Section 206C(1H) was omitted by the Finance Act 2025 with effect from
1 April 2025.** A receipt dated on or after that day collects nothing under
it, whatever the settings say, and the preview says why
(`SECTION_206C_1H_OMITTED_FROM` in `app/tcs/services/tcs_service.py`);
receipts dated earlier are charged as the law then stood, and collections
already made are never rewritten (D-CMP-12). The module still answers for
FY 2024-25 and earlier, which is why it stays.

**What a receipt is charged on is the year's running total, less what
standing collections have already charged.** A collection is never rewritten
-- the quarter it falls in may already have been filed -- so when the history
behind a receipt moves, the **next** receipt settles the difference
(D-CMP-16). Reverse a receipt and the collection on it goes back with it, but
the collections that followed it stand; a later receipt then charges only what
the year still owes, instead of charging again on what those collections
already covered. Back-date a receipt in front of collections already made and
it charges what was due on *its own* date -- usually nothing -- while the
shortfall it leaves is collected on the next receipt. Both fall out of
`_taxable_part` taking `already_taxed`, summed from the collections that still
stand and dated on or before the receipt, exactly as the consideration is
summed from the receipts.

## A supplier's opening balance is bills, not a balance

Built 2026-09-30 (`docs/BACKLOG.md` §36, the first cutover gap). A supplier has
no balance column -- what the firm owes is its bills less what was paid,
returned and credited against them, all derived by
`PaymentService.outstanding_invoices`. So a day-one debt is recorded the way
the old books held it, **bill by bill** (`vendor_opening_bills`): the
supplier's reference, the bill date the ageing counts from, a due date, and
what was still owed at cutover. Each posts **Dr Opening Balance Equity / Cr
Accounts Payable** on the **posting date** -- the day the books here start,
not the bill's own date, whose period is not open and whose trading happened
elsewhere. Numbered `OB-00001` across the firm, which is also the journal's
reference.

- **Not a purchase invoice.** It carries no goods and no tax; a row in
  `purchase_invoices` would be read by the GST returns, the purchase register
  and every purchase analysis as trading done here.
- **Paid like a bill.** `outstanding_invoices` lists it beside the purchase
  bills (`is_opening_bill: true`), so Record Payment, applying an advance
  later, the vendor outstanding and overdue reports and the vendor delete
  guard all see it without knowing it exists. A payment's allocation to it
  lands in `settlement_allocations.vendor_opening_bill_id`.
- **Cancelled, never edited.** `POST /vendors/opening-bills/{id}/cancel`
  posts the mirror (`OB-00001-REV`) and is refused while any payment is
  applied: reverse the payment first. The number is not reissued.
- **Imported all or nothing** by supplier code
  (`POST /vendors/opening-bills/import`): every unknown code is named with its
  row number before anything is written, then the batch is staged and
  committed once.
- **From a file** (2026-10-01, D-GOLIVE-1): `GET .../opening-bills/import-template`
  and `POST .../opening-bills/import-file` on both `/vendors` and `/customers`,
  behind *Import opening bills* in the "..." of the phase 2 lists. One posting
  date for the file, chosen on screen; every problem by row and column before
  anything is written; then each bill goes through the service's own
  `_stage`, so the journal, the balance and every refusal are the form's.
  `app/common/opening_bill_import.py` is the one importer, a subclass per side.
- **Supplier credit clears one too** (BUY-17, A52, 2026-10-03): a purchase
  return's or debit note's credit is set against an opening bill exactly as
  against a purchase bill -- `supplier_credit_applications.vendor_opening_bill_id`
  (migration 0239), exactly one of it and `purchase_invoice_id`. Nothing posts;
  `opening_bill_payments` counts it, so Record Payment, the opening bill list
  and the delete guard agree. Cancelling the opening bill withdraws the credit
  rather than refusing, as cancelling a purchase bill does; money paid still
  refuses it.

## A customer's opening balance is one figure or bills, never both

Built 2026-09-30 (`docs/BACKLOG.md` §36): the receivable mirror of the
supplier's opening bills above. A customer's day-one debt can be entered two
ways, and **only one of them per customer** -- the convention Tally calls the
bill-wise breakup of an opening balance:

- **One figure** on the master (`customers.opening_balance`), posted by
  `post_opening_balance`: Dr Receivables / Cr Opening Balance Equity (swapped
  for a customer in credit), with an `OPENING_BALANCE` receivable row. Quick,
  and it knows one date only, the day it was typed. **A figure that is owed
  is given one bill that stands for it** (`covers_master_balance`, D-MST-13,
  2026-10-05): it was on no receipt list, collection sheet or ageing report,
  because each of those is a list of bills. That row is the figure seen as a
  bill, not a second debt -- it posts **no journal** and writes **no
  receivable row**, and its `journal_entry_id` is the master's own entry --
  dated the day the figure was entered and due on the customer's terms. It
  is revised and withdrawn with the figure and refuses to be cancelled from
  the opening-bills screen. A customer who starts in credit gets none.
  `20261005_0333` gave one to every customer already carrying such a figure;
  a receipt taken on account before then stays on account beside it.
- **Bill by bill** (`customer_opening_bills`, `OBC-00001` -- a prefix the
  supplier series `OB-` cannot produce, since both are journal references and
  those are unique per firm): the old bill number, the bill date, a due date
  (given, or the bill date plus the customer's payment terms, **stored** so
  changing the terms later does not re-age it), and what was still owed at
  cutover. Each posts **Dr Accounts Receivable / Cr Opening Balance Equity**
  on the **posting date** through `DocumentPostingService.post_customer_opening_bill`
  (source `customer_opening_bills`), and writes an **`OPENING_BILL`**
  receivable row dated the same day, linked to that journal, raising
  `current_outstanding` exactly as an invoice does -- so the statement, credit
  control and the delete guard see it.

Both at once would count the same debt twice, so `CustomerOpeningBillService`
refuses a bill while the master's opening balance is non-zero ("set the
customer's opening balance to 0 first"), and `CustomerService.update` refuses a
non-zero opening balance while live bills stand. The receivable row has its own
type rather than `OPENING_BALANCE` because rows of that type are deleted and
their journals mirrored whenever the master's figure is revised; a bill must
never go with them.

- **Received like an invoice.** `ReceiptService.outstanding_invoices` lists it
  beside the sales invoices (`is_opening_bill: true`), outstanding derived
  from `settlement_allocations.customer_opening_bill_id`; allocation at
  receipt, applying an advance later and reversing a receipt all treat it as
  an invoice. The ageing reads it from its due date, through the same
  derivation, honouring `as_of`; the overdue report lists it.
- **Cancelled, never edited.** `POST /customers/opening-bills/{id}/cancel`
  posts the mirror (`OBC-00001-REV`) and reverses the `OPENING_BILL` row by
  its own delta on the mirror's date; refused while any receipt is applied.
- **Not a sale.** No row in `sales_invoices`, so GST returns, the sales
  register, e-invoicing, TCS turnover and collection commission never read it.

## Tax deducted at source posts with the money

Built in two steps (`docs/BACKLOG.md` 53.1). **2026-09-30:** a firm records its
TAN (Firms grid, beside PAN) and a customer's TAN (customer form), both
format-checked; every chart has **TDS Payable** (`2700`, purpose
`TDS_PAYABLE`) and **TDS Receivable** (`1400`, purpose `TDS_RECEIVABLE`),
backfilled by `20260930_0166`. Each is its own account, not TCS's: TDS is a
different return (26Q/24Q) on a different challan.

**2026-10-01 (items 3 and 4, migration `20261001_0175`):** a payment, a
receipt and an expense each carry `tds_amount` and `tds_section`, as Tally's
voucher does. **`amount` stays what settles the party** -- the bill's whole
value -- so allocations, the customer's balance, statements and ageing are
unchanged; only the journal splits the money leg:

- **Payment:** Dr Payables `amount`; Cr Bank `amount - tds`; Cr TDS Payable
  `tds`.
- **Receipt:** Dr Bank `amount - tds`; Dr TDS Receivable `tds`; Cr
  Receivables `amount`.
- **Expense:** Dr the expense `amount`; Cr the money account `amount - tds`;
  Cr TDS Payable `tds`. An expense with a deduction names its payee, and
  takes the payee's PAN (`payee_pan`, format-checked).
- **A refund carries none**, and is refused if asked.
- **Reversal mirrors every leg**, the deduction included, because
  `reverse_entry` copies the journal.

**The section is required and closed** (`app/finance/tds.py`: 194Q, 194C,
194J, 194I, 194H, 194A, 194R, 194T, 192, 194O) -- the Act's list. **No rate is
held anywhere**: rates and thresholds change every Finance Act, so the person
recording states the amount deducted, as the challan and the return will.

**194Q is suggested, never posted on its own** (ACC-8): `tds_194q.py` reads a
supplier's approved bills (without GST) and its 194Q payments for the
April-March year and suggests what the next payment deducts. The deduction
is still the payment's, posted as every TDS is; nothing journals at the bill.

**194C and 194J are worked out the way 194Q is, but deducted on the bill**
(PG-5, `tds_sections.py`). The Act deducts them at the earlier of credit and
payment, so a bill from a supplier whose master names 194C or 194J proposes
the deduction when it is **approved**, and a payment proposes it only for
money ahead of any bill. Each proposal is the year's tax due less what the
year already deducted (bills and payments, the April-March year, read from the
documents, never a counter), so it is deducted **once** whichever comes first:
a payment against a bill that bore TDS proposes nothing, and a bill after an
advance that bore it finds it deducted. An advance counts only for what the
supplier's open bills do not cover. Thresholds: 194C one bill past 30,000 or
the year past 1,00,000; 194J the year past 30,000. **Past the year's limit the
tax is on the whole year, not the excess** (unlike 194Q), so the bill that
crosses it carries the earlier bills' tax. Rates are per firm
(`tds_section_settings`, defaults where never saved): 194C 1% individual/HUF
(the supplier's flag, else the PAN's fourth letter P or H) and 2% others; 194J
10% professional and 2% technical; 20% with no PAN (206AA).

- **Bill:** Dr the accrual/input tax as before; Cr Payables `grand_total - tds`;
  Cr TDS Payable `tds`. The bill keeps `tds_section`, `tds_base_amount` (before
  GST), `tds_proposed_amount` and `tds_amount`; it owes the supplier
  `grand_total - tds_amount` everywhere a payable is read
  (`_purchase_bill_taken`, the payables report). Cancelling mirrors the journal,
  and is refused while a live challan carries the bill's deduction.
- **Override:** the approve request's `tds_amount` (0 deducts nothing) and a
  payment's own `tds_amount`; the proposal stays beside it
  (`tds_proposed_amount`) and the audit row records both and `tds_overridden`.
- **Challans and 26Q** take a bill's deduction as a third kind (`BILL`,
  `tds_challan_items.purchase_invoice_id`), filed under the bill's section
  with the base before GST as the amount credited.

**TCS a supplier charges the firm is an asset on the bill** (PG-6, 206C(1H)).
A supplier selling the firm more than 50 lakh a year may collect TCS on top of
its bill; the firm claims it against its own income tax once it shows in Form
26AS. The bill carries `tcs_rate_percent` (shown) and `tcs_amount` -- typed, or
the rate on `grand_total` (the section's base is the bill **including** GST)
when only the rate is given; a typed amount wins. It is **outside GST's
taxable value**: no line, no tax and no stock moves with it.

- **Bill:** Dr TCS Receivable `tcs` (the `TCS_RECEIVABLE` purpose, seeded as
  *1430 TCS Receivable* in current assets, migration `20261005_0308` for firms
  already open); Cr Payables `grand_total + tcs - tds`. It sits beside TDS
  Receivable rather than inside it -- a different section and a different line
  of 26AS.
- **Owed:** `grand_total + tcs_amount - tds_amount` everywhere a payable is
  read -- the settlement outstanding (`outstanding_invoices`,
  `purchase_bill_positions`), the payables report, and the cash purchase's
  *Paid now*; the response carries it as `amount_owed`.
- **Cancel** mirrors the journal, so the receivable goes with the payable.
- **Report:** `GET /purchase-invoices/reports/tcs-paid` lists each approved
  bill that bore TCS with the supplier's PAN, the base, rate and TCS, and
  closes each financial-year quarter with a `QUARTER_TOTAL` row.

**A post-dated cheque posts nothing while it is held** (ACC-2,
`post_dated_cheques.py`). Banking it posts the receipt or payment it becomes,
dated the day it was banked, through the settlement service. A returned cheque
reverses that settlement on the day the bank returned it, and its charges post
one entry of their own -- source module `post_dated_cheque`, reference
`<settlement number>-RTN`: Dr Bank charges / Cr the bank for the bank's fee,
and Dr Receivable / Cr *Cheque Return Charges Recovered*
(`CHEQUE_RETURN_CHARGES`) for what the customer is charged, written to the
customer's account too. No GST on that charge (CBIC circular 178/10/2022).

**A TDS challan empties TDS Payable** (ACC-7, `tds_challans.py`): Dr TDS
Payable for the tax, Dr *Interest and Fees on TDS* (`TDS_INTEREST_AND_FEES`)
for interest and the late fee, Cr the bank -- source module `tds_challan`,
reference the challan's own number. Interest and fee never touch TDS Payable:
nobody's deduction paid them. The tax is the sum of the deductions the challan
carries, under one section, and a deduction sits on one live challan only
(a partial unique key, not a read). Cancelling posts the mirror under
`<number>-CAN` and frees the deductions.

**The two registers** (`app/finance/services/tds_register.py`, read from the
documents, storing nothing): *TDS deducted* (`/finance/reports/tds-deducted`)
-- payments and expenses, by deductee, PAN and section, with the return
quarter (April-June is Q1, whatever the firm's year) -- is what 26Q is filed
from; *TDS deducted by customers* (`/finance/reports/tds-deducted-by-customers`)
carries each customer's TAN, to tick TDS Receivable against Form 26AS. A
missing PAN reads "PAN not given" (section 206AA's higher rate applies). A
reversed or cancelled document stays listed with its status: a challan may
already have been paid.

**Paying the challan** is still a journal: Dr TDS Payable, Cr Bank. **Claiming
TDS Receivable** against the firm's own tax is the CA's year-end entry.

**The 26Q export (2026-10-01)** -- Reports > Financial > *TDS return (26Q)*,
`/finance/reports/tds-26q` for the grid and `/finance/tds-returns/26q` for
the file, both on the TDS registers' permission (`ACCOUNT_VIEW` or
`REPORT_VIEW`). A return is named by **financial year and quarter**
(`2026-27`, `Q1`) and nothing else, so it is always exactly one quarter; a
malformed year or quarter is refused by name. It is built in
`app/finance/services/tds_return.py` from the *TDS deducted* register and
stores nothing.

**It is a workbook, not the FVU text file**, deliberately. The File
Validation Utility's input hangs every deductee row off a challan row, and a
challan row needs the BSR code, challan serial, date deposited and amount --
none of which the books record while the challan is a journal. A text file
with those blank fails the FVU at its first row; one with them guessed is
worse. So `format=xlsx` (the default) has four sheets: **Deductor** (name,
TAN, PAN, year, quarter, assessment year, totals, and what will stop the
return -- no TAN, deductees without a PAN); **Deductees** (Annexure I in the
Protean RPU deductee sheet's order: section, deductee code `01` company /
`02` other read off the PAN's fourth letter, PAN, name, date, amount, TDS,
rate, reason code; the challan serial left for the filer, who pastes the rows
under the challan in the RPU); **Challans due** (tax by section and month of
deduction, due the 7th of the next month, March's by 30 April); **Not in this
return** (deductions on a reversed payment or cancelled expense, and salary,
which is Form 24Q). `format=csv` is the deductee sheet alone. A deductee with
no PAN is written `PANNOTAVBL` with reason `C` (deducted at the higher rate,
206AA). When challans are recorded as documents, the FVU file becomes
possible and this is where it belongs.

## A bill in another currency posts rupees at its rate; the payment realises the difference

PG-12 part A (2026-10-05, migration `20261005_0313`), decided by the Tally and
ERPNext convention. The books are rupees (`BASE_CURRENCY` in
`app/finance/currency.py`); blank and `INR` are both rupees, and a rupee bill
posts and reads exactly as it did.

- **The bill** keeps its lines and totals as the supplier typed them, with
  `currency_code` (a new bill takes the supplier's `vendors.currency_code`)
  and `exchange_rate` (rupees per unit, required for any other currency). The
  ledger posts `base_grand_total` = `quantize_ledger(goods x rate) +
  quantize_ledger(tax x rate)` -- the legs converted one by one, never the
  total -- and each tax head converted the same way. Dr GRNI at the accrual,
  Cr Payables `base_grand_total`, as for any bill.
- **The stock** is the movement's: a receipt against an order in another
  currency is valued at the order's rate (`_post_inventory`), so a bill that
  raised its own order and receipt clears the accrual with no variance. A
  receipt raised from an order at a different rate posts the gap to price
  variance, as any bill does.
- **A bill is in its order's currency** (D-BUY-39). The order a person types
  carries the currency and rate; a bill billing its receipt takes them when
  it names none, and is refused by name in any other currency -- rupees off
  a USD order or USD off a rupee one would put nearly the whole bill in
  price variance. Ten at 100 USD ordered and received at 83, billed at 84.50:
  Dr GRNI 83,000 / Dr Purchase Price Variance 1,500 / Cr Payables 84,500.
- **Every report of these bills is in rupees** (D-BUY-35): the GST purchase
  register, the HSN summary, the purchase invoice register, purchase analysis
  and GSTR-3B's input credit and reverse charge read `base_grand_total`,
  `base_tax_total` and each component at the bill's rate (`rupee_rate` /
  `rupee_rate_sql` in `app/finance/currency.py`). GSTR-2B matching and rule
  37 read the same rate, and rule 42 reads GSTR-3B's summary (D-CMP-23).
- **A debit note or a purchase return against such a bill posts at the
  bill's rate** (D-BUY-41), each leg converted on its own, never at the
  day's: an exchange difference belongs to a payment. A claim of 100 USD on
  a bill at 83 is Dr Payables 8,300; two of ten units at 100 USD sent back
  is Dr Payables 16,600 / Cr Inventory at what the movement cost, any gap to
  price variance. The bill owes that much less in rupees **and** in its own
  currency. A return carries the currency and rate of what it sends back
  (`purchase_returns.currency_code` / `exchange_rate`, stamped by the
  server): its bill's, or its order's until a bill reaches the goods. A
  debit note stores neither and reads its bill's
  (`app/purchase_invoice/services/rupees.py`).
- **Owed** is derived in both currencies from `settlement_allocations`: rupees
  as `base_grand_total` less each allocation's `base_amount`, the bill's
  currency as `grand_total` less each `currency_amount`. The outstanding
  record carries `currency_code`, `exchange_rate`, `currency_total` and
  `currency_outstanding` beside the rupee figures; the payables report reads
  the rupees.
- **The payment** names `currency_code` and its own `exchange_rate`; its
  `amount` and allocations are in that currency and must all go to the
  supplier's bills in it (no advance in a foreign currency, no TDS and no
  deductions). Stored: `settlements.amount` = rupees paid (`currency_amount`
  x the payment's rate), each allocation's `amount` its share of those rupees,
  `base_amount` what it took off the bill at the bill's rate (the bill's whole
  remaining rupees when the payment clears it, so a part payment settles in
  proportion and the last leaves nothing). Journal: Cr Cash/Bank the rupees
  paid, Dr Payables the bills' rupee value, and the difference to *Exchange
  Gain/Loss* (`EXCHANGE_GAIN_LOSS`, seeded as *4950*, revenue) -- **Dr when
  it is a loss, Cr when a gain**.
- **Reversing the payment** mirrors its journal, gain or loss leg included,
  and the allocations stop counting, so the bill owes its whole value in both
  currencies again.
- **Rupees are refused against a foreign bill** -- an ordinary payment, an
  advance applied later, and the cash purchase's *Paid now* -- because only a
  payment in the bill's currency states the day's rate.
- **TDS and TCS** do not apply: a TCS on a foreign bill is refused when the
  bill is saved, no 194C/194J deduction is proposed and an override is
  refused (withholding on a payment abroad is section 195, not built).
- **Period-end revaluation** (`POST /finance/fx-revaluation`, `JOURNAL_POST`)
  takes `{as_of, rates: {USD: 84.1}}`, restates what each open bill dated by
  then still owes in its currency at the new rate, and posts the net once:
  Dr Exchange Gain/Loss / Cr Payables for a loss (the reverse for a gain),
  source module `fx_revaluation`, reference `FXREV-YYYYMMDD`, dated `as_of`,
  with its mirror `FXREV-YYYYMMDD-REV` dated the day after. Unrealised, so
  nothing on a bill or allocation changes and the payment still realises the
  whole difference against the bill's own rate. Minimal: it reads what each
  bill owes now, refuses a second revaluation of the same day, and refuses
  the whole thing when no period is open for the reversal's day. On `as_of`
  itself the payables account holds the restatement and no bill does, so the
  payables report's books check **allows for it** (D-FIN-27): `ledger_balance`
  is still what the account holds, `unrealised_revaluation` is the part that
  is revaluation (the `fx_revaluation` lines on payables dated by then), the
  difference compares the bills with the account less that, and the note says
  so. Narrowed to one supplier the check reads that supplier's own documents
  and never held it.
- **Not built yet**: purchase returns and debit notes are still rupee
  documents. The customs side is part B, below.

## A Bill of Entry books customs duty as cost and import IGST as credit

PG-12 part B (2026-10-05, migration `20261005_0314`, module
`app/bill_of_entry`, `/api/v1/bills-of-entry`), decided by Tally, ERPNext and
Indian customs practice. The goods of a foreign bill clear customs on a Bill
of Entry, typed as a `DRAFT` and posted (`PURCHASE_APPROVE`).

- **Each line** carries the assessable value in rupees, basic customs duty
  (BCD, % of assessable), the social welfare surcharge (SWS, % of BCD, 10
  unless typed), IGST (% of assessable + BCD + SWS) and compensation cess (an
  amount). An amount is worked out from its rate only when it was not typed;
  a typed amount wins (`compute_line_duty`, `app/bill_of_entry/services/duty.py`),
  every figure rounded to paise on its own.
- **BCD + SWS are a cost of the goods, with no credit.** At posting they are
  spread over the linked receipts' lines of the same product by stock
  quantity and landed through the landed cost mechanism
  (`land_on_receipt_lines` in `app/landed_costs/services`, shared with BUY-16):
  the share on stock still held revalues it (moving average up, no quantity
  moving, an `inventory_transactions` row of type `LANDED_COST`), the share on
  goods already sold goes to cost of goods sold. The receipts are those the
  Bill of Entry names plus every receipt its linked bills reach (named as a
  source, or raised by the bill itself); each must be completed. **A line no
  linked receipt carries** is booked to *Customs Duty* (`CUSTOMS_DUTY`, seeded
  as *5220*, expense): stock valuation does not absorb it, because there is
  no stock to revalue.
- **IGST on import is input tax**, debited to the account the purchase side
  claims IGST through (`input_tax_purpose("IGST")`, *1310 Input IGST*); cess
  to *1300 Input Tax*.
- **The credit** is *Customs Duty Payable* (`CUSTOMS_PAYABLE`, seeded as
  *2800*, liability) for the sum of the debits, each leg rounded on its own.
  Source module `bill_of_entry`, referenced by our number, which starts
  `BOE-` by default; the prefix is added only for a firm that numbers it some
  other way, never twice (D-BUY-47 -- postings before 2026-10-05 read
  `BOE-BOE-...` and keep that reference; a landed cost voucher's `LCV-` works
  the same way). A Bill of Entry with no duty at all posts no journal.
- **Paying customs** is not a new payment kind: a journal (`POST
  /finance/journal-entries`) Dr *2800 Customs Duty Payable* / Cr *Bank*. The
  payments module settles parties' bills and the expenses module books only
  to expense accounts, so neither reaches a liability control account.
- **Cancelling** a posted Bill of Entry reverses its journal (the original's
  own reference with `-REV`, as every reversal is -- a supplier refund's too)
  and takes the on-hand share back off the stock at today's quantity: what
  was sold since keeps the cost it was sold at, as a cancelled landed cost
  voucher does.
- **GSTR-3B 4(A)(1)** reads the IGST and cess of posted Bills of Entry by
  `boe_date` on every read (`itc_import_goods`), and net ITC includes it
  (`docs/TAX_FRAMEWORK.md`).

## A fixed asset is debited at cost, depreciated by run, and leaves at book value

PG-13 (2026-10-05, migration `20261005_0315`, module `app/fixed_assets`,
`/api/v1/fixed-assets`), decided by Companies Act Schedule II, Income-tax Act
s.32 and Tally/ERPNext practice. Four purposes, each a default an asset class
may override with its own account: `FIXED_ASSET_COST` (*1500 Fixed Assets*),
`ACCUMULATED_DEPRECIATION` (*1590*, a contra asset, both in a *Fixed Assets*
group), `DEPRECIATION_EXPENSE` (*6950*) and `ASSET_DISPOSAL_GAIN_LOSS`
(*4960*, income or expense).

- **A capital-goods bill line is an asset, never stock.** A purchase-bill
  line marked `is_capital_goods` names an `asset_class_id`; approving the bill
  raises one asset per such line at the line's value before tax (in rupees at
  the bill's rate) and the bill's journal debits the class's asset account
  for it. The bill's own receipt (a firm typing only the bill) is completed
  with **no stock movement and no accrual** for that line, so the goods value
  is not left to *Goods Received Not Invoiced* or price variance. A firm on
  the whole chain marks the line capital goods on the order or the receipt
  (D-BUY-40): that receipt completes with no movement and no accrual for the
  line either, so the bill posts the same journal. A line billing a receipt
  that already took it **into stock** is refused: the goods are in stock, and
  taking them out is a stock issue, not the bill's business.
- **Its GST is claimed in full** (current law, no five-year split) through
  the same input-tax legs as any line, and GSTR-3B counts it in 4(A)(5); the
  GST purchase register shows it apart as `capital_goods_tax`. Blocked or
  ineligible credit stays a cost, as on any line.
- **Cancelling the bill** takes its assets off the register (soft delete) and
  mirrors its journal, unless an asset has since been depreciated or
  disposed, which refuses the cancellation.
- **An asset typed by hand posts nothing**: an *opening* asset (with its
  depreciation to `opening_as_of`) or one bought outside a bill reached the
  ledger by the opening trial balance or the journal that brought it.
- **A depreciation run** (`POST /fixed-assets/depreciation-runs`, Companies
  Act book) charges every active asset from the later of the period start,
  its put-to-use day and the day after its last charge, to the period end:
  SLM `(cost - residual) / life` (or `cost x rate`), WDV `rate x book value`,
  each pro rata over a 365-day year and never below the residual value, each
  rounded on its own. **One journal per run**, reference `DEP-<number>`,
  source module `depreciation_run`: Dr expense / Cr accumulated per pair of
  accounts, dated the period end. Runs go forward and never overlap;
  cancelling (latest first, never under a disposal) reverses the journal
  (`DEP-<number>-REV`).
- **Disposal** (`POST /fixed-assets/{id}/dispose`) first charges depreciation
  to the day (a `DISPOSAL` run of one asset), then posts reference
  `FA-<number>-DISPOSAL`, source module `fixed_asset`: Dr accumulated
  depreciation (opening plus every charge), Dr *Cash* or *Bank* (`method`) for
  the sale money, Cr the asset account at cost, and the difference -- sale
  money less book value -- Cr (gain) or Dr (loss) to
  `ASSET_DISPOSAL_GAIN_LOSS`. GST on the sale is a sales invoice's business,
  not the disposal's.
- **The Income-tax block schedule posts nothing.** It is read on every call
  from the register for one of the firm's financial years: per block rate,
  opening WDV, additions at the full rate (used 180 days or more in the year)
  and at half the rate, sale proceeds, depreciation, closing WDV, and the
  short-term capital gain when proceeds exceed the block.

## A balance is cleared without money by a deduction or a party adjustment, never by tax

Backlog 74 row 2 (2026-10-01). A receipt three rupees short, a bank charge the
customer's bank took, a discount for paying early, a debt that will never be
paid, a supplier balance the firm will never pay, and a customer who is also a
supplier: each moves a party's balance **without money moving and without
tax**. Changing the value of a supply is a credit note (`/credit-notes`), a
debit note to a supplier (`/debit-notes`) or one to a customer
(`/customer-debit-notes`), which move the tax charged on it; nothing here
touches output or input tax, GSTR-1 or GSTR-3B.

**Deductions on a receipt or payment** (`settlements.rounding_amount`,
`bank_charges_amount`, `discount_amount`, migration `20261001_0191`) follow
the TDS model exactly: `amount` is what settles the party -- the bill's value
-- and each deduction is part of it that did not move as money.

- **Receipt:** Dr Bank `amount - tds - deductions`; Dr TDS Receivable `tds`;
  Dr Rounding (`ROUNDING`, 4900) / Bank Charges (`BANK_CHARGES`, 6700) /
  Discount Allowed (`DISCOUNT_ALLOWED`, 5300) each by its amount; Cr
  Receivables `amount`.
- **Payment:** Dr Payables `amount`; Cr Bank `amount - tds - deductions`; Cr
  TDS Payable `tds`; Cr Rounding / Discount Received (`DISCOUNT_RECEIVED`,
  4200) each by its amount.

The customer's receivable row moves by the whole `amount`, as for TDS, so the
statement and the ledger agree. Each deduction is rounded to the ledger on its
own and the money leg is what is left, so the entry balances to the paisa.
Reversing the settlement mirrors the whole journal -- every deduction leg with
it -- and puts the customer's balance back by the stored deltas, as any
reversal does. Decided by convention:

- **Bank charges are a receipt's only.** On a payment the firm's own bank fee
  settles nothing the supplier is owed; it is an expense, recorded against
  Bank Charges on the Expenses screen.
- **Rounding is capped** by the firm's rounding limit, **10.00** unless set
  (`party_adjustment_settings.rounding_limit`, `PUT
  /party-adjustments/settings`). More than that is a discount or a write-off
  and should be named as one.
- **Deductions must close bills**: together they cannot exceed what the
  settlement allocates. A discount on money held on account would turn an
  advance into a cost.
- **Some money must move.** TDS and deductions that take the whole amount are
  refused: a balance cleared with no money is a party adjustment.
- A refund takes none.

**A party adjustment** (`app/party_adjustments`, `/api/v1/party-adjustments`)
is a document of three kinds, DRAFT -> APPROVED -> CANCELLED, numbered in its
own `PA` series, with a required reason, a timeline and an audit row per step.
A draft posts nothing and clears nothing. Approval posts:

| Kind | Dr | Cr | Customer's account |
| --- | --- | --- | --- |
| Customer write-off | Bad Debts (`BAD_DEBTS`, 6800, indirect expense) | Receivables | `WRITE_OFF` row, outstanding down |
| Supplier write-back | Payables | Balances Written Back (`BALANCES_WRITTEN_BACK`, 4300, other income) | -- |
| Set-off | Payables | Receivables | `SET_OFF` row, outstanding down |
| Supplier rebate (BUY-13) | Payables | Supplier Rebates Receivable (`SUPPLIER_REBATE_RECEIVABLE`, 1410) | -- |
| Customer rebate (SG-9) | Customer Rebates Payable (`CUSTOMER_REBATE_PAYABLE`, 2900) | Receivables | `REBATE` row, outstanding down |

A **supplier volume rebate** (`app/supplier_rebates`) is accrued once its period is over: Dr Supplier Rebates Receivable, Cr Supplier Incentives Received (`SUPPLIER_INCENTIVE_INCOME`, 4320), dated on the period's last day, reference `REBATE-<code>`. The `SUPPLIER_REBATE` adjustment above is how it is settled, capped at what the accrual still has to settle; an accrual nothing has settled is reversed by its mirror.

A **customer turnover rebate** (`app/customer_rebates`, SG-9, migration `20261005_0325`) is the same the other way round. The turnover is derived on every read from the documents GSTR-1 counts -- approved and closed bills at `grand_total - tax_total - round_off`, less completed sales returns at the same figure and approved credit notes at `taxable_amount`, plus approved customer debit notes -- for the one customer the agreement names, or every customer in the group it names. It is accrued once its period is over: **Dr Rebates Allowed (`REBATES_ALLOWED`, 5310, direct expense), Cr Customer Rebates Payable (`CUSTOMER_REBATE_PAYABLE`, 2900, current liability)**, dated on the period's last day, with the turnover, rate and amount kept on the agreement and never re-read. The reference is `CREBATE-<code>`, and `CREBATE-<code>-2`, `-3` for an agreement accrued again after a reversal, because a journal reference is unique and a reversed accrual keeps its own; the mirror is `<that reference>-REV`. The `CUSTOMER_REBATE` adjustment above settles it -- capped at what the accrual still has to settle and at what the customer owes, with a `REBATE` row on the customer's account undone by its own deltas when the adjustment is cancelled. **No leg is tax, on the accrual or the settlement.** Under CGST Act s.15(3) a discount after the supply reduces its value only if it was agreed before the supply and is linked to the invoices; the agreement records `agreed_before_sale` so the firm's CA can decide whether to raise a GST credit note, and nothing here raises one. Both purposes are required only when an accrual or a settlement posts.

It may name open bills on either side
(`party_adjustment_allocations`) or move the balance on account. **What a bill
owes reads the adjustment beside the money**: `adjusted_against`
(`app/party_adjustments/services/allocations.py`) is added inside
`settled_against` (sales bills -- Record Receipt, the ageing, the outstanding
and overdue reports, the customer delete guard), inside
`PaymentService.outstanding_invoices` (purchase bills -- Record Payment, the
vendor reports), inside both opening-bill readers, and in the loyalty cap. It
counts approved adjustments only and honours `as_of` the way receipts do: one
dated on or before the day, and approved, or cancelled only after it. A bill
named by a live adjustment cannot be cancelled. The customer statement reads
the `WRITE_OFF` and `SET_OFF` receivable rows, so it reconciles with the
ledger; the supplier statement reads the payables ledger, which the
adjustment's journal reaches (see below).

**Caps.** A write-off or set-off cannot exceed what the customer owes on
account (`customers.current_outstanding` -- more would turn given-up debt into
an advance), a write-back or set-off what the supplier's open bills add up to,
an allocation what its bill still owes, and each side's allocations the
amount. Checked when drafted and again at approval, with the customer's and
supplier's rows locked, since a receipt may have cleared the bills since.

**Approval** (decided by convention): at or below the firm's threshold --
**1,000.00** unless set (`party_adjustment_settings.approval_threshold`) --
anyone holding `PARTY_ADJUSTMENT_MANAGE` may approve, their own draft
included. Above it the approver must hold `PARTY_ADJUSTMENT_APPROVE` **and**
must not be the person who drafted it, and cancelling an approved one needs
the same code. Setting the threshold needs `PARTY_ADJUSTMENT_APPROVE`: the
role a limit constrains does not move it. `FIRM_ADMIN` and `FIRM_MANAGER` hold
all three; `ACCOUNTANT` holds view and manage.

**Set-off between two businesses.** The masters do not link a customer to a
supplier, so the person setting off states they are one business; where both
carry a PAN -- recorded, or read off characters 3-12 of the GSTIN -- and the
two differ, the set-off is refused.

**Cancelling** an approved adjustment mirrors its journal and undoes the
customer's receivable row by its stored deltas (`receivable_transaction_id`),
dated the mirror's day; the bills owe again because a cancelled adjustment is
no longer counted.

## Money moved between the firm's own accounts is a contra voucher

Backlog 74 row 3. `app/contra`, `/api/v1/contra-vouchers`, table
`contra_vouchers` (migration `20261001_0199`). Before it, cash paid into the
bank was a hand journal with no number of its own and no word when the cash it
moved was not there.

| Kind (derived, never typed) | Dr | Cr |
| --- | --- | --- |
| Deposit -- cash to bank | the bank account | the cash account |
| Withdrawal -- bank to cash | the cash account | the bank account |
| Bank transfer | the receiving bank | the paying bank |
| Cash transfer | the receiving cash account | the paying cash account |

**It posts on save** (`DocumentPostingService.post_contra_voucher`, source
`contra`), as a receipt or an expense does: the money has moved before anybody
records it, so there is nothing to approve. Two legs, no party, no tax.
Numbered in its own `CV` series through the document framework, with a
timeline event and an audit row for posting and for cancelling. **A mistake is
cancelled, never edited**: a reason is required, the journal is mirrored under
`<number>-CAN` dated as every reversal is (the day it happens, never before the
original), and the original stays.

**Which accounts hold money** (decided by convention, 2026-10-01): the firm's
`CASH` and `BANK` control accounts, and every other active ASSET account in
the same account group as either that no other control purpose claims -- a
second bank account, petty cash. **A firm set up from 2026-10-02 has cash and
bank in groups of their own** (decision A22): *Cash-in-Hand* (`CA-CASH`, 1000)
and *Bank Accounts* (`CA-BANK`, 1010), both under *Current Assets*, as Tally
keeps them -- so only money accounts are offered, and a bank account opened in
*Bank Accounts* is a bank everywhere. A firm set up before keeps its chart
unchanged: there cash and bank share *Current Assets* with receivables,
inventory and input tax, which are mapped to their own purposes and never
offered, while an asset account the firm opened itself in that group (a
deposit, an advance to staff) **is** offered until the firm moves cash and bank
to a group of their own. **Cash or bank**: the CASH account is cash and the BANK
account a bank; any other is cash when it sits in cash's group and not
bank's, a bank in the reverse case, and -- where the two share a group, as
seeded -- cash when its name says "cash" and a bank otherwise.

**Below zero is a warning, never a refusal.** When the account the money
leaves would stand below zero at the end of the voucher's own date -- summed
from every posting dated on or before it, so a back-dated deposit is judged
on the day it says -- the voucher still posts, and the response says so in
`message` and `balance_warning`. The books are often a day behind (takings
not yet keyed), and refusing would make the clerk enter things out of order
to get past it. Cancelling checks the account the money goes back out of the
same way.

Read with `JOURNAL_VIEW`, recorded with `JOURNAL_POST` (it writes a posted
journal), cancelled with `JOURNAL_REVERSE` -- the codes a hand journal needs,
so no new permission and no grant migration. The register
(`/reports/register`) reads with `JOURNAL_VIEW` or `REPORT_VIEW`; each voucher
prints on the firm's letterhead (`/{id}/print`,
`app/document_framework/services/letter_pdf.py`).

## A supplier's statement is read off the payables ledger

Backlog 74 row 4. `GET /api/v1/vendors/{vendor_id}/statement?from_date&to_date`
(`app/vendors/services/statement_service.py`, `VENDOR_VIEW`, as the customer
statement is `CUSTOMER_VIEW`). A customer has a sub-ledger,
`customer_receivable_transactions`, and the customer statement reads it. A
supplier has none -- what the firm owes is the bills still owing -- so the
supplier statement reads **the payables lines of the general ledger** and
traces each to its supplier through the document that posted it:
`purchase_invoice` (bill, Cr), `vendor_opening_bills` (opening bill, Cr),
`settlements` (payment, Dr), `purchase_return`, `debit_note` and
`party_adjustments` (write-back or set-off), each Dr, and
`supplier_credit_refund` (money the supplier paid back against a return's or a
debit note's credit, Cr -- left out until D-BUY-48, which put the statement,
the balance confirmation and the per-supplier books check out by every
refund). **A new document that posts to payables for one supplier joins
`SUPPLIER_SOURCES`**, or all three close wrong. A cancelled document's
mirror carries the same source, so it appears on the day it was undone as a
`*_REVERSAL` line. Hand journals are refused on payables (D-FIN-11), so nothing
else moves the account.

Two properties follow by construction, and `tests/unit/test_supplier_statement.py`
holds it to both: **the closing balance is the payables ledger's balance for
that supplier** (and agrees with what Record Payment shows the open bills
owing, less any advance), and **the running balance is recomputed in date
order** -- opening summed from every line dated before the period, then the
lines by journal date -- never read off a stored snapshot, for the reason the
customer statement's is. Positive is what the firm owes; negative is an
advance or a credit the supplier owes back. It reads the account currently
nominated for `ACCOUNTS_PAYABLE`; a firm that re-points the purpose after
posting will see only what posted to the new account.

## A balance confirmation letter states the statement's own balance

Backlog 74 row 4. `GET /api/v1/customers/{id}/balance-confirmation?as_of` and
`GET /api/v1/vendors/{id}/balance-confirmation?as_of` draw one party's letter
as a PDF on the firm's letterhead (`app/common/balance_confirmation.py`,
`letter_pdf.py`, the firm block from `print_support.firm_party` and the accent
from the firm's invoice template). `GET /api/v1/customers/balance-confirmations`
and `/api/v1/vendors/balance-confirmations` zip one letter per party with a
balance that day -- one file each, because each goes to its own address -- and
refuse, by name, a day on which nobody had one. `as_of` defaults to today in
UTC.

**The balance is the statement's arithmetic for the same day**, so the letter
and the statement cannot disagree: a customer's is their receivable movements
dated on or before the day, outstanding less what is held on account
(`outstanding_delta - advance_delta`); a supplier's is the payables ledger's
lines for them, as above. The letter says in words who owes whom -- "due from
you to us" or "due from us to you", in rupees and in Indian words -- rather
than printing a sign, asks the party to sign and return it or send their
statement, and says that silence for 15 days is taken as confirmation (the
usual audit wording, decided by convention).

## PAN, TAN and GSTIN are checked when they are set

Backlog 53 item 2, on customers, vendors (header and tax rows) and the firm.
`settle_pan` and `check_tan_if_set` in `app/core/validation/common.py` are the
one implementation:

- **Format.** A PAN is `AAAAA9999A`, a TAN `AAAA99999A`, upper-cased; anything
  else is refused naming the field (`details.field`, which a file import turns
  into the column -- `service_issue` in `app/common/file_import.py`).
- **PAN against GSTIN.** Characters 3 to 12 of a GSTIN are its holder's PAN.
  When the GSTIN is built on one (a UIN is not, and is not compared), a blank
  PAN is **filled** from it and a different PAN is **refused naming both**.
- **Only what a write sets is checked** -- a create, a field the write moves,
  a tax row it adds. A PAN or TAN stored before the check existed is left
  alone by an edit that resends it unchanged, and checked the next time
  somebody changes it, so old data never blocks a change of phone number.
- **A customer's PAN and GSTIN may repeat** (decision A7, 2026-10-02): one
  company holds a GSTIN per state and is often several accounts, so a PAN
  filled from the GSTIN is always kept, and a save that repeats either is
  warned about by name rather than refused. Until A7 the PAN was unique and a
  filled one was left blank for the second branch.

## A month's GST is settled in one journal

Built 2026-10-01 (`docs/BACKLOG.md` §63, `app/gst_returns/services/gst_payment_service.py`). The month's liability per head is GSTR-3B 3.1(a) after credit notes, and its credit is table 4's net input credit plus what the month before carried. The set-off follows section 49(5) and rule 88A: IGST credit first and wholly, split across CGST and SGST in whichever way leaves the least cash; CGST credit never against SGST, nor SGST against CGST; cess only against cess.

Recording the challan posts **one journal**: Dr output tax for the whole liability, per head (below); Dr reverse-charge payable per head for 3.1(d); Cr each head's input-tax account (`INPUT_TAX_IGST/CGST/SGST`, cess to `INPUT_TAX`) for the credit it gave; Cr the bank for cash, interest and late fee; Dr the expense accounts the user chose for interest and late fee -- never the tax accounts, which must clear. The per-head figures live on the `gst_payments` row, never as JSON.

**Reverse charge is paid in cash only** (section 49(4)): it never enters the set-off, so no credit of any head can reach it, and it is added to the challan on top of what the set-off leaves (`reverse_charge_*` on the row). Its credit, claimed in 4(A)(3), is part of the month's net ITC and so may pay forward-charge tax like any other credit.

**Output tax is cleared head by head, and the single account with them.** Each head's account (`OUTPUT_TAX_IGST/CGST/SGST`) is debited by what the month's own journals credited to it -- settlements excluded -- never more than the head's liability; whatever is left of the liability (a month posted before the split, cess, a component the split does not name) is debited to `OUTPUT_TAX`. So a month before the split clears 2200 exactly as before, a month after clears the heads, and a month straddling it clears both. The next month's brought-forward credit is the row's `carried_*`, so only the latest settled month can be reversed, and one standing settlement per month is held by `UQ_gst_payments_firm_period_posted`.

**Which returns are due is read, not stored; that a return was filed is the one thing stored** (#898, `app/gst_returns/services/tax_calendar.py`, `GET /api/v1/gst-returns/calendar`, shown on Home). For each of the last three months the firm traded in it lists GSTR-1 (due the 11th of the next month, about the month's output tax), GSTR-3B (the 20th, about the cash the GST payment works out to, reverse charge included) and, only for a month that collected any, the TCS deposit (the 7th). Filing happens on the portal, so only a person can say a return was filed: `POST /api/v1/gst-returns/filings` writes a `gst_return_filings` row (withdrawn with `DELETE`, behind the same permission as recording a GST payment). A 3B is also done once its payment is recorded; a TCS deposit is never done, because recording one is not built. The calendar posts nothing.

**A quarterly filer deposits monthly and settles quarterly** (GST-7, A83, `app/gst_returns/services/gst_cash_deposits.py`). A PMT-06 deposit for month 1 or 2 sets nothing off: it posts **Dr GST Electronic Cash Ledger** (`GST_CASH_LEDGER`, 1340) **/ Cr the bank**, per head on the `gst_cash_deposits` row. The quarter's settlement (`return_period` = the quarter's last month) works the set-off over the whole quarter and pays its cash from the deposits head by head first -- **Cr GST Electronic Cash Ledger** for what it uses, `gst_payments.cash_ledger_*` -- and from the bank for the rest; interest is suggested on the bank part only. What no settlement has used is the balance, summed from the rows on every read. A deposit cannot be recorded for, or reversed from, a quarter already settled -- reverse the settlement first.

## Output tax is owed head by head

Built 2026-10-01 (`docs/BACKLOG.md` §63 item 3). **Every sales document credits
output tax one leg per GST head, and every reversal debits the same heads.**
`OUTPUT_TAX_IGST` (2210), `OUTPUT_TAX_CGST` (2220) and `OUTPUT_TAX_SGST` (2230)
join `OUTPUT_TAX` (2200), seeded with the chart for a new firm and by
`20261001_0201` for every existing one. `output_tax_purpose(component_code)`
names the account; UTGST goes with the state head; cess and anything else go
to 2200.

- **A sales invoice** splits by the components its lines recorded
  (`invoice_tax_by_component`, `app/sales_invoice/services/output_tax.py`),
  tax inside a price left out; **a sales return** by its own lines'
  components; **a credit note**, which stores one tax figure, the way the
  invoice it credits was taxed -- all IGST, or CGST and SGST halves
  (`credited_tax_by_component`, the rule GSTR-1's credit-note rows use).
- Each head is quantized to the ledger and the residual goes on the head the
  returns put it on -- IGST, else SGST, else CGST, as `settle_to_ledger` does
  -- so the legs sum to exactly the document's tax leg and the books agree
  with the return head by head (`_tax_legs`, shared with input tax; it went
  on the largest until D-SELL-48, 2026-10-05, which booked the odd paisa on
  CGST while the return filed it on SGST). With no component map the whole posts to 2200, as before.
- **History is left as posted**: no balance moves out of 2200. The GST
  payment clears both (above; `docs/OWNER_DECISIONS.md` A28).
- An unmapped head is named in the same refusal as every other gap.

## Reverse charge on a purchase bill

Built 2026-10-01 (`docs/BACKLOG.md` §68 row 8). Where the tax engine resolves a
bill line as reverse charge (a rule with the *Reverse charge* action), the
supplier charges nothing and the firm owes the tax itself:

- The line's components are kept with `reverse_charge` set and summed in
  `purchase_invoices.reverse_charge_tax_total`; `tax_total`, `grand_total` and
  **the payable exclude it**.
- Approval posts, beside the ordinary legs: **Dr input tax per head** (the
  same `INPUT_TAX_*` accounts) and **Cr reverse-charge payable per head**
  (`RCM_PAYABLE_IGST` 2260, `_CGST` 2270, `_SGST` 2280; cess to `RCM_PAYABLE`
  2250). Its own liability rather than output tax, because it is paid in cash
  only.
- Approval issues the **self-invoice number** (rule 47A) from its own series,
  `RCM_SELF_INVOICE` (prefix `RSI`, as `RSI-26-27-000001`; it was `SI`, the
  sales invoice's, and the two series issued the same numbers -- D-BUY-58,
  migration `20261005_0328`) -- never the bill's -- and a cancelled bill
  keeps it.
- Cancelling mirrors the journal, so the liability and the credit go with it.
- GSTR-3B: 3.1(d) `inward_reverse_charge`, 4(A)(3) `itc_reverse_charge`; the
  rows are left out of 4(A)(5) and out of the ordinary reversal in 4(B).
- **A purchase return or a debit note off the bill takes its share off**
  (2026-10-02, `app/purchase_invoice/services/reverse_charge.py`). The
  supplier charged nothing, so the note's own tax is zero; its share is of the
  bill line's **value** -- the returned line's net, a debit note line's
  taxable amount -- and that share of each reverse-charge component comes
  off: **Dr reverse-charge payable per head, Cr input tax per head**, the
  bill's legs mirrored. 3.1(d) and 4(A)(3) are reduced in the period the
  return was completed or the note approved (the credit by the recoverable
  part only, as the bill claimed it). The GST payment reads 3B, so it pays
  less. Cancelling the return or the note mirrors its journal, legs included,
  and 3B leaves a cancelled one out.

## The GST sales register is GSTR-1 laid out by document

Reports > Financial > *GST sales register* and *HSN summary of sales*
(`GET /api/v1/sales-invoices/reports/gst-register` and `/hsn-summary`,
`app/sales_invoice/services/gst_sales_register.py`, backlog §87 #1, SG-1) are
what a CA asks for outside the return: each approved bill by tax head, and
the outward supplies by HSN code and rate. Neither prices a document itself.
Both read through `GstReturnService`'s own readers -- `_priced` for a bill and
the `*_as_credits` shapers for a credit note, a customer debit note and a
sales return -- so every head is settled to what the journal credited
(`settle_to_ledger`) and the register, GSTR-1 and the ledger agree to the
paisa. `tests/unit/test_gst_sales_register.py` adds both reports up against
GSTR-1's Table 12 for the same days.

What counts is what GSTR-1 counts: a credit note and a completed sales return
are rows in minus on their own date, a customer debit note a row in plus, a
bill cancelled before its month's return was due is left out, and one
cancelled after it stays in its month with a *Cancelled invoice* row in minus
on the day of the cancellation. The register covers every GSTIN of the firm
at once; a firm with more than one compares it with the sum of its returns.
The HSN summary takes any period (a year, for GSTR-9) where the return itself
is held to three months, and has not been timed on the volume firm.

## A charge on the bill is taxed at its own rate and credited to its own account

Built 2026-10-05 (`docs/BACKLOG.md` §87 #4, SG-4; server #1157, and the bill's
**Other charges** editor on the desktop in #1159). A sales invoice now carries up to ten **charges** --
packing, handling, insurance -- each with a name, a pre-tax amount, an optional
SAC and an optional tax profile, in `sales_invoice_charges` (migration
`20261005_0319`, firm-owned). The two older fields are untouched:
`freight_amount` is still split across the lines and taxed at the goods' own
rates, and `additional_charges` is still an untaxed addition to the total.

- **Taxed like a line, by the profile it names.** `_replace_charges`
  (`app/sales_invoice/services/sales_invoice_service.py`) sends each charge
  through `TaxRuleService.simulate` as the same kind of supply to the same
  buyer on the bill's date, so a buyer in another state is charged IGST on the
  packing exactly as on the goods. A charge naming no profile carries no tax.
  The tax is stored **by GST head** on the row (`igst_amount`, `cgst_amount`,
  `sgst_amount`, `cess_amount`, with `tax_rate_percent`), never as JSON and
  never re-derived; tax already inside a price is not a head.
- **In the totals.** `tax_total` includes the charges' tax and `grand_total`
  their amount and tax; `subtotal` stays the goods. The response adds
  `charges` and `charges_total` (before tax).
- **Re-taxed on every draft save, replaced only when sent.** An update that
  omits `charges` keeps the stored ones (taxed again, against the buyer and
  date as they now stand); an empty list clears them.
- **Posting.** `ControlAccountPurpose.OTHER_CHARGES_RECOVERED` (*4050 Other
  Charges Recovered*, income; seeded with the chart and by `20261005_0319` for
  firms whose books are open, only where missing). `post_sales_invoice` takes
  `other_charges_amount`, credits that account with its ledger figure and
  takes the same figure off the `SALES_REVENUE` credit, so the receivable and
  the tax legs are what they were and the entry balances. The account is
  required only of a bill that carries a charge. Output tax by head adds the
  charges' heads under the plain codes `IGST` / `CGST` / `SGST` / `CESS`
  (`invoice_tax_by_component`). Cancelling reverses the one journal, so the
  charge comes off with it.
- **Returns.** `GstReturnService._priced` appends one priced row per charge
  (read once for the call, through the same `among` query or id chunks as the
  lines) and settles it with the lines, so B2B / B2CL / B2CS, the HSN table
  (under the charge's SAC, quantity 0), GSTR-3B and the GST sales register all
  carry it. A charge with no tax is *exempt* where it names a profile and
  *non-GST* where it names none, as a line is.
- **E-invoice.** A charge that names a profile is an item of the payload
  (`IsServc` Y, its SAC, which registration requires); one that names none is
  added to the document's `OthChrg`. Without this the items would not add up
  to `TotInvVal`.
- **Print.** The A4 and thermal bills list each charge by name between the
  taxable value and the tax rows; its tax joins the lines' per head and the
  HSN summary gains a row for its SAC.

**Not built:** carrying charges from the sales order (they are typed on the
bill); crediting a charge -- a credit note or a sales return
against the bill credits lines only and leaves the charge alone.
`tests/unit/test_invoice_charges.py` covers the tax by head within
and across states, the untaxed charge, the journal, GSTR-1 and 3B, the
update rule, the credit note, the print and the e-invoice item.

## A return before billing reverses the accrual, not the payable

**A return off a goods receipt line is taken first off what that line still
had to bill** (D-BUY-26, 2026-10-04; ERPNext's return against a purchase
receipt, the same in effect in Tally and Zoho). Until then every receipt-raised
return posted as a debit note -- Dr Trade Payables tax-inclusive / Cr
Inventory / Cr input tax -- even when no bill had reached the goods: QA01's
PR-2026-2027-000001 sent 2 of 6 unbilled units back and put the supplier at
-236 and input tax at -36 with no payable and no credit behind either, and the
bill then offered all 6, so a supplier who billed the 4 kept had the 2
deducted twice.

- **Left to bill** on a receipt line is accepted, less what approved or
  closed bills billed, less what completed returns took off before billing
  (`app/goods_receipt/billing.py`, `receipt_line_billing`). The goods
  receipt's response carries it per line and in total --
  `billed_quantity`, `returned_unbilled_quantity`, `left_to_bill_quantity`,
  `left_to_bill_amount` (tax included, at the line's own price).
- **Completing a return splits each receipt line** (`_split_against_billing`):
  up to what is left to bill is `unbilled_quantity`, stored on the return
  line with the accrual it took off (`grni_amount`, migration
  `20261004_0304`). That part posts **Dr goods received not invoiced (2300)**
  at the receipt's own cost -- the counterparty-facing leg valued from the
  receipt document -- against the one **Cr Inventory** at the movement's
  value, the gap to purchase price variance as before. No payable, no input
  tax: neither ever existed. Only the rest is the debit note #1080 fixed.
  One journal either way; a line can be both.
- **Rounding.** Each part's accrual is its quantity's share of the receipt
  line's cost. The bill that completes a receipt still takes the residual,
  now after what returns took (`_replay_accrual`, `returned`,
  `returned_cost`); a return that leaves nothing to bill or return on its
  receipt takes it instead, so the receipt's 2300 nets to exactly zero
  whichever comes last.
- **The bill is capped at what is left**, on save and again at approval
  (`_refuse_past_left_to_bill`), naming the receipt and line -- a draft
  bill for all 6 is refused once 2 have gone back.
- **Everything that reads a return's money reads the billed part**:
  `return_billed_amounts` (the payable and its tax) for the posting, the
  supplier credit and GSTR-3B's unplaced reversals; `return_tax_by_component`
  and `return_reverse_charge` scale each line by its billed share, so 4(B)(2)
  reverses only credit that was taken.
- **Cancelling mirrors the journal**, 2300 included, and a cancelled return
  drops out of left to bill. A goods receipt with a completed return against
  it cannot be cancelled -- the goods and their accrual would come off twice.
- Returns completed before `20261004_0304` read zero unbilled and stay debit
  notes. One raised off unbilled goods is put right by cancelling it and
  raising it again.

## Input tax is claimed head by head

**A bill's input tax posts one leg per GST head, and a return reverses the
same heads in the same proportions.** Purchase input tax posted to `1300
Input Tax` as one total until 2026-09-24, so GSTR-3B's credit -- claimed per
head, IGST against IGST and CGST and SGST each against their own -- could not
be derived from the books (D-CMP-20). Four things changed, in four PRs:

- **A bill line keeps the components it was charged** in
  `purchase_invoice_line_taxes` (#607), the mirror of
  `sales_invoice_line_taxes`: code, label, rate, base, amount, `recoverable`,
  `included_in_price`, written at pricing from the engine's answer and
  rebuilt on every edit. The line's `tax_profile_id` is the profile actually
  resolved.
- **Each head has an account** (#608): `INPUT_TAX_IGST` (1310),
  `INPUT_TAX_CGST` (1320), `INPUT_TAX_SGST` (1330) beside `INPUT_TAX` (1300),
  seeded with the chart for a new firm and by `20260924_0156` for every
  existing one. `input_tax_purpose(component_code)` in
  `app/finance/services/control_accounts.py` names the account a component
  is claimed through; UTGST goes with the state head; anything it does not
  name -- cess, another tax system -- goes to 1300.
- **The posting splits** (#609): `post_purchase_invoice` and
  `post_purchase_return` take `tax_by_component` and post one leg per head
  through `_input_tax_legs`, each head quantized to the ledger and the
  rounding residual on IGST, else SGST, else CGST (D-SELL-48), so the legs sum to the document's tax
  leg exactly. The bill sums its own rows; a return raised off a bill splits
  its tax in the bill line's proportions (`return_tax_by_component`, shared
  with 3B); a return off a **receipt** splits it in the proportions of the
  approved or closed bill lines that billed that receipt line, weighted by
  the quantity each billed (`_billed_lines`, D-BUY-28 -- the desktop raises
  returns off the receipt, and until 2026-10-04 those reversed 1300 whole
  while the bill had debited CGST and SGST). Only a return off an order names
  no bill and reverses 1300 as a whole; what goes back off a receipt line
  nothing has billed yet reverses no tax at all (next section, D-BUY-26). The same mapping takes a receipt-raised return's share of
  reverse charge and of blocked tax. **Without a map the total posts to 1300 as it always
  did** -- a bill approved before the rows existed keeps its posting and is
  not backfilled, because re-running the tax engine on old dates can answer
  differently from what the supplier charged.
- **3B reads the rows** (#610): table 4A(5) per head from the period's
  approved and closed bills, 4B(2) from completed returns off them, net ITC
  the difference; `unplaced_reversals` and `bills_without_components` say
  what could not be placed rather than zeroing it.

Cancelling an approved bill mirrors its journal leg for leg, so the split
reverses itself. Nothing on the sales side changed: output tax has always
carried its components and 3B's outward half has always read them.

## Tax the firm may not claim is a cost, not input tax

Backlog 78 row 1, D-TAX-1, decision A36. Tax a supplier charged on a purchase
that gives no credit -- blocked under s.17(5) (a car, catering, personal use,
gifts) or ineligible for another reason -- is part of the payable but not input
credit. Each purchase bill line carries `itc_eligibility`: the line's own, else
the product's, else a tax rule's *Input credit blocked*, else ELIGIBLE. Its tax
rows are `recoverable` only when the line is ELIGIBLE.

| Document | Claimable tax | Tax not claimable |
| --- | --- | --- |
| Bill | Dr input tax, head by head | Dr *Input Tax Not Claimable* (5450, `INELIGIBLE_INPUT_TAX`) |
| Return off the bill, or off the receipt it billed | Cr input tax, its share | Cr 5450, its share |
| Debit note off the bill | Cr input tax, its share | Cr 5450, its share |

Reverse charge keeps the component's own `recoverable`: the liability is owed
whether or not the credit is. GSTR-3B reports blocked credit in 4(A)(5) and
reverses it in 4(B)(1) (`itc_reversed_blocked`, CBIC circular 170/02/2022);
ineligible credit never enters 4(A) and is shown in 4(D)(2) (`itc_ineligible`).
A return's or a debit note's blocked share is never a 4(B)(2) reversal --
nothing was claimed.

## The opening trial balance is one journal, replaced whole

Built 2026-09-30 (`docs/BACKLOG.md` §36, the second cutover gap). Cash, bank,
fixed assets, loans, capital and tax balances brought over from the previous
tool are entered as **one statement as at one cutover date**, account by
account -- Tally's opening balances per ledger, Xero's conversion balances --
at **Accounts > Opening Balances** or `PUT /api/v1/finance/opening-trial-balance`
(`JOURNAL_POST`; read with `JOURNAL_VIEW`).

- **It is kept as one posted journal**, `OTB-n`, source `opening_balances`
  (`app/finance/services/opening_balances.py`), not in a table of its own: the
  ledger already is the record. Saving again **reverses the standing journal
  on its own date** (`OTB-n-REV`) and posts the new one, so what was entered
  and when stays readable; an empty statement just takes it off. The journal
  screen's reverse refuses it, as it refuses any document's journal.
- **Lines name accounts by code**, so a statement exported from the old tool
  loads without looking ids up. It is all or nothing: every bad row is named
  in one refusal and nothing is written, and a date with no open period is
  refused **before** the old statement is reversed.
- **Whatever the lines leave unbalanced goes to Opening Balance Equity** --
  credited when debits exceed credits, debited otherwise -- the counterpart
  opening stock, customer balances and supplier bills already post to. So
  the equity account itself is refused as a line.
- **Sub-ledger accounts are refused** (the same set as hand journals,
  D-FIN-11): receivables, payables, stock and the rest each have their own
  opening path that keeps the party or the batch beside the figure --
  a customer's opening balance, a supplier's opening bills, opening stock.

## A return is a view of the documents

**A return is a view of the documents, and a supply is placed by the tax it
was charged.** `app/gst_returns` stores nothing: GSTR-1 and the outward half
of 3B are derived on every read, so a cancelled invoice drops out and a
credit note lands in the month it was *issued*. Three rules, each of them a
defect found by driving it. **The place of supply is read off the tax** --
CGST with SGST is chargeable only within one state, IGST only between two,
so the document settles it, and for an unregistered buyer nothing else can;
the first version read a `state_code` field `customers` does not carry, so
every B2CS row filed a **blank** place, which the portal rejects. Where the
tax says a border was crossed and the buyer is unregistered, the invoice is
named in `unplaced_invoices` rather than filed blank. **A credit note to an
unregistered buyer is netted off its B2CS row**, not filed in CDNR and not
dropped -- dropped, on the belief this system could not produce one, 3B
deducted a credit GSTR-1 never declared and the two returns could not be
reconciled. And **3B is aggregated from the documents, never parsed out of
GSTR-1's own JSON**. `quantize_ledger` is the filing scale: documents carry
four decimals, no portal takes them, and the rounding happens once on the
way out or the HSN summary and the invoice detail drift apart a paisa at a
time. `split_components` in `app/tax/services/gst_buckets.py` is the one
place a component code becomes a bucket, shared with `app/einvoice`, so what
is filed and what was registered cannot disagree.

**The filed tax is what the journal credited, per document.** The journal
credits `quantize_ledger` of a document's whole tax, once; rounding CGST and
SGST each on its own declared 36.86 + 36.86 = 73.72 on a bill whose halves
were 36.855 and whose journal credited 73.71 -- 30 of WHOLE01's 52 live bills
(D-CMP-4). `settle_to_ledger` (same module) rounds every bucket of every line
to paise and puts the residual on the last bucket that carried tax (SGST
intra-state, IGST inter-state), and both GSTR-1/3B and the e-invoice payload
fold its answer; `intra_state_halves` does the same for a credit note, which
stores one tax figure.

**A month once due is not rewritten.** Derived on read, a return re-read a
bill's *current* status, so cancelling an August bill in September took it
out of August's GSTR-1 -- a return already due on 11 September -- and no
month showed the reversal (D-CMP-11). Nothing records that a return was
filed, so its due date stands in for it: a bill cancelled **after** the 11th
of the month following its date stays in its own month, and the
cancellation is declared in the month it happened (the date of the
receivable credit the cancellation posted) as a credit for the whole bill --
CDNR for a registered buyer, off B2CS otherwise, and deducted in 3B. One
cancelled before the due date simply drops out, as before.

## A credit note's receivable is rounded the way its journal rounded it

**A credit note's receivable is rounded the way its journal rounded it.**
Third occurrence of the four-decimals-into-a-two-decimal-receivable defect
-- `sales_invoice` hit it and fixed it privately, `sales_return` carried the
identical bug untouched, and `app/credit_note` was the third: approving a
note whose total ran past two decimals raised a pydantic error rather than
posting, so the whole approval failed. Rounding the *sum* is not rounding
the *parts*, so the receivable takes `quantize_ledger(taxable) +
quantize_ledger(tax)` -- what the journal actually credited -- or the two
books sit a paisa apart with nothing to say which is right. Invisible until
a seeded credit note reached it, which is what the demo history is for.

## A sandbox registration must never read as a filing

**A sandbox registration must never read as a filing.** `app/einvoice`
registers invoices and raises e-way bills, and `mode` is NOT NULL on both
tables with **no server default** -- a default is one migration away from
silently being LIVE. The sandbox marks every reference it mints (`SBX...`)
so a number carried away from its row still says what it is, and the desktop
shows the mode beside it everywhere. `portal_for("LIVE")` raises rather than
falling back: a firm that believes it is filing must never be rehearsing.
The payload is refused **locally, naming the field** (no GSTIN, no HSN)
rather than sent to return a numeric code, and the CGST/SGST-versus-IGST
split is read off the two GSTINs' **state codes**, so the document and its
tax cannot disagree. One registration and one bill per invoice by unique
key; a refusal lands on the row and a retry counts the attempt; withdrawal
is inside 24 hours judged in UTC, and afterwards a credit note is the way.
Live filing needs only GSP credentials and one implementation of
`InvoiceRegistrationPortal`.

## A credit note reverses tax on the base the invoice taxed, charges and freight included

**A credit note reverses tax on the base the invoice taxed, charges and
freight included.** `_charged_taxable` returned `gross - discount -
bill_discount`, which was the whole taxable value until #191 moved
`freight_amount` inside it; `charges_amount` had never been there. Since
`SalesInvoiceService._line_net_amount` hands the tax engine
`gross - discounts + charges + freight`, the credit note was working from a
smaller base than the tax it reverses was charged on, and it cost twice: the
cap refused a full credit of what the customer actually paid, and `_tax_rate`
-- tax over that base -- came out inflated, so crediting 1,000 of a 1,050
base reversed 189 of output tax where 180 was collected. Found by the
2026-09-03 review. **Nothing was wrong when it was written**; another
module's arithmetic moved underneath it, which is the thing to check
whenever a taxable base changes -- grep the fields rather than trusting that
a helper still means what its name says.

## A new financial year opens income and expense at zero

**The stored balances run on across years; the reports that show an opening
take the year's start off.** `ledger_balances` carries every account's closing
into the next period whatever its type, and no closing entry is posted at year
end -- the balance sheet depends on that, since it computes the firm's earnings
from the income and expense closings. A trial balance, an account ledger and an
account summary answer "this year", so `GeneralLedgerService._brought_forward`
takes off what an income or expense account had run up before the financial
year began, and the trial balance adds one equity row, **Profit and loss
brought forward**, so it still balances (D-FIN-22, 2026-09-30). A report that
shows an opening balance for an income or expense account must go through it,
and must take the same figure off its closing balance, so the closing is where
the running balance ends (D-FIN-24, 2026-10-02).

## A credit note that states its lines reverses tax

**A credit note that states its lines reverses tax; the bare receivable
adjustment did not.** It posted two legs -- receivable and sales returns --
because a `customer_receivable_transactions` row carries one figure and no
lines, so it had nothing to say what rate to take off. Its route,
`POST /customers/{id}/receivables/transactions`, was retired on 2026-09-30
(D-FIN-23). A firm
correcting a rate after invoicing therefore kept declaring output tax on a
price nobody paid. `app/credit_note` is the document that closes it:
`post_credit_note_document` posts the third leg. It is **not** a sales
return -- a return moves stock and this moves none -- and it always names
the invoice **and the line**, because the rate is derived from what that
line was actually charged rather than read off a tax profile that may since
have been edited. The cap is the line's charged value less what other live
credit notes took; **sales returns are deliberately not netted off**, since
a return may have sourced from a delivery note that cannot be mapped back to
an invoice line. Approving posts *and* moves the customer balance, or
neither. `CREDIT_NOTE_APPROVE` is separate from `CREDIT_NOTE_MANAGE` and not
granted to `SALES_MANAGER`: drafting is bookkeeping, approving reverses a
declared tax.

## A debit note to a customer charges tax and is owed on its invoice

Backlog 77 row 5 (2026-10-02, OWNER_DECISIONS A40). **More charged on a sale
already invoiced is a debit note against that invoice** (CGST Act s.34(3)),
never a second invoice -- which would declare a second supply -- and never a
hand adjustment of the balance, which charges no tax. `app/customer_debit_note`
(`POST /api/v1/customer-debit-notes`, `DRAFT -> APPROVED`, or `CANCELLED`) is
the credit note turned round: it names the invoice and the lines, moves no
stock, and charges tax at the rate each line was actually charged. Approving
posts `post_customer_debit_note_document` *and* raises the balance (a
`DEBIT_NOTE` receivable row), or neither:

```
Dr  1100 Trade Receivables            taxable + tax
    Cr  4000 Sales Revenue            taxable
    Cr  2200 Output Tax (per head)    tax, split the way the invoice was taxed
```

**The extra is owed on the invoice it names**, as TallyPrime's
against-reference debit note is: `settled_against` nets approved debit notes
(`debited_against`), so Record Receipt offers the invoice at its total plus
the note, a receipt allocated to it settles both, and the ageing ages the
extra from the invoice's due date. There is no cap -- a price can rise by
whatever the parties agree -- so the control is the approval:
`CUSTOMER_DEBIT_NOTE_APPROVE`, not granted to `SALES_MANAGER`. Cancelling
mirrors the journal and reverses the receivable row, and is refused while
money received on the invoice has already met the extra; an invoice with a
live debit note cannot be cancelled. GSTR-1 declares it in CDNR (or CDNUR, or
on the B2CS row) with note type **D**, the HSN summary takes its value and no
units, and GSTR-3B adds it to 3.1(a) and reports it as `debit_notes_added`
beside `credit_notes_deducted`.

## `app/settlements` is money in and money out

**`app/settlements` is money in and money out**, and it is one document for both directions: a receipt from a customer and a payment to a vendor differ only in signs. It posts to the general ledger through `DocumentPostingService.post_settlement`, and `settlements.journal_entry_id` is NOT NULL because the defect it exists to close is a settlement that never reached the ledger. ****A customer's opening balance posts** `Dr Accounts Receivable / Cr Opening Balance Equity` as of 2026-08-15, and is refused outright when the firm has no chart of accounts or open period -- a balance nobody can book is one the firm should not be told it has recorded. Revising one or deleting the customer mirrors the entry, traced through `customer_receivable_transactions.journal_entry_id`. `CustomerService.post_receivable_transaction` still moves a customer balance without writing a journal** -- it is the older, lower-level path and the two books drift by every rupee recorded through it, so record money through `/api/v1/receipts` and `/api/v1/payments` instead. What an invoice still owes is derived from `settlement_allocations`, never stored on the invoice. A settlement is reversed rather than edited or deleted: a mirror journal cancels it, the allocations stop clearing invoices but still record what they had cleared, and `CustomerService.reverse_receivable_transaction` puts the customer's balances back by the **deltas stored on the original row** -- never recomputed, because a receipt of 500 against an outstanding 300 splits into 300 of balance and 200 of advance and only that row remembers the split. **A receipt whose advance has since been applied wrote more than one row** -- its own and an `ADVANCE_APPLY` per application -- and the reversal undoes every one of them, the applications first (D-SELL-8, 2026-09-19): taking "the" row picked one at random, so a bounced cheque that had been applied was refused as overtaken or left the customer's balance out of step with 1100.

## `app/finance` and automatic GL posting

`app/finance/` was rewritten on 2026-08-09 and is live at `/api/v1/finance` (migration `20260809_0042`). It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace. The prior `accounting_event_consumer.py`, which guessed accounts by name, was removed — see git history if you want its posting rules.
**Automatic GL posting is built, and this line said for months that it was not.** It claimed the feature needed "a per-firm control-account mapping design" -- which is exactly what `firm_control_accounts` is, and it carries 45 purposes per firm as of 2026-10-03 -- count them with `len(ControlAccountPurpose)` rather than trusting this number (`ACCOUNTS_RECEIVABLE`, `INVENTORY`, `OUTPUT_TAX`, `INPUT_TAX_IGST`, `PURCHASE_PRICE_VARIANCE`, `LOYALTY_PAYABLE`, `COMMISSION_PAYABLE`, `TCS_PAYABLE` and the rest). **Eleven modules post through `DocumentPostingService`**: `delivery_note`, `sales_invoice`, `sales_return`, `credit_note`, `goods_receipt`, `purchase_invoice`, `purchase_return`, `settlements`, `loyalty`, `tcs` and `commission`. WHOLE01 alone holds 337 journal entries, and `verify_sample_data.py` fails the run if any approved invoice has not posted. A stale line like this is worse than no line: it talks the next reader out of checking, and it survived precisely because nobody re-derived it. Correct one when you find it rather than working around it.

## Rule 37 reversals and reclaims (backlog 78 row 4, 2026-10-02)

A bill unpaid 180 days after its date has the credit on its unpaid share
reversed: **Dr Input Tax Not Claimable (5450), Cr input tax per head**; when it
is paid the reclaim posts the mirror. Each is its own journal, referenced
`R37-<bill number>-<n>` with `source_module = "rule37"`, and each is a row in
`itc_reversals`. What stands reversed on a bill is the sum of those rows, never
a column; what the bill owes comes from `PaymentService.outstanding_invoices`.
Only eligible, recoverable, non-reverse-charge credit is ever reversed -- the
credit 4(A)(5) claimed.

## Rule 42 common credit (GST-4, 2026-10-03)

A firm with exempt, nil-rated or non-GST sales gives back the share of its
common credit they take: D1 = C2 x E / F per head, each return period, worked
from GSTR-3B's own figures (`app/gst_returns/services/rule42.py`). Posting it
(`rule42_mode` POST) is **Dr Input Tax Not Claimable, Cr input tax per head**,
dated inside the period, referenced `R42-M-<yyyymm>-<n>`, a row in
`itc_common_reversals`. The year's true-up, posted after 31 March, is the
difference between the year worked whole and what the periods posted: a
positive head posts the same way, a negative one the mirror (`R42-Y-...`).
GSTR-3B reports the reversal in 4(B)(1) and a reclaim in 4(A)(5), each in the
return its movement date falls in. A period cannot be taken back while its
year's true-up stands.

## The cash flow statement reads, never posts (ACC-9, 2026-10-03)

`app/finance/services/cash_flow.py` builds the statement by the indirect
method from the same span balances as the trial balance. Because every
journal balances, each non-cash account's credit less debit is its cash
effect and the three sections sum to the change in the cash and bank
accounts; `is_reconciled` fails only when an account the statement treats as
cash is not, or the reverse -- the chart's groups decide. It posts nothing.

## Bank reconciliation matches postings and posts nothing (ACC-1, 2026-10-03)

`app/bank_reconciliation` ties a bank statement's lines to the **postings on
the bank ledger account** -- not to receipts or payments as such -- so a
contra voucher, an expense, a TDS challan or a hand journal reconciles the
same way a receipt does. A deposit is a debit on the account, a withdrawal a
credit. Matching writes no journal: the cleared date is the matched line's
date and lives on the match, never on the posting. Bank charges and interest
the books do not have yet are booked as ordinary journals or expenses and then
matched; until then the reconciliation statement lists them as items the bank
shows and the books do not. An entry and its reversal, both unmatched, net to
nothing and are left out. A posting dated before the account's first imported
statement and matched by no line is taken as cleared before reconciling began
(decision A125).

## A promise to pay is recorded, never posted (SG-8, 2026-10-05)

`app/collections` keeps what a customer said about paying: `payment_promises`
holds the day promised **for**, the amount, a note, the day it was taken and
who took it, against one sales invoice or -- with no invoice -- against the
account as a whole. It moves no balance and writes no journal; the receipt
that later arrives is what posts, through `/api/v1/receipts` as always.

**Whether a promise was kept is derived on every read, never stored.** It is
*kept* when the posted receipts dated from the day it was taken up to and
including the day promised for cover the amount -- what they allocated to the
bill (`settlement_allocations`), or, for a promise on the account, what the
customer paid in that window. Past that day without them it is *broken*; on
the day, *due today*; before it, *pending*. Reversing a receipt therefore
un-keeps the promise it had kept, with nothing to put right. Money that came
before the promise was taken, or after its day, does not count toward it --
**before by time, not by day**: a receipt recorded earlier the same day does
not keep a promise taken after it (`Settlement.created_at >=
PaymentPromise.created_at`, D-SELL-56). **Recorded after is the whole test
of "after"**: the receipt's own date is no lower bound, so yesterday's cash
keyed in after the promise keeps it; only the day promised for bounds the
date (D-SELL-73). **A kept promise cannot be
withdrawn**; the server refuses it, not only the screen (D-SELL-62).
The amount received is one correlated expression (`received_amount` in
`app/collections/services/promises.py`), so the list filters on status and
pages in SQL.

**A promise is withdrawn, never edited or deleted** (`cancelled_at`,
`cancel_reason`, audited). A changed promise is a withdrawn one and a new one,
so how often a customer has promised stays on record. A bill promise is
refused on a draft, on another customer's bill, on a bill that owes nothing,
and for more than the bill owes -- read from Record Receipt's own list
(`ReceiptService.outstanding_invoices`), so the two cannot disagree.

**The collector** is `customers.collector_id`, a member of the firm checked
like the account manager; where it is blank the customer's account manager
(`customers.salesman_id`) collects. A promise records who took it, defaulting
to that person on the day.

**The collection sheet** (`GET /api/v1/collections/sheet`, and `/sheet/pdf`
for the paper) is Record Receipt's list of open bills for every customer --
opening bills included -- with days overdue, the latest live promise on the
bill (else on the account) and the collector, sorted by collector, customer
and due date. `as_of` dates the overdue count and the promise's status; what a
bill owes is always what it owes now. **The chase list**
(`GET /api/v1/collections/promises/due-today`) is the promises for today not
yet paid plus the broken ones nobody has taken a newer promise on; a bill that
has since stopped owing drops off it while its promise still reads broken.

Reading takes `RECEIPT_VIEW` and writing `RECEIPT_CREATE`. The desktop screens
(#1164) are Sell > All Sell screens > Money > *Collection Sheet* and *Payment
Promises*, with a **Collector** on the customer. Not built: the promise on the
customer statement and on
`GET /api/v1/receipts/outstanding`, reminders raised from a broken promise,
and a promise against an opening bill (it is made on the account instead).

## A till's shortage or excess posts to Cash short and over (SG-7, 2026-10-05)

A cashier's shift (`counter_shifts`, `docs/SALES_CHAIN_RULES.md`) moves no
money by being opened or by taking a bill: the receipts the bill's tenders
become are what post, exactly as before. **Closing is the only thing a shift
posts, and only when the drawer disagrees with the books.**

`DocumentPostingService.post_cash_short_and_over` posts one journal for the
difference between what was counted and what was expected --
`quantize_ledger(abs(difference))`:

| The drawer is | Debit | Credit |
| --- | --- | --- |
| **short** (counted less than expected) | *Cash short and over* | the shift's cash account |
| **over** (counted more than expected) | the shift's cash account | *Cash short and over* |

so the cash account reads what is actually in the drawer. An exact count posts
nothing. The journal is dated the UTC day of the close, carries
`source_module = "counter_shift"` and the shift's id, and takes the shift's
number (`SHIFT-000123`) as its reference -- a shift closes once, so the
reference is its own.

`ControlAccountPurpose.CASH_SHORT_AND_OVER` is **one account for both
directions**, as Tally keeps it: *6960 Cash Short and Over*, an indirect
expense, on which a credit balance is a gain. It is seeded with the chart and
by `20261005_0324` for firms whose books are open (only where missing, never
overwriting; a firm that already used 6960 for something else is left to map
the purpose itself). It may be mapped to an income or an expense account. **It
is required only when a difference is posted**: a close with one and no
account mapped is refused naming the purpose, and nothing closes.

Expected cash is the float plus the cash tenders whose receipts still stand,
derived on every read; the figure stored on the shift at the close is the
snapshot the count was judged against. A receipt reversed after the close
moves cash through its own mirror journal and does not reopen the shift.

The shift's cash account defaults to the firm's `CASH` control account, and
that is where every cash receipt is booked. A shift that names another asset
account posts only its difference against that account -- routing the
receipts themselves per till is not built.
