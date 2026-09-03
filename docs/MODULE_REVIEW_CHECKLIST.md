# Module Review Checklist

A per-module review pass, in the shape that worked for the platform layer on
2026-08-09. That pass found twelve unseeded permission codes, a login timing
side-channel, a permanently-burned email address on user delete, missing refresh
token reuse detection, and three unbounded tables — none of which were visible
from reading a single file.

Two rules carried over from it:

- **Verify before you claim.** Two of the eight platform findings were wrong and
  were caught only by checking against the running system before acting. Reproduce
  a defect before fixing it, and re-check the fix against a real database.
- **Record the baseline first.** Capture the module's test/lint/type counts before
  changing anything, so your diff is measured against fact rather than assumption.

## The checklist

Run these against one module at a time. Items marked **(found a real bug)** are
ones that produced a defect during the platform pass.

### Business profile

- [ ] Behaviour that is industry-specific is gated on a **feature**, not hardcoded
      **(found a real bug — 18 of 21 features were unenforced)**. Use
      `require_feature` / `require_module` from `app/business/gating.py`.
- [ ] The feature exists in `business_features` and is enabled for the profiles
      that should have it; check `profile_features`, not just the code.
- [ ] Gates are on writes only; reads stay open so existing data remains visible.

### Authorization and tenancy

- [ ] Every code passed to `require_permission` exists in `PERMISSION_GROUPS`
      **(found a real bug — 12 codes)**. `tests/unit/test_identity_hardening.py`
      now guards this globally, but check that new codes reach a sensible role.
- [ ] Every firm-owned route resolves scope through `X-Firm-ID` **and** validates
      an active `UserFirm` membership — platform admins included.
- [ ] Firm-scoped queries filter on `firm_id`; nothing leaks across firms. Write a
      two-firm test that asserts the second firm sees nothing.
- [ ] Uniqueness checks filter `is_deleted` **(found a real bug — user email)**.
      A soft-deleted row must not permanently reserve a natural key. **The
      database constraint has to agree with the service check** — `firms` kept
      table-wide `UNIQUE` constraints while `_assert_unique` ignored deleted
      rows, so re-creating a deleted firm passed validation and then died on the
      constraint with a 500 **(found a real bug — firm code, GST and PAN)**.

### Persistence and migrations

- [ ] Entities extend `BaseEntity`; no bespoke id/timestamp/soft-delete columns.
- [ ] Constraint names follow `UQ_`/`IX_`/`FK_`/`PK_`.
- [ ] Migration matches the ORM exactly. Diff them rather than eyeballing:
      build one schema from `Base.metadata.create_all` and one from the
      migration's `upgrade()`, then compare columns table by table.
- [ ] Migration is **idempotent** — guard `add_column`/`create_table` with
      `sa.inspect(bind)` checks **(found a real bug — `20260808_0040`)**. Firm
      schemas are partly built by `create_all` in the sample-data scripts, so
      `alembic_version` understates what exists.
- [ ] Cross-schema foreign keys are conditional **(found a real bug — finance)**.
      `firms` exists only in `platform`; `customers`/`vendors` only in firm
      schemas. Declare the FK only when `has_table()` finds the target.
- [ ] Migration applied to **every** target, not just the default schema:
      `platform`, `firm_shared`, each dedicated schema, each dedicated database.
- [ ] `downgrade()` actually reverses `upgrade()`, verified by running it.

### Correctness and conventions

- [ ] Every mutation emits `record_audit` with before/after data.
- [ ] Responses use `ApiResponse` / `PaginatedResponse`; lists accept only the
      whitelisted `page`, `page_size`, `search`, `sort_by`, `sort_direction`
      **(found a real bug — seven `sales_invoice` endpoints answered with the
      bare model)**. `tests/unit/test_response_envelope_conventions.py` fails
      the build on the next one.
- [ ] **A literal path is declared before the `/{id}` that would swallow it.**
      `tests/unit/test_route_declaration_order.py` walks the built application
      and fails the build **(found a real bug -- nine endpoints in eight
      routers, every one unreachable since it was written: both vendor masters
      and seven `GET /export`)**.
- [ ] **A new endpoint the desktop will call, or a new screen calling one,
      leaves both sides agreeing.** The desktop's paths and this application's
      route table are compared by `tests/unit/test_desktop_calls_reach_a_route.py`
      **(found a real bug -- the Refunds screen's Reverse button answered 405,
      because one page serves three settlement directions and only two had the
      route)**. Watch the families in `_FAMILIES`: a path a variable fills in
      cannot be resolved from the text, so each is checked by member in a test
      of its own, and adding an unchecked one is how that defect survived.
- [ ] `page` and `page_size` declare their bounds **on the query parameter**,
      not by constructing `PaginationParams` in the handler body
      **(found a real bug — 44 endpoints, 28 recorded 500s across four of
      them)**. `tests/unit/test_pagination_conventions.py`
      fails the build on the next one.
- [ ] An update dumps with `exclude_unset=True`, and anything read out of that
      dump to decide something takes the row as its fallback
      **(found a real bug — three times: vendors, branches, business
      profiles)**. Create still dumps in full; there a default is the value.
- [ ] Update endpoints accept `If-Match` and every response returning one
      versioned record publishes the version — in the body **and** as an
      `ETag`. Every module with a record to edit does as of 2026-08-22.
- [ ] Date filters use `datetime.combine(date, time.min/max, UTC)` — not naive
      local dates **(found a real bug — audit filters)**.
- [ ] Money is `Numeric(18, 2)` quantized at the boundary, never float.
- [ ] No table grows without bound, or there is a documented purge path
      **(found a real bug — tokens and history)**.

### Tests

- [ ] A dedicated `tests/unit/test_<module>.py` exists.
- [ ] It passes **standalone**, not only inside the full suite.
- [ ] Covers: firm isolation, permission denial, validation failures, and the
      module's lifecycle transitions — not just the happy path.
- [ ] **Every new guard was run against the unfixed code first.** A test written
      after the fix proves the code compiles, not that it caught anything — and
      two of the guards written on 2026-08-21 failed for the wrong reason on
      that first run (a renamed method, not the behaviour), which only showed up
      because they were run at all.

### Desktop

- [ ] Endpoint paths live in `api_client.dart`, not inlined in pages via the
      untyped `api.request(...)` escape hatch.
- [ ] Backend capabilities have UI, or are explicitly `available: false` in
      `module_catalog.dart` rather than silently absent. **A tab describing a
      capability in prose is not UI** — four vendor tabs said things like "bank
      details are supported with primary flag" and offered no field to type one
      into, so four collections could only be filled by import.
- [ ] A screen that saves an existing record sends the version it read, and
      says something true about the typing when the save is refused —
      `saveFailureMessage(..., changesKept:)`.
- [ ] Screens compose the shared workspace framework instead of bespoke shells.

### Diagnostics

The product ships to customers as an executable on machines nobody here can
reach. A failure that leaves no evidence is a failure that cannot be fixed, and
support gets "it closed" and nothing else.

- [ ] Failures a user can hit reach `CrashReporter.recordError`, not a bare
      `debugPrint` — `debugPrint` goes nowhere in a release build and is gone the
      moment the window is.
- [ ] Nothing the module logs or reports can carry a credential. Passwords,
      refresh tokens, `Bearer` headers and JWTs are redacted by
      `DiagnosticsRedaction`; a user is identified by id, never by name or email.
- [ ] A failure leaves the window open and usable. An error must not be a reason
      for the application to disappear.
- [ ] Long or destructive operations write a log line before and after, so a
      report shows what the application was doing when it stopped.
- [ ] Business-critical operations call `log_operation` / `operation`
      (`app/core/logging`) or `AppLog.operation`, so "did it post?" is
      answerable from the log rather than inferred.
- [x] **A triage screen exists** as of 2026-08-21 — Settings › Diagnostics
      (`desktop/lib/ui/settings/diagnostics_page.dart`), faults collapsed by
      fingerprint with their occurrences, stack trace and breadcrumbs. It read
      real data on its first run and immediately surfaced a live defect: 28
      `ValidationError`s on `GET /api/v1/products`, a `page_size=200` request
      answered with a 500 because the handler builds `PaginationParams` in its
      body instead of bounding the query parameter.

### Gates

- [ ] `ruff`, `black`, `mypy` clean. **Repo-wide, not just for the module** —
      `ruff check .` and `black --check .` have been clean across `app/`,
      `tests/`, `scripts/` and `alembic/` since 2026-08-14, so a finding
      anywhere is one this pass introduced. This item used to say repo-wide
      was still red, which is the kind of stale number that talks people out
      of running the tools at all.
- [ ] Full suite no worse than the baseline you captured.

### Defects the 2026-08-09 pass added to this list

Each of these was invisible to the unit suite, and each cost a real defect.

- [ ] Permission codes are **upper snake case and seeded**. The guard test matched
      only `[A-Z0-9_]+`, so lowercase `sales_invoice:read` slipped past it and made
      an entire module platform-admin-only.
- [ ] Firm scope is resolved through `app/common/scope.py`, **never** on the
      request's tenant session — `firms`/`user_firms` live only in the platform
      schema **(found a real bug — every firm-owned router)**.
- [ ] A service that receives someone else's session **does not commit it**.
      `DocumentFrameworkService` committed in all 11 mutating methods, splitting
      every document write into several transactions. `TaxRuleService.simulate`
      did the same and was worse hidden: it reads like a preview, but all seven
      transactional modules call it once per line while building a document, so
      a commit there published a half-written invoice **(found a real bug
      twice — check every service another service calls)**.
- [ ] Cancelling a document **reverses whatever it posted**. Cancelling a completed
      goods receipt or purchase return left the stock movement in place.
- [ ] Sequence allocation **takes a row lock**, and a losing race returns 409, not 503.
- [ ] Rounding, financial-year labels and `subtotal` come from the shared helpers.
      Seven private copies disagreed three ways, including one using banker's rounding.
- [ ] **Generated values are asserted, not just their prefix.** Extracting the shared
      document base silently dropped the company code from purchase order numbers and
      nothing failed, because every test supplied its own number.
- [ ] Child rows are **reconciled on their natural key**, not deleted and re-inserted.
      Downstream documents reference line ids with no foreign key.
- [ ] Anything touching tenancy, cross-schema FKs, triggers or concurrency has an
      **integration test**; SQLite cannot express any of it.

### Defects the `firms` pass added to this list

