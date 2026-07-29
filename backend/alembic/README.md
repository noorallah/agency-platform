# Alembic migrations

Alembic owns the backend database schema. The current migration head is
`20260728_0005`.

Run these commands from `backend`:

```powershell
uv run python -m alembic current
uv run python -m alembic heads
uv run python -m alembic upgrade head
```

The Phase 5 migrations create identity, RBAC, firms, user-firm assignments,
audit logs, and PostgreSQL's active-primary-firm constraint.

`20260728_0004_ensure_phase5_identity_schema` inspects a live database to
repair installations created from an incomplete early Phase 5 revision. It
cannot run in offline SQL mode by design. This command intentionally fails at
that revision:

```powershell
uv run python -m alembic upgrade head --sql
```

To inspect bootstrap DDL before the live reconciliation migration, use:

```powershell
uv run python -m alembic upgrade 20260728_0003 --sql
```

Use `alembic downgrade base` only for a disposable local database; it removes
all application tables.
