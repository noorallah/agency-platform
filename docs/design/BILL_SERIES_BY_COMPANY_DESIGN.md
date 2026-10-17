# A bill series per company: design note

**Status: design note for backlog 157 (PRT-7), written 2026-10-16; section 12
decided by the owner the same day. The server half is built (2026-10-17):
migration `20261017_0395`, `app/document_framework/services/bill_series.py`,
the settings routes, `series-preview` and the principal's prefix. The desktop
half is not.** Section 12 records what the owner settled.

As built, two points the note left open: the bill is numbered when it is
saved, as every sales bill already was, so a draft keeps the series its lines
gave it when first saved; and GENERAL issues the higher of its own counter
and the sales-bill rule's, keeping the rule's counter in step, so a firm's
configured starting number and its preview still hold.

## 1. What it does for the user

Today every sales bill takes the firm's one series: GENERAL and a running
number. That stays the default.

A firm may switch on **a series per company**. A company is the principal
whose goods are on the bill (Asian Paints, Pidilite). Each company is given a
short prefix, for example ASIAN or PIDI. A bill of Asian Paints goods then
prints ASIAN-26-27-0001 instead of GENERAL-26-27-0001. The principal's bills
and claims line up.

Rules the customer and the owner gave on 2026-10-16:

- Every series restarts each financial year.
- A bill whose lines are all one company, with a prefix, takes that series.
- A bill mixing companies takes GENERAL. It is never refused.
- A company with no prefix of its own takes GENERAL.
- Two companies may be given the same prefix. They then share one running
  number. A number is never issued twice.
- Only *one series* and *by company* are built now. Brand, goods type and
  product come later without reshaping anything.

## 2. What is there today

Read on 2026-10-16 at main `5328eeb7`.

- `DocumentNumberingRule` (`document_numbering_rules`) holds a firm's series
  for one document type: `prefix`, `separator`, `include_financial_year`,
  `short_financial_year`, `auto_reset`, `sequence_padding`, `is_default`,
  `is_active`. Its unique key is firm, document type and `code`.
- `DocumentNumberSequence` (`document_number_sequences`) holds the counter.
  It is keyed on **rule id and a scope signature** (financial year, branch,
  company code). So today a counter belongs to a rule, not to a prefix.
- `reserve_number` in `document_framework_service.py` loads the rule
  `with_for_update`, finds or creates the counter, builds the number and
  adds one. `_sequence_for` also revives a retired counter, so a series never
  goes back behind a number it has issued (D-CFG-7).
- `include_company_code` and `company_code` already exist on the rule and on
  `reserve_number`. They print a code in the number and widen the scope
  signature. The caller fills them, and nothing ties them to a principal.
  This design does not use them (section 4).
- `gst_numbering.py` holds `GST_NUMBER_LIMIT = 16`, the six types that carry a
  GST serial (`SALES_INVOICE`, `CREDIT_NOTE`, `SALES_RETURN`,
  `CUSTOMER_DEBIT_NOTE`, `DELIVERY_NOTE`, `RCM_SELF_INVOICE`),
  `gst_number_problem` and `short_year`.
- `principals` (`app/products/models/brand.py`) holds `code`, `name`,
  `vendor_id`, `is_active`, unique on firm and `code` among live rows.
  `brands.principal_id` is a nullable key to it. So a product's company is
  its brand's principal, and may be empty. (The backlog says a company is
  always known; the column allows none, so a bill line can have no company.
  Section 6 covers that.)
- A proforma is not a GST document (it is not in `GST_NUMBERED_TYPES`). Its
  number comes from its own series, never the tax invoice's: `ProformaService`
  (`app/proforma/services/proforma_service.py`) declares the
  `PROFORMA_INVOICE` type with a rule of its own (D-SELL-17).

## 3. The firm setting

One setting on the firm, in the bill numbering settings:

| Column | Meaning |
| --- | --- |
| `series_driver` | text, not null, default `ONE_SERIES`. Values now: `ONE_SERIES`, `BY_COMPANY`. Later: `BY_BRAND`, `BY_GOODS_TYPE`, `BY_PRODUCT` |

It is a text column with a list of allowed values, not a yes-or-no switch.
That is what lets a later level be added by adding a value and a prefix
column on that level's master. No table is reshaped.

