# Offers and discounts chosen on the bill line: design note

**Status: design note for row L6 of `docs/CUSTOMER_BUILD_TASKS.md`, written
2026-10-13. Nothing in it is built.** Row L7 is built from it, after the owner
approves it. Sister notes: `docs/design/LOT_COST_DESIGN.md` (L1) and
`docs/design/BOX_AND_PIECE_LINE_DESIGN.md` (L4); section 5 says how the three
meet. It also builds steps 1 and 4 of backlog 100 (a line names its source).

Words used here. An **offer** is a promotion the firm set up. A **standing
arrangement** is a discount the customer has anyway: his price list's, his
own rate, his group's. A **candidate** is any of these that could act on one
line. The **start** is what the server applies when nobody has chosen. A
**part share** is less than one full round of an offer: 5.5 + 0.5 of 11 + 1.

## 1. What it does for the bill maker

While a line is typed, the side panel lists every offer and every standing
discount that applies to it, with what each gives in rupees or free pieces.
One or more are applied to start with, as the firm's setting says. The bill
maker may tick another or untick one, and the server prices the line again.
An offer the line has nearly earned shows a hint: "2 more to get 1 free". An
offer that allows it can be billed as a part share. The discount box stays
blank throughout: the list is the choice, the box is for a figure a person
types. What was applied, and who chose it, is kept on the line.

### Worked example

One item at 100.00 a piece, GST 12%. For this customer and item the firm has:
price list CITY at 4%; the customer's standing rate of 2%; offer TEA-5, 5% off
a line of 5 pieces or more; offer TEA-11, buy 11 get 1 free, part share
allowed. Both offers combine. The firm's setting is "combine as each offer
allows".

| Step | Typed or chosen | The list shows | Bill line |
| --- | --- | --- | --- |
| 1 | 9 pieces | TEA-5: 45.00 off, **applied**. TEA-11: "2 more to get 1 free", and "part share: 9 pieces as 8.25 charged + 0.75 free". CITY 4% (36.00) and standing rate 2% (18.00): not applied, an offer gives this line its discount | 900.00 less 45.00. Taxable 855.00, GST 102.60, amount 957.60. 9 leave stock |
| 2 | Quantity changed to 11 | TEA-5: 55.00, **applied**. TEA-11: 1 free, **applied** | 1,100.00 less 55.00. Taxable 1,045.00, GST 125.40, amount 1,170.40. 12 leave stock |
| 3 | Unticks TEA-5, ticks CITY | CITY 4%: 44.00, **applied, chosen**. TEA-11: 1 free, applied. TEA-5: not applied, not chosen | Taxable 1,056.00, GST 126.72, amount 1,182.72. 12 leave stock |
| 4 | A new line: the customer takes 6 pieces. Types 6, picks "part share" on TEA-11 | Quantity becomes 5.5, free 0.5 from TEA-11. TEA-5: 27.50, applied | 550.00 less 27.50. Taxable 522.50, GST 62.70, amount 585.20. 6 leave stock |

- **Step 3 is the new thing.** Today an offer always beats the price list
  unless a figure is typed. Here the person picks the price list, the server
  works out the 44.00, and the line records that CITY was chosen, and by whom.
- **Under "best one only"** step 2 starts with TEA-11 alone (1 free piece is
  worth 100.00, against 55.00). With no offer discount on the line, the price
  list's 4% applies beside the free piece, as it does today.
- **Step 4's half piece is the offer's.** It counts against the offer's budget
  and its claim on the principal. Typed by hand today, it names no offer.

## 2. What exists today, and what is missing

### Already there