- [ ] On a full-replacement `PUT`, an **optional field that is omitted inherits
      the stored value** — it does not fall back to the system default. Every
      tenancy field on `FirmUpdate` is optional, so renaming a firm rewrote its
      storage mapping to `SHARED` with a null schema and stranded everything the
      firm had written to its dedicated schema **(found a real bug)**.
- [ ] **Anything provisioned once is immutable afterwards.** Nothing migrates a
      firm's rows between stores and `provision_new_firm` runs only at creation,
      so accepting a routing change on update either abandons the data or aims
      the firm at a schema that was never built. Reject it in the service and
      mark the field `readOnlyWhenEditing` in the desktop form.
- [ ] **Two tenants can never be routed into one store.** The only uniqueness on
      `firm_storage_mappings` is one row per firm, so two firms could name the
      same schema and read each other's rows; soft-deleted firms count, because
      their data is still sitting in that schema.

### Defects the `tax` pass added to this list

- [ ] **A flag or action the engine records has to change an outcome.**
      `included_in_price` and the `REVERSE_CHARGE` action were both stored,
      returned in the response and read by nobody, so configuring either
      silently produced wrong money — an inclusive component was billed on top
      of the price it was already inside, and a reverse-charge sale still
      charged the customer the tax. Trace every declared flag to the line that
      acts on it, or the feature is decoration.
- [ ] **A scope filter must be satisfiable by the callers that actually exist.**
      Rules can be scoped by country and business profile, but no document sends
      a country and two of the seven send no profile, so country-scoped rules
      never fired and profile-scoped rules fired on five document types out of
      seven. Check what the real callers pass, not what the API accepts.
- [ ] **Grep for `quantize(` across the module.** An eighth private helper was
      still rounding tax half-to-even after the seven document copies were
      unified on `quantize_money`.

### Defects the `uom` pass added to this list

- [ ] **Never let NULL ordering decide which row wins.** Selecting the most
      specific conversion rule with `ORDER BY product_id DESC` relied on where
      the backend sorts NULLs: PostgreSQL puts them first, SQLite last, so the
      firm-wide fallback beat the product's own factor in production while the
      unit suite saw the right answer **(found a real bug)**. Rank on an
      explicit expression — `case((col.is_(None), 1), else_=0)` — and cover it
      with an integration test.
- [ ] **No model may declare a column named `version`.** That name is
      `BaseEntity`'s optimistic-concurrency counter and the mapper's
      `version_id_col`. `ConversionRule` used it for the rule's published
      version, so the ORM incremented the number documents record to identify
      the factor they converted with, and every edit invented a version that
      never existed **(found a real bug)**. Business versions are
      `version_number`.
- [ ] **Deleting shared reference data needs a usage guard.** The UOM catalogue
      has no `firm_id`, so in a SHARED deployment every firm in the store reads
      the same rows and an unguarded delete took a unit out from under another
      firm's products and rules. Check usage across the store, not just the
      caller's firm.
- [ ] A recorded setting that changes nothing recurred here: `rounding_mode` was
      stored per rule and the conversion always rounded half up.

### Defects the `search` pass added to this list

- [ ] **A platform admin is not exempt from the firm filter.** Global search
      skipped it for them entirely, so in a SHARED deployment -- one schema
      holding every firm's rows -- an admin with no firm selected got two
      firms' customers in a single list **(found a real bug)**. Where a firm
      column is nullable, null means the row belongs to the platform, not that
      the filter should be dropped.

### Defects the `batch_serial` pass added to this list

- [ ] **A status nobody transitions is not a state.** Expiry counts filtered on
      `status = 'EXPIRED'`, which nothing ever set -- the platform has no
      scheduler -- so the summary reported zero expired batches while the
      expiry card, reading the date, listed them, and the guard blocking
      purchases of expired stock never fired **(found a real bug)**. Derive the
      state from the fact that decides it.
- [ ] **Two numbers describing the same rows must be computed the same way.**
      One dashboard held both, disagreeing.

### Defects the `inventory` pass added to this list

- [ ] **A response builder is not reusable just because the rows look alike.**
      `ledger_response` passed a `StockLedgerEntry` to the builder for
      `InventoryTransaction`; the ledger names its as-entered columns
      `original_quantity`/`original_uom_id` and has no `conversion_version`, so
      the endpoint raised AttributeError as soon as one movement existed
      **(found a real bug)**. mypy had been reporting it the whole time.
- [ ] **Read every endpoint back at least once in a test.** The write path was
      correct and covered; nothing had ever listed the rows it wrote.
- [ ] **Fixtures must use the module's whole vocabulary.** Repairing the ledger
      response uncovered a second failure underneath it only when the app was
      run against seeded data: the response validated `transaction_type`
      against a closed enum while the service writes RESERVE, UNRESERVE and
      DISPATCH, and `reverse_transaction` writes `"<TYPE>_REVERSAL"`, which no
      enum can enumerate. An adjustment-only fixture passed throughout
      **(found a real bug, by running the app)**. An immutable historical
      record carries the vocabulary it was written with; keep the enum for
      filters, where a closed set is what a caller should be held to.

### Defects the `branches` pass added to this list

- [ ] **Bulk endpoints audit every row they touch.** All six of them wrote
      nothing, so deleting fifty branches from the toolbar left a trail showing
      none of it while deleting one from the row menu was recorded
      **(found a real bug)**. Check the bulk path separately: it is usually a
      second implementation of the single-row one, and it drifts.
- [ ] **A bulk endpoint enforces the same rules as its single-row twin.** The
      guards, not just the audit, have to be in both.
- [ ] **Deleting a parent checks its children.** A branch could be soft deleted
      with live warehouses still trading under it, and a warehouse with stock
      still in it, while the module already refused to delete a storage node
      with children **(found a real bug)**.
- [ ] **An exclusivity flag needs an owner.** `is_default` was accepted on write
      and maintained by nothing, so every branch in a firm could claim it. Demote
      the incumbent in the service and back it with a partial unique index, as
      `UQ_user_firms_active_primary` does. Flush the demotion before writing the
      promoted row or the index rejects the statement.

- [ ] **Two resolvers give two answers.** `product_service` resolved a firm's
      features through a private query filtering neither `is_active` nor
      `is_deleted`, so deactivating BARCODE in the catalogue left barcodes
      accepted on products while every `require_feature` endpoint correctly
      refused **(found a real bug)**. Same shape as the bulk endpoints that
      skipped their single-row twins' guards. Route every caller through
      `app/business/gating.py`.
- [ ] **Gate the capability, not the record.** A feature that owns a resource
      gates the endpoint; a feature that is one optional field on a shared
      resource must gate the field, or a firm loses the whole resource because
      it does not use one column of it.

### Defects the tax gate-clearing pass added to this list

- [ ] **Verify a claim against the whole target, not the parts you happened to
      touch.** "Every module is clean" was written after re-measuring five
      modules; `tax` still had 184 ruff findings and 14 mypy errors, and the
      inventory table had recorded 0/0 for it since 2026-08-09. Run the tool
      against `app/` entire before saying so.
- [ ] **`.any()` takes one criterion.** `TaxRule.conditions.any(a, b, c)` is a
      TypeError at runtime, so `GET /tax-framework/rules?transaction_type=` was
      a 500 for every caller **(found a real bug)**. mypy reported it as "too
      many arguments for any of PropComparator" and nobody was reading the
      output. Combine with `and_()`.
- [ ] **An unreachable `else` after an exhaustive enum chain is dead, not
      defensive.** Default the variable before the chain instead: the branch
      then actually runs if a member is added later, rather than raising
      UnboundLocalError or being silently removed.
- [ ] **`Any` on a helper parameter is usually a missing type, not a
      requirement.** Most of `tax`'s were `row: Any` where `BaseEntity` was
      meant, or `value: Any` where `object` was. Reserve the `noqa` for the
      handful that genuinely accept any mapped class, and say why on the line.

### Open: three features deliberately left ungated

Feature gating landed for nine of the twelve features that have backing code.
The remaining three are **not** oversights — each needs a product decision that
the code cannot supply, and gating one on a guess would take a working
capability away from real firms.

- **`TERRITORY`** — only AGENCY and WHOLESALE enable it. Enforcing it would
  remove territory and route management from the other nine profiles, including
  PHARMACY, FOOD and RETAIL, all of which plausibly sell by territory on a
  distribution platform. The seed assignment looks wrong, not the code. Decide
  whether territory is core to every selling firm (in which case it should not
  be a switch), or genuinely optional (in which case the profiles that need it
  must be granted it first). Raised 2026-08-10; parked for more product
  knowledge.
- **`MULTIPLE_WAREHOUSES`** — needs two answers before it can be written: does
  disabling it refuse a *second* warehouse, and what happens to a firm that
  already has several when it is turned on? The framework's rule is that
  enabling enforcement never takes away what a firm already has, which argues
  for blocking new ones only, but that is a decision not a deduction.
- **`APPROVAL_WORKFLOW`** — the document framework has approval states, but
  what "no approval workflow" means is undecided: documents skip straight to
  approved, or the approve action is simply unavailable, or approval is
  self-service. Different answers, different code.

Do not gate any of these to close the gap. An unenforced feature is visible
debt; a wrongly enforced one silently removes a capability a firm was using.

### Defects the feature-catalogue survey added to this list

- [ ] **A declared capability with no implementation is a promise you cannot
      keep.** Seven of the twenty-one framework features had no backing code in
      either application, and seven industry profiles had them switched on — a
      pharmacy profile advertised `PRESCRIPTION_REQUIRED`, a restaurant profile
      advertised `KITCHEN_MANAGEMENT`, and neither did anything
      **(found a real bug)**. Before gating a feature, check something
      implements it. Same defect as the eleven docstring-only packages deleted
      on 2026-08-09, and worse: a catalogue is customer-facing.
- [ ] **"Not built" is not "switched off".** `is_active` is an administrator's
      choice; whether code exists is a fact. Keep them in separate columns, or
      an administrator can "activate" something that cannot run.
- [ ] **Check which store a table actually lives in before writing its
      migration.** The framework catalogue is firm-owned and has no row in
      `platform`, the opposite of what its name suggests. A platform-only
      migration would have silently done nothing.

### Defects the import pass added to this list

- [ ] **A batch endpoint that loops over a committing method is not a batch.**
      `import_branches` and `import_warehouses` called `create_branch` /
      `create_warehouse` per record, and both commit. A file whose fifth row
      clashed returned 409 with the first four already written, and re-sending
      the corrected file then failed on those four as duplicates — so the
      import could never be completed **(found a real bug)**. Stage every
      record, commit once, roll back on failure. Check that the staged path
      still writes the audit rows the single-row path does.
