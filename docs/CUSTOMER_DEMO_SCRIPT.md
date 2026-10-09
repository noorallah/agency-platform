# Customer demonstration script

A 30-minute demonstration for a distributor, whatever they sell. The demo firm
carries three example lines (medicines, food and paints); where the customer
sells something else, say so at the start and name their products as you go:
the steps are the same for any goods. This page
is for the person giving the demonstration, not for the customer; the
customer's copy is the *feature brochure*.

**The rule of the demonstration:** tell one story from start to finish and let
the customer watch the stock, the customer's account and the books change by
themselves. Do not tour the menus.

**If you lose a screen:** press **Ctrl+K** and type its name.

---

## Before the meeting

Do these the day before, not in front of the customer. **The demo firm DEMO01
(Trio Distributors) was built on 2026-10-09 and already covers rows 1 to 5, 7
and 8**; DEMO_FIRMS_USERS_AND_FEATURES.md lists what it holds and the
sign-ins. Row 6 (the offer and the Dealer price level) and the lapsed licence
of row 4 are still to be added.

| # | Prepare | Why |
| --- | --- | --- |
| 1 | A demo firm holding several lines of goods, each its own goods type and category, with four or five products in each. DEMO01 has Medicines, Food and Paints as examples; add a category for the customer's own line if it is none of these | The customer must see their own kind of goods |
| 2 | One line tracked by batch and expiry with a shelf life (medicines and food in DEMO01); one line in several pack sizes tracked by batch with no expiry (paints in DEMO01) | Shows that each line follows its own rules in one firm |
| 3 | Check that a product with no expiry saves and sells in that firm without being asked for an expiry date | Tried on DEMO01 on 2026-10-09 with the paints: stocked, received, sold and billed with a batch and no expiry. Keep each price with GST at or under the MRP, or the bill is refused |
| 4 | One supplier per line, and two customers for each line. Give one customer of a licensed trade a licence that has lapsed (a chemist's drug licence in DEMO01) | Needed for the licence stop in step 6 |
| 5 | Stock already in hand, including two batches that expire within 30 days | So the Expiry Monitor has something to show |
| 6 | One running offer on a product (buy 10 get 1 free) and a Dealer price level | Needed for step 7 |
| 7 | One customer close to their credit limit | Needed for step 8 |
| 8 | Sign-ins for an administrator and a sales executive | Needed for step 12 |
| 9 | Run the whole script once, start to finish, on the machine you will use | A demonstration that has not been rehearsed finds its faults in the meeting |

Show only what has been tested by hand. The purchasing and selling additions of
5 October (walk-in cash sale, rate contracts, supplier schemes, imports, the
GST registers and the rest) are built but have not been through a hand test;
mention them if asked, do not click them.

---

## The script

### Opening (2 minutes)

1. **Sign in.** Point at the customer's own name and logo on the sign-in
   screen: "This is what your staff will see."
2. **Home.** One sentence: "Sales, collections, what is due and what needs
   attention today." Do not explain every card.

### Buying (6 minutes)

3. **Purchase order** to a supplier of dated goods (the pharma supplier in
   DEMO01). Add two lines. Approve it.
   *Say:* "The order is now expected stock. Nothing has moved yet."
4. **Goods receipt** against that order. Type the batch number, the
   manufacturing date and the expiry for each line; record one free unit and
   one damaged unit.
   *Say:* "Stock went up the moment I saved. Free and damaged goods are kept
   apart from what you can sell."
5. **Supplier bill** from the receipt, then open **Stock Summary** and the
   supplier's outstanding.
   *Say:* "One document, and the stock, what you owe and the books all agree."

### Selling (12 minutes)

6. **Dated goods: the licence stop.** Raise a sales order for the customer
   whose licence has lapsed (a chemist in DEMO01) and approve it. The
   application warns or refuses.
   *Say:* "You decide whether this warns or blocks. An override asks for a
   reason, and the reason is kept."
   Then sell to another customer of that line: sales order, delivery note. On the delivery
   note show that the **earliest-expiry batch is picked first**, and that you
   can choose another batch.
7. **Pack sizes, price level and scheme.** Raise a sales order for a dealer
   (a paint dealer in DEMO01): the same product in two pack sizes, ten of one
   item so the
   **buy 10 get 1 free** offer appears. Show that the Dealer price came by
   itself.
   *Say:* "Nobody remembered the scheme. The system gave it, and the bill shows
   what the dealer saved."
8. **Credit limit.** Raise an order for the customer who is close to their
   limit (Fresh Mart in DEMO01). Show the warning.
   *Say:* "It warns from 80 percent. You can make it block instead."
9. **Bill and print.** Turn one delivery into a sales bill. Show the GST on
   each line, then print it.
10. **Receipt.** Record a part payment against that bill. Open the customer's
    **statement**: the bill, the payment and what is left.

### What the owner sees (8 minutes)

11. **Expiry Monitor.** The batches expiring within 30 days,
    with their value, and *Return to supplier now*.
    *Say:* "This one screen is what stops money being thrown away."
12. **Sales Analysis** by goods type and month: every line of goods side by
    side. Click one figure to open the bills behind it.
13. **Customer outstanding** and ageing: who owes what, and for how long.
14. **Profit & Loss and Trial Balance.**
    *Say:* "Nobody entered a journal today. Every figure came from the
    documents you just watched."
15. **GSTR-1.** The bills you raised are already in it.

### Control (2 minutes)

16. **Sign in as the sales executive.** Show that the menu is shorter and that
    the executive cannot approve.
17. **Audit trail** for one document: who did what, and when.

### Close

18. Hand over the brochure. Ask: "What do you do today that you did not see?"
    Write the answers down; do not answer "yes" to anything you have not
    checked.

---

## Questions to expect

| Question | Answer |
| --- | --- |
| My goods are none of your examples. Does it fit? | Yes. A line of goods is set up as a goods type with the tracking it needs: batch, expiry, serial number, or none. The ready-made types are only examples. |
| Can I keep my lines of goods as separate firms? | Yes. One installation holds several firms and staff switch between them. One firm with a goods type per line is simpler when there is one GST number. |
| Can I bring my data from Tally or Excel? | Products, customers, suppliers, opening stock, opening bills and the opening trial balance load from Excel, checked before anything is saved. A file from another program is mapped onto the template. |
| Is my data on the internet? | No. It stays on the server PC in your office. |
| Does it file GST for me? | It prepares the GSTR-1 and GSTR-3B figures and the e-invoice details from the bills. Uploading to the portal is done by hand today. |
| Can my salesmen take orders on a phone? | Not today. Orders are entered in the office from the salesman's call list. |
| Does it send bills on WhatsApp? | A bill can be shared by hand. Automatic messages need your own messaging account and are switched on per firm. |
| Can it work with my machines (a weighing scale, a tinting machine)? | No. Details such as weight, shade or base can be kept on the product as extra fields, but there is no link to a machine. |
| How many users? | Each person has their own sign-in and role. There is no fixed number in the application. |
| What if the server PC fails? | A backup is taken from the application; restore it on another PC. |
