"""Keep the firm's own list of salesmen (P2, salesman list design step 1).

Every column that names a salesman references this table (step 2,
`20261014_0382`); who may be named is decided in
`app/salesmen/services/nameable.py`.
"""

from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.commission.models.commission import CommissionRule
from app.commission.models.payout import CommissionPayout
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.credit_note.models.credit_note import CreditNote
from app.customer_debit_note.models.customer_debit_note import CustomerDebitNote
from app.customers.models.customer import Customer
from app.delivery_note.models.delivery_note import DeliveryNote
from app.enquiry.models import Enquiry
from app.quotation.models.quotation import SalesQuotation
from app.sales.models.territory import (
    SalesTerritoryNode,
    TerritorySalesmanAssignment,
)
from app.sales_invoice.models.sales_invoice import SalesInvoice
from app.sales_order.models.sales_order import SalesOrder
from app.sales_return.models.sales_return import SalesReturn
from app.sales_targets.models.sales_target import SalesTarget
from app.salesmen.models import Salesman
from app.salesmen.schemas import SalesmanCreate, SalesmanUpdate

SalesmanSort = Literal["name", "code", "created_at"]

#: Every place a salesman is named, with what to call it in a refusal. Each
#: carries its own ``firm_id`` and a ``salesman_id``; the round assignment is
#: the one exception and is asked separately, through its territory.
_NAMED_BY: tuple[tuple[Any, str], ...] = (
    (SalesInvoice, "sales invoice"),
    (SalesOrder, "sales order"),
    (DeliveryNote, "delivery note"),
    (SalesQuotation, "quotation"),
    (Enquiry, "enquiry"),
    (CreditNote, "credit note"),
    (CustomerDebitNote, "debit note"),
    (SalesReturn, "sales return"),
    (Customer, "customer"),
    (CommissionRule, "commission rule"),
    (CommissionPayout, "commission payout"),
    (SalesTarget, "sales target"),
)

#: Fields an update may not set to null: the table holds them NOT NULL.
_REQUIRED_FIELDS = ("name", "earns_commission", "is_active")


def _snapshot(row: Salesman) -> dict[str, object]:
    """Describe an entry for the audit trail."""
    return {
        "code": row.code,
        "name": row.name,
        "user_id": str(row.user_id) if row.user_id else None,
        "phone": row.phone,
        "earns_commission": row.earns_commission,
        "is_active": row.is_active,
    }


