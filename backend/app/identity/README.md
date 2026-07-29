# Identity and Platform Administration

This module owns credentials, JWT sessions, users, dynamic RBAC, user-role
assignments, and user-firm assignments. It does not implement ERP business
modules.

## Authentication endpoints

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `POST /api/v1/auth/login` | Public | Validates credentials, records the attempt, and returns access/refresh tokens. |
| `POST /api/v1/auth/refresh` | Public | Atomically rotates a single-use refresh token. |
| `POST /api/v1/auth/logout` | Public | Revokes the submitted refresh token. |
| `POST /api/v1/auth/change-password` | Bearer token | Changes the current password and revokes all refresh sessions. |

Failed authentication attempts are recorded. Accounts lock after
`AGENCY_SECURITY_MAX_LOGIN_ATTEMPTS` failures for
`AGENCY_SECURITY_LOCKOUT_MINUTES`. Passwords use Argon2 and cannot match the
most recent `AGENCY_SECURITY_PASSWORD_HISTORY_COUNT` values.

## Administration endpoints

All routes below require a platform-administrator bearer token.

| Resource | CRUD | Assignment routes |
| --- | --- | --- |
| Users | `GET/POST /api/v1/users`, `GET/PATCH/DELETE /api/v1/users/{id}` | `GET/PUT /api/v1/users/{id}/roles`, `GET/PUT /api/v1/users/{id}/firms` |
| Roles | `GET/POST /api/v1/roles`, `GET/PATCH/DELETE /api/v1/roles/{id}` | `GET/PUT /api/v1/roles/{id}/permissions` |
| Permissions | `GET/POST /api/v1/permissions`, `GET/PATCH/DELETE /api/v1/permissions/{id}` | None |

Assignment `PUT` calls replace the full assignment set. A user can have
multiple active firms, but only one active primary firm. Roles created through
the API are custom; system roles cannot be modified or deleted.

List routes accept `page`, `page_size`, `search`, `sort_by`, and
`sort_direction`. Allowed sort fields are defined by each endpoint's OpenAPI
schema.

## Implementation map

| Path | Responsibility |
| --- | --- |
| `models/identity.py` | Users, roles, permissions, token, login-history, and assignment ORM models. |
| `schemas/api.py` | HTTP request/response validation contracts. |
| `services/identity_service.py` | Authentication, lockout, password, RBAC, user, and assignment use cases. |
| `api/router.py` | FastAPI adapters registered under `/api/v1`. |
| `repositories/identity_repository.py` | Shared query helpers for identity persistence. |

Audit events for administration mutations are stored by `app.common.audit`.
For startup, bootstrap, and environment configuration, use the backend
[`README.md`](../../README.md).
