# API and persistence conventions

These rules were in `CLAUDE.md` until 2026-09-15, when that file passed the
150k-character limit that keeps it loadable in one context window. Nothing
was cut -- the prose is verbatim and the imperative half of each rule stays
in `CLAUDE.md` with a pointer here. Every one was written from a defect that
actually happened, so the story beside the rule is the part that says why it
is the rule.

Routers, schemas, pagination, concurrency, migrations and the clock.

## A report needs an entry in `report_catalog.dart`

**A report the server produces needs an entry in `report_catalog.dart`, and
the orphan-route guard cannot tell you it is missing.** That guard matches a
served path against the *shapes* the desktop builds, with a hole on either
side matching any segment -- so `/api/v1/sales-returns/reports/register`
reads as reachable because `/api/v1/sales-orders/reports/register` has the
same five-segment shape and is listed. Six reports were unreachable for
exactly that reason on 2026-09-04: the sales return's four and the
quotation's two, all written after the catalogue was and never added to it,
and all returning real rows the moment they were driven by hand. The reports
workspace renders what the catalogue names, so the question is whether
*this* path is listed rather than whether one of its shape is.
`tests/unit/test_reports_have_a_screen.py` asks it both ways -- a served
report with no entry, and an entry naming a path nothing serves, which is
the worse of the two because it appears in the list and fails when opened.
`_ELSEWHERE` records the one deliberate exception: `sales-invoices`'
`/reports/summary` answers a single object of counts that the invoice
workspace's header cards read, and a grid deriving columns from rows has
none to derive from.

## A route nothing calls is where whole features have gone missing

**A route nothing calls is where whole features have gone missing.** Three have come off that list -- `category_attribute_rules`, the two vendor masters, and `product_packaging_levels` -- each unusable for months. `tests/unit/test_routes_have_a_caller.py` is the inverse of `test_desktop_calls_reach_a_route.py` and pins the four routes deliberately left without one, so a new orphan fails the build rather than waiting to be rediscovered by hand. It does not forbid them: adding one is a deliberate act with the reason recorded in `_ACCEPTED`.
**A call in `api_client.dart` counts as a caller, which is the hole.**
Six features merged between 2026-09-02 and 2026-09-03 had a route, a client
method and **no button** -- charging for delivery on a quotation or an
invoice, raising a proforma, spending loyalty points, sweeping lapsed ones,
naming the order a deposit came in against, and reading what has been paid
against an order. Every one passed the orphan-route guard, because the guard
asks whether a path is named anywhere in the client rather than whether a
screen can reach it. `desktop/test/reachable_features_test.dart` pins the
controls themselves; extend it when a feature lands, because the day a
feature merges is the only day anybody remembers it is unreachable.
**The sales-order toolbar is full**, incidentally: at the 800x600 default
test window a seventh control wraps the row and pushes the empty state off
the bottom, which is what `test/sales_order_ux_test.dart` reported. Deposits
went into the order's own `DocumentViewDialog` instead, through a generic
`extra` slot -- a fact about the order belongs with its totals, and
`WorkspaceContextAction` is a fixed framework enum that must not grow a
member for one screen.

## A literal path must be declared before `/{id}` in the same router

**A literal path must be declared before `/{id}` in the same router.** FastAPI matches in declaration order, so `sales_territories` had `/{territory_id}` above `/dashboard`, `/search`, `/beat-plans` and `/export` -- all four were read as a territory id and answered 422 "Input should be a valid UUID", so the Geography dashboard had never shown a number and beat plans could not be listed at all. **Nine more were found on 2026-08-22, in eight routers**: `vendors/categories` and `vendors/types` (which is why those two masters had no caller -- neither list had ever returned a row) and the `GET /export` of `branches`, `warehouses`, `sales-orders`, `delivery-notes`, `goods-receipts`, `purchase-invoices` and `purchase-returns`. Every one had been unreachable since the day it was written. `tests/unit/test_route_declaration_order.py` walks the built application and fails the build on the next one, so this is now a caught mistake rather than a remembered one.

## A foreign key's name must be unique within its table

