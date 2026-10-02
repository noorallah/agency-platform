# Sanity check -- is this installation working?

**About 20 minutes.** Run it after installing or upgrading and before
anything else, or whenever something looks wrong. It has two parts:

1. **The quick check** (5-10 minutes, automatic). One command signs in to
   the running server and opens every list and report of every firm. It
   reports PASS, SLOW, SKIP or FAIL for each.
2. **The screen walk** (about 10 minutes, by hand). Fifteen steps that touch
   one thing in each area of the application, for what a script cannot
   judge: whether the screens open, read right and print.

If either part fails, stop. Send the quick-check page (part 1) or a
screenshot and the step number (part 2) before testing anything further. A
failure here makes the detailed test cases in this folder meaningless.

---

## Part 1 -- the quick check

The quick check only reads: it sends nothing but sign-in and GETs. It is
safe on a firm's live books and can be run as often as wanted.

### Run it

Open **PowerShell** on the machine where the server is installed. The check
also works from another PC on the network: add `--no-stores` and point
`--base-url` at the server.

**An installed copy:**

```powershell
& "C:\Program Files\Agency Platform\backend\agency-server.exe" quick-check --email <your sign-in email>
```

**A developer machine** (from `backend\`):

```powershell
uv run python -m app.cli quick-check --email <your sign-in email>
```

It asks for the password. It then checks every firm that person can open, so
sign in as someone who belongs to the firms you care about. A firm
administrator checks their firm; an `ALL_FIRMS` platform member checks all
of them.

| Option | What it does |
| --- | --- |
| `--firm WHOLE01` | Only this firm. Repeat it for several. |
| `--no-stores` | Skip the migration check. Use it when running away from the server, which cannot see the database. |
| `--base-url http://192.168.1.20:8000` | Check a server on another machine. The default is this machine, port 8000. |
| `--report C:\temp\check.html` | Where the result page goes. The default is `quick-check-<date>-<time>.html` in the current folder. |
| `--timeout 120` | Seconds to wait for one answer. The default is 60. |

### What it checks

| Section | Checks |
| --- | --- |
| Server | The server answers (and which version and environment it is); the database answers |
| Sign-in | The person can sign in |
| Stores | Every store -- the platform, the shared store, every dedicated firm store -- is at the newest database migration |
| Platform | *Who am I*, *My firms*, Firms, Users, Roles |
| One section per firm | Every list and every report the firm's screens open: about 280 routes, read from the application itself, so a new screen is checked from the day it ships. Reports are asked about last month. |

### Reading the result

At the end it prints the totals and every failure, then the path of an
**HTML page** with the full result: failures first, one table per section.

| Status | Meaning | What to do |
| --- | --- | --- |
| **PASS** | Answered, in time | Nothing |
| **SLOW** | Answered, but slower than a person should wait: 1 second for a list, 3 for a report | Note it. It is not a failure, but a list of them is worth sending. |
| **SKIP** | This person may not open it, or the firm has no data the route needs (no customer to show a statement for) | Nothing. Sign in as an administrator to see more of it. |
| **FAIL** | An error; the server's own message is beside it | Stop and send the page |

The command ends with **exit code 1** when anything failed, so it can also
be scheduled and alerted on.

If the server stops answering part-way, the check stops with one failure,
*The server kept answering*, rather than hundreds. Look at the server's log
(`C:\ProgramData\Agency Platform\logs`) and at the machine's free memory.

---

## Part 2 -- the screen walk

Use one firm with some data (on a developer machine, **WHOLE01**). Tick each
step as it passes. Every step names what you should see.

| # | Do | Expect | ✓ |
| --- | --- | --- | --- |
| 1 | Start the desktop app and sign in | Home opens with the firm's name; no error banner | |
| 2 | Switch to another firm with the firm switcher, then back | Each firm's own Home; nothing from the other firm shows | |
| 3 | **Masters > Customers**: open one customer, change its phone number, save | Saved; the list shows the new number | |
| 4 | **Masters > Products**: search for a product | The grid filters as you type; the product's stock shows | |
| 5 | **Sell > Sales Orders**: make an order for that customer, approve it | Approved; stock is reserved | |
| 6 | Dispatch it and invoice it (or **Dispatch and invoice**) | An approved invoice with tax split into CGST/SGST or IGST | |
| 7 | **Print** the invoice | The PDF opens. If the firm e-invoices and the buyer has a GSTIN, the print is refused until the invoice has an IRN; **Print reference copy** prints it marked "not a valid tax invoice" | |
| 8 | **Record Receipt** on the invoice (or **Sell > Receipts**) | The invoice shows paid (or what is still owed) | |
| 9 | **Buy**: a purchase order to a supplier, a goods receipt for it, the bill, approved | Stock rises by what was received; the bill is approved | |
| 10 | **Stock**: look at that product's stock and movements | The receipt and the dispatch both show, with the right quantities | |
| 11 | **Accounts > Tax filing > GST Returns**, GSTR-1 for this month | The invoice from step 6 is in it | |
| 12 | **Accounts > Tax filing > E-Invoice**, then **To register** (if the firm e-invoices) | Documents still without an IRN, with days left; registering one removes it from the list | |
| 13 | **Accounts > Statements > Trial Balance**, and a sales report under **Reports**, for this month | Both open; the trial balance's debits equal its credits | |
| 14 | **Admin > Users**: open your own user | Your roles and firms show | |
| 15 | **Admin > System > Backups** (platform administrator): take a backup | It completes and is listed with its size | |

When all fifteen pass, the installation is working and the detailed cases
in sections 01-14 of this folder can be run.

---

## When it was last run

| Date | Machine | Version | Quick check | Screen walk | By |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