The setting is per firm and applies to the sales bill (`SALES_INVOICE`)
only. It lives in a new small table `bill_series_settings`, one row per firm,
in every firm store. The firm's other behaviour switches
(`sales_workflow_settings`, `credit_control_settings`) are tables of their
own. A firm with no row reads as `ONE_SERIES`.

Changing the setting needs the permission that guards the numbering rules
today. A firm administrator holds it. Changing it mid-year is safe (section
5 says why).

## 4. The prefix on the principal

New column on `principals`:

| Column | Type | Meaning |
| --- | --- | --- |
| `bill_series_prefix` | string(10), null | the word the company's bills start with. Letters and digits only |

- It is **not unique.** Two companies may share a prefix (section 5).
- Blank means "this company has no series of its own": its bills take
  GENERAL.
- Stored upper case. Letters and digits only, so it can never carry a
  character GST refuses.
- It is read **only when the firm setting is `BY_COMPANY`**. A prefix typed
  while the firm is on one series is kept and does nothing until the setting
  is switched. The screen says so in its helper text.

Why a new column and not `include_company_code`: that flag prints a code
inside a series the rule already owns, and the counter is still the rule's.
The customer wants a different series word per company, with a counter that
follows the prefix. That needs the prefix on the company and the counter
keyed on the prefix.

GENERAL is the firm's existing sales-bill rule, its default. Nothing about it
changes.

## 5. One counter per prefix and year

This is the part the owner asked to be exact about.

**The problem.** The counter today belongs to a rule. If each company had its
own rule, two companies with the same prefix would each count from 1 and
issue ASIAN-26-27-0001 twice. GST wants the number unique in the year.

**The shape.** The counter is keyed on **firm, prefix and financial year**,
not on company or rule. New table `bill_series_counters`:

| Column | Type | Meaning |
| --- | --- | --- |
| `firm_id` | UUID, not null, no key | the firm |
| `prefix` | string(10), not null | `GENERAL`, `ASIAN`, ... as printed, upper case |
| `financial_year` | string(20), not null | the full label, `2026-2027`, as the counter is keyed today |
| `next_sequence` | integer, not null, default 1 | the number the next bill takes |

Plus the `BaseEntity` columns. A unique key on `(firm_id, prefix,
financial_year)` that is **not** partial, so a retired row can be revived and
never duplicated, which is the lesson of D-CFG-7.

**How it is locked.** To issue a number the service reads the row with
`with_for_update`, uses `next_sequence`, adds one, and flushes, all inside the
bill's own transaction. Two bills racing for the same prefix and year queue on
that one row. The second reads the number after the first. If the row does not
exist yet, it is inserted; the unique key makes a second inserter fail, and it
retries by reading the row. A lock on the counter row is the right tool: this
guards a sum (the next number), and optimistic `version` cannot guard that
(`CLAUDE.md`).

**GENERAL.** GENERAL is a prefix like any other. A firm already running
carries on from the number it has reached (section 10).

**Restart each year.** The year is part of the key. A new financial year finds
no row and starts at 1. A bill back-dated into last year finds last year's row
and carries on there, as the rule counters do today.

**Switching the setting on or off.** The counter is per prefix, so GENERAL
keeps counting where it was whichever way the setting goes. Nothing is reset
and no number is reused.

**How it joins the existing code.** `reserve_number` keeps doing the number
layout (separator, year, padding) and the rule checks (active, type switched
on). For a sales bill it asks the new counter for the next number under
`(firm, prefix, year)` instead of reading the rule's own counter. Every other
document type keeps the rule counter, untouched.

## 6. Which series a bill takes

At save, the bill resolves its series from its lines, once, on the server.

1. Setting is `ONE_SERIES`: GENERAL. Done.
2. Setting is `BY_COMPANY`: for each goods line, take the product's brand, its
   principal, and that principal's prefix.
3. If every line gives the **same** prefix, the bill takes it.
4. Otherwise (two different prefixes, or any goods line with no company or no
   prefix) the bill takes GENERAL.

Two companies that share a prefix give the same prefix, so a bill of both
takes that shared series. That is right: it is one series by the owner's
rule.

Lines that carry no goods, such as freight, are not counted. A goods line
with no company makes the bill a mixed bill, and it takes GENERAL.

A bill raised from several delivery notes is decided by the lines of the bill
as saved. The series is fixed when the number is issued.

**Does the number change on edit?** A bill is numbered when it leaves draft,
as today. An issued bill keeps its number. A draft changes its series as its
lines change.