**A foreign key's name must be unique within its table, which keying on the referring column guarantees.** `FK_<table>_<column>` is the convention and 574 of the 589 named keys follow it. Keying on the referred *table* collides whenever one table has two foreign keys to the same target, which SQLite ignores and PostgreSQL rejects — that made `Base.metadata.create_all` unusable on PostgreSQL, and the sample-data and tenancy-reset scripts build firm stores with it. The 15 exceptions are all UOM slots (`FK_products_purchase_uoms` and its siblings), which name the referred table but carry the slot's prefix, so they are unique and harmless. **The collision is the thing to guard, not the spelling**: `tests/unit/test_schema_registry.py` fails the build on two keys sharing a name.

## No model may declare its own `version` column

**No model may declare its own `version` column** — that name is the concurrency counter below, and a business version under it gets incremented by every ORM update. `tax` and `uom` both call theirs `version_number`; `uom.ConversionRule` was renamed in `20260809_0055` after the ORM was found moving the version documents record in `conversion_version`.

## A bare `ResolvedFirmScope` parameter is read by FastAPI as a request body field

**A bare `ResolvedFirmScope` parameter is read by FastAPI as a request body field.** `ResolvedFirmScope` is a plain dataclass; the injectable form is `RequiredFirmScope` (`Annotated[..., Depends(required_firm_scope)]`) from `app/common/scope.py`. Nineteen handlers on the sales router took the bare class, so every geography write and `PUT /hierarchy-levels` answered 422 demanding `body.payload` and `body.scope` — uncallable since the day they were written, and invisible because nothing called them. Grep for `scope: ResolvedFirmScope,` before adding a platform-admin endpoint.

## A handler never validates a request model by hand

**FastAPI answers 422 only for what it validated itself.** A JSON import arrives as a multipart form field, so the handler is handed a string and validated it with `Model.model_validate_json(payload)`. That raises pydantic's `ValidationError`, which is not FastAPI's `RequestValidationError`, so it reached the unhandled-exception handler: eight of the nine JSON import routes (sales orders, quotations, delivery notes, sales returns, purchase orders, goods receipts, supplier bills, purchase returns -- and products and opening stock, which were not driven) answered **500 "An unexpected error occurred."** for any file their schema refused, and wrote a diagnostics row for each. Since D-PRC-60 put the line-number rule in the schema, a file with two lines numbered 1 was one of them (D-PRC-76, 2026-10-06, found by round 7 of the pricing API check; 42 requests). `sales-invoices/import` takes a JSON body, which FastAPI validates, and always answered 422.

`parse_payload(Model, payload)` in `app/core/validation/payloads.py` is the one way a handler reads such text. A refusal is the project's `ValidationError` (422, `validation_error`). Its **message is the first problem, naming the record**: "Record 2 of 2: Lines 1 and 2 of the request are both numbered 1. Number each line once." -- the single save's own sentence where one of our validators wrote it, and `Record 1 of 1: customer_id: Field required` where pydantic did, because that sentence is nothing without its field. `details` lists every problem as `field` / `message` / `code`, the shape request validation uses; a message ends "(2 more problems in the details.)" when there are more. Text that is not JSON says so. Nothing is read from the store before the refusal.

`tests/unit/test_import_payload_refusals.py` walks every `app/*/api/router.py` and fails on `model_validate_json`, or `model_validate` on a request model, in a handler.

**A record the service refuses is named too** (D-PRC-85, 2026-10-06). A record the schema takes and the service then refuses -- a return line whose units are already back -- answered with the single save's sentence alone, so in a file of two nobody could tell which record it was about; a purchase return's import already said "Record 2 of 2: ... Nothing was imported." `stage_records(records, stage, rollback=...)` beside `parse_payload` is how an import stages its file: it rolls back and re-words the first refusal with its record number, keeping the refusal's class, status and details, and leaves any other failure as it is. The five selling imports (orders, quotations, delivery notes, bills, returns) stage through it, and the same test file fails if one goes back to a bare loop. A new import calls it rather than writing a sixth `try`.

## Declare `page` and `page_size` bounds on the query parameter

