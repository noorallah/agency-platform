# Go-live guide for the firm's accountant

What to do on the first day, and the jobs that come round every month,
quarter and year. Written 2026-10-01 for the first firms going live
(`docs/GO_LIVE_PLAN.md`). Menu paths are the new screens': the menu bar along
the top, and the **gear** at its right for settings.

Read it once before the first day, then keep it beside you for the first
month end.

---

## 1. Before the first day: bring the firm over

The firm is set up by whoever installed the product, from **Admin > Firms >
Set up**. That panel ticks off what the firm needs before it can post, and
under it, **Opening balances** lists what the firm brings over from its old
software, in this order. Do them in this order: each later step names things
the earlier ones created.

| Step | Where | What it needs |
| --- | --- | --- |
| 1. Products | Masters > Products > Import | Product codes, units, HSN, tax group |
| 2. Customers | Masters > Customers > Import | Codes, GSTIN, PAN, TAN where they deduct TDS |
| 3. Suppliers | Masters > Vendors > Import | Codes, GSTIN, PAN |
| 4. Customers' opening bills | Masters > Customers > ... > Import opening bills | Every unpaid bill, at what was still owed on it |
| 5. Suppliers' opening bills | Masters > Vendors > ... > Import opening bills | Every unpaid supplier bill |
| 6. Opening trial balance | Accounts > Opening Balances | Every other ledger balance on the cutover date |
| 7. Opening stock | Stock > Opening Stock > Import from file | Quantity, cost, batch and expiry per item per warehouse |

Every import works the same way:

1. **Download the template.** It names the firm's own codes on its Lists
   sheet, and its example row imports as it comes.
2. **Fill it**, or paste your old software's export into it. Common
   headings ("Customer Code", "Invoice No", "Pending Amount") are
   understood.
3. **Check file.** Every problem is listed by row and column, and nothing is
   written. Fix them all and check again.
4. **Import.** The whole file goes in, or none of it.

**One cutover date for everything.** The opening bills, the trial balance and
the opening stock all post on the day the books here start. Choose it once
(usually the first day of a month) and use it on every screen that asks.

**A customer's opening balance is bills or one figure, never both.** If a
customer was imported with an opening balance figure, set it to 0 before
importing their bills, or the bills are refused by name. Bill by bill is
better: each receipt then clears a bill, and the ageing knows how old each
one is.

**Before trading starts, check three things against the old software,** on
the cutover date:

- **Accounts > Trial Balance** matches the old trial balance.
- **Reports > Financial > Stock valuation** (as on the cutover date) matches
  the old closing stock value; its last rows also show the Inventory account
  beside it, which must agree.
- **Reports > Financial > Customer outstanding** and **Vendor outstanding**
  match the old outstanding lists, party by party.

If any one differs, find the difference before the first invoice. It is ten
minutes' work on day one and a week's work at the year end.

---

## 2. Tax deducted at source (TDS)

### When the firm deducts TDS (paying a supplier, rent, fees, transport)

Record the payment as normal, at the **full amount of the bill**, and type
what was deducted:

1. **Buy > Payments > Record payment.** Choose the supplier and enter the
   **bill's full amount**.
2. Under **TDS deducted**, enter what was deducted, and choose the
   **TDS section**: 194Q purchase of goods, 194C contractors and
   transporters, 194J professional fees, 194I rent, 194H commission, and so
   on.
3. The screen shows what is actually **paid from the bank**: the amount less
   the deduction.
4. Apply it to the bill as usual. The supplier is settled in full.

For **rent, fees and other expenses**, do the same on **Accounts > Expenses >
New**: the full amount, the TDS deducted, the section, and the **payee's
PAN**.

What it posts: the supplier (or expense) for the full amount, the bank for the
net, and **TDS Payable** for the deduction, which the firm now owes the
government.

**Paying the challan** (by the 7th of the next month): record a journal,
**Accounts > Journal Entries > New**: debit *TDS Payable*, credit *Bank*, the
challan number in the reference.

**The quarterly return (26Q).** **Reports > Financial > TDS deducted** for the
quarter lists every deduction: deductee, PAN, section, amount, TDS and the
return quarter. Give it to the CA. A row reading **"PAN not given"** means the
deductee has no PAN on record: the higher rate applies (section 206AA), so add
their PAN on the supplier's screen, or check the rate with the CA.

### When a customer deducts TDS from what they pay you

1. **Sell > Receipts > Record receipt.** Choose the customer and enter the
   **invoice's full amount**, not what reached the bank.
2. Under **TDS deducted**, enter what the customer deducted and choose the
   section (usually 194Q).
3. The screen shows what was **received in the bank**. Apply it to the
   invoice as usual. The invoice is settled in full.

