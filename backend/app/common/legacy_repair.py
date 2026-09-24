"""Repair rows that were written before the rule that now forbids them.

Each fix below closed a door; none of them walked back through it to tidy
what had already come in. The owner's decision of 2026-09-24 (decided by
Claude, industry standard) is to repair that legacy data once, by script,
rather than leave it for a screen to trip over:

* **A debtor cannot be deleted.** A soft-deleted customer still carrying a
  balance is restored -- the delete guard refuses the same thing today, and a
  balance nobody can see is one nobody collects.
* **A product that holds stock cannot be deleted.** A soft-deleted product
  still holding a quantity in any bucket (``find_stock_holdings``, the product
  delete guard's own question) is restored, or the stock is on the books
  under a product no screen lists.
* **A master reference names the record's own firm (D-MST-3).** In the shared
  store, a customer, vendor or product pointing at another firm's segment,
  category or type has that reference set to NULL -- a reference to another
  tenant's master is invalid data, and NULL is how the services read "none".
  A master with no firm column (a business profile) is shared by every firm
  in the store, so nothing about it is foreign.
* **Goodwill points are a liability from the day they are granted
  (D-SELL-19, IFRS 15).** Points given by hand before #477 were never
  accrued. The value of what is still held of them, at the scheme's value
  per point, is booked as one true-up per firm, ``Dr 5700 Loyalty Expense /
  Cr 2600 Loyalty Payable``, dated today -- a correction is booked in the
  current period -- under the reference ``LOY-GOODWILL-TRUEUP-<firm code>``.

**It is idempotent.** A restored row is no longer deleted, a cleared
reference is no longer foreign, and a firm whose true-up reference exists is
skipped, so a second run finds nothing to do. Every change writes an audit row
on the store it changes: a restore goes through the owning service's own
``restore``, which is also what refuses a restore into a code a live row has
taken since (D-MST-11) and re-posts an opening balance a pre-D-FIN-1 delete
reversed.

``repair_store`` is the work against one session; ``repair_every_store``
enumerates the stores from the firm registry, as ``purge_every_store`` and
``upgrade_every_store`` do, and reports every store -- including one it could
not read -- rather than stopping at the first failure.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.common.audit.services import record_audit
from app.common.open_documents import find_stock_holdings
from app.core.exceptions import ApplicationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import Customer, CustomerGroup
from app.finance.models import JournalEntry
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.services import LoyaltyService
from app.products.models import Product, ProductCategory
from app.vendors.models import Vendor, VendorCategory, VendorType

#: The journal reference a firm's goodwill true-up is posted under. Unique per
#: firm, which is what makes a second run skip the firm.
TRUEUP_REFERENCE = "LOY-GOODWILL-TRUEUP-{code}"

#: ``(record, field on it, master it names)`` for every master reference a
#: firm could have been handed from another firm's rows (D-MST-3).
_FOREIGN_REFERENCES: tuple[tuple[Any, str, Any], ...] = (
    (Customer, "customer_group_id", CustomerGroup),
    (Vendor, "category_id", VendorCategory),
    (Vendor, "type_id", VendorType),
    (Product, "category_id", ProductCategory),
    (Product, "sub_category_id", ProductCategory),
)

#: What each record is called in an audit row and a report line.
_ENTITY_NAMES: dict[Any, str] = {
    Customer: "customer",
    Vendor: "vendor",
    Product: "product",
}


@dataclass(frozen=True, slots=True)
class RepairFirm:
    """One firm living in the store being repaired."""

    id: UUID
    code: str


@dataclass(slots=True)
class StoreRepair:
    """What one store needed, and what was done about it."""

    label: str
    restored_customers: list[str] = field(default_factory=list)
    restored_products: list[str] = field(default_factory=list)
    cleared_references: list[str] = field(default_factory=list)
    goodwill_trueups: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def changes(self) -> int:
        """Return how many repairs this store needed."""
        return (
            len(self.restored_customers)
            + len(self.restored_products)
            + len(self.cleared_references)
            + len(self.goodwill_trueups)
        )

    def lines(self, *, dry_run: bool) -> list[str]:
        """Render the store's part of the summary."""
        if self.error is not None:
            return [self.label, f"  could not be read: {self.error}"]
        verb = "would" if dry_run else "did"
        out = [self.label]
        sections = (
            ("restore customer", self.restored_customers),
            ("restore product", self.restored_products),
            ("clear reference", self.cleared_references),
            ("post goodwill true-up", self.goodwill_trueups),
        )
        for what, items in sections:
            out.extend(f"  {verb} {what}: {item}" for item in items)
        out.extend(f"  skipped: {item}" for item in self.skipped)
        if len(out) == 1:
            out.append("  nothing to repair")
        return out


