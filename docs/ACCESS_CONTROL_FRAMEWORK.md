# Access control — roles, permissions, modules and settings

What decides whether a person can open a screen, press a button, or change a
setting; where each of those decisions is stored; and how to change it.

This is the reference for the *access* half of the platform, the way
[`TAX_FRAMEWORK.md`](TAX_FRAMEWORK.md) is the reference for tax.
[`FUNCTIONAL_GUIDE.md`](FUNCTIONAL_GUIDE.md) §1 covers the same ground as a
**workflow** — bring a firm into service, give somebody access, sign in. This
file covers it as a **model**: the tiers, what each grant actually reaches, and
every switch a person with the right code may turn.

Every number here was derived on **2026-09-06** by the commands in
[How to re-derive every number](#how-to-re-derive-every-number-in-this-file).
Re-run them rather than trusting the figures; counts in this repository have
drifted by a third before anybody noticed.

---

## The five gates, in the order a request meets them

A request is refused by the **first** gate that says no. They are independent:
holding a permission does not imply membership, and being a member does not
imply the firm operates the module.

| # | Gate | Asks | Stored in | Refused with |
| --- | --- | --- | --- | --- |
| 1 | **Authentication** | Is this a live token for a live user? | `users`, `refresh_tokens` | 401 |
| 2 | **Designation** | Does this route need a platform administrator? | `platform_admins` | 403 |
| 3 | **Permission** | Does the caller hold the code this route enforces? | `roles` → `role_permissions` → `user_roles` | 403 |
| 4 | **Membership** | May the caller act on the firm in `X-Firm-ID`? | `user_firms` | 403 |
| 5 | **Business profile** | Does this firm operate the module / feature? | `profile_modules`, `profile_features` | 403 on write, or the screen is not offered |

Gates 3 and 4 are asked **together** for every firm-owned route, by the one
dependency in `backend/app/common/scope.py`. No router writes its own; the
copies that used to resolve `firms` and `user_firms` on the tenant session
raised `UndefinedTable` for every firm outside the platform store.

Gate 5 is the only one that is *not* a security boundary in the desktop: the
client hides menu entries a firm has switched off, but the server is what
refuses the write (`require_feature` / `require_module`, and
`assert_feature_fields` for features that are optional fields rather than whole
endpoints).

---

# Part 1 — The two tiers of administrator

## Tier 1: the platform designation

A **platform administrator** is a row in `platform_admins`, not a role. It is
carried on its own token claim (`platform_admin`), never in the `roles` list.

That separation is load-bearing. The designation used to be appended to `roles`
as the lowercase string `"platform_admin"` while genuine role codes are
uppercase, so a designation and a role code shared one list — and
`RoleCreate.code` *requires* `^[a-z0-9._-]+$`. A firm administrator holding
`ROLE_CREATE` and `ROLE_ASSIGN` could create a role called `platform_admin`,
assign it to themselves, and sign in as a platform administrator, reaching every
platform-only route and **every firm's data**. Closed 2026-09-05; `create_role`
now also refuses the reserved codes case-insensitively.

### The designation has two reaches

`platform_admins.scope`, added by `20260905_0128`:

| Scope | Runs the platform | Acts inside a firm's books | Global `permissions` claim |
| --- | --- | --- | --- |
| `PLATFORM` | ✅ creates firms, their people, their settings, provisions storage | ❌ — **not exempted**, so they meet the ordinary membership check like anybody else | the 33 codes in `PLATFORM_OPERATOR_PERMISSION_CODES` |
| `ALL_FIRMS` | ✅ | ✅ — the designation as it has always behaved | all 189 codes |

Three grants had to be narrowed for `PLATFORM` to mean anything, because any
two without the third is not a narrowing at all:

1. the membership exemption in `app/common/scope.py`,
2. the permission short-circuit in `Principal.has_permission`,
3. the **stuffed `permissions` claim** — `has_permission` reads it directly, so
   a `PLATFORM` admin carrying operational codes would pass every firm
   permission check the moment they held a genuine membership.

**A designation is a ceiling, not a floor.** A `PLATFORM` administrator who
holds a real `UserFirm` row acts in that firm as whatever their roles make
them — no more, and no less.

`PLATFORM_OPERATOR_PERMISSION_CODES` is deliberately **not**
`PLATFORM_PERMISSION_CODES`. The latter answers a different question (what a
firm administrator may not *grant*) and is wrong in both directions here: it
omits `user`, `role` and `permission` — the operator's whole job — and includes
`high_risk`, which is `VOID_INVOICE` and `EDIT_POSTED_TRANSACTION` on a firm's
posted books, the one thing this tier exists not to touch.

### How a platform administrator comes to exist

There is **no API for it.** The designation is a table row, created in exactly
two places:

| Where | What it creates |
| --- | --- |
| Migration `20260728_0001` | The bootstrap admin — `platform-admin@agency.local`, `password_hash = '*'`, `force_password_change = true`. The first login accepts `AGENCY_BOOTSTRAP_ADMIN_PASSWORD`, hashes it, and demands a change |
| `scripts/generate_sample_data.py` | The demo administrators, which state their `scope` explicitly |

The column has **no server default** and the ORM default is the narrow value, so
a row written without stating a reach gets the safe answer. Existing rows were
backfilled to `ALL_FIRMS` — nobody was demoted. An **absent** scope claim on a
token that carries the designation reads as `ALL_FIRMS`: such a token can only
have been minted before the scope existed, for somebody who by definition
already had every firm, and demoting live administrators mid-session is worse
than an unchanged one for the few minutes an access token lives. An
**unrecognised** value reads as `PLATFORM`, the narrow one — a column holding
something nobody recognises is a reason to grant less, never more.

## Tier 2: everybody else

Everybody who is not a platform administrator holds access through two
independent things, both required:

- **roles** — *what* they may do, resolved to permission codes;
- **memberships** (`user_firms`) — *whose data* they may do it to.

An account with roles and no membership can sign in and open nothing. An account
with a membership and no roles can select a firm and press nothing.

---

# Part 2 — Roles

## What a role is

| Column | Meaning |
| --- | --- |
| `code` | Uppercase by convention for system roles; a custom code must match `^[a-z0-9._-]+$` and is unique platform-wide |
| `name`, `description` | What a firm reads |
| `is_active` | An inactive role grants nothing immediately — the token query filters on it |
| `is_system` | Seeded. **Immutable through the API**: `update_role`, `delete_role` and `set_role_permissions` all refuse it |
| `firm_id` | NULL = available to every firm. Set = the firm's own custom role, invisible to others |

`user_roles` carries its own `firm_id`, which answers a **different** question:
where the role was granted, not who owns it. See
[Part 4](#part-4--how-a-role-becomes-a-permission-on-a-request).

## The sixteen seeded roles

Four are platform-tier and twelve are firm-tier. `SUPPORT_ADMIN` is in
`HIDDEN_SYSTEM_ROLE_CODES` and is not offered in listings.

| Role | Tier | Codes | What it is for | Deliberately withheld |
| --- | --- | ---: | --- | --- |
| `PLATFORM_ADMIN` | platform | 189 | Every code that exists | — |
| `SUPPORT_ADMIN` | platform | 189 | Support access; hidden from role listings | — |
| `LICENSE_ADMIN` | platform | 3 | `LICENSE_MANAGE`, `FIRM_VIEW`, `REPORT_VIEW` | everything else |
| `SYSTEM_AUDITOR` | platform | 5 | Reads the trails: `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW`, `FIRM_VIEW`, `USER_VIEW`, `REPORT_VIEW` | every write |
| `FIRM_ADMIN` | firm | 170 | Runs the firm: every operational module **plus** users, roles, permissions, `SETTINGS_VIEW`/`SETTINGS_UPDATE` | platform codes, `high_risk`, and the six areas in [Part 11](#part-11--what-the-seeded-grants-do-not-cover) |
| `FIRM_MANAGER` | firm | 150 | Everything `FIRM_ADMIN` operates, **minus** administering the firm's people | `user`, `role`, `permission`, `SETTINGS_*` |
| `ACCOUNTANT` | firm | 24 | The books: `accounting`, `commission`, `report`, plus `CUSTOMER_MANAGE_SETTINGS` | sales and purchase writes |
| `SALES_MANAGER` | firm | 35 | Owns the sales desk: customers, the sales chain, territory assignment, credit notes (draft), proforma, loyalty spend | the ten controls in the table below |
| `SALES_EXECUTIVE` | firm | 6 | Works a beat: view customers and territory; raise quotation, order, invoice | approval, cancellation, every master write |
| `PURCHASE_MANAGER` | firm | 9 | All nine `purchase` codes | everything outside purchasing |
| `PURCHASE_EXECUTIVE` | firm | 8 | The same, minus `PURCHASE_APPROVE` | approval |
| `INVENTORY_MANAGER` | firm | 16 | `inventory` + `batch_serial` | everything else |
| `CASHIER` | firm | 4 | `PAYMENT_CREATE`/`PAYMENT_VIEW`, `RECEIPT_CREATE`/`RECEIPT_VIEW` | see [Part 11](#part-11--what-the-seeded-grants-do-not-cover) |
| `BILLING_EXECUTIVE` | firm | 2 | `SALES_INVOICE_CREATE`, `SALES_VIEW` | everything else |
| `CUSTOMER_SUPPORT` | firm | 3 | `CUSTOMER_VIEW`, `CUSTOMER_UPDATE`, `PRODUCT_VIEW` | everything else |
| `VIEWER` | firm | 37 | Every `*_VIEW` code **except** `PLATFORM_VIEW`, `USER_VIEW`, `ROLE_VIEW`, `PERMISSION_VIEW`, `AUDIT_LOG_VIEW`, `SETTINGS_VIEW` | every write |

### The twelve firm roles form a containment tree

Not a metaphor and not a design intention read back from the names -- computed
from `ROLE_PERMISSION_CODES` by asking which role's codes are a strict superset
of which. Re-derive it rather than trusting the drawing:

```
uv run python -c "from app.identity.system_seed import ROLE_PERMISSION_CODES as R;   [print(a, '>', [b for b in R if b != a and set(R[b]) < set(R[a])]) for a in R]"
```

```
FIRM_ADMIN (170)          runs the firm and its people
└── FIRM_MANAGER (150)    every module, none of the people
    ├── SALES_MANAGER (35)
    │   ├── SALES_EXECUTIVE (6)
    │   │   └── BILLING_EXECUTIVE (2)
    │   └── CUSTOMER_SUPPORT (3)
    ├── PURCHASE_MANAGER (9)
    │   └── PURCHASE_EXECUTIVE (8)
    ├── ACCOUNTANT (24)
    │   └── CASHIER (4)
    └── INVENTORY_MANAGER (16)

VIEWER (37)               outside the tree
```

Two things the shape says that the names do not.

**`CASHIER` sits under `ACCOUNTANT`, not under `SALES_MANAGER`.** A sales
manager holds neither `RECEIPT_CREATE` nor `PAYMENT_CREATE`, so they cannot
take money -- whoever agrees the price does not handle the cash. It is the same
separation that keeps `COMMISSION_PAY` away from whoever states the debt and
`TCS_MANAGE` away from the role the threshold constrains.

**`VIEWER` is a parallel axis rather than a rung.** It holds 37 read codes and
no writes, so it contains nothing -- not even `CUSTOMER_SUPPORT`, which can
update a customer -- and nothing contains it, because no operational role holds
every `*_VIEW`. Reading "VIEWER is the bottom of the ladder" out of the numbers
is wrong in both directions.

Everything else nests exactly as its name suggests, which is worth knowing
before inventing a custom role: if the job is "a purchase executive who may
also approve", that is `PURCHASE_MANAGER`, already seeded.

### Why the withholdings are what they are

One idea runs through all of them: **the role a control constrains must not be
able to switch the control off.**

| Role | Cannot | Because |
| --- | --- | --- |
| `SALES_MANAGER` | `CUSTOMER_MANAGE_SETTINGS` | The credit policy limits their own sales |
| `SALES_MANAGER` | `SALES_MANAGE_SETTINGS` | Turning the delivery-note stage off means dispatch is confirmed by the sale itself rather than by whoever watches the goods leave |
| `SALES_MANAGER` | `PROMOTION_MANAGE` | A discount the firm gives away is a control over the role measured on what it sells |
| `SALES_MANAGER` | `SALES_TARGET_MANAGE` | The number they are measured on is the firm's decision |
| `SALES_MANAGER` | `COMMISSION_MANAGE`, `COMMISSION_PAY` | Whoever states a debt must not move the cash — and would otherwise pay their own team, and on a rule with no salesman, themselves |
| `SALES_MANAGER` | `CREDIT_NOTE_APPROVE` | Drafting is bookkeeping; approving **reverses tax already declared to the authority** |
| `SALES_MANAGER` | `LOYALTY_MANAGE_SETTINGS` | The conversion rate decides what every customer's credit is worth |
| `SALES_MANAGER` | `TCS_MANAGE` | The policy decides what every buyer is charged on every receipt |
| `SALES_MANAGER` | `EINVOICE_MANAGE` | Reading a registration is running a sales desk; filing with the authority is not |
| `FIRM_MANAGER` | `user` / `role` / `permission` | Operating the firm and deciding who may operate it are different jobs |
| `ACCOUNTANT` | *(holds)* `CUSTOMER_MANAGE_SETTINGS` | Credit policy governs receivables, so it belongs to the role that owns them rather than to the role it constrains |

## Custom roles

`POST /api/v1/roles` (`ROLE_CREATE`) creates one. Three rules:

- **`is_system` is never client-supplied** — a custom role is always `false`.
- **`firm_id` is taken from the caller's scope**, not from the body. A platform
  caller creates an unscoped role; a firm caller creates their own firm's.
- **Reserved codes are refused case-insensitively**: `platform_admin`, plus the
  lowercase spelling of all sixteen system role codes.

`PUT /api/v1/roles/{id}/permissions` (`ROLE_ASSIGN`) sets what it grants. A
**firm-scoped** caller may not attach any of the 22 `PLATFORM_PERMISSION_CODES`
(the `platform`, `firm`, `system_administration` and `high_risk` groups), or a
firm administrator could mint themselves `VOID_INVOICE` or `SYSTEM_RESTORE`.

Every role edit calls `_revoke_role_users`, so everybody holding that role is
re-authenticated rather than carrying a stale token.

---

# Part 3 — Permissions

**189 codes in 30 groups**, all seeded by `backend/app/identity/system_seed.py`.
The naming convention is `DOMAIN_ACTION` — `CUSTOMER_VIEW`, `TAX_RULE_UPDATE`.

| Group | Codes | Group | Codes |
| --- | ---: | --- | ---: |
| `platform` | 6 | `purchase` | 9 |
| `firm` | 6 | `inventory` | 8 |
| `user` | 7 | `batch_serial` | 8 |
| `role` | 5 | `uom_framework` | 6 |
| `permission` | 5 | `pricing` | 2 |
| `customer` | 8 | `sales_targets` | 2 |
| `vendor` | 10 | `promotions` | 2 |
| `branch_warehouse` | 13 | `loyalty` | 3 |
| `tax_framework` | 14 | `tcs` | 2 |
| `product` | 11 | `commission` | 3 |
| `territory` | 9 | `accounting` | 14 |
| `sales` | 12 | `report` | 3 |
| `einvoice` | 2 | `financial_year` | 4 |
| `proforma` | 2 | `system_administration` | 4 |
| `credit_note` | 3 | `high_risk` | 6 |

Two combinations of those groups are load-bearing:

- **`platform` + `firm` + `system_administration` + `high_risk`** (22 codes) —
  what a firm role may never be granted.
- **`platform` + `firm` + `system_administration` + `user` + `role` +
  `permission`** (33 codes) — what a `PLATFORM`-scoped administrator holds.

## Rules that govern a code

- **A code you enforce must also be seeded.** An unseeded code has no permission
  row, so it cannot be attached to any role, and the endpoint silently becomes
  platform-admin-only — the admin check short-circuits the lookup.
  `tests/unit/test_identity_hardening.py::test_every_enforced_permission_code_is_seeded`
  fails the build if it recurs. Adding a code to the seed also needs a migration
  to insert it into existing databases (see `20260809_0044`).
- **`require_platform_admin()` on a route makes every permission code on it
  grant nothing**, because the designation comes from a `platform_admins` row
  and no role can reach it. `tests/unit/test_platform_only_routes.py` pins the
  **64** routes that are deliberately platform-only, with a reason per group,
  and fails both on a new one added by accident and on a pinned one that quietly
  stops being platform-only.
- **Permissions themselves are administered by the platform only.** `POST`,
  `GET /{id}`, `PATCH` and `DELETE` on `/api/v1/permissions` are all
  `require_platform_admin()`; only `GET /api/v1/permissions` takes
  `PERMISSION_VIEW`.
- **A firm's own directory of names is not a privilege.**
  `GET /api/v1/firm-members` is the one list of a firm's people, gated on
  membership and nothing else. *Acting* on a person is what needs a code.

## Adding a new permission

`POST /api/v1/permissions` exists, so a code can be created at runtime — and
doing only that gates **nothing**. No part of the application looks a
permission up by name at request time; every gate is written into a route:

```python
# app/customers/api/router.py
CustomerViewScope = Annotated[ResolvedFirmScope,
                              firm_permission_scope("CUSTOMER_VIEW")]
```

So a code created through the API, attached to a role and granted to a user is
a row nobody consults. A genuinely new capability is a code change, in five
steps, and skipping any one of them fails quietly rather than loudly.

1. **Seed the code in `PERMISSION_GROUPS`** (`app/identity/system_seed.py`).
   This is the step that bites: an unseeded code has no permission row, so it
   can be attached to no role, and the endpoint enforcing it becomes
   **platform-admin-only** — their check short-circuits the lookup, so it
   works for whoever wrote it and for nobody else. Twelve codes were in that
   state until 2026-08-09.
   `tests/unit/test_identity_hardening.py::test_every_enforced_permission_code_is_seeded`
   fails the build if it recurs.

2. **Write a migration inserting it.** `seed_system_rbac` is called by
   `generate_sample_data.py` and never at startup, so a live database gets
   seeded rows from migrations only — see `20260809_0044`.

3. **Enforce it.** `firm_permission_scope("CODE")` on a firm-owned route,
   composed the way `app/customers/api/router.py` does it;
   `require_permission("CODE")` on a platform one. Never
   `require_platform_admin()` beside a permission code — the designation makes
   every code on that route grant nothing, which is how `GET /api/v1/roles`
   came to refuse the one role whose job it is.

4. **Grant it to the roles that should hold it** in `ROLE_PERMISSION_CODES`,
   and to `_operational_permissions` if `FIRM_ADMIN` and `FIRM_MANAGER` should
   have it. That second list is hand-kept and **five groups drifted out of
   it** — `credit_note`, `proforma`, `einvoice`, `loyalty` and `tcs` each
   shipped with a module, a screen and a seeded gate that the role running the
   firm could not open.
   `tests/unit/test_firm_admin_holds_the_firms_own_modules.py` asks the
   derived question rather than naming the five.

5. **Gate the screen.** `requiredPermissions` on the module or tab in
   `desktop/lib/ui/workspace/module_catalog.dart`, or the endpoint exists and
   nothing reaches it. A tab naming no codes **inherits its module's list**,
   which is how a cashier came to hold exactly the right codes and be offered
   an empty sidebar.

**Before adding a code to any role, check its blast radius**: a permission's
reach is the set of endpoints enforcing it, not the group it is filed under.
`grep -rn CODE app/ --include=*.py` answers that in a second.

### What needs no code at all

Worth knowing before reaching for step 1, because most requests do not need
it. A firm composes its **own** access from the 167 codes already assignable
to it — a role it writes, permissions it picks, a template bundling those
roles, and the roles granted per firm — with no deployment. Only a genuinely
new *capability*, one no existing code describes, needs the five steps above.

---

# Part 4 — How a role becomes a permission on a request

At login, `IdentityService._issue_tokens` resolves the grants once and writes
them into the access token. Nothing is re-read per request except the user's
liveness and `authorization_version`.

```
platform_admins row ───────────► "platform_admin": true
                                 "platform_admin_scope": "PLATFORM" | "ALL_FIRMS"

user_roles (firm_id IS NULL)
  ∧ (role is a PLATFORM role ∨ role is custom) ──► "permissions": [...]   (global)

user_roles (firm_id = F)
  ∨ user_roles (firm_id IS NULL ∧ code ∈ FIRM_ROLE_CODES)
                                               ──► "firm_permissions": { F: [...] }
                                                     ...for every active membership
```

## The rule that surprises people

A **seeded firm role assigned globally** (`user_roles.firm_id IS NULL`) does
**not** land in the global `permissions` claim. It lands in `firm_permissions`
for **every firm the user is a member of**.

| Assignment | Where the codes land | Effect |
| --- | --- | --- |
| System firm role (e.g. `FIRM_ADMIN`), `firm_id` NULL | `firm_permissions[every membership]` | Firm administrator in each of their firms, and nothing outside one |
| System firm role, `firm_id = F` | `firm_permissions[F]` | Firm administrator in F alone |
| Custom role, `firm_id` NULL | `permissions` (global) **and** `firm_permissions` | Applies with or without a firm selected |
| Platform role (`PLATFORM_ADMIN`, `SUPPORT_ADMIN`, `LICENSE_ADMIN`, `SYSTEM_AUDITOR`), `firm_id` NULL | `permissions` (global) | Applies platform-wide |

`Principal.has_permission` checks the global set, then the set for the firm in
`X-Firm-ID`. The desktop's `PermissionService` resolves it identically — global
grants plus the grants for the **active** firm — deliberately not the union of
every firm's, which would show a user buttons the API then refuses.

## Assigning roles

`PUT /api/v1/users/{id}/roles` (`ROLE_ASSIGN`) **replaces** the set.

- A **platform caller** has a null scope: the assignment is unscoped
  (`user_roles.firm_id` NULL).
- A **firm caller** may only assign roles that firm can hold — its own
  `firm_id`-scoped roles, plus the unscoped seeded **firm** roles. A platform or
  cross-firm role is refused with *"Platform or cross-firm roles cannot be
  assigned."*

### Two tiers of grant, and neither undoes the other

A role is granted in one of two ways, and which one decides who may change it.

| | `user_roles.firm_id` | Written by | Applies |
| --- | --- | --- | --- |
| **Global** | NULL | a platform administrator only | every firm the person belongs to, including firms added later |
| **Firm** | the firm | a platform administrator naming a firm, **or** that firm's administrator | that firm |

Effective access in a firm is the **union**: `_issue_tokens` collects, per
membership, the permissions of every role where `UserRole.firm_id == <that
firm>` **or** `UserRole.firm_id IS NULL`. The tiers are strictly additive --
a firm administrator adds to what the platform granted and **cannot subtract
from it**, by design. A global `SYSTEM_AUDITOR` is therefore not removable by
the firm being audited.

`PUT /api/v1/users/{id}/roles` writes the tier the caller owns:
`_firm_scope` returns `None` for the designation, so a platform caller's save
is the *global* set, and a firm caller's is their own firm's.
`PUT /api/v1/users/{id}/firms/{firm_id}/roles` is how either administrator
writes one named firm; a firm caller is held to
`_firms_the_caller_may_staff`, and a firm outside it is refused by name.

**Each save replaces only its own tier.** `_replace_global_user_roles` touches
rows with `firm_id IS NULL`; `_replace_scoped_user_roles` touches one firm's.
That is load-bearing rather than tidy: before it, the platform path went
through `_replace_associations`, which keys on `role_id` alone and ignores
`firm_id` -- so a platform administrator who opened a user and pressed Save,
**changing nothing**, soft-deleted every firm-scoped row and re-created the
survivors unscoped. Two firms' separate grants collapsed into one global
grant, silently, from a no-op.

**Each caller is shown the tier they cannot write**, read-only, on the user
form: a firm administrator sees *Also applies here* (the global grants, which
apply in their firm), and a platform administrator sees *Roles in specific
firms* (what each firm holds, named beside its firm). Hiding either was the
same under-report pointing in opposite directions -- a firm administrator
could not tell that somebody was a firm administrator in their own firm, and a
platform administrator could not tell what anybody did in any firm.

**Each read answers for the tier its caller manages**, for the same reason.
`list_user_role_ids` returns the global set to a platform caller and one
firm's to a firm caller; it used to return every row from every firm merged
into a single list, which read as "holds all of these, everywhere" -- and then
the save made it true. `list_user_global_role_ids` is the read a firm
administrator gets of the tier they may not write: shown, because it applies
in their firm, and disabled, because it is not theirs.

### Giving one person different jobs in two firms

No second account, and no clearing required first:

1. A **platform administrator** grants anything that should apply everywhere
   on the user form (**Roles in every firm**), or leaves it empty.
2. Either administrator sets each firm's own roles under **Roles by firm** --
   on the Users grid, or from the footer of the user form -- one section per
   firm, saved one firm at a time.

**The form is one tier and Roles by firm is the other, for both callers.** A
platform administrator's form writes the global set and nothing else, and
selecting a firm in the switcher does not change that; a firm administrator's
form is their own firm's set (**Roles in this firm**), scoped by the server.
Nothing on the form names a firm. It briefly carried two more writers -- a
tier picker at create and a second column keyed off the firm switcher -- and
they were removed on 2026-09-08: two places that write the same row are two
places that can disagree, and a write keyed off the switcher is exactly what
put roles in a tier nobody chose.

Roles by firm lists, for a firm administrator, the firms the person belongs to
**and** the caller may staff (`USER_CREATE` held in that firm), which is the
set the server accepts a write for. It reads the firm names from
`/api/v1/me/firms`; until 2026-09-08 it read the platform-only `/api/v1/firms`
and answered a firm administrator with an error and no firm at all. The
per-firm read, `GET /users/{id}/firms/{firm_id}/roles`, is held to the same
reach as the write since the same day.

The person is a sales manager in one firm and a cashier in another, plus
whatever the global tier gave them in both.

## Two things that invalidate a token immediately

| Trigger | Mechanism |
| --- | --- |
| Roles changed, role edited, role permissions changed | `_revoke_user_tokens` / `_revoke_role_users` bump `users.authorization_version`; a token carrying the old number fails authentication on its next request |
| Password change required | `force_password_change` puts `password_change_required` on the token, and **every** permission check and the platform-admin check fail until it is changed — a forced reset locks the whole application, not one screen |

Other liveness checks on every request: the user must exist, not be soft-deleted,
be `is_active`, and not be past `expires_at`. Account lockout is separate and
happens at login (`AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS`, `..._LOCKOUT_MINUTES`).

---

# Part 5 — Memberships

`user_firms` joins a person to a firm. `PUT /api/v1/users/{id}/firms` takes
**`USER_UPDATE`**, limited by reach — it was `require_platform_admin()` until
2026-09-06, on the reasoning that attaching people to firms is a platform act.
That is true of *which firms exist*, and does not follow for *who works in
mine*: an administrator of two firms putting a new hire in both is the ordinary
case, and it was refused outright.

`_firms_the_caller_may_staff` limits a caller to firms where they hold
`USER_CREATE` **in that firm** — not firms they merely belong to. Two rules
follow: a firm outside that reach is refused **by name**, never silently
dropped; and the call **merges** rather than replaces, so memberships the
caller cannot see are carried through untouched.

A firm administrator may attach somebody who is not yet in their firm at all.
They find them with `GET /api/v1/users/lookup?q=` — see below.

- `is_active` — an inactive membership grants nothing.
- `is_primary` — the firm that opens by default. **One active primary per
  user**, enforced by the service and, on PostgreSQL, by the partial index
  `UQ_user_firms_active_primary`.
- The firm switcher in the shell header lists the firms the signed-in user may
  work in (`GET /api/v1/me/firms`) — their active memberships, or, for an
  `ALL_FIRMS` administrator, **every active firm**. See *Platform mode* below.
- **A platform administrator still has to pick a firm** to open firm-owned
  screens. `X-Firm-ID` is required by `required_firm_scope` regardless of
  designation; `ALL_FIRMS` skips the *membership* check, not the *header*.
- A firm with users assigned cannot be deleted — remove the memberships first.
- Soft delete releases the natural keys: a deleted user's email can be
  re-onboarded, and `users.email` is unique only among live accounts.

### Platform mode — the switcher is the mode switch

A tier-2 administrator has two jobs and one sidebar. **The firm switcher
decides which one they are doing.**

| Firm selected | What the sidebar offers |
| --- | --- |
| **Platform** (none) | Dashboard, Administration, Settings, Licensing — and, inside Administration, only the platform tabs: **Firms**, Users, Roles, Permissions, User Templates, User-Firm Assignments |
| A firm | that firm's whole application, plus everything above |

Three rules behind it, each of which was a defect before it was a rule:

- **`ALL_FIRMS` is offered every firm, not only the ones it has a membership
  row in.** The designation already exempts them from the membership check, so
  a list built from `user_firms` made their reach depend on somebody having
  remembered to insert rows. `superadmin` and `master.ops` were seeded into all
  four demo firms and worked; the bootstrap `platform-admin@agency.local` had
  none, so its switcher was **empty** while its token carried all 189 codes —
  Sales, Purchases and Inventory all offered, all unusable.
- **A `PLATFORM` administrator is deliberately not widened.** They are refused
  firm-owned routes outright, so a full switcher would offer them nothing but
  403s.
- **A platform administrator always starts in Platform mode**, whatever they
  were last working in. Their reach covers every firm's books, so restoring a
  firm would drop them into somebody's ledgers on a screen that looks like
  their own. The stored `default_firm_id` is left untouched, not cleared.

Nobody else can be in platform mode: for an ordinary user a null firm is not a
mode but an empty application, so `switchFirm(null)` refuses them.

**Firms is one of those tabs, and it used to be under Masters** — a firm's own
master data, which needs a firm selected. So the one screen that creates a firm
was reachable only from inside another firm. `FIRM_VIEW` is a platform code no
firm role may hold, so moving it costs no firm user a tab. Its **Open this
firm** action re-reads the firm list and switches into the new firm, because
the rest of setting one up — business profile, financial year, chart of
accounts — lives in that firm's own store; it is disabled for a dedicated firm
whose storage has not been provisioned, and for a retired one.

The module catalogue carries this as data — `requiresFirm` on
`ModuleDefinition` and on `ModuleTabDefinition`, defaulting to true. It is
declared per tab as well as per module because Administration holds both kinds
side by side: `users` and `roles` are platform tables, while the tax, UOM,
document-framework and business-profile tabs live in each firm's own store.

### Finding somebody who already has an account

`list_users` is scoped to the caller's own members, and its `search` is applied
*after* that filter — so a firm administrator cannot find, or even learn the
existence of, somebody who already works elsewhere. `_get_user` returns 404
rather than 403 for the same reason.

`GET /api/v1/users/lookup?q=` is the narrow opening for the one job that needs
it: hiring a person who already has an account. It is a **lookup, not a
directory**, and the limits are the design:

| Limit | Why |
| --- | --- |
| Minimum 3 characters | `"a"` must not return the platform |
| Cap of 10, **no paging** | it answers "is this them?", not "who works here?" |
| Returns `{id, full_name, email, already_a_member}` **only** | no mobile, no employee code, no status |
| **Never says which firms somebody belongs to** | the fact one firm must not learn about another |
| Excludes platform administrators | mirrors `list_users` |
| `USER_CREATE`, not `USER_VIEW` | reading your own firm's people and reaching across firms are different privileges |

Enumeration by walking prefixes remains possible; that is accepted and written
down rather than defended against. `POST /api/v1/users` already answers 409 on
a duplicate email and is a narrower oracle of the same kind.

`GET /api/v1/users/{id}/firms` is scoped to the caller's reach for the same
reason. It returned **every** membership on a route gated only by `ROLE_VIEW`
until 2026-09-06, so any firm administrator holding a user id could read which
firms that person belonged to — for every user, not only shared ones.

### Somebody who works in more than one firm

`_assert_exclusive_firm_user` refuses `update_user` and `delete_user` for
anybody with a second active membership. A user record is platform-wide, so
without it one firm could rename, deactivate or delete another firm's staff.

What their firm's administrator *may* do is set their roles and job template —
both scoped to `firm_id == firm_scope`, and both the whole point of having
them. `UserResponse.belongs_to_other_firms` carries the fact onto the row so
the screen can disable Edit rather than offer a form that cannot save.

---

# Part 6 — Hiring: templates and clone

Two ways to give a new person a job's access without reassembling it by hand.
Both are gated on **`ROLE_ASSIGN`**, not `USER_CREATE`: each ends with somebody
holding a set of roles, so whoever may open accounts but not grant access must
not be able to copy access instead.

## A user template — naming the job

`user_templates` / `user_template_roles` (`20260905_0129`). A template is a
**named bundle of roles**, deliberately not a dormant user row: a row copy
carries an email, a password, memberships, an audit trail and a login history,
and quietly inherits whatever was edited after the template was written.

**Eleven are seeded platform-wide** (`firm_id IS NULL` = offered to everybody);
a firm may add its own, visible only to it.

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

Most are one role, and that is not redundancy — **the value is the name.**
"Counter Sales" is a job a firm has; `CASHIER` plus `BILLING_EXECUTIVE` is a
permission decision somebody has to make correctly once, rather than on every
hire.

Four things to know:

- **Applying one is a plain `set_user_roles`**, so the firm-scope check that
  refuses a platform or cross-firm role applies unchanged. What the user holds
  afterwards is an ordinary role set, edited in the ordinary way, and **nothing
  on the user records which template they came from** — a user who has since
  been edited is no longer described by it.
- **The bundle is validated at creation**, not only at apply, or a template
  naming an unassignable role fails on whoever uses it weeks later with nothing
  to say the template was wrong rather than their permissions. `PLATFORM_ADMIN`
  carries every seeded code, so a firm template able to name it would be a
  second door onto the same room.
- **The code is unique per scope**, which needs two partial indexes rather than
  one: PostgreSQL treats NULLs as distinct, so a single key on `(firm_id, code)`
  would let the platform hold ten templates all called `counter-sales`.
- **The eleven are inserted by the migration**, not by `seed_system_rbac` — that
  seeder is called only by `generate_sample_data.py` and never at startup, so a
  live database gets its seeded rows from migrations.

Endpoints: `GET /api/v1/user-templates` (`ROLE_VIEW`), `POST` (`ROLE_CREATE`),
`PATCH /{id}` (`ROLE_UPDATE`), `DELETE /{id}` (`ROLE_DELETE`),
`POST /api/v1/users/{id}/apply-template` (`ROLE_ASSIGN`).

## Cloning a user — "hire like this person"

`POST /api/v1/users/{id}/clone` (`ROLE_ASSIGN`) copies **access and nothing
else.** The new user is built from scratch and given the source's roles and firm
memberships. The mobile number, employee code, joining date, photo, password,
login history, password history and audit trail are **not** copied — they belong
to the person rather than to the job. That is the whole reason it is not
"duplicate the row": a row copy carries all of it, silently. The clone always
starts with `force_password_change` — a password somebody else chose is not a
password.

The platform designation is never copied, and there are two locks on it:
`_get_user` excludes platform administrators from firm-scoped administration, so
a firm administrator cannot reach one to clone; and a platform caller who can
reach one gets their roles and not the `platform_admins` row.

A firm caller copies only what their scope can see — the firm-scoped rows plus
the unscoped firm roles — so another firm's roles stay invisible. The audit row
records `source_user_id`, because "a user was created" with nothing about where
their access came from is the one question anybody reviewing it will ask.

## Who names the firm

`_target_firm` resolves it for both the templates and the clone. **A platform
caller names the firm; a firm caller cannot.**

- A platform caller's scope resolves to null, which for a template means
  *offered to every firm* — so a "Kitchen Staff" template written while setting
  up a restaurant would otherwise be published to the wholesaler and the
  pharmacy too, and applying one would grant the job globally rather than in the
  firm being set up. `firm_id` on the request body fixes both, and null keeps
  the old meaning so nothing that worked before changes.
- A firm caller naming a **different** firm is **refused rather than ignored**.
  Silently writing it somewhere else is how the business-profile assignment
  endpoints came to report success while changing nothing.
- A template's roles are validated against the firm that will **own** it, not
  the caller's scope, or a platform operator could bundle a role that firm could
  never assign.

**Desktop:** Administration › Users, row actions *Hire like this person* (needs
`ROLE_ASSIGN` + `ROLE_VIEW` + `USER_CREATE`) and *Apply job template* (needs
`ROLE_ASSIGN` + `ROLE_VIEW`). The templates themselves are managed at
Administration › User Templates.

---

# Part 7 — Modules: what a person can actually open

The desktop declares **18 modules and 89 tabs** as data in
`desktop/lib/ui/workspace/module_catalog.dart`. Which of them a person sees is
decided by `desktop/lib/ui/workspace/module_visibility.dart` — a pure function,
so it is testable and can explain itself.

## The four module gates

Asked in this order. The order does not change the answer; it changes the
**explanation**, because a platform-admin refusal is a reason no permission list
can express.

| # | Gate | Refusal reads |
| --- | --- | --- |
| 1 | `requiresPlatformAdmin` | *platform administrators only* |
| 2 | Permission list — **all** of them, or **any** if `requiresAnyPermission` | *needs all of X, Y* / *needs any of X, Y* |
| 3 | The firm's active business modules | *this firm has switched the module off* |
| 4 | The sales stages this firm types by hand | *this firm does not type this stage of a sale* |

A **tab naming no permissions inherits the module's list and its any/all flag**,
which is why the module gate is not enough on its own.

`activeBusinessModules == null` means **show everything** — deliberately. The
codes are fetched from the server, and hiding a firm's whole application because
one request timed out is worse than briefly offering a module it has turned off.

## The catalogue

| Module | Permission gate | Any/All | Tabs | `business_modules` code |
| --- | --- | --- | ---: | --- |
| Dashboard | platform admin (+ `FIRM_VIEW`, `USER_VIEW`, `ROLE_VIEW`, `PERMISSION_VIEW` for its counts) | any | 0 | `DASHBOARD` |
| Administration | `USER_VIEW`, `ROLE_VIEW`, `PERMISSION_VIEW`, `TAX_VIEW`, `TAX_RULE_VIEW`, `TAX_SIMULATE`, `UOM_VIEW`, `UOM_MANAGE`, `PACKAGING_MANAGE`, `CONVERSION_RULE_MANAGE` | any | 23 | `ADMINISTRATION` |
| Masters | `FIRM_VIEW`, `CUSTOMER_VIEW`, `PRODUCT_VIEW`, `VENDOR_VIEW`, `BRANCH_VIEW`, `WAREHOUSE_VIEW` | any | 16 | `MASTERS` |
| Sales | `SALES_VIEW`, `TERRITORY_VIEW`, `PRICE_LIST_VIEW`, `PROMOTION_VIEW`, `COMMISSION_VIEW`, `SALES_TARGET_VIEW` | any | 16 | `SALES` |
| Quotations | `SALES_VIEW`, `SALES_QUOTATION_CREATE`, `SALES_APPROVE`, `SALES_CANCEL` | any | 0 | `SALES` |
| Sales Orders | `SALES_VIEW`, `SALES_CREATE`, `SALES_UPDATE`, `SALES_IMPORT`, `SALES_EXPORT`, `SALES_APPROVE`, `SALES_CANCEL` | any | 0 | `SALES` |
| Delivery Notes | as Sales Orders | any | 1 | `SALES` |
| Sales Invoices | as Sales Orders | any | 1 | `SALES` |
| Sales Returns | `SALES_VIEW`, `SALES_RETURN`, `SALES_UPDATE`, `SALES_APPROVE`, `SALES_CANCEL` | any | 0 | `SALES` |
| Purchases | the nine `PURCHASE_*` codes | any | 4 | `PURCHASES` |
| Purchase Invoices | seven `PURCHASE_*` codes | any | 0 | `PURCHASES` |
| Purchase Returns | seven `PURCHASE_*` codes | any | 0 | `PURCHASES` |
| Goods Receipts | seven `PURCHASE_*` codes | any | 1 | `PURCHASES` |
| Inventory | the eight `inventory` codes + `BATCH_VIEW`, `SERIAL_VIEW` | any | 14 | `INVENTORY` |
| Finance | `ACCOUNT_VIEW` | all | 9 | `ACCOUNTING` |
| Reports | `REPORT_VIEW` | all | 2 | `REPORTS` |
| Licensing | `LICENSE_MANAGE` | all | 0 | `LICENSING` — see [Part 11](#part-11--what-the-seeded-grants-do-not-cover) |
| Settings | `SETTINGS_VIEW`, `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW` | any | 2 | `SETTINGS` |

**A document is gated by the process that owns it.** All six sales documents
share the `SALES` code and all four purchase documents share `PURCHASES`;
`business_modules` has never held `SALES_ORDERS` or `GOODS_RECEIPTS`, and naming
a code the catalogue does not contain hides the module in **every firm**,
because a code that is absent can never be in the active set.

## The business-module catalogue

Fourteen codes exist, from `20260801_0011` and `20260801_0012`:

| Kind | Codes |
| --- | --- |
| Core — every profile operates them unless an administrator disables them | `DASHBOARD`, `ADMINISTRATION`, `SETTINGS`, `MASTERS`, `PRODUCTS`, `PURCHASES`, `SALES`, `INVENTORY`, `REPORTS`, `ACCOUNTING` |
| Industry — only some profiles | `KITCHEN`, `RECIPES` (RESTAURANT, MANUFACTURING), `PROJECTS`, `CONTRACTS` (SERVICE, ELECTRONICS) |

**The catalogue lives in every firm store, not in `platform`** — migrate each
firm target, and remember a firm's assignment is only visible from its own
store. See [`BUSINESS_PROFILE_FRAMEWORK.md`](BUSINESS_PROFILE_FRAMEWORK.md) for
the table map and the resolution flow.

## The sales-stage gate

`sales_workflow_settings` decides which of quotation, sales order and delivery
note a firm types by hand. All four sales documents share one business-module
code, so this cannot be expressed through the business profile — it is its own
predicate. **Sales returns are never hidden**: a counter sale still comes back,
and a return is the only correct way to undo one.

## What each seeded role is offered

Computed from the catalogue and the seed, with the business-profile gate open.
`Module(n/m)` = n of m tabs visible.

| Role | Modules | Offered |
| --- | ---: | --- |
| `PLATFORM_ADMIN` / `SUPPORT_ADMIN` | 18 | everything |
| `LICENSE_ADMIN` | 3 | Masters(3/16), Reports(2/2), Licensing |
| `SYSTEM_AUDITOR` | 4 | Administration(1/23), Masters(3/16), Reports(2/2), Settings(2/2) |
| `FIRM_ADMIN` | 16 | Administration(16/23), Masters(13/16), Sales(12/16), the five sales documents, Purchases(4/4), Purchase Invoices, Purchase Returns, Goods Receipts(1/1), Inventory(14/14), Finance(9/9), Reports(2/2), **Settings(0/2)** |
| `FIRM_MANAGER` | 15 | as `FIRM_ADMIN` minus Settings; Administration(11/23) |
| `ACCOUNTANT` | 4 | Masters(7/16), Sales(1/16), Finance(9/9), Reports(2/2) |
| `SALES_MANAGER` | 8 | Masters(5/16), Sales(15/16), the five sales documents, Reports(2/2) |
| `SALES_EXECUTIVE` | 7 | Masters(3/16), Sales(8/16), the five sales documents |
| `PURCHASE_MANAGER` / `PURCHASE_EXECUTIVE` | 4 | Purchases(4/4), Purchase Invoices, Purchase Returns, Goods Receipts(1/1) |
| `INVENTORY_MANAGER` | 1 | Inventory(14/14) |
| `CASHIER` | **0** | — see [Part 11](#part-11--what-the-seeded-grants-do-not-cover) |
| `BILLING_EXECUTIVE` | 6 | Sales(1/16), the five sales documents |
| `CUSTOMER_SUPPORT` | 1 | Masters(4/16) |
| `VIEWER` | 16 | everything readable; Inventory(12/14), Settings(1/2) |

A firm that has switched a module off removes it from every row above.

---

# Part 8 — Settings: what can be changed, by whom, and where

"Settings" is not one screen. It is five layers, each owned by a different
person, and the permission code is what says which.

## Layer 1 — Deployment settings (no screen, no API)

`backend/config/.env`, prefix `AGENCY_`; environment variables override the
file. Changing one needs a restart, and the file is never committed.

| Setting | Decides |
| --- | --- |
| `AGENCY_JWT_ACCESS_TOKEN_MINUTES` | How long a session token lasts before the client silently refreshes (default 15) |
| `AGENCY_JWT_REFRESH_TOKEN_DAYS` | How long "stay signed in" lasts (default 7) |
| `AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS` | Failed logins before the account locks (default 5) |
| `AGENCY_SECURITY_LOCKOUT_MINUTES` | How long the lock holds (default 15) |
| `AGENCY_SECURITY_PASSWORD_HISTORY_COUNT` | How many old passwords cannot be reused (default 5) |
| `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` | The first platform administrator's password. Staging and production **refuse to start** without it, or with the development JWT key |
| `AGENCY_TENANCY_*` | Where a new firm's data lives — shared database and schema names, dedicated prefixes, and `AGENCY_TENANCY_CONNECTION_PROFILES` for firms served from another server |
| `AGENCY_RETENTION_INTERVAL_SECONDS`, `AGENCY_RETENTION_MODE` | The opt-in retention job's period and whether it reports or deletes |

## Layer 2 — The platform catalogue (platform administrators only)

Every one of these is `require_platform_admin()`. They shape what firms *may*
operate, not what any one firm does.

| What | Screen | Endpoint |
| --- | --- | --- |
| Business profiles (the industries) | Administration › Business Profiles | `/api/v1/business-framework/profiles` |
| Which features a profile enables | Administration › Feature Management | `PUT /business-framework/profiles/{id}/features` |
| Which modules a profile operates | Administration › Module Configuration | `PUT /business-framework/profiles/{id}/modules` |
| Custom-field definitions | Administration › Attribute Definitions | `/business-framework/attribute-definitions` |
| Which fields a category makes mandatory | Administration › Mandatory Attributes | `/business-framework/category-attribute-rules` |
| **Which profile a firm gets** | Administration › Profile Assignment, or Masters › Firm Settings | `PUT /business-framework/firms/{id}/profile-assignment` |
| Firms, and their storage provisioning | Masters › Firms | `/api/v1/firms`, `POST /firms/{id}/provision` |
| Attaching people to firms | Administration › User-Firm Assignments | `PUT /api/v1/users/{id}/firms` |
| The permission catalogue itself | Administration › Permissions (read is `PERMISSION_VIEW`) | `/api/v1/permissions` |

`is_implemented = false` on a feature means the platform has no code behind it;
the service **refuses to enable it**. That flag is a fact about the codebase and
deliberately not `is_active`, which is an administrator's choice.

## Layer 3 — Firm-wide settings

| Setting | Decides | Read | Write | Screen |
| --- | --- | --- | --- | --- |
| Business profile assignment | Which features and modules this firm operates | `FIRM_VIEW` | platform admin | Masters › Firm Settings |
| Document numbering rules | The prefix, width, reset cycle and manual-number policy per document type | `SETTINGS_VIEW` | `SETTINGS_UPDATE` | Administration › Numbering Series |
| Print templates | What a printed document looks like | firm membership | firm membership | per-document print action |
| Financial years | Which period is open, and what may post | `FINANCIAL_YEAR_VIEW` | `FINANCIAL_YEAR_CREATE` creates, edits and deletes a year; closing or reopening a period is `FINANCIAL_YEAR_CLOSE` | Masters › Financial Years |
| Branch & warehouse defaults | A capability report today rather than editable settings | `BRANCH_VIEW` | — | Masters › Settings |

## Layer 4 — Module policies

These are the switches that change how a module behaves for the whole firm. Each
is split so that the role a policy constrains cannot rewrite it.

| Policy | Decides | Read | Write | Screen | Endpoint |
| --- | --- | --- | --- | --- | --- |
| **Credit control** | `OFF` / `WARN` / `BLOCK`, and the warn and block percentages, checked at sales-order and sales-invoice approval | `CUSTOMER_VIEW` | `CUSTOMER_MANAGE_SETTINGS` | Customers workspace › Settings | `GET`/`PUT /api/v1/customers/credit-settings` |
| **Customer groups** | The firm's own segmentation, and the last tier of the discount ladder | `CUSTOMER_VIEW` | `CUSTOMER_MANAGE_SETTINGS` | Masters › Customers | `/api/v1/customers/groups` |
| **Sales workflow stages** | Which of quotation, sales order and delivery note this firm types by hand | `SALES_VIEW` | `SALES_MANAGE_SETTINGS` | Sales Invoices workspace › workflow settings | `GET`/`PUT /api/v1/sales-orders/workflow-settings` |
| **Tax settings** | The firm's tax system, profile and defaults | `TAX_VIEW` | `TAX_MANAGE_SETTINGS` | Administration › Tax › Settings | `GET`/`PUT /api/v1/tax-framework/settings` |
| **Loyalty scheme** | The conversion rate, and `expiry_months` (NULL = points never expire) | `LOYALTY_VIEW` | `LOYALTY_MANAGE_SETTINGS` | Masters › Loyalty | `GET`/`PUT /api/v1/loyalty/settings` |
| **TCS policy** | Whether 206C(1H) is collected, the threshold and the rate. `is_enabled` defaults false | `TCS_VIEW` | `TCS_MANAGE` | Sales › TCS | `GET`/`PUT /api/v1/tcs/settings` |
| **Commission rules** | Rate, basis, ladder, floor, bonus and cap | `COMMISSION_VIEW` | `COMMISSION_MANAGE`; paying is `COMMISSION_PAY` | Sales › Commission | `/api/v1/commission` |
| **Promotions** | The offers, their conditions and their stacking | `PROMOTION_VIEW` | `PROMOTION_MANAGE` | Sales › Promotions | `/api/v1/promotions` |
| **Price lists** | The ladder of rates per product and quantity break | `PRICE_LIST_VIEW` | `PRICE_LIST_MANAGE` | Sales › Price Lists | `/api/v1/price-lists` |
| **Sales targets** | The numbers a salesman is measured on | `SALES_TARGET_VIEW` | `SALES_TARGET_MANAGE` | Sales › Targets | `/api/v1/sales-targets` |
| **UOM conversion rules** | How a purchase unit becomes an inventory unit | `UOM_VIEW` | `CONVERSION_RULE_MANAGE`, `PACKAGING_MANAGE`, `UOM_MANAGE` | Administration › UOM tabs | `/api/v1/uom-framework` |
| **Tax rules** | Which rate applies to which transaction | `TAX_RULE_VIEW` | `TAX_RULE_CREATE` / `_UPDATE` / `_DELETE` | Administration › Tax Rules | `/api/v1/tax-framework/rules` |

## Layer 5 — Per-user preferences

`GET` / `PATCH /api/v1/me/preferences`, and `POST /me/preferences/reset`. Only
`authenticated` — a person's own client settings need no code, and nobody else
can read them. Stored in `user_preferences` in the platform schema.

## Where the audit trail of a change lives

**A firm's trail is its own store plus the platform rows carrying its
`firm_id`.** Most firm-owned mutations are recorded in the firm's own store,
because `record_audit` runs on whichever session `get_db` resolved. Identity is
the exception and cannot not be: `users`, `roles` and `user_firms` live only in
the platform schema, so hiring somebody, editing their roles or applying a job
template runs on the platform session and is recorded there.

Those rows carry the firm. They were simply in a store the firm cannot read, so
until 2026-09-06 a firm administrator could not see their own staffing
decisions. `GET /api/v1/audit-logs` with `X-Firm-ID` now reads both.

The write was left where it is on purpose. A DATABASE-mode firm is a separate
database, possibly on a separate server, so writing the audit row there would
be a second transaction — the promotion could commit and its record fail, or
the reverse. They commit together today, and that is worth more than the row's
location.

| Reading | Sees |
| --- | --- |
| No `X-Firm-ID`, platform designation | The platform trail: firm creation, platform templates, anything belonging to no firm |
| `X-Firm-ID`, any authorised caller | That firm's own store **and** the platform rows whose `firm_id` is that firm |
| Anything else | Refused |

One firm never sees another's, and the platform's own unscoped rows
(`firm_id IS NULL`) are nobody's firm history.


**Per store, not central.** Platform administration writes to
`platform.audit_logs`; a firm-owned change writes to that firm's own store,
because `record_audit` runs on whichever session `get_db` resolved.
`GET /api/v1/audit-logs` reads **one** trail, chosen by firm context — no
`X-Firm-ID` plus platform authority gives the platform trail, `X-Firm-ID` gives
that firm's. No single query can answer "everything that happened".

---

# Part 9 — Recipes

### Hire somebody into an existing job

1. Administration › Users › **New** — email, name, a temporary password
   (`USER_CREATE`).
2. Row action **Apply job template**, pick the job (`ROLE_ASSIGN` +
   `ROLE_VIEW`).
3. Administration › User-Firm Assignments — attach them to the firm and mark it
   primary (platform administrator).
4. They sign in, are forced to change the password, and land in their firm.

Steps 1 and 2 collapse into one if you use **Hire like this person** on somebody
who already holds the right access — that also copies their memberships when a
platform caller runs it, so step 3 can be skipped.

### Give one job a capability it lacks

Do **not** edit a system role — it is immutable through the API and shared by
every firm. Instead:

1. Administration › Roles › **New**, with a lowercase code that is not reserved
   (`ROLE_CREATE`). A firm caller's role is owned by their firm automatically.
2. Attach the codes it should grant (`ROLE_ASSIGN`). A firm caller cannot attach
   any of the 22 platform codes.
3. Assign it alongside the person's existing roles (`ROLE_ASSIGN`). Permissions
   are a union, so a custom role adds to what they already hold.

Everybody holding a role you edit is signed out on their next request, by
design.

### Write a job template for one firm

`POST /api/v1/user-templates` with `firm_id` set to that firm (a platform caller
must name it; a firm caller's own firm is implied and naming a different one is
refused). The roles are validated against the **owning** firm.

### Turn a module off for one firm

The module list is a property of the **business profile**, not of the firm — so
either assign that firm a profile whose module set is right, or edit the
profile's module set (Administration › Module Configuration), remembering that
every firm on that profile is affected. Both are platform-administrator acts.

### Stop typing delivery notes

Sales Invoices workspace › workflow settings, clear the delivery-note stage
(`SALES_MANAGE_SETTINGS`). The chain still raises the document — `SalesChainService`
drives the same services a person would, so stock still leaves at dispatch and
cost of goods sold still belongs to the delivery note — but nobody types it and
the module disappears from the sidebar. The switch governs **new** documents
only, so turning a stage back on never strands work in flight.

### Narrow a platform administrator to platform work

Set `platform_admins.scope` to `PLATFORM` for that row. There is no endpoint;
this is a deliberate database change. They keep every platform screen and are
refused every firm-owned route unless they hold a real membership — in which
case they act there as their roles allow.

### Take access away

| Goal | Do this | Effect |
| --- | --- | --- |
| Stop them working in one firm | Deactivate the `user_firms` row | That firm's grants vanish from the next token |
| Stop them entirely, keep the record | `is_active = false` on the user | Every request fails authentication |
| Remove one capability | Reassign roles without it (`ROLE_ASSIGN`) | Tokens are revoked immediately |
| Retire a shared capability | Deactivate the role (`is_active = false`) | Nobody holding it gets those codes any more |
| Off-board | Soft-delete the user | The email is released for re-onboarding |

---

# Part 10 — Rules that bite

- **A permission code that is enforced but not seeded silently becomes
  platform-admin-only.** If a role "has" a permission and the screen still
  refuses, check this first.
- **`require_platform_admin()` on a route makes its permission codes
  meaningless.** `GET /api/v1/roles` had exactly this — the only one of the four
  role endpoints on the designation — so `ROLE_VIEW` was seeded, granted to
  `FIRM_ADMIN`, and honoured everywhere except the screen a firm administrator
  starts from. Found on 2026-09-05 by driving the endpoint with a real firm-admin
  token, not by reading the code.
- **A system role cannot be edited, and that is not a bug.** Add a custom role
  beside it.
- **A globally-assigned system firm role is not a global permission.** It
  applies inside each firm the person is a member of, and nowhere else.
- **A forced password change locks the whole application**, not one screen —
  every permission check fails until it is done.
- **A platform administrator still needs `X-Firm-ID`** for firm-owned screens.
  `ALL_FIRMS` skips the membership check, not the header. Which is why the
  switcher offers them every firm, and why picking one is what turns the
  firm-owned modules on.
- **The desktop's module filtering is cosmetic.** It hides menu entries; the
  server is the boundary.
- **`GET /api/v1/roles`, `/permissions` and `/users` list what the caller's
  scope can see.** A firm caller sees their own firm's roles plus the unscoped
  ones, never another firm's.
- **Three retention tables grow forever** — `refresh_tokens`, `login_history`,
  `password_history` — unless `scripts/purge_retention.py` is scheduled
  (`docker compose --profile retention up -d`, opt-in on purpose).
- **Role and permission changes revoke tokens.** Expect users to be signed out
  when you edit access; that is `authorization_version` doing its job.

---

# Part 11 — What the seeded grants do not cover

Derived mechanically from the seed and the module catalogue on 2026-09-06, and
verifiable with the commands below. None of these is a defect report: each is a
**question for whoever owns the seed**, in the same spirit as
[`FUNCTIONAL_GUIDE.md`](FUNCTIONAL_GUIDE.md)'s "four permission rows worth
questioning".

### ~~`CASHIER` is offered no module at all~~ — fixed

**Fixed 2026-09-06.** The role holds `RECEIPT_CREATE`, `RECEIPT_VIEW`,
`PAYMENT_CREATE`, `PAYMENT_VIEW`. Receipts and Payments are tabs of **Finance**,
whose gate was `ACCOUNT_VIEW` (all), and whose tabs named no codes of their own
so they inherited it. A cashier signed in to an empty sidebar — a working
account, correct permissions, nothing on screen. `BILLING_EXECUTIVE` is offered
six modules, so the seeded `counter-sales` template (`CASHIER` +
`BILLING_EXECUTIVE`) hid it; a cashier on their own was not something anybody
had made.

Finance now takes **any of** `ACCOUNT_VIEW`, `RECEIPT_VIEW`, `PAYMENT_VIEW`,
and **every tab names its own code**:

| Tab | Gate |
| --- | --- |
| Chart of Accounts | `ACCOUNT_VIEW` |
| Journal Entries | `JOURNAL_VIEW` |
| Receipts | `RECEIPT_VIEW` |
| Payments | `PAYMENT_VIEW` |
| Refunds | `ACCOUNT_VIEW` |
| Ledgers | `LEDGER_VIEW` |
| Trial Balance | `TRIAL_BALANCE_VIEW` |
| Profit & Loss | `PROFIT_LOSS_VIEW` |
| Balance Sheet | `BALANCE_SHEET_VIEW` |

Both halves were necessary. Widening the module gate alone would have fixed the
empty sidebar by handing a cashier the chart of accounts and the journal.

A cashier sees Finance with **Receipts and Payments**, and nothing else.
`ACCOUNTANT`, `FIRM_ADMIN` and `VIEWER` keep all nine — every code above is one
they already held, which is asserted rather than assumed. Refunds keeps
`ACCOUNT_VIEW` because no `REFUND_*` code exists and reversing a settlement is
not the job of whoever took the money.

`tests/unit/test_every_role_can_open_something.py` asks the question of every
seeded firm role, so the next stranded one fails the build.

### ~~`FIRM_ADMIN` is not granted six of the firm's own modules~~ — fixed

**Five of the six were granted on 2026-09-06** (`20260906_0130`).
`_operational_permissions` named eighteen groups and the groups added since had
never been added to it, so a firm administrator held **none** of:

| Group | Codes | Was not offered | Now |
| --- | --- | --- | --- |
| `credit_note` | `CREDIT_NOTE_VIEW`, `_MANAGE`, `_APPROVE` | Sales › Credit Notes | granted |
| `proforma` | `PROFORMA_VIEW`, `_MANAGE` | Sales › Proforma | granted |
| `einvoice` | `EINVOICE_VIEW`, `_MANAGE` | Sales › E-Invoice | granted |
| `loyalty` | `LOYALTY_VIEW`, `_MANAGE`, `_MANAGE_SETTINGS` | Masters › Loyalty | granted |
| `tcs` | `TCS_VIEW`, `_MANAGE` | Sales › TCS | granted |
| `firm` | `FIRM_VIEW` and the five others | Administration › Firms, Firm Settings | **still withheld, deliberately** |

User-Firm Assignments is no longer in that row: it asks for `USER_VIEW` and
`USER_UPDATE`, which a firm administrator holds, and is platform-only by a
tab-level `requiresPlatformAdmin` flag instead -- a subset of the Users form
that a firm administrator reaches anyway from Users › Edit › Firms.

`SALES_MANAGER` held most of the first five, so the screens were reachable by
somebody — just not by the role whose description is "runs the firm and every
module", which is why it survived until this file's survey asked the question
mechanically. `FIRM_MANAGER` gained the same twelve codes, since it is
`_operational_permissions` less the administration ones.

`FIRM_VIEW` and its group stay out: they are in `PLATFORM_PERMISSION_CODES`,
and deciding which firms exist is not a firm's own business. The desktop no
longer needs it — the users grid reads `/api/v1/me/firms`.

**The list is no longer hand-kept in a way that can drift silently.**
`tests/unit/test_firm_admin_holds_the_firms_own_modules.py` derives which
groups are operational — neither platform-withheld nor firm administration —
and fails when `_operational_permissions` omits one. Removing `loyalty` or
`credit_note` from the list fails it, which is how it was checked.

### ~~`FIRM_ADMIN` sees the Settings module with no tabs~~ — fixed

**Fixed 2026-09-06** (`20260906_0131`). Settings is offered on **any** of
`SETTINGS_VIEW`, `AUDIT_LOG_VIEW`, `DIAGNOSTICS_VIEW`; `FIRM_ADMIN` held only
the first, and both tabs demand one of the other two, so the module was offered
and every tab in it refused — it opened empty.

`AUDIT_LOG_VIEW` is granted directly, alongside `SETTINGS_VIEW` and
`SETTINGS_UPDATE` and for the same reason: `PLATFORM_PERMISSION_CODES` answers
*"what may a firm administrator not **grant**"*, which is a different question
from what they may hold. `audit_scope` reads **one** trail chosen by firm
context and still applies the membership check, so with `X-Firm-ID` they get
their own firm's history and nothing else — driven: 200 on their firm, 403 on
the platform trail.

`DIAGNOSTICS_VIEW` deliberately stays out, so **Diagnostics remains refused**
and the tab does not appear. Error reports are operational telemetry for
whoever maintains the product, kept in one place rather than per firm.

### The audit trail was unreachable for every platform administrator

Found on 2026-09-06, and **introduced on 2026-09-05 by the escalation fix in
#235**. That change moved the designation out of the `roles` claim into its
own; `audit_scope` tested `"platform_admin" in principal.roles` in two places,
which a grep for `is_platform_admin` did not find. The condition became
permanently false, so a platform administrator was refused the platform trail
by name and then refused every firm's trail by the membership check they have
no rows for.

It survived a full green suite because `test_audit_trail_api.py` built its
principal with `roles={"platform_admin"}` — the shape the application had
stopped issuing. **A fixture that supplies the old shape cannot see the
break.** The fixtures now build what `_issue_tokens` mints, and with them in
place the reverted router fails 2 of 6.

`tests/unit/test_identity_hardening.py::
test_no_module_reads_the_designation_out_of_the_roles_claim` is the guard. It
strips comments before matching, because a naive grep flags the comment that
*warns* against the pattern — the same false positive the `date.today()` sweep
hit.

### The Licensing module names a business-module code that does not exist

`ModuleCatalog.businessModuleCode` maps Licensing to `LICENSING`, and
`business_modules` holds fourteen codes, none of them `LICENSING`. A code that
is absent can never be in a firm's active set, so the module is hidden in every
firm as soon as the active-module fetch succeeds — the same shape as the
`SALES_ORDERS` / `GOODS_RECEIPTS` trap already recorded in the catalogue's own
comments. Licensing is deferred work, so this is recorded rather than raised.

### Two guards read oddly against their neighbours

| Endpoint | Guard | Why it reads oddly |
| --- | --- | --- |
| `GET /api/v1/roles/{id}/permissions` | `PERMISSION_ASSIGN` | Reading what a role holds needs the code for *granting* permissions, while reading the role itself needs only `ROLE_VIEW` |
| `GET /api/v1/users/{id}/firms` | `ROLE_VIEW` | A membership question answered behind a role code; the sibling `/users/{id}/roles` correctly takes `USER_VIEW or ROLE_VIEW` |

(The two other rows `FUNCTIONAL_GUIDE.md` listed have since changed:
`POST /api/v1/permissions` is now `require_platform_admin()`, and
`GET /api/v1/roles` now takes `ROLE_VIEW`.)

---

# How to re-derive every number in this file

Prefer a command that counts to a list that rots. From `backend/`:

```powershell
# 189 codes, 30 groups, 16 roles, 11 templates, and every per-role count
uv run python -c "from app.identity.system_seed import *; print(len(SYSTEM_PERMISSION_CODES), len(PERMISSION_GROUPS), len(SYSTEM_ROLE_CODES), len(SYSTEM_USER_TEMPLATES)); [print(c, len(ROLE_PERMISSION_CODES[c])) for c in SYSTEM_ROLE_CODES]"

# What guards every endpoint — the authority for every permission column above
uv run python scripts/dump_route_permissions.py                # every module
uv run python scripts/dump_route_permissions.py --markdown identity

# The 64 deliberately platform-only routes, and the seeded-code guard
uv run pytest tests/unit/test_platform_only_routes.py tests/unit/test_identity_hardening.py -q
```

From `desktop/`:

```powershell
# 18 modules and 89 tabs
Select-String -Path lib\ui\workspace\module_catalog.dart -Pattern 'ModuleDefinition\(|ModuleTabDefinition\(' | Measure-Object

# The visibility rules themselves
flutter test test\module_visibility_test.dart
```

If `uv run` fails with `uv trampoline failed to canonicalize script path`, use
`.\.venv\Scripts\python.exe` instead — that is a `uv` launcher bug on Windows.

## Where each fact in this file lives

| Claim | Source of truth |
| --- | --- |
| Roles, permissions, templates, and who holds what | `backend/app/identity/system_seed.py` |
| The designation and its two reaches | `backend/app/core/enums.py`, `backend/app/core/security/authorization.py` |
| How a role reaches a request | `IdentityService._issue_tokens` |
| Permission + membership on firm routes | `backend/app/common/scope.py` |
| What guards each endpoint | `scripts/dump_route_permissions.py` |
| Modules, tabs and their gates | `desktop/lib/ui/workspace/module_catalog.dart` |
| Who is offered which module | `desktop/lib/ui/workspace/module_visibility.dart` |
| Client-side grant resolution | `desktop/lib/core/security/permission_service.dart` |
| The business-module catalogue | `20260801_0011`, `20260801_0012`, `20260809_0046` |