**Declare `page` and `page_size` bounds on the query parameter, not by constructing `PaginationParams` inside the handler.** Swept across all 23 routers on 2026-08-21 and guarded by `tests/unit/test_pagination_conventions.py`, which fails the build on a handler that takes a bare `page: int = 1` or `page_size: int = 20`. `MAX_PAGE_SIZE` is 100 and the model enforces it — but constructing the model in the body of the function turns an over-cap request into a pydantic error *after* routing, which surfaces as a **500** rather than a 422 naming the limit. Two desktop screens shipped asking for `pageSize: 500` and were broken against every real backend while their tests, whose fakes ignore the value, stayed green. Client-side use `fetchAllPages` (`desktop/lib/ui/workspace/paged_fetch.dart`); server-side use `Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]`.

## A partial unique index cannot be `DEFERRABLE`

**A partial unique index cannot be `DEFERRABLE`, so a swap must release before it reassigns.** `UQ_territory_customer_assignments_sequence_active` keeps two shops off one stop number, and PostgreSQL checks it per statement — so reassigning row by row collided the moment two rows exchanged values, which is exactly what dragging one stop above another does. `set_customers` clears the numbers it is about to hand out, flushes, then writes them, and clears **only** the ones actually moving so a re-save that says nothing about order leaves the sequence alone. Any "reorder within a set" that grows a uniqueness key needs the same shape.

## A screen that replaces a whole list must prove it read that list first

**A screen that replaces a whole list must prove it read that list first.** `PUT /{id}/customers` and the salesmen twin replace rather than merge, so the pane on screen *is* the record. Both territory screens clear the pane **before** the read rather than after it succeeds, and refuse to save until the pane provably holds the selected route — without that, a failed read left the previous route's shops on screen and one Save wrote them over a different round.

## `ondelete="RESTRICT"` is not a guard on a soft-deleted table

**`ondelete="RESTRICT"` is not a guard on a soft-deleted table.** Every foreign key into the six geography tables is RESTRICT, which reads like protection; a soft delete never reaches the database's referential check, so a "deleted" city would stay wired to every branch naming it and simply vanish from the list. The refusal has to live in the service, and it has to look at the level below *and* at everything outside the module — addresses, branches, warehouses, route profiles.

## An update that dumps its whole write model turns an omission into an instruction

**An update that dumps its whole write model turns an omission into an instruction.** A write schema gives every optional field a default, so `model_dump()` returns a value for a field the caller never mentioned, and assigning all of them writes that default over live data. It has now shipped twice. `VendorUpdate`'s six child collections defaulted to `[]` and the API replaces rather than merges, so correcting a phone number destroyed a vendor's addresses, contacts, bank accounts, tax details, attachments and notes -- one seeded vendor had already lost its address. `BranchUpdate`/`WarehouseUpdate` did the scalar version: one rename cleared the branch's street lines, its city, its default flag and its GST registration, and a warehouse's ten capability flags, because the desktop form edits none of those and hardcoded `false` for the flags. Both now dump with `exclude_unset=True` on update only, so **absent means leave alone and an explicit `null` still clears** -- the distinction that makes a partial client safe without stopping a complete one clearing a field. Create is unchanged: there a default really is the value to store. Anything read from such a dump needs the row as its fallback (`values.get("is_default", row.is_default)`), or a promotion becomes a demotion. **A status field is the worst case of this shape, and `update_order` in `app/purchase` had it until 2026-08-18.** `PurchaseOrderUpdate` defaults `status` to DRAFT and the service assigned it straight onto the row, so a client that said nothing about the status silently reset an APPROVED order -- and a PARTIALLY_RECEIVED one, which nothing could then move back, because the receipt resync only touches an order already in the receiving part of its life. The desktop hid it by echoing back the status it last read, which produced the mirror-image fault: an approved order could be edited to any amount and stay approved. **A lifecycle status belongs to its transition endpoints and must never be writable through the update body**; the fix was to stop reading `data.status` at all, not to make the dump partial. **All eight remaining full-dump updates were made partial on 2026-08-21** -- `update_{attribute,category_rule,feature,module,profile}` in `app/business` and `update_{numbering_rule,state,type}` in `app/document_framework`. `update_profile` also reads `is_default` from the dumped values with the row as its fallback, because reading it off the model made an omission mean False: renaming the default profile demoted it and left the store with no default at all. Creates still dump in full, which is right -- there a default really is the value to store.
**`app/customers` joined on 2026-08-23** and brought the child collections
with it: `addresses` and `contacts` are replaced rather than merged, so
reconciling one the caller never sent soft-deleted every row in it, and a
full dump of the scalars reset `credit_limit`, `payment_terms_days` and the
new `default_discount_percent` on any partial request. Both are now guarded
on `model_fields_set`, and `opening_balance` is read out of the dumped values
with the row as its fallback -- reading it off the model made an omission
mean zero, which the balance-reset guard then acted on.

