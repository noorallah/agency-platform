# Demo and sample data

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

The commands are in `CLAUDE.md`; this is what the seeders produce and the
class of defect building the history has repeatedly exposed.

## A table that RESTRICTs a reset table blocks the whole reseed

**A table that RESTRICTs a reset table blocks the whole reseed, and the
schema can be asked.** `einvoice_registrations` and `eway_bills` reference
`sales_invoices` with `ondelete="RESTRICT"` and were never added to
`RESET_ORDER`, so a firm that had registered even one invoice could not be
reseeded at all -- it failed partway with a foreign key violation, the
**fourth** table to arrive with a feature and not reach that list after
settlements, `promotion_redemptions` and `promotion_coupons`.
`serial_numbers` is the same shape against `inventories` and was latent
because no demo firm serialises yet. `_assert_nothing_holds_the_history_down`
now asks the metadata the inverse question the existing guard never did --
the old one checked every configured name is a real table, this checks
nothing outside the list holds a table inside it down. **`ondelete="CASCADE"`
needs no entry**: eight referencing tables are correctly absent because the
database removes them itself, which is the distinction that makes the check
precise rather than noisy.

## A beat plan's weekday must be one its route actually works

**A beat plan's weekday must be one its route actually works, and the route
is the authority.** Every store held zero beat plans until 2026-09-04, so
both call-list endpoints answered an empty page for every firm and every
date -- the same "looks unbuilt" shape the territory module had before
2026-08-16. `seed_multi_firm_demo.py` now gives each route one weekly round
per working day, plus a fortnightly and a monthly so all three recurrences
are visible. **The days are read from the store, not from the seeder's own
list**, and `_node` keeps the two in step by **adding** a day the script
means a round to work and the store lacks -- never removing one, since the
service replaces the set and a day somebody added by hand has to survive a
reseed. `WHOLE01-R-N1` had drifted to Monday alone where its siblings work
Monday, Wednesday and Friday, which left that firm two blank weekdays. Three conditions
decide whether a plan calls anybody -- the recurrence hits, the route is in
force, **and** the route works that weekday -- and a seed that satisfies two
of the three reproduces the empty screen with extra rows. Finding it also
turned up the **fourth** instance of a master field added later never
reaching a store already seeded: `_node` returned an existing territory
without checking it had the route profile that makes it a route, so
`WHOLE01-R-S1` was not one and every plan against it was refused. Backfilled
only where missing.

## A master field added later never reaches a store already seeded (third instance)

**A master field added later never reaches a store already seeded --
third instance, and this one billed no tax for two years.** The batch flags
were the first, the HSN code the second, and `tax_profile_group_code` the
third: WHOLE01's toothpaste was seeded before its firm had a tax profile,
kept a NULL, matched no tax rule, and **every sale of it was billed with no
GST at all** -- 37,105 of supplies across two financial years, and nothing
said so until a GST return reported a nil-rated row nobody had asked for.
`seed_multi_firm_demo.py` now backfills it beside the other two, only where
missing. Expect a fourth; the demo's masters are skipped on a re-run by
design, so every new field on one needs a backfill written with it.

## A master field added later never reaches a store already seeded

**A master field added later never reaches a store already seeded.**
`seed_multi_firm_demo.py` skips firms, customers and products that exist, so
the firm's GSTIN, the customers' GSTINs and one product's HSN were all
absent -- and **no invoice could be registered with the tax authority at
all** until each was backfilled. All three are now backfilled *only where
missing* and never overwritten, beside the batch flags which had the same
problem first. Expect this every time a master gains a field the demo needs.

## Demo data has a history

