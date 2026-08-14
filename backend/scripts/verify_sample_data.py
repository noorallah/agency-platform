"""Check that the seeded data holds together, in every firm store.

The previous version of this script counted rows in one schema for one firm and
had not run since multi-tenancy: it failed at import on a model dropped in
`20260812_0068`, and repairing that only moved the failure to `relation
"platform.uoms" does not exist`, because it read platform and firm-owned tables
as though they shared a schema.

This checks the things that were actually found broken while building the
demo -- each one is a defect that shipped, not a hypothetical:

* **Stock value against the inventory control account.** Purchase returns,
  adjustments and opening stock all moved stock without posting at some point,
  and the gap was invisible until the two were compared.
* **Every accounting period balances.** The trial balance omitted accounts that
  had not moved in a period, so a sound ledger reported itself out of balance.
* **Customer outstanding against the receivable control account.** The
  receivable endpoint moved a customer balance without writing a journal, which
  drove these apart silently.
* **Every settlement carries a journal.** A settlement that never reached the
  ledger is the state the module exists to prevent.
* **Every approved invoice posted.** Posting is meant to fail the approval
  rather than be skipped, so an approved invoice with no journal means it was.

It reports every store rather than stopping at the first failure, and exits
non-zero if any check failed -- the same shape as `migrate_all_stores.py`,
which is also where the store list comes from, so a firm on another server is
checked on that server.

    uv run python scripts/verify_sample_data.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.config.settings import Settings  # noqa: E402
from app.core.database.engine import DatabaseManager  # noqa: E402
from app.core.tenancy import DeploymentMode  # noqa: E402
from app.core.tenancy.connections import (  # noqa: E402
    build_tenant_database_config,
    resolve_connection_profile,
)
from app.firms.models import Firm, FirmStorageMapping  # noqa: E402

#: How far apart the stock valuation and the ledger may be before it is a
#: defect rather than arithmetic. The valuation holds four decimals and the
#: ledger two, so a store with a few hundred products is legitimately out by a
#: fraction of a rupee; anything approaching one is a missing posting.
ROUNDING_TOLERANCE = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class _Store:
    """One database and schema pair holding a firm's data."""

    label: str
    database_url: str
    schema_name: str


@dataclass
class _Result:
    """What one store was found to be."""

    label: str
    checked: int = 0
    failures: list[str] = field(default_factory=list)
    skipped: str | None = None


def _stores(platform: DatabaseManager, settings: Settings) -> list[_Store]:
    """Return every distinct firm store, the way the migrator enumerates them."""
    base = platform.config
    platform_schema = base.default_schema or "platform"
    stores: dict[tuple[str, str], _Store] = {}

    def add(label: str, database_url: str, schema_name: str) -> None:
        url = make_url(database_url)
        stores.setdefault(
            (f"{url.host}:{url.port}/{url.database}", schema_name),
            _Store(label=label, database_url=database_url, schema_name=schema_name),
        )

    shared_database = settings.tenancy.shared_database_name or base.database
    add(
        f"shared ({shared_database}/{settings.tenancy.shared_schema_name})",
        make_url(base.url)
        .set(database=shared_database)
        .render_as_string(hide_password=False),
        settings.tenancy.shared_schema_name,
    )
    with platform.sessions(schema=platform_schema).session() as session:
        rows = session.execute(
            select(Firm, FirmStorageMapping)
            .join(FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id)
            .where(
                Firm.is_deleted.is_(False),
                FirmStorageMapping.is_deleted.is_(False),
                FirmStorageMapping.is_active.is_(True),
            )
        ).all()
        for firm, mapping in rows:
            if DeploymentMode(mapping.deployment_mode) is DeploymentMode.SHARED:
                continue
            if mapping.database_name is None or mapping.schema_name is None:
                continue
            config = build_tenant_database_config(
                base,
                database_name=mapping.database_name,
                schema_name=mapping.schema_name,
                database_type=mapping.database_type,
                profile=resolve_connection_profile(
                    settings.tenancy.connection_profiles, mapping.connection_profile
                ),
            )
            add(
                f"{firm.code} ({mapping.database_name}/{mapping.schema_name})",
                config.url,
                mapping.schema_name,
            )
    return list(stores.values())


def _check_store(store: _Store) -> _Result:
    """Run every check against one store."""
    from sqlalchemy import create_engine

    result = _Result(label=store.label)
    engine = create_engine(store.database_url)
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{store.schema_name}"'))
        if not connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'inventories'"
            ),
            {"schema": store.schema_name},
        ).scalar():
            result.skipped = "no firm-owned tables in this store"
            return result

        _stock_against_the_ledger(connection, result)
        _every_period_balances(connection, result)
        _customers_against_the_ledger(connection, result)
        _settlements_reached_the_ledger(connection, result)
        _approved_invoices_posted(connection, result)
    engine.dispose()
    return result


