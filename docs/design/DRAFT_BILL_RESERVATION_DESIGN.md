# A draft bill's stock reservation: design note for D-SELL-104

**Status: design note written 2026-10-16. Nothing in it is built.** The owner
picks an option; the fix goes into the next selling round.

## 1. The problem in plain words

With approval off for bills and the order and note stages off, a counter bill
raises its own order behind it. A bill of 500 against a stock of 50 was
refused at approval for stock (right) and stayed a draft (as TC-SELL-100 step
5 says). But the draft kept 500 reserved. The item showed 502 reserved on a
stock of 50, and the next bill's approval was refused "Insufficient available
stock" until the draft was cancelled. One impossible draft blocks every other
sale of that item.

Drafts of a counter bill reserve by design (TC-SELL-091), so that stock a
person has just rung up is not sold from under them. What is wrong is
reserving more than is on hand.

Where it happens: `SalesOrderService._reserve_inventory`
(`backend/app/sales_order/services/sales_order_service.py`) holds the stock an
order promises, called at order approval (about line 1031) and from
`reserve_again` (about line 1476). The inventory side is
`record_sales_order_reservation` in
`backend/app/inventory/services/inventory_service.py`. The counter bill
approves its own order, so the hold is taken before the bill's own stock check
refuses. The check at dispatch ("Insufficient available stock to dispatch")
sits later in the same service. (The exact order of the two steps was not
traced for this note; the build should confirm it.)

## 2. Options

### Option A: refuse the draft for stock

When the draft is saved, compare each line to the stock free to sell and
refuse with the shortage named.

- Cost: one check in the bill create/update path. No migration.
- Risk: it blocks a bill the firm may legitimately want to write ahead of a
  purchase receipt (selling stock that is due in). Firms that sell
  from stock on order would lose that. Could be a firm setting, default warn.

### Option B: reserve only what is free

Hold `min(requested, free)` per line, keep the line's request as it is, and
show the short part on the draft ("held 50 of 500").

- Cost: change `_reserve_inventory` to clamp, and record the held amount. The
  line already carries `reserved_quantity`, so no new column is likely. No
  migration.
- Risk: low to medium. Approval must re-check against the request, not the
  hold, or a part-held bill would pass. Cancelling must release the hold
  exactly (it already does by the held quantity).

### Option C: roll the hold back with the refusal

Keep reserving the full request while the bill is valid, but when approval is
refused for stock, release the hold in the same step, so a refused draft
holds nothing (it is then a plain draft until stock arrives).

- Cost: release call on the refusal path; no migration.
- Risk: medium. A draft that was never approved holds nothing, which departs
  from TC-SELL-091 for exactly the refused case. The refusal path must not
  commit half, which the project's "a chain of committing services" rule
  covers.

### Option D: leave, and have the screen warn

Keep the behaviour; the desktop shows the draft's hold and offers cancel.

- Cost: none in the backend. Risk: the stuck-sale trap stays for every
  client; not recommended.

## 3. What other products do (practice, from general knowledge, not verified)

- **Tally**: a sales voucher does not reserve stock; stock goes negative or
  is refused per a company setting ("allow negative stock"). A sales order
  does not reserve either; it only tracks pending quantity.
- **Zoho Inventory**: a sales order commits stock; if stock is short the
  commit is partial or the order is refused for sale unless negative stock is
  allowed. Drafts do not commit.
- **ERPNext**: a draft invoice reserves nothing; stock is checked at submit.
  Reservation (Stock Reservation Entry) is taken on a submitted sales order,
  and only up to available stock; short quantity stays unreserved.

The common thread is that a draft holds nothing, and a hold never exceeds
what is on hand (Option B's rule).

## 4. Recommendation

**Option B, reserving only what is free,** with approval checking the full
request. It keeps TC-SELL-091 (a counter bill's draft is protected) and fixes
the trap without a migration, and matches the ERPNext behaviour. Pair it with
a plain note on the draft showing the shortfall. Option A can be added later
as a firm setting if owners want a hard stop.

## 5. Points awaiting the owner

1. Should a firm be able to write a bill ahead of stock (Option A would stop
   it), or is a hard stop on the draft acceptable?
2. With Option B, should the draft be allowed to be approved once stock
   arrives, taking the rest of the hold then, or must the person edit it?
3. TC-SELL-100 step 5 and TC-SELL-091 would be updated with the fix; confirm
   that a refused draft showing "held 50 of 500" is the wanted display.
