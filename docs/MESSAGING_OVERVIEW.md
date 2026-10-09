# Email, WhatsApp and SMS: what is built, how to switch it on, and what is missing

Written 2026-10-09 for the owner, from the code and `docs/MESSAGING_FRAMEWORK.md`.
The step-by-step for a firm's administrator is `docs/MESSAGING_SETUP_GUIDE.md`;
the technical reference is `docs/MESSAGING_FRAMEWORK.md`. This page is the
summary: what a customer can be told today, what needs doing before it works,
and what is not there.

## In one paragraph

Sending by email, WhatsApp and SMS **is built** and ships in every
installation, **switched off**. A firm switches it on for itself and sends
through **its own** accounts, which bill the firm directly. Six events can send
by themselves; a person can also send a bill, a reminder or a statement at any
time. A background job in the server does the sending and the daily reminders.
**It has never been tried against a real provider** -- only against stand-ins
-- so each channel must be proved with a real account before a firm relies on
it.

## What is built

| Part | Built | Where |
| --- | --- | --- |
| A switch per firm, off by default | Yes | Settings > Firm > Messaging |
| Email through the firm's own mailbox (SMTP: Gmail, Outlook, domain mail) | Yes | Channels tab |
| WhatsApp through Meta's WhatsApp Cloud API, approved templates only | Yes | Channels tab |
| SMS through MSG91 on the firm's DLT registration, registered templates only | Yes | Channels tab |
| **Test** an account before it may be switched on | Yes | Channels tab |
| Choose which events send, on which channels, in what order | Yes | Events tab |
| A second channel tried when the first fails | Yes | the order on the event |
| Retry when a provider cannot be reached (after 1, 5, 15 and 60 minutes) | Yes | automatic |
| A log of every message: sent, failed or skipped, and why | Yes | Message log tab, and each document's history |
| Send again | Yes | *Resend* in the log |
| Per customer: no reminders, preferred channel, consent to WhatsApp | Yes | the customer record |
| Passwords and tokens stored encrypted, never shown again | Yes | needs `AGENCY_MESSAGING_KEY` on the server |

## Switching it on

Done once, by the firm's administrator, under **Settings > Firm > Messaging**.

1. Tick **Send messages from this firm**.
2. On **Channels**, enter the firm's own account for a channel, press **Test**,
   then switch the channel on. A channel cannot be switched on until Test
   passes.
3. On **Events**, tick what should send and on which channels, in order.

What each channel needs from the firm:

| Channel | The firm must have | Cost and effort |
| --- | --- | --- |
| Email | A mailbox and an app password | Free; about ten minutes |
| WhatsApp | A Meta Business account, a WhatsApp Business number, and each message **template approved by Meta** | Meta charges per conversation; approval takes days |
| SMS | An MSG91 account, a **DLT registration** (sender ID, entity ID) and each template registered | The provider charges per SMS; DLT takes days |

Nothing here is a setting of the platform's. No firm shares another's account,
and there is no "copy from another firm".

## What sends by itself

Each is off until the firm ticks it on the Events tab.

| Event | When | What the customer gets |
| --- | --- | --- |
| Invoice approved | a sales bill is approved | the bill; **email attaches the PDF** |
| Order approved | a sales order is approved | an order confirmation |
| Delivery dispatched | a delivery note is dispatched | a dispatch notice |
| Receipt recorded | a customer's payment is recorded | an acknowledgement |
| Payment due soon | once a day: a bill falls due within 3 days | a reminder |
| Payment overdue | once a day: the day after due, then every 7 days, until 90 days overdue | a reminder |

The three numbers (3, 7, 90) are the firm's to change. A customer marked *no
reminders* gets neither reminder, and the log says so. A message never blocks,
delays or undoes a document.

## What a person can send on demand

| Button | On | Sends | Needs |
| --- | --- | --- | --- |
| **WhatsApp** | an approved sales invoice | Saves the PDF, opens WhatsApp at the customer's number with the message typed; the person attaches and sends | **Nothing**: no account, no switch |
| **Send** | an approved sales invoice | The bill now, on the channel chosen | Messaging on, the channel working |
| **Send** (email) | quotation, sales order, receipt, customer statement, purchase order | The document as a PDF by email | Email working |
| **Remind** | the Customer Statement screen, or an overdue invoice | **What the customer owes**: a statement from the oldest unpaid bill, the balance, each unpaid bill with days overdue, and the UPI line -- by email, or by WhatsApp by hand | Email working, or nothing for WhatsApp by hand |
| **Resend** | the Message log | The same message again | The channel working |

So dues can be sent on demand today, **one customer at a time**.

## The job that does the sending

- It runs **inside the server**, every 60 seconds, started with the server. No
  separate program or scheduled task is needed.
- Each pass visits every firm's own data, sends what is waiting (up to 50 per
  firm per pass), retries what failed, and, **once a day**, works out the
  reminders.
- `agency-server messaging-run-once` runs one pass by hand, for an operator.
- A firm that switches messaging off stops sending at once; what was waiting
  goes when it is switched back on.
- If the server is not running, nothing is sent; it catches up when started.

## What is missing

Each of these is in `docs/BACKLOG.md` section 94. None is built.

**Before any firm relies on it**

1. **Never tried on a real account.** Email, WhatsApp and SMS were built from
   the providers' published documentation and tested against stand-ins.
2. **Reminders go out at about 5:30 in the morning.** The daily reminder run is
   keyed to the UTC day, which starts at 05:30 India time, and there is no
   "send between these hours" setting.
3. **No delivery report.** A message stays *sent*; whether WhatsApp or SMS
   delivered it is not read back.

**Sending dues**

4. **No "remind everybody who owes" in one go.** Remind is per customer.
5. **No statement on a schedule** (say, every month's first day to every
   customer who owes).
6. **No reminder by collector or route**, and none raised from a broken promise.

**Reach**

7. **Suppliers get nothing automatically.** A purchase order can be emailed by
   hand; a payment made to a supplier, or a purchase return, tells nobody.
8. **WhatsApp and SMS carry text only**: no PDF, no link to the bill, no
   payment link.
9. **Events that do not exist**: credit note or sales return approved, a cheque
   bounced, an order cancelled, a delivery proved, a quotation sent or about to
   lapse, a credit limit nearly reached, loyalty points earned or about to
   expire, a new offer or coupon.
10. **Nothing goes to the firm's own people**: no message to the owner for the
    day's sales and collections, to a salesman for an order approved, to an
    approver for something waiting.

**Running it**

11. **One provider per channel.** No second SMS or WhatsApp provider to choose.
12. **Nobody is told when a channel breaks.** It shows *Needs attention* on the
    Messaging page; no alert goes to the administrator.
13. **No count of what was sent** by channel and event for a month, to check
    against the provider's bill.
14. **No hours or daily limit**: nothing stops a message at night, or caps how
    many go to one customer in a day.

## For a demonstration

Only **WhatsApp by hand** on an invoice works without setting anything up.
Showing a bill arriving by email needs a mailbox and its app password, entered
by the firm's administrator on the Messaging page.
