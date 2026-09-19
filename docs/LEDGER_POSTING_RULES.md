# What posts to the ledger, and what it is valued at

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

Eleven modules post through `DocumentPostingService`. Also covers settlements,
receivables, TCS, credit notes, GST returns and e-invoicing.

## A ledger leg facing stock is valued from the movement

**A ledger leg facing stock is valued from the movement; a leg facing a counterparty is valued from the document.** Every forward posting already did this -- receipt, dispatch, both returns, both adjustment paths all read `StockLedgerEntry`. All three *reversals* broke it, and all three were fixed on 2026-08-22: a cancelled goods receipt and a cancelled purchase return credit inventory with what the movement removed and book the gap to `PURCHASE_PRICE_VARIANCE`, and a cancelled sales return's cost entry posts both legs at the movement value so the gap stays in cost of goods sold. Goods arrive at one average and leave at another; mirroring an entry across that gap is what puts a store out.

## Applying money already received posts no journal

**Applying money already received posts no journal, and only part of it
moves the balance.** `settlements.sales_order_id` records which order a
deposit came in against -- a note, not a ring-fence: cancelling the order
does not make the deposit vanish. `POST /api/v1/receipts/{id}/allocate` is
the other half, and it was missing entirely: `ADVANCE_APPLY` had been a
declared receivable type since the settlements module shipped with
**nothing able to reach it**. Two rules. **No journal** -- the receipt
debited cash and credited receivables, the invoice debited receivables; the
allocation only decides which invoice the credit belongs to, and a journal
would count the money twice. And **only the part that became an advance
moves the customer's balance**: a receipt splits when it is recorded,
`min(amount, outstanding)` off the balance and the excess into advance, so
posting `ADVANCE_APPLY` for the whole allocation double-counts. The first
version did, and a deposit taken while the customer already owed something
-- the ordinary case -- was refused outright with "exceeds unapplied
advance". `_advance_part_of` reads the split off the receipt's own
receivable row and subtracts what earlier allocations used, or the last of
an advance is stranded for ever.

## A proforma posts nothing

**A proforma posts nothing, and the absence of anywhere to record that it
did is the design.** `app/proforma` states what an approved sales order will
be charged, for a buyer who needs the figure before the goods move -- a
letter of credit, a payment approval, a customs entry. Neither table carries
a `journal_entry_id` or a `receivable_transaction_id`; adding one is the
first step towards a document that looks like a bill to the books as well as
to the customer, and the unit suite counts journal and receivable rows after
issuing rather than trusting the absence. **Its number comes from its own
`PI` series, never the tax invoice's** -- GSTR-1's DOCS section declares the
invoice series, so a proforma drawn from it would either leave a gap the
return cannot explain or put a number in it that was never a supply. **Its
lines are snapshotted**, not read live: an order can be edited afterwards,
withdrawing its own approval as it goes, and a document somebody is
arranging payment against must not change underneath them. Once ISSUED it
cannot be edited -- a revision is a new document with `supersedes_id`
pointing back -- and withdrawing keeps the row, because the customer holds a
copy.

## A statement's running balance is recomputed in date order, never read off `outstanding_after`

**A statement's running balance is recomputed in date order, never read
off `outstanding_after`.** That column on
`customer_receivable_transactions` is a snapshot taken when the row was
written, in the order things were *recorded*; a statement is read in the
order things were *dated*. Money arriving against last month's bill is
recorded after it and dated before it, so the stored figure shows a balance
that never existed on any day. `CustomerStatementService` sums the opening
balance from the deltas before the period -- the same arithmetic that
produced the current balance -- rather than subtracting the period's
movement from today's, which is right only while nothing is backdated.
**And an ageing row reconciles against the account and says how**: the
bills and the balance are not the same number, because a credit note or a
sales return reduces the account and sits on no invoice while TCS raises it
without being billed. One seeded customer's bills read 27,150.98 against an
account of 21,230.48; `total_outstanding - unapplied_credits +
charges_not_billed` is now the balance exactly, and the buckets always sum
to `total_outstanding`. Two reports about one customer that disagree with
nothing to explain the gap is a bug report waiting to be filed.

## Tax collected at source is charged on the money, not on the bill

**Tax collected at source is charged on the money, not on the bill.**
`app/tcs` implements 206C(1H), and the statute says "at the time of receipt
of such amount" -- so the event that raises it is a **receipt**, never an
invoice being approved, and `SettlementService.create` stages it. Putting it
on the invoice collects on money that may never arrive and misses money that
arrives against an older bill. Five rules follow. **Only the excess counts**
-- the first fifty lakh a buyer pays in the year attracts nothing, so a
receipt straddling the line pays on the part above it; charging the whole
receipt over-collects by the entire remaining headroom. **The running total
is summed from the receipts**, never a counter, net of refunds and excluding
the receipt being charged -- counting that one would make the first receipt
over the threshold pay on itself -- **and only from receipts dated on or
before the one being charged**: summing the whole year charged a back-dated
receipt on money the buyer paid after it (D-CMP-7). **The financial year is the firm's own**,
read off `financial_year_start`, because the threshold resets with it.
**A seller below the turnover threshold collects nothing**, and that
turnover is *stated* rather than derived: the preceding year may predate
this system. And **the tax raises what the buyer owes** (`Dr Accounts
Receivable / Cr TCS Payable`, account **2500** -- not 2200, which is Output
Tax; TCS is filed on a different return on a different cycle). `is_enabled`
defaults false so shipping it charged nobody, and `TCS_MANAGE` is not
granted to `SALES_MANAGER` for the reason the credit policy is not.
The direction check is `SettlementDirection.RECEIPT`, not `"IN"` -- the
first version compared against a string the column never holds, so it
collected nothing anywhere and only the tests said so.

