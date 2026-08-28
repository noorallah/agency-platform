# Module flows and permissions

One section per module: the workflows it supports, the permission each step
enforces, and what each step writes. Filled in **as each session of**
[`LEARNING_PLAN.md`](LEARNING_PLAN.md) **is worked through** — a module with no
section here has not been covered yet, and the checklist at the bottom says
which those are.

The point of the exercise is not the list. It is that writing the permission
column down forces you to read the guard rather than assume it, and this
repository has a history of that being where the surprise is: twelve permission
codes were enforced but never seeded (making their endpoints silently
platform-admin-only), nineteen handlers took a bare `ResolvedFirmScope` FastAPI
read as a request body, and ten literal paths were shadowed by `/{id}`.

---

## How to regenerate the permission tables

`backend/scripts/dump_route_permissions.py` reads the routers with `ast` — no
database, no server, no settings file:

```powershell
uv run python scripts/dump_route_permissions.py                    # all 588
uv run python scripts/dump_route_permissions.py --markdown firms   # one module
```

**Regenerate rather than hand-edit.** A table typed by hand is the failure mode
this file exists to avoid.

### Reading the Permission column

| Value | Means |
| --- | --- |
| `CODE` | `require_permission("CODE")`, plus firm-scope where the router composes it |
| `A + B` | Both codes required |
| `A or B` | `require_any_permission` — either will do |
| `PLATFORM-ADMIN` | `require_platform_admin()`. **Also what an unseeded code degrades to**, because the platform-admin check short-circuits the lookup |
| `firm-scope only` | Active `UserFirm` membership for `X-Firm-ID`, and nothing more |
| `authenticated` | A valid token, no permission code |
| `-- none --` | Open. Five endpoints, all deliberate (see below) |

A permission code alone is never the whole check on a firm-owned route: the
scope dependency validates active membership of the `X-Firm-ID` firm as well,
and **platform admins are not exempt from supplying one**.

## The platform in numbers

Measured 2026-08-28 by the script above.

| | |
| --- | ---: |
| Endpoints | 588 |
| Distinct permission codes enforced | 133 |
| Endpoints open to an unauthenticated caller | 5 |

The five open ones, all deliberate: `GET /health`, `GET /health/database`,
`POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` (the last three
carry their own credentials). `POST /api/v1/diagnostics/client-errors` is
authenticated but carries no permission code, because a client that has just
crashed must still be able to say so.

The most-used guards, which tells you where the surface actually is:

| Guard | Endpoints |
| --- | ---: |
| `SALES_VIEW` | 48 |
| `PLATFORM-ADMIN` | 39 |
| `PURCHASE_VIEW` | 33 |
| `PLATFORM-ADMIN, firm-scope only` | 29 |
| `TERRITORY_VIEW` | 23 |
| `SALES_APPROVE` | 15 |

---

# Session 1 — the frame

Not a module. It is the two-part check every module below composes, so it is
recorded once here rather than in each section.

**A firm-owned request is authorized twice.** `firm_permission_scope(code)`
(`app/common/scope.py:148`) composes:

1. `require_permission(code)` — does this principal hold the code, through a
   role assignment?
2. `required_firm_scope` — is the `X-Firm-ID` firm active, and does this
   principal hold an **active `UserFirm` membership** in it?

Both are resolved against a **platform** session (`get_platform_db`), because
`firms`, `user_firms` and `users` exist only in the platform schema.

| Concern | Where | Note |
| --- | --- | --- |
| Which store a request reads | `app/core/database/dependencies.py:22` | `_is_platform_path` first, then the tenant resolver |
| Which firm the caller may act on | `app/common/scope.py:72` | Always on a platform session |
| Which codes exist at all | `app/identity/system_seed.py` | `PERMISSION_GROUPS`; an unseeded code is enforced but ungrantable |
| One named firm's store from a platform screen | `dependencies.py:46` | `firm_store_session(request, firm_id)` |

---

# Session 2 — `firms` and `identity`

## `firms` — the firm registry

Platform-only: six endpoints, all `PLATFORM-ADMIN`, no firm scoping to reason
about. That is why it is the module to learn the five layers on.

### Workflows

**Onboarding a firm** — two steps on purpose, not one:

| # | Step | Endpoint | Permission | Writes |
| --- | --- | --- | --- | --- |
| 1 | Record the firm and its intended storage | `POST /api/v1/firms` | `PLATFORM-ADMIN` | `firms`, `firm_storage_mappings` (intent only), `audit_logs` (platform) |
| 2 | Build that storage | `POST /api/v1/firms/{id}/provision` | `PLATFORM-ADMIN` | Creates the database and/or schema, runs `alembic upgrade head` **in a subprocess**, prunes platform tables, sets `provisioned_at`; `audit_logs` |

Step 1 only records intent. A remote server that is slow or unreachable must
not fail the creation of a firm *record* — so nothing is built until step 2,
and until it succeeds `FirmRegistryTenantResolver` refuses the firm by name
(`app/core/tenancy/resolvers.py:122`) rather than letting a query fail deep
inside with "relation does not exist". A failure stores its reason in
`provisioning_error` (`firm_service.py:96`), so the firm page can say what went
wrong instead of only "not provisioned".

