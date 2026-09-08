# Platform administration guide

This guide shows how a platform administrator creates permissions, roles,
firms, and users, then maps users to roles and firms. All examples use the
backend REST API; the Flutter desktop client follows the same workflow.

## Before you begin

1. Start the backend from `backend`:

   ```powershell
   Copy-Item config\.env.example config\.env
   uv sync --group dev
   uv run python -m alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```

2. In another PowerShell window, define the API address:

   ```powershell
   $baseUrl = "http://localhost:8000"
   ```

3. For a new local database, sign in with the bootstrap administrator:

   ```powershell
   $login = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/login" `
     -ContentType "application/json" `
     -Body (@{
       email = "platform-admin@agency.local"
       password = "Local-Development-Only1!"
     } | ConvertTo-Json)
   ```

   Use the value configured in `AGENCY_BOOTSTRAP_ADMIN_PASSWORD`; the example
   password is for local development only. The first successful login requires
   a password change:

   ```powershell
   $headers = @{ Authorization = "Bearer $($login.data.access_token)" }

   Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/change-password" `
     -Headers $headers -ContentType "application/json" `
     -Body (@{
       current_password = "Local-Development-Only1!"
       new_password = "A-Unique-Local-Password1!"
     } | ConvertTo-Json)
   ```

4. Sign in again using the new password and set `$headers` from the new access
   token. Every administration request below uses this header.

## Example organization

The examples create the following structure:

```text
Permission: firms.read, firms.write, users.read
        │
        ▼
Role: agency.manager
        │
        ▼
User: priya.shah@example.test
        │
        ├── Role: agency.manager
        └── Firms: ACME-MUM (primary), ACME-DEL (active)
```

Platform administrators create firms, platform users, global permissions, and
global assignments. Firm administrators may manage non-platform users, custom
firm roles, and allowed role-permission assignments only inside their active
`X-Firm-ID` context. They cannot view other firms, assign platform roles, alter
firm membership, or change global resources.

## 1. Create permissions

Permissions are stable machine-readable capability codes. Use lower-case codes
with letters, digits, periods, underscores, or hyphens.

```powershell
$firmRead = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/permissions" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    code = "firms.read"
    name = "View firms"
    description = "Allows viewing firm details."
  } | ConvertTo-Json)

$firmWrite = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/permissions" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    code = "firms.write"
    name = "Manage firms"
    description = "Allows creating and updating firms."
  } | ConvertTo-Json)

$userRead = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/permissions" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    code = "users.read"
    name = "View users"
    description = "Allows viewing user details."
  } | ConvertTo-Json)
```

Save their identifiers:

```powershell
$firmReadId = $firmRead.data.id
$firmWriteId = $firmWrite.data.id
$userReadId = $userRead.data.id
```

## 2. Create a role and grant permissions

Create a custom role, then replace its full permission set with `PUT`.

```powershell
$managerRole = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/roles" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    code = "agency.manager"
    name = "Agency Manager"
    description = "Manages assigned firms."
    is_active = $true
  } | ConvertTo-Json)

$managerRoleId = $managerRole.data.id

Invoke-RestMethod -Method Put `
  -Uri "$baseUrl/api/v1/roles/$managerRoleId/permissions" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    ids = @($firmReadId, $firmWriteId, $userReadId)
  } | ConvertTo-Json)
```

`PUT /roles/{id}/permissions` replaces the role's complete permission set. To
add a permission later, first fetch the current set, append the new ID, and
send every retained ID again:

```powershell
$assigned = Invoke-RestMethod -Method Get `
  -Uri "$baseUrl/api/v1/roles/$managerRoleId/permissions" -Headers $headers
```

Use `$assigned.data.ids` together with the ID of the new permission in the
next `PUT` request. System roles are immutable; create a custom role for
application administration.

## 3. Create firms

**Only a platform administrator can create a firm, and no permission code
changes that.** Every route under `/api/v1/firms` is gated by
`require_platform_admin()`, which checks the `platform_admin` claim and that
the token is not flagged `password_change_required` -- it never looks at a
permission. So `FIRM_CREATE` gates only the desktop's **New** button, and no
firm role, `FIRM_ADMIN` included, can create a firm through any client. Either
platform scope works: `require_platform_admin()` does not read
`platform_admins.scope`, and running the platform is precisely what a
`PLATFORM` administrator is for.

