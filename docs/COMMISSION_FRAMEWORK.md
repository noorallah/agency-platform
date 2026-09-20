# Commission — rules, ladders, scope and payouts

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

## A margin rule needs a cost the invoice remembers, and NULL is not zero

**A margin rule needs a cost the invoice remembers, and NULL is not zero.**
`commission_rules.measure` is VALUE or MARGIN; MARGIN pays on the money less
what the goods cost, which is a different arrangement rather than a
different rate -- a firm selling at a thin markup pays far less on the same
turnover. The cost was always recoverable from `stock_ledger_entries`, which
records the moving average that actually left the warehouse, but reading it
at report time answers about *today's* average, so a payout approved in
March would disagree with the report beside it. It is **snapshotted onto
`sales_invoice_lines.cost_amount`** when the bill is raised, the same reason
a payout is snapshotted at accrual. The column is **nullable and NULL is not
zero**: an invoice raised straight off an order has no dispatch behind it,
so nothing moved and nothing was costed, and zero would say the goods were
free -- which on a margin rule pays commission on the whole sale price. Such
a line contributes nothing rather than being guessed at, and a sale below
cost earns nothing rather than a negative, because clawing it back off other
sales is an arrangement nobody asked for.

## A commission rule has a floor and a target bonus

**A commission rule has a floor and a target bonus, and both are fields on
the rule.** `minimum_amount` earns **nothing at all** below it and pays on
**all** of it above -- deliberately not a zero-percent bottom slab, which
pays from the first rupee once the ladder is climbed and is a different
deal. `bonus_percentage` is an extra percentage on the same value, paid only
when the salesman's targets over the period were met, and added **before**
the cap so a firm's ceiling still holds. A field rather than a second rule
because two live rules over one person's days are refused, and weakening
that guard to allow a bonus rule would reopen the defect it exists to close.
**Targets over a window are judged taken together** (the achievements summed
against the targets summed), because requiring every month makes an annual
bonus unearnable and requiring one makes it unmissable. **Somebody with no
target reports `target_met: null`, not false**, and earns no bonus: nobody
set them a number, so there is nothing they failed. **Margin-based
commission landed on 2026-09-03**: `sales_invoice_lines.cost_amount`
snapshots what the goods cost when the bill was raised, off the stock
ledger's own moving average.

## A commission rule can be about goods, and the report resolves per line

**A commission rule can be about goods, and the report resolves per line.**
`product_id`/`product_category_id` on `commission_rules` make a rule a
statement about lines rather than about the document, resolved in **six
rungs of specificity** -- the person's own product rule, their category
rule, their unscoped rule, then the same three firm-wide. Whose rule it is
outranks what it is about, or a firm-wide rule naming a product would
override a rate somebody negotiated. **An unscoped rule must keep measuring
exactly the document**: the report apportions each invoice's own
`grand_total` across its lines with `apportion` (the bill-discount helper),
so the shares sum to the invoice -- deriving a share from the line's own
`net_amount` instead drifts by whatever the header carries and silently
changes what every existing rule pays, which has a test. On the COLLECTED
basis a scoped rule takes its share of **each receipt** in the same
proportion, because a payment clears a share of every line it settles. An
invoice with no readable lines contributes as a single unscoped line, so
money that exists is still measured by a rule about the document.
`rate_type` PER_UNIT multiplies **quantity** and ignores value and slabs
entirely; it is refused on the COLLECTED basis (money has no cases) and
refused without a product or category (it would add cases of biscuits to
litres of oil). Commission is measured on the document total, which
**includes tax** -- whether that is right is an open question for the owner
and deliberately not changed, because changing it moves every payout.

## One live payout per person per period is held by the database, not by a read

**One live payout per person per period is held by the database, not by a
read.** `_assert_period_is_free` selects and `accrue` inserts with nothing
between them, so two requests that both check before either commits both
pass -- driven on WHOLE01 during the 2026-09-03 review, leaving one salesman
holding two live payouts for one month, which pays the same collections
twice. `UQ_commission_payouts_period_active` is the guard, partial so a
CANCELLED accrual holds no claim; the service check stays for the message it
gives and for *overlapping* periods, which no unique key can express, and the
`IntegrityError` is translated so the loser is refused by name rather than
answered with a 500. Two traps came with it. **A partial index declared with
`postgresql_where` alone is not partial on SQLite** -- the clause is ignored
and `create_all` builds an unconditional unique index, which is stricter than
intended and broke the documented "a cancelled payout frees the period";
declare `sqlite_where` beside it. And **two pending inserts of one key do not
race in PostgreSQL**, the second waits on the first, so a probe that inserts
both before committing either hangs rather than conflicting.

