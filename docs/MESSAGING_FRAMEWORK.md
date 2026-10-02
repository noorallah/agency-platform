# Messaging — email, WhatsApp and SMS, switched on by the firm

Sending documents, payment reminders and notices by email, WhatsApp and SMS.
**Built 2026-10-01** (`backend/app/messaging`, migration `20261001_0185`),
from `docs/BACKLOG.md` §51 and the owner's decisions of 2026-10-01, which
override the design this doc carried before (recorded under *What changed from
the design* below). How a firm sets up its accounts is
`docs/MESSAGING_SETUP_GUIDE.md`.

## The rule: built in, off, and the firm brings its own account

Every installation carries the code. Nothing is sent until the firm's
administrator, on the firm's own **Settings → Messaging** page:

1. switches messaging on for the firm (the master switch, off by default);
2. enters **its own** provider account for a channel, passes **Test**, and
   switches the channel on;
3. chooses which **events** send, on which channels, with which template.

The provider bills the firm directly. The platform never holds a shared
account, never pays for a message, and one firm's spam complaint cannot stop
another firm's messages (§51, decision 1). Each firm has its own page and its
own settings; there is deliberately no "copy from another firm".

**When messaging is off, every document behaves exactly as it did before** --
not one row is written for it, not even a skipped one. A failed or skipped send
never blocks, delays or undoes a document (§51, decision 4).

## Four switches, each a different owner

| Level | Where it lives | Who turns it | What it means |
| --- | --- | --- | --- |
| **Firm** | `messaging_settings.is_enabled` | Firm administrator (`SETTINGS_UPDATE`) | Messaging on or off for the whole firm |
| **Channel** | `messaging_channel_configs` | Firm administrator (`SETTINGS_UPDATE`) | Email / WhatsApp / SMS: the provider account, its health, on or off |
| **Event** | `messaging_event_configs` | Firm administrator (`SETTINGS_UPDATE`) | Which events send, on which channels in which order, with which template |
| **Party** | `customers.no_reminders`, `preferred_channel`, `whatsapp_opt_in` | Staff with customer edit rights | Opt out of reminders; channel tried first; consent to WhatsApp |

There is **no business-profile gate** (owner, 2026-10-01): messaging is not a
`business_features` code and no route calls `require_feature`. The firm's own
master switch is the gate.

Reading the page takes `SETTINGS_VIEW`; changing it `SETTINGS_UPDATE` -- the
codes the firm's numbering series and print templates already use, and which
`FIRM_ADMIN` holds. Sending a document by hand and resending take
**`DOCUMENT_SEND`** (§51, decision 5), seeded in its own `messaging` group,
operational (so `FIRM_ADMIN` and `FIRM_MANAGER` hold it) and granted to
`SALES_MANAGER`, `ACCOUNTANT` and `BILLING_EXECUTIVE`. The message log opens to
either `DOCUMENT_SEND` or `SETTINGS_VIEW`.

## Channels and providers

One provider per channel in this release (owner, 2026-10-01). Each is an
adapter behind one interface (`app/messaging/providers/base.py`):

```
required_fields() -> the account form's fields (name, label, secret, kind, ...)
send(message)     -> provider message id, or ProviderError(permanent=...)
fetch_status(id)  -> DELIVERED / READ / FAILED, or None when it cannot say
test_connection() -> proves the account, messages nobody
```

The settings page draws its account form from `required_fields`, so a second
provider for a channel is one more adapter in `ADAPTERS` and no screen change.

| Channel | Provider | Fields | Test does | Status |
| --- | --- | --- | --- | --- |
| Email | `SMTP` -- the firm's own mailbox (Gmail/Outlook app password, or domain mail) | host, port, security (STARTTLS/SSL/NONE), username, **password**, from address, sender name | connect, secure, sign in, NOOP | stays *sent*: SMTP has no status to fetch; a bounce returns to the firm's mailbox |
| WhatsApp | `META_CLOUD` -- Meta WhatsApp Cloud API, direct | phone number ID, business account ID, **access token** | reads the phone number's own record | stays *sent*: the Cloud API reports delivery only by webhook |
| SMS | `MSG91` on the firm's DLT registration | **auth key**, DLT sender ID (6 chars), DLT entity ID | reads the transactional balance | stays *sent*: MSG91 reports delivery only by webhook |

**Bold** fields are secret. HTTP is `urllib` and mail is `smtplib` -- no new
dependency, nothing the Nuitka build has to learn about.

