# Jugnix Trade for a distribution business

**One system for a distributor, whatever it sells: buying, stock, selling, collections, accounts and GST.**

This is a short overview for a distribution or wholesale business, with one
line of goods or several. It says what the application does for each kind of
product, what it does for the business as a whole, and what is not in it today.

---

## 1. The problem it solves

Different products need different handling, and many distributors carry more
than one kind under one roof:

| Kind of goods | Examples | What makes it different |
| --- | --- | --- |
| Goods that expire | Medicines, food, cosmetics | Batch and expiry on every pack, shelf life from the manufacturing date, a licence of the buyer where the trade needs one, near-expiry stock to clear first, expired goods back to the supplier |
| Goods kept by batch and pack | Paints, chemicals, hardware | Many pack sizes of one product, a batch number with no expiry, dealer price levels, company schemes |
| Goods with a serial number | Electronics, appliances | A serial number on every unit, warranty, the unit traced from receipt to sale |
| Goods with none of these | General trade items | Quantity and price only |

In Jugnix Trade each line is a **goods type**. A goods type says how its
products are tracked: by batch and expiry, by batch alone, by serial number
and warranty, or not at all. Medicine, Food, Cosmetics, Paint and Electronics
come ready-made as examples, and you add your own for any other line. You
choose the category when you add a product and the rules of its line come
with it; nobody ticks switches product by product, and one firm can carry
several lines.

Most businesses end up with one tool for billing, a spreadsheet for expiry,
another for schemes and a notebook for collections. Jugnix Trade keeps all
of it in one place, and every bill updates the stock, the customer's account
and the books by itself.

---

## 2. What each kind of goods gets

### Goods that expire (for example medicines and food)

- **Batch and expiry on every receipt and every bill.** Stock is held by batch;
  a delivery takes the earliest expiry first, or the batches you choose.
- **Manufacturing date and shelf life.** The expiry is worked out from the
  product's shelf life when only the manufacturing date is printed.
- **Expiry Monitor.** One screen of what has expired and what expires soon,
  with its value, and *Return to supplier now* for what is due back.
- **No sale of goods too close to expiry.** Each product can say how many days
  before expiry it stops being sold.
- **MRP, and price to retailer and to stockist, per batch.** No bill can
  charge more than the MRP.
- **Licence check.** A licence (a drug licence or an FSSAI licence, for
  example) can be recorded for the firm, each customer and each supplier. A
  sale to a shop with no valid licence can be allowed, warned or blocked, as
  you decide; an override asks for a reason and keeps it.
- **Damaged and expired goods** written off with a reason, or sent back to the
  supplier with a return.

### Goods kept by batch and pack (for example paints)

- **Pack sizes and units.** Buy by the carton, sell by the piece; the
  conversion is set once per product.
- **Batch without expiry.** A goods type can track a batch and never ask for
  an expiry date, in the same firm where another product cannot be received
  without one.
- **Pack barcodes.** Scanning a carton's barcode on a bill adds the pieces the
  carton holds.
- **Dealer price levels** (for example Retail, Dealer, Contractor), price lists
  by customer or area, and quantity breaks.
- **Company schemes.** Buy X get Y free, a percentage or amount off, a combo
  price, offers by date and by area, and the company's share of an offer
  claimed back from the principal.

### Goods with a serial number (for example electronics)

- **A serial number for every unit**, typed, pasted or scanned at the receipt.
- **Warranty** dates recorded on the unit.
- **The unit is traced** from receipt to sale, and goes with the goods when
  they move between warehouses.

### Any product

- **Your own extra fields** on a product (shade code, model, strength, pack
  type) without any change to the software, shown only on the goods type they
  belong to.

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
own**: the sales of one line this month, the stock value of another, what is near expiry in a third. Sales
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
switch between them. For a business with several lines of goods there are two
ways to set it up:

| | One firm, several goods types | A separate firm per line |
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
- A link to machines such as a weighing scale or a paint tinting machine.
- Online payment links.
- Van sales, export sales and job work.

---

## 8. What happens next

1. **A demonstration** on sample data shaped like your business: a purchase, a
   sale and a collection in each of your lines of goods, and the reports that
   follow.
2. **Your questions and your list** of what you do today that you did not see.
3. **A trial on your own data**: your products and customers loaded from
   Excel, for you to try for a few days.
