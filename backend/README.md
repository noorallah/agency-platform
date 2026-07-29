# Agency Platform Backend

The Agency Platform backend is a FastAPI administration platform. It provides
the reusable core framework plus the first vertical slice: authentication,
platform users, dynamic roles and permissions, firms, assignments, audit logs,
and the administration dashboard. ERP modules are intentionally not present.

## Quick start

Prerequisites: Python 3.13+, [uv](https://docs.astral.sh/uv/), and PostgreSQL
17. MySQL remains supported by the connection layer, but PostgreSQL is the
primary development target.

From `backend`:

```powershell
Copy-Item config\.env.example config\.env
uv sync --group dev
uv run python -m alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the interactive API. Use
`GET /health` to confirm the application and `GET /health/database` to confirm
database connectivity.

The development bootstrap administrator is:

| Field | Value |
| --- | --- |
| Email | `platform-admin@agency.local` |
| Initial password | `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` from `config/.env` |

On its first successful development login, the bootstrap secret becomes an
Argon2 hash and the account is required to change its password. Never use the
example bootstrap password or JWT signing key outside local development.

## API surface

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness status and configured environment |
| `GET /health/database` | Database connectivity check |
| `POST /api/v1/auth/login` | Login and receive access/refresh JWTs |
| `POST /api/v1/auth/refresh` | Rotate a persisted refresh token |
| `POST /api/v1/auth/logout` | Revoke a refresh token |
| `POST /api/v1/auth/change-password` | Change password and revoke sessions |
| `GET/PATCH /api/v1/me/preferences` | Authenticated user's versioned desktop preferences |
| `POST /api/v1/me/preferences/reset` | Restore the authenticated user's preference defaults |
| `GET /api/v1/dashboard` | Protected platform administration summary |
| `/api/v1/users` | Protected user CRUD and role/firm assignment |
| `/api/v1/roles` | Protected custom/system role CRUD and permission assignment |
| `/api/v1/permissions` | Protected permission CRUD |
| `/api/v1/firms` | Protected firm CRUD |
| `/docs` | Swagger UI |
| `/openapi.json` | OpenAPI document |

All administration routes require a bearer access token for the platform
administrator, except `/api/v1/me/preferences`, which every authenticated user
may manage for themselves. Login and refresh endpoints are public. Responses use
the standard envelope:

```json
{
  "success": true,
  "data": {},
  "message": null,
  "timestamp": "2026-07-28T00:00:00Z",
  "requestId": "..."
}
```

Collection responses additionally include
`pagination.page`, `pagination.page_size`, `pagination.total_records`, and
`pagination.total_pages`. Send the response `X-Request-ID` to support a log
search when reporting an issue.

## Startup flow

```mermaid
flowchart TD
    A[Copy config/.env.example to config/.env] --> B[uv sync --group dev]
    B --> C[uv run python -m alembic upgrade head]
    C --> D[uv run uvicorn app.main:app --reload]
    D --> E[Settings loads AGENCY_ variables]
    E --> F[DatabaseManager creates SQLAlchemy engine and sessions]
    F --> G[FastAPI starts health routes]
```

At startup, `app.main:create_app` loads `Settings`, configures logging, creates
a `DatabaseManager`, registers middleware and health routes, and serves the
FastAPI application. The API does not connect to the database until a route
such as `/health/database` requests a session.

## Settings

Settings are loaded by `app.core.config.Settings` from `config/.env` and
environment variables prefixed with `AGENCY_`. Environment variables override
the values in `config/.env`; do not commit that file.

| Group | Settings | Notes |
| --- | --- | --- |
| Application | `APP_NAME`, `APP_VERSION`, `ENVIRONMENT`, `DEBUG` | Environments: `development`, `testing`, `staging`, `production` |
| Logging | `LOG_LEVEL`, `LOG_DIRECTORY`, `LOG_FILE_NAME`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`, `LOG_FILE_ENABLED` | Console and optionally rotating-file logging |
| Database | `DATABASE_DIALECT`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` | Supported dialects: `postgresql` and `mysql` |
| Database pool | `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_RECYCLE_SECONDS`, `DATABASE_SCHEMA` | Optional connection-pool and default-schema controls |
| Database URL | `DATABASE_URL` | Overrides individual database fields; its dialect must match `DATABASE_DIALECT` |
| Security | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_MINUTES`, `JWT_REFRESH_TOKEN_DAYS`, `SECURITY_MAX_LOGIN_ATTEMPTS`, `SECURITY_LOCKOUT_MINUTES`, `SECURITY_PASSWORD_HISTORY_COUNT`, `BOOTSTRAP_ADMIN_PASSWORD` | JWT, login lockout, password history, and bootstrap policy |
| Licensing | `LICENSE_ENABLED`, `LICENSE_VALIDATION_URL` | Reserved configuration for a future licensing module |

For example, `AGENCY_DATABASE_DIALECT=postgresql` and
`AGENCY_DATABASE_HOST=localhost` configure PostgreSQL. When using
`AGENCY_DATABASE_URL`, set both values consistently:

```text
AGENCY_DATABASE_DIALECT=postgresql
AGENCY_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agency_platform
```

## Identity Domain and migrations

The Alembic revisions create UUID-backed identity tables plus:
`firms`, `user_firms`, and `audit_logs`. Roles carry an immutable system/custom
classification and users can have an optional expiry timestamp.

The initial identity migration creates these tables:
`users`, `platform_admins`, `roles`, `permissions`, `user_roles`,
`role_permissions`, `password_history`, `refresh_tokens`, and
`login_history`. SQLAlchemy models, schemas, and repositories are under
`app/identity`.

All shared entities include UUID and audit fields, soft-deletion state, and a
version field for future optimistic concurrency handling.

The migrations seed `platform-admin@agency.local` and its `PlatformAdmin`
designation with a non-usable `*` hash, plus the initial system RBAC roles,
permissions, and role-permission mappings. System roles and permissions are
protected from modification or deletion; custom roles and permissions remain
administrator-managed. The reserved `SUPPORT_ADMIN` role is not returned by
role-list endpoints. On the first local-development login,
the explicit `AGENCY_BOOTSTRAP_ADMIN_PASSWORD` is exchanged for an Argon2 hash
and the user is forced to change it. Development defaults to
`Local-Development-Only1!` only when no environment value is supplied; staging
and production refuse to start without an explicit bootstrap secret. Store the
production value in a secret manager and rotate it after bootstrap.

`AGENCY_JWT_SECRET_KEY` has a local-development default. Staging and production
reject that known value at startup; configure a unique high-entropy signing key
explicitly through the deployment secret store.

All `/api/v1/users`, `/api/v1/roles`, `/api/v1/permissions`, and `/api/v1/firms`
endpoints require a platform-admin access token. List endpoints use only
whitelisted `page`, `page_size`, `search`, `sort_by`, and `sort_direction`
query parameters. Every mutation emits an `audit_logs` record.

Every authenticated user can manage a versioned preference document through
`GET /api/v1/me/preferences`, `PATCH /api/v1/me/preferences`, and
`POST /api/v1/me/preferences/reset`. The document stores display, formatting,
firm, landing-page, paging, notification, and dashboard-layout preferences.

Firm membership replacement locks the owning user and its membership rows.
PostgreSQL 17 additionally enforces at most one active primary firm through
the partial unique index `UQ_user_firms_active_primary`. MySQL applies the
service-level locks but does not create that PostgreSQL-specific partial index.
Revision `20260728_0004` performs live schema inspection and must be run
online; `alembic upgrade head --sql` intentionally stops at that revision
instead of falsely marking a database reconciled. Inspect initial DDL with
`uv run python -m alembic upgrade 20260728_0003 --sql`.

Apply all migrations:

```powershell
uv run python -m alembic upgrade head
```

Check the applied revision and current migration head:

```powershell
uv run python -m alembic current
uv run python -m alembic heads
```

Roll back all migrations only in a disposable local database:

```powershell
uv run python -m alembic downgrade base
```

> Revision `20260728_0004` inspects the live schema to repair early Phase 5
> installations. It must run against a database. Therefore,
> `alembic upgrade head --sql` intentionally stops at that revision. Generate
> the pre-reconciliation bootstrap SQL with
> `uv run python -m alembic upgrade 20260728_0003 --sql`.

## Administration workflow

1. Sign in as the bootstrap platform administrator and change its initial
   password.
2. Create permissions, then custom roles, and assign permissions to roles.
3. Create firms with their currency and financial-year start.
4. Create users and assign their roles and one or more firms.
5. Choose at most one active primary firm for each user.

Assignments replace the submitted set. Re-sending the same set is safe.
Every create, update, delete, and assignment mutation produces an
`audit_logs` record.

For copyable PowerShell examples that create permissions, roles, firms, users,
and mappings, see the
[`Platform administration guide`](../docs/platform-administration-guide.md).

## Debugging and troubleshooting

| Symptom | Investigation and resolution |
| --- | --- |
| API does not start | Confirm `config\.env` exists, then run `uv sync --group dev` and use `uv run uvicorn app.main:app --reload`. |
| `/health/database` fails | Verify `AGENCY_DATABASE_*` values, PostgreSQL is running, and the database exists. The API starts without opening a database connection, so this endpoint is the connectivity check. |
| Alembic reports a missing database or fails to connect | Correct the same database settings, then rerun `uv run python -m alembic upgrade head`. |
| `uv run pytest`, `mypy`, or `black` reports `uv trampoline failed to canonicalize script path` on Windows | This is a Windows `uv` launcher issue, not a project failure. Run the equivalent command through the project environment, for example `.\.venv\Scripts\python.exe -m pytest -q`. |
| Request fails with `401` | Sign in again or refresh the session. Access tokens are short lived and the client retries a refresh once. |
| Request fails with `403` | The authenticated account is not the platform administrator or lacks the required permission. Check role and permission assignments. |
| Request fails with `422` | Inspect the `error.details` response field and the OpenAPI schema at `/docs`. |
| Need to correlate a client error with logs | Use the `X-Request-ID` response header. Logs are written to `AGENCY_LOG_DIRECTORY\AGENCY_LOG_FILE_NAME` when file logging is enabled. |

## Validation

Run these commands from `backend`:

```powershell
uv run ruff check .
uv run black --check .
uv run mypy app
uv run pytest -q
uv run python -m alembic heads
```

## Docker Compose

```powershell
Copy-Item config\.env.example config\.env
docker compose up --build
```

Compose starts PostgreSQL, waits for it to be healthy, applies Alembic
migrations, and starts Uvicorn on `http://localhost:8000`. Stop the stack with:

```powershell
docker compose down
```