**Demo data has a history.** `scripts/seed_multi_firm_demo.py` seeds the four demo firms and then drives two financial years of trading through the real services, so stock moves, receivables build and the ledger balances the way they would in use; `--no-history` restores the old masters-only behaviour. `scripts/generate_transaction_history.py` does one firm on its own and is what the seeder calls. Both go through the services rather than the tables, which makes them a blunt integration test — building history is what surfaced the accounting-period, receivable-scale and document-numbering defects fixed on 2026-08-10. `scripts/sql/check_backend_data.sql` holds the queries for checking the result by hand; read its header first, because firm-owned tables exist once per store. **The history exercises the pricing rules too, as of 2026-08-23** -- one customer per firm on a standing 7.5% discount, a bill-level discount every fourth month and a free unit every third -- so the apportionment is driven across all three tenancy modes rather than only in SQLite. Before that none of the three pricing features appeared anywhere in the demo. **That claim was mostly false between 2026-09-03 and 2026-09-04**, and the way it became false is the thing to remember: the `CLEARANCE` promotion was seeded with no conditions, so it matched every line of every document -- and a promotion outranks the price list, the standing rate and the customer group. One line of 58 orders reached any tier below promotions, while `price_lists` and `customer_groups` held zero rows in every store, so two tiers `resolve_line_discount` ranks had priced nothing anywhere. **A blanket offer switches off every tier beneath it, and a document priced by the wrong tier still looks discounted**, so nothing reports it -- the seeder now does, in the notes beside the tally, and every tier carries a rate no other tier and no compounded pair of promotions produces so a resolved percentage names the tier that set it. Found by asking every store which columns no live row populates, which is worth re-running whenever a feature lands: the same sweep turned up the null `buyer_id` on every purchase order and zero rows in `promotion_coupons`. **It collects money and names a salesman as of 2026-08-23 too**, and both were bigger holes than they look. Every store had **zero** rows in `territory_salesman_assignments` while every customer sat on a round, and `_validated_salesman` refuses anybody who does not cover the customer's territory -- so naming a salesman was refused on every customer of every firm, `_derived_salesman` had nobody to derive, and no document anywhere carried a `salesman_id`. That is why three separate `select(User)` calls on the tenant session survived for months. And every store had **zero** settlements: two financial years, 49 invoices a firm, and not one rupee collected, so receivables only ever grew, `app/settlements` was exercised by nothing, and commission -- earned on money collected -- could only report zero. The seeder now puts two salespeople per firm on the rounds, collects three invoices in four (one of those in part), and declares a firm-wide rate plus one person on a better one, so the precedence is visible rather than described. **It raises quotations and both kinds of return as of 2026-08-24**, which were the last three document types holding zero rows anywhere -- and each turned up something. Completing a sales return passed a four-decimal document total into a receivable amount capped at two, so it raised a pydantic error rather than posting: `sales_invoice` had hit and fixed that exact bug in a *private* helper its sibling never saw, and `quantize_ledger` in `app/core/utils/money.py` is now the shared one. Completing a purchase return refused any line that did not name a warehouse, where `sales_return` falls back to the header's -- and the header's is mandatory -- so such a return could be raised and approved and then never completed. And an offer cannot be sent, accepted or converted once `valid_until` has passed, judged against today and rightly so, which means a backdated history can only convert quotations inside the current window; the rest are declined or left to lapse, which is the ordinary fate of an offer anyway.

## The demo reaches the five paths nothing had exercised, as of 2026-09-08

**The demo reaches the five paths nothing had exercised, as of 2026-09-08.** `docs/MODULE_STATUS.md` had listed them: 42 of 182 tables held no live row anywhere, and five of those were whole code paths the demo could not reach. Each is now one deliberate choice on one blueprint rather than a setting everywhere, so the ordinary case sits beside the exceptional one. **FOOD01 leaves the delivery note to the service** (`ships_by_hand=False` → `sales_workflow_settings.delivery_note_stage`), so every one of its invoices is billed off the order and `SalesChainService` dispatches the goods -- the one path that moves stock from an invoice, and one that had never run on a store; `generate_transaction_history.sell()` branches on the firm's setting and the two paths share the same deposit, points, collection, return and credit note tail, because the first cut returned early after the invoice and quietly produced a firm with zero returns. **MEDI01 blocks on credit** (`credit_enforcement=BLOCK`, warn 80, block 100) and CityMed Clinic sits on a 20,000 limit the history crosses, so refused approvals appear in the seeder's notes and the refused orders stay unapproved on the grid -- 40,000 was the first figure and refused nothing in two years, because three bills in four are collected and the exposure peaks near 25,000; the other firms get a WARN row rather than none, so `credit_control_settings` is configured everywhere. **ELEC01's mixer grinder is serialised** (`requires_serial=True` → `track_serial`, tracking only, so receipts and issues do not demand the numbers and the history is unaffected) and up to twenty serials with warranty dates are laid onto the inventory record the history left; that needed `SERIAL_NUMBER` and `WARRANTY` on the ELECTRONICS profile, which the feature seed backfills. **Each firm's first product carries a `Case` packaging level** with a barcode, and **each firm has two cost centres, two profit centres and one posted manual journal naming them** -- a manual expense, since the automatic postings name no centre and a seeded account that required one would refuse them. The seeder prints a `once-empty paths` line per firm with the five counts, so a store that seeded without one is visible from the entry point. `lots` still holds nothing.

## The demo seeds the incentives

**The demo seeds the incentives as of 2026-09-03**, and each firm carries
four commission arrangements rather than one: the firm-wide default, one
person's own flat rate, a **product-scoped** rate for that same person, and
a **ladder** with a floor and a target bonus for the other. One target is
met and one missed, and one payout of two is paid. Before this every store
held zero targets and zero payouts, which is the state that has hidden every
defect in this repo worth finding. Three things it taught on the first run.
**`promotion_redemptions` and `promotion_coupons` were missing from
`RESET_ORDER`**, so `--reset` failed outright on any firm whose documents
had claimed an offer. **`seed_multi_firm_demo.py` printed the tally and
threw `tally.skipped` away**, so a firm seeding differently from its
siblings was invisible from the entry point everybody uses -- it prints the
notes now, and the very next run reported two firms seeding a different set
of rules. And **who gets which arrangement is chosen from the rules that
exist, never positionally**: reading the salesmen in id order put the ladder
on somebody who already had a flat rate in two firms of four, the overlap
guard refused it, and those stores seeded with no slabs at all. The scoped
rule names a **product** rather than a category because these firms carry a
single category, where a category rule would cover every line and show
nothing.
