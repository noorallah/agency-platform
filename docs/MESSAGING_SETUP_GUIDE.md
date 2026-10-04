# Sending bills and reminders by email, WhatsApp and SMS — setting it up

For the firm's administrator. Messaging is **off** until you switch it on, and
it sends through **your own** accounts: your mailbox, your WhatsApp Business
number, your SMS provider. Each provider bills you directly; the software
charges nothing for messages.

You can set up one channel, two or all three. Email costs nothing and takes ten
minutes, so most firms start there.

Everything below is done once, under **Settings → Firm → Messaging** (the gear at
the right of the menu bar, then the Firm section).

## 1. Switch messaging on

Tick **Send messages from this firm**. Set the reminder schedule if the
defaults do not suit you: a *due soon* reminder 3 days before a bill falls due,
and an *overdue* reminder the day after it falls due and every 7 days while it
is still owed -- until it is 90 days overdue (*stop after n days*), so a bill
unpaid for years is not suddenly chased the day you switch reminders on.

If the page says the server cannot store accounts, ask whoever installed the
software to set `AGENCY_MESSAGING_KEY` in the server's `config\.env` and
restart it. (The installer does this for you on a new installation.)

## 2. Email — your own mailbox (Gmail, Outlook or your domain)

Email goes out from your own address, with the invoice PDF attached.

**Gmail or Google Workspace**

1. Turn on 2-Step Verification for the Google account
   (myaccount.google.com → Security).
2. Create an **app password**: myaccount.google.com → Security → 2-Step
   Verification → App passwords. Name it "Billing". Google shows a 16-letter
   password once -- copy it.
3. On the Email channel, choose **Set up**: server `smtp.gmail.com`, port
   `587`, security `STARTTLS`, user name and *send from* your Gmail address,
   password the 16-letter app password (not your normal password).

**Outlook / Microsoft 365**

1. Turn on two-step verification for the account, then create an **app
   password** (account.microsoft.com → Security → Advanced security options →
   App passwords). For a company Microsoft 365 mailbox your IT administrator
   may have to allow "Authenticated SMTP" for it.
2. Server `smtp.office365.com`, port `587`, security `STARTTLS`, user name and
   *send from* your address, password the app password.

**Your own domain's mail** -- ask your mail host for the SMTP server, port
(587 with STARTTLS, or 465 with SSL), user name and password.

Then press **Test**. When it says *Test passed*, press **Switch on**.

## 3. WhatsApp — Meta's WhatsApp Business Platform (Cloud API)

WhatsApp is the most read channel, but Meta only lets a business start a
conversation with a **template it has approved**, and only with customers who
**agreed** to hear from you. Meta charges per message (about ₹0.12 for a
billing or reminder message in India in 2026, plus GST).

What you need:

1. **A Meta Business account** -- business.facebook.com. Verifying your
   business (GST certificate or similar) is recommended and lifts the low
   starting limits.
2. **A phone number not already on WhatsApp** -- a new SIM or a landline that
   can receive an SMS or call. A number in use on the WhatsApp app has to be
   deleted from the app first.
3. In **developers.facebook.com** create an app of type *Business*, add the
   **WhatsApp** product, and add your number under WhatsApp → API Setup. Note
   the **Phone number ID** (a long number -- not the phone number itself) and
   the **WhatsApp Business Account ID**.
4. **A permanent access token.** The token on the API Setup page expires in 24
   hours. In Business Settings → Users → **System users**, add a system user,
   give it the app and the WhatsApp account, and **Generate token** with the
   `whatsapp_business_messaging` and `whatsapp_business_management`
   permissions and no expiry. Copy it.
5. **Templates.** In WhatsApp Manager → Message templates, create one per
   message you want to send, category **Utility**. The body uses numbered
   variables, filled in the order the Messaging page lists for that event. For
   *Invoice approved* that order is customer name, invoice number, date,
   amount, due date, your firm's name -- so a template might read:

   > Dear {{1}}, your invoice {{2}} dated {{3}} for Rs {{4}} is due on {{5}}. Thank you, {{6}}.

   Approval usually takes minutes to a day.

On the Messaging page: WhatsApp → **Set up**, enter the Phone number ID, the
WhatsApp Business Account ID and the access token, **Test**, then **Switch
on**. Then under **Events**, name the approved template (exactly as in
WhatsApp Manager) and its language (`en`, `en_US`, `hi`, ...) for each event.

**Each customer must opt in.** Tick *Agreed to WhatsApp messages* on the
customer only when they have said yes -- the software records the date. A
customer without it is never sent a WhatsApp message.

## 4. SMS — MSG91, on your own DLT registration

Every business SMS in India must be sent from a registered sender with a
registered template (TRAI's DLT rules). That registration is in your firm's
name and is your paperwork; it usually takes a few days.

1. **Register on a DLT portal** as a *Principal Entity* -- any operator's portal
   works (Jio, Vodafone Idea, Airtel, BSNL). You need your GST certificate,
   PAN, and a signatory's ID; the fee is about ₹5,900 once. You get a
   **Principal Entity ID**.
2. On the DLT portal register a **header** (sender ID): 6 letters, for example
   `ABCTRD`, category *Transactional / Service Implicit*.
3. Register a **content template** for each message, for example:

   > Dear {#var#}, invoice {#var#} for Rs {#var#} is due on {#var#}. - ABC Traders

   You get a **DLT template ID** for each.
4. Open an account at **msg91.com**, complete its KYC, and add credit. Under
   **API → Auth key** copy your auth key. Add your DLT entity ID and header in
   MSG91, then create each template in MSG91 (*SMS → Templates*), pasting the
   DLT template ID, and naming the variables `var1`, `var2`, ... in order.
   MSG91 gives each template its own **template id**.

On the Messaging page: SMS → **Set up**, enter the auth key, the 6-letter
sender ID and your DLT entity ID, **Test**, then **Switch on**. Under
**Events**, enter the MSG91 template id for each event. The variables are
filled in the order the page lists for that event.

## 5. Choose what is sent

Under **Events**, choose for each event which channels to use, **in order**: a
message goes on the first one that can take it, and moves to the next if that
one fails. For example *Invoice approved*: Email, then WhatsApp.

- A customer's **Preferred channel** is tried first when the event offers it.
- A customer marked **No payment reminders** gets no *due soon* or *overdue*
  reminders; their bills and receipts are still sent.
- A customer with no email is skipped for email, and so on; the reason is on
  the document's history.

## 6. Day to day

- Every message -- sent, failed or skipped, and why -- is on the document's
  history and in the **Message log** under Settings → Firm → Messaging.
- **Send** on an approved invoice sends it now, on the channel you choose.
- **Resend** in the Message log sends a message again. Nothing is ever sent
  twice except by Resend or Send.
- If a provider refuses (expired token, no SMS balance, a template withdrawn),
  the channel shows **Needs attention** and messages go to your next channel.
  Fix the account, press **Test**, and switch it back on.
- Changing an account's details switches the channel off until it passes Test
  again.

Your passwords, tokens and keys are stored encrypted and are never shown again
after saving -- the page offers only **Replace** and **Test**.