| Subject | What exists | Where |
| --- | --- | --- |
| One ranking for a line's discount | Typed amount, typed percent, offers, price list, customer's rate, group's rate. The first that answers wins; they never add up. Blank and zero are different answers | `resolve_line_discount` in `backend/app/core/utils/pricing.py` |
| The offer engine | Finds every offer in force, checks coupon, limits, budgets and conditions, applies them in order, and answers a reason for every offer it did not apply. Never commits | `PromotionService.evaluate` in `backend/app/promotions/services/promotion_service.py` |
| The firm's combining setting | `COMBINE` (default) or `BEST_OFFER`, and a cap on what combined offers take off one line | `sales_workflow_settings.promotion_mode`, `max_line_discount_percent` |
| Combining per offer | Each offer says whether it combines (`allow_stacking`). Evaluation stops at the first that does not | `promotions.allow_stacking` |
| Best offer only | Each offer is valued alone, free goods at the line's rate, and one is applied **for the whole document** | `_apply_best`, `_worth_alone` in the engine |
| Limits and budgets | Uses in all and per customer, a money budget, a free-unit budget. Counted from approved claims only; a spent offer is not quoted | `_unavailable`, `budget_rooms`; `redemption_service.py` |
| A claim is made at approval | Pricing stages a pending row; approval claims under a lock and refuses by name | `RedemptionService.claim`; `docs/PRICING_AND_PROMOTIONS.md` |
| A priced preview | One call prices the whole draft through the save path and rolls back: no document, no number, no claim | `POST /api/v1/sales-orders/preview`, `/sales-invoices/preview`, `/quotations/preview` |
| "Try offers" | The engine's full answer, with a reason per offer, for a made-up document. Under Promotions only | `POST /api/v1/promotions/simulate`, `desktop/lib/ui/pricing/promotion_try_dialog.dart` |
| What a line records | The kind of source (`discount_source`: amount, percent, promotion, price_list, customer, customer_group, none, inherited) and the offer that gave free goods (`free_promotion_id`) | `backend/app/sales_order/models/sales_order.py`, the quotation and bill models |
| Downstream inherits | A note takes its order line's price, discount and free goods; a bill takes its note's | `continued_share`, `continued_free_goods` in `pricing.py` |
| Free goods in whole rounds only | Buy 11 get 1 gives nothing to 5.5 and 1 to 19 | `FREE_QUANTITY` in `_apply` |
| A part share typed by hand | 5.5 charged with 0.5 free typed is accepted on order, note and bill where the two together are whole pieces | D-SELL-91 in `docs/DEFECTS.md` |
| The line editors, new UI | The preview is called 350 ms after typing stops. The side panel shows the discount and "from a promotion" or "from the price list", and the free goods an offer gave. The discount box is never filled in | `desktop/lib/ui/sales/sales_order_editor_phase2.dart`, `sales_invoice_editor_phase2.dart`, `desktop/lib/ui/workspace/discount_source.dart` |
| Reports | Discount given by customer, salesman, product and offer; promotion performance and claims | `backend/app/sales_invoice/services/discount_report.py`, `backend/app/promotions/services/report_service.py` |

### Missing

1. **The list on the line.** The preview answers the priced line only. The
   reasons are seen under "Try offers" and nowhere else.
2. **A choice.** The one way to depart from the ranking is to type a figure,
   which counts as a typed discount and names no arrangement.
3. **The name of the source.** A line says "promotion", not which offer or
   list, nor how much each of two combined offers gave (backlog 100, step 1).
4. **A third setting**, "ask", beside combine and best one only.
5. **"Buy N more."** Nothing works out what a line has nearly earned.
6. **A part share the offer itself gives.** The engine gives whole rounds.
7. **Best offer per line.** Today one offer is given per document, so a bill
   of thirty items under twelve item schemes gets one of them.

## 3. The design

### 3.1 The server answers the candidates in the preview it already gives

No new route. The three preview calls gain a list per line, `candidates`, and
one for the whole bill, `bill_candidates`. The preview already runs the save
path and rolls back, so it commits nothing and counts no claim. The engine
already decides every offer for the document in one pass; the list is that
answer kept per line. The document service adds the standing arrangements,
which it already reads for the ranking.

### 3.2 What a candidate carries

| Field | Meaning |
| --- | --- |
| `key` | Minted by the server. An offer's is its `version_group_id`; a price list's its id; `CUSTOMER`; `CUSTOMER_GROUP` |
| `source` | `promotion`, `price_list`, `customer`, `customer_group`: the words `discount_source` already uses |
| `code`, `name` | As they read today: TEA-5, CITY |
| `gives` | The kind (percent, amount, free quantity, free product, buy X get Y, combo), its figures, and one sentence made by the server: "5% off", "11 + 1 free" |
| `worth` | What it takes off this line alone, in rupees; free pieces at the line's own rate. For ordering and for reading, not for the books |
| `applied`, `chosen` | Whether it is in the price shown, and whether a person put it there |
| `combines` | The offer's own `allow_stacking` |
| `available`, `reason` | False with a sentence: "needs a coupon", "claimed as often as it allows", "10.00 left of its budget", "does not combine with TEA-5", "a discount is typed on this line" |
| `needs_more`, `then_gives` | The hint: 2, "1 free" |
| `part_share` | Null, or the charged and free figures for the quantity typed |
| `funded_by` | The principal and its share, on screen only (backlog 102, item 3) |