def _control_balance(connection: object, purpose: str) -> Decimal | None:
    """Return what the firm's account for one purpose currently holds."""
    row = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT COALESCE(SUM(p.debit_amount - p.credit_amount), 0) "
            "FROM gl_postings p "
            "JOIN firm_control_accounts c "
            "  ON c.ledger_account_id = p.ledger_account_id "
            " AND c.is_deleted = false AND c.purpose = :purpose "
            "WHERE p.is_deleted = false"
        ),
        {"purpose": purpose},
    ).scalar()
    return None if row is None else Decimal(str(row))


def _stock_against_the_ledger(connection: object, result: _Result) -> None:
    """Stock value and the inventory control account must agree."""
    result.checked += 1
    stock = Decimal(
        str(
            connection.execute(  # type: ignore[attr-defined]
                text(
                    "SELECT COALESCE(SUM(total_value), 0) FROM product_valuations "
                    "WHERE is_deleted = false"
                )
            ).scalar()
        )
    )
    ledger = _control_balance(connection, "INVENTORY")
    if ledger is None:
        return
    drift = stock - ledger
    if abs(drift) > ROUNDING_TOLERANCE:
        result.failures.append(
            f"stock value {stock} against inventory account {ledger}, "
            f"out by {drift} -- a movement changed stock without posting"
        )


def _every_period_balances(connection: object, result: _Result) -> None:
    """Debits and credits must agree in every period the firm has traded."""
    result.checked += 1
    rows = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT p.id, p.name, COALESCE(SUM(g.debit_amount), 0), "
            "       COALESCE(SUM(g.credit_amount), 0) "
            "FROM accounting_periods p "
            "LEFT JOIN gl_postings g ON g.accounting_period_id = p.id "
            " AND g.is_deleted = false "
            "WHERE p.is_deleted = false "
            "GROUP BY p.id, p.name"
        )
    ).all()
    for _, name, debit, credit in rows:
        if Decimal(str(debit)) != Decimal(str(credit)):
            result.failures.append(
                f"{name} posts {debit} of debits against {credit} of credits"
            )


def _customers_against_the_ledger(connection: object, result: _Result) -> None:
    """Compare what customers owe against the receivable control account."""
    result.checked += 1
    owed = Decimal(
        str(
            connection.execute(  # type: ignore[attr-defined]
                text(
                    "SELECT COALESCE(SUM(current_outstanding), 0) FROM customers "
                    "WHERE is_deleted = false"
                )
            ).scalar()
        )
    )
    ledger = _control_balance(connection, "ACCOUNTS_RECEIVABLE")
    if ledger is None:
        return
    drift = owed - ledger
    if abs(drift) > ROUNDING_TOLERANCE:
        result.failures.append(
            f"customers owe {owed} against receivable account {ledger}, "
            f"out by {drift} -- a balance moved without a journal"
        )


def _settlements_reached_the_ledger(connection: object, result: _Result) -> None:
    """Every settlement must carry the journal it wrote."""
    result.checked += 1
    if not connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'settlements'"
        )
    ).scalar():
        return
    orphans = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT COUNT(*) FROM settlements s "
            "LEFT JOIN journal_entries j ON j.id = s.journal_entry_id "
            "WHERE s.is_deleted = false AND j.id IS NULL"
        )
    ).scalar()
    if orphans:
        result.failures.append(
            f"{orphans} settlement(s) name a journal that does not exist"
        )


def _approved_invoices_posted(connection: object, result: _Result) -> None:
    """Find approved invoices that wrote no journal, meaning posting was skipped."""
    result.checked += 1
    for table, module in (
        ("sales_invoices", "sales_invoice"),
        ("purchase_invoices", "purchase_invoice"),
    ):
        unposted = connection.execute(  # type: ignore[attr-defined]
            text(
                f"SELECT COUNT(*) FROM {table} i "  # noqa: S608 - fixed names
                "WHERE i.is_deleted = false "
                "  AND i.status IN ('APPROVED', 'COMPLETED', 'CLOSED') "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM journal_entries j "
                "    WHERE j.source_id = i.id AND j.source_module = :module "
                "      AND j.is_deleted = false)"
            ),
            {"module": module},
        ).scalar()
        if unposted:
            result.failures.append(
                f"{unposted} approved {table.replace('_', ' ')} wrote no journal"
            )


def main() -> int:
    """Check every store and report what was found."""
    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    stores = _stores(platform, settings)
    print(f"{len(stores)} store(s) to check.\n")

    failed = 0
    for store in stores:
        result = _check_store(store)
        if result.skipped is not None:
            print(f"  {result.label}: skipped -- {result.skipped}")
            continue
        if result.failures:
            failed += 1
            print(f"  {result.label}: {len(result.failures)} problem(s)")
            for failure in result.failures:
                print(f"      {failure}")
        else:
            print(f"  {result.label}: {result.checked} check(s) passed")

    print()
    if failed:
        print(f"{failed} of {len(stores)} store(s) have problems.")
        return 1
    print("Every store holds together.")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
