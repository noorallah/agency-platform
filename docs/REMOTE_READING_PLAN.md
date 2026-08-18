# Two days of theory — a remote reading plan

A reading order for understanding how the platform actually works, with nothing
to run and nothing to install. Roughly **3,200 lines of the 11,600** tracked in
the repo; the rest is reference, history, or a proposal.

Companion to [`LEARNING_PATH.md`](LEARNING_PATH.md), which is a
module-by-module order for when you intend to **write** something and can run
both processes. This one assumes you cannot.

Doc lengths measured 2026-08-18.

---

## Read these first, and skip these

The most useful thing here is the skip list. Four documents look essential by
title and will cost you most of a day for very little.

| Skip | Why |
| --- | --- |
| `MULTI_INDUSTRY_ERP_ARCHITECTURE.md` (1,055) | Its own header says *"Status: Architecture design. Scope: Future platform enhancement; no implementation in this phase."* It is intent, not description. Read `BUSINESS_PROFILE_FRAMEWORK.md` instead — that one was verified against a running backend |
| `DESIGN_SYSTEM.md` (1,661) | Desktop styling tokens. Useful the day you build a screen, near-useless for understanding what the system does |
| `BACKLOG.md` (1,348) | A history of decisions, most of them closed. Excellent for *why* something is the way it is; a poor way in |
| `MANUAL_UI_TEST_PLAN.md` (696) | A lookup table for when you are sitting in front of the app. You won't be |

---

## Day one — the frame: how any request finds its data

Everything else looks arbitrary until this lands. Most of what a router does is
compose these pieces.

### 1. Start with the map — ~45 min

| Read | Length |
| --- | --- |
| [`CLAUDE.md`](../CLAUDE.md) | 242 lines |
| [`SECURITY_ARCHITECTURE.md`](../SECURITY_ARCHITECTURE.md) | 76 lines |

`CLAUDE.md` is the densest thing in the repo and the only one written to be read
first. Every paragraph is a rule that exists because something broke. Read it
slowly; you will come back to it all week.

**Take away:** two applications, no shared build. The backend owns every rule
and the database; the desktop talks REST and never touches the database. If you
remember one thing from the whole day, make it that.

### 2. Multi-tenancy — the thing to understand first — ~90 min

Code, not docs:

- `backend/app/common/scope.py` — the single most important file to read early.
  Every firm-owned router composes it.
- `backend/app/core/database/dependencies.py` — decides, per request, whether
  you are on the platform schema or a firm's store.
- `backend/app/core/tenancy/` — skim. How a firm resolves to SHARED, SCHEMA or
  DATABASE, and how one on another server is reached.

**Take away:** a request carries `X-Firm-ID`. `users`, `firms` and `user_firms`
live **only** in the platform schema, and a tenant session cannot see them.
Business services never learn which storage mode a firm uses — they receive a
session and stay ignorant on purpose.

**Check yourself:**

1. A firm-owned service needs a salesman's name. Where does it get it, and why
   can it not just join?
2. A platform admin edits firm B while firm A is selected. Which store does the
   write land in, and what fixes that?

### 3. One module, end to end — ~90 min

- `backend/app/customers/` — router → service → repository. The designated
  reference master-data module. Follow one endpoint all the way down, then a
  second one back up.
- [`CUSTOMER_MANAGEMENT.md`](CUSTOMER_MANAGEMENT.md) (159 lines) — read *after*
  the code, not before.

**Take away:** the same five layers repeat in all 23 modules. Routers validate,
resolve scope and delegate; services own transactions, business rules and audit
writes; repositories own soft-delete-aware queries. Seen once, seen everywhere.

### 4. What makes one firm different from another — ~75 min

[`BUSINESS_PROFILE_FRAMEWORK.md`](BUSINESS_PROFILE_FRAMEWORK.md) — 706 lines,
verified against the running backend, so what it says is what runs. The table of
what is actually *enforced* versus merely recorded is the part to slow down on.

**Take away:** industry behaviour is never hardcoded into an entity. A
capability is declared as a feature and gated. Of 21 declared features, 12 have
backing code and 7 are roadmap carrying `is_implemented = false` — a fact about
the codebase, kept deliberately separate from whether an administrator switched
it on.

---

## Day two — the flows: where stock and money actually move

Day one was structure. Today is the business: one full transaction chain, then
the calculators that touch every line of it.

### 5. Purchase, end to end — ~90 min