**Choosing by hand.** Proposed: not allowed. The person cannot pick GENERAL
for a one-company bill. The series follows the lines, so the books stay
predictable. This is the owner's open point 1 (section 12).

## 7. The bill shows the company

On the bill form, each line shows a small *Company* column with the
principal's name. Above the lines, a line of text says which series the bill
will take: *This bill will be numbered ASIAN-...* or *Mixed companies: this
bill will be numbered GENERAL-...*. It updates as lines change. It comes from
one server call that returns the series for the lines (a new
`series-preview` route on the sales invoice), not from the client. That is
the same rule as pricing: the server decides, the screen shows.

The printed bill shows the number as usual. No print layout change is in
scope.

As built (part 2B-2): the invoice response carries `series_company_name`, and
the invoice list has a *Company* column that is hidden by default.

## 8. The 16-character limit

CGST rule 46(b): at most sixteen characters, letters, digits, `-` and `/`.
The number is prefix, separator, year, separator, padded number.

With the short year (`26-27`, five characters), a separator each side, and a
four-digit number, `ASIAN-26-27-0001` is exactly 16. So a five-letter prefix
with four digits just fits, and nothing longer does.

Rules:

- The limit is checked **when the prefix is saved**, not when a bill is
  issued. The check builds the longest number the series could print (prefix,
  year as the rule prints it, the rule's padding filled with nines) and runs
  it through `gst_number_problem`. A prefix that cannot fit is refused with
  the sentence that function already gives, naming the number.
- The same check runs when a rule's padding, separator or year setting is
  changed, against every prefix in use.
- The longest prefix is therefore worked out from the rule, not fixed. The
  column is 10 characters so a looser layout is allowed, but the check
  decides.
- A number that grows past the padding (the 10,000th bill when the padding is
  four) would print longer. The check at issue time stays as it is today and
  refuses it by name.
- The screen tells the firm the figure it works out, for example *With the
  short year, a prefix of up to five letters fits.* The figure is computed
  from the rule, not written into the text.

## 9. Returns, credit notes and proformas

- **Sales return, credit note, customer debit note.** These are GST numbered
  documents with their own types and rules. They keep their own series and
  counters. They do not take a company series in this build. The customer
  asked only for bills. If the owner wants a return to follow the company
  later, the same resolver serves it, because the return's lines name their
  products.
- **Proforma.** Not a GST document, and already numbered from its own series
  (`ProformaService`, D-SELL-17). It does not take a company series, and it
  can never use up a bill's number.
- **Quotations, orders, delivery notes.** Unchanged.
- **Cancelled bills.** A cancelled bill keeps its number. The number is not
  given back, so the series has a gap that is explained, not a repeat.

## 10. Migrating what exists

- The firm's existing sales-bill numbering rule **stays**, and is what GENERAL
  means. Its prefix is what GENERAL prints. No rule is edited or deleted.
- Each firm reads as `ONE_SERIES` until it switches. Behaviour is the same as
  today.
- For every firm, a `bill_series_counters` row is created for GENERAL and each
  existing financial year, with `next_sequence` taken from the rule's live
  counter for that year. This step matters: if GENERAL started at 1, the next
  bill would repeat a number already issued. The migration copies the higher
  of the rule's counter and the highest number found on issued bills with
  that prefix and year.
- Principals get `bill_series_prefix` as null. Nobody has a company series
  until the firm gives one.
- The migration follows the repo's rules: guarded and idempotent (check before
  `create_table` and `add_column`), explicit
  `server_default=sa.text("CURRENT_TIMESTAMP")` on the timestamps, no
  cross-schema foreign keys, and the backfill touches only rows not yet
  copied. It runs through `migrate_all_stores`.
- The sample-data reset order is checked for the two new tables. Both are leaf
  tables, so no entry is expected, but the check is run.

## 11. Tables and columns, and the tests

**Design only. What a build would touch:**

| Where | Change |
| --- | --- |
| `bill_series_settings` (new) | `firm_id`, `series_driver` |
| `bill_series_counters` (new) | `firm_id`, `prefix`, `financial_year`, `next_sequence`; unique on the first three |
| `principals` | add `bill_series_prefix` |
| `document_framework_service.py` | sales-bill numbering reads the new counter |
| new service | resolve the series from the lines; issue the next number under the lock |
| `sales_invoices` | store `series_prefix` as issued, so a report can group by series without parsing the number (open point 8) |
| routes | settings read and write; `series-preview`; the principal screens carry the prefix |
| permission | no new code expected; the seeded numbering code is reused, confirmed in the build with the grep the repo asks for |
| one migration | the tables, the column, the backfill of section 10 |

