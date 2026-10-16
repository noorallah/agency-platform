# Marking which offers a person chose: design note for D-SELL-101

**Status: design note written 2026-10-16. Nothing in it is built.** The owner
picks an option; the fix is built from the pick. It amends section 3.2 of
`docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`, where `chosen` means "whether
a person put it there".

## 1. The problem in plain words

A bill line records every offer and discount that acted on it, one row each.
A row has a `chosen` flag: true when a person picked it, false when the server
applied it on its own.

When the bill maker names only some of the things that apply, the server still
applies the rest, and it marks all of them chosen. Example, a line of 5.5:

- Choice sent: `{"part_share": <TEA-11>}`. TEA-11 is chosen (right). TEA-5's
  27.50 off, which the server applied by itself, is also stored as chosen.
- Choice sent: `{"discount_from": <CITY>}` alone. TEA-11's free piece is stored
  as chosen the same way.

Prices are right. What is wrong is the record: the saved view says "chosen by a
person" for things nobody chose, and anything that counts chosen rows
overstates it.

The cause is in `_judge` (`backend/app/promotions/services/offer_choice.py`):
when `choice.offers is None`, `named` becomes every promotion row. The cause
cannot be fixed by marking fewer rows alone, because `stored_choices` in the
same file rebuilds a kept choice from the rows marked chosen; no column holds
the choice. Mark only the part share and an edit that keeps the choice would
read back "TEA-11 only", drop TEA-5 and move the price.

So the record must tell an offer **named** from one **left to the server**.

## 2. Options

### Option A: a flag on the row

Add a second column on the offer rows (for example `named`, or make `chosen` a
three-state value: named, left to the server, none). `_judge` sets it from what
the request actually listed. `stored_choices` reads `named` rows only, and
treats `offers is None` as "unnamed" on read-back. `chosen` keeps its meaning.

- Cost: one column on each document's offer-row table (the rows share
  `LineOfferMixin`, so one mixin edit, one migration per store). Backfill:
  rows already chosen stay as they are (their history cannot be recovered);
  new rows are right.
- Risk: low. Migration is needed, per schema, idempotent. Old rows keep the
  overstated flag, which should be said in the QA doc.

### Option B: hold the choice on the line

Store the choice itself (offers named, `discount_from`, `part_share`, and
whether `offers` was absent) on the bill line as one typed record or three
columns. Rows then only say what was applied; `chosen` is derived from the
line's choice.

- Cost: columns on every line table that takes offers (eight or so document
  modules), a migration for each, and `stored_choices` becomes a plain read.
  Largest change; clean afterwards: the choice has one home.
- Risk: medium. More tables touched, more places to forget; a JSON column is
  not acceptable under the project rules, so typed columns.

### Option C: derive it, no storage

Treat a row as chosen only if it is not what the engine would apply with no
choice at all (the "start"). Recompute the start on read.

- Cost: no migration, but every read of a saved bill runs the engine against
  today's offers, which may have changed since. A saved record that changes
  with the master is the failure this project's rules warn against.
- Risk: high. Not recommended.

### Option D: leave it, document it

`chosen` reads "named or applied alongside a named offer". Price is right.

- Cost: nothing. Risk: the figure stays wrong for any report counting choices,
  and the design's own definition stays untrue.

## 3. What other products do (practice, from general knowledge, not verified)

- **Tally**: has no offer picker on the line; a discount is typed or comes
  from a price level, so there is nothing to mark.
- **Zoho Inventory**: applies price lists automatically; a line shows the rate
  and discount, with no record of whether the rate was picked or defaulted.
- **ERPNext**: pricing rules apply automatically and are listed on the document
  in a "pricing rule detail" table; a user can ignore rules with a checkbox
  (`ignore_pricing_rule`). The applied list is separate from the user's act.

None keeps "named" against "left to the server" per offer. This is finer than
the market, so the cost should be small.

## 4. Recommendation

**Option A.** It is the smallest change that makes the record say what the
design says, touches one mixin and one migration, and leaves `stored_choices`
reading from rows as it does now. Option B is the better shape only if the
line is to hold more choice data later (it is not planned).

## 5. Points awaiting the owner

1. Does anything you read count or show "chosen by a person" today (a report,
   the timeline)? If not, Option D is defensible and costs nothing.
2. Option A: accept that bills saved before the fix keep the overstated flag?
3. Should an edit that keeps an unnamed choice stay unnamed (the server may
   then re-pick if an offer expired), or freeze today's pick as named?