In the desktop client this is **Administration -> Firms**, which is the one
Administration tab that needs no firm selected -- so it is reachable from
Platform mode, where a platform administrator always starts.

Firm codes, country codes, and currency codes are normalized to upper case.
`financial_year_start` uses `YYYY-MM-DD`. Only `name`, `code`, `country`,
`currency_code` and `financial_year_start` are required; everything else is
optional.

**Choose `deployment_mode` deliberately -- it is permanent.** See 3a; nothing
migrates a firm's rows between stores afterwards.

```powershell
$mumbaiFirm = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/firms" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    name = "Acme Agencies Mumbai"
    code = "ACME-MUM"
    gst_number = "27ABCDE1234F1Z5"
    pan_number = "ABCDE1234F"
    address_line1 = "10 Marine Drive"
    city = "Mumbai"
    postal_code = "400001"
    country = "IN"
    state = "Maharashtra"
    contact_name = "Priya Shah"
    contact_email = "priya.shah@example.test"
    contact_phone = "+919876543210"
    currency_code = "INR"
    financial_year_start = "2026-04-01"
    is_active = $true
    notes = "Primary operating firm."
  } | ConvertTo-Json)

$delhiFirm = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/firms" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    name = "Acme Agencies Delhi"
    code = "ACME-DEL"
    country = "IN"
    state = "Delhi"
    currency_code = "INR"
    financial_year_start = "2026-04-01"
    is_active = $true
  } | ConvertTo-Json)

$mumbaiFirmId = $mumbaiFirm.data.id
$delhiFirmId = $delhiFirm.data.id
```

### 3a. Firms with their own database or schema

Both firms above use the default `SHARED` mode: their rows live in the platform
database's `firm_shared` schema, and they are usable immediately.

A firm can instead be given its own schema (`SCHEMA`) or its own database
(`DATABASE`), and that database can be on **another server**. The server is named
by `connection_profile`, which must match an entry in
`AGENCY_TENANCY_CONNECTION_PROFILES` — an unrecognized name is refused here
rather than at first use. Omit it to use the platform server.

```powershell
$remoteFirm = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/firms" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    name = "Acme Agencies Pune"
    code = "ACME-PUN"
    country = "IN"
    currency_code = "INR"
    financial_year_start = "2026-04-01"
    deployment_mode = "DATABASE"
    database_type = "postgresql"
    database_name = "acme_pune"
    schema_name = "pune_ops"
    connection_profile = "REMOTE_A"
  } | ConvertTo-Json)
```

Creating the firm **records the routing; it does not build anything**. The firm
cannot serve requests yet — any call carrying its `X-Firm-ID` is refused with a
message saying it has not been provisioned. Build its storage explicitly:

```powershell
Invoke-RestMethod -Method Post -Headers $headers `
  -Uri "$baseUrl/api/v1/firms/$($remoteFirm.data.id)/provision"