- [ ] **Say whether a failed write left anything behind.** After a refused
      import the user's first question is whether half of it went in. If the
      endpoint is atomic, the UI should say so in the error.
- [ ] **A dialog whose content grows with the data needs a scroll view.** The
      import dialog laid out fine empty and overflowed by 48px once a file was
      loaded; the widget test caught it because a render overflow fails a test,
      which is the argument for testing the populated state and not just the
      empty one.

### Defects the time-convention pass added to this list

- [ ] **Never read the server's local clock.** Everything persisted here is
      UTC, so `date.today()` compares against a date the data does not use: on
      a non-UTC deployment it is already tomorrow, or still yesterday, for part
      of every day. This shipped three separate times — `uom` picked a
      conversion rule that was not yet effective, `batch_serial` bucketed
      expiry a day out, and the overdue reports plus document numbering carried
      it until 2026-08-10 **(found real bugs)**. Call `utc_now().date()`.
      `tests/unit/test_time_conventions.py` now fails the build on any new
      occurrence, so this should not need a fourth fix.
- [ ] **`func.now()` is not a local clock.** It is SQL evaluated by the
      database and is the correct default for a timestamp column. The first
      version of the guard above flagged all four uses of it — check what
      evaluates an expression before calling it a defect.

### Defects the `finance` pass added to this list

- [ ] **Validate the values you are about to store, not the ones you were
      handed.** The journal engine summed the raw legs, rounded the two totals,
      and compared those — then stored each leg rounded individually. Sum-then-
      round and round-then-sum are different operations, so a document that
      balanced exactly at its own four decimals could be written as lines a cent
      apart with `is_balanced` set to true, and the general ledger copies line
      amounts verbatim **(found a real bug)**. Wherever a value is rounded on
      the way into storage, do the rounding first and check afterwards.
- [ ] **A caller that feeds a coarser store must derive the balancing figure,
      not round every component.** Rounding taxable, tax and total
      independently can leave them a cent apart. Derive one leg from the others
      at the destination's scale so the set agrees by construction.
- [ ] **A report's date column is the business date, not the wall clock.** The
      ledger statement dated and ordered its lines by `posting_date`, the moment
      someone pressed Post, so a back-dated entry appeared under today and the
      running balance ran in the order of clicks rather than of trade
      **(found a real bug)**. Keep the timestamp for the audit trail and report
      the document's own date.
- [ ] **Do not fall back through a field nothing writes.** The statement showed
      `posting.error_message or entry.description`; `error_message` is never
      assigned, so the branch was dead — and the line's own narration, captured
      on every posting, was never displayed. Same shape as a status nobody
      transitions.
- [ ] **Never assign to `version` by hand.** It is the mapper's version id;
      SQLAlchemy computes the next value and overwrites the assignment, so
      `row.version += 1` is dead code that reads as load-bearing concurrency
      control. Eight of them were in `finance`.

### Defects the 2026-08-15 pass added to this list

Both were in `customers`, which this checklist had already recorded as reviewed
with no findings. Neither was reachable by reading the code or by running the
suite; both fell out of driving the endpoint over HTTP against seeded data.

- [ ] **A derived balance is never recomputed from an input on update.**
      `CustomerService.update` recomputed `current_outstanding` from
      `opening_balance` on every call, so editing a phone number discarded every
      invoice, receipt and credit note the customer had **(found a real bug —
      one edit put a store 59,901.23 out)**. Ask of every denormalised total:
      what writes it, and does this path have the right to.
- [ ] **A bulk `delete()`/`update()` must not follow ORM changes to the same
      rows.** `synchronize_session=False` leaves the session's dirty objects
      pending, so their statement fires against rows that are already gone and
      raises `StaleDataError` — surfaced to the caller as 409 "this record
      changed since you loaded it" on an edit nobody was racing **(found a real
      bug)**. Delete through the ORM, or expire the objects first.
- [ ] **Test the service on a session shaped like a request's.** Fixtures build
      sessions with SQLAlchemy's default autoflush; `app/core/database/engine.py`
      passes `autoflush=False`. Autoflush writes a pending statement while the
      row still exists and repairs an ordering mistake by accident, so the
      defect above could only exist in production. Use
      `_request_like_session_factory` (`tests/unit/test_customer_management.py`)
      wherever a service mixes ORM mutation with bulk statements.
- [ ] **A precondition nobody can satisfy is not a feature.** Five routers
      accepted `If-Match` while no response published the version, so the only
      honest value was `*` — no precondition. If an endpoint takes a
      precondition, something must return the value it takes.
- [ ] **Run `scripts/verify_sample_data.py` after driving writes**, not only
      after seeding. It caught both of these within minutes, and it names the
      symptom precisely: "a balance moved without a journal".

### Defects the 2026-08-21 cross-cutting passes added to this list

