# Agency Platform for a multi-line distributor

**One system for paints, medicines and food: buying, stock, selling, collections, accounts and GST.**

This is a short overview for a distribution business that carries more than one
line of goods. It says what the application does for each line, what it does for
the business as a whole, and what is not in it today.

---

## 1. The problem it solves

A distributor of paints, medicines and food runs three trades under one roof,
and each has its own rules:

| Line | What makes it different |
| --- | --- |
| Medicines | Batch and expiry on every strip, drug licence of the buyer, MRP, price to retailer and price to stockist, expired goods back to the company |
| Food | Batch and expiry, shelf life from the manufacturing date, FSSAI licence, near-expiry stock to clear first |
| Paints | Many pack sizes of one product (1 L, 4 L, 10 L, 20 L), batch for shade matching, dealer price levels, company schemes |

In Agency Platform each line is a **goods type**. A goods type says how its
products are tracked: medicines and food by batch and expiry, paints by batch
alone, electronics by serial number and warranty. You choose the category when
you add a product and the rules of its line come with it; nobody ticks
switches product by product, and one firm can carry all three lines.

Most businesses end up with one tool for billing, a spreadsheet for expiry,
another for schemes and a notebook for collections. Agency Platform keeps all
of it in one place, and every bill updates the stock, the customer's account
and the books by itself.

---

## 2. What each line gets

### Medicines

- **Batch and expiry on every receipt and every bill.** Stock is held by batch;
  a delivery takes the earliest expiry first, or the batches you choose.
- **Expiry Monitor.** One screen of what has expired and what expires soon,
  with its value, and *Return to supplier now* for what is due back.
- **No sale of goods too close to expiry.** Each product can say how many days
  before expiry it stops being sold.
- **MRP, PTR and PTS per batch.** No bill can charge more than the MRP.
- **Drug licence check.** A licence can be recorded for the firm, each customer
  and each supplier. A sale to a shop with no valid licence can be allowed,
  warned or blocked, as you decide; an override asks for a reason and keeps it.

### Food

- **Batch, manufacturing date and expiry**, with the expiry worked out from the
  product's shelf life when only the manufacturing date is printed.
- **FSSAI licence check**, the same way as the drug licence.
- **Expiry Monitor and earliest-expiry-first delivery**, as for medicines.
- **Damaged and expired goods** written off with a reason, or sent back to the
  supplier with a return.

### Paints

- **Pack sizes and units.** Buy by the carton, sell by the tin; the conversion
  is set once per product.
- **Batch without expiry.** The Paint goods type tracks a batch for shade
  matching and never asks for an expiry date, in the same firm where a
  medicine cannot be received without one.
- **Pack barcodes.** Scanning a carton's barcode on a bill adds the tins the
  carton holds.
- **Dealer price levels** (for example Retail, Dealer, Contractor), price lists
  by customer or area, and quantity breaks.
- **Company schemes.** Buy X get Y free, a percentage or amount off, a combo
  price, offers by date and by area, and the company's share of an offer
  claimed back from the principal.
- **Your own extra fields** on a product (shade code, finish, base) without any
  change to the software.

---

## 3. What the whole business gets

### Selling

- Quotation, sales order, delivery, bill, return and receipt, each made from
  the one before so nothing is typed twice. A small firm can skip stages and
  bill directly.
- **Credit limit and payment terms** per customer, with a warning or a block
  when an order goes over.
- **Salesmen, areas and routes.** Territories, routes, beat plans and call
  lists; every order and bill carries its salesman and route.
- **Commission and targets** for salesmen, on sales or on collections.
- **Loyalty points** and coupons where you want them.

### Buying

- Purchase order, goods receipt, supplier bill, return and payment.
- Receipts record batch, expiry, free goods and damaged quantity.
- Supplier outstanding, overdue bills and supplier price trend.

### Stock

- Stock by product, warehouse and batch: available, reserved, damaged, in
  quarantine, incoming and outgoing.
- More than one warehouse or branch, with stock transfers between them.
- Physical count sheets, adjustments with approval limits, repacking and kits.
- Reorder levels and items below them.
- Barcode labels with name, MRP, batch and expiry.

### Money and accounts

- Receipts and payments against bills, with advances and part payments.
- Customer and supplier statements and ageing.
- Journal, ledgers, Trial Balance, Profit & Loss and Balance Sheet, kept up to
  date by the documents themselves. Bank reconciliation.
- Month and year closing with locks.

### GST and tax

- GST worked out on every line, with HSN.
- GSTR-1 and GSTR-3B figures read straight from the bills.
- GST sales and purchase registers, HSN summaries, input credit and GSTR-2B
  matching.
- TDS and TCS registers.
- E-invoice and e-way bill details prepared for upload.

### Reports

More than fifty reports, each with filters and export to Excel: sales by
product, category, customer, salesman, area or month; outstanding and overdue;
stock and expiry; purchase and supplier; promotions; commission; GST.

Because every product carries its goods type, **each line can be read on its
own**: paint sales this month, medicine stock value, food near expiry. Sales
and purchase analysis can be split by goods type, and so can the stock
reports and the product list.

### People and control

- Each person signs in with their own name and a role: administrator, manager,
  accountant, sales manager, sales executive, purchase, stock, cashier, billing
  and viewer. You can add your own roles.
- Every change is recorded with who made it and when, and cannot be altered.
- Approvals for orders, large stock adjustments and commission payouts.

---

## 4. One firm or separate firms

The application can hold several firms in one installation, and a person can
switch between them. For a business with three lines there are two ways to set
it up:

| | One firm, three goods types | A separate firm per line |
| --- | --- | --- |
| Suits | One GST number, one set of books | Separate legal entities or GST numbers |
| Customers and suppliers | One list | A list per firm |
| Accounts | One Profit & Loss; sales and stock read by category | A full set of books per line |
| Staff | One sign-in sees everything they are allowed | Switch firm from the top of the screen |

We recommend **one firm** unless the lines are already separate businesses on
paper.

---

## 5. How it is installed

- **One PC is the server.** It holds the data and runs the server program.
- **Every other PC runs only the app** and connects over the office network.
- **Your data stays on your own machine**, with a backup you control.
- Windows is the supported desktop. Printing covers A4 bills, thermal bills
  and barcode labels.
- Your own name and logo appear on the sign-in screen and at the top of every
  screen.

---

## 6. Bringing your data over

Products, customers, suppliers, opening stock, opening bills and the opening
trial balance are each loaded from an Excel file. The application gives you a
template, checks the file and names every problem by row and column before
anything is saved. A file exported from another program can be mapped onto the
template rather than retyped.

---

## 7. Not included today

So that nothing is promised that is not there:

- A direct connection to the e-invoice and e-way bill portals. The details are
  prepared in the application and uploaded by hand.
- Automatic WhatsApp or SMS of bills and reminders. Sharing by hand is there;
  automatic messages need the firm's own messaging account.
- A phone app for salesmen to take orders in the field.
- A link to a paint tinting machine or a shade-formula library.
- Online payment links.
- Van sales, export sales and job work.

---

## 8. What happens next

1. **A demonstration** on sample data shaped like your business: a purchase, a
   sale and a collection in each of the three lines, and the reports that
   follow.
2. **Your questions and your list** of what you do today that you did not see.
3. **A trial on your own data**: your products and customers loaded from
   Excel, for you to try for a few days.
