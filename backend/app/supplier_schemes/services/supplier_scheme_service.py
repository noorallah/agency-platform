"""Supplier free-goods schemes on an item (PG-11, backlog 86 #25).

A scheme is set once -- "10+2" on a product, or "a bucket free with 10 soap"
-- for one supplier or for every supplier of the product, and from then on a
purchase order line priced inside its dates takes the free goods by itself,
as Marg's item-wise and other-free schemes do:

* **Same product.** The line's free quantity is filled with
  ``floor(ordered / buy) * free`` -- but only where the line left it blank.
  An explicit ``0`` refuses the scheme, the same two answers as a discount
  (``resolve_supplier_free_goods`` in ``app/core/utils/pricing.py``).
* **Another product.** The free goods go on a line of their own (paid 0, free
  n). The order preview offers that line as a *suggestion*; the client adds it
  with the scheme's id when the buyer accepts. Saving never invents a line.

A supplier's own scheme beats an all-suppliers one. Two active schemes for
the same supplier (or both for every supplier) and product whose dates
overlap are refused, under a lock on the product: overlap is a fact about a
set of rows, which no key can express.

Schemes have no versions. A line records the scheme it took
(``purchase_order_lines.scheme_id``) and its label as it read then
(``scheme_name``), and the receipt and the bill raised from the line inherit
its free goods as they always have.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.pricing import SchemeFree, resolve_supplier_free_goods
from app.products.models import Product
from app.supplier_schemes.models import SupplierScheme
from app.supplier_schemes.schemas import (
    SupplierSchemeCreate,
    SupplierSchemeResponse,
    SupplierSchemeUpdate,
)
from app.vendors.models import Vendor

ZERO = Decimal("0")


def _number(value: Decimal) -> str:
    """Render a quantity without trailing zeros: 10.0000 is ``10``."""
    text = format(Decimal(value).normalize(), "f")
    return text


def scheme_label(row: SupplierScheme, free_product_name: str | None = None) -> str:
    """Return a scheme as a buyer says it: ``10+2``, or ``10 + 1 Bucket``."""
    buy, free = _number(row.buy_quantity), _number(row.free_quantity)
    if row.free_product_id is None or row.free_product_id == row.product_id:
        return f"{buy}+{free}"
    return f"{buy} + {free} {free_product_name or 'other product'}"


def schemes_in_force(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    product_ids: Iterable[UUID],
    on: date,
) -> dict[UUID, SupplierScheme]:
    """Return the scheme governing each product bought from a supplier on a day.

    One query. The supplier's own scheme beats one for every supplier; within
    either, the later ``valid_from`` (overlaps are refused, so a tie is a
    scheme that starts the day the other ends).
    """
    ids = list(set(product_ids))
    if not ids:
        return {}
    rows = session.scalars(
        select(SupplierScheme).where(
            SupplierScheme.firm_id == firm_id,
            SupplierScheme.product_id.in_(ids),
            SupplierScheme.is_deleted.is_(False),
            SupplierScheme.is_active.is_(True),
            SupplierScheme.valid_from <= on,
            or_(SupplierScheme.valid_to.is_(None), SupplierScheme.valid_to >= on),
            or_(
                SupplierScheme.vendor_id == vendor_id,
                SupplierScheme.vendor_id.is_(None),
            ),
        )
    ).all()
    found: dict[UUID, SupplierScheme] = {}
    for row in rows:
        held = found.get(row.product_id)
        # Ranked explicitly rather than by NULL sort order, which differs
        # between PostgreSQL and SQLite.
        rank = (row.vendor_id is not None, row.valid_from)
        if held is None or rank > (held.vendor_id is not None, held.valid_from):
            found[row.product_id] = row
    return found


@dataclass(frozen=True, slots=True)
class LineScheme:
    """What the supplier's scheme does to one order line."""

    #: The free quantity the line is saved with.
    free_quantity: Decimal
    #: The scheme the line's free goods came from, and its label then.
    scheme_id: UUID | None
    scheme_name: str | None
    #: A scheme giving another product, and how much of it this line earns.
    other: SupplierScheme | None
    other_quantity: Decimal
    other_label: str | None


