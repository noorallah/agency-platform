# Demonstration set: firms, sign-ins and features

What is on the demonstration PC after the rebuild of 2026-10-09, who to sign in
as, and what to show. For the person giving the demonstration. The customer's
copy is `CUSTOMER_FEATURE_BROCHURE.md`; the minute-by-minute script is
`CUSTOMER_DEMO_SCRIPT.md`.

Everything here is sample data. The database was emptied and rebuilt on
2026-10-09, so nothing older is left on this PC.

---

## 1. The firms

Seven firms on one server. Between them they show the three ways a firm's
data can be kept.

| Firm | What it is | Where its data is kept |
| --- | --- | --- |
| **DEMO01** Trio Distributors (Demo) | One firm trading in medicines, food and paints. **Use this one for the customer.** | Its own schema (`demo_trio`) in the main database |
| **MEDI01** Medisphere Pharma Distribution | A medicine distributor with three years of trading | Shared schema, with FOOD01 |
| **FOOD01** FreshRoute Food Supply | A food distributor with three years of trading | Shared schema, with MEDI01 |
| **WHOLE01** MarketBridge Wholesale Traders | A general wholesaler with three years of trading | Its own schema (`wholesale_hub`) in the main database |
| **ELEC01** ElectroLink Appliances Distribution | An electronics distributor with three years of trading and serial numbers | Its own database (`agency_electrolink`) on the same server |
| TEST01, TEST02 | Empty firms for the test cases | A schema each |

A firm on a **second server** is supported and is not set up on this PC; it is
to be tried later.

---

## 2. Sign-ins

### DEMO01 (password `DemoTrio@2026pw`)

One person for each job a customer will ask about, added on 2026-10-09. Every
one was signed in once after it was made. What each sees and may do is set by
its role; sign in as two of them in front of the customer to show the menu
change.

| Sign in as | Name | Role | Use it to show |
| --- | --- | --- | --- |
| `admin@demo01.test` | Demo Administrator | Firm administrator | Everything in the firm (the account the demonstration runs on) |
| `owner@demo01.test` | Ramesh Iyer (Owner) | Firm administrator | The owner's own sign-in: Home, reports, approvals |
| `manager@demo01.test` | Sunita Rao (Manager) | Firm manager | Running the firm day to day without the administrator's settings |
| `accounts@demo01.test` | Anita Shah (Accounts) | Accountant | Receipts and payments, the books, GST |
| `salesmanager@demo01.test` | Vikram Nair (Sales Manager) | Sales manager | Approving orders; prices and offers |
| `sales1@demo01.test` | Asha Menon (Sales) | Sales executive | Quotations and orders; cannot approve |
| `sales@demo01.test` | Demo Sales Executive | Sales executive | A second sales person |
| `purchase@demo01.test` | Farid Khan (Purchase) | Purchase executive | Purchase orders, goods receipts, supplier bills |
| `store@demo01.test` | Suresh Babu (Store) | Inventory manager | Stock, transfers, counts, expiry |
| `counter@demo01.test` | Meena Devi (Counter) | Cashier | The counter bill and cash |
| `billing@demo01.test` | Kiran Raj (Billing) | Billing executive | Sales bills |
| `viewer@demo01.test` | Auditor (View only) | Viewer | Looking without changing anything |

The "use it to show" column is what the job is for. Check the menu each one
actually gets on the day: the roles have not been walked through one by one in
this firm.

### The four trading firms (password `DemoAdmin@12345` for all)

| Sign in as | Firm | Role |
| --- | --- | --- |
| `medi01.admin@agency.local` | MEDI01 | Firm administrator |
| `medi01.sales1@agency.local`, `medi01.sales2@agency.local` | MEDI01 | Sales executive (Asha, Bala) |
| `food01.admin@agency.local` | FOOD01 | Firm administrator |
| `food01.sales1@agency.local`, `food01.sales2@agency.local` | FOOD01 | Sales executive |
| `whole01.admin@agency.local` | WHOLE01 | Firm administrator |
| `whole01.sales1@agency.local`, `whole01.sales2@agency.local` | WHOLE01 | Sales executive |
| `elec01.admin@agency.local` | ELEC01 | Firm administrator |
| `elec01.sales1@agency.local`, `elec01.sales2@agency.local` | ELEC01 | Sales executive |
| `master.ops@agency.local` | All four, and platform administration | Platform administrator: creates firms and users, switches between firms |

`platform-admin@agency.local` is the account made when the server was set up.
It must change its password at first sign-in, so do not use it in front of a
customer; use `master.ops@agency.local`.

The four trading firms have an administrator and two sales people each; the
other jobs have a sample user in DEMO01 only. A user for any role
is made in a minute under *Settings > Platform > People > Users*.

---

## 3. What DEMO01 holds

