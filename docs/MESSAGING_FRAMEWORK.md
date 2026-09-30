# Messaging — email, WhatsApp and SMS, switched on by the firm

Design for sending documents, payment reminders and other notifications by
email, WhatsApp and SMS. **Not built yet.** The plan and its open decisions are
`docs/BACKLOG.md` §51 (which takes up §14 and §42.1); this doc is the detail
behind Phase B of that plan and the rule that the whole thing ships **off** and
is turned on by each firm with its own provider account.

Written 2026-09-30. Prices are indicative for India as of that date -- re-check
before building.

## The rule: built in, off, and the firm brings its own account

Every installation carries the code. Nothing is sent until:

1. the firm's **business profile** allows the feature (the platform decides --
   this is where it can be sold as an add-on), and
2. the firm's administrator has entered **its own** provider account in
   **Settings → Messaging**, passed **Test**, and switched the channel on.

The provider bills the firm directly. The platform never holds a shared
account, never pays for a message, and one firm's spam complaint cannot stop
another firm's messages (§51, decision 1).

When messaging is off, every document behaves exactly as it does today. A
failed or skipped send never blocks, delays or undoes a document (§51,
decision 4).

## Four switches, each a different owner

| Level | Where it lives | Who turns it | What it means |
| --- | --- | --- | --- |
| **Feature** | `business_features` codes, per profile through `profile_features` | Platform administrator | The firm may use this at all. Enforced with `require_feature(...)` on the messaging write endpoints (`app/business/gating.py`) |
| **Channel** | The firm's messaging settings | Firm administrator (`SETTINGS_UPDATE`) | Email / WhatsApp / SMS on or off, with the provider and its credentials |
| **Event** | The firm's messaging settings | Firm administrator | Which events send automatically (invoice raised, reminder before due, overdue, receipt), and by which channels |
| **Party** | The customer / vendor | Staff | *No reminders* opt-out (§51, decision 7); preferred channel; WhatsApp opt-in |

Proposed feature codes (seeded **`default_enabled = false`**, **`is_implemented
= false`** until the code ships -- see the `is_implemented` note in
`app/business/models/framework.py`):

- `MESSAGING_EMAIL` -- email a document, Phase A1.
- `MESSAGING_PROVIDER` -- automatic sending through a paid provider: WhatsApp
  Business API and SMS, Phase B1-B3.
- `PAYMENT_LINKS` -- Razorpay / Cashfree links, Phase B4.

Phase A2 (open WhatsApp on the PC with the text typed in) and A3 (UPI QR on the
invoice) cost nothing and need no account, so they need no feature code.

**A channel cannot be switched on until its credentials are saved and Test has
passed.** If the provider later refuses (expired token, balance exhausted,
template withdrawn), the channel is marked *needs attention*, a strip says so in
the desktop client, and sends fall to the next channel the firm enabled.

## Channels and what the firm has to arrange (India)

### Email -- no cost

The firm's own mail account over SMTP: Gmail or Outlook with an app password,
or its domain mail. Attach, not link (§51, decision 3).

### WhatsApp Business API

- A Meta Business account (verification recommended) and a phone number **not**
  already on the WhatsApp app.
- Every message is a **template approved by Meta**. Billing messages are the
  *Utility* category.
- The party must have opted in.
- Two ways to connect, both behind the same adapter:
  - **Meta Cloud API direct** -- no platform fee, only Meta's per-message rate.
  - **A partner (BSP)** -- Interakt, AiSensy, Gupshup, MSG91 -- adds a dashboard
    and support for about ₹999-9,999 a month or ₹0.10-0.30 a message on top.
- Approximate Meta rates, India, 2026, before 18% GST: utility and
  authentication about ₹0.115 a message; marketing about ₹0.86. Replies inside
  the 24-hour customer-service window were free; reported to become chargeable
  from 1 Oct 2026, with 1,000 a month free per number.

### SMS

- **DLT registration** with a telecom operator is mandatory (TRAI): the firm
  registers as a principal entity (about ₹5,900 once), a 6-character sender ID,
  and each message template (usually approved in 24-48 hours). Documents: GST
  certificate, PAN, CIN or Udyam certificate, the signatory's ID. **The firm's
  paperwork, not ours** -- the product only stores the sender ID and each DLT
  template ID.
- Providers: MSG91, 2Factor, Textlocal, Twilio's Indian route.
- Transactional SMS about ₹0.12-0.20 a message; reaches DND numbers.

### Not supported, deliberately

Unofficial WhatsApp libraries (pywhatkit, whatsapp-web.js) and "phone as SMS
gateway" apps. They break the providers' terms, get the firm's number banned,
and fail at volume. A2 (open WhatsApp with the text typed in) is the free
option, and it is honest about needing a person to press send.

## No webhooks: the server fetches status

The server sits inside the office and a provider cannot call in (§51). So:

