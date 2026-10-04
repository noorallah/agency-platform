# Small firm setup guide

**For a firm of one to three people** -- an owner who buys, sells and keeps
the books himself, perhaps with one helper. It says which settings to change
once, what the day looks like after that, and which switch to turn when the
firm takes on its first storekeeper, salesman or accountant.

Everything here is a setting, not a different product: the same app runs a
distributor with forty people. Nothing is lost by switching stages off -- the
app still raises every document behind the scenes, so stock, GST and the
books stay complete, and the stages can be switched back on at any time.

The full list of settings, with every field, is
`docs/CONFIGURATION_SETTINGS_GUIDE.md`. Agree the tax settings with your CA.

## Contents

1. [Who this is for](#1-who-this-is-for)
2. [Set up once](#2-set-up-once)
3. [People](#3-people)
4. [The day's work in five screens](#4-the-days-work-in-five-screens)
5. [Month end](#5-month-end)
6. [When the firm grows](#6-when-the-firm-grows)
7. [What happens behind the scenes](#7-what-happens-behind-the-scenes)

---

## 1. Who this is for

| You are a small firm if... | Use this guide |
| --- | --- |
| The person who buys is the person who receives the goods | Yes |
| The person who sells is the person who hands the goods over | Yes |
| You do not need a manager to approve orders | Yes |
| You have a separate storekeeper, salesmen on the road, or an accounts clerk | Use `CONFIGURATION_SETTINGS_GUIDE.md` §3 instead (the distributor column) |

---

## 2. Set up once

Sign in as the firm's administrator. Most of these are behind the **gear**
(Settings) at the top right. First finish the firm's **Set up** panel (books
opened, GST template, control accounts, default branch) from the Firms screen
-- `docs/GO_LIVE_GUIDE.md` walks it.

| # | Setting | Where | Set it to | Why |
| --- | --- | --- | --- | --- |
| 1 | **Buying stages** | Settings > Buying > **Purchase Settings** | **Purchase order: off** (Goods receipt goes off with it) | You type only the supplier's bill; the app raises the order and the receipt itself |
| 2 | Default branch / warehouse for buying | Same screen | Your shop and its store | Where goods arrive when the bill raises the receipt |
| 3 | **Sales stages** | Settings > Selling > **Sales Stages** | **Sales order: off**, **Delivery note: off** | You type only the bill; the app raises the order and the delivery note itself, and stock leaves when the bill is approved |
| 4 | Default branch / warehouse for selling | Same screen | Your shop and its store | Where goods ship from |
| 5 | **Rates typed on a bill include GST** | Same screen | **On** | You can type the shelf price; the app works the tax out of it. Each bill can still switch it |
| 6 | Credit Control | Settings > Selling > Credit Control | **Warn** (the default) | You know your customers; a block would stop you at the counter |
| 7 | Price Floor | Settings > Selling > Price Floor | **Warn** (the default) | You are told when a price is below cost, not stopped |
| 8 | Discount Limits | Settings > Selling > Discount Limits | **None** (the default) | Limits are for salesmen, not the owner |
| 9 | Approval Levels, Approval Limits, Purchase Budgets | Settings > Firm / Buying | **None** (the default) | One person does not approve his own work twice |
| 10 | GST Documents: dispatch before invoice | Settings > Tax > GST Documents | **Warn** (the default) | With the delivery-note stage off, the bill ships the goods, so the question does not arise |
| 11 | My Branch and Warehouse | Settings > Firm > My Branch and Warehouse | Your shop and store | Every new document starts with them filled in |
| 12 | Messaging | Settings > Firm > Messaging | **Off**, or WhatsApp invoices only | `docs/MESSAGING_SETUP_GUIDE.md` when you want it |
| 13 | TDS on Purchases (194Q) | Settings > Tax | **Off** unless your turnover passed 10 crore last year | Ask your CA |

**Leave everything else as it comes.** Batch rules, licence checks and the
loyalty scheme matter only if you sell medicines or food, or run a scheme.

---

## 3. People

| Who | Job (template) | What they can do |
| --- | --- | --- |
| You, the owner | **Firm Administrator** | Everything in your firm |
| A helper at the counter (optional) | **Counter Sales** | Make and print bills, take money; cannot see the books or change settings |
| Your CA (optional) | **Accounts**, or **Read Only** | Accounts reads and posts the books and files returns; Read Only only looks |

Add people under **Settings > People > Users > New**, choosing the job; the job sets their access.
`docs/USER_ADMINISTRATION_GUIDE.md` explains jobs and roles.

---

## 4. The day's work in five screens

| When | Screen | What you type | What the app does |
| --- | --- | --- | --- |
| Goods arrive with the supplier's bill | **Buy > Purchase Invoices > New** | Supplier, products, quantities, rates, the supplier's bill number. **Save & approve** | Raises the order and the goods receipt; stock goes in; what you owe and the GST you can claim are posted |
| You sell | **Sell > Sales Invoices > New** | Customer, products, quantities, price. **Save & approve**, Print | Raises the order and the delivery note; stock goes out; what the customer owes and the GST you collect are posted |
| You pay a supplier | **Buy > Money > Payments > New** | Supplier, amount, cash or bank; tick the bills it pays | What you owe goes down; cash or bank goes down |
| A customer pays you | **Sell > Money > Receipts > New** | Customer, amount, cash or bank; tick the bills it settles | What they owe goes down; cash or bank goes up |
| You want to know what you have | **Stock > Inventory** | -- | Quantity on hand and its value, per product |

**Free goods from a supplier** go on the bill line's **Free** quantity (same
product), or as a line of their own with paid 0 and free 1 (a different
product). **Goods going back** to a supplier: **Buy > Purchase Returns > New**.

---

## 5. Month end

| What | Where |
| --- | --- |
| What you owe each supplier | Reports > Financial > **Vendor ageing**; the total is **Accounts > Statements > Trial Balance**, row *Trade Payables* |
| What customers owe you | Reports > Financial > **Customer outstanding** |
| One supplier's or customer's account | Buy > Money > **Supplier Statements**; Sell > Money > **Customer Statements** |
| GST to file | Accounts > Tax filing > **GST Returns** (GSTR-1, GSTR-3B) |
| Check suppliers filed your bills | Accounts > Tax filing > **GSTR-2B Reconciliation** |
| Profit | Accounts > Statements > **Profit & Loss** |

Your CA can do these with the **Accounts** job.

---

## 6. When the firm grows

Each switch affects only documents made **after** it is turned; nothing made
before changes.

| You take on... | Turn on | Give them the job | What changes for you |
| --- | --- | --- | --- |
| A **storekeeper** who receives goods | Settings > Buying > Purchase Settings: **Purchase order on, Goods receipt on** | **Warehouse** | Someone raises the order; the storekeeper records what actually arrived; you bill only what was received |
| A **buyer** | As above | **Purchasing** (and **Purchase Manager** for whoever approves) | Orders need an approver |
| A **salesman** on the road | Settings > Selling > Sales Stages: **Sales order on** | **Field Sales** | He books orders; you approve and bill them |
| A **warehouse that ships** | Sales Stages: **Delivery note on** | **Warehouse** | Goods leave on a delivery note; the bill follows it |
| An **accounts clerk** | -- | **Accounts** | The books and returns move off your desk |
| More than one shop | Masters > **Branches** and **Warehouses** | -- | Each shop is a branch with its own warehouse |

When salesmen join, revisit **Credit Control** (block at 100%), **Discount
Limits** and **Approval Levels** -- `CONFIGURATION_SETTINGS_GUIDE.md` §3 has the
distributor's starting points.

---

## 7. What happens behind the scenes

With the stages off, the app does not skip anything -- it does the typing for
you.

- **Buying:** approving the supplier's bill creates a purchase order and a
  completed goods receipt for exactly what the bill lists, into the default
  warehouse. Stock goes in through the receipt (Dr Inventory / Cr Goods
  received not invoiced) and the bill clears it (Dr Goods received not
  invoiced, Dr Input GST / Cr Trade Payables) -- the same entries a large firm
  makes. You will see these documents in Buy > Purchase Orders and Goods
  Receipts; you never have to open them.
- **Selling:** saving the bill creates the sales order and the delivery note;
  **stock leaves when the bill is approved**, and a draft bill ships nothing.
- **GST:** returns read the bills, so they are complete whichever stages are on.
- **Audit:** every document records who made it -- the documents the app
  raised name you, because they were raised from your bill.

So the day you hire a storekeeper and switch the receipt stage back on, the
books, the stock and the returns carry on without a seam.

---

## See also

- `docs/CONFIGURATION_SETTINGS_GUIDE.md` -- every setting and field
- `docs/GO_LIVE_GUIDE.md` -- opening balances and the first day
- `docs/PURCHASE_TO_PAYMENT_FLOW.md` -- what buying posts, step by step
- `docs/USER_ADMINISTRATION_GUIDE.md` -- people, jobs and roles