```

That creates the database on the profile's server, creates the schema, builds
every firm-owned table, and removes the platform tables from it. The response
carries `provisioned_at`; `already_provisioned` tells you whether this call did
the work or the firm was ready before it.

This is separate from creation on purpose: a target server that is slow or
unreachable must not fail the creation of the firm record. If provisioning
fails, the reason is kept on the firm and the same call is the retry — every
step is create-if-missing, so running it again is safe.

In the desktop client this is the **Provision storage** action on the Firms
workspace, and the Storage column reads `Not provisioned` until it succeeds.

Routing is fixed once the firm exists: nothing migrates a firm's rows between
stores, so `PUT /api/v1/firms/{id}` rejects any change to `deployment_mode`,
`database_name`, `schema_name` or `connection_profile`.

> After any schema change, upgrade **every** store, not just the platform one:
> `uv run python scripts/migrate_all_stores.py --dry-run` then `--yes`.

### 3b. Making the firm ready to trade

A provisioned firm has tables. It cannot trade yet, and the remaining steps
were easy to miss because nothing failed until somebody tried to approve
something. **Select the firm on Administration → Firms and press Set up**:
the panel lists every step -- storage, business profile, books, tax,
geography, branches and warehouses, people -- as done or missing, marks the
two the platform refuses to post without as *Required*, and does two of them
in place. **Provision storage** is the same action as the toolbar button.
**Open the books** gives the firm the default chart of accounts, the
financial year running now with twelve periods, the journal and voucher
types and all 24 control-account mappings, in one press, idempotently; it is
`POST /api/v1/firms/{id}/open-books` and is audited as `firm.books_opened`.
**Apply GST template** gives the firm the whole Indian GST setup -- system,
components, the slabs as local and interstate profiles, the rules, and the
country if the store has none -- and the **Business profile** row carries the
firm's own catalogue with an **Assign** button, and **Create head office and
main warehouse** gives the firm `HO` and `MAIN` to rename later. The People
row names the screen it is done on. The same list is
`GET /api/v1/firms/{id}/readiness` and `scripts/check_firm_readiness.py`.

**Switch into the firm.** Setting a firm up finishes *inside* it: the business
profile, the financial year and the chart of accounts live in the firm's own
store and need `X-Firm-ID`. In the desktop client, **Open this firm** on the
Firms workspace refreshes the switcher and switches you in -- necessary
because `session.firms` is read once at sign-in, so a firm created minutes ago
is in no switcher and `switchFirm` would reject it as "not assigned to this
user". The action is disabled for a retired firm and for a dedicated firm that
has not been provisioned, since switching into an empty store answers errors
on every screen.

**Set the business profile**, in **Administration -> Business Profiles ->
Profile Assignment** -- and note that this is *not* done from inside the firm.
The screen names the firm in the URL rather than reading `X-Firm-ID`, so it
lists every firm and a platform administrator sets any of them from platform
mode. It is platform-only twice over: the tab wants `FIRM_VIEW` or
`PLATFORM_VIEW`, neither of which a firm role may hold, and
`assign_profile_to_firm` takes the designation, so a firm administrator cannot
do this even with the tab in front of them.

A firm with no assignment resolves to the platform default (GENERIC), so a
wholesaler runs without the features and modules its profile would enable.
Nothing refuses a document over this; it simply behaves like a different kind
of business.

> **Select a firm first.** Every tab under Business Profiles needs one, this
> one included, so in platform mode the group is not offered at all. Open any
> existing firm and the tab appears; the grid still lists *every* firm, so a
> brand-new firm's profile is set from inside an established one.
>
> The reason is not the permission -- it is where the data lives. The grid and
> the record both answer 200 with no firm, but the edit dialog's profile
> dropdown reads `/business-framework/profiles`, and the profile *catalogue*
> lives in each firm's own store. With no firm the session falls back to the
> platform schema, where PostgreSQL answers `relation
> "platform.business_profiles" does not exist` and the user sees "The database
> is temporarily unavailable". Making the tab firm-free was tried on
> 2026-09-06 and reverted the same day for exactly that: the grid rendered and
> the dialog could not be filled in. Moving it needs the dropdown to read the
> catalogue of the firm being edited, which `FieldSpec.optionsResource` cannot
> express today.

**Open the books.** Documents post through `DocumentPostingService`, which
**refuses rather than guesses**, so before anything can be approved the firm
needs a chart of accounts, a financial year, open accounting periods, journal
and voucher types, and a mapped control account for each of the 24 posting
purposes.

> **There is no screen or endpoint for the control-account mapping.** No path
> in the served OpenAPI document contains `control`, and no desktop file
> references one. The only code that builds this is `seed_finance_setup` in
> `app/finance/services/opening_setup.py`, whose only callers are
> `scripts/generate_sample_data.py` and `scripts/generate_transaction_history.py`.

So a firm created purely through the UI will accept masters and let documents
be drafted, and then **refuse every posting action** -- approving an invoice,
completing a goods receipt. That refusal is the design working, not a fault in
the new firm. The chart itself *can* be built by hand (`POST` exists for
account groups, ledger accounts, financial years, periods, journal types and
voucher types); the mapping cannot, so posting stays blocked either way until
one of the two scripts is run against that store.

**Check where a firm stands** with the read-only report, from `backend`:

```powershell
./.venv/Scripts/python.exe scripts/check_firm_readiness.py ACME-MUM
./.venv/Scripts/python.exe scripts/check_firm_readiness.py   # every firm
```

It prints the deployment mode, whether storage is provisioned, the business
profile, the counts of accounts, years and periods, how many control purposes
are unmapped, and a verdict of `can post documents` or `CANNOT post -- books
not open`. It writes nothing, resolves a SHARED firm to the configured shared
store rather than to the NULLs on its mapping, and exits non-zero if any firm
it reported is not ready.

## 4. Create a user

Administrators set an initial password. `force_password_change = true` makes
the user change it after their first sign-in. `expires_at` is optional and uses
an ISO 8601 timestamp.

```powershell
$user = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/users" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    email = "priya.shah@example.test"
    full_name = "Priya Shah"
    password = "Initial-User-Password1!"
    is_active = $true
    force_password_change = $true
    expires_at = $null
  } | ConvertTo-Json)