def repair_store(
    session: Session,
    firms: Sequence[RepairFirm],
    *,
    dry_run: bool,
    actor_id: UUID,
    label: str = "store",
) -> StoreRepair:
    """Find, and unless ``dry_run`` repair, every legacy row in one store.

    Args:
        session: A session on the store.
        firms: The live firms whose rows live in it.
        dry_run: Report only; change nothing.
        actor_id: Who the audit rows and the journal name as the author.
        label: What to call the store in the report.

    Returns:
        What the store needed and what was done.

    """
    result = StoreRepair(label=label)
    for firm in firms:
        _restore_customers(session, firm, result, dry_run=dry_run, actor=actor_id)
        _restore_products(session, firm, result, dry_run=dry_run, actor=actor_id)
    _clear_foreign_references(session, result, dry_run=dry_run, actor=actor_id)
    for firm in firms:
        _true_up_goodwill(session, firm, result, dry_run=dry_run, actor=actor_id)
    return result


def _restore_customers(
    session: Session,
    firm: RepairFirm,
    result: StoreRepair,
    *,
    dry_run: bool,
    actor: UUID,
) -> None:
    """Restore every deleted customer of the firm still carrying a balance."""
    from app.customers.services import CustomerService

    rows = session.scalars(
        select(Customer)
        .where(
            Customer.firm_id == firm.id,
            Customer.is_deleted.is_(True),
            Customer.current_outstanding != 0,
        )
        .order_by(Customer.code)
    ).all()
    for row in rows:
        what = f"{firm.code} {row.code} (outstanding {row.current_outstanding})"
        if dry_run:
            result.restored_customers.append(what)
            continue
        try:
            CustomerService(session).restore(row.id, firm_scope=firm.id, actor_id=actor)
        except ApplicationError as exc:
            session.rollback()
            result.skipped.append(f"customer {what}: {exc}")
            continue
        result.restored_customers.append(what)


def _restore_products(
    session: Session,
    firm: RepairFirm,
    result: StoreRepair,
    *,
    dry_run: bool,
    actor: UUID,
) -> None:
    """Restore every deleted product of the firm that still holds stock."""
    from app.products.services import ProductService

    rows = session.scalars(
        select(Product)
        .where(Product.firm_id == firm.id, Product.is_deleted.is_(True))
        .order_by(Product.code)
    ).all()
    for row in rows:
        holdings = find_stock_holdings(session, firm.id, product_id=row.id)
        if not holdings:
            continue
        what = f"{firm.code} {row.code} (stock in {len(holdings)} place(s))"
        if dry_run:
            result.restored_products.append(what)
            continue
        try:
            ProductService(session).restore_product(
                row.id, firm_scope=firm.id, actor_id=actor
            )
        except ApplicationError as exc:
            session.rollback()
            result.skipped.append(f"product {what}: {exc}")
            continue
        result.restored_products.append(what)


def _clear_foreign_references(
    session: Session, result: StoreRepair, *, dry_run: bool, actor: UUID
) -> None:
    """Set to NULL every master reference naming another firm's row."""
    changed = False
    for record, column, master in _FOREIGN_REFERENCES:
        named = aliased(master)
        reference = getattr(record, column)
        rows = session.scalars(
            select(record)
            .join(named, named.id == reference)
            .where(named.firm_id != record.firm_id)
            .order_by(record.firm_id, record.code)
        ).all()
        entity = _ENTITY_NAMES[record]
        for row in rows:
            before = getattr(row, column)
            result.cleared_references.append(
                f"{entity} {row.code}.{column} named another firm's row {before}"
            )
            if dry_run:
                continue
            setattr(row, column, None)
            row.updated_by = actor
            record_audit(
                session,
                action=f"{entity}.foreign_reference_cleared",
                entity_type=entity,
                entity_id=row.id,
                actor_id=actor,
                firm_id=row.firm_id,
                before_data={column: str(before)},
                after_data={
                    column: None,
                    "reason": "D-MST-3: named another firm's master.",
                },
            )
            changed = True
    if changed:
        session.commit()


