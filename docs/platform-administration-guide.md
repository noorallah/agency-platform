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

Only platform administrators can create or change users, roles, permissions,
firms, and assignments. Roles and permissions then authorize future protected
ERP APIs.

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

Firm codes, country codes, and currency codes are normalized to upper case.
`financial_year_start` uses `YYYY-MM-DD`.

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
continuing. Their permissions are inherited from all assigned active roles;
firm mappings identify the firms available to future firm-scoped APIs.

## Troubleshooting

| Response | Cause | Action |
| --- | --- | --- |
| `401` | Missing, expired, or invalid access token. | Sign in again or refresh the token. |
| `403` | Caller is not a platform administrator. | Use the bootstrap administrator or grant the required administration access. |
| `409` | Duplicate email, role code, permission code, or firm code. | Use a unique value or update the existing resource. |
| `422` | Invalid request field or more than one active primary firm. | Inspect `error.details`, then correct and resend the complete assignment set. |

For the complete endpoint schema, open `http://localhost:8000/docs`. For
application startup and database troubleshooting, see
[`backend/README.md`](../backend/README.md).
