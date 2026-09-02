"""Manage the commercial segments a firm sells to.

Distinct from `customers.customer_type`, which is INDIVIDUAL or BUSINESS -- a
legal classification, and the wrong thing to hang a price or an offer on. A
firm that wants to give wholesalers a different rate needs a grouping of its
own choosing.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.customers.models import Customer, CustomerGroup
from app.customers.schemas import CustomerGroupWrite


class CustomerGroupService:
    """Create, read and retire a firm's customer segments."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_groups(
        self, *, firm_id: UUID, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[CustomerGroup], int]:
        """List a firm's segments by name."""
        statement = select(CustomerGroup).where(
            CustomerGroup.firm_id == firm_id, CustomerGroup.is_deleted.is_(False)
        )
        count = (
            select(func.count())
            .select_from(CustomerGroup)
            .where(
                CustomerGroup.firm_id == firm_id, CustomerGroup.is_deleted.is_(False)
            )
        )
        if search:
            token = f"%{search.strip()}%"
            statement = statement.where(CustomerGroup.name.ilike(token))
            count = count.where(CustomerGroup.name.ilike(token))
        rows = list(
            self._session.scalars(
                # Ordered on name, with the id breaking the tie: two segments
                # named alike would otherwise page unstably.
                statement.order_by(CustomerGroup.name.asc(), CustomerGroup.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_group(self, group_id: UUID, *, firm_id: UUID) -> CustomerGroup:
        """Fetch one segment, scoped to the firm."""
        row = self._session.scalar(
            select(CustomerGroup).where(
                CustomerGroup.id == group_id,
                CustomerGroup.firm_id == firm_id,
                CustomerGroup.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Customer group not found.")
        return row

    def create_group(
        self, data: CustomerGroupWrite, *, firm_id: UUID, actor_id: UUID
    ) -> CustomerGroup:
        """Record one segment."""
        self._assert_free(data, firm_id=firm_id)
        row = CustomerGroup(
            firm_id=firm_id,
            code=data.code.strip().upper(),
            name=data.name.strip(),
            description=data.description,
            default_discount_percent=data.default_discount_percent,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="customer_group.created",
            entity_type="customer_group",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "name": row.name},
        )
        self._session.commit()
        return row

    def update_group(
        self,
        group_id: UUID,
        data: CustomerGroupWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CustomerGroup:
        """Replace one segment's details."""
        row = self.get_group(group_id, firm_id=firm_id)
        self._assert_free(data, firm_id=firm_id, excluding=row.id)
        before: dict[str, object] = {
            "name": row.name,
            "rate": str(row.default_discount_percent),
        }
        row.code = data.code.strip().upper()
        row.name = data.name.strip()
        row.description = data.description
        row.default_discount_percent = data.default_discount_percent
        row.is_active = data.is_active
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="customer_group.updated",
            entity_type="customer_group",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={"name": row.name, "rate": str(row.default_discount_percent)},
        )
        self._session.commit()
        return row

    def delete_group(self, group_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Retire a segment nobody is in.

        `ondelete="RESTRICT"` is not a guard on a soft-deleted table -- a soft
        delete never reaches the database's referential check -- so the refusal
        has to live here, or a retired segment would stay wired to every
        customer naming it while vanishing from every list.
        """
        row = self.get_group(group_id, firm_id=firm_id)
        members = int(
            self._session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(
                    Customer.customer_group_id == row.id,
                    Customer.is_deleted.is_(False),
                )
            )
            or 0
        )
        if members:
            raise ValidationError(
                f"{members} customer(s) are still in {row.name}. Move them "
                "first, or the group would vanish from every list while "
                "staying on their records."
            )
        row.is_deleted = True
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="customer_group.deleted",
            entity_type="customer_group",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"code": row.code, "name": row.name},
        )
        self._session.commit()

    def _assert_free(
        self,
        data: CustomerGroupWrite,
        *,
        firm_id: UUID,
        excluding: UUID | None = None,
    ) -> None:
        """Refuse a segment whose code or name is already taken."""
        for column, value, label in (
            (CustomerGroup.code, data.code.strip().upper(), "code"),
            (CustomerGroup.name, data.name.strip(), "name"),
        ):
            statement = select(CustomerGroup).where(
                CustomerGroup.firm_id == firm_id,
                column == value,
                CustomerGroup.is_deleted.is_(False),
            )
            if excluding is not None:
                statement = statement.where(CustomerGroup.id != excluding)
            if self._session.scalar(statement) is not None:
                raise ConflictError(f"A customer group with this {label} exists.")