class SalesmanService:
    """The list, its uniqueness rules, and what may be deleted."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    # -- reading ---------------------------------------------------------------

    def list_salesmen(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str | None = None,
        active: bool | None = None,
        sort_by: SalesmanSort = "name",
        descending: bool = False,
    ) -> tuple[Sequence[Salesman], int]:
        """Return one page of the firm's live entries and the total."""
        query: Select[tuple[Salesman]] = select(Salesman).where(
            Salesman.firm_id == firm_id, Salesman.is_deleted.is_(False)
        )
        if active is not None:
            query = query.where(Salesman.is_active.is_(active))
        term = (search or "").strip()
        if term:
            pattern = f"%{term}%"
            query = query.where(
                or_(
                    Salesman.name.ilike(pattern),
                    Salesman.code.ilike(pattern),
                    Salesman.phone.ilike(pattern),
                )
            )
        total = int(
            self._session.scalar(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
            or 0
        )
        column: InstrumentedAttribute[Any] = {
            "name": Salesman.name,
            "code": Salesman.code,
            "created_at": Salesman.created_at,
        }[sort_by]
        ordering = column.desc() if descending else column.asc()
        rows = self._session.scalars(
            query.order_by(ordering, Salesman.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, total

    def get(self, salesman_id: UUID, *, firm_id: UUID) -> Salesman:
        """Return one live entry of this firm, or refuse by name."""
        row = self._session.scalar(
            select(Salesman).where(
                Salesman.id == salesman_id,
                Salesman.firm_id == firm_id,
                Salesman.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Salesman not found.")
        return row

    # -- the rules ---------------------------------------------------------------

    def _assert_unique(
        self,
        firm_id: UUID,
        *,
        name: str,
        code: str | None,
        user_id: UUID | None,
        excluding: UUID | None = None,
    ) -> None:
        """Refuse a second live entry with the same name, code or user."""

        def taken(*conditions: ColumnElement[bool]) -> bool:
            query = select(Salesman.id).where(
                Salesman.firm_id == firm_id,
                Salesman.is_deleted.is_(False),
                *conditions,
            )
            if excluding is not None:
                query = query.where(Salesman.id != excluding)
            return self._session.scalar(query.limit(1)) is not None

        if taken(func.lower(Salesman.name) == name.lower()):
            raise ConflictError(f"A salesman named {name} is already on the list.")
        if code is not None and taken(Salesman.code == code):
            raise ConflictError(f"A salesman with code {code} is already on the list.")
        if user_id is not None and taken(Salesman.user_id == user_id):
            raise ConflictError("That user is already tied to another salesman.")

    def _assert_member(self, firm_id: UUID, user_id: UUID | None) -> None:
        """Refuse a user who is not an active member of the firm.

        ``users`` and ``user_firms`` live only in the platform store, which
        `FirmMetadataReader` reads on its own connection.
        """
        if user_id is None:
            return
        members = FirmMetadataReader(self._session)
        if members.active_member_count(firm_id, [user_id]) != 1:
            raise ValidationError("That user is not an active member of this firm.")

    def references(self, salesman_id: UUID, *, firm_id: UUID) -> list[str]:
        """Name what still names this entry, the first of each kind found."""
        found: list[str] = []
        for model, label in _NAMED_BY:
            if self._session.scalar(
                select(
                    exists().where(
                        model.firm_id == firm_id,
                        model.salesman_id == salesman_id,
                        model.is_deleted.is_(False),
                    )
                )
            ):
                found.append(label)
        if self._session.scalar(
            select(
                exists().where(
                    TerritorySalesmanAssignment.territory_id == SalesTerritoryNode.id,
                    SalesTerritoryNode.firm_id == firm_id,
                    TerritorySalesmanAssignment.salesman_id == salesman_id,
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
        ):
            found.append("route assignment")
        return found

    # -- writing ---------------------------------------------------------------

    def create(
        self, data: SalesmanCreate, *, firm_id: UUID, actor_id: UUID
    ) -> Salesman:
        """Add one entry."""
        self._assert_unique(
            firm_id, name=data.name, code=data.code, user_id=data.user_id
        )
        self._assert_member(firm_id, data.user_id)
        row = Salesman(firm_id=firm_id, **data.model_dump(), created_by=actor_id)
        row.updated_by = actor_id
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="salesman.created",
            entity_type="salesman",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=_snapshot(row),
        )
        self._session.commit()
        return row

    def update(
        self,
        salesman_id: UUID,
        data: SalesmanUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> Salesman:
        """Change the fields sent; a field left out is left alone."""
        row = self.get(salesman_id, firm_id=firm_id)
        values = data.model_dump(exclude_unset=True)
        for field in _REQUIRED_FIELDS:
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be cleared.")
        name = values.get("name", row.name)
        code = values.get("code", row.code)
        user_id = values.get("user_id", row.user_id)
        self._assert_unique(
            firm_id, name=name, code=code, user_id=user_id, excluding=row.id
        )
        if user_id != row.user_id:
            self._assert_member(firm_id, user_id)
        before = _snapshot(row)
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="salesman.updated",
            entity_type="salesman",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=_snapshot(row),
        )
        self._session.commit()
        return row

    def delete(self, salesman_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Delete an entry nothing names; one in use is made inactive instead."""
        row = self.get(salesman_id, firm_id=firm_id)
        named_by = self.references(row.id, firm_id=firm_id)
        if named_by:
            raise ConflictError(
                f"{row.name} is named on a {', a '.join(named_by)}. "
                "Make the salesman inactive instead: those records keep the name."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="salesman.deleted",
            entity_type="salesman",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=_snapshot(row),
        )
        self._session.commit()

    def restore(self, salesman_id: UUID, *, firm_id: UUID, actor_id: UUID) -> Salesman:
        """Bring back a deleted entry, unless a live one took its name since."""
        row = self._session.scalar(
            select(Salesman).where(
                Salesman.id == salesman_id,
                Salesman.firm_id == firm_id,
                Salesman.is_deleted.is_(True),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Deleted salesman not found.")
        self._assert_unique(
            firm_id,
            name=row.name,
            code=row.code,
            user_id=row.user_id,
            excluding=row.id,
        )
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="salesman.restored",
            entity_type="salesman",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data=_snapshot(row),
        )
        self._session.commit()
        return row