Tests that would guard it (names are proposals):

1. **Never twice.** Two companies sharing the prefix ASIAN, bills raised
   alternately: numbers are 0001, 0002, 0003 with no repeat.
2. **Race.** Two sessions issuing under the same prefix and year at once, as an
   integration test on PostgreSQL, since SQLite cannot show a lock: no
   duplicate and no failed bill.
3. **Resolver.** One company with a prefix gives that prefix; two companies
   give GENERAL; one goods line with no company gives GENERAL; one company
   with no prefix gives GENERAL; a freight line is ignored; `ONE_SERIES` gives
   GENERAL whatever the principals hold.
4. **Restart.** A bill in a new financial year starts at 1; a back-dated bill
   carries on in last year's counter.
5. **Limit.** A prefix that cannot fit is refused at save; one that fits is
   accepted; changing the rule's padding is refused if it pushes a prefix
   over.
6. **Switching.** On, off and on again does not reset or reuse a number.
7. **Migration.** After the migration the next GENERAL bill follows the last
   issued number, including where the rule counter was behind the bills. The
   existing guard that every deployed table accepts an insert covers the
   timestamps.
8. **Other documents.** A sales return, a credit note and a proforma are
   numbered as before.
9. **Preview.** The series text from `series-preview` matches the number the
   saved bill gets.
10. **Later levels.** A test adds a fake extra driver through the resolver's
    table of drivers, to prove a new level is an entry in a table and not a
    rewrite.

## 12. Points for the owner -- Decided 2026-10-16: all eight accepted as proposed

1. May a person choose GENERAL by hand for a bill of one company? Proposed:
   no, the series follows the lines.
2. The setting: `ONE_SERIES` or `BY_COMPANY` in the bill numbering settings,
   with brand, goods type and product added later as further values, each
   master carrying its own prefix. Confirm the shape.
3. A line with no company: proposed that freight and other non-goods lines are
   ignored, and a goods line with no company makes the bill GENERAL. Confirm.
4. Prefix length is worked out from the rule so the number fits 16 characters
   (five letters with the short year and four digits). A firm wanting a
   longer prefix must shorten the padding or the year. Is that acceptable?
5. Should returns and credit notes follow the company of the bill they
   reverse? Proposed: not in this build; own series as today.
6. May a firm switch the setting in mid-year freely? Proposed: yes, since
   counters are per prefix and nothing is reset.
7. Should a prefix be unique? Proposed: no, because the owner allowed two
   companies to share one, and they then share a running number.
8. Should the bill store the series it took (`series_prefix`)? It costs one
   column and makes reports by series simple.

## 13. What other programs do

Stated from general knowledge, not checked against any current manual.

- **Tally.** A voucher type can have **voucher classes**, each with its own
  numbering and prefix that restarts each year. A firm makes one sales class
  per principal, and the person picks the class when entering the voucher. It
  is a choice by the person, not derived from the stock items.
- **Busy.** A sales voucher has **series** set up in the firm's masters. Each
  has its own prefix and numbering, and the person picks the series on the
  voucher. Again chosen by hand, not derived from the goods.
- **ERPNext.** Documents carry a **naming series** such as `SINV-.YY.-.####`.
  Several series can be set per document type, and a user picks one on the
  document; a default can be set. The counter is kept per series pattern, so
  two series with the same pattern share a counter. That is the same idea as
  the counter per prefix here.

All three leave the choice to the person. What is new here is that the series
follows the goods, so no one has to choose, and a mixed bill falls back to
GENERAL. That is why section 6 proposes no manual override.

## 14. How a firm switches it on

1. Give each company its prefix: open the principal (company) and fill *Bill
   series prefix* (letters and digits, saved in capitals, at most the length
   Settings shows). A company left blank takes GENERAL.
2. Open Settings > Firm > Bill series and choose *By company* instead of *One
   series*. Switching back and forth is safe: counters are per prefix and
   year, so nothing is reset or reused.
3. On the sales bill, the line above the lines says which series the bill will
   take, for example *ASIAN-26-27-0004*, or *GENERAL* when the companies are
   mixed or one has no prefix. Freight and service lines are not counted.
