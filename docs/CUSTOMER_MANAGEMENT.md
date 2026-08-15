# Customer Management Reference Module

Customer Management is the first complete firm-scoped ERP business module. It
is the reference implementation for Vendor, Product, Employee, Warehouse, and
future master-data modules.

## Data model

Migration `20260731_0009_customer_management` creates:

| Table | Purpose |
| --- | --- |
| `customers` | Firm-owned identity, tax, communication, financial, status, audit, and soft-delete data |
| `customer_addresses` | Multiple billing, shipping, office, home, or other addresses |
| `customer_contacts` | Multiple customer contact persons |

Every table uses the shared UUID, timestamp, actor, version, and lifecycle
columns. `customers.firm_id` references `firms.id`. Customer code, GST number,
and PAN number are unique within a firm. Addresses and contacts are owned by a
customer and are reconciled as part of the customer transaction.

`credit_limit` and `opening_balance` use `NUMERIC(18,2)`.
`payment_terms_days` is a non-negative integer. Customer types are
`INDIVIDUAL` and `BUSINESS`; statuses are `ACTIVE`, `INACTIVE`, and `ON_HOLD`.

## Permissions

| Permission | Capability |
| --- | --- |
| `CUSTOMER_CREATE` | Create customers in the active firm |
| `CUSTOMER_VIEW` | List, search, view, summarize, and read child records |
| `CUSTOMER_UPDATE` | Edit customers, addresses, contacts, and financial terms |
| `CUSTOMER_DELETE` | Soft delete customers |
| `CUSTOMER_RESTORE` | Restore soft-deleted customers |
| `CUSTOMER_EXPORT` | Export visible customers as CSV |
| `CUSTOMER_IMPORT` | Atomically import validated JSON customer batches |

System role mappings are seeded idempotently. The backend remains authoritative
for every action even when the desktop hides unauthorized controls.

## Firm security

The desktop sends the selected firm in `X-Firm-ID`. Ordinary users must have an
active, non-deleted `user_firms` membership for that identifier. Every query and
mutation is scoped to it. Platform administrators must also provide the header:
platform authority never turns a firm-owned endpoint into an unscoped query.

## REST API

| Method and path | Permission | Purpose |
| --- | --- | --- |
| `GET /api/v1/customers` | View | Paginated search, sorting, and filters |
| `POST /api/v1/customers` | Create | Create a customer with addresses and contacts |
| `GET /api/v1/customers/{id}` | View | Get a complete customer. Answers an `ETag` carrying the version |
| `PUT /api/v1/customers/{id}` | Update | Replace editable customer and child data. Accepts `If-Match`; answers a new `ETag` |
| `DELETE /api/v1/customers/{id}` | Delete | Soft delete |
| `POST /api/v1/customers/{id}/restore` | Restore | Restore |
| `GET /api/v1/customers/summary` | View | Lifecycle and financial aggregates |
| `GET /api/v1/customers/{id}/addresses` | View | List customer addresses |
| `GET /api/v1/customers/{id}/contacts` | View | List customer contacts |
| `GET /api/v1/customers/export` | Export | Download matching CSV |
| `POST /api/v1/customers/import` | Import | Import `{ "records": [...] }` atomically |

List search covers code, name, display name, GST, PAN, email, phone, city, and
status. Filters support status, customer type, city, state, creation-date range,
and deleted records within the selected firm. Sort fields are whitelisted:
code, name, status, credit limit, and creation date.

## Balances

A customer carries three figures, and only one of them is an input.

| Field | Written by |
| --- | --- |
| `opening_balance` | The user, at create. Effectively frozen afterwards |
| `current_outstanding` | Receivable activity — invoices, receipts, credit notes, returns |
| `unapplied_advance_balance` | Money received against no invoice |

**An opening balance posts to the ledger.** Creating a customer with one debits
Accounts Receivable and credits Opening Balance Equity: a day-one receivable
arrived from nowhere the ledger can see, and what it represents is what the
owners brought into the business. A customer in credit swaps the legs. It is
**refused** rather than skipped when the firm has no chart of accounts or no
open period — a balance nobody can book is one the firm should not be told it
has recorded. The customer itself still opens; it is the balance that cannot.
Revising one, or deleting the customer, mirrors the entry.

**`current_outstanding` is not recomputed on update.** It is derived from
receivable activity, and the only moment the opening figure is the whole truth
about it is before any of that activity exists. `update` therefore touches the
balances **only when `opening_balance` itself changed** — which the guard below
restricts to customers with no receivable transactions.

That guard is what makes the rule safe, and the rule is what the guard is for:
`update` refuses a changed `opening_balance` once receivable activity exists.
Until 2026-08-15 the balances were recomputed on every call regardless, so
editing a phone number reset `current_outstanding` to the opening balance and
put the receivable control account out by everything the customer had traded.
`scripts/verify_sample_data.py` reports that as "a balance moved without a
journal".

Money is recorded through `/api/v1/receipts` and `/api/v1/payments`, which post.
`CustomerService.post_receivable_transaction` moves a balance without writing a
journal and is the older, lower-level path — the two books drift by every rupee
recorded through it.

## Concurrent edits

`PUT /api/v1/customers/{id}` replaces the **whole** address and contact
collection, so two people editing one customer do not merge badly — the loser
loses every row they entered. `If-Match` is how a client refuses that: send the
version last read and a write aimed at a superseded one is refused with 409.

The version to send is published as an `ETag` on `GET` and on `PUT` itself.
Echo the header you were given rather than computing the next number: an update
can advance the counter by more than one. Sending nothing, or `*`, means no
precondition and is accepted — the guarantee is opt-in, and the desktop does
not use it yet.

## Validation and audit

Pydantic validates required values, formats, identifier normalization, E.164
phone numbers, email addresses, decimal bounds, payment terms, and unique
default address/contact selections. The service validates firm-local duplicate
code, GST, and PAN values and database constraints protect concurrent writes.

Create, update, soft delete, and restore each append an immutable `audit_logs`
entry in the same transaction. The desktop Audit tab displays entity actor and
timestamp metadata; complete mutation history remains in the shared audit log.

## Desktop workflow

Customers is an authorized tab under **Masters**. It composes the shared
`ManagementWorkspaceLayout`, toolbar, search/filter panel, data grid, summary
panel, status bar, notifications, confirmations, loading/empty states, context
menu, copy support, and keyboard shortcuts.

The shared `WorkspaceDialog` hosts General, Address, Contacts, Financial, and
Audit tabs. Address and contact collections edit inline to avoid nested modal
dialogs. Ctrl+N creates, Ctrl+S saves, Ctrl+F focuses search, Delete requests a
soft-delete confirmation, F5 refreshes, and Ctrl+C copies the selected row.
Right-click actions are View, Edit, Delete or Restore, Copy, Refresh, and
Export according to state and permissions.

## Extension points

Future additions should attach through domain services and dedicated tabs or
summary providers without changing the customer identity contract:

- attachments and documents
- customer groups and tags
- loyalty programs and credit holds
- geolocation
- sales history and outstanding balances
- statements
- communication history

Future master modules should copy the domain layering and component composition,
not customer-specific widgets or persistence code.