def _unbooked_goodwill(session: Session, firm_id: UUID) -> Decimal:
    """Return the goodwill points still held that were never accrued.

    Unbooked goodwill is what ``LoyaltyService`` itself treats as such: an
    ADJUSTED credit with no value and no journal -- given before D-SELL-19.
    What is left of each batch comes from ``unspent_batches``, the same
    oldest-first walk a redemption and the expiry sweep use.
    """
    service = LoyaltyService(session)
    customers = session.scalars(
        select(LoyaltyEntry.customer_id)
        .where(
            LoyaltyEntry.firm_id == firm_id,
            LoyaltyEntry.is_deleted.is_(False),
            LoyaltyEntry.kind == LoyaltyEntryKind.ADJUSTED.value,
            LoyaltyEntry.points > 0,
            LoyaltyEntry.amount == 0,
            LoyaltyEntry.journal_entry_id.is_(None),
        )
        .group_by(LoyaltyEntry.customer_id)
    ).all()
    held = ZERO
    for customer_id in customers:
        for batch, remaining in service.unspent_batches(
            customer_id, firm_scope=firm_id
        ):
            if (
                batch.kind == LoyaltyEntryKind.ADJUSTED.value
                and Decimal(str(batch.amount)) == ZERO
                and batch.journal_entry_id is None
            ):
                held += remaining
    return held


def _true_up_goodwill(
    session: Session,
    firm: RepairFirm,
    result: StoreRepair,
    *,
    dry_run: bool,
    actor: UUID,
) -> None:
    """Accrue, once, the goodwill points a firm still owes but never booked."""
    reference = TRUEUP_REFERENCE.format(code=firm.code)
    exists = session.scalar(
        select(JournalEntry.id).where(
            JournalEntry.firm_id == firm.id,
            JournalEntry.reference_number == reference,
        )
    )
    if exists is not None:
        return
    points = _unbooked_goodwill(session, firm.id)
    if points <= ZERO:
        return
    # The scheme's value per point, as `LoyaltyService.adjust` values points
    # given; a firm with no scheme values them at nothing.
    settings = LoyaltyService(session).settings_for(firm.id)
    rate = ZERO if settings is None else Decimal(str(settings.amount_per_point))
    value = quantize_ledger(points * rate)
    if value <= ZERO:
        return
    what = f"{firm.code} {reference}: {points} points at {rate} = {value}"
    if dry_run:
        result.goodwill_trueups.append(what)
        return
    try:
        posted = DocumentPostingService(session).post_loyalty(
            firm_id=firm.id,
            entry_id=firm.id,
            reference=reference,
            on=utc_now().date(),
            amount=value,
            earning=True,
            description="Goodwill points never accrued (D-SELL-19 true-up)",
            actor_id=actor,
        )
    except ApplicationError as exc:
        session.rollback()
        result.skipped.append(f"goodwill {what}: {exc}")
        return
    if posted is None:
        session.rollback()
        return
    record_audit(
        session,
        action="loyalty.goodwill_trued_up",
        entity_type="journal_entry",
        entity_id=posted.id,
        actor_id=actor,
        firm_id=firm.id,
        after_data={
            "reference": reference,
            "points": str(points),
            "amount_per_point": str(rate),
            "amount": str(value),
            "reason": "D-SELL-19: goodwill granted before #477 was never accrued.",
        },
    )
    session.commit()
    result.goodwill_trueups.append(what)


def _print_line(text_line: str) -> None:
    """Write one report line to stdout."""
    print(text_line)