**A period is accrued once it has ended, and a collection belongs to the
day the money met the bill (D-TER-6).** `accrue` accepted a period still
running -- September was accrued on the 19th with `accrued_on` 2026-09-30 --
and because the payout holds the whole period against a second accrual and a
PAID one cannot be cancelled, everything collected from the 20th belonged to
no payout. Now `period_end` must be before today in UTC (`utc_now().date()`,
never the server clock), `accrued_on` may not precede `period_end` nor fall
in the future, and `period_start <= period_end`; any *length* of period is
still allowed, because the overlap key already refuses the same day being
paid twice. The same hole opened backwards: `POST /receipts/{id}/allocate`
adds a later application to the original receipt, and the walk dated it by
`settlement_date`, so an advance of 2026-08-15 applied to a bill of
2026-09-19 was August's collection. `settlement_allocations.allocated_on`
(`20260920_0152`, backfilled from the settlement's date) is the day the money
met the bill -- the settlement's for an allocation made with it, the bill's
for an advance applied since -- and `net_sales.collected_net` reads it, so
the report, the clawback re-read and the target achievement move together.

## A commission payout is snapshotted, and it posts

**A commission payout is snapshotted, and it posts.** `commission_payouts`
goes DRAFT → APPROVED → PAID, or CANCELLED. **The report is read once, at
accrual, and never again** -- it walks live documents, so re-reading it would
answer differently after a settlement is reversed or a rate corrected, and
the journal posted at approval would then disagree with the record beside
it. One live payout per person per overlapping period, or the same
collections are paid twice; a CANCELLED one holds no claim, which is what
makes a period accrued at the wrong rate correctable. Approval posts
`Dr COMMISSION_EXPENSE / Cr COMMISSION_PAYABLE` and payment
`Dr COMMISSION_PAYABLE / Cr` the money account -- two purposes, because an
approved payout is a liability that outlives the month it was earned in.
Both are nominated per firm in `firm_control_accounts`, and the seeded chart
carries `5600` and `2400` (**not** 2200, which is Output Tax). Adjustments
need a reason and only work on a draft. `COMMISSION_PAY` is separate from
`COMMISSION_MANAGE` and **not** granted to `SALES_MANAGER`: whoever states a
debt must not be the one who moves the cash. Two traps found by driving it:
a journal reference is unique, so the accrual, the payment and the reversal
need distinct ones (`...`, `...-PAY`, `...-REV`) or an approved payout can
never be paid; and `JournalEntryEngine._load_accounts` already scopes
accounts to the firm, so a second check in the calling service changes no
outcome and was removed.

**The role split is not enough on its own; the service judges the person
(D-TER-4).** A user holding ACCOUNTANT beside SALES_EXECUTIVE accrued his own
payout, adjusted it by 5,000 with reason "because", approved it and paid it --
five audit rows with his own id as actor -- because `approve` and `pay` looked
at the status and at nothing else. Now nobody approves or pays a payout whose
`salesman_id` is their own; the accruer (`created_by`) cannot approve; and the
payer cannot be the approver. Each refusal is a 403 naming why. The row
carries `approved_by`, `approved_at` and `paid_by` (`20260920_0151`) so the
record and the trail agree, and cancelling clears none of them. The history
seeder signs as three people (`ACTOR`, `PAYOUT_APPROVER`, `PAYOUT_PAYER`)
rather than being let off the rule. A ceiling on a positive adjustment is an
owner decision still outstanding.

## Commission is a ladder, a basis and a ceiling, not one rate

**Commission is a ladder, a basis and a ceiling, not one rate.**
`commission_rules` still holds a flat `percentage`, and a rule with no slabs
still pays it -- but a rule with `commission_rule_slabs` ignores that column
entirely, so never show it beside a ladder. `slab_mode` decides whether the
bands read MARGINAL (each portion at its own rate) or WHOLE_AMOUNT (all of it
at the band reached); they pay very differently on the same numbers, so it is
declared rather than inferred. `basis` is COLLECTED or INVOICED and **a rule
pays on one of them** -- the overlap guard refuses a second live rule over
one person's days whatever its basis, which is what stops a firm changing
over from paying twice for one sale. `max_commission_amount` is applied
**after** the ladder, so it caps what was earned rather than what was sold.
A ladder must start at zero, meet exactly and be open-ended only at the top.
And the governing rule is resolved per row on its own date, then each rule's
subtotal is laddered separately -- pooling a person's whole period would
carry one arrangement's volume into another's thresholds.