## An audit row says what changed, on the trail of the firm that changed it

`record_change` (`app/common/audit/services/changes.py`) audits a create, an update or a soft delete of one row: the whole row on a create, the whole row on the before side of a delete, and on an update **only the fields that moved** -- and no row at all when none did. Take `row_state(row)` before the write and pass it as `before`. A row that names the record and not the change is a row nobody can use: a conversion factor moved 1 → 2 with both sides empty, the print template's bank account changed with only the document type recorded, and 521 empty `user_preferences.updated` rows from screens that changed nothing (D-CFG-13).

`get_db` and `firm_store_session` mark the session with the firm whose store they opened (`Session.info[STORE_FIRM_SESSION_KEY]`), and `record_audit` uses it when a write names no firm. A firm's trail filters on `firm_id`, so a row left null in a firm's own store -- the business-framework catalogue and geography, which carry no firm column -- was on no screen. The platform store carries no mark, so platform rows are unchanged. In `firm_shared` the catalogue is one set for every firm there, and the row lands on the trail of the firm that made the change, not of every firm it touches.

## Bulk endpoints are a second implementation

**Bulk endpoints are a second implementation.** The six branch/warehouse bulk operations wrote no audit rows and skipped the delete guards their single-row twins enforced, so review both paths. The same module's two import endpoints looped over `create_branch`/`create_warehouse`, which commit, so a batch whose fifth row clashed returned 409 with the first four already written — and the corrected file then failed on those four as duplicates, making the import impossible to complete. Imports stage and commit once (`import_branches`/`import_warehouses`, the shape `CustomerService.import_customers` always had); the desktop dialog says so, because the user's first question after a failure is whether half of it went in. Exclusivity flags (`is_default`) are demoted in the service and backed by a partial unique index (`UQ_branches_default_active`, `UQ_warehouses_default_active`, `20260809_0056`); demotion must flush before the promoted row is written.

## Never read the server's local clock

**Never read the server's local clock.** Everything persisted here is UTC, so `date.today()` compares against a date the data does not use — on a non-UTC deployment it is already tomorrow, or still yesterday, for part of every day. It shipped three times (a UOM rule that was not yet effective, expiry buckets a day out, then the overdue reports and document numbering until 2026-08-10). Call `utc_now()`; `tests/unit/test_time_conventions.py` fails the build on any new occurrence. `func.now()` is fine — that is SQL the database evaluates. **`utc_now().date()` is the UTC day, which is not "today" for a business date — see the next section.**

## A business date is the firm's own day

**"Today" for a business date is `firm_today(session, firm_id)`
(`app/common/firm_metadata.py`), never `utc_now().date()` (D-CFG-25,
2026-10-06).** The rule above settled the *clock*; it left every "today" as
the UTC day, and for a firm in India that is yesterday from midnight to
05:30. Driven at 00:30 IST: a supplier refund dated today was refused "A
refund cannot be received on a future date." and one dated yesterday "A
refund is received on or after the return", so the return could not be
refunded at all until 05:30; an opening bill could not be dated today; and
the stock valuation read 0.00 for stock on hand, because the route capped
its day at the UTC one. Tally, Zoho Books and ERPNext all judge a document
date in the company's time zone, and so does this now.

- **Timestamps are UTC and stay UTC, and `utc_now()` stays the one clock.**
  `firm_today` is `utc_now()` read in the firm's zone, nothing else. An
  instant -- a token's expiry, an audit timestamp, a retention cutoff, the
  five-minute tolerance on "received in the future" -- is not a business
  date and does not use it.
- **The zone comes from the firm's country**, through
  `business_zone` in `app/core/utils/dates.py`: `IN` is `Asia/Kolkata`. A
  firm carries no time zone of its own and no migration added one. A country
  not in that table, an unknown firm and no firm at all read the UTC day,
  which is what every firm read before. Only a country with **one zone and
  no daylight saving** belongs in the table, because each entry also names a
  fixed offset used where the machine has no zone database (`tzdata` is
  present in this venv only as somebody else's Windows dependency, and a
  compiled build or a slim container may not carry it).