**WhatsApp and SMS send templates only.** WhatsApp delivers business-initiated
messages only as templates Meta has approved; Indian SMS only as DLT-registered
templates. So each event names, per channel, the provider's template (Meta
template name and language; MSG91 template id) and the event's **variables are
filled in order** -- `{{1}}` / `var1` is the first variable the event lists,
`{{2}}` / `var2` the second. That order is a contract with every template a
firm has had approved, so `app/messaging/events.py` may only ever append to it.
Email uses the firm's subject and body (with `{customer_name}` placeholders),
or the defaults, and **attaches the invoice PDF** (§51, decision 3) from the
same builder `GET /sales-invoices/{id}/print` uses.

### Not supported, deliberately

Unofficial WhatsApp libraries (pywhatkit, whatsapp-web.js) and "phone as SMS
gateway" apps: they break the providers' terms, get the firm's number banned,
and fail at volume.

## Events

| Code | When | Document | Variables, in order |
| --- | --- | --- | --- |
| `SALES_INVOICE_APPROVED` | a bill is approved | sales invoice (email attaches the PDF) | customer_name, document_number, document_date, amount, due_date, firm_name |
| `SALES_ORDER_APPROVED` | an order is approved | sales order | customer_name, document_number, document_date, amount, firm_name |
| `DELIVERY_DISPATCHED` | a delivery note is dispatched | delivery note | customer_name, document_number, document_date, firm_name |
| `RECEIPT_POSTED` | a customer receipt is recorded | receipt | customer_name, document_number, document_date, amount, firm_name |
| `PAYMENT_DUE_SOON` | daily scan: an unpaid bill falls due within *n* days (`due_soon_days`, default 3) | sales invoice | customer_name, document_number, amount_due, due_date, firm_name |
| `PAYMENT_OVERDUE` | daily scan: the day after due, then every *n* days while owed (`overdue_every_days`, default 7), and not once a bill is more than `overdue_stop_after_days` (default 90) past due -- so switching reminders on never messages a customer about years-old bills (decision A12) | sales invoice | customer_name, document_number, amount_due, due_date, days_overdue, firm_name |

The two payment events are **reminders**: a customer marked *no reminders* gets
a SKIPPED row with the reason instead (§51, decision 7). What a bill still owes
is read from `ReceiptService.outstanding_invoices`, the same derivation the
ageing uses -- never a stored figure.

## How a message travels

```
document service (in its own transaction)          daily reminder scan
        │  stage_document_event(...)                     │
        ▼                                                 ▼
MessagingService.stage_event  ── savepoint; any failure is logged and swallowed
        │  firm switched on?  event chosen?  already asked for?
        │  reminder and customer opted out?  → SKIPPED, on the timeline
        │  first usable channel in the event's order (customer's preferred first):
        │     channel on and Test passed, customer has an address, WhatsApp opt-in
        │  none usable                                  → SKIPPED, reasons on the timeline
        ▼
messaging_outbox row, QUEUED  ── commits or rolls back WITH the document
        ▼
outbox worker (thread in the server; `agency-server messaging-run-once`)
        │  claim: SENDING, attempts+1, COMMIT  -- before the provider is called
        ▼
adapter.send
   ├─ ok                → SENT, provider id; MESSAGE_SENT on the timeline
   ├─ unreachable       → QUEUED again after 1, 5, 15, 60 minutes; then as refused
   └─ refused           → FAILED; channel NEEDS_ATTENTION; MESSAGE_FAILED on the
                          timeline; a new QUEUED row on the next usable channel
        ▼
status fetch (every 15 min for 3 days, where the adapter supports it)
```

- **In the document's transaction.** `stage_event` adds the outbox row to the
  session the document is being written on and never commits. A document that
  rolls back leaves no message; one that commits has its message queued. It
  runs inside `begin_nested()` and swallows every exception, so a missing table
  in an unmigrated store or a bug here cannot block or undo the document.
