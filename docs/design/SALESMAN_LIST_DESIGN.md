# A list of salesmen of the firm's own: design note

**Status: design note for row P2 of `docs/CUSTOMER_BUILD_TASKS.md` (PRT-8,
*Order By*), written 2026-10-14. Nothing in it is built.** The owner answered
on 2026-10-14 that the firm keeps its own list of salesmen and said to build
it; this note does not wait for him. What it decided in his absence is listed
in section 8 for him to confirm.

## 1. What it does for the user

The firm keeps a list of salesmen under *Settings* > *Sales*. Each entry has a
name and, where the salesman signs in, the user account he signs in with. An
entry tied to no account is an ordinary entry: a salesman who writes his
orders on paper, *Phone order*, *Company staff*. Nobody is given a sign-in so
that a name can print.

Every document of a sale names its salesman from that list: the enquiry, the
quotation, the order, the delivery note, the bill, the return and the two
notes. So do the customer (his account manager), the round, the targets,
the commission rules and the payouts. The full-page bill prints the name
under *Order By*.

On a new bill, order or delivery note the *Salesman* box is filled in to start
with (section 5), any other entry may be chosen, and it can be changed
afterwards for as long as the document's other fields can. A document raised
from an earlier one keeps that one's salesman, as the chain already does. A
firm may make the box required: a switch of its own, off to start with.

## 2. What is there today

Read on 2026-10-14 at main `d3f1ef65`.

- **Eleven columns name a salesman, and every one is a user id.**
  `salesman_id` on `sales_invoices`, `sales_orders`, `delivery_notes`,
  `quotations` (each a foreign key to `users.id`), on `enquiries`,
  `credit_notes`, `customer_debit_notes`, `sales_returns` and `customers`
  (no key; `users` lives only in the platform store), on `commission_rules`,
  `commission_payouts` and `sales_targets` (a key to `users.id`), and
  `territory_salesman_assignments.user_id`.
- The keys to `users.id` are declared in the ORM, but `users` exists only in
  the platform schema; the migrations declare them only where the target is
  found (`_external_fk`), so in a firm's own store they are not there and
  nothing holds the reference.
- **Names are read from the platform store** (`salesman_names` in
  `app/common/report_names.py`, through `platform_reader()`), once a page.
- **Who may be named is checked against membership**: commission rules and
  targets refuse a person who is not an active member of the firm
  (`active_member_count`), and the bill checks its salesman the same way
  (`_fill_missing_scope` in `sales_invoice_service.py`).
- **A blank salesman is filled on save** by `resolve_sales_scope`
  (`app/sales/services/scope_resolution.py`): the customer's account manager,
  then the round's salesman.
- **The bill must agree with its sources**: "Invoice salesman must match all
  source documents", and a bill over several notes takes the salesman they
  share.
- **Nothing is limited to one's own records.** No route narrows a list, a
  target or a commission statement to the signed-in salesman; the filters
  take any `salesman_id`.
- A promotion's or loyalty rule's salesman condition is not checked when the
  offer is written (`app/promotions/services/references.py`) because the
  list it would check against is in the platform store.

## 3. The table

`salesmen`, in every firm store (`firm_shared` and each dedicated store),
a `BaseEntity`:

| Column | Type | Meaning |
| --- | --- | --- |
| `firm_id` | UUID, not null, indexed, no key | the firm (the `firm_shared` rule) |
| `code` | string(30), null | the firm's own short code, as the old software's salesman master keeps one; unique among live rows of the firm when present |
| `name` | string(120), not null | what prints; unique among live rows of the firm, case-insensitive |
| `user_id` | UUID, null, no key | the account he signs in with; `users` is a platform table. Unique among live rows of the firm when present, so one user is one salesman |
| `phone` | string(20), null | |
| `earns_commission` | bool, not null, default true | false for *Phone order*, *Company staff*: no rule, payout or target may name such an entry |
| `is_active` | bool, not null, default true | an inactive entry is kept on old documents and offered on none |
| `notes` | text, null | |