4. The saved bill carries the number of that series, its company name shows in
   the invoice list's hidden-by-default *Company* column, and a sales return
   keeps its own series. The drive that proves this is
   `backend/scripts/drive_bill_series.py`; its cases and results are in
   `docs/qa/BILL_SERIES_BY_COMPANY_CASES.md`.
5. A new firm pads bill numbers to six digits, which leaves room for a
   three-letter prefix only. Settings shows the length that fits; shorten the
   padding on the sales bill series to make room for a longer one (four digits
   fit five letters with the short year).

## 15. More digits, no year printed -- Decided 2026-10-17 (owner)

**The problem.** The default of six digits fits a three-letter prefix only,
and the firm expects far more bills over the years. CGST rule 46(b) caps an
invoice number at 16 characters, so the room has to be found inside that.

**Options weighed.**

| Layout | Example | Chars | Verdict |
| --- | --- | --- | --- |
| Short year `26-27`, 6 digits | `ASIAN-26-27-000001` | 18 | does not fit |
| Year as `2627`, no separators | `ASIAN2627000001` | 15 | fits, but hard to read |
| Two-digit start year, 7 digits | `ASIAN/26/0000001` | 16 | fits exactly |
| **No year, 8 digits** | `ASIAN/00000001` | 14 | **default for new firms** |
| Letters in the counter | `ASIAN/00000A1` | 14 | rejected |

**Letters in the counter** give more numbers per character, but staff, auditors
and the GST return read a bill number as a consecutive serial. Letters break
sorting and the gap check (a missing number is how a deleted bill is found).
The owner chose digits: *"increase the invoice number to more digits"*.

**Decision.**

1. A new firm's sales bill series prints **no year**: prefix, `/`, **8 digits**
   (`ASIAN/00000001`, 14 characters). Up to 10 digits fit behind a five-letter
   prefix.
2. The year in the number is a choice on the numbering rule: *none* (default
   for new firms), *two-digit start year* (`ASIAN/26/0000001`) or *short*
   (`26-27`, as today). Existing firms keep their layout until their
   administrator changes it.
3. **With no year printed the counter never resets.** A yearly reset would
   print `ASIAN/00000001` again every April: two bills with one number in the
   books, in search and in the old-bill import. So *none* forces auto-reset
   off and keys the counter per prefix only. The other two choices keep the
   counter keyed on the full year label, so it resets each year as now. This
   also matches the customer's old program (series name plus a running
   number, `docs/SWATHI_IMPORT_PLAN.md`).
4. **A new prefix is the way past a series' limit.** Changing a company's
   prefix after bills exist is allowed (admin only, audited). The new prefix
   starts its own counter at 1; the old prefix's counter is kept, so going
   back to it continues where it stopped and no number repeats. Bills already
   issued keep their numbers.
5. Settings warns when a series has used 95% of its padding. At the limit the
   refusal reads: *"This series has used its last number; give the company a
   new prefix to start a new series."*
6. A change of padding or year format is refused if any prefix in use would no
   longer fit in 16 characters, as today (section 8).

**Build, in small parts (Opus for code).**

- (a) this section;
- (b) the year-format option on the numbering rule, and the counter key per
  prefix only when no year is printed;
- (c) new firms default to *none* with 8-digit padding on the sales bill
  series; existing firms unchanged;
- (d) Settings text shows the fit, the 95% warning and the limit message;
- (e) prefix change mid-year, change back, the 16-character check and a year
  rollover with no repeated number, in tests; docs; a drive on a NEW test firm.

**(b) is built (2026-10-17).** `document_numbering_rules.year_format`
(migration `20261017_0397`) holds `NONE`, `TWO_DIGIT`, `SHORT` or `FULL`; the
fourth keeps a rule that prints `2026-2027` printing it. The two year flags
stay and are kept in step; existing rows were backfilled from them, so every
firm prints as before. Sending `NONE` forces `auto_reset` off, and a sales
bill whose number prints no year counts under its prefix alone (an empty
`financial_year` on `bill_series_counters`), starting past the highest
number the prefix reached in any year. `TWO_DIGIT` prints `26` and is still
counted per full year label. The 16-character check reads the format, so a
prefix of up to 3, 6 or 9 characters fits with six digits under `SHORT`,
`TWO_DIGIT` or `NONE`. New firms' defaults are unchanged until (c).

**Open for the owner.** None; the build order puts it after the Buying sweep
and the Viewer-menu fix.
