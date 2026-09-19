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

**Never read the server's local clock.** Everything persisted here is UTC, so `date.today()` compares against a date the data does not use — on a non-UTC deployment it is already tomorrow, or still yesterday, for part of every day. It shipped three times (a UOM rule that was not yet effective, expiry buckets a day out, then the overdue reports and document numbering until 2026-08-10). Call `utc_now().date()`; `tests/unit/test_time_conventions.py` fails the build on any new occurrence. `func.now()` is fine — that is SQL the database evaluates.

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

## `TaxRuleService.simulate` is the tax calculation, not a preview

**`TaxRuleService.simulate` is the tax calculation, not a preview.** **Nine** modules call it once per line while building a document -- the eight above and `quotation`, which prices with tax even though it converts no units -- on their own session, so it must never commit — the `/simulate` endpoint owns that. It also derives `country_id` from the applied profile's tax system and `business_profile_id` from the firm's assignment, because no document sends either and rules scoped that way otherwise never match. `total_tax_amount` is only what the counterparty is billed: tax `included_in_price` and tax under `REVERSE_CHARGE` are reported in `inclusive_tax_amount` / `reverse_charge_tax_amount` and must not be added to a document total.