$userId = $user.data.id
```

Passwords must satisfy the backend password policy. Use `PATCH /users/{id}` to
change the user's name, active state, expiry, or unlock a locked account:

```powershell
Invoke-RestMethod -Method Patch -Uri "$baseUrl/api/v1/users/$userId" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    full_name = "Priya R. Shah"
    unlock = $true
  } | ConvertTo-Json)
```

## 5. Assign the user to roles

Use the complete desired role set. This request is safe to repeat.

```powershell
Invoke-RestMethod -Method Put -Uri "$baseUrl/api/v1/users/$userId/roles" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    ids = @($managerRoleId)
  } | ConvertTo-Json)
```

Check the assignment:

```powershell
Invoke-RestMethod -Method Get -Uri "$baseUrl/api/v1/users/$userId/roles" `
  -Headers $headers
```

## 6. Map the user to firms

Use the complete desired firm membership list. A user may belong to many
firms, but at most one active firm can be primary. The example maps Priya to
Mumbai as primary and Delhi as another active firm.

```powershell
Invoke-RestMethod -Method Put -Uri "$baseUrl/api/v1/users/$userId/firms" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    assignments = @(
      @{
        firm_id = $mumbaiFirmId
        is_primary = $true
        is_active = $true
      },
      @{
        firm_id = $delhiFirmId
        is_primary = $false
        is_active = $true
      }
    )
  } | ConvertTo-Json -Depth 4)
```

To move the primary firm from Mumbai to Delhi, submit both memberships again
with Delhi as primary:

```powershell
Invoke-RestMethod -Method Put -Uri "$baseUrl/api/v1/users/$userId/firms" `
  -Headers $headers -ContentType "application/json" `
  -Body (@{
    assignments = @(
      @{ firm_id = $mumbaiFirmId; is_primary = $false; is_active = $true },
      @{ firm_id = $delhiFirmId; is_primary = $true; is_active = $true }
    )
  } | ConvertTo-Json -Depth 4)
```

Verify memberships:

```powershell
Invoke-RestMethod -Method Get -Uri "$baseUrl/api/v1/users/$userId/firms" `
  -Headers $headers
```

## 7. Test the new user's login

```powershell
Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{
    email = "priya.shah@example.test"
    password = "Initial-User-Password1!"
  } | ConvertTo-Json)
```

The first response has `data.must_change_password = true`. The user must call
`POST /api/v1/auth/change-password` with their bearer access token before
continuing. Global permissions and firm-scoped permissions are issued separately. The
selected `X-Firm-ID` determines which firm grant applies, and authorization
changes immediately invalidate existing access and refresh sessions.

## Troubleshooting

| Response | Cause | Action |
| --- | --- | --- |
| `401` | Missing, expired, invalid, or authorization-version-stale access token. | Sign in again or refresh the token. |
| `403` | Caller lacks platform authority, an active selected-firm membership, or the required scoped permission. | Use the correct administrator, send `X-Firm-ID` for firm administration, and verify assignments. |
| `409` | Duplicate email, role code, permission code, or firm code. | Use a unique value or update the existing resource. |
| `422` | Invalid request field or more than one active primary firm. | Inspect `error.details`, then correct and resend the complete assignment set. |

For the complete endpoint schema, open `http://localhost:8000/docs`. For
application startup and database troubleshooting, see
[`backend/README.md`](../backend/README.md).
