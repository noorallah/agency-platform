# Profit and loss: what fills it, and where a firm's own expenses go

For the firm's owner or accountant, and for QA. It explains what the
**Profit & Loss** screen shows, which figures reach it by themselves, and how
to record the expenses no document raises -- rent, fuel, salaries, electricity,
telephone -- so the profit it shows is the firm's real profit.

Written 2026-09-26 against the version 2 screens (Accounts menu in the top
bar), with its menu paths brought up to release 1.3.0 on 2026-10-04: the
Accounts drop-down shows daily work only (Journal Entries, Expenses, Ledgers,
Bank Reconciliation, Trial Balance, Profit & Loss, Balance Sheet, GST Returns)
and every other screen is behind **All Accounts screens** at its foot. The steps were taken from the product's own tested cases
(`INDEPENDENT_TEST_CASES.md`, TC-FIN-001 and TC-FIN-003).

## 1. What the Profit & Loss screen shows

**Accounts → Profit & Loss.** Choose an **Accounting period** (a month); the
screen opens on the month you are in. It lists:

| Part | What is in it |
| --- | --- |
| **Income** | Sales, less Sales Returns, and any other income account |
| **Expenses** | Purchases, Cost of Goods Sold, Discount Allowed, Purchase Price Variance, Inventory Adjustment, Commission, Loyalty -- and every expense account the firm adds |
| **Net profit or loss** | Income less expenses |

Two columns: **This period** (the month chosen) and **Year to date** (from the
start of the financial year to the end of that month). A figure in brackets is
negative. Showing a whole financial year, or a range of months, in one go is
not built yet (BACKLOG section 50).

## 2. What reaches it by itself

Every trading document posts its own journal when it is approved or completed,
so nobody types these:

| When you ... | The P&L moves by ... |
| --- | --- |
| Approve a **sales invoice** | Sales (income) up by the taxable value |
| Dispatch a **delivery note** | Cost of Goods Sold (expense) up by what the goods cost |
| Complete a **sales return** / approve a **credit note** | Sales Returns (reduces income) |
| Approve a **debit note to a customer** (more charged on an invoice already raised) | Sales (income) up by the extra taxable value -- the same Sales account as the invoice, not a separate income account |
| Approve a **purchase invoice** at a price different from the receipt | Purchase Price Variance |
| Post a stock **adjustment** or **write-off** | Inventory Adjustment |
| Approve a **commission payout** | Commission Expense |
| Customers earn **loyalty points** | Loyalty Expense |

Stock bought and not yet sold is **not** an expense: it sits in Inventory on
the balance sheet until it is sold, when its cost moves to Cost of Goods Sold.

## 3. Expenses no document raises: rent, fuel, salaries

These are recorded in two steps, both under **Accounts**: open an account for
the expense once, then enter a journal each time it is paid.

### Step A -- open an expense account (once per kind of expense)

**Accounts → All Accounts screens → Books → Chart of Accounts → + New.**

| Field | What to enter |
| --- | --- |
| Group | **EXP · Direct Expenses** (the one expense group the books open with) |
| Code | a free number in the 6000s, for example the table below |
| Name | what the expense is |
| Type | **EXPENSE** |

Suggested accounts:

| Code | Name | Typical entries |
| --- | --- | --- |
| 6100 | Rent | shop, godown and office rent |
| 6200 | Fuel and Transport | diesel, petrol, freight paid to transporters |
| 6300 | Salaries and Wages | staff salaries, helpers' wages |
| 6310 | Staff Welfare | tea, meals, bonus, uniforms |
| 6400 | Electricity and Water | power and water bills |
| 6500 | Telephone and Internet | mobile, broadband |
| 6600 | Repairs and Maintenance | vehicle, shop, equipment repairs |
| 6700 | Office Expenses | stationery, printing, courier |
| 6800 | Bank Charges | charges, commission, card fees |
| 6900 | Miscellaneous Expenses | anything that fits nowhere else |

The group, type and code cannot be changed once saved; the name can. Choose the
group before the code: an EXPENSE account refused under the Revenue group says
"A ledger account must share its group's account type".