| | |
| --- | --- |
| Goods types in use | Medicine, Food and Paint, one category each |
| Products | 15, five in each line. Medicines and food are tracked by batch and expiry; paints by batch only. Nobody ticked a switch: the goods type did it |
| Paints | Interior Emulsion White in 1 L, 4 L, 10 L and 20 L, and a wall primer |
| Suppliers | Sanjeevani Pharma Distributors, Annapurna Food Products, Rangoli Paints Limited |
| Customers | Two chemists (City Medicals, Lifeline Chemists), two grocers (Sri Lakshmi Stores, Fresh Mart), two paint dealers (Colour World Paints, Sai Hardware and Paints), each with a credit limit |
| Opening stock | Every product, in batches. One medicine batch (Cough Syrup) and one food batch (Glucose Biscuits) expire in 20 days, so the Expiry Monitor has something to show |
| Buying done | One purchase order per supplier, received with batch numbers (and manufacturing and expiry dates for medicines and food), and each billed: three approved supplier bills |
| Selling done | Seven sales orders, each delivered and billed: seven approved sales bills, GST worked out by line |
| Money | One part payment: 100.00 received from City Medicals against its bill, so its statement shows a bill, a payment and a balance |
| Credit limit | **Fresh Mart** owes about 4,590 against a limit of 5,000 (92%): the next order for it shows the credit warning |

**Not yet in DEMO01**, and needed by the script: a *buy 10 get 1 free* offer
on a paint product, a Dealer price level, and a chemist whose drug licence has
lapsed. Until they are added, show offers and price lists in WHOLE01, which
has them from three years of trading.

---

## 4. What the trading firms hold

Each of MEDI01, FOOD01, WHOLE01 and ELEC01 has three financial years of
documents, built by the real application and not typed into tables:

| Document | In each firm (about) |
| --- | --- |
| Purchase orders, goods receipts, supplier bills, purchase returns | 34, 31, 31, 6 |
| Quotations, sales orders | 30, 60 |
| Delivery notes | 60 (FOOD01 50, MEDI01 51: see below) |
| Sales bills, receipts | 50, 38 (MEDI01 41, 31) |
| Sales returns, credit notes | 8, 10 |
| Proformas, advances, loyalty redemptions | 15, 10, 5 or 6 |
| E-invoice registrations (sandbox), e-way bills | 17, 8 |
| Promotions, sales targets, commission payouts | 5, 2, 2 |

Two firms differ on purpose, and each difference is worth showing:

- **MEDI01 blocks on credit.** CityMed Clinic has a credit limit of 20,000 that
  its trading crosses, so nine of its orders were refused and stand unapproved
  on the list. This is the credit block working.
- **FOOD01 bills straight from the order.** It has the delivery note stage
  switched off, so the goods leave when the bill is approved. This is how a
  small firm skips a stage.
- **ELEC01 tracks serial numbers** on its mixer grinder, with warranty dates.

The books of every store were checked after the rebuild (stock value against
the stock account, every period balancing, customer dues against the
receivable account, every receipt carrying its journal): all passed.

---

## 5. Features to show, and where

In the order of the demonstration script. Firm in brackets where DEMO01 does
not have the data yet.

| Show | Where | Firm |
| --- | --- | --- |
| The agency's own name on the sign-in screen and header | Sign-in | any |
| One firm, three lines of goods: each product follows its goods type | Masters > Products; open a medicine and a paint side by side | DEMO01 |
| A paint is received with a batch and no expiry; a medicine cannot be received without one | Buy > Goods Receipts | DEMO01 |
| Purchase order, goods receipt with batch and expiry, supplier bill | Buy | DEMO01 |
| Earliest-expiry batch picked first on a delivery | Sell > Delivery Notes | DEMO01 |
| A bill cannot charge more than the MRP printed on the batch | Sell > Sales Orders (type a higher price) | DEMO01 |
| Expiry Monitor: what expires in 30 days, and its value | Stock > Expiry Monitor | DEMO01 |
| Stock by product, warehouse and batch | Stock > Stock Summary, Batches | DEMO01 |
| Credit limit: warning, or a block | Sell > Sales Orders | MEDI01 (block), others (warning) |
| Offers, price lists, customer discounts | Settings > Set up > Pricing; a sales order | WHOLE01 |
| Sales bill with GST by line, print, receipt, customer statement | Sell | WHOLE01 |
| Sales Analysis by goods type, product, customer, month | Sell > All Sell screens > Insight > Sales Analysis | DEMO01 (goods type), WHOLE01 (history) |
| Customer outstanding and ageing | Sell > Customer Statements | WHOLE01 |
| Profit & Loss, Trial Balance, Balance Sheet | Accounts | WHOLE01 |
| GSTR-1 and GSTR-3B from the bills | Accounts, the GST returns screens (Ctrl+K, type `GSTR`) | WHOLE01 |
| Serial numbers and warranty | Stock > All Stock screens > Tracking > Serial Numbers | ELEC01 |
| A sales executive's shorter menu, and no approval | Sign in as a sales user | any |
| Audit trail: who did what and when | Settings > Platform > System > Audit Logs | any |
| Switching between firms | The firm name at the top, as `master.ops` | all |

**Show only what has been tried by hand.** The purchasing and selling
additions of 5 October (walk-in cash sale, rate contracts, supplier schemes,
imports, the GST registers) and the changes of 6 to 9 October have passed
their automated checks and have not been through a hand test. Mention them if
asked; do not click them in front of a customer until they have been tried.

---

## 6. Before the meeting

1. Start the server and sign in as `admin@demo01.test`.
2. Open Stock Summary and Expiry Monitor in DEMO01 and check they show stock
   and the two batches near expiry. The dates move with today's date: after
   20 days from 2026-10-09 those two batches will have expired.
3. Run the script once, start to finish, on this PC.