### 3.3 The choice, and how the server checks it

A line of a sales order or a quotation gains one optional field,
`offer_choice`, with two parts, each optional:

- `discount_from`: `offers`, or the key of one standing arrangement.
- `offers`: the keys of the offers this line takes, discount and free alike.

Left out, the server decides, as today. **The client sends keys, never
amounts.** On every save and every preview the server builds the candidates
afresh and then:

1. refuses a key that is not an available candidate of that line, by name:
   "Line 2: offer TEA-5 does not apply to this line any more. Choose again.";
2. runs the chosen offers through the same engine, in the same order, limited
   to those chosen. One the engine does not reach is refused: "TEA-9 does not
   combine with TEA-5.";
3. works out every figure itself and stores it.

So a chosen offer is always one the server itself would have listed. A
preview is lenient: it reports a stale key and prices the line from the
start, so the screen can drop the key before the save.

**A choice equal to the start is not a choice.** It is stored as the
server's, and the line goes on following the server. A typed price equal to
the ranking's is read the same way today, and it makes an editor that sends
back what it read harmless.

Offers on the whole bill (bill discount, free delivery, a combo across lines,
a gift counted over several lines) are listed under the totals. They can be
refused, through `refused_offers` on the document, and nothing more.

A bill typed straight in is priced by the order raised behind it, so its
lines carry `offer_choice` to that order, as the coupon is carried. A bill or
note that continues documents already priced shows the order's list read-only
and refuses a choice. A quotation turned into an order hands its choices
over, and the order checks them on its own date.

### 3.4 How this sits with the ranking, and with blank and zero

The ranking keeps its order. A choice is one more input, placed where the
arrangements are: **typed amount, typed percent, the chosen arrangement,
offers, price list, customer's rate, group's rate.**

A small helper beside `resolve_line_discount` blanks the tiers not chosen and
the resolver runs unchanged, so the recorded rate is still derived from the
branch taken. **This changes one rule, on purpose.** "A promotion beats the
price list" stays the start; a person may now put a lower tier first for one
line, and only by a recorded choice.

| The discount box | The choice | The line takes |
| --- | --- | --- |
| Blank | None | The start. Today's behaviour, unchanged |
| Blank | Sent | The chosen arrangement |
| A figure, zero included | None | The figure. Zero refuses every arrangement, as today |
| A figure | Sent | Refused: two answers on one line |

The free box is the same: blank takes the free goods of the offers applied,
zero refuses them, a figure stands as typed and names no offer. **No editor
fills the discount box from a choice**; the panel says what blank took.

Unchanged: a line's discount comes from offers **or** one standing
arrangement, never both added (decision 3). Free goods sit beside either. A
line with a typed discount is passed over by every offer.

### 3.5 The firm's combining setting

`sales_workflow_settings.promotion_mode` gains a third value.

| Setting | Applied to start | The bill maker may |
| --- | --- | --- |
| `BEST_OFFER`, best one only | The one offer worth most on the line | Take another one in its place |
| `COMBINE`, as each offer allows (default) | Every offer that combines, in order, under the line cap | Untick any; take a standing arrangement in place of the offers' discount |
| `ASK` (new) | The one offer worth most, as under best one only | Tick more; they combine as each offer allows, under the line cap |

Best one only is judged **per line**, and once more among the offers on the
whole bill (decision 2). Anything beyond the setting is not a choice: it is a
typed discount, which the approver's limit already judges.

### 3.6 The "buy N more" hint

Worked out in the same pass, in memory, for an offer whose other conditions
hold and whose quantity, or next round, the line is short of. Also for the
next break of the customer's price list ("11 more for 6%"). Shown where the
shortfall is no more than the quantity typed, nearest first, two a line at
most. A hint cannot be chosen. **Cost in calls: none**, and no statement per
line: offers and the ladder are already loaded once per document.

### 3.7 A part share, as a switch on each offer

`promotions.allow_part_share`, off by default, on the offer's own form. It
applies to one kind of offer: buy N get M free of the same item.

- With it on, free goods are **in proportion at every quantity**: free =
  charged x M / N. 5.5 gives 0.5; 16.5 gives 1.5. Off: whole rounds, as today.
