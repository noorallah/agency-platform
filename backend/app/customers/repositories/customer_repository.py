"""SQLAlchemy persistence adapter for firm-scoped customers."""

from datetime import UTC, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.customers.models import (
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerReceivableTransaction,
)
from app.customers.schemas.customer import CustomerListFilters


class CustomerRepository:
    """Centralize customer queries and firm scoping."""

    SORT_COLUMNS = {
        "code": Customer.code,
        "name": Customer.name,
        "status": Customer.status,
        "credit_limit": Customer.credit_limit,
        "current_outstanding": Customer.current_outstanding,
        "created_at": Customer.created_at,
    }

    def __init__(self, session: Session) -> None:
        """Bind the adapter to one request transaction."""
        self._session = session

    def add(self, customer: Customer) -> None:
        """Stage a new customer."""
        self._session.add(customer)

    def flush(self) -> None:
        """Flush staged records."""
        self._session.flush()

    def get(
        self, customer_id: UUID, firm_scope: UUID | None, *, include_deleted: bool
    ) -> Customer | None:
        """Return one customer inside the caller's firm scope."""
        statement = (
            select(Customer)
            .options(
                selectinload(Customer.addresses),
                selectinload(Customer.contacts),
            )
            .where(Customer.id == customer_id)
        )
        if firm_scope is not None:
            statement = statement.where(Customer.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(Customer.is_deleted.is_(False))
        return self._session.scalar(statement)

    def duplicate_id(
        self,
        firm_id: UUID,
        *,
        code: str,
        gst_number: str | None,
        pan_number: str | None,
        excluding_id: UUID | None = None,
    ) -> UUID | None:
        """Find a conflicting firm-local business identifier."""
        conditions = [Customer.code == code]
        if gst_number:
            conditions.append(Customer.gst_number == gst_number)
        if pan_number:
            conditions.append(Customer.pan_number == pan_number)
        statement = select(Customer.id).where(
            Customer.firm_id == firm_id, or_(*conditions)
        )
        if excluding_id is not None:
            statement = statement.where(Customer.id != excluding_id)
        return self._session.scalar(statement)

    def list_customers(
        self,
        *,
        firm_scope: UUID | None,
        filters: CustomerListFilters,
        search: str | None,
        sort_by: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Customer], int]:
        """Return one filtered and paginated customer page."""
        statement = select(Customer).options(
            selectinload(Customer.addresses),
            selectinload(Customer.contacts),
        )
        count = select(func.count()).select_from(Customer)
        conditions = self._conditions(firm_scope, filters)
        statement = statement.where(*conditions)
        count = count.where(*conditions)
        if search:
            term = f"%{search.strip()}%"
            address_match = exists(
                select(CustomerAddress.id).where(
                    CustomerAddress.customer_id == Customer.id,
                    CustomerAddress.is_deleted.is_(False),
                    CustomerAddress.city.ilike(term),
                )
            )
            condition = or_(
                Customer.code.ilike(term),
                Customer.name.ilike(term),
                Customer.display_name.ilike(term),
                Customer.gst_number.ilike(term),
                Customer.pan_number.ilike(term),
                Customer.email.ilike(term),
                Customer.phone.ilike(term),
                Customer.status.ilike(term),
                address_match,
            )
            statement, count = statement.where(condition), count.where(condition)
        ordering_column = self.SORT_COLUMNS[sort_by]
        ordering = ordering_column.desc() if descending else ordering_column.asc()
        rows = self._session.scalars(
            statement.order_by(ordering, Customer.id).offset(offset).limit(limit)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def summary(
        self, firm_scope: UUID | None, filters: CustomerListFilters
    ) -> tuple[int, int, int, int, int, Decimal, Decimal, Decimal, Decimal]:
        """Aggregate customer lifecycle and financial totals."""
        base = select(
            func.count(Customer.id),
            func.sum(case((Customer.status == "ACTIVE", 1), else_=0)),
            func.sum(case((Customer.status == "INACTIVE", 1), else_=0)),
            func.sum(case((Customer.status == "ON_HOLD", 1), else_=0)),
            func.sum(case((Customer.is_deleted.is_(True), 1), else_=0)),
            func.coalesce(func.sum(Customer.credit_limit), 0),
            func.coalesce(func.sum(Customer.opening_balance), 0),
            func.coalesce(func.sum(Customer.current_outstanding), 0),
            func.coalesce(func.sum(Customer.unapplied_advance_balance), 0),
        )
        base = base.where(*self._conditions(firm_scope, filters))
        row = self._session.execute(base).one()
        return (
            int(row[0] or 0),
            int(row[1] or 0),
            int(row[2] or 0),
            int(row[3] or 0),
            int(row[4] or 0),
            Decimal(row[5] or 0),
            Decimal(row[6] or 0),
            Decimal(row[7] or 0),
            Decimal(row[8] or 0),
        )

    def _conditions(
        self,
        firm_scope: UUID | None,
        filters: CustomerListFilters,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        scoped_firm = firm_scope or filters.firm_id
        if scoped_firm is not None:
            conditions.append(Customer.firm_id == scoped_firm)
        if not filters.include_deleted:
            conditions.append(Customer.is_deleted.is_(False))
        if filters.status is not None:
            conditions.append(Customer.status == filters.status.value)
        if filters.customer_type is not None:
            conditions.append(Customer.customer_type == filters.customer_type.value)
        if filters.city:
            conditions.append(
                exists(
                    select(CustomerAddress.id).where(
                        CustomerAddress.customer_id == Customer.id,
                        CustomerAddress.is_deleted.is_(False),
                        CustomerAddress.city.ilike(filters.city.strip()),
                    )
                )
            )
        if filters.state:
            conditions.append(
                exists(
                    select(CustomerAddress.id).where(
                        CustomerAddress.customer_id == Customer.id,
                        CustomerAddress.is_deleted.is_(False),
                        CustomerAddress.state.ilike(filters.state.strip()),
                    )
                )
            )
        if filters.created_from:
            conditions.append(
                Customer.created_at
                >= datetime.combine(filters.created_from, time.min, UTC)
            )
        if filters.created_to:
            conditions.append(
                Customer.created_at
                <= datetime.combine(filters.created_to, time.max, UTC)
            )
        return conditions

    def active_addresses(self, customer_id: UUID) -> list[CustomerAddress]:
        """Return visible addresses for one customer."""
        return list(
            self._session.scalars(
                select(CustomerAddress)
                .where(
                    CustomerAddress.customer_id == customer_id,
                    CustomerAddress.is_deleted.is_(False),
                )
                .order_by(CustomerAddress.created_at)
            )
        )

    def active_contacts(self, customer_id: UUID) -> list[CustomerContact]:
        """Return visible contacts for one customer."""
        return list(
            self._session.scalars(
                select(CustomerContact)
                .where(
                    CustomerContact.customer_id == customer_id,
                    CustomerContact.is_deleted.is_(False),
                )
                .order_by(CustomerContact.created_at)
            )
        )

    def has_receivable_transactions(self, customer_id: UUID) -> bool:
        """Return whether a customer has any receivable activity rows."""
        return (
            self._session.scalar(
                select(func.count())
                .select_from(CustomerReceivableTransaction)
                .where(
                    CustomerReceivableTransaction.customer_id == customer_id,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                    CustomerReceivableTransaction.transaction_type
                    != "OPENING_BALANCE",
                )
            )
            or 0
        ) > 0

    def list_receivable_transactions(
        self,
        customer_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[CustomerReceivableTransaction], int]:
        """Return paged receivable transactions for one customer."""
        statement = (
            select(CustomerReceivableTransaction)
            .where(
                CustomerReceivableTransaction.customer_id == customer_id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
            .order_by(
                CustomerReceivableTransaction.transaction_date.desc(),
                CustomerReceivableTransaction.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        count = (
            self._session.scalar(
                select(func.count())
                .select_from(CustomerReceivableTransaction)
                .where(
                    CustomerReceivableTransaction.customer_id == customer_id,
                    CustomerReceivableTransaction.is_deleted.is_(False),
                )
            )
            or 0
        )
        rows = list(self._session.scalars(statement).all())
        return rows, int(count)