- **Once only.** One message per `(event, document, channel, occurrence)`,
  held by the partial unique index `UQ_messaging_outbox_firm_dedupe_active`
  and checked before staging. The occurrence is empty for a document event,
  `DUE-<date>` for a due-soon reminder and `OVERDUE-<cycle>` for each overdue
  cycle. **Resend** (and a person's Send) carries no key, which is what makes
  it the only way anything goes twice.
- **Never sent twice by itself.** A row is marked SENDING and committed before
  the provider is called. A row still SENDING after 15 minutes was interrupted:
  whether it reached the customer cannot be known, so it is marked FAILED with
  "use Resend" and never retried automatically.
- **No webhooks.** The server sits inside the office and a provider cannot call
  in (§51), so status is fetched on a timer where the provider offers a way; a
  message is never shown *delivered* on a guess. None of the three providers
  offers one today, so their messages stop at *sent*; the fetch loop is there
  for the next adapter that can say.
- **Held for the IRN** (§77 row 6, A43). An email attaching a B2B invoice
  the firm must e-invoice is not a valid tax invoice until the invoice has its
  IRN, so the worker leaves it QUEUED with the reason ("Waiting for SI-1's
  IRN") and looks again every 5 minutes; it goes on the first pass after the
  registration. A person's Send by email is refused at once instead. WhatsApp
  and SMS are not held -- they name the invoice and attach nothing. Rows
  waiting (a retry backing off, an email held) are filtered out in the
  worker's query, so a firm with many cannot crowd the rows behind them.
- **Every send is on the document's timeline** -- `document_lifecycle_events`
  with action `MESSAGE_SENT`, `MESSAGE_FAILED` or `MESSAGE_SKIPPED`, the channel,
  recipient (`email_recipient` for email), reason and message id in
  `details_json`, and the requesting user as actor. The whole log, across
  documents, is `GET /api/v1/messaging/messages` and the page's Message log.

## Credentials

- Entered on the firm's Messaging page by its administrator; **never returned**
  -- a channel reports its public fields and the *names* of the secrets it
  holds (`secrets_set`), and the page offers only *Replace* and *Test*. A
  secret left blank on Replace keeps the one saved.
- **Sealed at rest** in `messaging_channel_configs.credentials_encrypted` under
  `AGENCY_MESSAGING_KEY` from `config\.env`, never under anything in the
  database (§51, decision 2). `app/core/security/secret_box.py` is standard
  library only (the release is compiled with Nuitka): purpose-bound keys
  derived with HMAC-SHA256, a random 16-byte nonce, an HMAC-SHA256 counter-mode
  keystream, and **encrypt-then-MAC** with a constant-time tag check before
  anything is decrypted. Stored as `v1.<base64>`, so a later release can change
  the construction and still read this one's.
- **The key, like the JWT key.** Development and testing fall back to a fixed,
  published development key. **Staging and production have no fallback**: with
  no key (or the development one) the server still starts -- messaging is
  optional -- but no firm can save an account, and the page says the operator
  must set `AGENCY_MESSAGING_KEY`. `install\install.ps1` generates one on a
  fresh install and adds one to an existing `config\.env` that lacks it. **Never
  change it on a server where firms have saved accounts**: they would have to
  enter them again (Test reports the account as unreadable).
- **Never logged.** `docs/LOGGING.md`'s redaction list carries `authkey`,
  `access_token`, `password` and `credentials`; a provider's error text has
  every saved secret value scrubbed out before it is stored or shown; HTTP
  errors never include the URL (MSG91's balance check carries the key in one).
- **Every change is audited** -- who, when, which channel, which fields, never
  a secret's value.
- Saving an account switches the channel **off** and back to *untested*: a
  changed account has not been shown to work, and **only a passed Test lets a
  channel on**. A refusal from the provider later marks it *needs attention*,
  and a channel needing attention is passed over until it is tested again.

## Data

All firm-owned, in every firm store; none carries a foreign key to `firms`.

- **`messaging_settings`** -- per firm: `is_enabled` (default false),
  `due_soon_days` (3), `overdue_every_days` (7), `overdue_stop_after_days` (90, migration 0220), `last_reminder_scan_on`.
- **`messaging_channel_configs`** -- per firm and channel: `provider`,
  `is_enabled`, `public_settings` (JSON), `credentials_encrypted`, `health`
  (`NOT_CONFIGURED` / `UNTESTED` / `OK` / `NEEDS_ATTENTION`), `last_tested_at`,
  `last_error`.
- **`messaging_event_configs`** -- per firm, event and channel: `is_enabled`,
  `priority` (the fallback order), `template_name`, `template_language`,
  `subject`, `body`.
- **`messaging_outbox`** -- one row per message: event, document type / id /
  number, customer, channel, provider, recipient, status (`QUEUED`, `SENDING`,
  `SENT`, `DELIVERED`, `READ`, `FAILED`, `SKIPPED`), reason, rendered subject
  and body, template and ordered `variables`, `attach_pdf`,
  `fallback_channels`, `occurrence`, `dedupe_key`, `is_resend`,
  `previous_message_id`, `requested_by`, attempts, `next_attempt_at`,
  provider message id, sent / delivered / status-checked times.
- **Customers** -- `no_reminders`, `preferred_channel`, `whatsapp_opt_in` and
  `whatsapp_opt_in_at` (set by the server when the box is ticked, cleared when
  unticked; a client cannot send it). Audited with the customer.

## API

All under `/api/v1/messaging`, firm-scoped by `X-Firm-ID`.

| Route | Permission | Does |
| --- | --- | --- |
| `GET /settings`, `PUT /settings` | `SETTINGS_VIEW` / `SETTINGS_UPDATE` | master switch and schedule; `can_store_credentials` |
| `GET /providers`, `GET /events` | `SETTINGS_VIEW` | the account forms' fields; the events and their variables |
| `GET /channels` | `SETTINGS_VIEW` | each channel's provider, health, public fields, secret names |
| `PUT /channels/{channel}` | `SETTINGS_UPDATE` | save or replace an account (`{provider, settings}`) |
| `POST /channels/{channel}/test`, `/enable`, `/disable` | `SETTINGS_UPDATE` | Test; switch on (refused unless Test passed); switch off |
| `GET /event-configs`, `PUT /event-configs/{event_code}` | `SETTINGS_VIEW` / `SETTINGS_UPDATE` | which channels each event uses, in order, with templates |
| `GET /messages` | `DOCUMENT_SEND` or `SETTINGS_VIEW` | the message log, paginated, newest first |
| `POST /send` | `DOCUMENT_SEND` | send an approved invoice now on one channel (email attaches the PDF) |
| `POST /messages/{id}/resend` | `DOCUMENT_SEND` | send a message again |

A person's **Send** on an invoice borrows the template the firm named for
`SALES_INVOICE_APPROVED` on that channel, so WhatsApp and SMS need one named
there first; it is refused while messaging is off or the channel cannot send.

## Running it

- The server starts the worker in its lifespan (`AGENCY_MESSAGING_WORKER_ENABLED`,
  default on; `AGENCY_MESSAGING_WORKER_INTERVAL_SECONDS`, default 60). Each pass
  walks every live firm from the registry and opens **that firm's own store**
  (`app/messaging/services/runtime.py`), so a DATABASE-mode firm on another
  server is reached where its outbox lives; a store it cannot read is logged
  and the pass continues.
- `agency-server messaging-run-once` runs one pass over every firm and exits
  non-zero if a store could not be reached -- for operators and tests.
- The reminder scan runs once per UTC day per firm, inside the first pass of
  the day.
- A firm that switches messaging **off** stops sending at once: what it had
  queued waits, and goes when it switches back on.

## What changed from the design (owner, 2026-10-01)

- **No business-profile gate.** The design had `MESSAGING_EMAIL` /
  `MESSAGING_PROVIDER` feature codes the platform administrator would allow per
  profile; the owner decided messaging is a feature the firm turns on itself.
  No feature code was seeded.
- **Per firm, no copying** between firms.
- **Providers chosen**: SMTP, Meta Cloud API direct (not a partner/BSP), MSG91.
- **Templates live on the event**, not in a separate `messaging_templates`
  table: one event's channel row names the provider template it uses.
- **Reminder defaults**: 3 days before due; overdue the day after due and every
  7 days (§51, open question 4).

## Not built yet

- Phase A2 (open WhatsApp on the PC with the text typed in), A3 (UPI QR on the
  invoice), A4 (Remind from the overdue list and statements) and B4 (payment
  links) of §51.
- Sending documents other than the sales invoice by hand; attaching a PDF to
  any event but the invoice's.
- WhatsApp media (a PDF in a document-header template) -- WhatsApp and SMS send
  link-free template text.
- Vendors: the party preferences exist on customers only.
- **Verification against the real providers** needs a firm's own accounts; the
  adapters were built from the providers' published APIs and are tested only
  against fakes. Check each with a real account before a firm relies on it.

## Sources

- [WhatsApp Business API pricing in India, 2026 -- MyOperator](https://myoperator.com/blog/whatsapp-business-api-pricing-india-2026)
- [A2P SMS pricing in India, 2026 -- Message Central](https://www.messagecentral.com/blog/a2p-sms-pricing-india)
- [DLT registration, 2026 -- SMSGatewayHub](https://www.smsgatewayhub.com/dlt-registration)
- [Meta WhatsApp Cloud API documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