### Step B -- record each payment as a journal

**Accounts → Journal Entries → + New.**

| Field | What to enter |
| --- | --- |
| Accounting period | the month the expense belongs to |
| Journal type | **GEN · General** |
| Voucher type | **JV · Journal Voucher** |
| Date | the date it was paid |
| Reference | the bill or receipt number, e.g. `RENT-SEP-26` |
| Narration | what it was for, e.g. *Godown rent for September* |
| Lines | the expense account **Debit**, and the money account **Credit** -- `1010 Bank` when paid from the bank, `1000 Cash` in cash |

**Save Draft**, then select it on the list and **Post**. A draft changes
nothing; only a posted entry reaches the ledger and the P&L. The two sides
must be equal.

### Worked example -- one month's expenses

| Expense | Debit | Credit |
| --- | --- | --- |
| September rent, paid by bank | 6100 Rent **25,000** | 1010 Bank 25,000 |
| Diesel for the delivery van, cash | 6200 Fuel and Transport **3,000** | 1000 Cash 3,000 |
| September salaries, paid by bank | 6300 Salaries and Wages **1,20,000** | 1010 Bank 1,20,000 |

After posting all three, **Profit & Loss** for September shows the three
accounts under **Expenses**, total expenses up by **1,48,000**, and the net
profit down by the same amount. **Trial Balance** still reads **Balanced**;
Bank is down by 1,45,000 and Cash by 3,000.

### When the bill carries GST you can claim

Rent from a GST-registered landlord, a repair bill with GST: the tax is input
tax credit, not an expense. Put it on its own lines:

| Account | Debit | Credit |
| --- | --- | --- |
| 6100 Rent | 25,000 | |
| 1320 Input CGST | 2,250 | |
| 1330 Input SGST | 2,250 | |
| 1010 Bank | | 29,500 |

Only 25,000 reaches the P&L; the 4,500 is recovered against output tax.
Fuel (petrol and diesel) is outside GST: the whole amount is the expense.
Salaries carry no GST.

### Splitting expenses by branch or department

**Settings (the gear) → Set up → Account structure → Cost Centres** (a branch, a van, a
department). An account can be
set to require one, and each journal line then says which centre it belongs
to, so the cost of running each branch can be read separately.

## 4. Where to look afterwards

| To see | Go to |
| --- | --- |
| Each expense entry | Accounts → **Journal Entries**, search the reference |
| Everything booked to one expense | Accounts → **Ledgers**, choose the account and the month |
| Month's result | Accounts → **Profit & Loss** |
| Books still in balance | Accounts → **Trial Balance** (the *Balanced* chip) |

A posted entry is not edited or deleted: a mistake is put right with
**Reverse** on the entry and a new, correct one, so the history stays.

## 5. What is not built yet

Recorded so a decision can be made; none of these stops the steps above.

1. **The Expenses screen -- built since this guide was written.** Tally's
   payment voucher and Zoho Books' *Expenses* let a clerk pick an expense, an
   amount and "paid from", with the journal made for them. In 1.3.0 that is
   **Accounts → Expenses → New** (it also takes the TDS deducted, the section
   and the payee's PAN; see `docs/GO_LIVE_GUIDE.md`), so a manager can record
   rent without the journal screen. The hand-typed journal in section 3 still
   works and needs an accountant's permission (post journals).
2. **Indirect Expenses -- built 2026-09-27.** The books open with an
   *Indirect Expenses* group holding Rent, Salaries and Wages, Electricity,
   Telephone and Internet, Travel and Conveyance, Office and General Expenses,
   Repairs and Maintenance and Bank Charges (6000-6700); migration
   `20260927_0162` gave every firm with open books the same. **Still open:**
   the Profit & Loss sections by account type, not by group, so it does not
   yet show a gross profit (Direct) above a net profit (Indirect) -- that
   belongs with backlog section 50 -- and the Chart of Accounts screen cannot
   add a group.
3. **Payments pays suppliers only.** Buy → Payments settles purchase bills; it
   cannot pay an expense account.
4. **P&L by year or chosen months** is backlog section 50.
