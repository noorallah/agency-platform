# Configuration Settings Guide

Every setting a firm can change in version 1.3.0, and the settings of the
agency itself that the platform administrator sees: **why it exists, what each
choice does, what a person sees when it acts, and who may change it.**

Written 2026-10-04 from the code (the schemas, the defaults and the services
that read each field), not from earlier documents, and brought up to release
1.3.0 (the light menu, Settings > Set up and Platform, My preferences and the
agency's branding) the same day. The messages quoted are the
ones the application shows. Where this guide and the application disagree,
the application is right and this guide is out of date -- say so and it will
be corrected.

---

## Contents

1. [How settings work](#1-how-settings-work)
2. [Quick reference: every setting on one page](#2-quick-reference-every-setting-on-one-page)
3. [Suggested starting points by type of firm](#3-suggested-starting-points-by-type-of-firm)
4. [This PC and me](#4-this-pc-and-me)
5. [Firm](#5-firm)
6. [Selling](#6-selling)
7. [Buying](#7-buying)
8. [Stock](#8-stock)
9. [Tax](#9-tax)
10. [Accounts: closing months, ageing, adjustments](#10-accounts-closing-months-ageing-adjustments)
11. [Settings that live on a customer, product or supplier](#11-settings-that-live-on-a-customer-product-or-supplier)
12. [Before sign-in: Application Settings](#12-before-sign-in-application-settings)
13. [Platform: the agency's branding](#13-platform-the-agencys-branding)
14. [Things worth knowing](#14-things-worth-knowing)

---

## 1. How settings work

Open them from the **gear (Settings)** at the right of the menu bar. It opens
the Settings page in a tab of its own: cards grouped under three headings, with
a search box. **Settings** holds *This PC and me*, Firm, Selling, Buying, Stock,
Tax and Business profile (the groups of this guide, in the same order);
**Set up** holds the lists set up once and changed rarely (Pricing, Territories
& routes, Account structure, Party lists, Item lists, Locations); **Platform**
holds People, Firms, Agency and System, for the platform tier. Each group is
offered only to a person whose role may open it. A few settings sit on the
screen they govern instead; each entry below says where.

Seven rules hold for every setting:

1. **A firm that never saved a setting uses its default.** The dialog says
   so: *"This firm has not chosen, so it is using the default shown here.
   Saving makes it the firm's own."* Nothing is written until somebody saves.
2. **Settings belong to one firm.** Two firms on the same server can choose
   differently. Switch firm first, then change the setting.
3. **Settings govern what happens next, not what has already happened.** A
   document already approved, dispatched or billed is not re-judged when a
   setting changes. Switching a stage on or off never strands work in flight.
4. **Most checks have three strengths: Off, Warn, Block.**
   - *Off* -- not checked at all.
   - *Warn* -- the person is told, the action goes ahead, and the warning is
     kept on the document's history and in the audit trail.
   - *Block* -- the action is refused, with a message that says why and what
     to do instead.

   **Almost every default is Warn**, because a check that stops the counter
   on the day it is switched on is a check nobody switches on. A firm moves
   to Block once its people know the rule.
5. **Every change is recorded in the audit trail** -- who changed what, from
   what, to what, and when.
6. **The person a rule limits cannot switch it off.** Changing selling
   settings needs *manage sales settings*, which the Sales Manager role does
   not hold; changing credit control needs *manage customer settings*, which
   sits with accounts. Anyone may *read* a setting that affects their work,
   so a warning can always be traced to the rule behind it. A dialog opened
   by someone without the right to change it is read-only and says which
   permission is needed.
7. **Checks are made by the server, not the screen.** No client, import or
   other route can step round them.

---

## 2. Quick reference: every setting on one page

| Setting | Where | Default for a new firm | Who may change it |
| --- | --- | --- | --- |
| My Preferences | Settings > This PC and me | Last screen, light theme, dd-MM-yyyy | Each person, for themselves |
| Firm Settings (business profile) | Settings > Firm | Platform default profile | `FIRM_UPDATE` |
| Financial Years: month close check, ageing columns | Settings > Firm > Financial Years | Warn; 30, 60, 90 days | `FINANCIAL_YEAR_CREATE` |
| Numbering Series | Settings > Firm | Set up with the firm | `SETTINGS_UPDATE` |
| My Branch and Warehouse | Settings > Firm | None | Each person, for themselves |
| Messaging | Settings > Firm | **Off** | `SETTINGS_UPDATE` |
| Approval Levels | Settings > Firm | None: one approval is enough | Manage sales / purchase settings |
| Sales Stages | Settings > Selling | Every stage typed by hand | `SALES_MANAGE_SETTINGS` |
| Credit Control | Settings > Selling | **Warn** at 80% | `CUSTOMER_MANAGE_SETTINGS` |
| Price Floor | Settings > Selling | **Warn**, cost counts | `SALES_MANAGE_SETTINGS` |
| Discount Limits | Settings > Selling | No limits | `SALES_MANAGE_SETTINGS` |
| Loyalty Scheme | Settings > Selling | **Off** | `LOYALTY_MANAGE_SETTINGS` |
| TCS Settings | Settings > Selling | **Off** | `TCS_MANAGE` |
| Purchase Settings | Settings > Buying | Every stage typed; no tolerance check | `PURCHASE_MANAGE_SETTINGS` |
| Reorder planning | Reports > Operational > Below reorder level | Typed levels | `PURCHASE_MANAGE_SETTINGS` |
| Approval Limits (purchase) | Settings > Buying | No limits | `PURCHASE_MANAGE_SETTINGS` |
| Purchase Budgets | Settings > Buying | None | `PURCHASE_MANAGE_SETTINGS` |
| Inventory Settings | Settings > Stock | Per person, this PC | Each person |
| Adjustment Reasons | Settings > Stock | Eight standard reasons | `INVENTORY_MANAGE_REASONS` |
| Adjustment Limits | Settings > Stock | No limits | `INVENTORY_MANAGE_SETTINGS` |
| Batch Rules | Settings > Stock | Warn / record; shelf life **blocks** | `SALES_MANAGE_SETTINGS` |
| Licence Check | Settings > Set up > Party lists | **Warn** | `TRADE_LICENCE_MANAGE_SETTINGS` |
| Tax Configuration, Tax Rules | Settings > Tax | From the GST template | `TAX_CREATE` / `TAX_UPDATE` |
| Tax Settings (labels) | Settings > Tax | "Tax", "Component", "Profile" | `TAX_MANAGE_SETTINGS` |
| GST Documents (+ e-invoice route) | Settings > Tax | Dispatch before invoice **warns**; e-invoice not applicable; sandbox | `TAX_MANAGE_SETTINGS` |
| TDS on Purchases (194Q) | Settings > Tax | **Off** | `ACCOUNT_MANAGE` |
| Party adjustment limits | Accounts > All Accounts screens > Books > Party Adjustments | 1,000 / rounding 10 | `PARTY_ADJUSTMENT_APPROVE` |
| Print settings | The Print button on a document | Standard layout | `SETTINGS_UPDATE` |
| Application Settings | The gear on the sign-in screen | This PC's server | Anyone at this PC |
| Agency branding (name, tagline, logo) | Settings > Platform > Agency > Branding | Not set: Agency Platform's own name shows | `PLATFORM_SETTINGS` |

---

## 3. Suggested starting points by type of firm

These are starting points, not rules. Agree the tax ones with the firm's CA.

| Setting | Small shop / counter billing | Distributor with salesmen and a warehouse | Pharma or food (batches and expiry) |
| --- | --- | --- | --- |
| Sales Stages | Quotation, order and delivery note **off**: type only the bill | All **on** | All **on** |
| Buying stages (Purchase Settings) | Purchase order **off** (goods receipt goes with it): type only the supplier's bill -- see `SMALL_FIRM_SETUP_GUIDE.md` | All **on** | All **on** |
| Rates typed include GST | **On** | Off | Off |
| GST Documents: dispatch before invoice | Warn (the bill ships the goods anyway) | **Block** -- goods leave only with *Dispatch and invoice* or a challan reason | **Block** |
| Van or route sales need the invoice first | Off | Off if vans sell on the road; **on** if every load is pre-billed | As for distributor |
| Credit Control | Warn | **Block** at 100%, warn at 80% | **Block** |
| Price Floor | Warn | Warn; **Block** once minimum prices are set | Warn |
| Discount Limits | None | Salesman 5%, Sales Manager 10% | Salesman 2-5% |
| Approval Levels | None | Orders above 1 lakh signed by the Sales Manager | As for distributor |
| Batch Rules | Leave as is | Leave as is | Near expiry 60-90 days, **Need a reason** for near-expiry and for skipping an earlier batch |
| Licence Check | Off | Warn | **Block** (drug licence) |
| Messaging | Off, or invoice by WhatsApp | Invoice + payment reminders | As for distributor |
| Month close check | Warn | **Refuse** once the accountant closes monthly | **Refuse** |

---

## 4. This PC and me

### My Preferences

**Where:** the user menu (your name, top right) > My preferences, or Settings >
This PC and me > My Preferences. Every signed-in person, with or without a firm
chosen; no permission needed. (The *Primary firm* entry the earlier menu had is
gone: *Start in firm* below replaces it.)

**Why:** each person starts their day differently. These choices are personal
and change nothing for anyone else.

| Choice | Options | What it does |
| --- | --- | --- |
| Start in firm | Firms you belong to | The firm you land in at your next sign-in. Shown only when you belong to more than one firm; a platform administrator always starts in none. Switching firm from the menu bar lasts for this session only; this is for next time. |
| First screen | *The screen I was last on* (default), or any screen your role may open | Where the application opens after sign-in. A choice your role can no longer open reads as the default. |
| Theme | Light, Dark, Follow Windows | Colours. |
| Text size | Small, Default, Large | **This PC only**; useful on a small laptop or a large shared screen. |
| Date format | dd-MM-yyyy (default), dd/MM/yyyy, yyyy-MM-dd, MM/dd/yyyy | How dates are shown on the new screens. Anyone coming from an earlier build is moved to dd-MM-yyyy on first sign-in, because nobody could choose one before. |

Everything except text size follows you to every PC you sign in to, and your
favourites (the star in the menus) are kept with them. Opening the dialog asks
the server nothing, and saving sends one small update containing only what you
changed (saving with nothing changed sends nothing). A refusal leaves the
dialog open with the server's message. There is no *Rows per page* in 1.3.0.

---

## 5. Firm

### Firm Settings (business profile)

**Where:** Settings > Firm > Firm Settings. Changing needs `FIRM_UPDATE`.

**Why:** a pharmacy, an electronics distributor and an FMCG agency need
different features. The **business profile** decides which features and
modules this firm operates -- batches and expiry, serial numbers, vehicle
tracking and so on -- so that nobody is asked for fields their trade does not
use.

**What happens:** choose a profile and press **Apply profile**. Menus and
the optional features follow it. A firm with no profile runs as *Generic* and a
warning says so. The firm's name, GSTIN and address are not here; they are on
the platform **Firms** screen (Settings > Platform > Firms).

**What a profile no longer does:** it does not decide which extra fields the
firm sees, or which are compulsory. Changing the profile takes no stored value
out of any record. That moved to the custom field screens below (changed on
2026-10-08, not yet tested by hand).

### Custom Fields and Custom Field Rules

*Added on 2026-10-08, not yet tested by hand.*

**Where:** Settings > Firm > Custom Fields, and Settings > Firm > Custom Field
Rules. Changing needs `CUSTOM_FIELD_MANAGE`, which the firm administrator holds
and the firm manager and sales manager do not.

**Why:** a pharmacy wants a batch note on its medicines and a drug licence on
its chemists. A wholesaler does not. These two screens say which extra fields
each kind of record carries.

**What happens:**

- **Custom Fields** lists the platform's shared fields and the firm's own. Switch
  a shared field **off** and it disappears from this firm's forms. Every value
  already stored is kept, and switching it **on** again shows them. A field the
  firm made itself is retired with its own *Active* flag instead.
- **Custom Field Rules** ties a field to a kind, or makes it compulsory. A rule
  can name a goods type, a customer group, a supplier type or a product
  category. A rule on a goods type, a customer group or a supplier type shows the
  field only on that kind (products of that goods type, customers in that group,
  suppliers of that type) and says whether it must be filled there. A field with
  no such rule is shown on every record of its sort. A product with no goods
  type, a customer in no group, a supplier with no type and every document are
  shown no tied field. A rule on a product category only makes the field
  compulsory for products in that category.
- Moving a customer to another group, or a supplier to another type, deletes
  nothing. The old value stays and can still be saved back. The new kind's
  required fields are asked for at the next save.

### Financial Years

**Where:** Settings > Firm > Financial Years. Changing the two settings on
this page needs `FINANCIAL_YEAR_CREATE`; closing a month needs
`FINANCIAL_YEAR_CLOSE`.

Besides opening and closing years and months, the page holds two settings.

#### Before closing a month with unfinished work in it

**Why:** a month closed with draft bills still in it gives the accountant
figures that change afterwards.

| Choice | What happens when somebody closes a month |
| --- | --- |
| **Warn** (default) | The close shows a checklist of unfinished work and offers **Close anyway**. |
| **Refuse** | The close is refused while any of these remain: draft journals dated in the month; documents dated in the month still in draft; approved documents with no journal. The message names how many and up to five examples: *"... cannot be closed yet -- the firm refuses a close while work is unfinished ... Post or cancel them first, or set 'Before closing a month' to warn."* |

Three things are always listed and never stop a close: receipts held on
account and not set against a bill, bank statement lines not matched, and GST
returns not marked filed.

#### Ageing columns (days)

**Why:** some firms chase money at 30/60/90 days, others at 15/30/45.

**Choices:** one to five boundaries in ascending order, each 1 to 3,650 days.
Default **30, 60, 90**, which gives the columns 0-29, 30-59, 60-89 and 90+.

**What happens:** customer ageing and supplier ageing both use these columns.
It changes how reports are grouped, never a document.

### Numbering Series

**Where:** Settings > Firm > Numbering Series. Changing needs
`SETTINGS_UPDATE` (the firm administrator).

**Why:** every firm numbers its documents its own way, and GST sets limits on
how a tax invoice may be numbered.

| Field | Default | What it does |
| --- | --- | --- |
| Document type | -- | Which document the series numbers. Cannot be changed later. |
| Code, Name | -- | How the series is known on screen. |
| Prefix / Suffix | None | Printed first / last, such as `INV` or `/HYD`. |
| Separator | `-` | Joins the parts. |
| Digits | 6 | The counter is zero-padded to this many digits. |
| Include the financial year | Off | Puts `2026-2027` in the number. |
| Print the year as 26-27 | Off | Shortens the year, to keep a GST number within 16 characters. |
| Restart numbering each financial year | **On** | The counter goes back to 1 on 1 April. Off: one continuous series. |
| Include branch code | Off | Each branch numbers separately. |
| Include the firm code | Off | The firm's code in the number. |
| Allow a number to be typed in | Off | For copying in hand-written documents; a typed number does not move the counter. |
| Use this series by default | Off | One default per document type. |
| Active | On | A switched-off series raises nothing. |
| Start numbering at | 1 | Only when the series is created; afterwards the server owns the counter. |
| Format pattern | None | Advanced: overrides the switches above with placeholders such as `{prefix}{separator}{financial_year_short}{separator}{sequence}`. |

Two checks protect the firm:

- **A series that restarts every year must show the year**, or the first
  invoice of April repeats one issued last year. The editor warns, and saving
  is refused.
- **A GST document number may be at most 16 characters** (CGST rule 46(b)).
  This applies to sales invoices, credit notes, sales returns, customer debit
  notes, delivery notes and self-invoices. A series whose longest number would
  be longer is refused, with suggestions: a shorter prefix, the year as 26-27,
  no firm or branch code, or fewer digits.

Example without a pattern: `INV-2026-2027-000001`.

### My Branch and Warehouse

**Where:** Settings > Firm > My Branch and Warehouse. Each person sets their
own; an administrator can set it for someone else from the **Users** screen
(`USER_UPDATE`).

**Why:** a person who always works at the Secunderabad counter should not
pick that branch on every document.

**What happens:** your usual branch and warehouse **fill in only when the
field is blank** on a new document. A document continuing another keeps its
own, and every branch and warehouse can still be chosen. Choosing only a
warehouse sets its branch too.

### Messaging (email, WhatsApp, SMS)

**Where:** Settings > Firm > Messaging, four tabs. Changing needs
`SETTINGS_UPDATE`. The step-by-step account setup is in
`docs/MESSAGING_SETUP_GUIDE.md`.

**Why:** customers expect their invoice on WhatsApp and a reminder before a
payment falls due. The firm sends **from its own accounts**, so the messages
come from the firm's name and number and it pays its provider directly.

**Tab 1 -- Switch and schedule**

| Field | Default | What it does |
| --- | --- | --- |
| Send messages from this firm | **Off** | Off means nothing is sent, queued or recorded, whatever the other tabs say. |
| Payment due soon: days before due | 3 | A reminder this many days before a bill falls due (0-60). |
| Payment overdue: repeat every n days | 7 | After the due date, a reminder the next day and then every n days (1-90). |
| Payment overdue: stop after n days | 90 | Bills overdue longer than this are not chased. Switching reminders on does not suddenly chase very old bills. |

**Tab 2 -- Channels.** One account per channel: Email (SMTP), WhatsApp (Meta
Cloud API), SMS (MSG91). Passwords and tokens are stored encrypted and never
shown again; leaving one blank keeps the saved one. **Saving an account always
switches the channel off**, and it can be switched on only after **Test**
passes. A channel is used only when it has an account, is switched on and its
last test was OK.

**Tab 3 -- Events.** Which messages go out, on which channels, in which order:

| Event | When |
| --- | --- |
| Invoice approved | A sales invoice is approved (email attaches the PDF) |
| Sales order approved | An order is approved |
| Goods dispatched | A delivery note is dispatched |
| Payment received | A receipt is recorded |
| Payment due soon / Payment overdue | The daily reminder run |

Each event lists up to three channels, in order; the first one that can reach
the customer is used. If the customer has a preferred channel, it goes first.
If none can send, the message is recorded as skipped with the reason for each
channel -- for example *"the customer has no phone number"* or *"the customer
has not opted in to WhatsApp"*.

**Tab 4 -- Message log.** What was sent, skipped or failed.

**Good to know:** a failed message never stops a document. Per customer, *No
reminders*, *Preferred channel* and *WhatsApp opt-in* are on the customer
record.

### Approval Levels

**Where:** Settings > Firm > Approval Levels. Changing the sales levels needs
`SALES_MANAGE_SETTINGS`; changing the purchase levels needs
`PURCHASE_MANAGE_SETTINGS`.

**Why:** a large order should be seen by a manager before stock is reserved
or money is committed, without slowing down every small one.

**Applies to:** sales orders, sales invoices, purchase orders, purchase bills.

**Fields per rule:** *Level* (1 to 3), *From amount*, *Role*.

**Default:** none. *"No levels set. One approval is enough."*

**What happens:**

- A document whose total is at or above a rule's amount needs that level
  signed by someone holding the role. Several roles on one level are
  alternatives.
- Levels are signed in order. The person signing the last open level approves
  the document in the same step.
- **One person cannot sign two levels** of the same document.
- Approving before the chain is complete is refused: *"This needs a level N
  sign-off by ... before it can be approved."*
- **If the total rises after a signature, that level has to be signed
  again.**
- Rejecting needs a reason and clears earlier signatures.
- Documents waiting for your signature appear on Home and under the bell.

Example: orders from 1,00,000 need the Sales Manager (level 1); orders from
5,00,000 also need the Owner (level 2).

---

## 6. Selling

### Sales Stages

**Where:** Settings > Selling > Sales Stages. Changing needs
`SALES_MANAGE_SETTINGS` (not held by the Sales Manager).

**Why:** a one-person counter does not type an order and a delivery note for
every sale; a distributor with a warehouse must. A firm that grows can switch
stages on later.

| Field | Default | What it does |
| --- | --- | --- |
| Quotation | On | Recorded for the firm's own reference. **In 1.3.0 it changes nothing**; quotations stay available either way (see section 13). |
| Sales order | On | On: people type orders. |
| Delivery note | On | On: people raise and dispatch delivery notes. Off: billing an order raises and dispatches the note itself. |
| Default branch / warehouse | Firm's default | Where goods ship from when the bill raises the delivery note itself. |
| When several offers match | **Combine offers** | *Combine* applies each matching offer in turn; *Best offer only* gives the one worth most. |
| Most offers may take off one line (%) | No cap | Only with *Combine*. Past the cap, the last offer applied gives back first. |
| Rates typed on a bill include GST | Off | On: a new counter bill starts with *Rate includes GST*, so the shelf price can be typed; each bill can still switch it. |
| New outlets wait for approval | Off | On: a customer added by someone who cannot approve customers can take orders but **cannot be billed** until approved. |
| Release stock held by unshipped orders after (days) | Never | An approved order that has not shipped in this many days gives its reserved stock back. The order stays approved; reserve it again to hold the stock. |

**What happens when the order and delivery note stages are both off:** the
person types only the bill. When it is saved, the bill raises the order and
the delivery note itself, and **stock leaves when the bill is approved**. The
documents are real, so stock, cost and the audit trail are exactly as if they
had been typed. A draft bill ships nothing.

**When either stage is on,** a bill line must name the order or note it bills:
*"This firm raises a sales order and a delivery note before it bills, so an
invoice line must name the document it bills."*

### Credit Control

**Where:** Settings > Selling > Credit Control. Changing needs
`CUSTOMER_MANAGE_SETTINGS`, held by accounts and deliberately **not** by the
Sales Manager. Changing a customer's credit limit needs the same permission.

**Why:** selling more to a customer who already owes too much is how
distributors lose money.

**When it acts:** when a **sales order** is approved and again when a **sales
invoice** is approved. What counts is what the customer owes, less any
unapplied advance, plus this document. A customer whose credit limit is **0
has no limit** and is never checked.

| Field | Default | What it does |
| --- | --- | --- |
| When a customer reaches their limit | **Warn** | *Do nothing*: limits are recorded, never checked. *Warn*: the approval goes ahead with a warning. *Block*: warn at the first threshold, refuse at the second. |
| Warn at (%) | 80 | *"Ravi Stores would be at 88.5% of a 250000.00 credit limit, leaving 12000.00 available."* |
| Block at (%) | 100 | Only under Block: *"... would be at 112.0% of a 250000.00 credit limit. Collect payment or raise the limit before continuing."* Must not be below the warning level. |
| Cash discount: pay within (days) and Discount (%) | None | An early-payment discount offered on bills paid within the days. A customer's own terms override it. |
| Overdue interest: rate a year (%) | 0 (none) | Interest on overdue bills, shown on the statement; charged only when somebody raises it. |
| Grace (days) | 0 | No interest until this many days after the due date. |

The approval screens warn but never block on their own: when the firm chooses
Block, it is the server that refuses.

### Price Floor

**Where:** Settings > Selling > Price Floor. Changing needs
`SALES_MANAGE_SETTINGS`.

**Why:** to stop goods being sold below their minimum price, or below cost,
by mistake.

**When it acts:** at sales order approval and sales invoice approval, before
any stock moves. It looks at the net rate per unit after all discounts.

| Field | Default | What it does |
| --- | --- | --- |
| Enforcement | **Warn** | *Off*: not checked. *Warn*: approval goes ahead; the finding is kept on the document. *Block*: approval refused unless overridden. |
| Cost is a floor too | **On** | A line below the product's cost is a finding even if the product has no minimum price. Off: only the product's *minimum selling price* counts, so clearance below cost is allowed. |

Message on a line: *"Line 2 (...) is sold at 90.00 a unit, below its minimum
price of 95.00."* The seller is never shown the cost figure.

**Override:** under Block, someone holding `SALES_PRICE_OVERRIDE` (not the
Sales Manager by default) may approve with a reason, which is recorded.
**Near-expiry stock** may be sold below the floor if Batch Rules allow it.

### Discount Limits

**Where:** Settings > Selling > Discount Limits. Changing needs
`SALES_MANAGE_SETTINGS`.

**Why:** a salesman's discount should be limited, a manager's less so.

**Fields:** one row per role -- *Role* and *Max discount (%)*. A role with no
row has no limit.

**What happens:** at approval, a discount **typed by hand** that is larger than
the approver's limit is refused: *"Line 3 carries a discount of 12.00%, above
your limit of 5.00%. It needs approval by someone allowed at least 12.00%."*
A person's limit is the largest among their roles. **Discounts that come from
a price list, a promotion or the customer's standing rate are never limited**
-- only what somebody typed.

### Loyalty Scheme

**Where:** Settings > Selling > Loyalty Scheme. Changing needs
`LOYALTY_MANAGE_SETTINGS`.

**Why:** to reward repeat customers with points or cashback.

| Field | Default | What it does |
| --- | --- | --- |
| Scheme is running | **Off** | Off: nothing is earned and nothing can be spent; balances already earned are kept. |
| Points earned (per 100 billed) | 1 | Points credited when an invoice is approved; cancelling the bill takes them back. |
| A point is worth | 1 | The money value of a point when redeemed. 1 means cashback. |
| Minimum to redeem | 0 | Points a customer must hold before spending any. |
| Points expire after (months) | Never | Applies to points earned after the change. |

**Good to know:** the scheme **costs the firm when points are earned**, not
when they are spent, so the earning rate is what sets its cost. Redeeming
points **settles** a bill like a payment; it is not a discount, so the full
GST is still charged.

### TCS Settings (tax collected at source)

**Where:** Settings > Selling > TCS Settings. Needs `TCS_MANAGE`.

**Why:** section 206C(1H) required large sellers to collect tax from buyers
whose purchases passed 50 lakh a year.

| Field | Default | What it does |
| --- | --- | --- |
| Collect under section 206C(1H) | **Off** | On: collect on customer **receipts**. |
| Threshold | 50,00,000 | What one buyer may pay in the financial year before collection starts. Only the excess is taxed. |
| Rate / rate without PAN | 0.1% / 1% | |
| Preceding-year turnover / Turnover threshold | 0 / 10 crore | The firm is in scope only when its turnover is above the threshold. |

> **Important:** section 206C(1H) was **omitted by the Finance Act 2025 from 1
> April 2025**. The application collects nothing on a receipt dated on or after
> that day, whatever this switch says. The setting remains for receipts before
> that date.

---

## 7. Buying

### Purchase Settings (buying stages and checks)

**Where:** Settings > Buying > Purchase Settings. Changing needs
`PURCHASE_MANAGE_SETTINGS`.

| Field | Default | What it does |
| --- | --- | --- |
| Purchase order stage | On | Off: the supplier's bill raises the order itself. |
| Goods receipt stage | On | Off: the bill raises the goods receipt itself. It cannot be on while the order stage is off: a receipt is always raised against an order. |
| Default branch / warehouse | Firm's default | Where goods arrive when the bill raises the receipt. |
| Rate may exceed the order by (%) | No check | At bill approval, a line billed above its order's rate by more than this is named. |
| Whole bill may exceed the order by (amount) | No check | The bill's total excess over its order's prices. |
| Order quantities off the supplier's terms | **Warn** | *Refuse*: an order line not meeting the supplier's minimum or multiple cannot be saved. *Warn*: the editor suggests the right quantity. |
| Past a purchase budget | **Warn** | *Needs approval*: an order taking a budget past its amount can be approved only with `PURCHASE_APPROVE_OVER_BUDGET`. |

**Tolerance:** any breach refuses approval unless the approver holds
`PURCHASE_APPROVE_OVER_TOLERANCE`, and names each line, for example *"billed
at X against Y ordered (Z% over, tolerance T%)"*. A bill with no order behind
it has nothing to compare against.

**With stages off**, stock still arrives through a goods receipt and the
accounts still pass through *Goods received not invoiced*, exactly as if the
documents had been typed.

### Reorder planning

**Where:** the **Below reorder level** report, Reports > Operational (not on the gear).
Changing needs `PURCHASE_MANAGE_SETTINGS`.

| Field | Default | What it does |
| --- | --- | --- |
| Basis | **Typed levels** | *Typed levels*: suggest orders only for products with a reorder level typed on their stock. *From sales*: work one out for every product without one. |
| Read sales over (days) | 90 | 7-365. |
| Lead time (days) | 7 | How long the supplier takes. A supplier's own lead time wins where recorded. |
| Safety stock (days) | 7 | Extra cover. |
| Order enough for (days) | 30 | How much to order. |

From sales: reorder point = average daily sales x (lead time + safety days);
suggested order = that plus *order enough for* days of sales, less what is
already on order. **A level typed on a product always wins.**

### Approval Limits (purchase orders)

**Where:** Settings > Buying > Approval Limits. Changing needs
`PURCHASE_MANAGE_SETTINGS`.

**Fields:** *Role* and *Max order amount*. A role with no row has no limit.

**What happens:** an order whose total (with tax) is above the approver's limit
is refused: *"This order's total of ... is above your approval limit of
.... It needs approval by someone allowed at least ...."* The order stays
submitted for someone with a higher limit.

### Purchase Budgets

**Where:** Settings > Buying > Purchase Budgets. Changing needs
`PURCHASE_MANAGE_SETTINGS`.

**Why:** to keep monthly buying within plan, by branch or by category.

**Fields:** month, branch (blank = all), category (blank = all), amount. One
budget per month, branch and category.

**What happens:** *Used* is the value before tax of approved orders dated in
that month. Going over warns or needs approval, as chosen under **Past a
purchase budget** in Purchase Settings. The order editor shows which budgets an
order touches and what is left.

---

## 8. Stock

### Inventory Settings

**Where:** Settings > Stock > Inventory Settings. **Personal, on this PC
only** -- not a firm setting.

Two conveniences: whether opening stock posts automatically after saving, and
the default format for quick exports.

### Adjustment Reasons

**Where:** Settings > Stock > Adjustment Reasons. Changing needs
`INVENTORY_MANAGE_REASONS`.

**Why:** every stock write-off must say why -- damage, expiry, sample -- and
can post to its own ledger account so that losses are visible in the
accounts.

Eight standard reasons are provided: Damage, Expiry, Loss, Internal use,
Staff, Display, Given free to customer, Sample. They can be renamed and linked
to an account; they cannot be deleted, only marked inactive. Add the firm's
own as needed.

### Adjustment Limits

**Where:** Settings > Stock > Adjustment Limits. Changing needs
`INVENTORY_MANAGE_SETTINGS`.

**Why:** a storekeeper should not be able to write off a lakh of stock alone.

**Fields:** *Role* and *Max value*. A role with no row has no limit.

**What happens:** an adjustment worth more than the person's limit (quantity x
average cost) is refused: *"This moves stock worth ..., above your limit of
.... Submit it for approval instead."* The request then waits on **Adjustment
Approvals**; a person whose limit covers it posts it unchanged, and rejecting
needs a reason.

### Batch Rules

**Where:** Settings > Stock > Batch Rules. Changing needs
`SALES_MANAGE_SETTINGS`.

**Why:** in pharma and food, which batch leaves matters -- for expiry, for the
customer's shelf-life demand and for the price.

**When it acts:** when a delivery note is dispatched, including the one a
counter bill dispatches.

| Field | Default | What it does |
| --- | --- | --- |
| A batch is near expiry within (days) | 30 | Flags batches in the batch picker and drives the next rules. |
| A near-expiry batch left behind | **Warn** | *Warn*: dispatch goes ahead with a note. *Need a reason*: refused until a reason is given. |
| Skipping an earlier-expiring batch | **Record** | When someone picks a later batch ahead of an earlier one. *Record*: kept in the audit trail. *Need a reason*: refused without one. |
| A near-expiry batch may be sold below the price floor | **On** | Lines wholly from near-expiry batches are exempt from Price Floor, so stock can be cleared. |
| Batch short of the customer's minimum shelf life | **Block** | A hand-picked batch expiring before the customer's keep-until date is refused: *"... expires before ..., the customer's minimum shelf life. Choose a later batch, or change the customer's minimum shelf life."* *Warn* records it instead. Automatic picking always skips such batches. |
| Take a line's rate from its batch's selling price | Off | On: choosing a batch fills the line rate from that batch's selling price. |
| Hold customer returns in quarantine until checked | Off | On: returned goods go to quarantine, not the shelf, until released from Stock. |

Whatever the settings, **no bill may charge more than a batch's MRP**, and an
expired batch never leaves.

### Licence Check (trade licences)

**Where:** Settings > Set up > Party lists > Licence Check, beside *Licence Types*.
Changing needs `TRADE_LICENCE_MANAGE_SETTINGS`; overriding a block needs
`TRADE_LICENCE_OVERRIDE`.

**Why:** some goods -- medicines, pesticides -- may be sold only to buyers
holding a valid licence, and the seller must hold one too.

| Field | Default | What it does |
| --- | --- | --- |
| Sales | **Warn** | Checked when an order, delivery note or invoice is approved. A licensed product sold to a buyer with no valid licence (missing, expired or not yet valid) is a finding. *Warn*: approval goes ahead. *Block*: refused unless approved with an override reason. |
| Purchases | **Warn** | Order and goods receipt approval warn when the supplier holds no valid licence. **Only Off or Warn**: the goods have already arrived. |

---

## 9. Tax

### Tax Configuration and Tax Rules

**Where:** Settings > Tax > Tax Configuration, Tax Rules, Rule Simulator,
Execution Log. Changing needs `TAX_CREATE` / `TAX_UPDATE`.

**Why:** these say what tax is charged. They are filled in for an Indian firm
by the **GST template** when the firm is set up, and are rarely touched
afterwards.

- **Tax systems and profiles** -- the rates: GST 5, 12, 18 and 28, cess, and
  so on. A component can be *recoverable* (input credit may be claimed) or
  *included in price* (MRP-based pricing: reported, never added to the
  total).
- **Tax rules** -- which profile applies to which transaction. **Rules attach
  to the transaction, never to the product.** The first matching active rule,
  by priority, wins.
- **Rule Simulator** -- try a transaction and see which rule matches and what
  is charged, before saving anything.
- **Execution Log** -- which rule taxed which line.

Change these only with the firm's CA.

### Tax Settings

**Where:** Settings > Tax > Tax Settings. Changing needs
`TAX_MANAGE_SETTINGS`.

**Labels only:** what the firm calls *Tax*, *Component*, *Profile* and the tax
report in headings. The GST template sets them to *GST*, *Component*, *Tax
Profile* and *GST Report*. **They change no calculation.**

### GST Documents

**Where:** Settings > Tax > GST Documents. Changing needs
`TAX_MANAGE_SETTINGS`.

*"GST law wants a sale's tax invoice to exist before the goods leave. These
settings say how this firm is held to that."*

#### Dispatch of a sale before its invoice

**Why:** a tax invoice for goods must be issued at or before their removal
(CGST s.31). A plain delivery challan may carry goods only for the reasons the
law allows.

**When it acts:** when somebody dispatches a delivery note by hand. Only notes
whose reason is **Sale** are judged (and **Van or route sale** when the switch
below is on).

| Choice | What happens |
| --- | --- |
| Off | Not checked. |
| **Warn** (default) | Dispatch goes ahead. The person is told, and the warning is kept on the note and in the audit trail. |
| Block | Refused: *"DN-0388 is a sale with no invoice yet. GST requires the tax invoice at or before the goods leave (CGST s.31): use Dispatch and invoice, or give the challan a reason that allows invoicing later."* |

**With Block, goods can still leave in three ways, all lawful:**

1. **Dispatch and invoice** on the delivery note: dispatches, raises the bill
   for the whole note and approves it in one step. If the bill is refused (a
   price below its floor, a missing licence), nothing is dispatched.
2. **A counter bill** (when the delivery note stage is off): stock leaves when
   the bill is approved, so the invoice always exists first.
3. **A challan with a reason that allows billing later:** *Supply on approval*,
   *Quantity not known at removal*, *Job work*, *Other* -- and *Van or route
   sale* unless the next switch is on. These are billed afterwards, several
   notes on one invoice if need be.

#### Van or route sales need the invoice before the van leaves

Default **Off**: a van may load goods on a challan and invoice each shop at
delivery, as the law allows. **On**: a van load is judged like a sale.

#### E-invoicing applies from / 30-day reporting limit applies from

**Why:** e-invoicing becomes compulsory once a firm's turnover passes the
limit, and only the firm knows its turnover -- so the application never
guesses either date.

- **E-invoicing applies from** (default: not applicable). From this date, a
  B2B sales invoice, credit note, debit note or sales return **cannot be
  printed, emailed or sent until it has its IRN**: *"... has no IRN yet ...
  it is not a valid tax invoice until it is registered on the portal (CGST
  rule 48(4)). Register it under E-invoice first, or print a reference copy
  marked not valid."* A reference copy carries the banner *NO IRN YET - NOT A
  VALID TAX INVOICE*. HSN codes must then have 6 digits instead of 4.
- **30-day reporting limit applies from** (needs the e-invoicing date first).
  From this date, a document more than 30 days old cannot be registered; it
  has to be cancelled and raised again under today's date.

#### E-invoice filing (route)

| Choice | What happens |
| --- | --- |
| **Sandbox (rehearsal, nothing filed)** -- default | Registering rehearses; nothing reaches the government. |
| Offline: upload on the e-invoice portal | Export the portal's bulk-upload file (up to 500 documents), upload it on the portal, then import the result: each document is reported registered, failed or unmatched. Free, no contract. |

Direct filing through NIC or a GSP is not yet available.

#### The remaining GST Documents fields

| Field | Default | What it does |
| --- | --- | --- |
| E-way bill needed above (Rs) | 50,000 | Invoices and delivery notes above this with no e-way bill are listed as due. A goods receipt above it with no e-way bill number is warned. Set your state's limit if it differs. |
| Claim input credit | **All bills** | *All bills*: claim every eligible bill in GSTR-3B and list what GSTR-2B lacks. *Only bills matched to GSTR-2B*: hold back unmatched bills until they appear. |
| Matching tolerance (Rs) | 1.00 | A bill matches a GSTR-2B line when the tax differs by no more than this. |
| Supplier bill without an IRN | **Warn** | A bill from a supplier marked *issues e-invoices* with no IRN is warned: its credit is at risk. |
| 180-day unpaid bills (rule 37) | **Report only** | Input credit on supplier bills unpaid 180 days after their date. *Report only*: listed for the CA. *Report and post*: also moves the credit out of input tax. *Off*. |
| Common credit reversal (rule 42) | **Report only** | Credit used for exempt supplies; same three choices. |
| Returns are filed | **Monthly** | *Quarterly (QRMP)*: GSTR-1 and 3B per quarter, with monthly PMT-06 deposits. |
| Quarterly from | -- | Only with quarterly filing; must be 1 Jan, 1 Apr, 1 Jul or 1 Oct. Months before it stay monthly. |
| PMT-06 deposit method | **Fixed sum (35% of last quarter)** | Or *Self-assessment*: the month's tax less its credit. |

The tax calendar on Home follows these choices.

### TDS on Purchases (194Q)

**Where:** Settings > Tax > TDS on Purchases (194Q). Changing needs
`ACCOUNT_MANAGE`.

**Why:** a buyer whose turnover passed 10 crore last year deducts TDS on
purchases from a supplier above 50 lakh in the year.

| Field | Default | What it does |
| --- | --- | --- |
| Our turnover passed Rs 10 crore last year (deduct 194Q) | **Off** | On: the payment screen suggests the 194Q to deduct. |
| Threshold per supplier, per year | 50,00,000 | Purchases before GST, counted April to March. |
| Rate % / Rate % without a PAN | 0.1 / 5 | Section 206AA applies when the supplier has given no PAN. |

The setting only suggests; the deduction is posted by the payment, and the TDS
registers and 26Q work as before.

---

## 10. Accounts: closing months, ageing, adjustments

- **Month close check** and **ageing columns** -- on Settings > Firm >
  Financial Years; see [section 5](#financial-years).
- **Party adjustment limits** -- on the **Party Adjustments** screen (Accounts >
  All Accounts screens > Books), button *Adjustment limits*. Changing needs `PARTY_ADJUSTMENT_APPROVE`.

| Field | Default | What it does |
| --- | --- | --- |
| Second approver above | 1,000.00 | An adjustment (a write-off or settlement of a customer's or supplier's small balance) above this can be approved only by someone holding `PARTY_ADJUSTMENT_APPROVE`, **and not by the person who drafted it**. Cancelling an approved one above it needs the same. |
| Rounding limit | 10.00 | The most a receipt or payment may round off. More than this is refused: *"Record the difference as a discount, or write the balance off with a party adjustment."* |

---

## 11. Settings that live on a customer, product or supplier

These are on the record itself, not behind the gear, but they change what a
sale or purchase does.

### Customer

| Field | Default | What it changes |
| --- | --- | --- |
| Status | Active | *Inactive* or *On hold*: no new quotation, order or bill. *Pending* (a new outlet waiting for approval): orders are taken, billing waits for approval (`CUSTOMER_APPROVE`). |
| Credit limit | 0 = no limit | Checked under Credit Control. Changing it needs `CUSTOMER_MANAGE_SETTINGS`. |
| Standing discount % | 0 | Applied when a line's discount is left blank; typing 0 refuses it. |
| Payment terms (days) | 0 | Due date on the bill (the order's terms win when billing from an order). Also drives reminders and interest. |
| GST registration type | From the GSTIN | Regular, Composition, Unregistered, SEZ, Deemed export, Overseas: decides CGST+SGST or IGST, the GSTR-1 section and the e-invoice type. |
| Minimum shelf life (days) | None | Batches expiring sooner are skipped automatically and judged by Batch Rules if picked by hand. |
| No reminders / Preferred channel / WhatsApp opt-in | -- | See Messaging. |

### Product

| Field | Default | What it changes |
| --- | --- | --- |
| Status | -- | Only *Active* and *Discontinued* can be sold. |
| Not for sale / Free issue only | Off | Bought and stocked only / only ever given free. |
| Minimum selling price | None | The price floor. |
| MRP | None | No bill may charge more (a batch's own MRP wins). |
| Tax group | None | Part of what tax rules match on. |
| Input credit eligibility | Eligible | Default for purchase bill lines. Changing needs `PRODUCT_TAX_MANAGE`. |
| Track batch / expiry / serial ... | Off | What is captured at receipt and issue; the *require on receipt/issue* switches refuse a line without it. |
| Issue rule | Earliest expiry | FEFO, FIFO or picked by hand. |
| Shelf life (days) | None | Fills expiry from the manufacturing date at receipt. |
| Inspection required | Off | Received goods wait in quarantine until passed. |
| Allow negative stock | Off | Whether stock may go below zero. |
| Preferred supplier | None | Reorder drafts the order to this supplier. |
| Reorder / minimum / maximum level, safety stock | None | Per branch and warehouse; drive *Below reorder level*; win over reorder planning. |

### Supplier

| Field | What it changes |
| --- | --- |
| Status Blocked (with reason) | No new purchase order. |
| GST registration type | Composition, Unregistered or Overseas: bill lines carry no GST and no credit. |
| Issues e-invoices | Bills without an IRN are warned (GST Documents). |
| Payment terms (days) | Default due date on supplier bills. |
| MSME (Udyam number, category, written agreement) | Micro and small suppliers must be paid within 45 days (15 with no written agreement); medium is recorded only. |
| Default TDS section | Suggested on payments. |

---

## 12. Before sign-in: Application Settings

**Where:** the gear on the sign-in screen. Anyone at the PC; no sign-in
needed.

| Control | What it does |
| --- | --- |
| API URL (server address) | Which server this PC talks to: `https://` anywhere, or `http://` on your own network (for example `http://192.168.1.20:8000`). Saving signs the user out and reconnects. |
| Recent servers | Fills the address from earlier choices. |
| Appearance | Light, Dark or System; applies at once. |
| Diagnostics report / Open logs folder | For support: what to send when something goes wrong. |

**Which server wins:** the address chosen here, then the one the installer
wrote (`127.0.0.1:8000` on the server PC, or the address typed during an
app-only install), then the built-in default. It is stored per Windows user.

### Print settings

**Where:** the **Print** button on a sales invoice, delivery note or purchase
order. Changing needs `SETTINGS_UPDATE`.

| Field | Default | What it does |
| --- | --- | --- |
| Title on the document | TAX INVOICE | May be reworded (for example Bill of Supply), not removed. |
| Accent colour | Dark blue | Heading colour. |
| Header note, terms, declaration, jurisdiction, footer note, "Signed for" | Standard declaration | The firm's own words around the bill. |
| Bank details / show bank details | Shown | Printed for payment. |
| UPI ID | None | Sales invoice only: prints a QR code for the amount still owed. |
| Discount / batch / expiry columns | Discount shown; batch and expiry hidden | Which columns print. |
| How many copies | One, unlabelled | Up to four labelled copies (Original for recipient, Duplicate for transporter ...). |
| Page size | A4 | A4, A5, or an 80 mm thermal roll. |
| Margin (mm) | 12 | 5-40. |

**Nothing statutory can be changed or hidden:** GSTINs, HSN per line, tax per
component, the tax summary and the amount in words always print.

---

## 13. Platform: the agency's branding

These are settings of the **installation**, not of a firm: one record for the
whole agency, read by every PC and every firm. They belong to the platform
tier, so no firm needs to be chosen to see or change them.

### Agency branding (name, tagline, logo)

**Where:** Settings (gear) > Platform > Agency > Branding. Offered only to a
person holding `PLATFORM_SETTINGS` (the platform administrator); no firm needs
to be open. Anyone, signed in or not, can *read* the branding, because the
sign-in screen shows it.

**Why:** the agency's own name, tagline and logo lead the sign-in screen and
the top of every screen, and Agency Platform's own name is shown quietly beside
them.

| Field | Default | What it does |
| --- | --- | --- |
| Agency name | **Required** (up to 150 characters; spaces alone are refused) | Shown on the sign-in screen, in the header strip and in the window title (*agency > firm*). |
| Tagline | None (up to 200 characters; blank is stored as none) | Shown under the name on the sign-in card and in the header from 1280 px wide. |
| Logo | None: the agency's initials show instead | **PNG or JPG, at most 1 MB.** Checked by its content, not its file name: a text file renamed `.png` is refused (*The logo must be a PNG or JPG image.*), and an over-size picture is refused naming its size. A logo needs the name to be given first. The server does not check its shape; the screens fit it into a square. **Remove logo** goes back to the initials. |
| Accent colour | None | **Kept but not asked or applied** in 1.3.0: the form has no box for it, and a saved colour goes back to the server unchanged. |

The form shows a live preview of the sign-in card and the header strip, and
beneath it, read-only, the product, its company and its logo (*set by the
installer; changed only by an update*). Saving shows *Saved.* and the header
changes at once on this PC; another PC sees the new branding at its next
sign-in screen.

**Two people editing at once:** the second save is refused with the
somebody-else-saved message and keeps what was typed, so nothing is lost.

**Every change is audited** in the platform trail (Settings > Platform > System
> Audit Logs, no firm chosen): `agency_branding.created`,
`agency_branding.updated` and `agency_branding.logo_changed`, each naming who. A
logo change records its type and size, never the image.

#### How the branding is first given

- **On a fresh server install,** the installer has a **Branding** page after
  *This PC* (agency name, tagline, a logo file, all optional; a tagline or logo
  without a name is refused). It does not appear for an app-only PC, an upgrade
  or a repair. A refused logo never fails the install: the name is saved, the
  logo is skipped and the install log holds a warning; add the logo later here.
- **At the first sign-in, if it is still not set,** the platform administrator
  (a holder of `PLATFORM_SETTINGS`) is asked **Set up your agency** (name,
  tagline, logo and a preview). *Skip for now* closes it; it does not reopen for
  that user, and Home shows a **Finish setting up** card until the branding is
  given. A firm administrator, or anyone without platform settings rights, is
  never shown the dialog.
- **After an upgrade** the branding is empty, so the first platform
  administrator to sign in is asked in the same way. Until it is set, the
  sign-in screen and header show Agency Platform's own name.

**Not part of it:** the product's own name, company, logos and the support
phone, WhatsApp, hours, email and website on the sign-in screen come from the
package, not from this form; the support details are blank in 1.3.0, so none
shows. The *Finish setting up* card stands in for the later first-run steps,
which are not built.

---

## 14. Things worth knowing

Found while checking this guide against the code on 2026-10-04:

- **Quotation stage changes nothing yet.** It is saved and shown, but no part
  of the application acts on it in 1.3.0. Quotations stay available whatever
  it says.
- **TCS under 206C(1H) collects nothing on receipts from 1 April 2025**,
  because the section was omitted by the Finance Act 2025.
- **Tax Settings is labels only.** It does not change any tax calculation;
  Tax Configuration and Tax Rules do.
- **Inventory Settings is per person and per PC**, not a firm setting.
- **Four settings are not behind the gear:** Reorder planning (Reports >
  Operational > Below reorder level), Party adjustment limits (Party Adjustments
  screen), the
  month close check and ageing columns (Financial Years page), and Print
  settings (the Print button).

## See also

- `docs/SALES_TO_RECEIPT_FLOW.md` and `docs/PURCHASE_TO_PAYMENT_FLOW.md` --
  each step of the sale and the purchase, and which setting acts where.
- `docs/PRICING_AND_PROMOTIONS.md` -- how a line's price and discount are
  decided.
- `docs/GST_DOCUMENT_COMPLIANCE.md` -- the GST document rules in full.
- `docs/MESSAGING_SETUP_GUIDE.md` -- setting up email, WhatsApp and SMS
  accounts.
- `docs/ACCESS_CONTROL_FRAMEWORK.md` -- roles and the permissions named here.