Eight PRs (#109–#116) over two days, none of them a single-module review. What
they have in common is that each defect lived in the space *between* modules —
a second copy of a resolver, a rule written down and unenforced, a screen that
could not read what the server had been recording.

- [ ] **One question, one resolver.** Five modules each carried a private copy
      of "which business profile does this firm operate under", and they did not
      agree: `tax` and `sales` answered None for an unassigned firm where the
      gate answered the platform default, so every profile-scoped tax rule
      skipped that firm and its territories were filed under no industry at all
      **(found a real bug)**. Before writing a lookup, grep for one.
- [ ] **A second copy drifts in more than one way at once.**
      `InventoryService` kept its own conversion-rule resolver, and it matched a
      line's stored *revision* against the *concurrency counter* — agreeing only
      until somebody edited a rule — **and** ordered by `product_id DESC`, the
      NULL-ordering defect fixed in `uom` a fortnight earlier and never carried
      across **(found a real bug — twice in twelve lines)**.
- [ ] **A name that means two things blocks the fix for both.** `uom` exposed a
      conversion rule's published revision as `version`, which is the one name
      the concurrency counter needs, so the module could not be given
      `If-Match` at all. Renaming the revision to `version_number` — the column's
      name, and how `tax` always spelled it — unblocked it and surfaced the
      inventory defect above.
- [ ] **A rule in `CLAUDE.md` is not a rule until something checks it.** The
      `page_size` bound had been written down for months while 44 handlers
      ignored it. What turned it into a defect with a count was a screen that
      could read the crash log.
- [ ] **Telemetry nobody can read is telemetry nobody acts on.** The desktop had
      queued crash reports to disk and flushed them to the server since the
      crash reporter was written, and nothing could read one back. The first run
      of the triage screen surfaced 28 live 500s.
- [ ] **A save that changes nothing does not move the version.** A second save
      carrying the same `If-Match` is therefore accepted — correct, since the
      record did not change, and the reason a concurrency probe has to change
      something to see the refusal. The first pass of one here did not, and read
      as a broken precondition.

## Module inventory

**Endpoint counts re-measured 2026-08-15** by counting route decorators under
each package, which is why several moved: the 2026-08-09 figures predate five
modules and a good deal of growth in the ones already listed. `ruff` and `mypy`
are zero for every module because the whole tree is clean, and the columns are
kept so a regression has somewhere to show.

Counting note: `settlements` declares three routers (`receipts_router`,
`payments_router`, `refunds_router`) rather than one `router`, so a count keyed
on `@router.` misses it entirely. That is how it stayed off this table.

| Module | Endpoints | ruff | mypy | Unit test | Desktop |
| --- | ---: | ---: | ---: | --- | --- |
| `finance` | 33 | 0 | 0 | `test_finance_module` | full — chart, trial balance, journals, ledgers, P&L, balance sheet |
| `common` (audit) | 1 | 0 | 0 | `test_audit_trail_api` | **none** |
| `identity` | 29 | 0 | 2 | `test_identity_service`, `test_identity_hardening` | typed |
| `firms` | 6 | 0 | 0 | `test_firms_module` | typed |
| `document_framework` | 15 | 0 | 0 | `test_document_framework` | widgets only |
| `business` | 28 | 0 | 0 | `test_business_profile_framework`, `test_business_profile_gating` | typed |
| `sales` (territory) | 63 | 0 | 0 | eight files, 84 tests — see `docs/TERRITORY_FRAMEWORK.md` | typed |
| `customers` | 17 | 0 | 0 | `test_customer_management` | typed |
| `products` | 17 | 0 | 0 | `test_product_master` | typed |
| `search` | 1 | 0 | 0 | `test_global_search` | typed |
| `vendors` | 23 | 0 | 0 | `test_vendor_management`, `test_vendor_collections_survive_an_edit` | typed — all six tabs are forms as of 2026-08-21, except attachments |
| `purchase` | 12 | 0 | 0 | `test_purchase_management` | typed |
| `batch_serial` | 17 | 0 | 0 | `test_batch_serial_expiry` | typed |
| `goods_receipt` | 16 | 0 | 0 | `test_goods_receipt` | typed |
| `inventory` | 29 | 0 | 0 | `test_inventory_foundation`, `test_inventory_transaction_vocabulary` | typed |
| `branches` | 39 | 0 | 0 | `test_branch_warehouse_management`, `test_branch_warehouse_partial_update` | typed |
| `uom` | 28 | 0 | 0 | `test_uom_packaging_framework` | typed |
| `sales_order` | 17 | 0 | 0 | `test_sales_order_module` | typed |
| `sales_invoice` | 16 | 0 | 0 | `test_sales_invoice_module` | typed |
| `purchase_invoice` | 16 | 0 | 0 | `test_purchase_invoice_module` | typed |
| `delivery_note` | 19 | 0 | 0 | `test_delivery_note_module` | typed |
| `purchase_return` | 18 | 0 | 0 | `test_purchase_return_module` | typed |
| `tax` | 52 | 0 | 0 | `test_tax_framework` | typed |
| `sales_return` | 15 | 0 | 0 | `test_sales_return_module` | typed |
| `quotation` | 14 | 0 | 0 | `test_quotation_module` | typed |
| `settlements` | 12 | 0 | 0 | `test_settlements` | typed — receipts, payments, refunds |
| `diagnostics` | 3 | 0 | 0 | `test_diagnostics_module` | triage screen — Settings › Diagnostics (2026-08-21) |

As of 2026-08-10 no page holds an endpoint path: `grep -rn "'/api/v1/" lib/`
matches only `api_client.dart`. The five document workspaces share
`documentSummary`/`documentPage`/`documentHistory`/`documentAction`, and the tax
screens use the typed client that already existed — they had simply never been
wired to it.

## Suggested order

**Every module in the ordering below has been reviewed** — the progress table
records passes 0 through 21, finishing on 2026-08-10. The list it replaced
ranked modules by lint and type debt, which is no longer a way to tell them
apart: the tree has been clean under all four tools since 2026-08-14, so the
numbers that used to sort this list are now zero everywhere.

What is left is the four modules built **after** the review passes ended, none
of which has had one:

**1. `settlements` (12 endpoints)** — **reviewed 2026-08-18**, row 23 below.
It found nothing, which is recorded there along with what was actually driven.

**2. `sales_return` (15)** — moves three books at once (stock, the customer's
account, the ledger) and any of them failing must fail the whole document.
Check the cancel path against the checklist item "cancelling a document
reverses whatever it posted", which is exactly where its known valuation leak
was.

**3. `quotation` (14)** — the opposite risk: it is defined by what it does
**not** do. A review should assert the negative — no reservation, no balance
movement, no journal — and check that expiry stays derived from `valid_until`
rather than acquiring a stored flag.

**4. `diagnostics` (3)** — **reviewed 2026-08-22**, row 32. Two findings, both
in seams a module-only review would have missed.

**Every module on this board has now had a pass, and the nine oldest have had
two** (row 33). What is worth doing next is not another sweep of the same kind:

- **Re-seed the demo stores.** Two of three fail `verify_sample_data.py` on
  legacy drift the code no longer produces, and a failing verifier is how a real
  break goes unnoticed.
- **Chase the 38.46 the second pass could not attribute** in `wholesale_hub`, or
  satisfy yourself it is valuation rounding.
- **The modules with no review at all are gone**, so the next first pass is for
  whatever gets built next -- and this checklist is the thing to run against it.

Then a second pass over anything the four PRs of 2026-08-15 touched, since two
defects in `customers` survived its 2026-08-10 review: that pass found nothing
because both were only reachable by driving `PUT /customers/{id}` over HTTP,
which nothing did until the endpoint published an ETag.

## Progress

| # | Module | Reviewed | Findings | Fixed |
| --- | --- | --- | --- | --- |
| 0 | platform (`identity`, `firms`, security, RBAC) | 2026-08-09 | 6 real, 2 retracted | yes |
| 0b | `business` (profile framework) | 2026-08-09 | gating was client-side only; 18/21 features unenforced; profile data empty for every industry but GENERIC | mechanism + seed done; per-module gating outstanding |
| 0c | **all firm-owned routers** (tenancy) | 2026-08-09 | every one resolved `firms`/`user_firms` on the tenant session, so all firm-owned endpoints failed on PostgreSQL outside the platform schema | yes — shared `app/common/scope.py` |
| 0d | **persistence conventions** | 2026-08-09 | FK naming collided on two FKs to one target, so `create_all` could not build the schema on PostgreSQL; `BaseEntity.version` never read or incremented | yes |
| 1 | `sales_invoice` | 2026-08-09 | permission codes unseeded (whole API admin-only); every handler mis-called its service; the six tables never matched the ORM | yes — module now has a test |
| 2 | `goods_receipt` | 2026-08-09 | cancel left stock posted; totals computed twice with different formulas; lines re-inserted on edit | yes — `test_goods_receipt` added 2026-08-10 to pin the fixes |
| 3 | `firms` | 2026-08-09 | soft delete burned the code, GST and PAN forever; a `PUT` omitting the optional tenancy fields re-pointed a dedicated firm at the shared schema; two firms could be routed into one schema; update carried no `after_data` and no `If-Match` | yes — module now has a test |
| 4 | `purchase_invoice` | 2026-08-09 | `subtotal` folded in line charges; committed mid-write; `_flush_or_conflict` left the session unusable | yes |
| 5 | `purchase_return` | 2026-08-09 | cancel left stock posted and its movements were unlinkable; `subtotal` folded in line charges | yes |
| 6 | `delivery_note` | 2026-08-09 | lines re-inserted on edit, dangling downstream references | yes |
| 7 | `sales_order` | 2026-08-09 | lines re-inserted on edit, resetting `reserved_quantity` while the RESERVE movement stayed in the ledger | yes |
| 8 | `tax` | 2026-08-09 | `simulate` committed the caller's session while every document computed tax line by line; an eighth private rounding helper still used banker's rounding; country-scoped rules never matched a document and profile-scoped ones matched five of seven; `included_in_price` was billed on top of the price; `REVERSE_CHARGE` changed nothing; the execution log had no purge path | yes — desktop endpoints still inlined |
| 9 | `uom` | 2026-08-09 | a product's own conversion factor lost to the firm-wide one on PostgreSQL only; the rule's published version was the same column as the concurrency counter, so any edit moved it; the configured `rounding_mode` was ignored; a unit in use could be deleted out from under other firms | yes — module is now clean under ruff, black and mypy |
| 10 | `branches` | 2026-08-10 | the six bulk endpoints wrote no audit entries at all; a branch could be deleted with live warehouses under it and a warehouse deleted with stock in it; `is_default` was maintained by nothing, so every branch could be the firm default | yes — module is now clean under ruff, black and mypy |
| 11 | `inventory` | 2026-08-10 | `GET /inventory/ledger` raised AttributeError for every firm that had ever moved stock, because the ledger row was fed to the transaction response builder | yes — module is now clean under ruff, black and mypy |
| 12 | `batch_serial` | 2026-08-10 | expiry counts keyed on a `status` nothing ever sets, so the summary reported zero expired batches while the expiry card listed them; the guard blocking purchases of expired stock never fired for the same reason; expiry windows used the server's local date | yes — module is now clean under ruff, black and mypy |
| 13 | `customers` | 2026-08-10, **re-opened 2026-08-15** | The 2026-08-10 pass reported none and said receivable arithmetic held. **It did not.** `update` recomputed the balances from `opening_balance` on every call, so editing any field discarded everything the customer had traded; and it collided with its own opening-balance reversal, answering 409 to an edit nobody was racing. Both were invisible to a read-through and to the unit suite — see the note below | credit control shipped 2026-08-10; both balance defects fixed 2026-08-15 |
| 14 | `products` | 2026-08-10 | bulk delete and restore wrote no audit entries, the same gap found in `branches`; deleting a category was unaudited too | yes |
| 15 | `vendors` | 2026-08-10 | all five bulk endpoints wrote no audit entries — the third module with this gap | yes — module is now clean under ruff, black and mypy |
| 16 | `purchase` | 2026-08-10 | a purchase order with goods receipts against it could be deleted, though cancelling the same order was refused; a CSV import helper closed over its loop variable | yes — module is now clean under ruff, black and mypy |
| 17 | `business` | 2026-08-10 | deleting a feature or module a profile still enabled silently revoked the capability for every firm on that profile, so `require_feature` began rejecting writes those firms made the day before | yes |
| 18 | `sales` (territory) | 2026-08-10 | bulk status changes and moves wrote one summary audit row keyed on the first id, so the trail recorded that N territories changed without naming any of them | yes |
| 19 | `search` | 2026-08-10 | the firm filter was skipped entirely for platform admins, so an admin with no firm selected saw every firm's rows in one result list — in a SHARED store that is one schema holding all of them | yes |
| 20 | `document_framework` | 2026-08-10 | none — the commit-per-method defect was fixed in the 2026-08-09 pass and lifecycle, numbering and timeline events all hold | gates only |
| 21 | `finance` | 2026-08-10 | the journal engine checked the balance on the summed-then-rounded totals but stored each leg rounded, so a document balanced at four decimals could store lines a cent apart with `is_balanced` true — and `_post_line` copies line amounts straight into the general ledger; the ledger statement was dated and ordered by the wall clock at posting rather than the journal date; line narration was collected and never displayed, the report preferring a field nothing writes | yes — no stored data was affected |
| 22 | `sales` (territory) | 2026-08-16 | the whole reporting chain was unfed — `territory_id`/`route_id`/`salesman_id` were never populated, so three reports answered `[]` from correct endpoints; six geography reads carried no principal at all and served data to an unauthenticated caller; nineteen handlers took the bare `ResolvedFirmScope`, which FastAPI read as a **request body field**, so every geography write and `PUT /hierarchy-levels` was uncallable; two bulk assignments committed per item, so a batch refused partway left the earlier rows written; `effective_from`/`effective_to` were stored and read nowhere | yes — plus four migrations and `docs/TERRITORY_FRAMEWORK.md` |
| 23 | `settlements` | 2026-08-18 | **none** — the first module review to find nothing. Every refusal it needs already fires, and each was driven rather than read: over-allocating an invoice, allocating more than the money that moved, the same invoice twice, another party's invoice, a zero or negative amount, a refund applied to a document, and a receipt against a vendor id. Reversal restores the invoice **and** the customer balance to the exact figures they held, and a second reversal is refused. Two concurrent settlements against one invoice end 201/409 in both directions and with a client-supplied number, so the invoice cannot be over-settled. ELEC01 could not read, list or settle anything of WHOLE01's, and its token with WHOLE01's firm header answered 403 | nothing to fix — two observations recorded below |
| 24 | **business profile resolution** (`tax`, `sales`, `products`, `inventory`, `uom`) | 2026-08-21 | five private copies of one resolver, and they disagreed: `tax` and `sales` answered None for an unassigned firm where the gate answered the platform default, so every profile-scoped tax rule skipped that firm and its hierarchy, nodes and beat plans recorded no industry at all. `products` and `inventory` fell back correctly but each demanded `status = 'ACTIVE'` on the *assigned* profile, so a deactivated profile put GENERIC's fields on the form while the gate went on enforcing the assigned one | yes — #109, #110, plus `20260821_0095` to fill the NULLs and a guard that all four resolvers answer alike |
| 25 | **`diagnostics` surface** | 2026-08-21 | the module had no desktop screen at all, so crash reports had been collected for months with no way to read one. Not a defect in the module — a hole in the product | yes — #111, Settings › Diagnostics, faults collapsed by fingerprint |
| 26 | **pagination bounds** (all 23 routers) | 2026-08-21 | 44 handlers took a bare `page_size: int = 20` and built `PaginationParams` in the body, so an over-cap request answered **500** instead of a 422 naming the limit; `page: int = 1` had the same shape, so `page=0` was a 500 too. The rule had been in `CLAUDE.md` for months. The new triage screen is what turned it into a defect with a count: 28 stored `ValidationError`s over three days -- **from four endpoints**, `warehouses` 12, `assignable-customers` 10, `attribute-definitions` 5 and `products` 1, which the 2026-08-22 `diagnostics` review had to correct because the grouping made them look like one | yes — #112, plus `tests/unit/test_pagination_conventions.py` |
| 27 | **optimistic concurrency** (`uom`, `tax`, `batch_serial`, `inventory`, `sales`, `business`) | 2026-08-22 | six modules were still last-one-wins. `uom` was blocked by a name: a conversion rule's published revision was exposed as `version`, which the counter needs. Renaming it to `version_number` unblocked the wiring and surfaced `InventoryService`'s private copy of the rule resolver matching a line's revision against the counter — and ordering by `product_id DESC`, the NULL-ordering defect fixed in `uom` and never carried across | yes — #115, #116; 31 updates across the six (uom 6, tax 6, sales 9, business 5, batch_serial 3, inventory 2), taking the platform to 42 endpoints accepting the header, and `publish_version` covers the services that return response models rather than rows |
| 28 | **partial updates** (`business`, `document_framework`) | 2026-08-21 | the last eight full-dump updates. `update_profile` was the worst: it read `is_default` off the model, so renaming the default profile demoted it and left the store with no default — and a store with no default enforces nothing, so one rename would have switched off business-profile gating for every unassigned firm | yes — #114 |
| 29 | **`vendors` editor** | 2026-08-21 | four of the six tabs described a capability in prose and offered no field: contacts, banking, tax and notes round-tripped through the API and could only be filled by import. The model dropped three of the four collections on the way in | yes — #113 |
| 30–32 | `sales_return`, `quotation`, `diagnostics` | 2026-08-22 | see the prose section below — all three driven rather than read, and two of the three findings could only have been found that way | yes |
| 33 | **second pass** over the nine modules reviewed 2026-08-09 | 2026-08-22 | one finding, in the data rather than the code | yes |
| 34–35 | **the cancel paths** (`goods_receipt`, `purchase_return`, `sales_return`, `delivery_note`) | 2026-08-22 | a cancelled receipt credited inventory with a number no movement removed, putting a seeded store 2,287.42 out in one request; two siblings carried the same shape | yes |
| 37 | **every ledger posting**, against one rule | 2026-08-22 | a leg facing stock is valued from the movement; all three reversals broke it | yes |
| 38 | `promotions` | 2026-09-03 | **three findings, one root cause: a promotion's identity is its `version_group_id`, and three checks used the row id.** Editing a published coupon-gated offer silently orphaned every code in circulation (109.00 → 10.00 on a driven line); its redemption caps reset to zero on the same edit, so an exhausted campaign became fully available again; and retiring an offer left its codes ACTIVE in the list, naming a retired offer and giving nothing | yes |
| 39 | `loyalty` | 2026-09-03 | **two findings in the expiry sweep.** It wrote back the whole earned batch without asking how much of it was still there, so a batch the customer had already spent lapsed a second time and left them holding **negative points** -- the balance is a sum with no floor and redeeming is refused above it, so the sweep was the only way below zero. And nothing released the liability the points raised, so `Loyalty Payable` kept a debt no customer could ever claim: measured at **936.31** across nine lapsed batches in WHOLE01, against 49 earnings that had all posted | yes |
| 40 | `commission` | 2026-09-03 | **one finding, and it is a race.** `_assert_period_is_free` reads and `accrue` writes with nothing between them and no constraint behind them, so two requests that both check before either commits both pass -- driven on WHOLE01, leaving one salesman holding two live payouts for one month, which pays the same collections twice. Everything else the module claims was checked and holds | yes |

### 23 `settlements` — what was checked, and the two things worth knowing

Reviewed 2026-08-18. Chosen because it is the module handling every rupee in
and out and the only one the table had never covered, and because the two days
before it produced two real ledger defects in neighbouring code — both found by
driving endpoints, neither visible to the unit suite.

It found nothing. That is a result rather than an absence of effort, so here is
what was actually exercised, all of it against a running backend on the seeded
`WHOLE01` firm:

- **Every refusal fires.** Allocating more than the invoice owes, more than the
  money that moved, the same invoice twice (a schema-level
  `_one_row_per_invoice` validator), another party's invoice, a zero or
  negative amount, a refund applied to a document, and a receipt naming a
  vendor. Each answered 422 or 404 with a message naming the actual rule.
- **A part settlement moves both books.** The invoice went 5,841.00 → 2,920.50
  and the customer's outstanding 59,901.23 → 56,980.73, with
  `journal_entry_id` set.
- **Reversal is exact.** Both figures returned to 5,841.00 and 59,901.23, the
  mirror journal was linked, the allocation rows stayed (so the reversed
  settlement still shows what it had cleared), and a second reversal was
  refused by name.
- **Firm isolation holds.** ELEC01 reading WHOLE01's customer's outstanding got
  200 with zero rows rather than a leak; settling that invoice got 404; listing
  receipts got its own store; and ELEC01's token with WHOLE01's `X-Firm-ID`
  answered 403.

Two observations, neither a defect:

- **The concurrency protection is incidental, not declared.** Two receipts
  racing for one invoice end 201/409, and so do two payments — including when
  the caller supplies its own `settlement_number`, which skips number
  reservation. Nothing in `_validate_allocations` locks the invoice: it reads
  the outstanding and writes, and what actually serialises the pair is a
  version collision on a row further down (`_ensure_document_setup`, and the
  customer row on the receipt side). It holds today. It is worth knowing that
  no code says so, because a change that stops touching those rows would open
  the race silently, and the symptom would be an over-settled invoice rather
  than an error.
- **The party parameter is named three ways.** The create body takes
  `party_id`; `GET /receipts/outstanding` takes `customer_id` and
  `GET /payments/outstanding` takes `vendor_id`. Each is defensible on its own
  endpoint and the pair cost a wrong call while probing. Left alone — renaming
  a query parameter breaks clients for tidiness.

Not covered, and deliberately: `RefundService` beyond its refusal to allocate,
because the rule that a refund cannot exceed the advance a customer holds lives
in `CustomerService` and belongs to that module's review.
| 30 | `sales_return` | 2026-08-22 | **one** — cancelling a completed return put the customer's balance back by recomputing from the return's total instead of reversing what the credit note actually did. A credit note is applied up to what the customer owes and the rest becomes an unapplied advance; cancelling posted a fresh INVOICE for the whole amount, so the customer owed more than before the return and held an advance no money paid for. Net exposure (`outstanding - advance`) came out right, which is why it went unseen — the two figures were individually wrong and cancelled out, while an aging report reads `outstanding` alone and an advance can be applied to a real invoice. Stock and both journals were already reversed correctly | yes — `_reverse_receivable` uses `reverse_receivable_transaction`, the way `settlements` always has |
| 31 | `quotation` | 2026-08-22 | **none.** The negatives were asserted against a running backend rather than read: creating, sending, accepting and converting a quotation left the customer's outstanding, the unapplied advance, every reserved and on-hand quantity and the journal count **identical**. Conversion builds the order through `SalesOrderService.create_order`, so credit control, tax at the order's date and numbering all happen on the order; a second conversion is refused by name ("already became SO-2026-2027-000013"). Expiry stays derived from `valid_until` — an expired quotation cannot be accepted or converted, and nothing writes an EXPIRED status | nothing to fix |
| 32 | `diagnostics` | 2026-08-22 | **two, both in the part that had no test.** (1) Every server-recorded fault carried a NULL request id — 28 of 28 — so the screenshot-to-traceback join the module exists for could never be made: the handler read a context variable that `CoreRequestMiddleware` has already reset, because a bare-`Exception` handler is served by `ServerErrorMiddleware` from outside it. (2) Server faults grouped by exception type alone: the fingerprint hashed the **first** five frames, which are always the ASGI plumbing, so 28 `ValidationError`s from **four** endpoints shared one identity and the screen showed whichever context came first | yes — `request_id_for` reads `request.state`, and the fingerprint takes this codebase's frames nearest the raise; both proven on the four stored tracebacks |
| 33 | **second pass** over the nine modules first reviewed 2026-08-09 (`sales_invoice`, `goods_receipt`, `firms`, `purchase_invoice`, `purchase_return`, `delivery_note`, `sales_order`, `tax`, `uom`) | 2026-08-22 | **one, and it is data rather than code.** Two of the three stores fail the stock-versus-ledger invariant, and the drift is exactly the stock value backed out by goods-receipt reversals whose journal was never mirrored: `firm_shared` out by 52,582.436 against 52,582.437 of such reversals, `wholesale_hub` out by 3,971.21 with 4,009.67 attributable and 38.46 left over. Every one of those cancellations happened on 2026-08-18 -- the day the fix landed -- and the only one carrying a mirror is the last. The code is right; nobody backfilled what the defect had already written. Nothing else moved: every period balances, customers match the receivable account, settlements all reached the ledger, approved invoices all posted, no stock row is negative or fails `available = current - reserved - blocked`, and nothing is left reserved in any store | the verifier now names this cause when the arithmetic agrees; the demo data itself wants a re-seed |
| 34 | **cancel paths**, driven on freshly seeded data (`goods_receipt`, `delivery_note`, `sales_invoice`, `purchase_invoice`, `sales_order`, `sales_return`) | 2026-08-22 | **one, and it is live.** Cancelling a completed goods receipt reverses the journal at the price the goods came in at and the stock at today's moving average, so the two disagree by whatever the average has moved since. Measured on ELEC01: a receipt of 60 units at 134.00 posted 8,040.00; cancelling mirrored the full 8,040.00 out of the inventory account while the stock reversal removed 60 × 95.876591 = 5,752.60, leaving the store out by 2,287.42 -- from balanced to broken in one request. Every other cancel path held: the receipt and delivery-note refusals fire for stated reasons, and the sales-invoice, purchase-invoice and sales-order cancels each left all five checks passing | yes -- the reversal now credits inventory with what the movement removed and books the gap to `PURCHASE_PRICE_VARIANCE`, the account `post_purchase_return` already uses for the same reason. Driven on ELEC01: the sequence that put it 2,287.42 out leaves all five checks passing, and the entry reads Dr goods received not invoiced 12,000.00 / Cr inventory 11,943.90 / Cr variance 56.10 against a movement of 11,943.8959 |
| 35 | **cancel paths, the three the first sweep could not reach** (`purchase_return`, `sales_return` with real money, `delivery_note`) | 2026-08-22 | **one, the mirror of a defect fixed four days earlier.** Cancelling a completed purchase return reversed the stock and never touched the ledger -- no `reverse_entry`, no stored entry id, nothing -- so the payable, the input tax and the inventory credit all stayed on the books while the goods went back on the shelf. `goods_receipt` carried exactly this until 2026-08-18; nobody looked at its mirror. One cancellation put ELEC01 199.07 out. `sales_return` came back clean on a 212.40 return -- the customer moved 133,220.55 → 133,008.15 and back to the penny -- and no delivery note in seeded data is cancellable at all: every one is DISPATCHED, which is deliberately terminal | yes -- `reverse_purchase_return` mirrors the payable and tax legs and debits inventory with what the movement put back, difference to variance |
| 36 | **the response envelope**, all 23 routers | 2026-08-22 | seven `sales_invoice` endpoints answered with the bare model rather than `ApiResponse` -- create, get, update, approve, cancel, close and import -- so they carried no `success`, no `timestamp` and no `requestId`, and a client reading `body["data"]` got nothing. Invisible from the desktop, which unwraps with a fallback to the raw body, and found only when a probe script raised `KeyError: 'data'`. The reports in the same module had the same break and were fixed on 2026-08-14; the lifecycle endpoints beside them were not looked at | yes -- all seven wrapped, and `test_response_envelope_conventions.py` checks every router. `ConversionResult` is the one allowed exception and says why: it extends `ApiResponse` to carry the order a quotation became |
| 37 | **the movement-versus-document audit**, every posting that touches inventory | 2026-08-22 | **one more of the family, and the family is now closed.** All six forward postings read the stock ledger already -- receipt, dispatch, both returns and both adjustment paths. Of the three reversals, two had been fixed that morning and the third, `sales_return._reverse_postings`, still mirrored its cost entry: goods come back at the average of the day the return completed and leave at the average of the day it is cancelled. Proven live -- complete a return, receive twenty units at four times the price, cancel: 16.45 out | yes -- `reverse_goods_return_to_stock`. Both its legs are the movement value, so it balances alone and the difference stays in cost of goods sold; no third account, unlike the receipt and purchase-return cases |
| 38 | **the desktop sidebar**, every declared tab against what its screen does (all 14 modules) | 2026-08-22 | **thirteen entries that did not do what they said**, in three modules. Sales Invoices declared seven and `SalesInvoiceManagementPage` never took a tab id at all, so Overdue Invoices, Invoice Register, Invoice vs Delivery, Customer Outstanding, Pending and History all built the same widget with the same query as the list -- byte-identical results. Delivery Notes declared seven under a group labelled *Reports*: two applied a status filter and four filtered nothing. Goods Receipts declared a Settings entry whose page takes a `tabId` and reads it nowhere, so it opened the receipts list. The nine report entries are the sharp part: every report they name **exists**, at `/api/v1/{delivery-notes,sales-invoices}/reports/*`, and is wired into `report_catalog.dart` -- reachable from Reports, and from nowhere the menu pointed at | yes -- one entry per module with the lifecycle statuses on a segmented bar, `fromTabId` carrying a retired id's choice across, and `test/document_navigation_test.dart` asserting the query rather than the screen. `desktop/docs/WORKSPACE_NAVIGATION_RULES.md` states the three rules |
| 39 | **desktop-to-backend integration**, every route against every caller | 2026-08-22 | **two, one live.** (1) The Refunds screen offers Reverse on every row -- `SettlementsPage` is one widget for all three directions -- and `POST /api/v1/refunds/{id}/reverse` did not exist, so the button answered 405 on that screen alone. Worse, the route could not simply be added: `SettlementService.reverse` put the customer's balances back only for a RECEIPT, while `create` posts a receivable transaction for a REFUND too, so wiring the route alone would have mirrored the journal and left the advance short by the whole refund. (2) `verify_sample_data.py` compared **gross** customer outstanding against the receivable control account, and a receipt credits the whole amount to receivables while the customer row splits it into balance and advance -- so 500.00 of advance read as "a balance moved without a journal". It had never fired because the history generator allocates every receipt; it fired on the first refund driven through the API. Everything else held: all 33 report paths resolve, every lifecycle action the five document workspaces can fire has a route, and every permission code the desktop gates on is seeded | yes -- both endpoints added, `reverse` widened to REFUND, the invariant nets advances. Driven on ELEC01: advance 500 → refund 400 → advance 100 → reverse → advance 500, five checks passing at every step |
| 40 | **`category_attribute_rules`**, the first of the no-UI list from row 39 | 2026-08-22 | **a hole in the product, and one deviation.** `20260815_0087` cleared the four blanket `mandatory` flags that asked a pharmacy for an IMEI, on the stated understanding that a real requirement would be declared in `category_attribute_rules` instead -- scoped to a category and optionally to one industry. The endpoints were there; nothing in the desktop called them, so from 2026-08-15 no firm could make any attribute mandatory at all. The list endpoint was also the only one in the module returning an unpaginated `ApiResponse[list[...]]`, which nothing had noticed because nothing called it | yes -- an Administration screen under Business Profiles, the list paginated and searchable like its siblings, and the response carrying the attribute and profile names so the grid is not three UUIDs. Driven on ELEC01: a product saves, the rule is written, the same product is refused naming the missing attribute, it saves once carrying it, and saves again once the rule is deleted |
| 41 | **vendor categories and types**, the second item off row 39's no-UI list | 2026-08-22 | **nine unreachable endpoints, and the reason the masters had no caller.** `vendors.category_id` and `type_id` have been columns since the module was written and `VendorWrite` has always accepted both, but the vendor form offered neither field and the two master tables had no screen. Building one surfaced why nobody had noticed: `GET /vendors/categories` and `/types` were declared **after** `GET /vendors/{vendor_id}`, so FastAPI read "categories" as a vendor id and answered 422 -- neither list had ever returned a row. A guard written for that found seven more of the same shape, all `GET /export`: `branches`, `warehouses`, `sales-orders`, `delivery-notes`, `goods-receipts`, `purchase-invoices`, `purchase-returns`. Third occurrence of the trap after `sales_territories` | yes -- the routes reordered and all nine answering 200 against a running server, both master lists paginated and searchable, two Masters screens, and category and type pickers on the vendor form that stay **absent** from the payload while the lists are loading rather than sending a null that would clear them. `tests/unit/test_route_declaration_order.py` fails the build on the next one |
| 42 | **printing a bill**, end to end | 2026-08-22 | **the platform could not send a customer an invoice at all.** No PDF library, no print endpoint, no template -- while a Print control on the purchase workspace showed a toast saying print was "reserved for the next transactional phase" and the document dialog's Print, Export and Email buttons did nothing whatsoever. Worse, the record could not have supported one: a line kept a single `tax_amount`, so the CGST/SGST split a tax invoice must state existed only in a prunable log, and the line did not even name the profile that produced it. Due date and place of supply were likewise absent | yes -- `sales_invoice_line_taxes` and `place_of_supply` (`20260822_0096`), a per-firm `document_print_templates` (`20260822_0097`), a reportlab renderer, `GET /api/v1/sales-invoices/{id}/print`, a Print button on the invoice workspace, and the two purchase controls fixed as well -- the toolbar one that showed a toast and the dialog one that did nothing, both now rendering the order through the same renderer, with Export and Email removed for having no backend at all. Driven on ELEC01: a real bill with both parties' identifiers, HSN 854442, CGST 9% 90.00 + SGST 9% 90.00, the HSN-wise summary, the amount in lakh-and-crore words, and two labelled copies |
| 43 | **packaging levels**, the third item off row 39's no-UI list | 2026-08-23 | **a table with a full CRUD API, no caller and no reader.** Recomputing row 39's audit left eight routes nothing in the desktop builds a path to, and four of them are `products/{id}/packaging-levels`. Unlike the two items before it, the endpoints worked -- a level created and read back fine against ELEC01 -- so this was not the declaration-order trap a third time. It was worse: `ProductPackagingLevel` is referenced by **nothing** outside its own CRUD, so the `barcode`, `gtin`, `ean` and `upc` columns on every level were text no code path read, and `docs/UOM_FRAMEWORK.md`'s claim that this "lets a scanner read a carton label and know it holds 120 pieces" had no implementation behind it. There is no scan endpoint anywhere in the platform, and global search matches `products.barcode` alone. The other four uncalled routes are redundant rather than missing: `document-framework/documents/{id}/timeline` and `/events` duplicate the per-module `/timeline` endpoints the desktop does call, and the two `sales-territories/addresses/{owner_type}/{owner_id}` routes are superseded by the per-module address forms | yes -- `GET /barcode-lookup` resolving a code across all four columns and then the product's own barcode, returning the product and how many base units one scan is; and a Packaging Levels screen with the hierarchy editor and a scan box beside it. Driven on ELEC01: a carton at ×10 resolves by barcode, a second thing carrying the same code is refused naming the count, and a code nobody carries is refused naming the code |
| 44 | **the sales module**, every feature against what a distribution firm needs | 2026-08-23 | **eleven gaps, and the first is that a firm using only the desktop cannot bill a customer.** No invoice editor, no "bill this delivery note" action, and no call POSTing to `/api/v1/sales-invoices` anywhere in `desktop/lib` -- while the route worked and `SALES_INVOICE_CREATE` sat seeded with no screen checking it, so the authority was modelled and the capability was not reachable. It also left the invoice print work of row 42 with nothing to print. Two more of the same family: a sales order can only be raised by converting a quotation, and a sales order's status never moves as it is delivered -- `SalesOrderStatus` declares four states and nothing resyncs from delivery notes, where `goods_receipt` has `_resync_order_status`. Then: only two documents in the platform can be printed, so no delivery challan, no quotation and no credit note; optimistic concurrency stops before the invoice, which accepts no `If-Match` and publishes no version while the sales return publishes one and accepts no precondition; `products.selling_price` and `mrp` are columns nothing reads; and there are no price lists, schemes, commission or targets at all | `docs/SALES_FRAMEWORK.md` records all eleven with the four decisions that look like gaps and are not. Gap 1 is **closed**: `GET /sales-invoices/billable` and a New Invoice editor. Driving that endpoint found a defect in it before it shipped -- the limit was applied to candidate notes and the fully billed ones filtered afterwards, so `limit=1` returned nothing at all; it filters in SQL now and a regression test asks for one and expects one |

### 24–29 the cross-cutting passes — how they were found

Six of these are not module reviews. They are what a module review keeps almost
finding: a rule that holds in one module and not its neighbour, a name that
means two things, a screen that cannot see what the server records.

Three things produced all of them, and are worth reusing:

**Answering "which module is incomplete" honestly.** The list that started this
run came from reading the catalogue against the code rather than the docs — it
is how `diagnostics` and the vendor tabs surfaced, both of which every previous
pass had walked past because the module's own tests were green.

**Building the screen that reads the telemetry.** The `page_size` sweep did not
come from a review. It came from the triage screen's first contact with real
data, which listed 28 identical 500s and named the endpoint. A defect nobody can
see is one every pass will keep missing.

**Renaming the thing that means two things.** `uom`'s `version` collision had
been recorded in `CLAUDE.md` as a reason not to wire `If-Match` there — a
decision deferred rather than a difficulty. Resolving the name immediately
exposed a second copy of a resolver getting both the column and the ordering
wrong, and the ordering half could not have been reported by a test: the unit
suite runs on SQLite, where NULLs sort the other way round.

Two habits carried over from the earlier passes did the actual verifying:
**drive it against a running backend** (every one of these was confirmed on the
seeded firms, and restored afterwards), and **make the guard fail first** — each
new test was run against the unfixed code before the fix was kept.

### 30–32 the last three unreviewed modules

`sales_return`, `quotation` and `diagnostics` were what the suggested order had
left. All three were driven rather than read; two of the three findings could
only have been found that way.

**`sales_return` — the arithmetic of an undo.** Its cancel path reverses stock
and both journals correctly, and the existing test proved the customer's balance
came back too. It did, in the fixture's case: the customer owed more than the
return was worth, so the credit note applied in full and had nothing to split.
Give the customer a smaller balance than the return and the credit note splits —
applied up to what is owed, the rest an unapplied advance — and only that row
remembers the split. Cancelling posted a fresh INVOICE for the whole amount.

    owed 100, return worth 200
    complete → outstanding 0, advance 100
    cancel   → outstanding 200, advance 100      (was: owed 100, advance 0)

Reproduced as a unit test before the fix, which is the only reason the numbers
above are the measured ones. `settlements` has always reversed by the stored
deltas; `sales_return` now does the same, and `sales_invoice`'s cancel was read
and left alone — undoing an invoice the customer has since part-paid *should*
leave an advance.

**`quotation` — proving a negative.** The module is defined by what it does not
do, and nothing in its own code could show that: the proof has to come from the
modules it might have touched. Snapshotting the customer's balances, every
reserved and on-hand quantity for the product, and the journal count, then
creating, sending, accepting and converting a quotation, left all of them
identical. The order the conversion produced is a draft, and a draft reserves
nothing — which is where the reservation belongs, not in the quote.

**`diagnostics` — the module with no test where it mattered.** Both findings sit
in the two seams the unit tests could not reach: what the exception handler is
handed, and what a real traceback looks like. The first was visible in the data
the moment anyone looked — 28 of 28 rows with a NULL request id — and the second
needed the four stored tracebacks to see at all, because every one of them
begins with the same five lines of ASGI plumbing.

Neither is a defect a review of `app/diagnostics` alone would have found. The
request id is decided by middleware ordering in `app/core`; the fingerprint is
decided by what Python puts at the top of a traceback.

### 33 the second pass — what a review finds when the code is already right

The suggested order ended with "a second pass over the modules reviewed on
2026-08-09, before driving endpoints was the habit". Nine modules, and the pass
turned up one finding — in the data, not the code.

**The method was to ask the invariants first.** `scripts/verify_sample_data.py`
already knows what has to be true across these modules: stock value against the
inventory control account, every period balancing, customers against the
receivable account, every settlement reaching the ledger, every approved invoice
posted. Running it before touching anything is how the pass started, and two of
three stores failed the first check.

**Decomposing a drift is the slow part, so the verifier now does it.** The
number came apart like this:

| store | drift | goods-receipt reversals with no mirror | left over |
| --- | ---: | ---: | ---: |
| `firm_shared` | −52,582.436 | 52,582.437 | 0 |
| `wholesale_hub` | −3,971.207 | 4,009.666 | 38.459 |

Cancelling a completed goods receipt reversed the stock and left the journal
standing until 2026-08-18. Every cancellation in these stores is dated that day,
and exactly one — the last — carries a mirror, which is the fix being tested the
moment it landed. So the ledger still holds inventory the warehouse gave back.
`_unmirrored_receipt_note` says so now, and says how much a drift it does *not*
explain would be, because that is the case worth an hour of somebody's time.

**Two classes were closed by reading rather than driving.** The
"recompute a balance instead of reversing it" defect found in `sales_return`
that same day cannot exist on the purchase side: vendors keep no running
balance at all — no payable transactions, no outstanding or advance columns —
so `purchase_invoice` and `purchase_return` have nothing to drift. On the sales
side the only other recompute is `sales_invoice`'s cancel, which is deliberate:
undoing an invoice the customer has since part-paid *should* leave an advance.

**What passed, and is worth recording because it was measured.** Reservations
balance (127 RESERVE against 127 UNRESERVE in one store, 57/57 in another,
nothing left reserved anywhere); no stock row in any store is negative or
disagrees with `available = current - reserved - blocked`; every journal entry
balances; customers match the receivable control account in all three stores;
`ELEC01` passes all five checks outright.

### 34 the cancel paths, and the one that is still wrong

The seeders only ever drive the happy path, so nothing in the demo data has ever
been cancelled. Two of this week's defects were in cancel paths, so with three
freshly seeded stores and a verifier that answers in seconds, the obvious pass
was: cancel one of everything and ask the books after each.

Driven on ELEC01 — a dedicated database, so a drift there is unambiguous:

| cancelled | result | books after |
| --- | --- | --- |
| goods receipt | refused: *"has been invoiced… cancel the purchase invoice first"* | 5/5 |
| delivery note | refused: *"can no longer be cancelled"* | 5/5 |
| sales invoice | 200 | 5/5 |
| purchase invoice | 200 | 5/5 |
| sales order | 200 | 5/5 |
| **goods receipt**, after cancelling its invoice as instructed | **200** | **1 problem** |

**The finding.** `_reverse_receipt_journal` mirrors the entry the receipt
posted — the full amount, at the price the goods arrived at — while
`_reverse_inventory` takes the stock back out at **today's** moving average.
Those are the same number only until something else is received at a different
price:

```
receipt   60 units @ 134.000000  → posted     8,040.00 to INVENTORY
cancel    60 units @  95.876591  → removed    5,752.60 of stock value
                                   mirrored  -8,040.00 from INVENTORY
                                   drift      2,287.42
```

**The codebase already has an opinion about this, twice.** Both return modules
value their posting from the stock ledger rather than from the document, and
say why in the code: *"stock leaves at the moving average it was carried at, and
the two are routinely different."* By that convention the ledger follows the
movement, and the receipt cancel is the odd one out.

**Fixed the way the codebase already leans.** The difference had to land in a
named account, and one already existed for exactly this: `PURCHASE_PRICE_VARIANCE`,
which `post_purchase_return` uses when goods leave at an average that disagrees
with the price on the document. So a cancelled receipt now debits goods received
not invoiced in full — the firm owes nobody for goods it handed back — credits
inventory with what the warehouse actually removed, and books the gap to the
variance account:

```
Dr Goods Received Not Invoiced  12,000.00
Cr Inventory                    11,943.90     ← the movement removed 11,943.8959
Cr Purchase Price Variance          56.10
```

`reverse_entry` grew a `lines` parameter for it: a reversal that is not a mirror
still wants everything else a reversal is — the link back, the original marked
REVERSED, one audit row. The other option, unwinding the moving average to what
it was before the receipt, would have been a change to the valuation engine
rather than to this method, and would still have to answer for stock that has
since been sold.

**What this pass cost and returned.** One store had to be regenerated
afterwards (`generate_transaction_history.py --firm ELEC01 --years 3 --reset
--yes`), and all three stores pass again. The defect had survived a review pass
in 2026-08-09, a fix to its neighbour in 2026-08-18 and a second pass in
2026-08-22 that read the code — and took one cancel to find.

### 35 the rest of the cancel paths

Row 34 left three unreached: `purchase_return` had none seeded, the
`sales_return` probe built one worth nothing, and every delivery note it tried
refused. All three post to the ledger and move stock, which is the pairing that
has now produced four defects.

**`purchase_return` — the same defect, in the mirror module.** Completing a
return debits payables for the supplier's credit note, reverses the input tax
and credits inventory. `cancel_return` reversed the stock and stopped: no
`reverse_entry` call, no `JournalEntryEngine` import, not even a
`journal_entry_id` on the model. So a cancelled return left the firm showing a
supplier owing it for goods it had kept, and the store 199.07 out on one
cancellation.

`goods_receipt` carried precisely this until 2026-08-18. When it was fixed,
nobody asked which other module had the same shape. The fix here is the one
written that morning: mirror the payable and tax legs, debit inventory with what
the movement actually put back, and let purchase price variance carry the
difference.

**`sales_return` — clean, and this time it meant something.** The first probe
built a return worth nothing, because every delivery-note line in seeded data
carries `unit_price = 0` while every sales-invoice line carries a real one.
Sourced from an invoice instead: a 212.40 return moved the customer from
133,220.55 to 133,008.15 on completion and back to 133,220.55 on cancellation,
with the books passing at every step. The advance-split fix of the same morning
holds against real money.

**`delivery_note` — nothing to test.** Every note in every seeded store is
DISPATCHED, and a dispatched note is deliberately not cancellable: the goods
have gone, and the way back is a sales return. The refusal *is* the behaviour,
and it fires.

**One thing worth knowing about the data:** a delivery note line carries no
price. That is defensible -- a dispatch is about quantity, and the money is on
the invoice -- but it means a sales return raised from a delivery note is worth
nothing until somebody types a price, and the operator gets no default.

### 37 the rule the four defects were all breaking

Four defects in two days had one shape, so the fourth was found by asking the
question directly of every posting rather than by waiting for it to surface:

> **A ledger leg that faces stock is valued from the movement the warehouse
> made. A leg that faces a counterparty — payables, receivables, tax, revenue —
> is valued from the document.**

Read against that rule, the forward path was already right everywhere. Every one
of `post_goods_receipt`, `post_goods_issue`, `post_sales_return`,
`post_goods_return_to_stock`, `post_purchase_return` and both adjustment paths
takes its inventory figure from `StockLedgerEntry`, several of them with a
comment saying why.

The reversals were where it broke, all three of them, because a reversal is
where the two dates differ:

| reversal | before | after |
| --- | --- | --- |
| `goods_receipt.cancel` | mirrored the receipt price | movement value, gap to variance |
| `purchase_return.cancel` | no journal at all | movement value, gap to variance |
| `sales_return.cancel` (cost) | mirrored the completion | movement value, gap stays in COGS |

The sales-return case needs no variance account: both legs of that entry are the
same figure, so posting it at the movement value balances on its own and the
difference lands in cost of goods sold, which is where the valuation of goods
that were sold belongs.

**What made the audit cheap** was having the rule. The first three were found
one at a time, each by cancelling something and watching a store break. The
fourth was found by reading eight call sites against a sentence -- and then
confirmed the same way, because reading is a hypothesis and the verifier is the
answer.

**One trap worth repeating**, from `docs/RUNNING.md` and paid for again here: a
server started before an edit serves the code it loaded. The first "verification"
of this fix ran against a stale process and reported the drift growing; the fix
was fine. Restart, or check something the change added, before believing a
result.


### 38 `promotions` — three findings and one sentence behind them

Reviewed 2026-09-03, first of the nine modules built since 2026-08-22 that the
table had never covered (`promotions`, `pricing`, `loyalty`, `tcs`,
`gst_returns`, `einvoice`, `credit_note`, `proforma`, `commission`). Chosen
because it gives money away and because #198 had already turned up a real
defect in it by accident, which is usually a sign there are more.

Baseline first, per the rule at the top of this file: 12 files, 2,477 lines, 11
endpoints, 43 tests passing, clean under ruff and mypy, six tables.

**What was already right**, and checked rather than assumed: both permission
codes are seeded; nothing reads a platform table on the tenant session;
nothing calls `date.today()`; no update dumps its whole write model any more
(#198 fixed the one that did); and a coupon's own status, effective window and
two limits are all enforced, with the window judged on the **document's** date
rather than today's. `PromotionRedemption` extends `BaseEntity`, so `claim`
and `reverse` carry their own actor and timestamp -- they write no separate
audit row, and that is a judgement rather than a gap, for the reason the
loyalty ledger gives: a second copy of a fact is one that can disagree with it.

**All three findings were the same sentence, unstated:**

> **A promotion's identity is its `version_group_id`. The row is only the
> version that happens to be current.**

`CLAUDE.md` already says an ACTIVE promotion is superseded by a new row rather
than edited, so that a document priced in March is still explicable in
September. Three checks compared a row id instead, and each broke across that
supersede:

1. **A coupon was orphaned by any edit to its offer.** `requires_coupon`
   compared `coupon.promotion_id` against the live promotion's id, so editing a
   published coupon-gated offer left every code in circulation pointing at the
   predecessor. Driven on WHOLE01: a 10% offer gave 109.00 on a 1,000.00 line;
   changing it to 12% dropped the same line to 10.00, with the coupon still
   listed ACTIVE. **This is the worst of the three because editing is the
   routine act** -- there is no way to change a published offer that does not
   go through supersede.
2. **The redemption caps reset on the same edit.** `Promotion.max_redemptions`
   and `max_redemptions_per_customer` were counted with
   `PromotionRedemption.promotion_id == promotion.id`, so the successor started
   at zero claims. An exhausted campaign became fully available again on a
   one-character edit.
3. **Retiring an offer left its codes live.** `delete_promotion` soft-deleted
   the row and nothing else, so the coupon stayed in the list as ACTIVE,
   naming a retired offer, giving nothing, with nothing on screen to say why --
   `ondelete="RESTRICT"` is no guard on a soft-deleted table, which this file
   already records for the geography masters and customer groups.

The fix is the sentence: `_claimed` counts across the version group,
`_coupon_reaches` matches on it, and retiring the **last live version** of an
offer retires the codes that reach it. Only the last one -- retiring a
superseded predecessor leaves the codes alone, because the offer they reach is
still live on another row, and that distinction was driven both ways.

**What this pass says about the other eight.** Finding 1 and 2 are both
"identity is not the row", which only exists in a module that supersedes.
`app/tax` supersedes the same way and its rules carry a `version_group_id`
too, so its equivalent checks are the first thing to read in that module's next
pass. Finding 3 generalises further: **every soft delete in the nine new
modules should be asked what points at the row afterwards.**


### 39 `loyalty` — the sweep, and what it forgot to give back

Reviewed 2026-09-03, second of the nine. Chosen because it is a ledger with a
payable account behind it, and because #194 had already found its two books
drifting once -- the redemption that moved the control account while the
customer's own balance stayed put.

Baseline: 9 files, 1,174 lines, 7 endpoints, two tables, 19 tests, clean under
ruff and mypy.

**What was already right**, checked rather than assumed: all three permission
codes seeded; nothing reads a platform table on the tenant session; nothing
calls `date.today()` -- `expire` documents its own use of `utc_now()` and the
reason; no update dumps its whole write model; the balance is derived and
there is no column to disagree with it; `expiry_months` NULL really does mean
never rather than today; and the sweep was already idempotent, naming the
entry it takes through `reverses_id`.

**Finding 1: expiry took points that had already been spent.** `expire` wrote
`points=-entry.points` -- the whole batch -- without asking how much of it was
left. Earn 100, spend 100, let the batch lapse, and the customer holds **-100
points** for credit they had legitimately used. `balance` sums the ledger with
no floor, and `redeem` refuses anything above the balance, so this sweep was
the only route below zero, and it took it silently.

The fix allocates spending **oldest batch first**, which is both the ordinary
treatment and the reason it cannot simply cap at the customer's balance: a
customer holding one lapsing batch and one fresh one, who spent the older
one's worth, should keep the fresh one in full. Capping at the balance would
have taken the batch with a year left on it. That case is a test of its own.

**Finding 2: nothing released the liability.** Earning posts
`Dr Loyalty Expense / Cr Loyalty Payable`, deliberately, so a scheme's cost
lands in the month it was incurred. Nothing reversed that when the credit ran
out of time, so the payable kept a debt no customer could ever claim.
`post_loyalty` had exactly two modes and expiry was neither. Measured in
WHOLE01: nine lapsed batches worth **936.31** when earned, **none** carrying a
journal, against 49 earnings that had all posted one. A lapse now posts the
accrual in reverse, pro-rated for the share of the batch that lapsed.

**Two process notes, both mistakes made here.**

The API response for a loyalty entry carries no `journal_entry_id`, so an
early reading of "nine expiries, none with a journal" was drawn from a field
that does not exist in the payload -- every row would have looked that way.
The claim was only worth anything once it came from the database. **Ask
whether the absence you are reading is in the data or in the shape of the
response.**

And `expire` commits internally, so the probe script's `session.rollback()`
could not undo it: two runs left an artificial batch, spend and lapse in
WHOLE01, and its journals with them. Removed by hand -- the rows were
identifiable because a seeded earning or redemption always names an invoice
and a hand-written one does not -- and `verify_sample_data.py` green
afterwards, with the store back to its 49 / 7 / 9. **A driver that calls a
committing service is not a dry run**, whatever the last line of it says.


### 40 `commission` — the arithmetic holds; the month-end button does not

Reviewed 2026-09-03, third of the nine. Chosen because it pays people, and
because slabs, margins, caps and six rungs of precedence are a lot of places
for money to go wrong.

Baseline: 11 files, 3,146 lines, 13 endpoints, three tables, 35 tests, clean
under ruff and mypy.

**Almost all of it was right, and each rule was read against the code rather
than taken on trust.** `minimum_amount` returns nothing below the threshold
and pays on the whole subtotal above it, which is the deal a zero-percent
bottom slab would *not* express. The bonus is added before the cap, so a
firm's ceiling still holds. The cap is applied after the ladder, so it limits
what was earned rather than what was sold. MARGINAL charges each portion at
its own rate and WHOLE_AMOUNT the whole subtotal at the rung reached.
`slabs_of` orders by `from_amount` rather than `sequence` -- and says why, in
so many words, because the `break` in the marginal loop depends on it. The
ladder validator refuses a gap, an overlap, and a bottom rung that does not
start at zero. PER_UNIT is refused on the COLLECTED basis and refused without
a product or category, both with the reason in the message. Targets are summed
against targets, and a person with nobody's number to hit is absent from the
answer rather than False. A MARGIN rule skips a line whose cost is unknown
rather than treating it as free, and a negative margin is floored rather than
clawed back. Every permission code is seeded, nothing reads a platform table
on a tenant session, nothing calls `date.today()`, no update dumps its whole
write model.

**The finding is one the code could not have shown by reading.**
`_assert_period_is_free` runs a SELECT, `accrue` then INSERTs, and nothing sits
between them -- no lock, and only plain indexes on the table. Two sessions on
WHOLE01, interleaved by hand so both checked before either committed, both
wrote: one salesman, two live payouts, one month.

`app/promotions` takes `with_for_update` on the promotion for exactly this
class of problem and `settlements` was proven against it in row 23, so the
house standard was already there; commission was the exception. There is no
per-salesman row to lock here, so the guard is a **partial unique index** --
the shape `UQ_firms_code_active` and `UQ_branches_default_active` already
take -- on `(firm_id, salesman_id, period_start, period_end)` where the row is
live and not CANCELLED. The service check stays: it gives the message somebody
can act on, and it covers *overlapping* periods, which no unique key can
express. The `IntegrityError` is translated where the flush happens, so the
loser of the race is refused by name instead of answered with a 500.

**Three things this pass paid for, all worth repeating.**

A partial index declared with `postgresql_where` alone is **not** partial on
SQLite -- the clause is ignored and `create_all` builds an unconditional
unique index, which is *stricter* than intended. It broke the documented
behaviour that a CANCELLED payout frees the period, and the unit suite caught
it. `sqlite_where` beside it fixes the shape on both dialects.

Two pending inserts of the same key do not race in PostgreSQL: the second
**waits** on the first transaction rather than failing. A test that inserted
both before committing either simply hung. The interleaving to write is the
one that happens: the second session does its *read*, the first commits, and
only then does the second write.

And an integration test that holds two connections must not share the pool
with the fixtures. `SET search_path` rides on a pooled connection into
whichever test gets it next, and a sibling that sets one and expects it back
began failing as soon as this file shuffled the pool. These sessions take a
`NullPool` engine of their own, and every statement names its schema.
