# Security Architecture

## Administrative boundaries

Platform administration is an immutable security boundary. A platform
administrator is designated by the `platform_admins` table, not by a
client-editable role name. Only that principal can use global firm, user, role,
permission, configuration, licensing, audit, and reporting administration
APIs.

Firm administrators are operational tenant users. Their system role excludes
platform settings, firm lifecycle, licensing, global audit, destructive system
operations, and every other platform permission. Firm permissions are emitted
under a firm identifier and are evaluated against the `X-Firm-ID` context. A
firm role cannot create or assign a platform administrator designation.

## Role hierarchy and permission model

Authorization is deny-by-default:

1. Authentication validates the JWT signature, token type, expiry, active user
   state, account expiry, deletion state, and authorization version.
2. Platform endpoints require the immutable platform-administrator
   designation.
3. Firm endpoints require active firm membership and a permission grant for
   the selected firm.
4. Services validate ownership, and repositories include the firm predicate in
   object and collection queries.

Role, permission, membership, account-status, expiry, and password changes
increment the user's authorization version and revoke refresh tokens. Existing
access tokens therefore stop authorizing immediately.

## Tenant isolation

Every firm-owned request requires `X-Firm-ID`, including requests made by a
platform administrator. Firm membership and the firm must be active and not
deleted. Customer IDs are always resolved with the authorized firm predicate,
so an ID from another firm cannot be used for reads, writes, exports, restores,
or nested-record access.

New firm-owned entities must use a non-null `firm_id`, composite tenant indexes
and uniqueness constraints, repository firm filters, service ownership
validation, and API permission dependencies.

## Audit and lifecycle strategy

Audit events contain actor, firm where applicable, timestamp, action, entity
type and ID, before/after values, client IP when available, and an optional
application version. They are insert-only. SQLAlchemy rejects mutation and
deletion, while PostgreSQL enforces the same rule with a trigger.

Persisted business and security entities use UUID identifiers and common
created, updated, deleted, actor, and optimistic-version fields. Deletion is
logical and records `deleted_at` plus `deleted_by`; restoration clears both.
Customer child reconciliation uses soft deletion rather than orphan deletion,
and foreign keys restrict physical cascade deletion.

## Security assumptions

- TLS terminates before any non-loopback API connection. The desktop rejects
  remote HTTP URLs and refuses redirects for authenticated requests.
- JWT, database, bootstrap, and other secrets are injected at deployment.
  Known development defaults are rejected in staging and production.
- The runtime database principal has only required DML rights. Migration
  credentials are separate in production.
- UI visibility is permission-driven, but is never an authorization control.
- Logs contain request metadata, never request bodies, passwords, tokens, or
  sensitive customer fields.

## Future extensibility

Future modules must use firm-scoped role grants, repository scoping, bounded
pagination, whitelisted sorting, common response/error contracts, append-only
audit events, and soft-delete lifecycle fields. Cross-firm reporting or support
access must be an explicit platform capability, never a weakened tenant filter.