What it posts: the customer cleared for the full amount, the bank for what
arrived, and **TDS Receivable** for the deduction. The firm claims it against
its own income tax.

**Every quarter**, open **Reports > Financial > TDS deducted by customers**
and tick each row against **Form 26AS** on the income tax portal, by the
customer's **TAN**. A deduction missing from 26AS means the customer has not
filed it: ask them to.

### Before TDS is recorded at all

- Put the **firm's TAN** on the firm (Admin > Firms, beside PAN).
- Put the **customer's TAN** on each customer that deducts (customer form).
- Put **PANs** on suppliers and customers.

---

## 3. Approving many orders at once

On **Sell > Sales Orders** or **Buy > Purchase Orders**:

1. Tick the orders in the list (up to 100 at a time).
2. Choose **Approve selected**, or **Cancel selected** (it asks for a
   reason).
3. Each order is approved on its own, by the same rules as approving it
   alone. One order over its customer's credit limit does not hold back the
   others: the result lists **what was approved and what was refused, and
   why**.
4. **Retry the refused** sends only the refused ones again, after you have
   dealt with what stopped them.

---

## 4. Closing a month

Closing a month stops anybody posting into it by mistake after you have
reconciled it: a bill dated last month and typed today is refused, by name.

1. Reconcile the month first: bank, cash, the outstanding lists, GST
   (including the GSTR-2B match, section 7).
2. **Gear > Financial Years.** Open the year, and in its list of months press
   **Close** beside the month.
3. To correct something later, press **Open** on that month, post the
   correction, and close it again.

Close months in order, and keep the current month open.

---

## 5. Closing the year

1. Close every month of the year first (section 4), and post or delete every
   **draft journal** dated in it. The close refuses while either remains, and
   says which.
2. **Gear > Financial Years > Close year.** The year is locked: nothing can be
   posted into it.
3. **No closing entry is posted, and none is needed.** The balance sheet
   carries the year's profit into retained earnings itself, and the next
   year's trial balance starts from the balances as they stand, as Tally does.
4. If the auditor needs a correction, **Reopen year** (only a user holding the
   reopen right; it asks for a reason, which is kept), post the correction,
   and close it again.

Before closing, make sure the next year exists (**Gear > Financial Years**):
invoices dated in the new year need it.

---

## 6. When a licence check stops a sale or a purchase

Drug and FSSAI licences are checked when a sale or purchase is approved, if
the firm has switched the check on: **Masters > Licence Check** (under the
configuration lists), separately for sales and purchases:

- **Off**: nothing is checked.
- **Warn**: the approval says what is missing and offers **Approve anyway**.
- **Block**: the approval is refused.

When it **blocks**:

- **The usual cause is a lapsed or missing licence.** Add or renew it, then
  approve again: the firm's own licence under **Masters > Trade Licences**,
  the customer's or supplier's on their screen. A licence that lapsed before
  the document's date does not count for it.
- **A product needing a licence the party does not hold** (a Schedule H drug
  to a shop with no drug licence) is a real stop. Do not override it to get
  the bill out.
- **Override...** is offered only to users holding the override right. It
  asks why, and the reason is recorded on the document's timeline for the
  auditor. Use it for a licence you have seen on paper that is not yet
  entered, and enter it the same day.

---

## 7. Every month, in short

| When | What | Where |
| --- | --- | --- |
| Daily | Receipts and payments, with TDS where deducted | Sell > Receipts, Buy > Payments |
| Daily | Expenses | Accounts > Expenses |
| By the 7th | TDS challan for last month, as a journal | Accounts > Journal Entries |
| By the 11th | GSTR-1 | Accounts > GST Returns |
| Before the 20th | Import the month's **GSTR-2B** from the portal and look at what it lacks: bills you booked that the supplier has not filed | Accounts > GSTR-2B Reconciliation |
| By the 20th | GSTR-3B, and pay the GST due: credit set off, the rest by challan | Accounts > GST Returns, then Accounts > GST Payment |
| Month end | Reconcile, then close the month | Gear > Financial Years |
| Quarter end | TDS deducted list to the CA for 26Q; tick TDS by customers against 26AS | Reports > Financial |
| Year end | Close every month, then the year | Gear > Financial Years |

Dates are the statutory ones as of 2026; check the current calendar with the
CA. Home also shows a **Tax calendar** (for whoever may open GST Payment):
the last three months' GSTR-1, GSTR-3B and TCS deposit, each due, late or
done. Filing happens on the portal, so press **Mark filed** there with the date
and the acknowledgement number; recording the GST payment closes GSTR-3B for
you.

---

## 8. Backups

The installed copy backs up on a schedule. Once a month, check that the
latest backup file is there and dated today or yesterday. A backup nobody has
looked at is a hope, not a backup.