- The bill maker types what the customer takes away. The candidate answers
  the split: charged = total x N / (N + M) to four places, free = total less
  charged, so the two always add up. 6 is 5.5 + 0.5; 4 is 3.6667 + 0.3333.
  Picking it sets the quantity; the free box stays blank.
- Charged and free together must be whole pieces where the unit is counted
  whole: D-SELL-91's rule, asked by one check on order, note and bill.
- Money is the charged quantity times the rate. Nothing new to round.
- **A part-share line is delivered and billed whole** where the unit is
  whole pieces. Half of 5.5 + 0.5 is no number of pieces.
- The claim, the free-unit budget and the principal's claim take the
  fraction.

### 3.8 Who may choose

One new permission, `SALES_OFFER_CHOOSE`, seeded to every role that makes
sales bills. Without it the list is shown and the start stands; a choice
sent anyway is refused. With it a person may take any candidate the server
lists, giving the customer more or less: each is an arrangement the firm
itself set up, so the approver's discount limit is not asked. Each choice
goes to the audit trail: line, start, what was taken, by whom (decision 4).

### 3.9 Tables and columns

Two new tables of one shape, `sales_order_offers` and
`sales_quotation_offers`: a row for each arrangement applied to, or refused
on, a line or the whole document. The note and the bill read them through
the order line they continue: one record, not two that can disagree.

| Column | Type | Meaning |
| --- | --- | --- |
| `firm_id` | UUID, indexed | The firm |
| `sales_order_id` | UUID, FK CASCADE | The document, for one read per page |
| `sales_order_line_id` | UUID, null, FK CASCADE | The line; null for an offer on the whole bill |
| `sequence` | Integer | Order applied |
| `source` | String(20) | promotion, price_list, customer, customer_group |
| `promotion_id`, `promotion_group_id` | UUID, null; the first FK `promotions.id` RESTRICT | The revision applied and the offer's lasting identity |
| `price_list_id` | UUID, null, FK RESTRICT | The list |
| `code`, `name` | String(50), String(120) | As they read that day |
| `state` | String(20) | `APPLIED` or `REFUSED` |
| `chosen` | Boolean, default false | True where a person decided it |
| `discount_amount` | Numeric(18,4) | What this source took off the line |
| `free_quantity` | Numeric(18,4) | Free stock units it gave |
| `part_share` | Boolean, default false | Given as a part share |

A line's rows are rewritten each time it is priced; nothing refers to them
by id. Its APPLIED rows add up to its discount and its offers' free goods.

Also: `promotions.allow_part_share` (Boolean, default false, carried to each
revision); `offer_choice_made` (Boolean, default false) on the order and
quotation lines; `promotion_mode` takes `ASK` (it is String(20) already).

Repo rules observed. Both tables extend `BaseEntity`, hold no column called
`version`, name each foreign key `FK_<table>_<column>`, carry none to `firms`,
use only types SQLite holds, and join `app/core/database/all_models.py`. The
migration sets `CURRENT_TIMESTAMP` defaults, checks before each
`create_table` and `add_column`, backfills nothing, inserts the permission
(also added to `PERMISSION_GROUPS`), and runs per store through
`scripts/migrate_all_stores.py`. Updates still dump with `exclude_unset`; a
line is that line as sent, so its read carries `offer_choice` to send back.

## 4. Screens (new UI only)

**The line table does not change.** No new column, no pop-up, nothing that
takes the cursor. Typing a line is the same keys as today.

**The side panel** gains one block for the line the cursor is on:

| | Offers and discounts | Gives | |
| --- | --- | --- | --- |
| [x] | TEA-5, 5% off | 55.00 | applied |
| [x] | TEA-11, 11 + 1 free | 1 free | applied |
| [ ] | Price list CITY, 4% | 44.00 | an offer gives the discount |
| [ ] | Standing rate, 2% | 22.00 | an offer gives the discount |
| | TEA-24, 24 + 3 free | | 13 more to get 3 free |

- One key on the line moves the cursor into the list (proposed F6; the build
  confirms it is free). Arrows move, Space ticks, Enter goes back.
- A hint shows under the quantity: "2 more: 1 free".
- The editor holds no rule about what combines: it sends keys, shows answers.
- "Part share" is a button on its row. It sets the quantity to the charged
  figure and shows "0.5 free from TEA-11".
