# Alembic migrations

Alembic owns the backend database schema. The current migration head is
`20260802_0021`.

Run these commands from `backend`:

```powershell
uv run python -m alembic current
uv run python -m alembic heads
uv run python -m alembic upgrade head
```

Implemented migrations now include:

1. Identity, RBAC, firms, assignments, audit logs, and preferences
2. Business profile and dynamic-attribute framework
3. Product master enterprise extensions
4. Territory/route foundation and extensions
5. Vendor and branch/warehouse enterprise modules
6. Tax framework and tax rule engine foundation
7. Inventory foundation, opening stock, transactions, and ledger
8. Batch/lot/serial/expiry framework
9. UOM and packaging framework

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
