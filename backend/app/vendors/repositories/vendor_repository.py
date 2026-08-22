"""SQLAlchemy persistence adapter for firm-scoped vendors."""

from datetime import UTC, datetime, time
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.vendors.models import (
    Vendor,
    VendorAddress,
    VendorCategory,
    VendorType,
)
from app.vendors.schemas.vendor import VendorListFilters


class VendorRepository:
    """Centralize vendor queries and firm scoping."""

    SORT_COLUMNS = {
        "code": Vendor.code,
        "name": Vendor.name,
        "status": Vendor.status,
        "created_at": Vendor.created_at,
    }

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def add(self, vendor: Vendor) -> None:
        """Stage a new row for insertion."""
        self._session.add(vendor)

    def add_category(self, category: VendorCategory) -> None:
        """Add category."""
        self._session.add(category)

    def add_type(self, vendor_type: VendorType) -> None:
        """Add type."""
        self._session.add(vendor_type)

    def flush(self) -> None:
        """Push pending work so generated ids are available."""
        self._session.flush()

    def get(
        self, vendor_id: UUID, firm_scope: UUID | None, *, include_deleted: bool
    ) -> Vendor | None:
        """Return one vendor the firm owns."""
        statement = (
            select(Vendor)
            .options(
                selectinload(Vendor.contacts),
                selectinload(Vendor.addresses),
                selectinload(Vendor.bank_accounts),
                selectinload(Vendor.tax_details),
                selectinload(Vendor.attachments),
                selectinload(Vendor.notes),
            )
            .where(Vendor.id == vendor_id)
        )
        if firm_scope is not None:
            statement = statement.where(Vendor.firm_id == firm_scope)
        if not include_deleted:
            statement = statement.where(Vendor.is_deleted.is_(False))
        return self._session.scalar(statement)

    def duplicate_id(
        self,
        firm_id: UUID,
        *,
        code: str,
        gstin: str | None,
        excluding_id: UUID | None = None,
    ) -> UUID | None:
        """Duplicate id."""
        conditions = [Vendor.code == code]
        if gstin:
            conditions.append(Vendor.gstin == gstin)
        statement = select(Vendor.id).where(Vendor.firm_id == firm_id, or_(*conditions))
        if excluding_id is not None:
            statement = statement.where(Vendor.id != excluding_id)
        return self._session.scalar(statement)

    def list_vendors(
        self,
        *,
        firm_scope: UUID | None,
        filters: VendorListFilters,
        search: str | None,
        sort_by: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Vendor], int]:
        """Return a page of vendors for the firm in scope."""
        statement = select(Vendor).options(
            selectinload(Vendor.contacts),
            selectinload(Vendor.addresses),
            selectinload(Vendor.bank_accounts),
            selectinload(Vendor.tax_details),
            selectinload(Vendor.attachments),
            selectinload(Vendor.notes),
        )
        count = select(func.count()).select_from(Vendor)
        conditions = self._conditions(firm_scope, filters)
        statement = statement.where(*conditions)
        count = count.where(*conditions)
        if search:
            term = f"%{search.strip()}%"
            address_match = exists(
                select(VendorAddress.id).where(
                    VendorAddress.vendor_id == Vendor.id,
                    VendorAddress.is_deleted.is_(False),
                    VendorAddress.address_line1.ilike(term),
                )
            )
            condition = or_(
                Vendor.code.ilike(term),
                Vendor.name.ilike(term),
                Vendor.legal_name.ilike(term),
                Vendor.display_name.ilike(term),
                Vendor.gstin.ilike(term),
                Vendor.pan.ilike(term),
                Vendor.email.ilike(term),
                Vendor.phone.ilike(term),
                Vendor.mobile.ilike(term),
                Vendor.status.ilike(term),
                address_match,
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering_column = self.SORT_COLUMNS[sort_by]
        ordering = ordering_column.desc() if descending else ordering_column.asc()
        rows = self._session.scalars(
            statement.order_by(ordering, Vendor.id).offset(offset).limit(limit)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def summary(
        self, firm_scope: UUID | None, filters: VendorListFilters
    ) -> tuple[int, int, int, int, int, int]:
        """Return vendor counts by status."""
        base = select(
            func.count(Vendor.id),
            func.sum(case((Vendor.status == "ACTIVE", 1), else_=0)),
            func.sum(case((Vendor.status == "INACTIVE", 1), else_=0)),
            func.sum(case((Vendor.status == "DRAFT", 1), else_=0)),
            func.sum(case((Vendor.status == "ARCHIVED", 1), else_=0)),
            func.sum(case((Vendor.is_deleted.is_(True), 1), else_=0)),
        ).where(*self._conditions(firm_scope, filters))
        row = self._session.execute(base).one()
        return (
            int(row[0] or 0),
            int(row[1] or 0),
            int(row[2] or 0),
            int(row[3] or 0),
            int(row[4] or 0),
            int(row[5] or 0),
        )

    def list_categories(
        self,
        firm_id: UUID,
        include_deleted: bool,
        *,
        page: int = 1,
        page_size: int = 100,
        search: str | None = None,
    ) -> tuple[list[VendorCategory], int]:
        """Return one page of the firm's vendor categories, and the total.

        Paged since 2026-08-22, when these masters got a screen. They returned
        every row and ignored `search` before that, which nothing noticed
        because the only caller was a dropdown.
        """
        statement = select(VendorCategory).where(VendorCategory.firm_id == firm_id)
        count = (
            select(func.count())
            .select_from(VendorCategory)
            .where(VendorCategory.firm_id == firm_id)
        )
        if not include_deleted:
            statement = statement.where(VendorCategory.is_deleted.is_(False))
            count = count.where(VendorCategory.is_deleted.is_(False))
        if search:
            condition = or_(
                VendorCategory.code.ilike(f"%{search.strip()}%"),
                VendorCategory.name.ilike(f"%{search.strip()}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement.order_by(VendorCategory.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(self._session.scalar(count) or 0)

    def get_category(
        self, category_id: UUID, firm_id: UUID, *, include_deleted: bool
    ) -> VendorCategory | None:
        """Return one vendor category the firm owns."""
        statement = select(VendorCategory).where(
            VendorCategory.id == category_id,
            VendorCategory.firm_id == firm_id,
        )
        if not include_deleted:
            statement = statement.where(VendorCategory.is_deleted.is_(False))
        return self._session.scalar(statement)

    def list_types(
        self,
        firm_id: UUID,
        include_deleted: bool,
        *,
        page: int = 1,
        page_size: int = 100,
        search: str | None = None,
    ) -> tuple[list[VendorType], int]:
        """Return one page of the firm's vendor types, and the total."""
        statement = select(VendorType).where(VendorType.firm_id == firm_id)
        count = (
            select(func.count())
            .select_from(VendorType)
            .where(VendorType.firm_id == firm_id)
        )
        if not include_deleted:
            statement = statement.where(VendorType.is_deleted.is_(False))
            count = count.where(VendorType.is_deleted.is_(False))
        if search:
            condition = or_(
                VendorType.code.ilike(f"%{search.strip()}%"),
                VendorType.name.ilike(f"%{search.strip()}%"),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement.order_by(VendorType.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), int(self._session.scalar(count) or 0)

    def get_type(
        self, type_id: UUID, firm_id: UUID, *, include_deleted: bool
    ) -> VendorType | None:
        """Return type."""
        statement = select(VendorType).where(
            VendorType.id == type_id,
            VendorType.firm_id == firm_id,
        )
        if not include_deleted:
            statement = statement.where(VendorType.is_deleted.is_(False))
        return self._session.scalar(statement)

    def _conditions(
        self,
        firm_scope: UUID | None,
        filters: VendorListFilters,
    ) -> list[ColumnElement[bool]]:
        """Conditions ."""
        conditions: list[ColumnElement[bool]] = []
        scoped_firm = firm_scope or filters.firm_id
        if scoped_firm is not None:
            conditions.append(Vendor.firm_id == scoped_firm)
        if not filters.include_deleted:
            conditions.append(Vendor.is_deleted.is_(False))
        if filters.status is not None:
            conditions.append(Vendor.status == filters.status.value)
        if filters.category_id is not None:
            conditions.append(Vendor.category_id == filters.category_id)
        if filters.type_id is not None:
            conditions.append(Vendor.type_id == filters.type_id)
        if filters.business_profile_id is not None:
            conditions.append(Vendor.business_profile_id == filters.business_profile_id)
        if filters.city_id is not None:
            conditions.append(
                exists(
                    select(VendorAddress.id).where(
                        VendorAddress.vendor_id == Vendor.id,
                        VendorAddress.is_deleted.is_(False),
                        VendorAddress.city_id == filters.city_id,
                    )
                )
            )
        if filters.state_id is not None:
            conditions.append(
                exists(
                    select(VendorAddress.id).where(
                        VendorAddress.vendor_id == Vendor.id,
                        VendorAddress.is_deleted.is_(False),
                        VendorAddress.state_id == filters.state_id,
                    )
                )
            )
        if filters.country_id is not None:
            conditions.append(
                exists(
                    select(VendorAddress.id).where(
                        VendorAddress.vendor_id == Vendor.id,
                        VendorAddress.is_deleted.is_(False),
                        VendorAddress.country_id == filters.country_id,
                    )
                )
            )
        if filters.created_from:
            conditions.append(
                Vendor.created_at
                >= datetime.combine(filters.created_from, time.min, UTC)
            )
        if filters.created_to:
            conditions.append(
                Vendor.created_at <= datetime.combine(filters.created_to, time.max, UTC)
            )
        return conditions