- **`firms` is a platform table**, so the country is read through
  `FirmMetadataReader` and remembered on `Session.info` for the life of the
  request: a list that asks "is this row overdue today" per row pays one
  lookup, not one per row.
- **`firm_date_of(session, firm_id, instant)`** is the same reading of a
  stored timestamp, for setting one beside a business date. Proof of
  delivery compared the UTC date of `delivered_at` with the note's date, so
  goods handed over at 01:00 on the note's own day were "received before the
  note".
- **It is applied everywhere a day is a business date** (2026-10-06, in two
  passes). The first moved the "not in the future" and "today or later"
  checks on a typed date and the report defaults in the buying, selling,
  customer, supplier, settlement and inventory modules, and stopped there,
  listing what it left. A check on the running server the same night showed
  what the remainder cost: a tax invoice raised by *Dispatch and invoice* at
  01:00 was dated **yesterday**, a batch on its last day read "1 day", a
  shift opened at 02:31 on the 6th listed under the 5th and its report said
  "printed 05-10-2026". The second pass took the whole of `app/` from an
  inventory rather than a list -- 84 reads of `utc_now().date()`, three
  `now.date()` on an instant read a line earlier, two on a stored
  `created_at`, and eight day boundaries built at UTC midnight -- in four
  pull requests:
  - **dates the server stamps**: an invoice, order, purchase order or RFQ it
    raises for somebody; a document number issued with no date, and so its
    financial year on the night of 31 March; every reversal dated
    `max(today, original)` -- the mirror journal in
    `journal_engine.reverse_entry` and the statement, stock and loyalty rows
    that follow it. Still never before the original (D-FIN-5);
  - **validity windows**: a batch's expiry and days left, a rate contract's
    or supplier quote's period, a price revision, a licence, a rebate's or
    commission period's "is it over", loyalty expiry, a lapsing reservation,
    the 30-day e-invoice limit;
  - **report defaults and "printed on"** outside the first pass's modules;
  - **as-of boundaries on a timestamp**, below.
- **A price list and a promotion were never in this class**: both are judged
  on the *document's* date, never on today, so the only day that reaches
  them is the one on the document -- which is why the date the server puts
  on a document mattered most.
- **A helper with no firm to hand takes the day from its caller.**
  `_batch_is_expired(batch, today)` and `display_status(row, today)` gained a
  parameter rather than a hidden lookup; a `responses(rows)` builder reads
  the firm off its first row. A platform screen that holds the `Firm` row --
  firm readiness and "open books" -- calls `business_today(firm.country)`.
  The sandbox e-way bill portal dates validity on India's day whoever calls
  it, because the portal it stands in for is India's.
