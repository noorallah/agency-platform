"""A firm's rules for which batches go out on a sale (backlog 79 row 6).

Three questions a pharmacy or a food distributor is asked afterwards, each a
firm setting because firms answer them differently:

* **How near is near expiry?** 30 days unless the firm says otherwise. The
  batch picker flags a batch inside the window, and the two rules below judge
  it.
* **Does a near-expiry batch leaving need a reason?** WARN (the default)
  records it on the dispatch; REASON refuses the dispatch until somebody says
  why -- Marg's "short expiry" prompt.
* **Does drawing a later batch ahead of an earlier one need a reason?** RECORD
  (the default) keeps both splits in the audit trail, as #911 did; REASON also
  wants a reason, kept beside them.

And one exemption, decision A2: a line drawn wholly from near-expiry batches
may be sold below its price floor, because clearing short-dated stock at a
loss is the point of selling it. Cost stays one moving average per product;
the batches that made the exemption are named on the approval, so the trail
says why the floor did not bite.

A firm with no row shares the defaults, the shape of ``price_floor_settings``.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord, BatchSaleSettings
from app.batch_serial.schemas import BatchSaleSettingsResponse, BatchSaleSettingsWrite
from app.common.audit.services import record_audit

#: The rules every firm without a row shares. Never mutated.
DEFAULT_NEAR_EXPIRY_DAYS = 30
DEFAULT_NEAR_EXPIRY_POLICY = "WARN"
DEFAULT_FEFO_SKIP_POLICY = "RECORD"
DEFAULT_NEAR_EXPIRY_BELOW_FLOOR = True
DEFAULT_SHELF_LIFE_POLICY = "BLOCK"
DEFAULT_PRICE_FROM_BATCH = False

_ZERO = Decimal("0")


def describe_batches(batches: Sequence[BatchRecord], as_of: date) -> str:
    """Name batches and their expiry, as a message or an audit row says them."""
    parts: list[str] = []
    for batch in batches:
        if batch.expiry_date is None:
            parts.append(f"batch {batch.batch_number}")
            continue
        days = (batch.expiry_date - as_of).days
        parts.append(
            f"batch {batch.batch_number} (expires {batch.expiry_date.isoformat()}, "
            f"{days} day{'' if days == 1 else 's'} left)"
        )
    return ", ".join(parts)


class BatchSalePolicyService:
    """The firm's batch-sale rules, and judging a split of batches against them."""

    def __init__(self, session: Session) -> None:
        """Hold the session the document is being written on."""
        self._session = session

    # -- Policy ---------------------------------------------------------------

    def _stored(self, firm_id: UUID) -> BatchSaleSettings | None:
        """Return the firm's own row, or None if it never chose."""
        return self._session.scalar(
            select(BatchSaleSettings).where(
                BatchSaleSettings.firm_id == firm_id,
                BatchSaleSettings.is_deleted.is_(False),
            )
        )

    def settings_response(self, firm_id: UUID) -> BatchSaleSettingsResponse:
        """Report the firm's rules and whether the firm actually chose them."""
        stored = self._stored(firm_id)
        if stored is None:
            return BatchSaleSettingsResponse(
                near_expiry_days=DEFAULT_NEAR_EXPIRY_DAYS,
                near_expiry_policy=DEFAULT_NEAR_EXPIRY_POLICY,
                fefo_skip_policy=DEFAULT_FEFO_SKIP_POLICY,
                near_expiry_below_floor=DEFAULT_NEAR_EXPIRY_BELOW_FLOOR,
                shelf_life_policy=DEFAULT_SHELF_LIFE_POLICY,
                price_from_batch=DEFAULT_PRICE_FROM_BATCH,
                hold_returns_for_check=False,
                is_configured=False,
            )
        return BatchSaleSettingsResponse(
            near_expiry_days=stored.near_expiry_days,
            near_expiry_policy=stored.near_expiry_policy,
            fefo_skip_policy=stored.fefo_skip_policy,
            near_expiry_below_floor=stored.near_expiry_below_floor,
            shelf_life_policy=stored.shelf_life_policy,
            price_from_batch=stored.price_from_batch,
            hold_returns_for_check=stored.hold_returns_for_check,
            is_configured=True,
        )

    def update_settings(
        self, data: BatchSaleSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> BatchSaleSettingsResponse:
        """Replace the firm's rules, creating its row on the first write."""
        row = self._stored(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = BatchSaleSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
        else:
            before = self._snapshot(row)
        row.near_expiry_days = data.near_expiry_days
        row.near_expiry_policy = data.near_expiry_policy
        row.fefo_skip_policy = data.fefo_skip_policy
        row.near_expiry_below_floor = data.near_expiry_below_floor
        row.shelf_life_policy = data.shelf_life_policy
        row.price_from_batch = data.price_from_batch
        row.hold_returns_for_check = data.hold_returns_for_check
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "batch_sale_settings.updated"
                if before is not None
                else "batch_sale_settings.created"
            ),
            entity_type="batch_sale_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        self._session.commit()
        return self.settings_response(firm_id)

    @staticmethod
    def _snapshot(row: BatchSaleSettings) -> dict[str, object]:
        """Return the four rules, as the audit trail keeps them."""
        return {
            "near_expiry_days": row.near_expiry_days,
            "near_expiry_policy": row.near_expiry_policy,
            "fefo_skip_policy": row.fefo_skip_policy,
            "near_expiry_below_floor": row.near_expiry_below_floor,
            "shelf_life_policy": row.shelf_life_policy,
            "price_from_batch": row.price_from_batch,
            "hold_returns_for_check": row.hold_returns_for_check,
        }

    def near_expiry_days(self, firm_id: UUID) -> int:
        """Return how many days before expiry a batch counts as near expiry."""
        return self.settings_response(firm_id).near_expiry_days

    # -- Judging --------------------------------------------------------------

    def near_expiry(
        self,
        firm_id: UUID,
        batch_ids: Sequence[UUID | None],
        *,
        as_of: date,
        days: int | None = None,
    ) -> list[BatchRecord]:
        """Return the named batches that are near expiry on ``as_of``.

        In date and expiring within the window -- an expired batch is not near
        expiry, it is refused elsewhere. ``days`` saves re-reading the rules.
        """
        wanted = [batch_id for batch_id in batch_ids if batch_id is not None]
        if not wanted:
            return []
        window = self.near_expiry_days(firm_id) if days is None else days
        return list(
            self._session.scalars(
                select(BatchRecord)
                .where(
                    BatchRecord.id.in_(wanted),
                    BatchRecord.expiry_date.is_not(None),
                    # Out of date on its expiry day, as dispatch judges it.
                    BatchRecord.expiry_date > as_of,
                    BatchRecord.expiry_date <= as_of + timedelta(days=window),
                    BatchRecord.status != "EXPIRED",
                )
                .order_by(BatchRecord.expiry_date.asc(), BatchRecord.id.asc())
            )
        )

    def keep_until(self, customer_id: UUID | None, *, on: date) -> date | None:
        """Return the date a customer's goods must last to, or None (79 row 6).

        Read from the customer's minimum shelf life on the document's date.
        """
        if customer_id is None:
            return None
        # Imported here: customers is a large module batch_serial need not load.
        from app.customers.models import Customer

        days = self._session.scalar(
            select(Customer.minimum_shelf_life_days).where(Customer.id == customer_id)
        )
        return on + timedelta(days=int(days)) if days else None

    def short_of(
        self, batch_ids: Sequence[UUID | None], *, keep_until: date
    ) -> list[BatchRecord]:
        """Return the named batches that expire before ``keep_until``."""
        wanted = [batch_id for batch_id in batch_ids if batch_id is not None]
        if not wanted:
            return []
        return list(
            self._session.scalars(
                select(BatchRecord)
                .where(
                    BatchRecord.id.in_(wanted),
                    BatchRecord.expiry_date.is_not(None),
                    BatchRecord.expiry_date < keep_until,
                )
                .order_by(BatchRecord.expiry_date.asc(), BatchRecord.id.asc())
            )
        )

    def floor_exemption(
        self,
        firm_id: UUID,
        split: Sequence[tuple[UUID | None, Decimal]],
        *,
        as_of: date,
    ) -> str | None:
        """Say why a line may be sold below its floor, or None (decision A2).

        Only when the firm allows it and **every** batch the line draws is near
        expiry: a line half from a fresh batch is a sale of fresh stock as
        well, and the floor protects that half.
        """
        drawn = [(batch_id, qty) for batch_id, qty in split if qty > _ZERO]
        if not drawn or any(batch_id is None for batch_id, _ in drawn):
            return None
        policy = self.settings_response(firm_id)
        if not policy.near_expiry_below_floor:
            return None
        ids = list(dict.fromkeys(batch_id for batch_id, _ in drawn))
        near = self.near_expiry(firm_id, ids, as_of=as_of, days=policy.near_expiry_days)
        if len(near) != len(ids):
            return None
        return f"near expiry: {describe_batches(near, as_of)}"