Partial unique indexes on `(firm_id, lower(name))`, `(firm_id, code)` and
`(firm_id, user_id)`, each `WHERE is_deleted = false`, with `sqlite_where`
beside `postgresql_where`. A salesman named by any document, customer,
round, target, rule or payout cannot be deleted; he is made inactive.

Routes, `/api/v1/salesmen`: list (`page`, `page_size`, `search`, `sort_by`,
`sort_direction`, plus `active`), one, create, update (`exclude_unset`,
`ETag`), delete, restore, and `GET /api/v1/salesmen/starting-choice` (section
5). Reading the list is gated on membership alone, like
`GET /api/v1/firm-members`: whoever makes a bill must be able to fill the
box. Writing needs a new code, `SALESMAN_MANAGE`, in `PERMISSION_GROUPS` and
inserted by the migration, granted to the firm administrator and
`SALES_MANAGER`. Tying an entry to a user checks, on the platform store, that
the user is an active member of the firm (`FirmMetadataReader`).

## 4. Moving the eleven columns across

**The salesman made for a user takes the user's id as its own id.** Every
column above then stays valid as it stands: no document row is rewritten,
nothing printed or reported changes, and a migration replayed on a store that
`create_all` already built finds nothing to do.

The migration, per store, idempotent:

1. Create `salesmen` if missing.
2. Collect every distinct id in the eleven columns. For each with no
   `salesmen` row, insert one with `id = user_id = that id`. Its name is
   copied from `platform.users.full_name` where that table can be reached
   from this database (the shared database and dedicated schemas); in a
   dedicated database it cannot, so the row is named `Salesman` and the
   first eight characters of the id, and `upgrade_every_store`
   (`app/core/tenancy/migrations.py`), which holds the platform session,
   renames those rows from `users` once every store is at head. Where two users
   share a name, the second is named with the first eight characters of
   its id after it, so the name key holds.
3. Declare the keys: each `salesman_id` references `salesmen.id`
   (`FK_<table>_salesman_id`, `ondelete="RESTRICT"`), replacing the key to
   `users.id` where one was declared.
4. `territory_salesman_assignments.user_id` becomes `salesman_id`: add the
   column, copy, move the unique key and the index onto it, drop `user_id`.
   This is the clean-up the owner's rule asks for: the user-keyed column the
   list replaces goes in the same work.
5. Insert `SALESMAN_MANAGE` and grant it where `TERRITORY_ASSIGN_SALESMEN`
   is granted.
6. Add `salesman_required` to `sales_workflow_settings` (section 6).

`customers.collector_id` is **not** moved: the collector is the member who
chases the money and is answered for in the collection sheet, and the owner
did not name it. Listed in section 8.

After the move:

- **Who may be named** is an active entry of the firm's list, read in the
  firm's own store. `active_member_count` stops being asked for a salesman.
  A rule, payout or target refuses an entry with `earns_commission` false,
  by name.
- **Names** are read from `salesmen` in the same session; `salesman_names`
  loses its platform read, and with it the 503 a firm store could answer
  when the platform was unreachable.
- **Promotion and loyalty salesman conditions** are checked when written,
  now that the list is local.
- The desktop's pickers that offer `firm-members` for a salesman offer the
  salesman list instead.

## 5. What the box starts on

On a new bill, order or delivery note, the screen asks
`GET /api/v1/salesmen/starting-choice?customer_id=...` once when the customer
is chosen, and fills the box with what it answers, in this order:

1. the salesman tied to the signed-in user (the owner's rule);
2. otherwise the customer's account manager (`customers.salesman_id`);
3. otherwise the primary salesman of the customer's round
   (`territory_salesman_assignments.is_primary`);
4. otherwise blank.

Steps 2 and 3 are what `resolve_sales_scope` already fills on save, so the
box shows on screen what the server would have filled; that resolver keeps
filling a blank sent by any other client, in the same order after step 1.
A document raised from an earlier one takes that one's salesman and does not
ask. An inactive entry is never a starting choice.

## 6. Required, as a firm's choice

`sales_workflow_settings.salesman_required`, bool, default false, written
where the firm's sales settings are written (the *Sales* section of the
settings screens, backlog 148). When it is on, the sales order, the delivery
note and the bill refuse a save that, after the fill of section 5, still
names no salesman: *"This firm requires a salesman on every order, delivery
note and bill. Choose one in the Salesman box."* The check sits in each
service's create and update and in the chain (`SalesChainService`), so a
stage a firm skips is held to it too. Documents already saved are not
touched by turning it on; the rule applies to their next save. The enquiry,
the quotation, the return and the notes are not held to it.

## 7. The steps of the build

Each a run of its own, merged on targeted tests.

1. **The list.** Model, migration (sections 3 and 4, steps 1 and 2 only),
   `all_models.py`, service, router, `SALESMAN_MANAGE`, the renaming pass in
   `upgrade_every_store`. Nothing reads it yet. Tests: a new
   `test_salesmen.py`; `test_identity_hardening.py`, `test_schema_registry.py`,
   `test_route_declaration_order.py`, `test_pagination_conventions.py`;
   an integration test that a dedicated store's entries are renamed.
2. **The move.** Section 4 steps 3 and 4; validation against the list in the
   bill, order, delivery note, quotation, enquiry, return and notes services,
   in `scope_resolution.py`, commission, payouts and targets;
   `salesman_names` local; promotion and loyalty conditions checked. The
   assignment column renamed everywhere it is read. Tests: each module's own
   file, `test_commission*`, `test_sales_target*`, `test_sales_territory*`,
   `test_collection*`, `test_sales_analysis*`, `test_list_pages_are_batched.py`,
   and `tests/integration/test_multi_schema_tenancy.py`.
3. **The start and the switch.** `starting-choice`, `salesman_required`, the
   refusals, the chain. Tests: the three document modules and
   `test_sales_chain*`.
4. **The screens** (phase 2 only). The *Salesmen* list under *Settings* >
   *Sales*; the *Salesman* box on the bill, order and delivery note editors
   filled from `starting-choice`; the switch beside the other sales
   settings; the round, target, commission and customer pickers on the list.
   One read of the list a session, cached as the other masters are.
5. **The print.** *Order By* on the full-page bill prints the salesman's
   name; a bill with none prints no such row. Then the reference docs
   (`docs/COMMISSION_FRAMEWORK.md`, `docs/TERRITORY_FRAMEWORK.md`,
   `docs/SALES_CHAIN_RULES.md`), the user guide, the QA cases, and row P2
   and PRT-4/PRT-8 closed.

## 8. Decided here, for the owner to confirm

1. **Where the box starts when the signed-in user is tied to no salesman:**
   the customer's account manager, then the primary salesman of his round,
   otherwise blank. The owner's question named only the round; the account
   manager is put first because it is the customer's own choice and is what
   the server already fills first.
2. **A salesman made from a user keeps the user's id as his own,** so no
   document is rewritten. This is invisible to anyone using the application.
3. **Entries such as *Phone order* and *Company staff* earn nothing:** an
   entry marked so cannot be given a commission rule, a payout or a target.
   Commission is otherwise as now.
4. **The collector is not moved to the list:** he remains a member of the
   firm, because he is the one who signs in to work the collection sheet.
5. **One user is at most one salesman,** and one salesman at most one user.
6. **A salesman is never deleted once a document names him;** he is made
   inactive and stays on what he sold.
7. **Required covers the order, the delivery note and the bill only,** not
   the enquiry, the quotation, the return or the notes, which take their
   salesman from what they follow.
8. **Order By prints on the full page only.** The half page is laid out as
   its own sample (backlog 118) and has no such row.
9. **The list carries an optional code** beside the name, as the old
   software's salesman master does, so that an import of the customer's
   data can match on it.
10. **Nothing is limited to one's own records,** as today. A salesman tied
    to a user may sign in and work as his roles allow; what he sees is not
    narrowed to his own bills or targets. If the owner wants that, it is a
    later row of its own.