**Section 206C(1H) was omitted by the Finance Act 2025 with effect from
1 April 2025.** A receipt dated on or after that day collects nothing under
it, whatever the settings say, and the preview says why
(`SECTION_206C_1H_OMITTED_FROM` in `app/tcs/services/tcs_service.py`);
receipts dated earlier are charged as the law then stood, and collections
already made are never rewritten (D-CMP-12). The module still answers for
FY 2024-25 and earlier, which is why it stays.

## A return is a view of the documents

**A return is a view of the documents, and a supply is placed by the tax it
was charged.** `app/gst_returns` stores nothing: GSTR-1 and the outward half
of 3B are derived on every read, so a cancelled invoice drops out and a
credit note lands in the month it was *issued*. Three rules, each of them a
defect found by driving it. **The place of supply is read off the tax** --
CGST with SGST is chargeable only within one state, IGST only between two,
so the document settles it, and for an unregistered buyer nothing else can;
the first version read a `state_code` field `customers` does not carry, so
every B2CS row filed a **blank** place, which the portal rejects. Where the
tax says a border was crossed and the buyer is unregistered, the invoice is
named in `unplaced_invoices` rather than filed blank. **A credit note to an
unregistered buyer is netted off its B2CS row**, not filed in CDNR and not
dropped -- dropped, on the belief this system could not produce one, 3B
deducted a credit GSTR-1 never declared and the two returns could not be
reconciled. And **3B is aggregated from the documents, never parsed out of
GSTR-1's own JSON**. `quantize_ledger` is the filing scale: documents carry
four decimals, no portal takes them, and the rounding happens once on the
way out or the HSN summary and the invoice detail drift apart a paisa at a
time. `split_components` in `app/tax/services/gst_buckets.py` is the one
place a component code becomes a bucket, shared with `app/einvoice`, so what
is filed and what was registered cannot disagree.

**A month once due is not rewritten.** Derived on read, a return re-read a
bill's *current* status, so cancelling an August bill in September took it
out of August's GSTR-1 -- a return already due on 11 September -- and no
month showed the reversal (D-CMP-11). Nothing records that a return was
filed, so its due date stands in for it: a bill cancelled **after** the 11th
of the month following its date stays in its own month, and the
cancellation is declared in the month it happened (the date of the
receivable credit the cancellation posted) as a credit for the whole bill --
CDNR for a registered buyer, off B2CS otherwise, and deducted in 3B. One
cancelled before the due date simply drops out, as before.

## A credit note's receivable is rounded the way its journal rounded it

**A credit note's receivable is rounded the way its journal rounded it.**
Third occurrence of the four-decimals-into-a-two-decimal-receivable defect
-- `sales_invoice` hit it and fixed it privately, `sales_return` carried the
identical bug untouched, and `app/credit_note` was the third: approving a
note whose total ran past two decimals raised a pydantic error rather than
posting, so the whole approval failed. Rounding the *sum* is not rounding
the *parts*, so the receivable takes `quantize_ledger(taxable) +
quantize_ledger(tax)` -- what the journal actually credited -- or the two
books sit a paisa apart with nothing to say which is right. Invisible until
a seeded credit note reached it, which is what the demo history is for.

## A sandbox registration must never read as a filing

**A sandbox registration must never read as a filing.** `app/einvoice`
registers invoices and raises e-way bills, and `mode` is NOT NULL on both
tables with **no server default** -- a default is one migration away from
silently being LIVE. The sandbox marks every reference it mints (`SBX...`)
so a number carried away from its row still says what it is, and the desktop
shows the mode beside it everywhere. `portal_for("LIVE")` raises rather than
falling back: a firm that believes it is filing must never be rehearsing.
The payload is refused **locally, naming the field** (no GSTIN, no HSN)
rather than sent to return a numeric code, and the CGST/SGST-versus-IGST
split is read off the two GSTINs' **state codes**, so the document and its
tax cannot disagree. One registration and one bill per invoice by unique
key; a refusal lands on the row and a retry counts the attempt; withdrawal
is inside 24 hours judged in UTC, and afterwards a credit note is the way.
Live filing needs only GSP credentials and one implementation of
`InvoiceRegistrationPortal`.

## A credit note reverses tax on the base the invoice taxed, charges and freight included