def line_schemes(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    on: date,
    lines: Sequence[tuple[UUID, Decimal, Decimal | None, UUID | None]],
) -> list[LineScheme]:
    """Resolve each ``(product, ordered, typed free, typed scheme)`` line.

    A line naming a scheme itself is a gift line the client added from a
    suggestion: it keeps the scheme if the scheme is the firm's and gives
    that line's product, and is refused otherwise.

    Raises:
        ValidationError: If a line names a scheme that does not give its
            product.

    """
    governing = schemes_in_force(
        session,
        firm_id=firm_id,
        vendor_id=vendor_id,
        product_ids=[product_id for product_id, _, _, _ in lines],
        on=on,
    )
    named_ids = {scheme_id for _, _, _, scheme_id in lines if scheme_id is not None}
    named = (
        {
            row.id: row
            for row in session.scalars(
                select(SupplierScheme).where(
                    SupplierScheme.id.in_(named_ids),
                    SupplierScheme.firm_id == firm_id,
                )
            ).all()
        }
        if named_ids
        else {}
    )
    free_ids = {
        row.free_product_id
        for row in [*governing.values(), *named.values()]
        if row.free_product_id is not None
    }
    names: dict[UUID | None, str] = (
        {
            product_id: name
            for product_id, name in session.execute(
                select(Product.id, Product.name).where(Product.id.in_(free_ids))
            ).all()
        }
        if free_ids
        else {}
    )
    out: list[LineScheme] = []
    for number, (product_id, ordered, typed, typed_scheme) in enumerate(lines, start=1):
        if typed_scheme is not None:
            row = named.get(typed_scheme)
            gives = None if row is None else (row.free_product_id or row.product_id)
            if row is None or gives != product_id:
                raise ValidationError(
                    f"Line {number} names a supplier scheme that does not give "
                    "its product free."
                )
            if row.free_product_id not in (None, row.product_id):
                out.append(
                    LineScheme(
                        free_quantity=typed if typed is not None else ZERO,
                        scheme_id=row.id,
                        scheme_name=scheme_label(row, names.get(row.free_product_id)),
                        other=None,
                        other_quantity=ZERO,
                        other_label=None,
                    )
                )
                continue
        scheme = governing.get(product_id)
        same = scheme is not None and scheme.free_product_id in (None, product_id)
        resolved: SchemeFree = resolve_supplier_free_goods(
            typed=typed,
            quantity=ordered,
            buy_quantity=scheme.buy_quantity if scheme is not None else None,
            scheme_free_quantity=scheme.free_quantity if scheme is not None else None,
            same_product=same or scheme is None,
        )
        label = (
            scheme_label(scheme, names.get(scheme.free_product_id))
            if scheme is not None
            else None
        )
        out.append(
            LineScheme(
                free_quantity=resolved.free_quantity,
                scheme_id=scheme.id if resolved.applied and scheme else None,
                scheme_name=label if resolved.applied else None,
                other=(
                    scheme
                    if scheme is not None and resolved.other_product_quantity > ZERO
                    else None
                ),
                other_quantity=resolved.other_product_quantity,
                other_label=label if resolved.other_product_quantity > ZERO else None,
            )
        )
    return out


