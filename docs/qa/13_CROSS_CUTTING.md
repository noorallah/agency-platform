# Cross-cutting: permissions, concurrency and grants

Part of the QA test suite in `docs/qa/` for **release 1.3.0**, the first
end-to-end test pass (it includes 1.2.0). Read `00_README.md` first: it
explains the preparations, the accounts and how to record results. Every menu
path is the 1.3.0 menu: `Sell > Quotations` is the Sell drop-down on the menu
bar, `Sell > Documents > Proforma` is a screen in the
Documents column, and `Settings > Set up > Pricing > Price Lists` is the gear at the
right of the bar. Generated on 2026-10-15 from `docs/INDEPENDENT_TEST_CASES.md` (cases driven against a
running server) and the application's own screen catalogue; regenerate
rather than hand-edit when those change.

Each case keeps its original id (TC-…), so a failure can be traced to the
developer case it came from. Steps marked **(HTTP)** are optional API checks
for a tester with a REST client such as Postman; skip them otherwise.

## Permissions — the server refuses, not only the button

`SALES_EXECUTIVE` holds `CUSTOMER_VIEW`, `TERRITORY_VIEW`, `SALES_VIEW` and the
three `SALES_*_CREATE` codes, nothing else. A hidden button is not a control:
each case below checks the screen **and** the route behind it.

### TC-PERM-001 — What a salesperson is not offered

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**. Click the gear and look for a **Platform** part; open Sell and Accounts and look for Commission, Credit Notes and TCS.
- **Expect:** **no Platform part** on the Settings page. The territory screens (Settings > Set up > Territories & routes, on `TERRITORY_VIEW`) are offered, and none of **Commission** (Sell > Incentives), **Credit Notes** (Sell > Documents) or **TCS** (Accounts > Tax filing) — nor Price Lists, Promotions, Targets, Proforma, E-Invoice or GST Returns, each hidden on its own view code. That is expected, not a fault.
### TC-PERM-002 — The credit policy opens read-only

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** as the prepared **Seller**, Masters > Customers → toolbar **Settings**.
- **Expect:** the dialog **opens read-only** — the policy's fields shown but disabled, Save greyed, only Close works — with "Changing the policy needs the manage customer settings permission."
### TC-PERM-003 — Six writes, six refusals; two reads allowed

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps (HTTP)** — sign in as the prepared seller (`POST /api/v1/auth/login`) and send, with `X-Firm-ID` of QA01:
  1. `GET /api/v1/document-framework/numbering-rules`, then `PUT /api/v1/document-framework/numbering-rules/{any listed id}` `{"name": "x"}`.
  2. `GET /api/v1/customers/credit-settings`, then `PUT` it `{"enforcement": "OFF"}`.
  3. `POST /api/v1/commission/payouts/{any id}/approve` and `/pay`.
  4. `POST /api/v1/credit-notes/{any id}/approve`.
  5. `PUT /api/v1/tcs/settings` `{"is_enabled": true}`.
- **Expect:** both **reads answer 200** — any member may read how documents are numbered and the credit rule that warns them. **All six writes answer 403**, body `{"success": false, "error": {"code": "authorization_denied", …}}`. The id need not exist: the permission is checked before the record is looked up.
---

## Concurrency — two people, one record

Run these with **two clients** on one server (or two windows of one client),
**A** and **B**, both signed in as the same preparation's firm admin. An editor that
saves from **inside** its dialog — customer, sales order, sales invoice,
product, price list, promotion, coupon, customer group, target, payout
adjustment — says on a lost race, keeping the dialog open with the typing in
it: *"Somebody else saved this <thing> while you were editing it. Your changes
are still here and have not been sent. Copy anything you need, then close and
reopen to see theirs."* An editor that closes first — branch, warehouse,
quotation, batch, lot, serial number, beat plan, place, territory, tax
component — says in a red toast: *"Somebody else saved this <thing> while you
were editing it. Your changes were not saved. Open it again to see theirs and
redo yours."*

### TC-FIN-030 — Bills handed to a collector and taken back change no balance and no report

*Added 2026-10-13 (backlog 122). Covered by unit and widget tests and driven over HTTP; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** two customers in different areas, each with two approved sales bills still unpaid; two people of the firm to act as collectors; a user who is a Cashier only.
- **Steps**
  1. Note the first customer's closing balance on *Customer Statements*, and the totals of the trial balance.
  2. Open *Sell → Money → Bills with Collectors*.
  3. Tick the first customer's first bill, choose the first collector under **Hand to** and press **Hand over ticked**.
  4. Tick the same bill and another, choose the second collector and press **Hand over ticked**.
  5. Type the first customer's area in **Area or city**, choose the second collector and press **Hand over all matching**; confirm.
  6. Type one bill number of the second customer in both **Bill no. from** and **Bill no. to**, clear the area, and press **Hand over all matching**; confirm.
  7. Read the first customer's closing balance and the trial balance again.
  8. Record a receipt in full for a bill that is out, then choose **History**.
  9. Tick every row still out and press **Take back ticked**. Read the balances once more.
  10. Sign in as the Cashier and open *Bills with Collectors*.