| Read | Length |
| --- | --- |
| [`PURCHASE_FRAMEWORK.md`](PURCHASE_FRAMEWORK.md) | 371 lines |
| [`PURCHASE_TO_PAYMENT_FLOW.md`](PURCHASE_TO_PAYMENT_FLOW.md) | 277 lines |

The second was written by driving a real order through a running backend on
2026-08-18. Every ledger line in it is one the server produced.

**Take away:** three moments move anything — completing a goods receipt (stock
arrives, `Dr Inventory / Cr Goods Received Not Invoiced`), approving a purchase
invoice (the payable appears), and recording a payment (money leaves). Raising
and approving an order move nothing at all. Both clearing accounts net to zero
when the chain completes; that is how you tell it did.

**Check yourself:**

1. An order is approved and nothing has arrived. What has changed in the ledger?
2. Why is inventory deliberately *not* touched when the supplier's invoice is
   approved?
3. Why can a receipt that has been invoiced no longer be cancelled?

### 6. The two calculators on every line — ~90 min

| Read | Length |
| --- | --- |
| [`TAX_FRAMEWORK.md`](TAX_FRAMEWORK.md) | 283 lines |
| [`UOM_FRAMEWORK.md`](UOM_FRAMEWORK.md) | 294 lines |

**Take away:** tax rules attach to the **transaction**, never to a product — the
product only contributes matching context. And `TaxRuleService.simulate` is not
a preview: it is the calculation, called once per line by all seven
transactional modules, which is why it must never commit.

### 7. Stock, and how it is counted — ~75 min

| Read | Length |
| --- | --- |
| [`INVENTORY_FRAMEWORK.md`](INVENTORY_FRAMEWORK.md) | 311 lines |
| [`BATCH_SERIAL_EXPIRY_ARCHITECTURE.md`](BATCH_SERIAL_EXPIRY_ARCHITECTURE.md) | 395 lines |

Skim the second if the day is running long — come back to it before touching
inventory.

### 8. Distribution — the part that makes this an agency platform — ~45 min

[`TERRITORY_FRAMEWORK.md`](TERRITORY_FRAMEWORK.md) — 319 lines. The
firm-configurable hierarchy, what makes a node a route, how a beat plan becomes
a call list, and how a sale is filed against a round.

**Take away:** this is the newest area and the one with an open product decision
— visit execution. If you want to form an opinion about where the product goes
next, form it here.

---

## The traps, read as a list

These live inside `CLAUDE.md`, but they are worth a second pass on their own.
Each is a defect that actually shipped, and each is the kind of thing that reads
as fine and is not.

1. **An update that dumps its whole write model turns an omission into an
   instruction.** Optional fields have defaults, so `model_dump()` returns a
   value for a field the caller never mentioned. It has now shipped four times —
   destroying vendor addresses, clearing branch details, and silently
   un-approving a purchase order.
2. **A literal path must be declared before `/{id}` in the same router.**
   FastAPI matches in declaration order, so four territory endpoints answered
   "not a valid UUID" for their whole existence.
3. **Never read the server's local clock.** Everything persisted is UTC, so
   `date.today()` compares against a date the data does not use. Shipped three
   times.
4. **Never let NULL ordering pick a row.** PostgreSQL sorts NULLs first in
   `DESC`, SQLite last — so a firm-wide rule outranked a product's own factor in
   production while the unit suite saw the right answer.
5. **`ondelete="RESTRICT"` is not a guard on a soft-deleted table.** A soft
   delete never reaches the database's referential check, so the refusal has to
   live in the service.
6. **Migrations are per-schema.** A bare `alembic upgrade head` advances only
   the platform schema and silently leaves every firm's data behind. The drift
   is invisible until a query hits a missing column.

---

## If you only get two hours

1. **`CLAUDE.md`** in full — 242 lines, the highest return per minute in the repo.
2. **`app/common/scope.py`** and **`app/core/database/dependencies.py`** — how a
   request finds its data.
3. **`PURCHASE_TO_PAYMENT_FLOW.md`** — one complete business chain, with the
   ledger entries each step raises.

The frame, the tenancy model, and one real transaction. Enough to follow any
conversation about the system.

---

## When you're back at the machine

- [`LEARNING_PATH.md`](LEARNING_PATH.md) — module-by-module reading order for
  when you intend to write something, ranked by dependency count rather than
  size. Measured 2026-08-10; it says how to re-measure.
- [`RUNNING.md`](RUNNING.md) — gets both processes up.
- [`MODULE_REVIEW_CHECKLIST.md`](MODULE_REVIEW_CHECKLIST.md) — what a review
  actually checks. Its entries are derived from defects that occurred, not from
  generic advice.