class SupplierSchemeService:
    """Set up, change and remove supplier schemes."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session

    # -- reading --------------------------------------------------------
    def get(self, scheme_id: UUID, *, firm_id: UUID) -> SupplierScheme:
        """Return one live scheme of the firm.

        Raises:
            ResourceNotFoundError: If there is none.

        """
        row = self._session.get(SupplierScheme, scheme_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            raise ResourceNotFoundError("Supplier scheme not found.")
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        vendor_id: UUID | None,
        product_id: UUID | None,
        all_suppliers: bool | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[SupplierScheme], int]:
        """Return one page of the firm's schemes, latest start first."""
        query: Select[tuple[SupplierScheme]] = select(SupplierScheme).where(
            SupplierScheme.firm_id == firm_id, SupplierScheme.is_deleted.is_(False)
        )
        if vendor_id is not None:
            query = query.where(SupplierScheme.vendor_id == vendor_id)
        if all_suppliers is True:
            query = query.where(SupplierScheme.vendor_id.is_(None))
        elif all_suppliers is False:
            query = query.where(SupplierScheme.vendor_id.is_not(None))
        if product_id is not None:
            query = query.where(
                or_(
                    SupplierScheme.product_id == product_id,
                    SupplierScheme.free_product_id == product_id,
                )
            )
        if is_active is not None:
            query = query.where(SupplierScheme.is_active.is_(is_active))
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(
                SupplierScheme.valid_from.desc(),
                SupplierScheme.created_at.desc(),
                SupplierScheme.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def responses(self, rows: Sequence[SupplierScheme]) -> list[SupplierSchemeResponse]:
        """Build a page of responses, reading vendors and products once each."""
        vendor_ids = {row.vendor_id for row in rows if row.vendor_id is not None}
        product_ids = {row.product_id for row in rows} | {
            row.free_product_id for row in rows if row.free_product_id is not None
        }
        vendors = (
            {
                vendor_id: (code, name)
                for vendor_id, code, name in self._session.execute(
                    select(Vendor.id, Vendor.code, Vendor.name).where(
                        Vendor.id.in_(vendor_ids)
                    )
                ).all()
            }
            if vendor_ids
            else {}
        )
        products = (
            {
                product_id: (code, name)
                for product_id, code, name in self._session.execute(
                    select(Product.id, Product.code, Product.name).where(
                        Product.id.in_(product_ids)
                    )
                ).all()
            }
            if product_ids
            else {}
        )
        today = utc_now().date()
        out: list[SupplierSchemeResponse] = []
        for row in rows:
            vendor = vendors.get(row.vendor_id) if row.vendor_id else None
            product = products.get(row.product_id, ("", ""))
            free = products.get(row.free_product_id or row.product_id, ("", ""))
            out.append(
                SupplierSchemeResponse(
                    id=row.id,
                    vendor_id=row.vendor_id,
                    vendor_code=vendor[0] if vendor else None,
                    vendor_name=vendor[1] if vendor else None,
                    product_id=row.product_id,
                    product_code=product[0],
                    product_name=product[1],
                    buy_quantity=row.buy_quantity,
                    free_quantity=row.free_quantity,
                    free_product_id=row.free_product_id,
                    free_product_code=free[0],
                    free_product_name=free[1],
                    label=scheme_label(row, free[1]),
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    is_active=row.is_active,
                    in_force=row.is_active
                    and row.valid_from <= today
                    and (row.valid_to is None or row.valid_to >= today),
                    notes=row.notes,
                    version=row.version,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return out

    # -- writing --------------------------------------------------------
    def create(
        self, data: SupplierSchemeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SupplierScheme:
        """Set a scheme up and commit.

        Raises:
            ValidationError: If a reference is not the firm's, the dates run
                backwards, or an active scheme for the same supplier and
                product overlaps it.

        """
        row = SupplierScheme(
            firm_id=firm_id,
            vendor_id=data.vendor_id,
            product_id=data.product_id,
            buy_quantity=data.buy_quantity,
            free_quantity=data.free_quantity,
            free_product_id=(
                None
                if data.free_product_id == data.product_id
                else data.free_product_id
            ),
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            is_active=data.is_active,
            notes=data.notes,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._check(row)
        self._session.add(row)
        self._session.flush()
        self._audit("supplier_scheme.created", row, actor_id, before=None)
        self._session.commit()
        return row

    def update(
        self,
        scheme_id: UUID,
        data: SupplierSchemeUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SupplierScheme:
        """Change a scheme; a field left out is left alone.

        Raises:
            ValidationError: If a required field is cleared, or the change
                leaves the scheme invalid or overlapping another.

        """
        row = self.get(scheme_id, firm_id=firm_id)
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        for field in (
            "product_id",
            "buy_quantity",
            "free_quantity",
            "valid_from",
            "is_active",
        ):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        for field, value in values.items():
            setattr(row, field, value)
        if row.free_product_id == row.product_id:
            row.free_product_id = None
        row.updated_by = actor_id
        self._check(row)
        self._session.flush()
        self._audit("supplier_scheme.updated", row, actor_id, before=before)
        self._session.commit()
        return row

    def delete(self, scheme_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a scheme; lines that took it keep its id and label."""
        row = self.get(scheme_id, firm_id=firm_id)
        before = self._snapshot(row)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        self._audit("supplier_scheme.deleted", row, actor_id, before=before)
        self._session.commit()

    # -- rules ----------------------------------------------------------
    def _check(self, row: SupplierScheme) -> None:
        """Refuse a scheme off the firm's masters, backwards, or overlapping."""
        if row.valid_to is not None and row.valid_to < row.valid_from:
            raise ValidationError("A scheme cannot end before it starts.")
        if row.vendor_id is not None:
            vendor = self._session.get(Vendor, row.vendor_id)
            if vendor is None or vendor.is_deleted or vendor.firm_id != row.firm_id:
                raise ValidationError("Supplier not found in this firm.")
        # The lock serialises scheme writes per product, so two overlapping
        # schemes saved at once cannot both pass the check below.
        product = self._session.scalar(
            select(Product).where(Product.id == row.product_id).with_for_update()
        )
        if product is None or product.is_deleted or product.firm_id != row.firm_id:
            raise ValidationError("Product not found in this firm.")
        if row.free_product_id is not None:
            free = self._session.get(Product, row.free_product_id)
            if free is None or free.is_deleted or free.firm_id != row.firm_id:
                raise ValidationError("Free product not found in this firm.")
        if not row.is_active:
            return
        query = select(SupplierScheme).where(
            SupplierScheme.firm_id == row.firm_id,
            SupplierScheme.product_id == row.product_id,
            SupplierScheme.is_deleted.is_(False),
            SupplierScheme.is_active.is_(True),
            (
                SupplierScheme.vendor_id.is_(None)
                if row.vendor_id is None
                else SupplierScheme.vendor_id == row.vendor_id
            ),
            or_(
                SupplierScheme.valid_to.is_(None),
                SupplierScheme.valid_to >= row.valid_from,
            ),
        )
        if row.valid_to is not None:
            query = query.where(SupplierScheme.valid_from <= row.valid_to)
        if row.id is not None:
            query = query.where(SupplierScheme.id != row.id)
        clash = self._session.scalars(query.limit(1)).first()
        if clash is not None:
            whom = "this supplier" if row.vendor_id else "every supplier"
            until = clash.valid_to.isoformat() if clash.valid_to else "open-ended"
            raise ValidationError(
                f"An active scheme for {whom} on this product already runs "
                f"{clash.valid_from.isoformat()} to {until}. End or switch it "
                "off first."
            )

    @staticmethod
    def _snapshot(row: SupplierScheme) -> dict[str, object]:
        """Return the audited fields of a scheme."""
        return {
            "vendor_id": str(row.vendor_id) if row.vendor_id else None,
            "product_id": str(row.product_id),
            "buy_quantity": str(row.buy_quantity),
            "free_quantity": str(row.free_quantity),
            "free_product_id": (
                str(row.free_product_id) if row.free_product_id else None
            ),
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "is_active": row.is_active,
        }

    def _audit(
        self,
        action: str,
        row: SupplierScheme,
        actor_id: UUID,
        *,
        before: dict[str, object] | None,
    ) -> None:
        """Write one audit row for a scheme."""
        record_audit(
            self._session,
            action=action,
            entity_type="supplier_scheme",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