- Sending is outbound only.
- Delivery status (sent / delivered / read / failed) is **fetched** by the
  server on a timer from the provider's API, where the provider offers it.
- Where a provider has no status API, the record stops at *sent*. It is never
  shown as *delivered* on a guess.

A firm that does expose its server publicly may later get a webhook receiver as
an option; the design must not depend on it.

## Shape of the code

```
document service / reminder schedule
        │  event: SALES_INVOICE_RAISED, PAYMENT_DUE, PAYMENT_OVERDUE, RECEIPT_POSTED
        ▼
MessagingService.request(firm, event, party, document)
        │  feature allowed?  event on?  channel on and healthy?  party opted in?
        │  otherwise: record *skipped* with the reason, return -- never raise
        ▼
outbox row (queued)  ── the server may be offline when a send is asked for
        ▼
outbox worker, with retry and back-off
        ▼
channel adapter  ── one interface for every provider
   ├─ SmtpAdapter
   ├─ WhatsAppCloudAdapter / WhatsAppPartnerAdapter
   └─ SmsAdapter (MSG91, ...)
        ▼
status fetcher (timer) ── updates the outbox row and the document timeline
```

- **One adapter interface:** `send(to, template, variables, attachment) ->
  provider_message_id`, `fetch_status(provider_message_id)`,
  `test_connection()`, and `required_fields()` -- the list of credential fields
  that provider needs. The settings screen draws its form from that list, so
  adding a provider changes no screen.
- **Idempotent:** one send per `(event, document, channel)` unless a person
  presses *Resend*.
- **Every send is on the document's timeline** -- channel, to whom, by whom,
  when, and sent / failed / skipped with the reason (§51, A5).
  `document_timeline.email_recipient` and `document_states.allows_email` already
  exist for this.
- **Sending is its own permission**, `DOCUMENT_SEND` (§51, decision 5).

## Credentials

- Entered once in Settings → Messaging by the firm administrator.
- Stored **encrypted**, with the key in the server's config and not in the
  database (§51, decision 2).
- Never shown again after saving: the screen offers only *Replace* and *Test*.
- Never logged -- `docs/LOGGING.md` already redacts `token`, `secret`,
  `api_key` and `password`; check each provider's own key names (MSG91's
  `authkey`, Meta's `access_token`) are covered, and add any that are not.
- Every change is audited: who, when, which channel, never the value.

## Data (draft -- confirm against `docs/TABLE_CATALOGUE.md` before migrating)

- **`messaging_channel_configs`** -- per firm and channel: provider,
  `is_enabled` (default false), encrypted credentials, health (`NOT_CONFIGURED`
  / `OK` / `NEEDS_ATTENTION`), last tested at, last error.
- **`messaging_event_configs`** -- per firm and event: enabled, channels in
  order, the template per channel.
- **`messaging_templates`** -- per firm: code, channel, the provider's template
  ID (Meta template name or DLT template ID), language, variables, preview text.
- **`messaging_outbox`** -- one row per send: firm, event, document, party,
  channel, rendered variables, provider message ID, status, attempts, last
  error, timestamps.
- Party fields: `no_reminders`, preferred channel, WhatsApp opt-in with the date
  it was given.
- Reminder schedule per firm (for example 3 days before the due date, on it,
  then every 7 days) -- §51, open question 4.

## Order of work

1. Feature codes seeded off; channel config table with encryption; Settings →
   Messaging screen with Test.
2. `MessagingService`, outbox and worker; the timeline record; `DOCUMENT_SEND`.
3. SMTP adapter and *Email* on each document's bar (A1). A2-A5 alongside.
4. WhatsApp adapter (Meta Cloud API first), templates, automatic reminders (B2,
   B3), status fetcher.
5. SMS adapter (B1).
6. Payment links with the draft receipt (B4).
7. A guide for firms: how to open a Meta WhatsApp Business account, and how to
   do DLT registration.

Tests to write with it: messaging off changes nothing about a document; a
channel without a passing Test cannot be enabled; a provider failure falls back
and is on the timeline; a resend is the only way to send twice; no credential
appears in any log line or response body.

## Open (adds to §51's list)

- Sell `MESSAGING_PROVIDER` as a paid add-on through the profile, or allow it
  for every profile and let the provider cost be the only gate?
- Which WhatsApp route first: Meta direct or one partner?

## Sources

- [WhatsApp Business API pricing in India, 2026 -- MyOperator](https://myoperator.com/blog/whatsapp-business-api-pricing-india-2026)
- [A2P SMS pricing in India, 2026 -- Message Central](https://www.messagecentral.com/blog/a2p-sms-pricing-india)
- [DLT registration, 2026 -- SMSGatewayHub](https://www.smsgatewayhub.com/dlt-registration)
- [Meta WhatsApp Cloud API documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