def repair_every_store(
    *,
    dry_run: bool,
    actor_email: str | None = None,
    report: Callable[[str], None] | None = None,
) -> int:
    """Report, or apply, every legacy repair across every firm store.

    Args:
        dry_run: Report only; change nothing.
        actor_email: Whose name the repairs go under. Defaults to the
            longest-standing platform administrator.
        report: Where the summary goes; stdout by default.

    Returns:
        A process exit code: 0, or 1 when a store could not be read or no
        actor could be found.

    """
    from app.core.config.settings import Settings
    from app.core.database.engine import DatabaseManager
    from app.core.tenancy.models import DeploymentMode, TenantContext
    from app.core.tenancy.provider import MultiTenantDatabaseProvider
    from app.core.tenancy.resolvers import FirmConnectionResolver, FirmSchemaResolver
    from app.firms.models import Firm, FirmStorageMapping
    from app.identity.models import PlatformAdmin, User

    say = report if report is not None else _print_line
    settings = Settings()
    platform = DatabaseManager.from_settings(settings)
    stores: dict[
        tuple[str | None, str | None, str | None],
        tuple[str, TenantContext, list[RepairFirm]],
    ] = {}
    with platform.sessions(schema=platform.config.default_schema).session() as session:
        if actor_email is not None:
            actor = session.scalar(
                select(User.id).where(
                    User.email == actor_email, User.is_deleted.is_(False)
                )
            )
        else:
            actor = session.scalar(
                select(PlatformAdmin.user_id)
                .where(PlatformAdmin.is_deleted.is_(False))
                .order_by(PlatformAdmin.created_at.asc(), PlatformAdmin.id.asc())
                .limit(1)
            )
        rows = session.execute(
            select(Firm, FirmStorageMapping)
            .join(FirmStorageMapping, FirmStorageMapping.firm_id == Firm.id)
            .where(
                Firm.is_deleted.is_(False),
                FirmStorageMapping.is_deleted.is_(False),
                FirmStorageMapping.is_active.is_(True),
            )
            .order_by(Firm.code)
        ).all()
        for firm, mapping in rows:
            mode = DeploymentMode(mapping.deployment_mode)
            if mode is DeploymentMode.SHARED:
                database_name = settings.tenancy.shared_database_name
                schema_name = settings.tenancy.shared_schema_name
            else:
                database_name = mapping.database_name
                schema_name = mapping.schema_name
            key = (mapping.connection_profile, database_name, schema_name)
            if key not in stores:
                label = f"{database_name}/{schema_name}" + (
                    f" on {mapping.connection_profile}"
                    if mapping.connection_profile
                    else ""
                )
                context = TenantContext(
                    firm_id=firm.id,
                    deployment_mode=mode,
                    database_name=database_name,
                    schema_name=schema_name,
                    database_type=mapping.database_type,
                    connection_profile=mapping.connection_profile,
                )
                stores[key] = (label, context, [])
            stores[key][2].append(RepairFirm(id=firm.id, code=firm.code))
    if actor is None:
        say(
            "No actor: name one with --actor-email, or create a platform "
            "administrator first. Nothing was read."
        )
        return 1

    provider = MultiTenantDatabaseProvider(
        platform,
        FirmConnectionResolver(platform, settings.tenancy.connection_profiles),
        FirmSchemaResolver(),
    )
    failed = 0
    total = 0
    try:
        for label, context, firms in sorted(stores.values(), key=lambda s: s[0]):
            try:
                manager = provider.manager_for(context)
                schema = provider.schema_for(context)
                with manager.sessions(schema=schema).session() as session:
                    outcome = repair_store(
                        session, firms, dry_run=dry_run, actor_id=actor, label=label
                    )
            except Exception as exc:  # noqa: BLE001 -- reported, never hidden
                outcome = StoreRepair(label=label, error=f"{type(exc).__name__}: {exc}")
                failed += 1
            total += outcome.changes
            for text_line in outcome.lines(dry_run=dry_run):
                say(text_line)
    finally:
        provider.dispose()
    verb = "would repair" if dry_run else "repaired"
    say(
        f"total: {verb} {total} row(s) across {len(stores)} store(s)"
        + (f"; {failed} store(s) could not be read" if failed else "")
    )
    return 1 if failed else 0
