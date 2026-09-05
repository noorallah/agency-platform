# Setting people up

How a person gets an account, and how they get the access their job needs.

Written 2026-09-06, after PRs #235–#240. Every screen and endpoint named here
was driven against a running backend rather than read off the code.

---

## 1. The four kinds of user

They are not interchangeable, and which one you are decides everything below.

| Tier | Who | Reaches | Cannot |
| --- | --- | --- | --- |
| **1** | Platform operator | Creates firms and their people, provisions storage, sets a firm up until it works | **A firm's books.** No invoices, no journals, no stock |
| **2** | All-firms super user | Everything, in every firm, without needing a membership | — |
| **3** | Firm administrator | Everything inside their own firm, including its people and their access | Anything outside their firm |
| **4** | Firm staff | The modules their job needs | The rest |

Tiers 1 and 2 are both rows in `platform_admins`, told apart by a `scope`
column: `PLATFORM` or `ALL_FIRMS`. Tier 3 is the seeded `FIRM_ADMIN` role.
Tier 4 is the other eleven seeded firm roles, or a role the firm wrote itself.

**A designation is a ceiling, not a floor.** A tier-1 operator who also holds a
genuine membership of a firm acts there as whatever their roles make them —
they simply lose the exemption that lets tier 2 walk into any firm.

### Which accounts are which today

| Account | Tier |
| --- | --- |
| `platform-admin@agency.local` | 2 |
| `master.ops@agency.local` | 2 |
| `superadmin@agency.local` | 2 |
| `whole01.admin@agency.local` and the other three firm admins | 3 |
| `whole01.sales1` and friends | 4 |

There is no seeded tier-1 account. Section 16 of the manual test plan makes one
with a single `UPDATE`, and puts it back afterwards.

---

## 2. What a template is

**A named bundle of roles for one job.** "Counter Sales" is a job a firm has;
`CASHIER` plus `BILLING_EXECUTIVE` is a permission decision somebody has to
make correctly. A template is that decision, made once, under a name the firm
already uses.

It is deliberately **not** a dormant user row. Cloning a user carries
everything a user has — an email, a password, memberships, an audit trail, a
login history — and the clone quietly inherits whatever was edited after the
template was written. A bundle carries only what the job needs.

Eleven come with the platform and are offered to every firm:

| Code | Name | Roles |
| --- | --- | --- |
| `firm-administrator` | Firm Administrator | `FIRM_ADMIN` |
| `firm-manager` | Firm Manager | `FIRM_MANAGER` |
| `counter-sales` | Counter Sales | `CASHIER`, `BILLING_EXECUTIVE` |
| `field-sales` | Field Sales | `SALES_EXECUTIVE` |
| `sales-manager` | Sales Manager | `SALES_MANAGER` |
| `warehouse` | Warehouse | `INVENTORY_MANAGER` |
| `purchasing` | Purchasing | `PURCHASE_EXECUTIVE` |
| `purchase-manager` | Purchase Manager | `PURCHASE_MANAGER` |
| `accounts` | Accounts | `ACCOUNTANT` |
| `customer-support` | Customer Support | `CUSTOMER_SUPPORT` |
| `read-only` | Read Only | `VIEWER` |

Most are a single role, and that is not a redundancy — the value is the name.

---

## 3. Hiring somebody into a job

**Administration → Users.** You need `USER_CREATE`, `USER_UPDATE`,
`ROLE_ASSIGN` and `ROLE_VIEW`; `FIRM_ADMIN` holds all four.

1. **New.** Fill in the name, email and an initial password.
   * A firm administrator's new user lands in **their own firm** automatically.
   * The **Firms** picker lists the firms *you* belong to. A platform
     administrator sees every firm instead.
2. Save. The person exists but holds nothing yet.
3. Select them → **Apply job template**.
4. Pick the job. The picker names the roles beside each one, because choosing
   by name alone is a permission decision made blind.
5. **Apply.**

What they hold afterwards is an ordinary role set. Edit it in the ordinary way
— nothing on the user records which template they came from, deliberately: a
user who has since been edited is no longer described by it.

> **The person must change their password when they first sign in.** A password
> somebody else chose is not a password.

---

## 4. Hiring somebody to do what an existing person does

The more common case: you have a person in mind rather than a written-down job.

**Administration → Users → select somebody → Hire like this person.**

Give the new person a name, an email and an initial password. That is all that
crosses over from you.

| Copied | Not copied |
| --- | --- |
| Their roles | Email, password |
| Their firm memberships | Mobile, employee code, joining date, photo, department |
| | Login history, password history, audit trail |
| | **The platform designation, ever** |

That last row is why this is not "duplicate the row" — a row copy carries all
of it, and carries it silently.