**Re-running step 2 is the repair action.** Every step is create-if-missing and
Alembic stops at head.

**Amending a firm**

| # | Step | Endpoint | Permission | Refuses |
| --- | --- | --- | --- | --- |
| 1 | Read (take the `ETag`) | `GET /api/v1/firms/{id}` | `PLATFORM-ADMIN` | — |
| 2 | Update, echoing `If-Match` | `PUT /api/v1/firms/{id}` | `PLATFORM-ADMIN` | Any change to `deployment_mode` / `schema_name` / `database_name` / `connection_profile`; a stale `If-Match` → 409 |
| 3 | Soft delete | `DELETE /api/v1/firms/{id}` | `PLATFORM-ADMIN` | A firm with assigned users |

**A firm's storage routing is fixed at creation** — nothing migrates rows
between stores, so the update refuses it rather than silently re-pointing a
firm at an empty schema. Omitted tenancy fields inherit the stored mapping
instead of defaulting to `SHARED`, which is the bug that shape had.

### Endpoints

| Method | Path | Permission | Handler |
| --- | --- | --- | --- |
| GET | `/api/v1/firms` | `PLATFORM-ADMIN` | `list_firms` |
| POST | `/api/v1/firms` | `PLATFORM-ADMIN` | `create_firm` |
| GET | `/api/v1/firms/{firm_id}` | `PLATFORM-ADMIN` | `get_firm` |
| PUT | `/api/v1/firms/{firm_id}` | `PLATFORM-ADMIN` | `update_firm` |
| POST | `/api/v1/firms/{firm_id}/provision` | `PLATFORM-ADMIN` | `provision_firm_storage` |
| DELETE | `/api/v1/firms/{firm_id}` | `PLATFORM-ADMIN` | `delete_firm` |

## `identity` — who exists, and what they may do

29 endpoints and the only module whose *own* data decides every other module's
answers.

### Workflows

**Signing in**

| # | Step | Endpoint | Permission | Note |
| --- | --- | --- | --- | --- |
| 1 | Log in | `POST /api/v1/auth/login` | `-- none --` | Writes `login_history`; issues access + refresh tokens |
| 2 | Pick a firm | `GET /api/v1/me/firms` | `authenticated` | The client's firm switcher; only the refresh token is persisted, in the OS vault |
| 3 | Renew | `POST /api/v1/auth/refresh` | `-- none --` | Carries its own credential; the desktop retries a 401 exactly once |
| 4 | Change password | `POST /api/v1/auth/change-password` | `authenticated` | A principal flagged for password change fails **every** permission check until it does |

**Onboarding a person** — three separate grants, in this order:

| # | Step | Endpoint | Permission | Grants |
| --- | --- | --- | --- | --- |
| 1 | Create the account | `POST /api/v1/users` | `USER_CREATE` | Nothing yet — an account with no membership can log in and open nothing |
| 2 | Give them roles | `PUT /api/v1/users/{id}/roles` | `ROLE_ASSIGN` | The permission codes behind those roles |
| 3 | Give them firms | `PUT /api/v1/users/{id}/firms` | `PLATFORM-ADMIN` | `UserFirm` membership — the *second* half of every firm-owned check |

Step 3 being platform-admin is the deliberate part: a role grants what someone
may **do**, membership decides **whose data** they may do it to, and the two
are held by different people.

**Defining what a role means**

| # | Step | Endpoint | Permission |
| --- | --- | --- | --- |
| 1 | List the catalogue | `GET /api/v1/permissions` | `PERMISSION_VIEW` |
| 2 | Create a role | `POST /api/v1/roles` | `ROLE_CREATE` |
| 3 | Attach codes to it | `PUT /api/v1/roles/{id}/permissions` | `ROLE_ASSIGN` |
| 4 | Read what it holds | `GET /api/v1/roles/{id}/permissions` | `PERMISSION_ASSIGN` |

System roles and permissions are immutable through the API.

### Endpoints