**A credit note reverses tax on the base the invoice taxed, charges and
freight included.** `_charged_taxable` returned `gross - discount -
bill_discount`, which was the whole taxable value until #191 moved
`freight_amount` inside it; `charges_amount` had never been there. Since
`SalesInvoiceService._line_net_amount` hands the tax engine
`gross - discounts + charges + freight`, the credit note was working from a
smaller base than the tax it reverses was charged on, and it cost twice: the
cap refused a full credit of what the customer actually paid, and `_tax_rate`
-- tax over that base -- came out inflated, so crediting 1,000 of a 1,050
base reversed 189 of output tax where 180 was collected. Found by the
2026-09-03 review. **Nothing was wrong when it was written**; another
module's arithmetic moved underneath it, which is the thing to check
whenever a taxable base changes -- grep the fields rather than trusting that
a helper still means what its name says.

## A credit note that states its lines reverses tax

**A credit note that states its lines reverses tax; the bare receivable
adjustment does not.** `post_credit_note` posts two legs -- receivable and
sales returns -- because a `customer_receivable_transactions` row carries one
figure and no lines, so it has nothing to say what rate to take off. A firm
correcting a rate after invoicing therefore kept declaring output tax on a
price nobody paid. `app/credit_note` is the document that closes it:
`post_credit_note_document` posts the third leg. It is **not** a sales
return -- a return moves stock and this moves none -- and it always names
the invoice **and the line**, because the rate is derived from what that
line was actually charged rather than read off a tax profile that may since
have been edited. The cap is the line's charged value less what other live
credit notes took; **sales returns are deliberately not netted off**, since
a return may have sourced from a delivery note that cannot be mapped back to
an invoice line. Approving posts *and* moves the customer balance, or
neither. `CREDIT_NOTE_APPROVE` is separate from `CREDIT_NOTE_MANAGE` and not
granted to `SALES_MANAGER`: drafting is bookkeeping, approving reverses a
declared tax.

## `app/settlements` is money in and money out

**`app/settlements` is money in and money out**, and it is one document for both directions: a receipt from a customer and a payment to a vendor differ only in signs. It posts to the general ledger through `DocumentPostingService.post_settlement`, and `settlements.journal_entry_id` is NOT NULL because the defect it exists to close is a settlement that never reached the ledger. ****A customer's opening balance posts** `Dr Accounts Receivable / Cr Opening Balance Equity` as of 2026-08-15, and is refused outright when the firm has no chart of accounts or open period -- a balance nobody can book is one the firm should not be told it has recorded. Revising one or deleting the customer mirrors the entry, traced through `customer_receivable_transactions.journal_entry_id`. `CustomerService.post_receivable_transaction` still moves a customer balance without writing a journal** -- it is the older, lower-level path and the two books drift by every rupee recorded through it, so record money through `/api/v1/receipts` and `/api/v1/payments` instead. What an invoice still owes is derived from `settlement_allocations`, never stored on the invoice. A settlement is reversed rather than edited or deleted: a mirror journal cancels it, the allocations stop clearing invoices but still record what they had cleared, and `CustomerService.reverse_receivable_transaction` puts the customer's balances back by the **deltas stored on the original row** -- never recomputed, because a receipt of 500 against an outstanding 300 splits into 300 of balance and 200 of advance and only that row remembers the split. **A receipt whose advance has since been applied wrote more than one row** -- its own and an `ADVANCE_APPLY` per application -- and the reversal undoes every one of them, the applications first (D-SELL-8, 2026-09-19): taking "the" row picked one at random, so a bounced cheque that had been applied was refused as overtaken or left the customer's balance out of step with 1100.

## `app/finance` and automatic GL posting

`app/finance/` was rewritten on 2026-08-09 and is live at `/api/v1/finance` (migration `20260809_0042`). It uses the seeded `accounting` / `financial_year` permission codes rather than a `FINANCE_*` namespace. The prior `accounting_event_consumer.py`, which guessed accounts by name, was removed — see git history if you want its posting rules.
**Automatic GL posting is built, and this line said for months that it was not.** It claimed the feature needed "a per-firm control-account mapping design" -- which is exactly what `firm_control_accounts` is, and it carries 24 purposes per firm (`ACCOUNTS_RECEIVABLE`, `INVENTORY`, `OUTPUT_TAX`, `PURCHASE_PRICE_VARIANCE`, `LOYALTY_PAYABLE`, `COMMISSION_PAYABLE`, `TCS_PAYABLE` and the rest). **Eleven modules post through `DocumentPostingService`**: `delivery_note`, `sales_invoice`, `sales_return`, `credit_note`, `goods_receipt`, `purchase_invoice`, `purchase_return`, `settlements`, `loyalty`, `tcs` and `commission`. WHOLE01 alone holds 337 journal entries, and `verify_sample_data.py` fails the run if any approved invoice has not posted. A stale line like this is worse than no line: it talks the next reader out of checking, and it survived precisely because nobody re-derived it. Correct one when you find it rather than working around it.