It needs `ROLE_ASSIGN`, `ROLE_VIEW` and `USER_CREATE`. Copying access **is**
granting access, so whoever may open accounts but not grant them does not get
this button.

A firm administrator copies only what their own scope can see: the roles the
source holds in their firm, plus the unscoped firm roles. Another firm's roles
stay invisible.

---

## 5. Writing your own template

**Administration → User Templates → New.** Needs `ROLE_CREATE` and
`ROLE_VIEW`.

| Field | Notes |
| --- | --- |
| **Template code** | Lower case, digits, dots, dashes. Unique within your firm — two firms may both have a `night-shift`. |
| **Job name** | What the firm calls the job. This is what people pick from. |
| **What this job does** | Optional; shown in the picker when a job bundles no roles. |
| **Roles** | What somebody hired into this job starts with. |
| **Offered** | Turn off to stop hiring into it without deleting it. |
| **Offered to** | **Platform administrators only** — see §6. |

Three things the server will not let you do:

* **Bundle a platform role.** `PLATFORM_ADMIN` carries every permission code
  the platform seeds, so a firm template able to name it would be a second door
  onto the same room. Refused at creation, not at apply — a template that fails
  weeks later on whoever tries to use it says nothing about whose fault it is.
* **Bundle another firm's role.** Same refusal.
* **Edit or retire a platform template.** They are offered to every firm, so no
  one firm may change them. Both buttons are disabled on those rows, and the
  server refuses anyway.

**Retiring a template changes nothing for the people hired through it.** It is
a decision about future hires.

---

## 6. Setting a new firm up (platform operators)

When a firm is created, its people and their templates are the operator's job.

1. **Create the firm.** Administration → Firms → New. Provision storage if it
   is not a shared-database firm.
2. **Write its templates.** User Templates → New, and set **Offered to** to
   that firm.
   * Leave **Offered to** blank and the template is offered to **every firm**
     on the platform. That is right for a job every firm has and wrong for one
     firm's own, which is why the field says so.
3. **Create its administrator**, put them in the firm, and apply the
   `firm-administrator` template.
4. Hand over. From there the firm administrator does §3, §4 and §5 themselves.

A tier-1 operator can do all of this and is still refused the firm's books —
`GET /api/v1/customers` answers 403 for them, by design.

---

## 7. Somebody who works in more than one firm

A firm administrator of two firms can put a person in both.

**Administration → Users → select → Edit → Firms.** The picker lists the firms
you belong to; tick the ones this person should be in.

Two rules, both enforced server-side:

* **You may only name firms you may staff** — judged on holding `USER_CREATE`
  *in that firm*, not on merely belonging to it. Someone who administers one
  firm and sells in another cannot staff the second. Naming one is refused by
  name rather than quietly dropped.
* **What you cannot see, you cannot remove.** Memberships of firms outside your
  reach are carried through untouched. Saving your own firm's membership does
  not take the person out of the others.

**You do not move the primary firm.** It is one flag across every firm a person
belongs to, so a caller who can see only some of them would either collide with
a primary they cannot see or quietly demote it. A person with no primary at all
gets one, so a new hire still lands somewhere when they sign in.

A platform administrator replaces the whole list, which is what they have
always done — their reach is every firm, so "replace within your reach" and
"replace everything" are the same thing.

---

## 8. Who can press what

| Action | Needs | `FIRM_ADMIN` |
| --- | --- | --- |
| Users → New / Edit | `USER_CREATE` (or `USER_UPDATE`), `ROLE_ASSIGN`, `ROLE_VIEW` | yes |
| Users → Apply job template | `ROLE_ASSIGN`, `ROLE_VIEW` | yes |
| Users → Hire like this person | `ROLE_ASSIGN`, `ROLE_VIEW`, `USER_CREATE` | yes |
| Users → Edit → Firms | `USER_UPDATE`, plus `USER_CREATE` in each firm named | yes, for their own firms |
| User Templates (see) | `ROLE_VIEW` | yes |
| User Templates → New / Edit / Retire | `ROLE_CREATE` / `ROLE_UPDATE` / `ROLE_DELETE` | yes |
| User Templates → Offered to | The platform designation | no |
| Roles (see) | `ROLE_VIEW` | yes |
| Firms (see, create) | The platform designation | no |

`FIRM_VIEW` is deliberately **not** in any of these. It is a platform code —
one of the set a firm administrator may not even grant — and it used to be
demanded by the New-user gate, which hid the button from the only role whose
job it is.

---

## 9. Testing it

`docs/MANUAL_UI_TEST_PLAN.md` has the cases:

| Section | Covers |
| --- | --- |
| 16 | The four tiers, including making a tier-1 account and putting it back |
| 17 | User templates |
| 18 | Hiring like an existing person |
| 19 | Setting a firm up from the platform side |
| 20 | A firm administrator creating users, and multi-firm assignment |