- Without the permission the block is read-only. A saved document's view
  shows, per line, what was applied and "chosen by".

**Calls.**

| Moment | Calls today | Calls with this design |
| --- | --- | --- |
| Typing a line | One preview, 350 ms after typing stops; none per keystroke | The same one. The list rides on it |
| Moving between lines | None | None. Every line's list came with the last preview |
| A tick or an untick | n/a | One preview, on the same 350 ms timer |
| Save | One | One |

A bill of 30 lines makes today's calls plus one per tick. A test holds the
preview's statement count level as lines grow; offer limits, read per offer
today, become one grouped statement.

**Settings.** *Sales Stages* shows the third setting. The offer's form gains
"Allow a part share". Roles show the new permission.

**Prints.** A print states the deal, not the choice.

| Paper | Change |
| --- | --- |
| Full page | The offer's name under the item where an offer gave the line a discount or free goods: "Offer: TEA-11". The Disc. column and "11 + 1 free" as today. A part share prints "5.5 + 0.5 free" |
| Half page, 80 mm roll | No change: Free and Disc. as today |
| Any | Never: candidates not taken, hints, the name of a price list, who chose |

## 5. Effect on existing features

| Feature | Effect |
| --- | --- |
| Limits and running out at approval | Unchanged. A pending row is staged only for offers applied. Approval claims under the lock and refuses by name. Re-saving prices without the spent offer; a choice naming it is reported by the preview and dropped |
| Budgets | Count what the rows say was given. A part share takes its fraction of free units. "Fits whole or not at all" stays |
| Coupons | A coupon offer is a candidate once the code is on the document; before that it reads "needs a coupon" |
| Returns | A return inherits from the bill line, as today. One change: a return of part of a part-share line comes back in the line's own proportion (3 of 6 is 2.75 charged + 0.25 free) where the free figure is left blank. "Charged first" would credit more than was paid |
| Commission on margin | Reads net value and cost off the bill line. A chosen arrangement changes the net like any discount. No change to the rules |
| Loyalty | Points are earned on the bill's value at approval. No change. Bonus-points offers are listed for reading and cannot be chosen |
| Price floor, discount limit | The floor judges the line's net at approval whatever gave the discount. The limit judges typed figures only |
| Principal claims | Unchanged in L7. They can later read each offer's exact amount off the rows in place of today's split in proportion |
| Reports | Discount by offer can go down to the product (backlog 100, step 4). Two new columns in the discount reports: chosen by a person, and offers passed over |
| Lots with their own price (L1) | No conflict. A lot's rate is a **price**; candidates are discounts and free goods worked on quantity times that price. Changing the lot re-prices through the same preview. Free pieces leave from lots like any units. One point for L2: an offer counts each line by itself today, so an item split over two lines by lot would not earn "11 + 1" on 6 and 6. If L2 makes two lines of it, the engine must count the item's lines together |
| Box and piece (L4) | Offers count pieces and give pieces; a pair line carries them on itself, shown as boxes + pieces. A part share makes the piece figure a fraction, so L5's whole-number check on the piece box must judge charged and free pieces together, as D-SELL-91 does. Both builds must call one check |
| Import | An imported order sends no choice and is priced by the start. Bills brought in as history keep the figures in the file as typed and name no offer |
| Old UI | Sends no choice. An order chosen in the new UI and saved again in the old one returns to the start |

## 6. Build steps for L7

Each step is mergeable and testable alone. After every step a firm that
chooses nothing is priced exactly as before. Steps 1 to 7 are server only.