| Method | Path | Permission | Handler |
| --- | --- | --- | --- |
| POST | `/auth/login` | `-- none --` | `login` |
| POST | `/auth/refresh` | `-- none --` | `refresh` |
| POST | `/auth/logout` | `-- none --` | `logout` |
| POST | `/auth/change-password` | `authenticated` | `change_password` |
| GET | `/me/preferences` | `authenticated` | `get_my_preferences` |
| PATCH | `/me/preferences` | `authenticated` | `update_my_preferences` |
| POST | `/me/preferences/reset` | `authenticated` | `reset_my_preferences` |
| GET | `/me/firms` | `authenticated` | `list_my_firms` |
| GET | `/users` | `USER_VIEW` | `list_users` |
| POST | `/users` | `USER_CREATE` | `create_user` |
| GET | `/users/{user_id}` | `USER_VIEW` | `get_user` |
| PATCH | `/users/{user_id}` | `USER_UPDATE` | `update_user` |
| DELETE | `/users/{user_id}` | `USER_DELETE` | `delete_user` |
| PUT | `/users/{user_id}/roles` | `ROLE_ASSIGN` | `set_user_roles` |
| GET | `/users/{user_id}/roles` | `USER_VIEW or ROLE_VIEW` | `list_user_roles` |
| GET | `/users/{user_id}/firms` | `ROLE_VIEW` | `list_user_firms` |
| PUT | `/users/{user_id}/firms` | `PLATFORM-ADMIN` | `set_user_firms` |
| GET | `/roles` | `PLATFORM-ADMIN` | `list_roles` |
| POST | `/roles` | `ROLE_CREATE` | `create_role` |
| GET | `/roles/{role_id}` | `ROLE_VIEW` | `get_role` |
| PATCH | `/roles/{role_id}` | `ROLE_UPDATE` | `update_role` |
| DELETE | `/roles/{role_id}` | `ROLE_DELETE` | `delete_role` |
| PUT | `/roles/{role_id}/permissions` | `ROLE_ASSIGN` | `set_role_permissions` |
| GET | `/roles/{role_id}/permissions` | `PERMISSION_ASSIGN` | `list_role_permissions` |
| GET | `/permissions` | `PERMISSION_VIEW` | `list_permissions` |
| POST | `/permissions` | `PERMISSION_VIEW` | `create_permission` |
| GET | `/permissions/{permission_id}` | `PLATFORM-ADMIN` | `get_permission` |
| PATCH | `/permissions/{permission_id}` | `PLATFORM-ADMIN` | `update_permission` |
| DELETE | `/permissions/{permission_id}` | `PLATFORM-ADMIN` | `delete_permission` |

Paths are relative to `/api/v1`.

### Four rows worth arguing about

Building this table is what surfaced them; none is a defect I have driven, and
each is a question the module owner should answer.

1. **`POST /permissions` is gated on `PERMISSION_VIEW`** — a *read* code on a
   write endpoint. `PermissionCreatePrincipal` is declared at
   `app/identity/api/router.py:73` bound to `PERMISSION_CREATE` and **used
   nowhere**; `PermissionUpdatePrincipal` and `PermissionDeletePrincipal` are
   dead in the same way, their endpoints falling back to `PLATFORM-ADMIN`.
   All five codes *are* seeded, so this is wiring, not seeding. Severity turns
   on who holds `PERMISSION_VIEW`: `VIEWER` explicitly excludes it, so the
   likely answer is "only administrators" — which would make it untidy rather
   than dangerous. Worth confirming rather than assuming.
2. **`GET /roles/{id}/permissions` needs `PERMISSION_ASSIGN`** to *read* what a
   role holds, while `GET /roles/{id}` needs only `ROLE_VIEW`. Reading a role's
   codes is what a screen showing that role has to do.
3. **`GET /users/{id}/firms` needs `ROLE_VIEW`** — a role code answering a
   membership question. Compare `list_user_roles`, which correctly takes
   `USER_VIEW or ROLE_VIEW`.
4. **`GET /roles` is `PLATFORM-ADMIN` while `GET /roles/{id}` is `ROLE_VIEW`.**
   The list is stricter than the item it lists.

## `common` — the two shared routers

| Method | Path | Permission | Handler | Note |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/audit-logs` | `AUDIT_LOG_VIEW` | `list_audit_logs` | Reads **one** trail, chosen by firm context: no `X-Firm-ID` + platform authority → the platform trail; `X-Firm-ID` → that firm's |
| GET | `/api/v1/firm-members` | `firm-scope only` | `list_firm_members` | Deliberately no permission code — a firm's own directory of names is not a privilege; *acting* on a person is what needs one |

`firm-members` replaced three copies of the same list behind
`TERRITORY_ASSIGN_SALESMEN`, `COMMISSION_VIEW` and `USER_VIEW`, none of which
the sales-order form held — so it offered no salesman field at all.

---

# Still to fill in

One section per session, in [`LEARNING_PLAN.md`](LEARNING_PLAN.md) order.

| Session | Modules | Done |
| ---: | --- | --- |
| 1 | the frame | ✅ |
| 2 | `firms`, `identity`, `common` | ✅ |
| 3 | `customers` | ☐ |
| 4 | `products`, `vendors` | ☐ |
| 5 | `branches`, geography | ☐ |
| 6 | `business` | ☐ |
| 7 | `uom` | ☐ |
| 8 | `tax` | ☐ |
| 9 | `document_framework` | ☐ |
| 10 | `inventory`, `batch_serial` | ☐ |
| 11 | `purchase` | ☐ |
| 12 | `goods_receipt`, `purchase_invoice`, `purchase_return` | ☐ |
| 13 | `quotation`, `sales_order`, `delivery_note` | ☐ |
| 14 | `sales_invoice`, `sales_return`, `pricing` | ☐ |
| 15 | `finance` | ☐ |
| 16 | `settlements`, `commission` | ☐ |
| 17 | `sales` (territory) | ☐ |
| 18 | `search`, `diagnostics`, desktop | ☐ |

**The section format, so each one is comparable:** the module's workflows as
numbered steps (endpoint, permission, what it writes or refuses), then the full
endpoint table pasted from the script, then the rows worth arguing about.