- **Expect**
  - Step 2: every unpaid bill, the customer's area and city beside the name, **With** empty.
  - Step 3: a message says 1 bill was handed to the collector and for how much; the row shows his name and today under **Handed on**.
  - Step 4: refused, naming the bill already out; the other ticked bill stays in the office.
  - Step 5: the message says 1 bill handed and 1 already out and left; the first bill is still with the first collector.
  - Step 6: only the bill of that number goes out.
  - Step 7: both figures are what they were in step 1.
  - Step 8: the paid bill is no longer among the unpaid bills; History lists it as out, owing 0.00 now, with what it owed when handed.
  - Step 9: every row reads as taken back with its date; the unpaid bills show nobody under **With**; the balances are unchanged by the taking back.
  - Step 10: the list is shown; **Hand to** and the three buttons are not.

### TC-FIN-031 — A bill collector sees only the bills handed to him

*Added 2026-10-13 (backlog 123). Covered by unit and widget tests and driven over HTTP; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** two customers, the first with three approved sales bills still unpaid and the second with one; two users of the firm hired from the **Bill Collector** job (role Bill Collector only); a user who may hand bills out (the firm's administrator).
- **Steps**
  1. As the administrator open *Sell → Money → Bills with Collectors*. Hand the first customer's first bill to the first collector and the first customer's second bill to the second collector. Leave the third bill and the second customer's bill in the office.
  2. Sign in as the first collector.
  3. Open *Sell → Money → My Bills to Collect*.
  4. Sign in as the second collector and open *My Bills to Collect*.
  5. As the administrator record a receipt for part of the first bill, then sign in as the first collector and open the screen again.
  6. As the administrator take the first bill back, then sign in as the first collector and open the screen again.
  7. As the first collector, look in the menu for Receipts, Customers and Bills with Collectors.
- **Expect**
  - Step 2: Home opens with no figures. The menu offers one screen of the firm, *My Bills to Collect*; the gear offers his own preferences.
  - Step 3: three rows, all of the first customer. The first bill is marked **With me** with the day it was handed over; the second and third bills are marked **Not handed to me**. The lines above the list count 1 bill with him and 2 other unpaid bills of his customers, each with its total. The second customer is not on the list. The second bill does not say who carries it.
  - Step 4: the same three rows, the second bill marked **With me** and the other two **Not handed to me**.
  - Step 5: the first bill shows what it still owes after the receipt.
  - Step 6: the list is empty and says no bills are handed to him.
  - Step 7: none of the three is in his menu.

### TC-FIN-033 — One receipt from a parent closes bills of three shops

*Added 2026-10-13 (backlog 126). Covered by unit and widget tests and driven over HTTP; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a parent customer with three shops under it (TC-CUST-014 makes them), and one approved sales bill on each shop, say for 100.00, 250.00 and 400.00.
- **Steps**
  1. Note what each shop owes on *Customer Statements*.
  2. Open *Sell → Money → Receipts* → **Record receipt**. Choose the parent as the customer.
  3. Look at the list of bills.
  4. Amount 1,000.00, by bank. Set 100.00, 250.00 and 400.00 against the three shops' bills. Save.
  5. Open the statement of each shop, and of the parent.
  6. Open the receipt in the list and look at the bills it cleared.
  7. Raise one more bill of 150.00 on the first shop and approve it. On the receipt press **Apply**, choose that bill, 150.00, save.
  8. Open the statement of the first shop and of the parent again.
  9. Record a receipt from the second shop itself and look at the list of bills.
  10. Reverse the parent's receipt with a reason. Open the three shops' statements and the parent's.
- **Expect**
  - Step 3: the three shops' bills are listed, each with its shop's code and name under the bill number, and a line above says the bills of the shops under this customer are listed too.
  - Step 4: saved as one receipt in the parent's name for 1,000.00; 750.00 set against bills, 250.00 not.
  - Step 5: each shop owes nothing, and its statement has one receipt line for its own bill's amount with the parent's receipt number and "Paid by" the parent. The parent's statement has one receipt line of 250.00, held on account.
  - Step 6: each bill is followed by its shop's code and name.
  - Step 7: saved. The receipt has 100.00 left not set against a bill.
  - Step 8: the first shop owes nothing again. The parent holds 100.00 on account.
  - Step 9: only that shop's own bills are listed; no other shop's and not the parent's.
  - Step 10: every shop owes its bills again in full, the parent holds nothing on account, and the receipt reads Reversed.

### TC-FIN-034 — Year end: what closing refuses, and starting the next year

*Added 2026-10-13 (customer task C3, decision D12). Driven over HTTP on a preparation firm, on a year made for the purpose; **no screen was clicked**, so the steps are written from the build, not from the screen. Do not run steps 2 to 9 on a year the firm is still working in.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a user holding the rights to create, close and reopen a financial year; a past year with two months in it, both open, and one draft journal dated in it (make them over the API: the screen makes no past year).
- **Steps**
  1. Open *Settings → Firm → Financial Years*. On the year you are working in, press **Close year** and confirm.
  2. Choose the past year. Press **Close year** and confirm.
  3. Press **Close** beside its second month.
  4. Close its first month, then its second. Press **Close year** and confirm.
  5. Delete the draft journal. Press **Close year** and confirm.
  6. Try to press **Open** beside one of its months, and type a journal dated in the year.
  7. Press **Reopen year** and leave the reason empty.
  8. Type a reason and confirm. Look at the months.
  9. Open the audit trail and find the reopening.
  10. Open *Settings → Firm → Numbering Series*, choose the sales bill series and preview a number for the first day of the next year.
  11. On *Financial Years* press **Start next year** and confirm.
  12. Press **Start next year** again and confirm.
- **Expect**
  - Step 1: refused. The message says how many months are open and names them. The year stays open.
  - Step 2: refused, naming the two open months.
  - Step 3: refused: the first month, which comes before it, is still open.
  - Step 4: the months close. The year is refused, naming the draft journal.
  - Step 5: the year closes and reads LOCKED.
  - Step 6: both refused; the message says the year is locked or the month is closed.
  - Step 7: refused: a reason is required.
  - Step 8: the year is open again. Its months still read CLOSED.
  - Step 9: one line for the reopening, with the reason typed.
  - Step 10: the number carries the next year (27-28) and its counter is 000001, though no such year has been made.
  - Step 11: a new year appears, beginning the day after the last one ends, with twelve months, all open. The year you are in is still open.
  - Step 12: refused: that year is already there and has not begun.

### TC-FIN-035 — The account books: an expense from the form to the books

*Added 2026-10-13 (customer task C4, decision D13). Driven over HTTP on a preparation firm; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a user holding the rights to manage accounts and to record and cancel an expense. Note the closing balance of *Cash book* and *Bank book* before you begin.
- **Steps**
  1. Open *Accounts → Books → Chart of Accounts* and start a new account: group **Indirect Expenses**, code **6800**, name *Packing material*, type **EXPENSE**. Save.
  2. Change the code to one not used (6810) and save. Open the account again and try to change its code, its type and its group; change its name.
  3. Open *Accounts → Books → Expenses* and start a new expense. Try to pick tomorrow in **Date**.
  4. Record 3,200 today: **Expense** *Packing material*, **Paid from** *Bank*, a payee, a bill number, a narration. Save.
  5. Record 150 today, **Paid from** *Petty Cash*.
  6. In the search box type *Packing*, then the payee, then the bill number.
  7. Open *Accounts → Books → Ledgers*, pick *Packing material* and this month.
  8. Open the report *Bank book* for today, then *Cash book*, then *Day book*.
  9. On *Expenses* select the first expense and press **Cancel** with no reason, then with one.
  10. Read *Bank book* and the *Packing material* ledger again.
  11. Cancel the second expense. Open the account, switch **Active** off and save. Start a new expense.
- **Expect**
  - Step 1: refused: an account with this code already exists (6800 is *Bad Debts*).
  - Step 2: saved. Afterwards the code, the type and the group cannot be changed; the name can. There is no delete.
  - Step 3: the calendar offers no day after today.
  - Step 4: saved with a number beginning EXP, posted at once. The row reads *Paid from: Bank*.
  - Step 5: saved; the row reads *Paid from: Petty Cash*.
  - Step 6: each search finds the expense it names; the first finds both.
  - Step 7: Opening 0, Debits 3,350, Credits 0, Closing 3,350, one line per expense with the balance after it.
  - Step 8: the Bank book has a payment of 3,200 naming *Packing material* and closes 3,200 lower than noted. The Cash book has the 150 with *Petty Cash* as its account and not the 3,200. The Day book lists both.
  - Step 9: refused without a reason; with one, the expense reads CANCELLED and stays in the list.
  - Step 10: the Bank book closes where it began. The ledger reads Credits 3,200 and Closing 150.
  - Step 11: the Cash book closes where it began. *Packing material* is no longer offered in **Expense**.

### TC-FIN-036 — Paying out of cash that is not there is asked about, never refused

*Added 2026-10-13 (customer task F2, backlog 133). Covered by unit and widget tests and driven over HTTP on a preparation firm; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a user who may record expenses, payments, receipts and refunds; a supplier; a customer who owes nothing. Read *Cash book* for today and note what **Cash** and **Petty Cash** hold; call the Cash figure C.
- **Steps**
  1. Open *Accounts → Books → Expenses* and record an expense today, **Paid from** *Petty Cash*, for 300 more than Petty Cash holds. Press **Save**.
  2. Press **Go back**. Then press **Save** again and **Save anyway**.
  3. Record an expense today, **Paid from** *Bank*, for far more than the bank holds.
  4. Record an expense today, **Paid from** *Cash*, for less than C.
  5. Record a payment to the supplier today, mode **Cash**, for 700 more than Cash now holds. Press **Record payment**, then **Save anyway**.
  6. Record the same payment with mode **Bank transfer**.
  7. Record a receipt of 100 from the customer by **Bank transfer**, then a refund of 100 to the same customer in **Cash**. Press **Record refund**, then **Save anyway**.
  8. Record a receipt from the customer in **Cash**.
  9. Open *Cash book* for today.
- **Expect**
  - Step 1: nothing is saved. A box titled *Cash would go below zero* reads *Petty Cash holds … and this pays … out of it, which leaves it 300.00 below zero. Save anyway?*
  - Step 2: **Go back** returns to the form with everything typed still there, no error on it, and no new expense in the list. **Save anyway** saves the expense, posted.
  - Step 3: saved at once; no question for a bank account.
  - Step 4: saved at once; cash covers it.
  - Step 5: the box names *Cash*, what it holds and 700.00 below zero; **Save anyway** saves the payment.
  - Step 6: saved at once.
  - Step 7: the box reads *Cash is already 700.00 below zero … and this pays 100.00 more out of it*; **Save anyway** saves the refund.
  - Step 8: saved at once; money coming in is never asked about.
  - Step 9: the cash book shows every payment made, and closes below zero by what was confirmed.

### TC-FIN-038 — Part returns, a return of a line typed with GST, and a debit note on a paid bill

*Added 2026-10-14 (D-FIN-28, D-FIN-29, D-SELL-90, D-SELL-97, row G4). Driven over HTTP on a preparation firm; the screens were not clicked.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a product at 100.00 plus 18% local GST with stock; four customers of the case's own, each owing nothing.
- **Steps**
  1. First customer: sell 3 at 100.00 with a line discount of 200.00 (a bill of 118.00). Return 1, then 1, then 1 off the bill, completing each.
  2. Second customer: an order of 500 at **100.00 including GST**; deliver and bill it (50,000.00). Return all 500 off the bill, typing no price.
  3. Third customer: order and deliver 12 at 100.00 and raise **no** bill. Return all 12 off the delivery note and open the return.
  4. Fourth customer: sell 24 at 100.00 (2,832.00), take a receipt of 2,832.00 against the bill, return 7 off the bill, then approve a customer debit note of 100.00 before tax on the bill.
- **Expect**
  - Step 1: the three returns post 39.33, 39.34 and 39.33 to the customer's account, 118.00 in all; the customer owes 0.00 and holds 0.00, and the bill is not offered in *Record Receipt*.
  - Step 2: the return is **taken**, reads 42,372.88 + 7,627.12 = 50,000.00, and the customer owes 0.00. It is not refused with "A customer cannot be credited more than they were billed."
  - Step 3: the return states 1,416.00 and `credited_amount` **0.00**; the customer's account does not move. (The same return off a bill reads `credited_amount` 1,416.00.)
  - Step 4: after the return the customer holds 826.00. After the debit note the bill still owes nothing, the customer **owes 0.00 and holds 708.00**, and *Customer credits* reads 708.00 held. Cancelling the debit note is refused until the receipt is reversed, naming 118.00.
### TC-FIN-039 — A cheque written to any account, dated today or ahead

*Added 2026-10-14 (customer task F13, COL-11, backlog 150). The server was driven over HTTP on a preparation firm and the screen is covered by widget tests; **no screen was clicked and no cheque was printed on a leaf**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a user who may record payments, expenses and journals; a supplier; a customer who holds 500.00 on account (a receipt by bank transfer not set against a bill); an expense account; a ledger account that no document keeps, such as *Capital* or a loan account. Note the bank account's balance.
- **Steps**
  1. Open *Accounts → Books → Cheques Issued* and press **New**. Choose the bank under **Drawn on**, **Pays** *Expense account*, pick the expense account, leave the name as it fills in, amount 1,250.00, a cheque number, the date today. Read the line under the date, then press **Write cheque**.
  2. In the print box that opens, press **Print**.
  3. Open *Accounts → Books → Expenses*, select the expense the cheque became and press **Print cheque**.
  4. Write a cheque to the supplier for 4,000.00 dated one month ahead, typing another name over the one filled in.
  5. Select that cheque and press **Present**, leaving today's date.
  6. Write a second cheque with the same number on the same bank.
  7. Write a cheque to the customer for 500.00 dated today. Open *Sell → Money → Refunds*, select the refund and press **Print cheque**.
  8. Write a cheque to the ledger account for 10,000.00 dated today.
  9. Write a cheque to the supplier dated ahead, then select it and press **Cancel**, giving a reason. Select it again.
  10. Select the cheque of step 1 and press **Returned**, with a reason.
  11. Record an expense paid from *Cash*, select it and press **Print cheque**, then **Print**. On *Refunds*, select a refund paid in cash.
  12. Sign in as a user who may record expenses and nothing else about money, and open **Write a cheque** from the command box (*write a cheque*).
- **Expect**
  - Step 1: the line reads *Dated today or before: it is recorded now as an expense.* The cheque is saved; the list shows it with **Pays** *Expense*, **Paid to** the name, **Recorded as** the expense's number, and the bank is down by 1,250.00.
  - Step 2: the cheque prints with its date, the name, the amount in words and in figures, at the bank's saved layout.
  - Step 3: the same cheque prints from the expense.
  - Step 4: the line reads *Dated ahead: it is held and posts nothing until you present it.* The cheque is **Held**, the name typed is kept, **Recorded as** is blank and neither the bank nor the supplier's account has moved. **Print cheque** prints it now, with next month's date.
  - Step 5: refused: the date cannot be before the cheque's own date. Presented on its date, it becomes a payment to the supplier on account and **Recorded as** shows the payment's number.
  - Step 6: refused, naming the number already written on that bank account; the form stays open with everything typed.
  - Step 7: the cheque is recorded as a refund, the customer holds 0.00, and the refund prints as a cheque in the customer's name.
  - Step 8: **Recorded as** reads *Payment voucher*; the ledger account is debited and the bank credited 10,000.00.
  - Step 9: the cheque is **Cancelled** and **Print cheque** is not offered for it.
  - Step 10: the cheque is **Bounced**, the expense it became is cancelled and the bank has the 1,250.00 back.
  - Step 11: the print box stays open and says a cash expense has no cheque to print; nothing prints. **Print cheque** is not offered for the cash refund.
  - Step 12: the list itself needs the right to see payments, so this user is told he cannot see it (known and left, backlog 150). With that right added, **Pays** offers *Expense account* only.
### TC-FIN-040 — A salary advance to an employee, and its recovery

*Added 2026-10-14 (customer task P4, USR-3, backlog 153). The server was driven over HTTP on a preparation firm and the screen is covered by widget tests; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a user who may record and cancel expenses. Note the balance of *Cash*, of the bank account and of *Salaries and Wages*.
- **Steps**
  1. Open *Accounts → Books → Staff Advances* and press **Add employee**. Type a name and save. Press **Add employee** again and type the same name.
  2. Select the employee and press **Give advance**: today, paid from the bank account, 5,000.00.
  3. Press **Record recovery**, choose *Taken from salary*, leave the salary account, and type 5,000.01.
  4. Change the amount to 2,000.00 and save.
  5. Open *Accounts → Statements → Trial Balance* for this month and find the employee's account.
  6. Back on *Staff Advances*, press **Give advance**, paid from *Cash*, for more than the cash account holds.
  7. Press **Record recovery**, choose *Paid back in cash or bank*, *Cash*, 500.00.
  8. Open *Accounts → Books → Expenses*, press **New** and open **Paid from**.
  9. On *Staff Advances*, select the employee and press **Entries**. Select the advance of step 2 and press **Cancel**, with a reason.
  10. Cancel the recovery of step 7, then the recovery of step 4, then the advance of step 2, each with a reason.
  11. Give an advance dated tomorrow.
  12. Sign in as a user who may see expenses and not record them, and open *Staff Advances*.
- **Expect**
  - Step 1: the employee is on the list with a code `ADV-` and a number, owing 0.00. The second is refused: he already has an account.
  - Step 2: the entry is saved with a number beginning `SADV`; the list shows Advanced 5,000.00, Still owes 5,000.00; the bank is down by 5,000.00.
  - Step 3: refused: he owes only 5,000.00.
  - Step 4: saved. The list shows Recovered 2,000.00, Still owes 3,000.00, and *Salaries and Wages* is up by 2,000.00.
  - Step 5: his account stands at 3,000.00 on the debit side, under *Staff Advances*, and the trial balance balances.
  - Step 6: the screen asks before saving, naming what the cash account holds; **Save anyway** saves it and **Go back** saves nothing. (Go back here, or cancel the entry afterwards.)
  - Step 7: saved. Still owes 2,500.00 and *Cash* is up by 500.00.
  - Step 8: the employee is not on the **Paid from** list.
  - Step 9: refused: he owes less than this advance; the recovery taken against it is cancelled first.
  - Step 10: each is cancelled. The list shows Still owes 0.00, and the bank, *Cash* and *Salaries and Wages* are back where they started.
  - Step 11: refused: it cannot be recorded on a future date.
  - Step 12: the list opens; **Add employee**, **Give advance**, **Record recovery** and **Cancel** are not offered.
### TC-FIN-041 — One customer pays another customer's bill

*Added 2026-10-14 (customer task P5, COL-12, backlog 154). The server was driven over HTTP on a preparation firm and the screen is covered by widget tests; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** two customers, A and B, neither a shop of the other and neither with shops; B with two approved bills not yet paid; a user who may record receipts. Note what A owes and holds on account, and what B owes.
- **Steps**
  1. Open *Record Receipt* and choose customer B. Leave **Paid by** alone and look at it.
  2. Press **Another customer paid** and pick customer A. Set the whole amount of B's first bill against it and save.
  3. Answer **Cancel** to the question. Save again and answer **Record receipt**.
  4. Open B's statement, then A's statement.
  5. Print the receipt.
  6. Reverse the receipt, with a reason. Look at both customers again.
  7. Record a receipt from A for 10,000.00 against no bill. Open it and press **Apply**. Look at the bills offered.
  8. Choose **Bill of another customer**, pick B, pick B's first bill, apply its whole amount and confirm.
  9. Record a receipt for B, **Paid by** A, for the amount of B's second bill and 50.00 more, set against that bill.
  10. Record a payment to a supplier and look for **Paid by**.
- **Expect**
  - Step 1: **Paid by** reads B's own name.
  - Step 2: B's bills stay listed; a line says the money is recorded as A's and that anything left over stays on A's account.
  - Step 3: the screen asks *Paid by A for B?*. Cancel saves nothing. Record receipt saves one receipt in A's name.
  - Step 4: B's bill is paid, B owes that much less, and B's statement has a line *Paid by A*. A's statement has the receipt and a line *Paid for B* with the bill's number, and A owes and holds exactly what it did before.
  - Step 5: the receipt reads *Received from* A and *Paid for* B, with the bill under *Against*.
  - Step 6: B owes the bill again; A is unchanged.
  - Step 7: A holds 10,000.00 on account. **Apply** offers A's own bills, not B's.
  - Step 8: B's bill is paid; A holds that much less on account; no new entry is in the day book for it.
  - Step 9: B owes nothing; the 50.00 is held on A's account, not B's.
  - Step 10: a payment has no **Paid by**.
### TC-FIN-032 — The collector's day sheet adds up to the receipts

*Added 2026-10-13 (backlog 124). Covered by unit and widget tests and driven over HTTP; **no screen was clicked**, so the steps are written from the build, not from the screen.*

- **Preconditions:** A finished firm (every Set up step done, Wholesale profile), its firm administrator, a Viewer, two product categories, a customer, and one 500.00 cash receipt recorded from that customer.
- **Also needs:** a customer with three approved sales bills still unpaid, each for the same amount; a user hired from the **Bill Collector** job; the firm's administrator. *Customers → Credit settings → Collectors record their own receipts* switched **off**.
- **Steps**
  1. As the administrator open *Sell → Money → Bills with Collectors* and hand the three bills to the collector.
  2. Sign in as the collector and open *Sell → Money → My Bills to Collect*.
  3. On the first bill press **Record**, choose **Collected in full** and save.
  4. On the second bill press **Record**, choose **Part collected**, enter less than the bill owes, name a promised day for the rest and save.
  5. On the third bill press **Record**, choose **Not collected**, write a note and save.
  6. As the administrator open *Bills with Collectors → Day sheet* and choose the collector and today.
  7. On the first two lines press **Record receipt**.
  8. As the administrator switch *Collectors record their own receipts* **on**. Hand a fourth unpaid bill to the collector. As the collector record it **Collected in full**.
  9. As the collector try to withdraw the fourth bill's line.
- **Expect**
  - Step 3: the dialog says the office records the receipt. The bill stays on his list marked **Collected** and still owes its full amount. No receipt exists.
  - Step 4: the bill is marked **Part collected** with the amount. The promise for the rest is on *Payment Promises* in his name.
  - Step 5: the bill is marked **Not collected**. The line under the list counts three lines and says how much is still to be handed in.
  - Step 6: three lines. Stated is the first bill plus the part; in receipts is nothing; the sheet says it **does not add up** by that amount.
  - Step 7: each line names its receipt. The first bill owes nothing, the second owes the rest. The sheet says it **adds up**. Each receipt is on *Receipts*, dated today, applied to its bill.
  - Step 8: the dialog says Save records the receipt. The fourth bill leaves his list; its receipt is on *Receipts*; the sheet still adds up. He still has no Receipts screen.
  - Step 9: refused, naming the receipt to reverse first.

### TC-CONC-001 — Two people editing one customer

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps:** on **A** and **B**: Masters > Customers → double-click `QA-CM`. On A change the phone → **Save**. On B change the phone to something else → **Save**.
- **Expect:** A saves ("Customer updated."). B is refused **inside the editor** with the sentence naming `customer`; the dialog stays open with B's typed phone still in the box. Cancel B; reopen: A's phone.
### TC-CONC-002 — The same race on an order, a product and a price list

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** create a draft Sales Order for `QA-C01` first (any line). Then, on A and B: open that draft → **Edit**, change **Remarks** on both, Save A then B. Repeat on Masters > Products → `QA-DET` (Description) and Settings > Set up > Pricing > Price Lists → `STANDING` (the **Name** — the dialog has no Description).
- **Expect:** B is refused each time with the sentence naming `sales order`, `product`, `price list`; typing kept, dialog open.
### TC-CONC-003 — Saving unchanged does not move the version

- **Preconditions:** A firm administrator and a salesperson of QA01, and a customer `QA-CM` *Master Check* fully described: one billing address, one contact, credit limit 50,000, payment terms 30 days, standing discount 7.5%, segment `QA-RET`, phone +919800000100.
- **Steps:** on A alone, double-click `QA-CM`, change nothing → Save; do it again. **(HTTP)** `GET /api/v1/customers/{id}` before and after; compare the `ETag`.
- **Expect:** accepted both times; the `ETag` and the body's `version` are **the same before and after** — so a client re-sending the same `If-Match` is still accepted. *(Driven: `"2"` before and after an unchanged PUT.)*
### TC-CONC-004 — Two approvals of one order

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps:** create a draft order for `QA-C01`. On A and B select it in the grid. **Approve** on A; then **Approve** on B, whose grid still says DRAFT.
- **Expect:** A: the row reads APPROVED. B: a red toast — "Only draft sales orders can be approved." (A finished first) or the conflict sentence (both in flight) — never a silent no-op, never a 500. Refresh B: APPROVED once.
### TC-CONC-005 — The last use of a coupon goes to one order

- **Preconditions:** The selling firm described in this section's preparation table: customers, product, price lists and promotions as listed there.
- **Steps**
  1. Settings > Set up > Pricing > Promotions → **Coupons** → `WELCOME10B` → Edit → **Total claims allowed** `1` → Save.
  2. Raise two draft orders for `QA-C01` with **Coupon** `WELCOME10B`, one on each client. Approve both.
- **Expect:** the first approves; the second is refused **by name**: "Coupon WELCOME10B has been used as often as it allows. Re-save the document to price it without." — not silently repriced. A claim counts only at approval, under a lock on the promotion. (`test_the_refusal_is_for_the_race_two_orders_priced_before_either_approved` covers the true race.)
### TC-CONC-006 — Two accruals of one payout period

- **Preconditions:** As *territory-firm*, plus commission rules, targets and three collected sales, as in the preparation table.
- **Steps:** on A and B: Sell > Incentives > Commission → **Payouts** → **Accrue period**, this month on both; **Accrue** on A, then on B.
- **Expect:** A: "2 payout(s) accrued." B: "A commission payout already covers part of that period for this salesman (…)." — a **409** by name, never a 500. The database holds the rule (`UQ_commission_payouts_period_active`); the service supplies the sentence.
---

## The five modules a firm administrator could not open

`FIRM_ADMIN` is built from `_operational_permissions`, a hand-kept list, and
five permission groups had never been added to it: `credit_note`, `proforma`,
`einvoice`, `loyalty` and `tcs`. Each shipped with a module, a screen and a
seeded gate that the role running the firm could not open. Granted in
`20260906_0130`.

**A token carries the claims it was minted with** — a session from before a
grant changes shows the old screens. Fixture accounts are always new, so this
only matters for accounts you already had open.

### TC-GRANT-001 — Credit notes: raise one against an approved invoice

- **Preconditions:** A firm administrator of QA01, and one sale taken to an approved invoice: order, dispatched delivery note, approved invoice. (a sale of yours in QA01: one invoice for 5 **APPROVED**, one **CANCELLED**.)
- **Steps**
  1. Sign in as the prepared **Firm admin** → Sell > **Credit Notes** → **Raise credit note**.
  2. Open the **Invoice** picker and look for the prepared two invoice numbers and its delivery note number.
  3. Pick the approved invoice; open **Line**.
  4. Enter an amount below what the line was charged (it was charged 590.00: 5 × 100 plus 18% GST) → **Raise**.
- **Expect**
  - Step 1: the dialog is titled **Raise a credit note**, its button reads **Raise** — this screen is hand-built, so nothing is called New or Save.
  - Step 2: the **approved** invoice is offered; the **cancelled** one is not, and no `DN-…` number is. Approved sales invoices with lines, and nothing else.
  - Step 3: the line names its product — **Fixture Product qa** — not `Line 1`.
  - Step 4: a draft is listed. **Approve** and **Cancel** are **row actions** on the right, not toolbar buttons; Approve being there *is* the approve gate this case checks. Leave it a draft — approving posts the credit and reverses declared output tax.
### TC-GRANT-002 — Proforma opens

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Sell > Documents > **Proforma**.
- **Expect:** offered, and a real screen — a grid or a proper empty state, never a "coming soon" placeholder. A proforma states what an approved order **will** be charged and **posts nothing**; its number comes from its own `PF` series, not the tax invoice's.
### TC-GRANT-003 — E-Invoice opens, and never says LIVE

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Accounts > Tax filing > **E-Invoice**.
- **Expect:** offered and opens. Wherever a mode is shown it reads **`SANDBOX`**; if it reads LIVE anywhere, stop — that is not cosmetic. `mode` is NOT NULL with no server default on both e-invoice tables, and the sandbox marks every reference it mints `SBX…`. *(QA01 has registered nothing, so the grid may be empty and show no mode at all; that passes.)*
### TC-GRANT-004 — Loyalty: the banner states the scheme, and a firm can change it

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **QA01's scheme is shared by every run.** It starts **off**; switch it back off at the end.
- **Steps**
  1. As the prepared **Firm admin**, Settings > Set up > Pricing > **Loyalty**. Read the banner.
  2. **Scheme settings** → switch **Scheme is running** on; **Minimum to redeem** `50`; **Points expire** off → Save.
  3. Scheme settings → switch **Scheme is running** off → Save.
- **Expect**
  - Step 1: "No scheme is running: nobody is earning anything."
  - Step 2: the dialog saves and the banner re-reads: "1 points per 100, worth 1 each and never expire. At least 50 before any can be spent."
  - Step 3: back to "No scheme is running…".
  - *Until #399 there was no editor at all: the settings route, the code and the grant existed, and the desktop carried only the read.*
### TC-GRANT-005 — Loyalty settings are readable by somebody who cannot change them

- **Preconditions:** A QA01 user hired with the *Sales Manager* job template. (`SALES_MANAGER`, which holds `LOYALTY_VIEW` and not `LOYALTY_MANAGE_SETTINGS`.)
- **Steps**
  1. Sign in as the prepared **Loyalty viewer** → Settings > Set up > Pricing > Loyalty → **Scheme settings**.
  2. **(HTTP)** As them, `PUT /api/v1/loyalty/settings` with the body `GET` returned.
- **Expect**
  - Step 1: it **opens**, read-only, saying "Changing the scheme needs the manage loyalty settings permission." Offered rather than hidden on purpose: whoever is asked why a balance is what it is should reach the rule behind it.
  - Step 2: **403**. Whoever a scheme constrains must not rewrite what it is worth.
### TC-GRANT-006 — TCS settings open, and TCS is off

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps:** as the prepared **Firm admin**, Accounts > Tax filing > **TCS** → **Settings**; save without changing anything.
- **Expect:** offered, opens and saves. **Collect under section 206C(1H)** is off — it defaults false so shipping the feature charged nobody. Leave it off: on, every receipt in QA01 collects TCS, and other cases record receipts there.
### TC-GRANT-007 — The fix was a grant, not a wider gate

- **Preconditions:** A QA01 user hired with the *Field Sales* job template (role SALES_EXECUTIVE only).
- **Steps:** sign in as the prepared **Seller**; open **Sales**, then **Masters**.
- **Expect:** Sales is offered — `SALES_VIEW` is one of their six codes — with **no** Credit Notes, Proforma, E-Invoice or TCS; Masters has **no** Loyalty. Any of the five appearing means a tab lost its own code and its module gate is carrying it alone.
### TC-GRANT-008 — The server grants all five

- **Preconditions:** A firm administrator of QA01 (a user hired with the *Firm Administrator* job template).
- **Steps (HTTP)** — as the prepared firm admin with `X-Firm-ID` QA01: `GET /api/v1/credit-notes`, `/api/v1/proforma-invoices`, `/api/v1/einvoice/registrations`, `/api/v1/loyalty/settings`, `/api/v1/tcs/settings`.
- **Expect:** **200** on all five. They answered 403 before `20260906_0130`. The screens being offered is the desktop honouring the claims; these are the claims being there.
---

## Results summary

| | |
| --- | --- |
| Tester | |
| Date | |
| Installed version | |
| Cases passed / failed / blocked | |
| Worst problem found | |