| # | Step | Migration | Proved by |
| --- | --- | --- | --- |
| 1 | The two tables, `allow_part_share`, `offer_choice_made`, the permission, `ASK` accepted by the settings schema. Nothing reads them | **Yes** | Schema registry test; the PostgreSQL insert test; the seeded-permission test |
| 2 | Naming the source: the engine answers what each offer gave each line; the order and the quotation write the rows; reads carry them; the panel says "TEA-5", not "a promotion" | No | Rows add up to the line's discount and free goods; no price moves on seeded data |
| 3 | Candidates in the three previews, with reasons and worth; standing arrangements listed; limits read in one statement | No | The worked example, steps 1 and 2; statement count level as lines grow; nothing left behind after a preview |
| 4 | The hint: offers nearly earned, the price list's next break | No | Step 1 of the example; no hint past the window |
| 5 | The choice on the order and the quotation: the field, the mask, the refusals, the permission, the audit row, "equal to the start is not a choice", `ASK`, best one per line | No | Step 3 of the example; a stale key refused; a second offer refused under best one only |
| 6 | The chain: a bill typed straight in carries the choice to its order and through an edit; a bill of documents refuses one; quotation to order | No | Counter bill tests; claims still made at the bill's approval |
| 7 | Part share: the switch on the offer, the proportion, the whole-pieces check, delivered and billed whole, the return in proportion, budgets in fractions | No | Step 4 of the example to the paisa; 5.5 + 0.5 named and claimed; a return of 3 of 6 |
| 8 | Screens: the block in the order, quotation and bill editors, the key, the hint, the part-share button, the settings and the offer form | No | Widget tests at 800x600; a request-count test (no call per keystroke, none on moving lines); a guard that every key sent is declared |
| 9 | The document view, the full-page print, the report columns and offer by product | No | Print and report tests |
| 10 | Reference docs, user guide, QA cases; driven over HTTP on a fixture firm in all three settings | No | The check file of the round |

## 7. What is deliberately not in this design

- **Adding a standing discount on top of an offer's.** One source a line.
- **Choosing among offers on the whole bill.** They can be refused only.
- **A hint on bill value** ("300.00 more for 2% off the bill").
- **A part share of any other kind of offer**, and **splitting a part-share
  line** over two deliveries or two bills.
- **A choice beyond the firm's setting.** That is a typed discount.
- **The buying side** (backlog 100, steps 2, 3 and 5), **the free quantity
  register** (backlog 99), **passing a supplier's scheme on** (backlog 102).
- **Exact principal claims from the rows**, and **the price a line starts
  at**: price list rate, lot rate and price level keep their ranking.
- **Restating old documents**, and **the old UI.**

## 8. Decisions for the owner

All five were answered by the owner on 2026-10-13, each as recommended.

1. **What is applied to start: today's ranking, or the best for the customer?**
   **ANSWERED: today's ranking: offers first, then price list, then standing
   rate.** No saved or seeded document changes price, and the list shows
   each candidate's worth, so a better one is one tick away.
2. **"Best one only": one offer per line, or one per bill as today?**
   **ANSWERED: per line, with the offers on the whole bill judged among
   themselves.** A firm already on "best one only" will give more schemes
   on a bill of many items than it did; say so in the release notes.
3. **Does the customer's own discount add on top of an offer's discount?**
   **ANSWERED: no. One source a line, as today; free goods sit beside
   either.**
4. **Who may change what is applied?**
   **ANSWERED: anybody holding the new permission, given to every role that
   makes bills; every choice is audited.** A firm takes the permission off
   a role to lock the list. A discount typed by hand is still judged by the
   role's discount limit.
5. **A part share: which offers, and what of pieces?**
   **ANSWERED: only "buy N get M free" of the same item, a switch per
   offer, off by default; charged and free must make whole pieces; such a
   line is delivered and billed whole.**

Two points the sister notes have since settled:

- **A line that takes from two lots stays one line** (the lot note, section
  10), so an offer counts the line's whole quantity and 6 + 6 from two lots
  earns "11 + 1".
- **Boxes and pieces are worked out from the line's one quantity and are
  never stored** (the box-and-piece note, 3.1), so there is no second
  whole-number check to disagree with a part share. The one check judges
  charged plus free pieces together, as D-SELL-91 does; a part-share line
  of 5.5 + 0.5 shows as 0 boxes + 6 pieces, of which 0.5 free.

## 9. Decided here by convention

| Point | Choice | After |
| --- | --- | --- |
| Where the list comes from | The preview already called; no new route | Owner rule: fewer calls |
| What the client sends | Keys only; the server works out every figure | A flag the caller sets is not a control |
| A choice equal to the start | Not a choice | A typed price equal to the ranking's (PG-9) |
| A stale choice | Refused by name on save; reported and dropped in a preview | An agreed price is not changed underneath somebody |
| Where the names are kept | On the document that prices: order and quotation; bills read through | The discount report's existing join; L1's "one record" |
| Part share at any quantity | In proportion, not whole rounds plus a part | Marg's half scheme, from our own knowledge, not confirmed from its help pages |
| Print | Offer's name on the full page only | Our choice: the half page has no room, and the name helps a principal's audit |