- **A day's boundary on a timestamp is `firm_day_after(session, firm_id,
  day)`** (and `firm_day_start`), built on `business_day_start` in
  `app/core/utils/dates.py`. "Was it cancelled after the 5th" was asked as
  `cancelled_at >= midnight UTC on the 6th` in five private copies -- the
  customer ageing, customer opening bills twice, party adjustments, the
  payables report, `settled_against` -- and for India that instant is five
  and a half hours late: a bill cancelled at 01:00 on the 6th read as
  cancelled on the 5th and left an ageing as on the 5th, when it was still
  owed that day. The 6th begins in India at 18:30 UTC on the 5th. Compare
  with `>=` or `<` against the start of the next day; a `time.max` upper
  bound leaves a microsecond out.
- **What still reads the UTC day, on purpose**, is short enough to name:
  `app/diagnostics/quick_check.py`, a command-line client with no session
  and no firm row, picking last month as a window that holds data; and the
  `created_from` / `created_to` filters on customers, vendors and branches
  with the audit trail's date filters, which are inclusive **UTC** calendar
  days by this document's own convention (the platform trail has no firm at
  all). A firm with no country known, and a screen with no firm -- no
  `X-Firm-ID` -- read the UTC day through the same helpers. The territory
  dashboard's "new in the last 30 days" is thirty times twenty-four hours
  on an instant, not a calendar window.
- **`tests/unit/test_time_conventions.py` fails the build on the next one.**
  Two AST guards beside the local-clock one: `utc_now().date()` (and
  `now = utc_now()` then `now.date()`) anywhere outside `UTC_DAY_ALLOWED`,
  and `datetime.combine(..., UTC)` outside `UTC_MIDNIGHT_ALLOWED`. Each entry
  carries its reason, and a third test fails when an entry no longer needs
  its exemption. What the guards cannot see is a day computed **in SQL** --
  none exists today (`func.current_date` and a `created_at` cast to a date
  appear nowhere in `app/`), and a new one would be the same defect.
- **Whether a batch dated today has expired was not changed.** The picker
  and the expiry cards say yes on the day itself (`expired_condition` is
  `<=`); dispatch and reservation pass a batch over only from the day after
  (`_expired_batches` is `<`). The two disagreed before this work and still
  do; only the day both count from moved.
- **A test freezes `app.core.utils.dates.utc_now`** at 19:30 UTC, which is
  01:00 the next day in India (`tests/unit/test_business_date.py`). A fixture
  firm with `country="IN"` sees India's day, so a test that builds "today"
  from `utc_now().date()` and expects a business rule to agree is wrong for
  five and a half hours of every day: take the day from `firm_today`, or pass
  the day in. Eighteen test files were corrected for exactly that across the
  two passes, found by running them between midnight and 05:30. **Patch the
  shared clock, not a module's copy of it**: two reversal-date tests set
  `journal_engine.utc_now`, which stopped deciding the day the moment the
  engine asked `firm_today`.

## Never let NULL ordering pick a row

**Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in `DESC`, SQLite last, so `ORDER BY product_id DESC` made a firm-wide UOM conversion rule outrank a product's own factor in production while the unit suite saw the right answer. Rank on `case((col.is_(None), 1), else_=0)` and cover it in `tests/integration/`.

## Optimistic concurrency protects a row, never a set of rows

**Optimistic concurrency protects a decision about a *row*, and nothing
about a decision about a *set* of rows.** The rule behind four findings on
2026-09-03. A guard that reads a row and updates it is safe --
`version_id_col` makes the stale write raise -- which is why `inventory`
dispatch is safe despite having no lock, no CHECK on `available_quantity`
and a read-modify-write in Python. A guard that reads a **sum or a count and
then inserts** is not: no row is updated, so no version can conflict, and
two transactions that both read before either commits both pass. Three sites
had it, and each wanted a different mechanism because each guards a
different kind of thing: `commission.accrue` guards a **key** and took a
partial unique index; `loyalty.redeem` and `credit_note`'s per-line cap
guard a **sum**, which no key can express, so they hold the thing being
consumed with `with_for_update` -- the customer, and the invoice line, per
row rather than per firm so unrelated work does not queue. Reaching for one
mechanism everywhere would have been wrong twice out of three times.

## `BaseEntity.version` is the mapper's version id

**`BaseEntity.version` is the mapper's version id.** Every ORM update bumps it and checks it, so a stale write raises `StaleDataError` (mapped to 409). Bulk `query().update()` bypasses this by design. Update endpoints accept `If-Match` carrying the version the client last read, and **every response that returns one versioned record publishes that version as an `ETag`** through `set_etag` in `app/core/concurrency.py`. **Twenty-four routers do**, not the six this line used to name -- it enumerated firms, purchase orders, sales orders, delivery notes, goods receipts and customers, and stopped being exhaustive the moment the seventh was added. Count them rather than trusting a list: `grep -rl 'set_etag\|publish_version' app/*/api/router.py`. Publish it on any new endpoint of that shape: five routers accepted the header for months while no response carried the version anywhere, so the only value a client could honestly send was `*`, which means no precondition. A client should echo the `ETag` it was given rather than compute the next version — an update can advance the counter by more than one. Sending nothing is still accepted, so the precondition is opt-in and existing clients keep working. **The version is also a field on those response bodies** -- 28 of them -- which is not duplication: a header carries one value and a list carries many records, and the desktop opens its editors from list rows rather than re-reading the record, so an ETag alone could never reach the screen that needs it. The desktop sends `If-Match` for **every module that publishes a version** as of 2026-08-22 -- customers, vendors, products, branches, warehouses, quotations, UOM, tax, batch/serial, inventory, territories (including places and beat plans) and the business-profile catalogue, which the backend accepts even though no desktop screen edits it yet. Two shapes of wiring: a service that returns the row uses `set_etag`, and `app/sales`, which builds its response models in the service, uses `publish_version` with the number. **A save that changes nothing does not move the counter**, so a second save with the same `If-Match` is accepted -- correct, and worth knowing before writing a test that expects a 409 from re-sending an unchanged record. **UOM and tax joined on 2026-08-22**, which needed a name first: a conversion rule and a tax rule each publish a revision of their own, and `uom` exposed that as `version` — the one name the counter has to have. The revision is `version_number` everywhere now (the column's name, and how `tax` always spelled it) and `version` is the counter. The rename found a second copy of the rule resolver in `app/inventory` matching a line's stored revision against the *counter*, which agreed only until somebody edited a rule. Client-side the message differs by editor shape: a dialog that saves from inside keeps the user's typing on a refusal and says so, one that closes first does not — see `concurrencyMessage(noun, changesKept:)`. A record whose `version` is absent reads as zero client-side and saves with no precondition, so an older backend stays usable.

## `as_utc()` in `app/core/utils/dates.py` reads a stored timestamp

**`as_utc()` in `app/core/utils/dates.py` reads a stored timestamp.**
`UTCDateTime` is `DateTime(timezone=True)` and **SQLite ignores the
timezone**, so what PostgreSQL returns aware the unit suite returns naive.
Anything comparing a stored timestamp to `utc_now()` raises "can't subtract
offset-naive and offset-aware datetimes" in the tests and works in
production, or the reverse. Everything stored here is UTC, so a naive value
is one that lost its label leaving the database -- say so once, there.

## A hand-written `op.create_table` must spell out the timestamp defaults

**A hand-written `op.create_table` must spell out the timestamp defaults,
or the table cannot be inserted into at all.** `TimestampMixin` declares
`created_at`/`updated_at` with `server_default=func.now()`, so
`Base.metadata.create_all` builds them with a default and SQLAlchemy leaves
the column out of every INSERT. A migration that writes the two columns
without `server_default=sa.text("CURRENT_TIMESTAMP")` builds a NOT NULL
column with no default, and the **first** write raises `NotNullViolation`.
The unit suite cannot see it -- it builds its schema from the ORM, so the
default the migration forgot is always there in the tests. Found by driving
a real firm; `20260903_0114` set the default on every undefaulted column in
every store, which turned out to include all **twelve `tax` tables**, live
since they were written and usable only because `TaxFrameworkService` passes
`created_at=now` by hand on every insert.
`tests/integration/test_multi_schema_tenancy.py::test_every_deployed_table_can_be_inserted_into`
is the guard.

## Nothing prunes the history tables until somebody enables it

`refresh_tokens`, `login_history` and `password_history` have no automatic cleanup of their own, and neither does `tax_rule_execution_logs`. **`scripts/purge_retention.py` is the one to run**: it enumerates every firm store from the registry — dedicated schemas and dedicated databases included — and applies both retention services, so it cannot miss a store the way running the two single-purpose scripts by hand does. `--dry-run` reports, `--yes` applies. The `retention` service in `docker-compose.yml` runs it on a loop, and is **opt-in**: `docker compose --profile retention up -d`, because bringing the stack up should not start deleting rows on its own. Until someone enables it nothing prunes these tables, which is how they grew unbounded to begin with. `AGENCY_RETENTION_INTERVAL_SECONDS` sets the period (default daily) and `AGENCY_RETENTION_MODE=--dry-run` makes it report instead of delete. `scripts/purge_identity_history.py` and `scripts/purge_tax_execution_logs.py` remain for pruning one store on its own. `tax_rule_execution_logs` is the same shape and grows fastest — one row holding three JSON documents per document line — and is pruned per firm store by `scripts/purge_retention.py` (every store at once) or `scripts/purge_tax_execution_logs.py` (one store, selected with `AGENCY_DATABASE_SCHEMA` the way a migration does).

## An uploaded file's bytes live in the firm's own store

Decided 2026-10-05 for PG-4 (the supplier's bill on a purchase bill and a goods
receipt), when the platform first kept file *content*. Until then every
`*_attachments` table (`purchase_invoice_attachments`, `goods_receipt_attachments`,
`ledger_attachments`, `stock_attachments` and their siblings) recorded only a
`file_path` the client typed, and the document tables among them are rewritten
wholesale on every edit, so an uploaded file could not live there. **The bytes
go in the firm's store**: `document_files` holds name, type, size, SHA-256 and
caption, and `document_file_contents` holds the bytes in a separate table keyed
by the file, so a list, or the per-page `attached_file_count` on bill and
receipt list rows, never reads a file. This keeps a firm's paper inside its
own database, where the isolation and per-firm backup and restore already
apply, and needs no file server, path or second backup. **At most 10 MB a
file, and only PDF, JPG and PNG**: the type stored and served is the one the
file's first bytes name, and the name's extension and the declared multipart
type (unless it says only `application/octet-stream`) must agree with it, so
an `.exe` renamed `.pdf` is refused by its contents. A removal is a soft delete
and is audited; the bytes stay with the row. A download is served under the
stored type with `X-Content-Type-Options: nosniff`. `app/document_files` is
the one implementation; a new document that takes uploads adds a nullable
parent key and a check, not a new table.

**The five sales documents joined it on 2026-10-05 (SG-6)** -- the quotation,
the sales order, the delivery note, the sales invoice and the sales return --
exactly that way: five nullable keys on `document_files`, an index on each, and
the check widened from "the bill or the receipt" to "exactly one of the seven"
(migration `20261005_0321`, firm-owned and idempotent). No second service and
no new table; a kind of document is one entry in `FileParent` and one in the
`_PARENTS` map beside it. Each document has the same four routes under its own
prefix (`/quotations`, `/sales-orders`, `/delivery-notes`, `/sales-invoices`,
`/sales-returns`): `GET /{id}/files`, `POST /{id}/files`,
`GET /{id}/files/{file_id}/content` and `DELETE /{id}/files/{file_id}`.

- **Permission is the document's own, and no code was added.** Listing and
  downloading take the module's view scope (`SALES_VIEW`); uploading and
  removing take its update scope -- `SALES_UPDATE` on the quotation, the
  delivery note and the return, and `SALES_UPDATE` *or* the create code on the
  order and the invoice, because those two routers already let whoever may
  raise the document edit its draft.
- **A file belongs to one document of one firm.** Another firm's document, or
  a file named under a document it is not on, is *not found* (404) rather than
  forbidden, so the answer never confirms that an id exists somewhere.
- **Status does not gate it.** PG-4 lets a file go on or come off a bill in any
  status -- the supplier's paper usually turns up after the bill is approved --
  and sales follows the same rule: the signed challan arrives after dispatch
  and the customer's debit note after the return is closed. What protects the
  record is the trail (`document_file.attached`, `document_file.removed`), not
  the document's lifecycle.
- **`attached_file_count` is on all five list rows and single responses**,
  filled by `document_file_counts` in one grouped read for the page, never per
  row and never touching `document_file_contents`.
- **The older `*_attachments` tables on these documents are untouched.** They
  still hold a name and a path the client typed and are still rewritten with
  the document; an uploaded file is a different thing and lives only here.

**A check constraint a migration names is not always called that in the
store.** `alembic/env.py` hands the metadata's naming convention to `op`, so
`20261005_0306` creating `CK_document_files_one_parent` deployed it as
`CK_document_files_CK_document_files_one_parent`, while a store built by
`Base.metadata.create_all` carries the name the model declares. `20261005_0321`
therefore finds the check by what it says rather than by its name, and passes
names through `op.f()` so they are used as written.

## `TaxRuleService.simulate` is the tax calculation, not a preview

**`TaxRuleService.simulate` is the tax calculation, not a preview.** **Nine** modules call it once per line while building a document -- the eight above and `quotation`, which prices with tax even though it converts no units -- on their own session, so it must never commit — the `/simulate` endpoint owns that. It also derives `country_id` from the applied profile's tax system and `business_profile_id` from the firm's assignment, because no document sends either and rules scoped that way otherwise never match. `total_tax_amount` is only what the counterparty is billed: tax `included_in_price` and tax under `REVERSE_CHARGE` are reported in `inclusive_tax_amount` / `reverse_charge_tax_amount` and must not be added to a document total.
